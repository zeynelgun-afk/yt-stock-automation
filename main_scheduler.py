import json
import logging
import re
import shutil
import subprocess
import time
from datetime import datetime

from data_fetcher import FMPDataFetcher, FMPDataError, ny_now
from story_pool import StoryPoolCollector, summarize_pool, compact_pool
from story_selector import StorySelector
from script_generator import ScriptGenerator, ScriptGenerationError
from voice_generator import VoiceGenerator
from subtitle_generator import SubtitleGenerator
from video_engine import VideoEngine, LONG_BG_CLIPS
from telegram_bot import TelegramApprovalBot
from youtube_publisher import YouTubePublisher
from config import TEMP_DIR, MIN_SHORTS_STORY_SCORE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("YT_AUTO")


def get_audio_duration(audio_path: str) -> float:
    """Duration in seconds via ffprobe; 0.0 if it can't be determined."""
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", audio_path],
            capture_output=True, text=True, timeout=30,
        )
        return float(res.stdout.strip())
    except Exception as e:
        logger.warning(f"Could not probe audio duration: {e}")
        return 0.0


def abort_pipeline(reason: str):
    """Stops the pipeline and alerts the operator. NEVER publish without live data.

    Raises SystemExit(1): aborts used to return with exit code 0, so a failed
    slot showed a green check in GitHub Actions — indistinguishable from
    success in the run history."""
    logger.error(f"PIPELINE ABORTED: {reason}")
    if not TelegramApprovalBot().send_text(
            f"🚨 Video pipeline DURDU — video üretilmedi.\n\nSebep: {reason}"):
        logger.error("Telegram abort alert could not be delivered either.")
    raise SystemExit(1)


def cleanup_temp(max_age_days: float = 3.0) -> None:
    """Sweeps TEMP_DIR of old run artifacts (voiceovers, cards, Pexels clips,
    chart frame dirs). CI runners are ephemeral, but the same pipeline runs on
    the local machine, where temp assets used to accumulate indefinitely."""
    cutoff = time.time() - max_age_days * 86400
    try:
        for p in TEMP_DIR.iterdir():
            try:
                if p.stat().st_mtime >= cutoff:
                    continue
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass


def validate_hero_number(hero: str, story: dict, script: str, change_pct: str) -> str:
    """The hero number is the biggest type on screen and comes from the LLM.
    Guardrail, not oracle: its leading significant digits must appear somewhere
    in the story facts, headline, script or change% — otherwise blank it so the
    card falls back to the change-led layout instead of publishing a
    hallucinated figure in 200pt type. Loose on purpose ('$28.2M' must survive
    facts that say $28,171,450)."""
    digits = re.sub(r"\D", "", hero)
    if not digits:
        return hero
    corpus = re.sub(r"\D", "", json.dumps(story.get("facts", {}), default=str)
                    + story.get("headline", "") + script + change_pct)
    if digits[:2] in corpus:
        return hero
    logger.warning(f"hero_number '{hero}' not found in story data — using change-led card layout.")
    return ""


