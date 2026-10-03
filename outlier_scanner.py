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
]
FINANCE_TITLE = re.compile(r"\b(stock|stocks|market|markets|earnings|shares|insider|trading|nasdaq|treasury|fed|inflation|investing|dividend)\b|S&P", re.I)
OUTLIER_RATIO = 3.0       # video views vs channel average
MIN_VIEWS = 3_000
MAX_SUBSCRIBERS = 50_000
MIN_BASELINE_VIDEOS = 5
LOOKBACK_DAYS = 30


def _build_client():
    from googleapiclient.discovery import build

    if YOUTUBE_API_KEY:
        return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    token_path = BASE_DIR / "token.json"
    env_token = os.getenv("YOUTUBE_TOKEN_JSON", "")
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


def persist_breakouts(videos):
    from pathlib import Path
    target = Path('reports'); target.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    evidence = dict(generated_at=stamp, max_subscribers=MAX_SUBSCRIBERS,
                    min_views=MIN_VIEWS, min_ratio=OUTLIER_RATIO,
                    baseline='Median current views of 5–20 earlier videos in the same duration bucket; not equal age.',
                    videos=videos)
    (target / 'small-channel-breakouts.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Küçük kanallarda öne çıkan videolar', '', f'Güncelleme: {stamp}', '',
             'Eşikler: en fazla 50.000 abone, en az 3.000 izlenme ve önceki 5–20 benzer süreli videonun medyanının en az 3 katı.',
             'Abone sayıları yaklaşık olabilir. İzlenmeler eşit video yaşında ölçülmez. Süre grubu Shorts sınıflaması değildir.', '',
             '| Video / kanal | Abone | İzlenme | Önceki medyan | Kat / örneklem |', '|---|---:|---:|---:|---:|']
    for v in videos:
        title = v['title'].replace('|', '/').replace('\n', ' ')
        channel = v['channel'].replace('|', '/')
        lines.append(f"| [{title}]({v['url']}) / {channel} | {v['subscribers']} | {v['views']} | {v['baseline_median_views']} | {v['ratio']}× / {v['baseline_samples']} |")
    if not videos:
        lines += ['', 'Bu taramada eşiği geçen doğrulanmış örnek bulunamadı; büyük kanallar otomatik olarak yerine geçirilmedi.']
    lines += ['', 'Bunlar izleyici ilgisi ve anlatım biçimi için adaylardır. Finansal olgular kendi kaynaklarımızla doğrulanır; başlık, senaryo ve espriler kopyalanmaz.', '']
    (target / 'small-channel-breakouts.md').write_text('\n'.join(lines))


