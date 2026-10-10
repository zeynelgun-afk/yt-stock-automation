"""Outlier scanner — ROADMAP Faz 2.5.

Weekly sweep of small finance channels: find videos from the last 30
days doing 3x+ the median of their preceding similar-duration uploads ("outliers"), and have the LLM
distill the packaging patterns that are working THIS week (title shapes,
hook shapes, duration). ScriptGenerator injects those patterns into its
prompts as few-shot guidance.

Hard boundary (YouTube "inauthentic content" policy + channel positioning):
patterns are STRUCTURE and PACKAGING only — titles/scripts are never copied,
and fear-clickbait framings are explicitly rejected in the extraction prompt.

Auth: YOUTUBE_API_KEY (Data API v3 key) preferred; falls back to token.json
OAuth if it carries the youtube.readonly scope.

Library module: learning_engine.run_weekly_learning() calls scan_outliers +
extract_patterns weekly and persists the result inside channel_learnings.json
(the scan no longer owns its own file or Telegram messaging).
"""
import json
import os
import logging
import re
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from collections import Counter

from config import YOUTUBE_API_KEY, BASE_DIR, DATA_DIR
from script_generator import ScriptGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    "stock market today",
    "stock market explained",
    "earnings report reaction",
    "congress stock trading",
    "insider buying stocks",
    "fear and greed index",
    "AI stocks analysis",
    "Nvidia stock earnings",
    "Tesla stock analysis",
    "small cap stocks",
]
FINANCE_TITLE = re.compile(r"\b(stock|stocks|market|markets|earnings|shares|insider|trading|nasdaq|treasury|fed|inflation|investing|dividend)\b|S&P", re.I)
OUTSIDE_US_STOCK_NICHE = re.compile(r'\b(pok[eé]mon|cricket|crypto|bitcoin|ethereum|nifty|sensex|nse|bse|bollywood)\b|₹', re.I)
OUTLIER_RATIO = 3.0       # strong signal vs preceding median
MIN_VIEWS = 3_000
MAX_SUBSCRIBERS = 50_000
MIN_BASELINE_VIDEOS = 5
LOOKBACK_DAYS = 30
DISCOVERY_MAX_SUBSCRIBERS = 100_000
DISCOVERY_MIN_VIEWS = 1_000
DISCOVERY_MIN_RATIO = 2.0
DISCOVERY_MIN_BASELINE = 3
BASELINE_MAX_PAGES = 4


def _build_client():
    from googleapiclient.discovery import build

    if YOUTUBE_API_KEY:
        return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    token_path = BASE_DIR / "token.json"
    env_token = os.getenv("YT_LOCAL_TOKEN_JSON", "")
    if token_path.exists() or env_token:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        # Fresh CI runners have the token in Secrets before token.json exists.
        # Read that credential directly; trend scanning must not depend on a
        # later publisher/dedup call creating files as a side effect.
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path))
        else:
            creds = Credentials.from_authorized_user_info(json.loads(env_token))
        if "https://www.googleapis.com/auth/youtube.readonly" in (creds.scopes or []):
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return build("youtube", "v3", credentials=creds)

    raise RuntimeError(
        "Outlier scanner needs YOUTUBE_API_KEY in .env, or a token.json "
        "carrying the youtube.readonly scope."
    )


def duration_bucket(video):
    match = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',
                         video.get('contentDetails', {}).get('duration', ''))
    if not match:
        return 'unknown'
    hours, minutes, seconds = [int(value or 0) for value in match.groups()]
    return 'up_to_180s' if hours * 3600 + minutes * 60 + seconds <= 180 else 'over_180s'


def preceding_baseline(video, uploads):
    bucket = duration_bucket(video)
    if bucket == 'unknown':
        return []
    previous = [r for r in uploads if r['id'] != video['id']
                and r.get('snippet', {}).get('publishedAt', '') < video['snippet']['publishedAt']
                and duration_bucket(r) == bucket and 'liveStreamingDetails' not in r
                and 'viewCount' in r.get('statistics', {})]
    return sorted(previous, key=lambda r: r['snippet']['publishedAt'], reverse=True)[:20]


