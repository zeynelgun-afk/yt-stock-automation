"""Unified weekly learning engine — ALL of the channel's self-improvement in
one job, one artifact, one read path.

Runs on the Sunday analytics CI slot and writes data/channel_learnings.json,
which the pipeline reads on every video run. Consolidates what used to be
three separate loops:

1. FRANCHISE WEIGHTS (own analytics): views x APV per franchise -> score
   multipliers for the story selector. Precomputed weekly here instead of a
   live Analytics API call on every video run.
2. NARRATION CALIBRATION (own analytics): measured words/sec from the w:/v:
   machine tags stamped on uploads + real video durations -> auto-tuned
   word budgets for the 35s Shorts / 5-6min recap targets.
3. OWN PACKAGING LESSONS (own analytics): retention curves (hook hold over
   the first 30%) + APV + views per video -> LLM-distilled winning/losing
   structural patterns FROM OUR OWN UPLOADS, injected into script prompts.
4. MARKET PATTERNS (external): the outlier scan of the finance niche
   (structure only, never copied titles) — same scan as before, now stored
   in the same file.

Merge semantics: each section that fails keeps its previous value from the
existing file. One broken API must never wipe learned state.
"""
import json
import logging
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config import LEARNINGS_FILE
from telegram_bot import TelegramApprovalBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Duration targets set by retention data (2026-08-10 retarget)
TARGET_SHORTS_SECONDS = (32, 38)
TARGET_LONG_SECONDS = (150, 210)  # September experiment: 76s average watch on long videos
SANE_WPS = (1.2, 3.0)          # outside this the w: tag or duration is garbage
MIN_WPS_SAMPLES = 3
EARLY_RETENTION_CUTOFF = 0.3   # "hook hold" = avg watch ratio over first 30%
MAX_RETENTION_QUERIES = 20     # one Analytics API call per video
STALE_AFTER_DAYS = 10          # consumers ignore a file older than this


def load_learnings() -> Dict[str, Any]:
    """The single read path for every consumer. {} if missing/unreadable/stale."""
    try:
        if not LEARNINGS_FILE.exists():
            return {}
        data = json.loads(LEARNINGS_FILE.read_text())
        updated = datetime.fromisoformat(data.get("updated_at", "1970-01-01T00:00:00"))
        if (datetime.now() - updated).days > STALE_AFTER_DAYS:
            logger.warning("channel_learnings.json is stale (> %d days) — ignoring.",
                           STALE_AFTER_DAYS)
            return {}
        # Refreshing one section must not make old patterns look newly measured.
        for section in ("franchise_weights", "narration", "own_patterns", "market_patterns"):
            stamp = data.get("section_updated_at", {}).get(section, data.get("updated_at"))
            try:
                if (datetime.now() - datetime.fromisoformat(stamp)).days > STALE_AFTER_DAYS:
                    data.pop(section, None)
            except (TypeError, ValueError):
                data.pop(section, None)
        return data
    except Exception as e:
        logger.warning(f"Could not load channel learnings: {e}")
        return {}


# ---------- Section 2: narration calibration ----------

