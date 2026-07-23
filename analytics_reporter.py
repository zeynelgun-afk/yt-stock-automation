"""Analytics feedback loop — ROADMAP Faz 4.3.

Pulls per-video YouTube Analytics for the last N days and sends a weekly
performance digest to Telegram: views, average view percentage (the Shorts
swipe-away proxy), watch time and subscriber gains, tagged by franchise
(parsed from the video title where possible).

Requires token.json with the readonly + yt-analytics scopes. Tokens created
before those scopes were added to youtube_publisher.SCOPES must be
re-consented once: delete token.json and run any upload to re-auth.

Cron: run weekly (see README) — `python analytics_reporter.py`.
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

from config import BASE_DIR
from telegram_bot import TelegramApprovalBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN_PATH = BASE_DIR / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Success targets from ROADMAP — flag videos against these
TARGET_AVG_VIEW_PCT_SHORTS = 80.0


def _get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not TOKEN_PATH.exists():
        raise RuntimeError("token.json not found — run an upload once to authenticate.")
    # Load WITHOUT forcing scopes: passing them would mask what was actually
    # granted, and refresh would then die with invalid_scope
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    granted = set(creds.scopes or [])
    if not set(SCOPES).issubset(granted):
        raise RuntimeError(
            "token.json lacks analytics scopes. Delete token.json and run one "
            "upload to re-consent with the new scope list."
        )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def fetch_video_stats(days: int = 7):
    """Per-video analytics rows for the last `days` days, most-viewed first."""
    from googleapiclient.discovery import build

    creds = _get_credentials()
    yt_analytics = build("youtubeAnalytics", "v2", credentials=creds)
    yt_data = build("youtube", "v3", credentials=creds)

    end = datetime.now().date()
    start = end - timedelta(days=days)
    resp = yt_analytics.reports().query(
        ids="channel==MINE",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics=("views,estimatedMinutesWatched,averageViewDuration,"
                 "averageViewPercentage,subscribersGained"),
        dimensions="video",
        sort="-views",
        maxResults=25,
    ).execute()

    rows = resp.get("rows", [])
    if not rows:
        return []

    ids = [r[0] for r in rows]
    titles = {}
    meta = yt_data.videos().list(part="snippet", id=",".join(ids)).execute()
    for item in meta.get("items", []):
        titles[item["id"]] = item["snippet"]["title"]

    return [{
        "video_id": r[0],
        "title": titles.get(r[0], r[0]),
        "views": int(r[1]),
        "watch_minutes": int(r[2]),
        "avg_view_seconds": round(r[3]),
        "avg_view_pct": round(r[4], 1),
        "subs_gained": int(r[5]),
    } for r in rows]


def build_report(days: int = 7) -> str:
    stats = fetch_video_stats(days)
    if not stats:
        return f"📊 Haftalık rapor: son {days} günde izlenme verisi yok."

    total_views = sum(s["views"] for s in stats)
    total_subs = sum(s["subs_gained"] for s in stats)
    lines = [
        f"📊 HAFTALIK PERFORMANS ({days} gün)",
        f"Toplam izlenme: {total_views:,} | Yeni abone: {total_subs:+d}",
        "",
    ]
    for s in stats[:10]:
        flag = "✅" if s["avg_view_pct"] >= TARGET_AVG_VIEW_PCT_SHORTS else "⚠️"
        lines.append(
            f"{flag} {s['views']:,} izl. | APV %{s['avg_view_pct']} "
            f"({s['avg_view_seconds']}sn) | +{s['subs_gained']} abone\n"
            f"   {s['title'][:70]}"
        )
    lines.append("")
    lines.append(f"Hedef: APV ≥ %{TARGET_AVG_VIEW_PCT_SHORTS:.0f} (Shorts). "
                 "⚠️ işaretli formatların hook/loop kurgusunu gözden geçir.")
    return "\n".join(lines)


def send_weekly_report(days: int = 7) -> bool:
    try:
        report = build_report(days)
    except Exception as e:
        report = f"🚨 Analytics raporu üretilemedi: {e}"
        logger.error(report)
    return TelegramApprovalBot().send_text(report)


if __name__ == "__main__":
    print(build_report())
