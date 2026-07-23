"""Outlier scanner — ROADMAP Faz 2.5.

Weekly sweep of the finance niche on YouTube: find videos from the last 30
days doing 3x+ their channel's average views ("outliers"), have the LLM
distill the packaging patterns that are working THIS week (title shapes,
hook shapes, duration), and persist them to data/packaging_patterns.json.
ScriptGenerator injects those patterns into its prompts as few-shot guidance.

Hard boundary (YouTube "inauthentic content" policy + channel positioning):
patterns are STRUCTURE and PACKAGING only — titles/scripts are never copied,
and fear-clickbait framings are explicitly rejected in the extraction prompt.

Auth: YOUTUBE_API_KEY (Data API v3 key) preferred; falls back to token.json
OAuth if it carries the youtube.readonly scope.

Cron: weekly, together with the analytics report (see workflow).
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from config import YOUTUBE_API_KEY, BASE_DIR, PATTERNS_FILE
from script_generator import ScriptGenerator, ScriptGenerationError
from telegram_bot import TelegramApprovalBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    "stock market today",
    "stock market crash",
    "earnings report reaction",
    "congress stock trading",
    "insider buying stocks",
    "fear and greed index",
]
OUTLIER_RATIO = 3.0       # video views vs channel average
MIN_VIEWS = 10_000
LOOKBACK_DAYS = 30


def _build_client():
    from googleapiclient.discovery import build

    if YOUTUBE_API_KEY:
        return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    token_path = BASE_DIR / "token.json"
    if token_path.exists():
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_file(str(token_path))
        if "https://www.googleapis.com/auth/youtube.readonly" in (creds.scopes or []):
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return build("youtube", "v3", credentials=creds)

    raise RuntimeError(
        "Outlier scanner needs YOUTUBE_API_KEY in .env, or a token.json "
        "carrying the youtube.readonly scope."
    )


def scan_outliers() -> List[Dict[str, Any]]:
    yt = _build_client()
    published_after = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")

    video_ids: List[str] = []
    for q in SEARCH_QUERIES:
        try:
            res = yt.search().list(
                q=q, part="id", type="video", maxResults=25,
                publishedAfter=published_after, relevanceLanguage="en", order="viewCount",
            ).execute()
            video_ids += [it["id"]["videoId"] for it in res.get("items", [])]
        except Exception as e:
            logger.warning(f"Search failed for '{q}': {e}")
    video_ids = list(dict.fromkeys(video_ids))
    if not video_ids:
        return []

    videos: List[Dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        res = yt.videos().list(
            part="statistics,snippet,contentDetails", id=",".join(video_ids[i:i + 50])
        ).execute()
        videos += res.get("items", [])

    channel_ids = list({v["snippet"]["channelId"] for v in videos})
    channel_avg: Dict[str, float] = {}
    for i in range(0, len(channel_ids), 50):
        res = yt.channels().list(part="statistics", id=",".join(channel_ids[i:i + 50])).execute()
        for ch in res.get("items", []):
            st = ch.get("statistics", {})
            n = int(st.get("videoCount") or 0)
            channel_avg[ch["id"]] = (int(st.get("viewCount") or 0) / n) if n else 0.0

    outliers = []
    for v in videos:
        views = int(v.get("statistics", {}).get("viewCount") or 0)
        avg = channel_avg.get(v["snippet"]["channelId"], 0.0)
        if views < MIN_VIEWS or not avg or views < OUTLIER_RATIO * avg:
            continue
        outliers.append({
            "title": v["snippet"]["title"],
            "views": views,
            "ratio": round(views / avg, 1),
            "duration": v["contentDetails"]["duration"],
            "publishedAt": v["snippet"]["publishedAt"][:10],
            "channel": v["snippet"]["channelTitle"],
        })
    outliers.sort(key=lambda o: o["ratio"], reverse=True)
    logger.info(f"Found {len(outliers)} outlier videos")
    return outliers[:40]


def extract_patterns(outliers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """LLM distills structure/packaging patterns — never copyable content."""
    sg = ScriptGenerator()
    prompt = f"""You are a YouTube growth analyst for a data-first, no-hype US stock market channel.

Here are finance-niche OUTLIER videos from the last 30 days (each did {OUTLIER_RATIO}x+ its channel's average views):
{json.dumps(outliers, indent=1)}

Extract the PACKAGING PATTERNS that are working this week. Patterns must be structural
(title shapes, framing devices, number usage, duration sweet spots) — NEVER copyable titles.
REJECT fear-clickbait patterns (doom thumbnails, "everything will collapse" framing):
this channel's positioning is "no hype, just numbers".

Return strictly valid JSON:
- "title_patterns": array of 5-8 abstract title templates (e.g. "[TICKER] just did [specific unrounded number] — here's why")
- "hook_patterns": array of 3-5 opening-line shapes
- "packaging_notes": array of 3-5 short observations (duration, numbers, framing)
"""
    return sg._call_llm(prompt, default_title="outlier pattern extraction")


def save_patterns(patterns: Dict[str, Any]) -> None:
    patterns["updated_at"] = datetime.now().isoformat(timespec="seconds")
    PATTERNS_FILE.write_text(json.dumps(patterns, indent=1, ensure_ascii=False))
    logger.info(f"Patterns saved to {PATTERNS_FILE}")


def run_weekly_scan() -> bool:
    bot = TelegramApprovalBot()
    try:
        outliers = scan_outliers()
        if not outliers:
            return bot.send_text("🔭 Outlier taraması: bu hafta outlier video bulunamadı.")
        patterns = extract_patterns(outliers)
        save_patterns(patterns)
        top = "\n".join(f"• {o['ratio']}x — {o['title'][:60]}" for o in outliers[:5])
        return bot.send_text(
            f"🔭 OUTLIER TARAMASI ({len(outliers)} video)\n\nEn güçlüler:\n{top}\n\n"
            f"Kalıplar güncellendi → sonraki videolar bu hafta çalışan paketlemeyi kullanacak."
        )
    except (RuntimeError, ScriptGenerationError) as e:
        logger.error(f"Outlier scan failed: {e}")
        return bot.send_text(f"🚨 Outlier taraması başarısız: {e}")


if __name__ == "__main__":
    outliers = scan_outliers()
    print(f"{len(outliers)} outliers")
    for o in outliers[:10]:
        print(f"{o['ratio']:5.1f}x {o['views']:>10,}  {o['title'][:70]}")
    if outliers:
        patterns = extract_patterns(outliers)
        save_patterns(patterns)
        print(json.dumps(patterns, indent=1))
