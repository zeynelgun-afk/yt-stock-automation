import subprocess
import logging
import textwrap
from pathlib import Path
from typing import Dict, Any, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont

from config import PEXELS_API_KEY, TEMP_DIR, OUTPUT_DIR, SHORTS_RES, LONG_RES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NEON_GREEN = '#22c55e'
NEON_RED = '#ef4444'
DARK_BG = '#0f172a'

# First existing path wins — Arch and Debian/Ubuntu (GitHub Actions) layouts
FONT_CANDIDATES = {
    True: [   # bold
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
    False: [  # regular
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
}

CHART_FPS = 25
CHART_DRAW_SECONDS = 3.0  # how long the line takes to draw left-to-right


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES[bold]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    logger.warning("No TTF font found, falling back to PIL default")
    return ImageFont.load_default()


def _card_layout(is_shorts: bool) -> Dict[str, Any]:
    """Card pixel geometry. chart_box is (x, y, w, h) in card coordinates —
    render_video maps it into video coordinates for the animated chart overlay."""
    if is_shorts:
        return {
            "card_size": (960, 1300),
            "scaled_w": 900,          # card width on the 1080x1920 canvas
            "chart_box": (40, 800, 880, 460),
        }
    return {
        "card_size": (1600, 760),
        "scaled_w": 1400,             # card width on the 1920x1080 canvas
        "chart_box": (760, 90, 800, 630),
    }


class VideoEngine:
    def __init__(self, pexels_key: str = PEXELS_API_KEY):
        self.pexels_key = pexels_key

    # ------------------------------------------------------------------ card

    def create_dashboard_overlay(self, title: str, ticker: str, change_pct: str,
                                 output_path: str, is_shorts: bool = True,
                                 franchise_name: str = "") -> str:
        """First-frame engineered stock card: the shock number IS the opening frame.

        Huge ticker + huge colored change% readable before any speech starts —
        no logo, no intro. The chart area is left empty; the animated chart
        video is overlaid there by render_video().
        """
        layout = _card_layout(is_shorts)
        width, height = layout["card_size"]
        img = Image.new("RGBA", (width, height), (15, 23, 42, 242))
        draw = ImageDraw.Draw(img)

        pct = str(change_pct).lstrip("+")
        is_positive = not pct.startswith("-")
        change_color = (34, 197, 94, 255) if is_positive else (239, 68, 68, 255)
        change_text = f"{'+' if is_positive else ''}{pct}%"

        draw.rectangle([0, 0, width - 1, height - 1], outline=(56, 189, 248, 255), width=6)

        badge = "US STOCK MARKET DAILY" + (f"  •  {franchise_name.upper()}" if franchise_name else "")
        draw.rectangle([36, 36, width - 36, 116], fill=(30, 41, 59, 255))
        badge_size = 30
        while badge_size > 16 and draw.textlength(badge, font=_font(badge_size)) > width - 112:
            badge_size -= 2
        draw.text((56, 76 - badge_size // 2), badge, font=_font(badge_size), fill=(56, 189, 248, 255))

        if is_shorts:
            draw.text((48, 160), ticker, font=_font(190), fill=(248, 250, 252, 255))
            draw.text((48, 390), change_text, font=_font(130), fill=change_color)
            y = 580
            for line in textwrap.wrap(title, width=38)[:3]:
                draw.text((48, y), line, font=_font(42, bold=False), fill=(148, 163, 184, 255))
                y += 58
        else:
            draw.text((48, 150), ticker, font=_font(140), fill=(248, 250, 252, 255))
            draw.text((48, 330), change_text, font=_font(96), fill=change_color)
            y = 470
            for line in textwrap.wrap(title, width=34)[:3]:
                draw.text((48, y), line, font=_font(34, bold=False), fill=(148, 163, 184, 255))
                y += 48

        # Subtle frame marking where the animated chart lands
        cx, cy, cw, ch = layout["chart_box"]
        draw.rectangle([cx - 2, cy - 2, cx + cw + 2, cy + ch + 2],
                       outline=(51, 65, 85, 255), width=2)

        img.save(output_path)
        return output_path

    # ----------------------------------------------------------------- chart

    def create_animated_chart(self, symbol: str, intraday: List[Dict[str, Any]],
                              output_path: str) -> str:
        """Real intraday line drawn left-to-right (matplotlib frames -> ffmpeg).

        `intraday` must be actual candles from FMPDataFetcher.get_intraday_chart()
        (oldest first). Fabricated chart data is never acceptable on this channel.
        Raises RuntimeError if the chart video cannot be produced.
        """
        if not intraday:
            raise RuntimeError(f"No intraday data provided for {symbol} chart")

        closes = [row["close"] for row in intraday]
        n = len(closes)
        is_up = closes[-1] >= closes[0]
        line_color = NEON_GREEN if is_up else NEON_RED

        frames_dir = Path(TEMP_DIR) / f"chart_frames_{symbol.strip('^')}"
        frames_dir.mkdir(parents=True, exist_ok=True)
        for old in frames_dir.glob("*.png"):
            old.unlink()

        total_frames = int(CHART_FPS * CHART_DRAW_SECONDS)
        y_min, y_max = min(closes), max(closes)
        pad = (y_max - y_min) * 0.08 or abs(y_max) * 0.01 or 1.0

        fig, ax = plt.subplots(figsize=(8.8, 4.6), dpi=100)
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARK_BG)
        ax.set_xlim(0, n - 1)
        ax.set_ylim(y_min - pad, y_max + pad)
        ax.set_xticks([])
        ax.tick_params(colors='#94a3b8', labelsize=11)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            ax.spines[side].set_color('#334155')
        session_date = intraday[-1]["date"][:10]
        ax.set_title(f"{symbol} — {session_date}", color='#f8fafc',
                     fontsize=15, fontweight='bold', pad=10)

        line, = ax.plot([], [], color=line_color, linewidth=4,
                        solid_capstyle='round', zorder=3)
        dot, = ax.plot([], [], 'o', color=line_color, markersize=9, zorder=4)
        fill = None
        fig.tight_layout()

        for f in range(total_frames):
            # Ease-out reveal: fast start, settles at the end
            progress = 1 - (1 - (f + 1) / total_frames) ** 2
            upto = max(2, round(progress * n))
            xs = list(range(upto))
            ys = closes[:upto]
            line.set_data(xs, ys)
            dot.set_data([xs[-1]], [ys[-1]])
            if fill is not None:
                fill.remove()
            fill = ax.fill_between(xs, ys, y_min - pad, color=line_color, alpha=0.18)
            fig.savefig(frames_dir / f"f_{f:04d}.png", facecolor=fig.get_facecolor())
        plt.close(fig)

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(CHART_FPS),
            "-i", str(frames_dir / "f_%04d.png"),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Chart video encode failed: {result.stderr[-400:]}")
        return output_path

    def create_stock_chart_image(self, symbol: str, intraday: List[Dict[str, Any]],
                                 output_path: str = None) -> str:
        """Static real-intraday chart (used by the thumbnail generator)."""
        if not intraday:
            raise RuntimeError(f"No intraday data provided for {symbol} chart")
        if not output_path:
            output_path = str(TEMP_DIR / "chart_overlay.png")

        closes = [row["close"] for row in intraday]
        is_up = closes[-1] >= closes[0]
        line_color = NEON_GREEN if is_up else NEON_RED

        fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARK_BG)
        ax.plot(range(len(closes)), closes, color=line_color, linewidth=5)
        ax.fill_between(range(len(closes)), closes, min(closes), color=line_color, alpha=0.2)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        plt.tight_layout(pad=0.5)
        plt.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor='none',
                    transparent=False)
        plt.close()
        return output_path

    # ------------------------------------------------------------- thumbnail

    def create_thumbnail(self, ticker: str, change_pct: str, hook_words: str,
                         intraday: List[Dict[str, Any]], output_path: str) -> str:
        """1280x720 thumbnail for long videos: big number, direction arrow,
        3-5 word hook, real chart as backdrop. High contrast, no clutter."""
        width, height = 1280, 720
        img = Image.new("RGB", (width, height), (15, 23, 42))

        # Real chart as backdrop, right side
        chart_path = self.create_stock_chart_image(ticker, intraday,
                                                   str(TEMP_DIR / "thumb_chart.png"))
        chart = Image.open(chart_path).convert("RGB").resize((820, 410))
        img.paste(chart, (440, 290))

        draw = ImageDraw.Draw(img)
        pct = str(change_pct).lstrip("+")
        is_positive = not pct.startswith("-")
        color = (34, 197, 94) if is_positive else (239, 68, 68)
        arrow = "▲" if is_positive else "▼"

        draw.text((60, 50), ticker, font=_font(150), fill=(248, 250, 252),
                  stroke_width=4, stroke_fill=(0, 0, 0))
        draw.text((60, 240), f"{arrow} {'+' if is_positive else ''}{pct}%",
                  font=_font(120), fill=color, stroke_width=4, stroke_fill=(0, 0, 0))
        y = 430
        for line in textwrap.wrap(hook_words, width=18)[:2]:
            draw.text((60, y), line.upper(), font=_font(72), fill=(250, 204, 21),
                      stroke_width=5, stroke_fill=(0, 0, 0))
            y += 92

        img.save(output_path, quality=92)
        return output_path

    # ---------------------------------------------------------------- render

    def render_video(self, audio_path: str, ass_sub_path: str, output_filename: str,
                     card_img_path: str, chart_video_path: Optional[str] = None,
                     is_shorts: bool = True) -> str:
        """Final MP4: animated dark gradient + stock card + left-to-right chart
        animation + subtitles. Card and chart must be pre-rendered with the
        video's actual ticker/change/candles."""
        out_video = str(OUTPUT_DIR / output_filename)
        width, height = SHORTS_RES if is_shorts else LONG_RES

        layout = _card_layout(is_shorts)
        card_w, card_h = layout["card_size"]
        scaled_w = layout["scaled_w"]
        scale = scaled_w / card_w
        scaled_h = round(card_h * scale)
        card_x = (width - scaled_w) // 2
        card_y = (height - scaled_h) // 2

        cx, cy, cw, ch = layout["chart_box"]
        chart_x = card_x + round(cx * scale)
        chart_y = card_y + round(cy * scale)
        chart_w = round(cw * scale) // 2 * 2   # libx264 needs even dims
        chart_h = round(ch * scale) // 2 * 2

        gradient_src = (
            f"gradients=s={width}x{height}:c0=0x0f172a:c1=0x1e3a5f:"
            f"speed=0.02:rate=30"
        )
        solid_src = f"color=c=0x0f172a:s={width}x{height}:r=30"

        # Inputs after the background: card [1], optional chart [2], audio [last]
        tail_inputs = ["-i", card_img_path]
        if chart_video_path:
            tail_inputs += ["-i", chart_video_path]
            audio_idx = 3
            chart_chain = (
                f"[2:v]scale={chart_w}:{chart_h},tpad=stop_mode=clone:stop=-1[chart]; "
                f"[v1][chart]overlay={chart_x}:{chart_y}[v2]; "
            )
        else:
            audio_idx = 2
            chart_chain = "[v1]null[v2]; "
        tail_inputs += ["-i", audio_path]

        filter_complex = (
            f"[0:v]scale={width}:{height},fps=30[bg]; "
            f"[1:v]scale={scaled_w}:-1[card]; "
            f"[bg][card]overlay={card_x}:{card_y}[v1]; "
            f"{chart_chain}"
            f"[v2]ass={ass_sub_path}[outv]"
        )

        def build_cmd(bg_src: str) -> List[str]:
            return [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", bg_src,
                *tail_inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", f"{audio_idx}:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-t", "900",
                out_video,
            ]

        logger.info(f"Rendering video to: {out_video}")
        result = subprocess.run(build_cmd(gradient_src), capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Video render completed successfully!")
            return out_video

        logger.error(f"FFmpeg render error: {result.stderr[-800:]}")
        # Fallback: solid dark background if the gradients filter is unavailable
        fb = subprocess.run(build_cmd(solid_src), capture_output=True, text=True)
        if fb.returncode != 0:
            logger.error(f"Fallback render also failed: {fb.stderr[-800:]}")
            return ""
        return out_video


if __name__ == "__main__":
    ve = VideoEngine()
    print("Video Engine initialized.")