def finance_context(video):
    snippet = video.get('snippet', {})
    # Company/ticker-only titles may omit "stock". Use the author's description
    # as niche context, never as evidence for financial claims.
    return bool(FINANCE_TITLE.search(snippet.get('title', '') + ' ' +
                                    snippet.get('description', '')[:1500]))


US_EQUITY = re.compile(r'\b(nasdaq|nyse|s&p|dow jones|us stocks?|u\.s\.|american stocks?|nvidia|nvda|tesla|tsla|apple|aapl|microsoft|msft|amazon|amzn|meta|palantir|pltr|gamestop|gme|nike|nke|micron|mu|sofi|uber|apld|celsius|spacex|wall street)\b', re.I)
FOREIGN_MARKET = re.compile(r'\b(india|indian|nifty|sensex|nse|bse|sip|lakh|crore|multibagger|ftse|dax|bist)\b|₹', re.I)
CRYPTO_MARKET = re.compile(r'\b(crypto\w*|bitcoin|ethereum|solana|xrp|defi|altcoins?)\b', re.I)


def outside_stock_niche(video, channel):
    snippet = video.get('snippet', {})
    title = snippet.get('title', '')
    if OUTSIDE_US_STOCK_NICHE.search(title) or FOREIGN_MARKET.search(title):
        return True
    # Search region is a ranking hint, not a market/language filter. Channels
    # based elsewhere may cover US equities; retain explicit US-stock subjects.
    context = channel.get('snippet', {})
    channel_text = context.get('title', '') + ' ' + context.get('description', '')
    explicit_us = bool(US_EQUITY.search(title + ' ' + snippet.get('description', '')[:500]))
    if CRYPTO_MARKET.search(channel_text) and not US_EQUITY.search(title):
        return True
    if context.get('country') == 'IN' and not explicit_us:
        return True
    if FOREIGN_MARKET.search(channel_text) and not explicit_us:
        return True
    return False


def fetch_baseline_uploads(yt, channel, candidate, diagnostics):
    playlist = channel.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
    if not playlist:
        return []
    uploads, page = [], None
    for _ in range(BASELINE_MAX_PAGES):
        res = yt.playlistItems().list(part='contentDetails', playlistId=playlist,
                                     maxResults=50, **({'pageToken': page} if page else {})).execute()
        diagnostics['baseline_pages'] += 1
        ids = [r['contentDetails']['videoId'] for r in res.get('items', [])]
        if ids:
            uploads.extend(yt.videos().list(part='snippet,statistics,contentDetails,liveStreamingDetails',
                                           id=','.join(ids)).execute().get('items', []))
        page = res.get('nextPageToken')
        # Earlier candidates on a prolific channel can sit beyond page one.
        if not page or len(preceding_baseline(candidate, uploads)) >= 20:
            break
    return uploads


