import time
import logging
from datetime import datetime
from data_fetcher import FMPDataFetcher
from script_generator import ScriptGenerator
from voice_generator import VoiceGenerator
from subtitle_generator import SubtitleGenerator
from video_engine import VideoEngine
from telegram_bot import TelegramApprovalBot
from config import SCHEDULE_TIMES_TSI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("YT_AUTO")

def run_pipeline(video_type: str = "shorts"):
    """Executes full automated pipeline for creating a YouTube Shorts or Long video."""
    is_shorts = (video_type == "shorts")
    logger.info(f"=== STARTING AUTOMATED PIPELINE: {video_type.upper()} ===")

    # 1. Fetch Market Data
    fetcher = FMPDataFetcher()
    gainers = fetcher.get_top_gainers()
    fear_greed = fetcher.get_fear_greed_index()
    news = fetcher.get_market_news()

    top_gainer_symbol = gainers[0]['symbol'] if gainers else "NVDA"
    top_gainer_change = gainers[0]['changesPercentage'] if gainers else 5.0
    news_title = news[0]['title'] if news else "Market Hits New Highs"

    market_summary = f"Top Gainer: {top_gainer_symbol} (+{top_gainer_change:.2f}%). Fear/Greed Score: {fear_greed['score']} ({fear_greed['rating']}). News: {news_title}"
    logger.info(f"Market Summary Data: {market_summary}")

    # 2. Generate LLM Script
    sg = ScriptGenerator()
    if is_shorts:
        script_data = sg.generate_shorts_script(topic="US Stock Market Daily Movement", data_summary=market_summary)
    else:
        script_data = sg.generate_long_script(market_data={"gainers": gainers, "fear_greed": fear_greed, "news": news})

    logger.info(f"Generated Title: {script_data['title']}")

    # 3. Generate Audio Voiceover (Edge-TTS)
    vg = VoiceGenerator()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_file = f"voice_{timestamp}.mp3"
    srt_file = f"sub_{timestamp}.srt"
    ass_file = f"sub_{timestamp}.ass"
    
    audio_path, srt_path = vg.generate_audio(script_data["full_script"], audio_file, srt_file)
    if not audio_path:
        logger.error("Audio generation failed. Aborting pipeline.")
        return

    # 4. Generate Subtitles
    ass_path = str(SubtitleGenerator.srt_to_ass(srt_path, srt_path.replace('.srt', '.ass'), is_shorts=is_shorts))

    # 5. Render Video
    ve = VideoEngine()
    video_name = f"render_{video_type}_{timestamp}.mp4"
    rendered_video_path = ve.render_video(audio_path, ass_path, video_name, is_shorts=is_shorts)

    if not rendered_video_path:
        logger.error("Video rendering failed.")
        return

    # 6. Telegram Approval
    bot = TelegramApprovalBot()
    sent = bot.send_video_for_approval(rendered_video_path, script_data["title"], script_data.get("description", script_data["full_script"]), is_shorts=is_shorts)

    logger.info(f"=== PIPELINE FINISHED FOR {video_type.upper()}! Telegram Notification Sent: {sent} ===")

if __name__ == "__main__":
    logger.info("Starting Youtube Stock Automation Engine...")
    run_pipeline("shorts")
