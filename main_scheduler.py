import json
import logging
from datetime import datetime

from data_fetcher import FMPDataFetcher, FMPDataError
from story_pool import StoryPoolCollector, summarize_pool, compact_pool
from story_selector import StorySelector
from script_generator import ScriptGenerator, ScriptGenerationError
from voice_generator import VoiceGenerator
from subtitle_generator import SubtitleGenerator
from video_engine import VideoEngine
from telegram_bot import TelegramApprovalBot
from youtube_publisher import YouTubePublisher
from config import TEMP_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("YT_AUTO")


def abort_pipeline(reason: str):
    """Stops the pipeline and alerts the operator. NEVER publish without live data."""
    logger.error(f"PIPELINE ABORTED: {reason}")
    TelegramApprovalBot().send_text(f"🚨 Video pipeline DURDU — video üretilmedi.\n\nSebep: {reason}")


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
        return
    logger.info("Story pool collected:\n" + summarize_pool(pool))

    # 2. Story selection engine: score candidates, LLM picks the day's angle
    sg = ScriptGenerator()
    story = StorySelector(sg).select(pool)

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
            )
        else:
            script_data = sg.generate_long_script(market_data={
                **digest,
                "selected_story": {k: story[k] for k in ("franchise_name", "headline", "angle", "facts")},
            })
    except ScriptGenerationError as e:
        abort_pipeline(str(e))
        return

    # The chart must match the story — the selector's ticker wins over the LLM's
    ticker = story["ticker"] or script_data.get("ticker") or pool["movers"]["gainers"][0]["symbol"]

    logger.info(f"Generated Title: {script_data['title']}")
    logger.info(f"Script Text: {script_data['full_script'][:100]}...")

    # 4. Fetch REAL intraday chart data for the ticker the script actually covers
    try:
        intraday = fetcher.get_intraday_chart(ticker)
    except FMPDataError as e:
        abort_pipeline(f"Intraday chart data unavailable for {ticker}: {e}")
        return

    # Card change % is computed from the same candles as the chart — never from
    # the LLM, which can echo an index move instead of the ticker's own
    session_open = intraday[0]["open"] or intraday[0]["close"]
    change_pct = f"{(intraday[-1]['close'] - session_open) / session_open * 100:+.2f}"

    # 5. Generate Audio Voiceover (Edge-TTS)
    vg = VoiceGenerator()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_path, srt_path = vg.generate_audio(
        script_data["full_script"], f"voice_{timestamp}.mp3", f"sub_{timestamp}.srt"
    )
    if not audio_path:
        abort_pipeline("Audio generation failed.")
        return

    # 6. Generate Subtitles
    ass_path = str(SubtitleGenerator.srt_to_ass(
        srt_path, srt_path.replace('.srt', '.ass'), is_shorts=is_shorts
    ))

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
    )

    try:
        chart_video_path = ve.create_animated_chart(
            ticker, intraday, str(TEMP_DIR / f"chart_{timestamp}.mp4")
        )
    except RuntimeError as e:
        abort_pipeline(f"Animated chart rendering failed: {e}")
        return

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
        is_shorts=is_shorts,
    )
    if not rendered_video_path:
        abort_pipeline("Video rendering failed.")
        return

    # 8. Telegram Approval & Live Listener
    bot = TelegramApprovalBot()
    approved = bot.send_video_and_wait_for_approval(
        video_path=rendered_video_path,
        title=script_data["title"],
        description=script_data.get("description", script_data["full_script"]),
        tags=script_data.get("tags", ["stocks", "finance"]),
        is_shorts=is_shorts,
        timeout_seconds=300,
    )

    if approved:
        logger.info("Video approved by user! Publishing to YouTube...")
        yp = YouTubePublisher()
        video_id = yp.upload_video(
            video_path=rendered_video_path,
            title=script_data["title"],
            description=script_data.get("description", script_data["full_script"]),
            tags=script_data.get("tags", ["stocks", "finance"]),
            is_shorts=is_shorts,
            thumbnail_path=thumbnail_path,
        )
        logger.info(f"Published to YouTube! Video ID: {video_id}")
    else:
        logger.warning("Video was not approved or approval timed out.")

    logger.info(f"=== PIPELINE FINISHED FOR {video_type.upper()}! Approved: {approved} ===")


if __name__ == "__main__":
    logger.info("Starting Youtube Stock Automation Engine...")
    run_pipeline("shorts")