def persist_breakouts(videos, diagnostics=None):
    from pathlib import Path
    target = Path('reports'); target.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    evidence = dict(generated_at=stamp, max_subscribers=MAX_SUBSCRIBERS,
                    min_views=MIN_VIEWS, min_ratio=OUTLIER_RATIO,
                    baseline='Median current views of 3–20 earlier videos in the same duration bucket; not equal age.',
                    discovery_thresholds=dict(max_subscribers=DISCOVERY_MAX_SUBSCRIBERS, min_views=DISCOVERY_MIN_VIEWS, min_ratio=DISCOVERY_MIN_RATIO, min_baseline=DISCOVERY_MIN_BASELINE),
                    diagnostics=diagnostics or {}, videos=videos)
    (target / 'small-channel-breakouts.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Küçük kanallarda öne çıkan videolar', '', f'Güncelleme: {stamp}', '',
             'Güçlü sinyal: ≤50.000 abone, ≥3.000 izlenme, ≥3× medyan ve ≥5 geçmiş video. Erken sinyal: ≤100.000 abone, ≥1.000 izlenme, ≥2× medyan ve ≥3 geçmiş video.',
             'Abone sayıları yaklaşık olabilir. İzlenmeler eşit video yaşında ölçülmez. Süre grubu Shorts sınıflaması değildir.', '',
             '| Video / kanal | Sinyal | Abone | İzlenme | Önceki medyan | Kat / örneklem |', '|---|---|---:|---:|---:|---:|']
    for v in videos:
        title = v['title'].replace('|', '/').replace('\n', ' ')
        channel = v['channel'].replace('|', '/')
        lines.append(f"| [{title}]({v['url']}) / {channel} | {v['signal_tier']} | {v['subscribers']} | {v['views']} | {v['baseline_median_views']} | {v['ratio']}× / {v['baseline_samples']} |")
    if not videos:
        lines += ['', 'Bu taramada eşiği geçen doğrulanmış örnek bulunamadı; büyük kanallar otomatik olarak yerine geçirilmedi.']
    lines += ['', 'Tarama özeti: ' + json.dumps(diagnostics or {}, ensure_ascii=False), '']
    lines += ['', 'Bunlar izleyici ilgisi ve anlatım biçimi için adaylardır. Finansal olgular kendi kaynaklarımızla doğrulanır; başlık, senaryo ve espriler kopyalanmaz.', '']
    (target / 'small-channel-breakouts.md').write_text('\n'.join(lines))


