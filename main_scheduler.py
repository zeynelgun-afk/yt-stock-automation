import logging
from datetime import datetime

from data_fetcher import FMPDataFetcher, FMPDataError
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

    # 1. Fetch LIVE market data — abort on any failure, no fake fallbacks
    try:
        fetcher = FMPDataFetcher()
        gainers = fetcher.get_top_gainers()
        losers = fetcher.get_top_losers()
        indexes = fetcher.get_index_quotes()
        news = fetcher.get_market_news()
    except FMPDataError as e:
        abort_pipeline(str(e))
        return

    fear_greed = fetcher.get_fear_greed_index()  # optional; None if unavailable

    top_gainer = gainers[0]
    top_gainer_symbol = top_gainer["symbol"]
    top_gainer_change = float(top_gainer.get("changesPercentage", 0.0))

    index_summary = ", ".join(
        f"{q['symbol']}: {q.get('price')} ({q.get('changePercentage', 0):+.2f}%)"
        for q in indexes
    )
    fg_summary = (
        f"Fear/Greed Score: {fear_greed['score']} ({fear_greed['rating']})"
        if fear_greed else "Fear/Greed unavailable"
    )
    market_summary = (
        f"Indexes: {index_summary}. "
        f"Top Gainer: {top_gainer_symbol} ({top_gainer_change:+.2f}%). "
        f"{fg_summary}. News: {news[0]['title']}"
    )
    logger.info(f"Market Summary Data: {market_summary}")

    # 2. Generate Script using DeepSeek V3 / Qwen 2.5 via OpenRouter
    sg = ScriptGenerator()
    try:
        if is_shorts:
            script_data = sg.generate_shorts_script(
                topic="US Stock Market Daily Movement", data_summary=market_summary
            )
        else:
            script_data = sg.generate_long_script(market_data={
                "indexes": indexes,
                "gainers": gainers,
                "losers": losers,
                "fear_greed": fear_greed,
                "news": news,
            })
    except ScriptGenerationError as e:
        abort_pipeline(str(e))
        return

    ticker = script_data.get("ticker", top_gainer_symbol)
    change_pct = str(script_data.get("change_pct", f"{top_gainer_change:+.2f}"))

    logger.info(f"Generated Title: {script_data['title']}")
    logger.info(f"Script Text: {script_data['full_script'][:100]}...")

    # 3. Fetch REAL intraday chart data for the ticker the script actually covers
    try:
        intraday = fetcher.get_intraday_chart(ticker)
    except FMPDataError as e:
        abort_pipeline(f"Intraday chart data unavailable for {ticker}: {e}")
        return

    # 4. Generate Audio Voiceover (Edge-TTS)
    vg = VoiceGenerator()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_path, srt_path = vg.generate_audio(
        script_data["full_script"], f"voice_{timestamp}.mp3", f"sub_{timestamp}.srt"
    )
    if not audio_path:
        abort_pipeline("Audio generation failed.")
        return

    # 5. Generate Subtitles
    ass_path = str(SubtitleGenerator.srt_to_ass(
        srt_path, srt_path.replace('.srt', '.ass'), is_shorts=is_shorts
    ))

    # 6. Render video with the real ticker card + real chart
    ve = VideoEngine()
    card_img_path = str(TEMP_DIR / f"card_{timestamp}.png")
    ve.create_dashboard_overlay(
        title=script_data["title"],
        ticker=ticker,
        change_pct=change_pct,
        intraday=intraday,
        output_path=card_img_path,
        is_shorts=is_shorts,
    )

    rendered_video_path = ve.render_video(
        audio_path, ass_path, f"render_{video_type}_{timestamp}.mp4",
        card_img_path=card_img_path, is_shorts=is_shorts,
    )
    if not rendered_video_path:
        abort_pipeline("Video rendering failed.")
        return

    # 7. Telegram Approval & Live Listener
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
        )
        logger.info(f"Published to YouTube! Video ID: {video_id}")
    else:
        logger.warning("Video was not approved or approval timed out.")

    logger.info(f"=== PIPELINE FINISHED FOR {video_type.upper()}! Approved: {approved} ===")


if __name__ == "__main__":
    logger.info("Starting Youtube Stock Automation Engine...")
    run_pipeline("shorts")
