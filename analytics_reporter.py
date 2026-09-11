"""Analytics feedback loop — ROADMAP Faz 4.3 + Faz 5.1.

Pulls per-video YouTube Analytics for the last N days and sends a weekly
performance digest to Telegram: views, engaged views, average view percentage,
watch time and subscriber gains, tagged by franchise. APV is NOT swipe-away.
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

    end = datetime.now().date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    resp = yt_analytics.reports().query(
        ids="channel==MINE",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics=("views,engagedViews,estimatedMinutesWatched,averageViewDuration,"
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

    # The live API rejects video + creatorContentType as joint dimensions.
    # Use its supported lowercase filter to classify Shorts accurately; a
    # duration heuristic mislabels vertical Shorts longer than 90 seconds.
    short_rows = yt_analytics.reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
        dimensions="video", filters="creatorContentType==shorts", metrics="views",
        sort="-views", maxResults=200,
    ).execute().get("rows", [])
    short_ids = {r[0] for r in short_rows}

    ids = [r[0] for r in rows]
    titles: Dict[str, str] = {}
    durations: Dict[str, int] = {}
    machine: Dict[str, Dict[str, str]] = {}
    published: Dict[str, str] = {}
    for i in range(0, len(ids), 50):   # videos.list caps at 50 ids per call
        meta = yt_data.videos().list(
            part="snippet,contentDetails", id=",".join(ids[i:i + 50])).execute()
        for item in meta.get("items", []):
            titles[item["id"]] = item["snippet"]["title"]
            published[item["id"]] = item["snippet"].get("publishedAt", "")
            durations[item["id"]] = _iso_duration_to_seconds(
                item.get("contentDetails", {}).get("duration", ""))
            # Machine tags stamped at upload (invisible to viewers): fr:=exact
            # franchise, w:=script word count, v:=voice engine. They make the
            # channel itself the durable per-video metadata store on stateless
            # CI — no more guessing the franchise from title keywords.
            machine[item["id"]] = {
                k: v for k, _, v in
                (t.partition(":") for t in item["snippet"].get("tags", []))
                if k in ("fr", "w", "v", "fmt") and v
            }

    # Read returned headers instead of relying on dimension/metric positions.
    names = [c["name"] for c in resp["columnHeaders"]]
    result = []
    for values in rows:
        r = dict(zip(names, values))
        vid = r["video"]
        content_type = "shorts" if vid in short_ids else "videoondemand"
        result.append({
            "video_id": vid,
            "title": titles.get(vid, vid),
            "published_at": published.get(vid, ""),
            "views": int(r["views"]),
            "engaged_views": int(r["engagedViews"]),
            "watch_minutes": float(r["estimatedMinutesWatched"]),
            "avg_view_seconds": round(r["averageViewDuration"], 1),
            "avg_view_pct": round(r["averageViewPercentage"], 1),
            "subs_gained": int(r["subscribersGained"]),
            "duration_s": durations.get(vid, 0),
            "content_type": content_type,
            "is_long": content_type != "shorts",
            "machine": machine.get(vid, {}),
            "franchise": machine.get(vid, {}).get("fr") or classify_franchise(titles.get(vid, "")),
        })
    return result


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
                              lo: float = 0.7, hi: float = 1.3,
                              stats: Optional[List[Dict]] = None) -> Dict[str, float]:
    """Score multiplier per franchise from recent per-video performance.

    Compare Shorts only, using engaged views and capped completion. Tiny
    samples and exceptional replay loops must not dominate editorial choices.
    Franchises with fewer than `min_videos` classified
    uploads stay unweighted so new formats keep getting explored, and the
    clamp keeps one hot streak from monopolizing the channel.
    """
    per: Dict[str, List[float]] = {}
    for s in (fetch_video_stats(days) if stats is None else stats):
        engaged = s.get("engaged_views", 0)
        if s.get("is_long") or engaged < 20:
            continue
        fr = s.get("franchise")   # machine tag when present, else title keywords
        if fr:
            per.setdefault(fr, []).append(engaged * min(100, max(0, s["avg_view_pct"])) / 100.0)

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
            f"{flag}{kind} {s['views']:,} izl. / {s['engaged_views']:,} engaged | APV %{s['avg_view_pct']} "
            f"({s['avg_view_seconds']}sn) | +{s['subs_gained']} abone\n"
            f"   {s['title'][:70]}"
        )
    lines.append("")
    lines.append("APV, kaydırmadan izleme oranı değildir. Engaged/views oranı da Studio'daki stayed-to-watch metriği değildir.")
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