def scan_outliers(lookback_days: int = LOOKBACK_DAYS, min_views: int = MIN_VIEWS,
                  min_ratio: float = OUTLIER_RATIO, queries=None,
                  max_subscribers: int = MAX_SUBSCRIBERS) -> List[Dict[str, Any]]:
    yt = _build_client()
    from datetime import timezone
    published_after = (datetime.now(timezone.utc) - timedelta(days=lookback_days)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")

    effective_views = min(min_views, DISCOVERY_MIN_VIEWS)
    effective_subscribers = max(max_subscribers, DISCOVERY_MAX_SUBSCRIBERS)
    effective_ratio = min(min_ratio, DISCOVERY_MIN_RATIO) if min_ratio else 0
    diagnostics = Counter()
    video_ids: List[str] = []
    for q in (SEARCH_QUERIES if queries is None else queries):
        # View-count results favor established channels; relevance exposes niche
        # channels. Date ordering previously spent half the scan on newborn clips.
        for order in ('relevance', 'viewCount'):
            try:
                res = yt.search().list(
                    q=q, part="id", type="video", maxResults=50,
                    publishedAfter=published_after, relevanceLanguage="en",
                    regionCode="US", order=order,
                ).execute()
                diagnostics['search_requests'] += 1
                video_ids += [it["id"]["videoId"] for it in res.get("items", [])]
            except Exception:
                raise RuntimeError("Breakout discovery failed; previous evidence retained") from None
    video_ids = list(dict.fromkeys(video_ids))
    diagnostics['discovered_videos'] = len(video_ids)
    videos: List[Dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        res = yt.videos().list(
            part="statistics,snippet,contentDetails,liveStreamingDetails",
            id=",".join(video_ids[i:i + 50]),
        ).execute()
        videos += res.get("items", [])

    channel_ids = list({v["snippet"]["channelId"] for v in videos})
    channels = {}
    for i in range(0, len(channel_ids), 50):
        res = yt.channels().list(part="statistics,contentDetails,snippet", id=",".join(channel_ids[i:i + 50])).execute()
        channels.update({ch['id']: ch for ch in res.get('items', [])})
    prior_cache = {}
    oldest_candidates = {}
    for video in videos:
        cid = video['snippet']['channelId']
        if cid not in oldest_candidates or video['snippet']['publishedAt'] < oldest_candidates[cid]['snippet']['publishedAt']:
            oldest_candidates[cid] = video

    outliers = []
    per_channel: Dict[str, int] = {}
    for v in videos:
        views = int(v.get("statistics", {}).get("viewCount") or 0)
        channel = channels.get(v['snippet']['channelId'], {})
        stats = channel.get('statistics', {})
        if stats.get('hiddenSubscriberCount') or 'subscriberCount' not in stats:
            diagnostics['unknown_subscribers'] += 1
            continue
        subscribers = int(stats['subscriberCount'])
        if views < effective_views:
            diagnostics['below_views'] += 1
            continue
        if subscribers > effective_subscribers:
            diagnostics['above_subscribers'] += 1
            continue
        # Live-stream VODs (Zee Business "First Trade" etc.) rack up views as
        # recurring broadcasts, not packaging — nothing transferable to model
        if "liveStreamingDetails" in v:
            diagnostics['livestream'] += 1
            continue
        title = v["snippet"]["title"]
        language = v["snippet"].get("defaultAudioLanguage") or v["snippet"].get("defaultLanguage", "")
        if language and not language.lower().startswith("en"):
            diagnostics['non_english'] += 1
            continue
        # Search relevance is only a hint: political speeches and general
        # geopolitical videos can dominate a financial query's raw view count.
        if outside_stock_niche(v, channel):
            diagnostics['outside_us_stock_niche'] += 1
            continue
        if not finance_context(v):
            diagnostics['non_finance_video'] += 1
            continue
        # Model the US/English niche only
        if sum(ord(c) > 127 for c in title) > len(title) * 0.2:
            diagnostics['non_english_title'] += 1
            continue
        channel_id = v['snippet']['channelId']
        if channel_id not in prior_cache:
            prior_cache[channel_id] = fetch_baseline_uploads(yt, channel, oldest_candidates[channel_id], diagnostics)
        baseline = preceding_baseline(v, prior_cache[channel_id])
        if len(baseline) < DISCOVERY_MIN_BASELINE:
            diagnostics['insufficient_baseline'] += 1
            continue
        finance_count = sum(finance_context(r) for r in baseline)
        channel_context = channel.get('snippet', {})
        is_finance_channel = bool(FINANCE_TITLE.search(
            channel_context.get('title', '') + ' ' + channel_context.get('description', '')))
        if not is_finance_channel and finance_count < max(2, len(baseline) / 2):
            diagnostics['non_finance_channel'] += 1
            continue
        avg = statistics.median(int(r.get('statistics', {}).get('viewCount', 0)) for r in baseline)
        if avg <= 0 or (effective_ratio and views < effective_ratio * avg):
            diagnostics['below_ratio'] += 1
            continue
        strong = (views >= min_views and subscribers <= max_subscribers
                  and len(baseline) >= MIN_BASELINE_VIDEOS and views >= min_ratio * avg)
        tier = 'strong' if strong else 'emerging'
        diagnostics[tier] += 1
        # A channel with many simultaneous "outliers" is just a big channel
        # burying the signal — cap so patterns stay diverse
        ch = v["snippet"]["channelId"]
        if per_channel.get(ch, 0) >= 3:
            continue
        per_channel[ch] = per_channel.get(ch, 0) + 1
        outliers.append({
            "video_id": v["id"],
            "signal_tier": tier,
            "url": f"https://www.youtube.com/watch?v={v['id']}",
            "title": v["snippet"]["title"],
            "views": views,
            "subscribers": subscribers,
            "views_per_subscriber": round(views / subscribers, 2) if subscribers else None,
            "baseline_median_views": avg,
            "baseline_samples": len(baseline),
            "baseline_video_ids": [r['id'] for r in baseline],
            "duration_bucket": duration_bucket(v),
            "ratio": round(views / avg, 1) if avg else None,
            "duration": v["contentDetails"]["duration"],
            "publishedAt": v["snippet"]["publishedAt"],
            "channel": v["snippet"]["channelTitle"],
        })
    for o in outliers:
        published = datetime.fromisoformat(o["publishedAt"].replace("Z", "+00:00"))
        age_hours = max(1, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
        o["views_per_hour"] = round(o["views"] / age_hours, 1)
    outliers.sort(key=lambda o: o["ratio"] or 0 if min_ratio else o["views_per_hour"], reverse=True)
    logger.info("Discovery diagnostics: %s", dict(diagnostics))
    logger.info("Found %d %s videos", len(outliers), "outlier" if min_ratio else "recent popular finance")
    result = outliers[:40]
    if queries is None:
        persist_breakouts(result, dict(diagnostics))
    return result


def recent_market_trends() -> List[Dict[str, Any]]:
    """Recent small-channel finance breakouts, cached daily.

    Six searches per cache miss. These are audience-interest signals only;
    FMP remains the source for every published financial claim.
    """
    path = DATA_DIR / "market_trends.json"
    now = datetime.now(timezone.utc)
    try:
        cached = json.loads(path.read_text())
        updated = datetime.fromisoformat(cached["updated_at"])
        if cached.get('strategy') == 'small-channel-breakouts-v2' and 0 <= (now - updated).total_seconds() < 86400:
            return cached["videos"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    videos = scan_outliers(lookback_days=14, min_views=MIN_VIEWS, min_ratio=OUTLIER_RATIO, queries=[
        "US stock market news", "stock earnings reaction", "US insider buying stocks",
    ])[:15]
    path.write_text(json.dumps({"updated_at": now.isoformat(), "strategy": "small-channel-breakouts-v2", "videos": videos}, indent=2))
    return videos


def extract_patterns(outliers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """LLM distills structure/packaging patterns — never copyable content."""
    sg = ScriptGenerator()
    prompt = f"""You are a YouTube growth analyst for a data-first, no-hype US stock market channel.

Here are recent finance-niche candidates. Strong signals: <=50,000 subscribers,
>=3,000 views, >=3x the median of 5–20 prior similar-duration uploads. Emerging
signals: <=100,000 subscribers, >=1,000 views, >=2x median and 3–20 prior uploads.
Keep signal tiers distinct; do not present emerging evidence as a strong outlier:
{json.dumps(outliers, indent=1)}

Extract the PACKAGING PATTERNS that are working this week. Patterns must be structural
(title shapes, framing devices, number usage, duration sweet spots) — NEVER copyable titles.
REJECT fear-clickbait patterns (doom thumbnails, "everything will collapse" framing):
this channel's positioning is "no hype, just numbers".
You have titles, durations, approximate subscriber counts and current view counts,
NOT transcripts or retention curves. Baseline counts are NOT equal-age measurements.
A <=180-second duration bucket is NOT proof that a video is a Short.
Prefer transferable questions and concrete companies/events over generic market panic.
Suggest original, brief dry humor or everyday analogies only as hypotheses; metadata
cannot prove a creator used comedy. Never copy a title, a joke or a script.
Hook suggestions are hypotheses, not measured evidence of successful opening lines.
Do not infer causal performance or apply long-video durations to Shorts.

Return strictly valid JSON:
- "title_patterns": array of 5-8 abstract title templates (e.g. "[TICKER] just did [specific unrounded number] — here's why")
- "hook_patterns": array of 3-5 opening-line shapes
- "packaging_notes": array of 3-5 short observations (duration, numbers, framing)
"""
    return sg._call_llm(prompt, default_title="outlier pattern extraction")


if __name__ == "__main__":
    outliers = scan_outliers()
    print(f"{len(outliers)} outliers")
    for o in outliers[:10]:
        print(f"{o['ratio']:5.1f}x {o['views']:>10,}  {o['title'][:70]}")
    if outliers:
        print(json.dumps(extract_patterns(outliers), indent=1))