def _measure_narration(stats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Median words/sec from uploads carrying w: tags, per dominant voice
    engine — mixing ElevenLabs and Edge pacing would blur both."""
    by_engine: Dict[str, List[float]] = {}
    for s in stats:
        w = s.get("machine", {}).get("w")
        d = s.get("duration_s") or 0
        if not w or d < 15:
            continue
        try:
            wps = int(w) / d
        except (ValueError, ZeroDivisionError):
            continue
        if SANE_WPS[0] <= wps <= SANE_WPS[1]:
            by_engine.setdefault(s.get("machine", {}).get("v", "?"), []).append(wps)

    if not by_engine:
        return None
    engine, samples = max(by_engine.items(), key=lambda kv: len(kv[1]))
    if len(samples) < MIN_WPS_SAMPLES:
        return None
    wps = round(statistics.median(samples), 3)
    return {
        "wps": wps,
        "engine": engine,
        "samples": len(samples),
        "shorts_word_range": [round(TARGET_SHORTS_SECONDS[0] * wps),
                              round(TARGET_SHORTS_SECONDS[1] * wps)],
        "long_word_range": [round(TARGET_LONG_SECONDS[0] * wps),
                            round(TARGET_LONG_SECONDS[1] * wps)],
    }


# ---------- Section 3: own packaging lessons ----------

def _fetch_hook_holds(stats: List[Dict[str, Any]], days: int) -> None:
    """Annotates stats rows in-place with hook_hold: average audienceWatchRatio
    over the first 30% of the video — the per-video number for 'did the hook
    hold viewers', straight from the retention curve."""
    from googleapiclient.discovery import build
    from analytics_reporter import _get_credentials

    creds = _get_credentials()
    yta = build("youtubeAnalytics", "v2", credentials=creds)
    end = datetime.now().date()
    start = end - timedelta(days=days)

    for s in stats[:MAX_RETENTION_QUERIES]:
        if s["views"] < 10:   # curve is noise below this
            continue
        try:
            resp = yta.reports().query(
                ids="channel==MINE",
                startDate=start.isoformat(), endDate=end.isoformat(),
                metrics="audienceWatchRatio",
                dimensions="elapsedVideoTimeRatio",
                filters=f"video=={s['video_id']}",
            ).execute()
            early = [float(r[1]) for r in resp.get("rows", [])
                     if float(r[0]) <= EARLY_RETENTION_CUTOFF]
            if early:
                s["hook_hold"] = round(sum(early) / len(early), 3)
        except Exception as e:
            logger.warning(f"Retention fetch failed for {s['video_id']}: {e}")


def _distill_own_patterns(stats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """LLM turns our own per-video numbers into structural lessons. Same
    structure-only boundary as the market scan: shapes, never verbatim titles."""
    from script_generator import ScriptGenerator

    rows = [{
        "title": s["title"],
        "franchise": s.get("franchise"),
        "views": s["views"],
        "engaged_views": s.get("engaged_views", 0),
        "avg_view_pct": s["avg_view_pct"],
        "hook_hold_first30pct": s.get("hook_hold"),
        "is_long": s.get("is_long", False),
    } for s in stats if s.get("engaged_views", 0) >= 20][:MAX_RETENTION_QUERIES]
    if not rows:
        return None

    prompt = f"""You are the growth analyst for "US Stock Market Daily", a data-first, no-hype US stock market channel.

Below is OUR OWN channel's per-video performance for the last two weeks.
hook_hold_first30pct = average audience retention over the first 30% of the video (the hook window). avg_view_pct = how much of the video the average viewer watched.

{json.dumps(rows, indent=1, ensure_ascii=False)}

Extract structural lessons about what holds OUR viewers and what loses them: title shapes, hook framings, number usage, franchise observations. STRUCTURE ONLY — never quote a full title back as a pattern.
If the sample is thin (few videos or low views), return fewer, conservative patterns rather than overfitting noise.
Analyze Shorts and long videos separately. APV is not swipe-away or feed conversion.
Do not treat replay-driven APV above 100% as proof of broad audience demand.
These are correlations, not causal evidence that a title shape increases distribution.

Return strictly valid JSON:
- "winning_patterns": array of 2-5 structural patterns from our best-retaining videos
- "losing_patterns": array of 2-4 structural patterns from our worst (things to avoid)
- "notes": array of 1-3 short observations (e.g. a franchise or duration insight)
"""
    return ScriptGenerator()._call_llm(prompt, default_title="own-channel lessons")


# ---------- Orchestrator ----------

def run_weekly_learning(days: int = 14) -> bool:
    """One weekly pass over all four learning sections. Failed sections keep
    their previous values; the Telegram summary says what refreshed."""
    from analytics_reporter import fetch_video_stats, compute_franchise_weights

    bot = TelegramApprovalBot()
    previous: Dict[str, Any] = {}
    try:
        if LEARNINGS_FILE.exists():
            previous = json.loads(LEARNINGS_FILE.read_text())
    except Exception:
        pass
    learnings: Dict[str, Any] = {**previous}
    section_times = dict(previous.get("section_updated_at", {}))
    for section in ("franchise_weights", "narration", "own_patterns", "market_patterns"):
        if section in previous:
            section_times.setdefault(section, previous.get("updated_at", "1970-01-01T00:00:00"))
    status: Dict[str, str] = {}

    stats: List[Dict[str, Any]] = []
    stats_available = False
    try:
        stats = fetch_video_stats(days)
        stats_available = True
    except Exception as e:
        logger.error(f"Video stats fetch failed: {e}")
        status["stats"] = f"failed: {e}"

    # 1. Franchise weights
    if stats_available:
        try:
            weights = compute_franchise_weights(days=days, stats=stats)
            learnings["franchise_weights"] = weights
            learnings["weights_version"] = 2
            status["weights"] = f"ok ({len(weights)} franchise)" if weights else "not enough data"
            section_times["franchise_weights"] = datetime.now().isoformat(timespec="seconds")
        except Exception as e:
            status["weights"] = f"failed: {e}"
    else:
        status["weights"] = "failed: stats unavailable; previous weights retained"

    # 2. Narration calibration (needs w:/v: machine tags on uploads)
    if stats:
        narration = _measure_narration(stats)
        if narration:
            learnings["narration"] = narration
            status["narration"] = (f"ok ({narration['wps']} w/s, "
                                   f"{narration['samples']} video)")
        else:
            status["narration"] = "no tagged samples yet"

    # 3. Own packaging lessons (retention + LLM)
    if stats:
        try:
            _fetch_hook_holds(stats, days)
            own = _distill_own_patterns(stats)
            if own:
                learnings["own_patterns"] = own
                status["own_patterns"] = "ok"
        except Exception as e:
            logger.error(f"Own-pattern distillation failed: {e}")
            status["own_patterns"] = f"failed: {e}"

    # 4. Market patterns (external outlier scan)
    try:
        from outlier_scanner import scan_outliers, extract_patterns
        outliers = scan_outliers()
        if outliers:
            learnings["market_patterns"] = extract_patterns(outliers)
            status["market_patterns"] = f"ok ({len(outliers)} outlier)"
        else:
            status["market_patterns"] = "no outliers found"
    except Exception as e:
        logger.error(f"Outlier scan failed: {e}")
        status["market_patterns"] = f"failed: {e}"

    learnings["updated_at"] = datetime.now().isoformat(timespec="seconds")
    for section, status_key in (("franchise_weights", "weights"), ("narration", "narration"),
                                ("own_patterns", "own_patterns"), ("market_patterns", "market_patterns")):
        if status.get(status_key, "").startswith("ok"):
            section_times[section] = learnings["updated_at"]
    learnings["section_updated_at"] = section_times
    learnings["section_status"] = status
    LEARNINGS_FILE.write_text(json.dumps(learnings, indent=1, ensure_ascii=False))
    logger.info(f"Learnings saved to {LEARNINGS_FILE}")

    lines = ["🧠 HAFTALIK ÖĞRENME DÖNGÜSÜ", ""]
    for section, st in status.items():
        mark = "✅" if st.startswith("ok") else ("➖" if "no " in st or "not " in st else "🚨")
        lines.append(f"{mark} {section}: {st}")
    narr = learnings.get("narration")
    if narr:
        lines.append(f"\n⏱ Ölçülen hız: {narr['wps']} kelime/sn ({narr['engine']}) → "
                     f"Shorts {narr['shorts_word_range'][0]}-{narr['shorts_word_range'][1]} kelime, "
                     f"recap {narr['long_word_range'][0]}-{narr['long_word_range'][1]} kelime")
    own = (learnings.get("own_patterns") or {}).get("winning_patterns", [])
    if own:
        from script_generator import _pattern_text
        lines.append("\n🏆 Kendi verimizden bu haftanın kazanan kalıpları:")
        lines += [f"• {_pattern_text(p)[:200]}" for p in own[:3]]
    return bot.send_text("\n".join(lines))


if __name__ == "__main__":
    run_weekly_learning()
