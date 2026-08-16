"""Outlier scanner — ROADMAP Faz 2.5.

Weekly sweep of the finance niche on YouTube: find videos from the last 30
days doing 3x+ their channel's average views ("outliers"), and have the LLM
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
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from config import YOUTUBE_API_KEY, BASE_DIR
from script_generator import ScriptGenerator

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
    from datetime import timezone
    published_after = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")

    video_ids: List[str] = []
    for q in SEARCH_QUERIES:
        try:
            res = yt.search().list(
                q=q, part="id", type="video", maxResults=25,
                publishedAfter=published_after, relevanceLanguage="en",
                regionCode="US", order="viewCount",
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
            part="statistics,snippet,contentDetails,liveStreamingDetails",
            id=",".join(video_ids[i:i + 50]),
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
    per_channel: Dict[str, int] = {}
    for v in videos:
        views = int(v.get("statistics", {}).get("viewCount") or 0)
        avg = channel_avg.get(v["snippet"]["channelId"], 0.0)
        if views < MIN_VIEWS or not avg or views < OUTLIER_RATIO * avg:
            continue
        # Live-stream VODs (Zee Business "First Trade" etc.) rack up views as
        # recurring broadcasts, not packaging — nothing transferable to model
        if "liveStreamingDetails" in v:
            continue
        title = v["snippet"]["title"]
        # Model the US/English niche only
        if sum(ord(c) > 127 for c in title) > len(title) * 0.2:
            continue
        # A channel with many simultaneous "outliers" is just a big channel
        # burying the signal — cap so patterns stay diverse
        ch = v["snippet"]["channelId"]
        if per_channel.get(ch, 0) >= 3:
            continue
        per_channel[ch] = per_channel.get(ch, 0) + 1
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


if __name__ == "__main__":
    outliers = scan_outliers()
    print(f"{len(outliers)} outliers")
    for o in outliers[:10]:
        print(f"{o['ratio']:5.1f}x {o['views']:>10,}  {o['title'][:70]}")
    if outliers:
        print(json.dumps(extract_patterns(outliers), indent=1))
