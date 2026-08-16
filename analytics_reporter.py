"""Analytics feedback loop — ROADMAP Faz 4.3 + Faz 5.1.

Pulls per-video YouTube Analytics for the last N days and sends a weekly
performance digest to Telegram: views, average view percentage (the Shorts
swipe-away proxy), watch time and subscriber gains, tagged by franchise
(parsed from the video title where possible).

Faz 5.1: the same stats feed compute_franchise_weights(), which the story
selector multiplies into candidate scores — formats that hold viewers get
picked more often, underperformers less. CI is stateless, so weights are
recomputed from the channel itself on every run instead of persisted.

Requires token.json with the readonly + yt-analytics scopes. Tokens created
before those scopes were added to youtube_publisher.SCOPES must be
re-consented once: delete token.json and run any upload to re-auth.

Cron: run weekly (see README) — `python analytics_reporter.py`.
"""
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from config import BASE_DIR
from telegram_bot import TelegramApprovalBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN_PATH = BASE_DIR / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Success targets from ROADMAP — flag videos against these.
# Long recaps structurally cannot hit Shorts-level APV (nobody watches 80% of
# a 6-minute video); holding them to 80 flagged every recap ⚠️ forever, which
# trains the reader to ignore the flag.
TARGET_AVG_VIEW_PCT_SHORTS = 80.0
TARGET_AVG_VIEW_PCT_LONG = 45.0
LONG_VIDEO_MIN_SECONDS = 90


def _iso_duration_to_seconds(iso: str) -> int:
    """PT#H#M#S -> seconds (YouTube contentDetails.duration)."""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(g or 0) for g in m.groups())
    return h * 3600 + mi * 60 + s


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
        # 25 truncated the tail: at 4-5 uploads/weekday a 14-day window has
        # ~50 videos, and dropping the low-view ones biased franchise weights
        # toward whatever already got views
        maxResults=200,
    ).execute()

    rows = resp.get("rows", [])
    if not rows:
        return []

    ids = [r[0] for r in rows]
    titles: Dict[str, str] = {}
    durations: Dict[str, int] = {}
    for i in range(0, len(ids), 50):   # videos.list caps at 50 ids per call
        meta = yt_data.videos().list(
            part="snippet,contentDetails", id=",".join(ids[i:i + 50])).execute()
        for item in meta.get("items", []):
            titles[item["id"]] = item["snippet"]["title"]
            durations[item["id"]] = _iso_duration_to_seconds(
                item.get("contentDetails", {}).get("duration", ""))

    return [{
        "video_id": r[0],
        "title": titles.get(r[0], r[0]),
        "views": int(r[1]),
        "watch_minutes": int(r[2]),
        "avg_view_seconds": round(r[3]),
        "avg_view_pct": round(r[4], 1),
        "subs_gained": int(r[5]),
        "is_long": durations.get(r[0], 0) >= LONG_VIDEO_MIN_SECONDS,
    } for r in rows]


# ---------- Faz 5.1: analytics -> story-selector feedback ----------

# Order matters: first matching franchise wins. Matched case-insensitively
# against upload titles — the only durable franchise record on stateless CI.
FRANCHISE_KEYWORDS = [
    ("insider_watch", ("insider",)),
    ("congress_trade", ("congress", "senator", "politician", "capitol")),
    ("earnings_shock", ("earnings", "eps")),
    ("reddit_radar", ("reddit", "wsb", "wallstreetbets")),
    ("analyst_shock", ("analyst", "price target")),
    ("fear_gauge", ("fear", "greed", "vix")),
    ("market_close", ("market close", "s&p", "nasdaq", "dow", "recap")),
]


def classify_franchise(title: str) -> Optional[str]:
    t = title.lower()
    for franchise, keys in FRANCHISE_KEYWORDS:
        if any(k in t for k in keys):
            return franchise
    return None


def compute_franchise_weights(days: int = 14, min_videos: int = 2,
                              lo: float = 0.7, hi: float = 1.3) -> Dict[str, float]:
    """Score multiplier per franchise from recent per-video performance.

    perf = views x avg_view_pct: a video only counts as much of it as viewers
    actually watched. Franchises with fewer than `min_videos` classified
    uploads stay unweighted so new formats keep getting explored, and the
    clamp keeps one hot streak from monopolizing the channel.
    """
    per: Dict[str, List[float]] = {}
    for s in fetch_video_stats(days):
        fr = classify_franchise(s["title"])
        if fr:
            per.setdefault(fr, []).append(s["views"] * s["avg_view_pct"] / 100.0)

    scored = {f: sum(v) / len(v) for f, v in per.items() if len(v) >= min_videos}
    if not scored:
        return {}
    overall = sum(scored.values()) / len(scored)
    if overall <= 0:
        return {}
    return {f: round(min(hi, max(lo, perf / overall)), 2) for f, perf in scored.items()}


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
        target = TARGET_AVG_VIEW_PCT_LONG if s.get("is_long") else TARGET_AVG_VIEW_PCT_SHORTS
        kind = "📺" if s.get("is_long") else "📱"
        flag = "✅" if s["avg_view_pct"] >= target else "⚠️"
        lines.append(
            f"{flag}{kind} {s['views']:,} izl. | APV %{s['avg_view_pct']} "
            f"({s['avg_view_seconds']}sn) | +{s['subs_gained']} abone\n"
            f"   {s['title'][:70]}"
        )
    lines.append("")
    lines.append(f"Hedef: APV ≥ %{TARGET_AVG_VIEW_PCT_SHORTS:.0f} (📱 Shorts), "
                 f"≥ %{TARGET_AVG_VIEW_PCT_LONG:.0f} (📺 uzun). "
                 "⚠️ işaretli formatların hook/loop kurgusunu gözden geçir.")

    try:
        weights = compute_franchise_weights()
        if weights:
            lines.append("")
            lines.append("⚖️ Otomatik format ağırlıkları (son 14 gün — hikâye seçici bunları uyguluyor):")
            for f, w in sorted(weights.items(), key=lambda kv: -kv[1]):
                arrow = "📈" if w > 1 else ("📉" if w < 1 else "➖")
                lines.append(f"  {arrow} {f}: x{w}")
        else:
            lines.append("")
            lines.append("⚖️ Format ağırlıkları: henüz yeterli veri yok (format başına ≥2 video gerekli).")
    except Exception as e:
        logger.warning(f"Could not append franchise weights to report: {e}")

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