def run_pipeline(video_type: str = "shorts"):
    """Executes full automated pipeline for creating a YouTube Shorts or Long video."""
    is_shorts = (video_type == "shorts")
    logger.info(f"=== STARTING AUTOMATED PIPELINE: {video_type.upper()} ===")

    # 1. Collect the day's story pool — backbone failures abort, no fake fallbacks
    try:
        fetcher = FMPDataFetcher()
        pool = StoryPoolCollector(fetcher).collect()
    except FMPDataError as e:
        abort_pipeline(str(e))
    logger.info("Story pool collected:\n" + summarize_pool(pool))

    # 2. Story selection engine: score candidates, LLM picks the day's angle
    sg = ScriptGenerator()
    selector = StorySelector(sg)
    story = selector.select(pool)

    # Quality gate (Shorts only): a weak story tanks retention and trains the
    # algorithm that the channel is skippable. Skipping the slot is a decision,
    # not a failure — informational Telegram note, no alarm.
    if is_shorts and story.get("score", 100) < MIN_SHORTS_STORY_SCORE:
        msg = (f"⏭️ Slot atlandı — günün en iyi hikâyesi zayıf "
               f"(skor {story.get('score', 0):.0f} < {MIN_SHORTS_STORY_SCORE:.0f}): "
               f"{story['headline']}")
        logger.info(msg)
        TelegramApprovalBot().send_text(msg)
        return

    # 3. Generate Script using DeepSeek V3 / Qwen 2.5 via OpenRouter
    digest = compact_pool(pool)
    try:
        if is_shorts:
            data_summary = (
                f"SELECTED STORY ({story['franchise_name']}): {story['headline']}\n"
                f"Why it matters: {story['why_it_matters']}\n"
                f"Story facts: {json.dumps(story['facts'], default=str)}\n"
                f"Market context: {json.dumps(digest['market'], default=str)}"
            )
            script_data = sg.generate_shorts_script(
                topic=story["headline"],
                data_summary=data_summary,
                franchise_style=story["franchise_style"],
                angle=story["angle"],
                recent_titles=selector.recent_titles,
            )
        else:
            script_data = sg.generate_long_script(market_data={
                **digest,
                "selected_story": {k: story[k] for k in ("franchise_name", "headline", "angle", "facts")},
            })
    except ScriptGenerationError as e:
        abort_pipeline(str(e))

    # The chart must match the story — the selector's ticker wins over the LLM's
    ticker = story["ticker"] or script_data.get("ticker") or pool["movers"]["gainers"][0]["symbol"]

    logger.info(f"Generated Title: {script_data['title']}")
    logger.info(f"Script Text: {script_data['full_script'][:100]}...")

    # 4. Fetch REAL intraday chart data for the ticker the script actually covers
    try:
        intraday = fetcher.get_intraday_chart(ticker)
    except FMPDataError as e:
        abort_pipeline(f"Intraday chart data unavailable for {ticker}: {e}")

    # Card change % is computed from the same candles as the chart — never from
    # the LLM, which can echo an index move instead of the ticker's own
    session_open = intraday[0]["open"] or intraday[0]["close"]
    change_pct = f"{(intraday[-1]['close'] - session_open) / session_open * 100:+.2f}"

    # 5. Generate Audio Voiceover (ElevenLabs -> Edge-TTS, measured word timings)
    vg = VoiceGenerator()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_path, srt_path = vg.generate_audio(
        script_data["full_script"], f"voice_{timestamp}.mp3", f"sub_{timestamp}.srt"
    )
    if not audio_path:
        abort_pipeline("Audio generation failed.")

    # 6. Generate Subtitles — an empty return here used to flow into the render
    # as an empty ass= filter path, killing all three render attempts with a
    # misleading "Video rendering failed" after burning asset credits
    ass_path = str(SubtitleGenerator.srt_to_ass(
        srt_path, srt_path.replace('.srt', '.ass'), is_shorts=is_shorts
    ))
    if not ass_path:
        abort_pipeline("Subtitle conversion failed — SRT was empty or unparseable.")

    # 7. Render video: first-frame card + animated real chart + subtitles
    ve = VideoEngine()
    card_img_path = str(TEMP_DIR / f"card_{timestamp}.png")
    ve.create_dashboard_overlay(
        title=script_data["title"],
        ticker=ticker,
        change_pct=change_pct,
        output_path=card_img_path,
        is_shorts=is_shorts,
        franchise_name=story["franchise_name"],
        # Empty strings fall the card back to its change%-led layout;
        # validation blanks a hero figure the story data can't back up
        hero_number=validate_hero_number(
            str(script_data.get("hero_number", "")).strip(),
            story, script_data["full_script"], change_pct),
        hero_label=str(script_data.get("hero_label", "")).strip(),
    )

    # Stretch the chart reveal over ~80% of the narration so the frame keeps
    # moving for the whole video (user feedback: static frames aren't engaging)
    audio_dur = get_audio_duration(audio_path)
    chart_draw = max(3.0, min(audio_dur * 0.8, 60.0)) if audio_dur else 3.0
    try:
        chart_video_path = ve.create_animated_chart(
            ticker, intraday, str(TEMP_DIR / f"chart_{timestamp}.mp4"),
            draw_seconds=chart_draw, is_shorts=is_shorts,
        )
    except RuntimeError as e:
        abort_pipeline(f"Animated chart rendering failed: {e}")

    # 7.5 Fetch background clips: Higgsfield AI (if configured) -> Pexels fallback
    visual_keywords = script_data.get("visual_keywords", [])
    if not visual_keywords:
        visual_keywords = [f"{ticker} stock", "wall street trading", "stock market chart",
                           "finance money", "federal reserve building"]
    # A 35-second Short holds on one clip. A 5-6 minute recap on one looping
    # clip stops changing about 20 seconds in, so it gets a clip per section.
    bg_clips = ve.fetch_background_videos(
        visual_keywords, is_shorts=is_shorts,
        count=1 if is_shorts else LONG_BG_CLIPS,
    )

    thumbnail_path = ""
    if not is_shorts:
        thumbnail_path = str(TEMP_DIR / f"thumb_{timestamp}.png")
        ve.create_thumbnail(
            ticker=ticker,
            change_pct=change_pct,
            hook_words=script_data.get("thumbnail_hook", script_data["title"]),
            intraday=intraday,
            output_path=thumbnail_path,
        )

    rendered_video_path = ve.render_video(
        audio_path, ass_path, f"render_{video_type}_{timestamp}.mp4",
        card_img_path=card_img_path, chart_video_path=chart_video_path,
        is_shorts=is_shorts, bg_video_path=bg_clips,
    )
    if not rendered_video_path:
        abort_pipeline("Video rendering failed.")

    # 8. Fully autonomous publish: Telegram gets the render as an FYI (with the
    # measured duration for pacing calibration), then YouTube upload proceeds
    # unconditionally. This is a deliberate design decision (2026-08-16) — the
    # old inline-button approval flow was removed, there is no human gate.
    bot = TelegramApprovalBot()
    bot.send_video_notification(
        video_path=rendered_video_path,
        title=script_data["title"],
        is_shorts=is_shorts,
        duration_s=audio_dur,
    )

    yp = YouTubePublisher()
    video_id = yp.upload_video(
        video_path=rendered_video_path,
        title=script_data["title"],
        description=script_data.get("description", script_data["full_script"]),
        tags=script_data.get("tags", ["stocks", "finance"]),
        is_shorts=is_shorts,
        thumbnail_path=thumbnail_path,
        contains_synthetic_media=ve.used_ai_video,
        # Machine metadata (invisible to viewers): the weekly learning engine
        # reads these back for exact franchise stats + narration calibration
        extra_tags=[
            f"fr:{story['franchise']}",
            f"w:{len(script_data['full_script'].split())}",
            f"v:{vg.engine_used or 'unknown'}",
        ],
    )
    if video_id:
        logger.info(f"Published to YouTube! Video ID: {video_id}")
        bot.send_text(f"✅ Yayında ({audio_dur:.0f}sn): https://youtu.be/{video_id}")
    else:
        logger.error("YouTube upload failed.")
        bot.send_text(f"🚨 YouTube yüklemesi BAŞARISIZ oldu.\nSebep: {yp.last_error}\n"
                      f"Dosya: {rendered_video_path}")

    cleanup_temp()
    logger.info(f"=== PIPELINE FINISHED FOR {video_type.upper()}! Uploaded: {bool(video_id)} ===")


