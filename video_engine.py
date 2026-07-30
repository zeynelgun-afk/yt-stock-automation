import math
import subprocess
import logging
import textwrap
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont

from config import PEXELS_API_KEY, TEMP_DIR, OUTPUT_DIR, SHORTS_RES, LONG_RES, BASE_DIR

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

    # ------------------------------------------------------------------ background

    def fetch_background_video(self, keywords: List[str], is_shorts: bool = True) -> Optional[str]:
        """Background clip source chain: Higgsfield AI generation (if API keys
        are configured) -> Pexels stock footage -> None (animated gradient)."""
        try:
            from higgsfield_client import HiggsfieldClient
            hf = HiggsfieldClient()
            if hf.enabled:
                path = hf.generate_background_video(keywords, is_shorts=is_shorts)
                if path:
                    return path
                logger.warning("Higgsfield generation failed; falling back to Pexels.")
        except Exception as e:
            logger.warning(f"Higgsfield unavailable ({e}); falling back to Pexels.")
        return self.fetch_pexels_video(keywords, is_shorts=is_shorts)

    # ------------------------------------------------------------------ pexels

    def fetch_pexels_video(self, keywords: List[str], is_shorts: bool = True) -> Optional[str]:
        """Fetches a relevant stock video background from Pexels API matching the keywords."""
        if not self.pexels_key:
            logger.info("PEXELS_API_KEY is not configured; using default background.")
            return None
        
        orientation = "portrait" if is_shorts else "landscape"
        for query in keywords:
            try:
                url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation={orientation}"
                headers = {"Authorization": self.pexels_key}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"Pexels API error {resp.status_code} for query: {query}")
                    continue
                data = resp.json()
                videos = data.get("videos", [])
                if not videos:
                    continue
                
                # Pick the first video with HD quality
                selected_url = None
                for vf in videos[0].get("video_files", []):
                    if vf.get("quality") == "hd":
                        selected_url = vf.get("link")
                        break
                if not selected_url and videos[0].get("video_files"):
                    selected_url = videos[0]["video_files"][0].get("link")

                if not selected_url:
                    continue

                safe_name = "".join([c if c.isalnum() else "_" for c in query])
                out_path = str(TEMP_DIR / f"pexels_{safe_name}_{'shorts' if is_shorts else 'long'}.mp4")
                
                logger.info(f"Downloading Pexels stock video for '{query}'...")
                r = requests.get(selected_url, stream=True, timeout=30)
                if r.status_code == 200:
                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=16384):
                            f.write(chunk)
                    logger.info(f"Downloaded Pexels video clip: {out_path}")
                    return out_path
            except Exception as e:
                logger.warning(f"Failed fetching Pexels video for '{query}': {e}")
        return None

    # ------------------------------------------------------------------ logo

    def fetch_company_logo(self, symbol: str) -> Optional[str]:
        """Fetches HD company logo PNG from Parqet API for the given stock symbol."""
        symbol_clean = symbol.strip("^").upper()
        out_path = str(TEMP_DIR / f"logo_{symbol_clean}.png")
        if Path(out_path).exists():
            return out_path
        try:
            url = f"https://assets.parqet.com/logos/symbol/{symbol_clean}?format=png&size=300"
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and len(r.content) > 500:
                with open(out_path, "wb") as f:
                    f.write(r.content)
                logger.info(f"Downloaded company logo for {symbol_clean}")
                return out_path
        except Exception as e:
            logger.warning(f"Could not fetch logo for {symbol_clean}: {e}")
        return None

    # ------------------------------------------------------------------ card

    def create_dashboard_overlay(self, title: str, ticker: str, change_pct: str,
                                 output_path: str, is_shorts: bool = True,
                                 franchise_name: str = "", logo_path: Optional[str] = None) -> str:
        """Glassmorphism first-frame engineered stock card:
        Translucent backdrop + glowing neon accents + high-contrast text overlay + HD Company Logo.
        """
        layout = _card_layout(is_shorts)
        width, height = layout["card_size"]
        # Translucent RGBA dark slate background (80% opacity for glassmorphism overlay)
        img = Image.new("RGBA", (width, height), (15, 23, 42, 205))
        draw = ImageDraw.Draw(img)

        pct = str(change_pct).lstrip("+")
        is_positive = not pct.startswith("-")
        change_color = (34, 197, 94, 255) if is_positive else (239, 68, 68, 255)
        change_text = f"{'+' if is_positive else ''}{pct}%"

        # Glass shine highlight line near top edge
        draw.rectangle([10, 10, width - 10, 24], fill=(255, 255, 255, 20))

        # Double glowing border frame
        draw.rectangle([0, 0, width - 1, height - 1], outline=(56, 189, 248, 230), width=5)
        draw.rectangle([5, 5, width - 6, height - 6], outline=(30, 41, 59, 200), width=3)

        # Header Badge
        badge = "US STOCK MARKET DAILY" + (f"  •  {franchise_name.upper()}" if franchise_name else "")
        draw.rectangle([36, 36, width - 36, 116], fill=(30, 41, 59, 220), outline=(56, 189, 248, 120), width=2)
        badge_size = 30
        while badge_size > 16 and draw.textlength(badge, font=_font(badge_size)) > width - 112:
            badge_size -= 2
        draw.text((56, 76 - badge_size // 2), badge, font=_font(badge_size), fill=(56, 189, 248, 255))

        # Paste company logo if available
        if not logo_path:
            logo_path = self.fetch_company_logo(ticker)
        
        if logo_path and Path(logo_path).exists():
            try:
                logo_img = Image.open(logo_path).convert("RGBA")
                logo_size = (150, 150) if is_shorts else (120, 120)
                logo_img = logo_img.resize(logo_size, Image.Resampling.LANCZOS)
                
                # Draw rounded white background badge for logo
                lx = width - logo_size[0] - 56
                ly = 150
                badge_bg = Image.new("RGBA", logo_size, (255, 255, 255, 240))
                img.paste(badge_bg, (lx, ly))
                img.paste(logo_img, (lx, ly), logo_img)
                draw.rectangle([lx - 2, ly - 2, lx + logo_size[0] + 2, ly + logo_size[1] + 2],
                               outline=(56, 189, 248, 255), width=3)
            except Exception as e:
                logger.warning(f"Could not render logo image: {e}")

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
                       outline=(56, 189, 248, 180), width=2)

        img.save(output_path)
        return output_path

    # ----------------------------------------------------------------- chart

    def create_animated_chart(self, symbol: str, intraday: List[Dict[str, Any]],
                              output_path: str, draw_seconds: float = CHART_DRAW_SECONDS) -> str:
        """Real intraday line drawn left-to-right (matplotlib frames -> ffmpeg).

        `intraday` must be actual candles from FMPDataFetcher.get_intraday_chart()
        (oldest first). Fabricated chart data is never acceptable on this channel.
        `draw_seconds` stretches the reveal — pass ~80% of the audio length so
        the chart keeps moving for the whole video instead of freezing early.
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

        # Cap matplotlib frames (CI time); ffmpeg framerate compensates so the
        # clip still lasts exactly draw_seconds
        total_frames = min(int(CHART_FPS * draw_seconds), 600)
        framerate = total_frames / draw_seconds
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
            # Pulsing endpoint dot keeps the frame alive even late in the reveal
            dot.set_markersize(9 + 2.5 * math.sin(f * 0.35))
            dot.set_data([xs[-1]], [ys[-1]])
            if fill is not None:
                fill.remove()
            fill = ax.fill_between(xs, ys, y_min - pad, color=line_color, alpha=0.18)
            fig.savefig(frames_dir / f"f_{f:04d}.png", facecolor=fig.get_facecolor())
        plt.close(fig)

        cmd = [
            "ffmpeg", "-y",
            "-framerate", f"{framerate:.3f}",
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

    @staticmethod
    def _probe_duration(media_path: str) -> float:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", media_path],
                capture_output=True, text=True)
            return float(result.stdout.strip())
        except (ValueError, OSError):
            return 0.0

    def render_video(self, audio_path: str, ass_sub_path: str, output_filename: str,
                     card_img_path: str, chart_video_path: Optional[str] = None,
                     is_shorts: bool = True, bg_video_path: Optional[str] = None) -> str:
        """Final MP4: HD background (Pexels stock video or animated gradient) +
        glassmorphism stock card + left-to-right chart animation + subtitles.
        """
        out_video = str(OUTPUT_DIR / output_filename)

        # -shortest is unreliable on some ffmpeg builds when the audio graph
        # contains looped inputs (Ubuntu CI rendered to the 900s cap with the
        # tail silent) — so the output is explicitly cut at the voiceover end.
        audio_dur = self._probe_duration(audio_path)
        max_dur = f"{min(audio_dur + 0.3, 900.0):.2f}" if audio_dur > 0 else "900"
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

        # Track FFmpeg input indices precisely
        cur_idx = 1  # 0 is reserved for background video/gradient
        card_idx = cur_idx
        tail_inputs = ["-i", card_img_path]
        cur_idx += 1

        if chart_video_path:
            tail_inputs += ["-i", chart_video_path]
            chart_idx = cur_idx
            cur_idx += 1
            chart_chain = (
                f"[{chart_idx}:v]scale={chart_w}:{chart_h},tpad=stop_mode=clone:stop=-1[chart]; "
                f"[v1][chart]overlay={chart_x}:{chart_y}[v2]; "
            )
        else:
            chart_chain = "[v1]null[v2]; "

        tail_inputs += ["-i", audio_path]
        audio_idx = cur_idx
        cur_idx += 1

        # Check for background music and SFX audio assets
        bg_music_file = BASE_DIR / "assets" / "music" / "bg_music.wav"
        whoosh_file = BASE_DIR / "assets" / "sfx" / "whoosh.wav"

        audio_mix_filter = ""
        audio_map = f"{audio_idx}:a"

        if bg_music_file.exists():
            tail_inputs += ["-stream_loop", "-1", "-i", str(bg_music_file)]
            music_idx = cur_idx
            cur_idx += 1
            if whoosh_file.exists():
                tail_inputs += ["-i", str(whoosh_file)]
                whoosh_idx = cur_idx
                cur_idx += 1
                audio_mix_filter = (
                    f"; [{music_idx}:a]volume=0.08[bgm]; "
                    f"[{whoosh_idx}:a]adelay=4000|4000[sfx1]; "
                    f"[{audio_idx}:a][bgm][sfx1]amix=inputs=3:duration=first[outa]"
                )
            else:
                audio_mix_filter = (
                    f"; [{music_idx}:a]volume=0.08[bgm]; "
                    f"[{audio_idx}:a][bgm]amix=inputs=2:duration=first[outa]"
                )
            audio_map = "[outa]"

        zoom = (
            f"zoompan=z='min(1+0.00008*on,1.10)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps=30"
        )
        filter_complex = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=30[bg]; "
            f"[{card_idx}:v]scale={scaled_w}:-1[card]; "
            f"[bg][card]overlay={card_x}:{card_y}[v1]; "
            f"{chart_chain}"
            f"[v2]{zoom}[v3]; "
            f"[v3]ass={ass_sub_path}[outv]"
        )

        def build_cmd(bg_inputs: List[str], custom_filter: str) -> List[str]:
            return [
                "ffmpeg", "-y",
                *bg_inputs,
                *tail_inputs,
                "-filter_complex", custom_filter + audio_mix_filter,
                "-map", "[outv]", "-map", audio_map,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-t", max_dur,
                out_video,
            ]

        logger.info(f"Rendering video to: {out_video}")

        # Try Pexels background video first if available
        if bg_video_path and Path(bg_video_path).exists():
            logger.info(f"Using Pexels background video: {bg_video_path}")
            bg_inputs = ["-stream_loop", "-1", "-i", bg_video_path]
            # Multi-Scene Timeline Cut:
            # - 0.0s to 4.0s: Shock Opening Card + Logo + Background Video
            # - 4.0s to 15.0s: Pure Cinematic Full-Screen B-Roll Stock Footage (Card & chart hidden for dynamic scene change)
            # - 15.0s+: Card + Animated Matplotlib Live Chart + Summary
            if chart_video_path:
                chart_chain = (
                    f"[{chart_idx}:v]scale={chart_w}:{chart_h},tpad=stop_mode=clone:stop=-1[chart]; "
                    f"[v1][chart]overlay={chart_x}:{chart_y}:enable='between(t,0,4)+between(t,15,999)'[v2]; "
                )
            video_filter = (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=30,"
                f"boxblur=5:2,eq=brightness=-0.25:contrast=1.1:saturation=1.2[bg]; "
                f"[{card_idx}:v]scale={scaled_w}:-1[card]; "
                f"[bg][card]overlay={card_x}:{card_y}:enable='between(t,0,4)+between(t,15,999)'[v1]; "
                f"{chart_chain}"
                f"[v2]{zoom}[v3]; "
                f"[v3]ass={ass_sub_path}[outv]"
            )
            result = subprocess.run(build_cmd(bg_inputs, video_filter), capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Video render with Pexels background & Multi-Scene Cuts completed successfully!")
                return out_video
            logger.warning(f"Pexels background render failed, falling back to gradient: {result.stderr[-400:]}")

        # Gradient fallback
        gradient_src = (
            f"gradients=s={width}x{height}:c0=0x0f172a:c1=0x1e3a5f:"
            f"speed=0.08:rate=30"
        )
        bg_inputs = ["-f", "lavfi", "-i", gradient_src]
        result = subprocess.run(build_cmd(bg_inputs, filter_complex), capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Video render with gradient completed successfully!")
            return out_video

        # Solid fallback
        solid_src = f"color=c=0x0f172a:s={width}x{height}:r=30"
        bg_inputs = ["-f", "lavfi", "-i", solid_src]
        fb = subprocess.run(build_cmd(bg_inputs, filter_complex), capture_output=True, text=True)
        if fb.returncode != 0:
            logger.error(f"Fallback render also failed: {fb.stderr[-800:]}")
            return ""
        return out_video


if __name__ == "__main__":
    ve = VideoEngine()
    print("Video Engine initialized.")

