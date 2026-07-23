import os
import subprocess
import logging
import requests
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import PEXELS_API_KEY, TEMP_DIR, OUTPUT_DIR, SHORTS_RES, LONG_RES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoEngine:
    def __init__(self, pexels_key: str = PEXELS_API_KEY):
        self.pexels_key = pexels_key

    def fetch_stock_video(self, query: str = "stock market finance", is_shorts: bool = True) -> str:
        """Fetches a free stock video clip from Pexels API, or generates a dark animated background if API key is missing."""
        target_path = TEMP_DIR / "bg_stock.mp4"
        
        if self.pexels_key:
            headers = {"Authorization": self.pexels_key}
            orientation = "portrait" if is_shorts else "landscape"
            url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation={orientation}"
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    videos = res.json().get("videos", [])
                    if videos:
                        v = random.choice(videos)
                        v_file = v["video_files"][0]["link"]
                        logger.info(f"Downloading Pexels background video: {v_file}")
                        v_res = requests.get(v_file, timeout=20)
                        with open(target_path, "wb") as f:
                            f.write(v_res.content)
                        return str(target_path)
            except Exception as e:
                logger.error(f"Error fetching Pexels video: {e}")

        # Fallback: Create a dark gradient background video using FFmpeg
        width, height = SHORTS_RES if is_shorts else LONG_RES
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x0f172a:s={width}x{height}:d=60",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(target_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(target_path)

    def create_stock_card_overlay(self, title: str, ticker: str, change_pct: str, output_path: str, is_shorts: bool = True):
        """Generates a sleek dark-mode stock data card overlay image (PIL)."""
        width, height = (900, 400) if is_shorts else (1200, 300)
        img = Image.new("RGBA", (width, height), (15, 23, 42, 230))
        draw = ImageDraw.Draw(img)

        # Border
        draw.rectangle([0, 0, width-1, height-1], outline=(56, 189, 248, 255), width=3)

        # Text Content
        is_positive = not change_pct.startswith("-")
        change_color = (34, 197, 94, 255) if is_positive else (239, 68, 68, 255)

        draw.text((40, 40), title.upper(), fill=(248, 250, 252, 255))
        draw.text((40, 120), f"TICKER: {ticker}", fill=(148, 163, 184, 255))
        draw.text((40, 200), f"CHANGE: {change_pct}%", fill=change_color)

        img.save(output_path)
        return output_path

    def render_video(self, audio_path: str, ass_sub_path: str, output_filename: str, is_shorts: bool = True) -> str:
        """Renders final MP4 video using FFmpeg by combining background video, voiceover audio, and ASS subtitles."""
        bg_video = self.fetch_stock_video("finance stock market", is_shorts=is_shorts)
        out_video = str(OUTPUT_DIR / output_filename)
        
        width, height = SHORTS_RES if is_shorts else LONG_RES

        # FFmpeg command string
        # Filters: scale background, crop to fill, apply ASS subtitles
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", bg_video,
            "-i", audio_path,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},ass={ass_sub_path}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            out_video
        ]

        logger.info(f"Rendering video to: {out_video}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Video render completed successfully!")
            return out_video
        else:
            logger.error(f"FFmpeg error: {result.stderr}")
            return ""

if __name__ == "__main__":
    ve = VideoEngine()
    print("Stock video fetched.")
