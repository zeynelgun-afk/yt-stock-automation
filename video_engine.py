import os
import subprocess
import logging
import requests
import random
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import PEXELS_API_KEY, TEMP_DIR, OUTPUT_DIR, SHORTS_RES, LONG_RES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoEngine:
    def __init__(self, pexels_key: str = PEXELS_API_KEY):
        self.pexels_key = pexels_key

    def create_stock_chart_image(self, symbol: str = "NVDA", output_path: str = None) -> str:
        """Generates a high-res neon stock price chart image using Matplotlib."""
        if not output_path:
            output_path = str(TEMP_DIR / "chart_overlay.png")

        fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
        fig.patch.set_facecolor('#0f172a') # Dark slate background
        ax.set_facecolor('#0f172a')

        # Fake stock price movement data with positive trend
        x = np.linspace(0, 10, 50)
        y = 120 + np.sin(x) * 3 + x * 1.5 + np.random.normal(0, 0.5, 50)

        ax.plot(x, y, color='#22c55e', linewidth=4) # Neon green line
        ax.fill_between(x, y, 115, color='#22c55e', alpha=0.2)

        ax.set_title(f"DAILY MOVEMENT: {symbol}", color='#f8fafc', fontsize=14, fontweight='bold', pad=12)
        ax.tick_params(colors='#94a3b8', labelsize=10)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#334155')
        ax.spines['bottom'].set_color('#334155')

        plt.tight_layout()
        plt.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close()
        return output_path

    def create_dashboard_overlay(self, title: str, ticker: str, change_pct: str, output_path: str, is_shorts: bool = True) -> str:
        """Generates a sleek dark-mode stock data card overlay image (PIL)."""
        width, height = (960, 1200) if is_shorts else (1600, 700)
        img = Image.new("RGBA", (width, height), (15, 23, 42, 240))
        draw = ImageDraw.Draw(img)

        # Border
        draw.rectangle([0, 0, width-1, height-1], outline=(56, 189, 248, 255), width=6)

        # Header Badge
        draw.rectangle([40, 40, width-40, 140], fill=(30, 41, 59, 255))
        draw.text((60, 65), "US STOCK MARKET DAILY", fill=(56, 189, 248, 255))

        # Stock Details
        is_positive = not str(change_pct).startswith("-")
        change_color = (34, 197, 94, 255) if is_positive else (239, 68, 68, 255)
        sign = "+" if is_positive else ""

        draw.text((60, 180), f"TICKER: {ticker}", fill=(248, 250, 252, 255))
        draw.text((60, 260), f"CHANGE: {sign}{change_pct}%", fill=change_color)

        # Draw Chart into Card
        chart_path = self.create_stock_chart_image(ticker)
        if Path(chart_path).exists():
            chart_img = Image.open(chart_path).convert("RGBA")
            chart_img = chart_img.resize((width - 120, 500))
            img.paste(chart_img, (60, 360), chart_img)

        img.save(output_path)
        return output_path

    def render_video(self, audio_path: str, ass_sub_path: str, output_filename: str, is_shorts: bool = True) -> str:
        """Renders final vibrant MP4 video with stock dashboard graphics, motion background, and subtitles."""
        out_video = str(OUTPUT_DIR / output_filename)
        width, height = SHORTS_RES if is_shorts else LONG_RES

        # 1. Create Stock Card Overlay Image
        card_img_path = str(TEMP_DIR / "overlay_card.png")
        self.create_dashboard_overlay(
            title="US Stock Alert",
            ticker="NVDA",
            change_pct="6.85",
            output_path=card_img_path,
            is_shorts=is_shorts
        )

        # 2. Render high-quality moving background + overlay + text using FFmpeg
        # Moving radial gradient + Overlay card + ASS subtitles
        filter_complex = (
            f"[0:v]scale={width}:{height},fps=30[bg]; "
            f"[1:v]scale=900:-1[card]; "
            f"[bg][card]overlay=(W-w)/2:(H-h)/2[v1]; "
            f"[v1]ass={ass_sub_path}[outv]"
        )

        # FFmpeg command using animated color gradient
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"cellauto=s={width}x{height}:rate=30:rule=30",
            "-i", card_img_path,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "2:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            out_video
        ]

        logger.info(f"Rendering high-quality video to: {out_video}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("Video render completed successfully with vibrant graphics!")
            return out_video
        else:
            logger.error(f"FFmpeg render error: {result.stderr}")
            # Fallback simple render if cellauto is missing
            fallback_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x0f172a:s={width}x{height}:r=30",
                "-i", card_img_path,
                "-i", audio_path,
                "-filter_complex", f"[0:v][1:v]overlay=(W-w)/2:(H-h)/2[v1]; [v1]ass={ass_sub_path}[outv]",
                "-map", "[outv]", "-map", "2:a",
                "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                out_video
            ]
            subprocess.run(fallback_cmd, capture_output=True)
            return out_video

if __name__ == "__main__":
    ve = VideoEngine()
    print("Video Engine initialized.")
