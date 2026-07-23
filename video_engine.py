import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw

from config import PEXELS_API_KEY, TEMP_DIR, OUTPUT_DIR, SHORTS_RES, LONG_RES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NEON_GREEN = '#22c55e'
NEON_RED = '#ef4444'
DARK_BG = '#0f172a'


class VideoEngine:
    def __init__(self, pexels_key: str = PEXELS_API_KEY):
        self.pexels_key = pexels_key

    def create_stock_chart_image(self, symbol: str, intraday: List[Dict[str, Any]],
                                 output_path: str = None) -> str:
        """Renders the REAL intraday price line for the last session.

        `intraday` must be actual candles from FMPDataFetcher.get_intraday_chart()
        (oldest first). Fabricated chart data is never acceptable on this channel.
        """
        if not intraday:
            raise ValueError(f"No intraday data provided for {symbol} chart")
        if not output_path:
            output_path = str(TEMP_DIR / "chart_overlay.png")

        closes = [row["close"] for row in intraday]
        times = list(range(len(closes)))
        is_up = closes[-1] >= closes[0]
        line_color = NEON_GREEN if is_up else NEON_RED

        fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARK_BG)

        ax.plot(times, closes, color=line_color, linewidth=4)
        ax.fill_between(times, closes, min(closes), color=line_color, alpha=0.2)

        session_date = intraday[-1]["date"][:10]
        ax.set_title(f"{symbol} — {session_date}", color='#f8fafc',
                     fontsize=14, fontweight='bold', pad=12)
        ax.tick_params(colors='#94a3b8', labelsize=10)
        ax.set_xticks([])
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            ax.spines[side].set_color('#334155')

        plt.tight_layout()
        plt.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close()
        return output_path

    def create_dashboard_overlay(self, title: str, ticker: str, change_pct: str,
                                 intraday: List[Dict[str, Any]], output_path: str,
                                 is_shorts: bool = True) -> str:
        """Generates the dark-mode stock card with the real chart embedded."""
        width, height = (960, 1200) if is_shorts else (1600, 700)
        img = Image.new("RGBA", (width, height), (15, 23, 42, 240))
        draw = ImageDraw.Draw(img)

        draw.rectangle([0, 0, width - 1, height - 1], outline=(56, 189, 248, 255), width=6)
        draw.rectangle([40, 40, width - 40, 140], fill=(30, 41, 59, 255))
        draw.text((60, 65), "US STOCK MARKET DAILY", fill=(56, 189, 248, 255))

        pct = str(change_pct).lstrip("+")
        is_positive = not pct.startswith("-")
        change_color = (34, 197, 94, 255) if is_positive else (239, 68, 68, 255)
        sign = "+" if is_positive else ""

        draw.text((60, 180), f"TICKER: {ticker}", fill=(248, 250, 252, 255))
        draw.text((60, 260), f"CHANGE: {sign}{pct}%", fill=change_color)

        chart_path = self.create_stock_chart_image(ticker, intraday)
        chart_img = Image.open(chart_path).convert("RGBA")
        chart_img = chart_img.resize((width - 120, 500))
        img.paste(chart_img, (60, 360), chart_img)

        img.save(output_path)
        return output_path

    def render_video(self, audio_path: str, ass_sub_path: str, output_filename: str,
                     card_img_path: str, is_shorts: bool = True) -> str:
        """Renders the final MP4: animated dark gradient + the provided stock card + subtitles.

        The card must be pre-rendered with the video's actual ticker/change/chart —
        this function no longer builds its own card.
        """
        out_video = str(OUTPUT_DIR / output_filename)
        width, height = SHORTS_RES if is_shorts else LONG_RES

        filter_complex = (
            f"[0:v]scale={width}:{height},fps=30[bg]; "
            f"[1:v]scale=900:-1[card]; "
            f"[bg][card]overlay=(W-w)/2:(H-h)/2[v1]; "
            f"[v1]ass={ass_sub_path}[outv]"
        )

        # Slow-moving dark blue gradient — reads as "finance dashboard", unlike the
        # old cellauto noise pattern.
        gradient_src = (
            f"gradients=s={width}x{height}:c0=0x0f172a:c1=0x1e3a5f:"
            f"speed=0.02:rate=30"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", gradient_src,
            "-i", card_img_path,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "2:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            out_video,
        ]

        logger.info(f"Rendering video to: {out_video}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("Video render completed successfully!")
            return out_video

        logger.error(f"FFmpeg render error: {result.stderr[-800:]}")
        # Fallback: solid dark background if the gradients filter is unavailable
        fallback_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x0f172a:s={width}x{height}:r=30",
            "-i", card_img_path,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "2:a",
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            out_video,
        ]
        fb = subprocess.run(fallback_cmd, capture_output=True, text=True)
        if fb.returncode != 0:
            logger.error(f"Fallback render also failed: {fb.stderr[-800:]}")
            return ""
        return out_video


if __name__ == "__main__":
    ve = VideoEngine()
    print("Video Engine initialized.")