def scan_outliers(lookback_days: int = LOOKBACK_DAYS, min_views: int = MIN_VIEWS,
                  min_ratio: float = OUTLIER_RATIO, queries=None,
                  max_subscribers: int = MAX_SUBSCRIBERS) -> List[Dict[str, Any]]:
    yt = _build_client()
    from datetime import timezone
    published_after = (datetime.now(timezone.utc) - timedelta(days=lookback_days)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")

    video_ids: List[str] = []
    for query_index, q in enumerate(SEARCH_QUERIES if queries is None else queries):
        try:
            res = yt.search().list(
                q=q, part="id", type="video", maxResults=25,
                publishedAfter=published_after, relevanceLanguage="en",
                regionCode="US", order="viewCount" if query_index % 2 == 0 else "date",
            ).execute()
            video_ids += [it["id"]["videoId"] for it in res.get("items", [])]
        except Exception as e:
            raise RuntimeError("Breakout discovery failed; previous evidence retained") from None
    video_ids = list(dict.fromkeys(video_ids))
    if not video_ids:
        return []

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
        res = yt.channels().list(part="statistics,contentDetails", id=",".join(channel_ids[i:i + 50])).execute()
        channels.update({ch['id']: ch for ch in res.get('items', [])})
    prior_cache = {}

    outliers = []
    per_channel: Dict[str, int] = {}
    for v in videos:
        views = int(v.get("statistics", {}).get("viewCount") or 0)
        channel = channels.get(v['snippet']['channelId'], {})
        stats = channel.get('statistics', {})
        if stats.get('hiddenSubscriberCount') or 'subscriberCount' not in stats:
            continue
        subscribers = int(stats['subscriberCount'])
        if views < min_views or subscribers > max_subscribers:
            continue
        # Live-stream VODs (Zee Business "First Trade" etc.) rack up views as
        # recurring broadcasts, not packaging — nothing transferable to model
        if "liveStreamingDetails" in v:
            continue
        title = v["snippet"]["title"]
        language = v["snippet"].get("defaultAudioLanguage") or v["snippet"].get("defaultLanguage", "")
        if language and not language.lower().startswith("en"):
            continue
        # Search relevance is only a hint: political speeches and general
        # geopolitical videos can dominate a financial query's raw view count.
        if not re.search(r"\b(stock|stocks|market|markets|earnings|shares|insider|trading|nasdaq|treasury|fed|inflation|investing)\b|S&P", title, re.I):
            continue
        # Model the US/English niche only
        if sum(ord(c) > 127 for c in title) > len(title) * 0.2:
            continue
        channel_id = v['snippet']['channelId']
        if channel_id not in prior_cache:
            playlist = channel.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
            if not playlist:
                continue
            ids = [r['contentDetails']['videoId'] for r in yt.playlistItems().list(
                part='contentDetails', playlistId=playlist, maxResults=50).execute().get('items', [])]
            prior_cache[channel_id] = yt.videos().list(
                part='snippet,statistics,contentDetails,liveStreamingDetails',
                id=','.join(ids)).execute().get('items', []) if ids else []
        baseline = preceding_baseline(v, prior_cache[channel_id])
        if len(baseline) < MIN_BASELINE_VIDEOS:
            continue
        # A gaming/political clip mentioning trading is not a finance-channel signal.
        finance_count = sum(bool(FINANCE_TITLE.search(r.get('snippet', {}).get('title', ''))) for r in baseline)
        if finance_count < max(3, len(baseline) / 2):
            continue
        avg = statistics.median(int(r.get('statistics', {}).get('viewCount', 0)) for r in baseline)
        if avg <= 0 or (min_ratio and views < min_ratio * avg):
            continue
        # A channel with many simultaneous "outliers" is just a big channel
        # burying the signal — cap so patterns stay diverse
        ch = v["snippet"]["channelId"]
        if per_channel.get(ch, 0) >= 3:
            continue
        per_channel[ch] = per_channel.get(ch, 0) + 1
        outliers.append({
            "video_id": v["id"],
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
    logger.info("Found %d %s videos", len(outliers), "outlier" if min_ratio else "recent popular finance")
    result = outliers[:40]
    if queries is None:
        persist_breakouts(result)
    return result


def recent_market_trends() -> List[Dict[str, Any]]:
    """Recent small-channel finance breakouts, cached daily.

    Three searches per cache miss. These are audience-interest signals only;
    FMP remains the source for every published financial claim.
    """
    path = DATA_DIR / "market_trends.json"
    now = datetime.now(timezone.utc)
    try:
        cached = json.loads(path.read_text())
        updated = datetime.fromisoformat(cached["updated_at"])
        if cached.get('strategy') == 'small-channel-breakouts-v1' and 0 <= (now - updated).total_seconds() < 86400:
            return cached["videos"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    videos = scan_outliers(lookback_days=14, min_views=MIN_VIEWS, min_ratio=OUTLIER_RATIO, queries=[
        "US stock market news", "stock earnings reaction", "US insider buying stocks",
    ])[:15]
    path.write_text(json.dumps({"updated_at": now.isoformat(), "strategy": "small-channel-breakouts-v1", "videos": videos}, indent=2))
    return videos


def extract_patterns(outliers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """LLM distills structure/packaging patterns — never copyable content."""
    sg = ScriptGenerator()
    prompt = f"""You are a YouTube growth analyst for a data-first, no-hype US stock market channel.

Here are finance-niche OUTLIER videos from the last 30 days from channels with at most {MAX_SUBSCRIBERS} subscribers (at least {OUTLIER_RATIO}x the
median views of 5–20 earlier public videos in the same duration bucket):
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