def is_event_day() -> tuple[bool, str]:
    """Turbo-mode check (ROADMAP Faz 4.2): is today a CPI/FOMC/NFP or
    mega-cap earnings day? Cron uses the exit code to trigger extra videos."""
    fetcher = FMPDataFetcher()
    reasons = []

    macro = [
        r["event"] for r in fetcher.get_economic_calendar(days_ahead=0)
        if r.get("country") == "US" and r.get("impact") == "High"
    ]
    reasons += [f"Macro: {e}" for e in macro[:3]]

    today = ny_now().strftime("%Y-%m-%d")
    def _us_listed(sym: str) -> bool:
        # No exchange suffix, and not an OTC ADR/foreign ordinary
        # (5-letter tickers ending in Y/F by convention: RHHBY, NSRGY, CRERF...)
        return "." not in sym and not (len(sym) == 5 and sym[-1] in "YF")

    big_earnings = [
        r["symbol"] for r in fetcher.get_earnings_calendar(days_ahead=0)
        if r.get("date") == today
        and (r.get("revenueEstimated") or 0) >= 10_000_000_000
        and _us_listed(r["symbol"])
    ]
    if big_earnings:
        reasons.append(f"Mega-cap earnings: {', '.join(big_earnings[:5])}")

    return (bool(reasons), " | ".join(reasons) or "No high-impact events today")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="US Stock Market Daily pipeline")
    parser.add_argument("mode", nargs="?", default="shorts",
                        choices=["shorts", "long", "event-check"],
                        help="shorts/long: produce a video; "
                             "event-check: exit 0 on CPI/FOMC/mega-earnings days (for cron turbo mode)")
    args = parser.parse_args()

    if args.mode == "event-check":
        # Exit codes: 0 = event day, 1 = quiet day, 2 = the check itself broke.
        # Without the distinction, an FMP outage on CPI day read as "no event"
        # and silently skipped the turbo slot with no notification.
        try:
            hot, reason = is_event_day()
        except Exception as e:
            logger.exception("event-check failed")
            TelegramApprovalBot().send_text(f"⚠️ Event-check çalıştırılamadı: {e}")
            raise SystemExit(2)
        print(reason)
        raise SystemExit(0 if hot else 1)

    logger.info("Starting Youtube Stock Automation Engine...")
    try:
        run_pipeline(args.mode)
    except SystemExit:
        raise  # abort_pipeline already alerted and set the exit code
    except Exception as e:
        # Catch-all: an unexpected exception anywhere in the pipeline used to
        # die with a traceback in CI logs only — no Telegram, green check
        logger.exception("Unhandled pipeline error")
        abort_pipeline(f"Beklenmeyen hata: {type(e).__name__}: {e}")
