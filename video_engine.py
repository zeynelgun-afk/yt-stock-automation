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

# The channel's signature grade, applied to every stock-footage background
# regardless of where the clip came from. Pexels clips and Higgsfield
# generations arrive with wildly different white balance; without a common
# grade a recap that cuts between them looks like four different channels.
# Teal shadows against amber highlights sits under the card's #0f172a palette,
# and the blur keeps the card, chart and subtitles the only things in focus.
BG_LOOK = (
    "boxblur=5:2,eq=brightness=-0.25:contrast=1.1:saturation=1.2,"
    "colorbalance=rs=-0.06:bs=0.10:rm=0.04:bm=-0.04:rh=0.08:bh=-0.06"
)

# Background clips per long recap — one scene change per major script section.
# A 35-second Short holds fine on a single clip; a 5-6 minute recap on one
# looping clip stops changing about 20 seconds in.
LONG_BG_CLIPS = 5
BG_XFADE_SECONDS = 1.0
MIN_BG_SCENE_SECONDS = 25.0  # below this a cut reads as flicker, not as pacing

# Higgsfield charges two jobs (image, then video) per clip and can take minutes
# each, so only the first couple of scenes are AI-generated and the rest come
# from Pexels. The shared BG_LOOK grade is what makes the mix hold together.
HIGGSFIELD_MAX_CLIPS = 2


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

    def fetch_background_videos(self, keywords: List[str], is_shorts: bool = True,
                                count: int = 1) -> List[str]:
        """Up to `count` visually distinct background clips, one per keyword.

        Source chain per clip: Higgsfield AI generation (if API keys are
        configured, capped at HIGGSFIELD_MAX_CLIPS) -> Pexels stock footage.
        Returns however many clips it managed to get — possibly fewer than
        `count`, possibly empty, in which case the renderer uses its gradient.
        """
        clips: List[str] = []
        remaining = list(keywords)

        try:
            from higgsfield_client import HiggsfieldClient
            hf = HiggsfieldClient()
            if hf.enabled:
                for theme in remaining[:min(count, HIGGSFIELD_MAX_CLIPS)]:
                    path = hf.generate_background_video([theme], is_shorts=is_shorts)
                    if path:
                        clips.append(path)
                        remaining.remove(theme)
                    else:
                        logger.warning(f"Higgsfield generation failed for '{theme}'; "
                                       "Pexels will cover this scene.")
        except Exception as e:
            logger.warning(f"Higgsfield unavailable ({e}); falling back to Pexels.")

        for query in remaining:
            if len(clips) >= count:
                break
            path = self._fetch_pexels_clip(query, is_shorts=is_shorts)
            if path and path not in clips:
                clips.append(path)

        if not clips:
            logger.info("No background clips available; renderer will use the gradient.")
        return clips

    def fetch_background_video(self, keywords: List[str], is_shorts: bool = True) -> Optional[str]:
        """Single background clip — the Shorts path, where one clip is enough."""
        clips = self.fetch_background_videos(keywords, is_shorts=is_shorts, count=1)
        return clips[0] if clips else None

    # ------------------------------------------------------------------ pexels

    def fetch_pexels_video(self, keywords: List[str], is_shorts: bool = True) -> Optional[str]:
        """First Pexels clip matching any of the keywords, in order."""
        for query in keywords:
            path = self._fetch_pexels_clip(query, is_shorts=is_shorts)
            if path:
                return path
        return None

    def _fetch_pexels_clip(self, query: str, is_shorts: bool = True) -> Optional[str]:
        """Downloads one Pexels stock clip for a single search query."""
        if not self.pexels_key:
            logger.info("PEXELS_API_KEY is not configured; using default background.")
            return None

        orientation = "portrait" if is_shorts else "landscape"
        try:
            url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation={orientation}"
            headers = {"Authorization": self.pexels_key}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"Pexels API error {resp.status_code} for query: {query}")
                return None
            videos = resp.json().get("videos", [])
            if not videos:
                return None

            # Pick the first video with HD quality
            selected_url = None
            for vf in videos[0].get("video_files", []):
                if vf.get("quality") == "hd":
                    selected_url = vf.get("link")
                    break
            if not selected_url and videos[0].get("video_files"):
                selected_url = videos[0]["video_files"][0].get("link")

            if not selected_url:
                return None

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
                                 franchise_name: str = "", logo_path: Optional[str] = None,
                                 hero_number: str = "", hero_label: str = "") -> str:
        """Glassmorphism first-frame engineered stock card:
        Translucent backdrop + glowing neon accents + high-contrast text overlay + HD Company Logo.

        `hero_number` is the story's own headline figure ("$28.2M", "+290%",
        "6,297%") and gets the largest type on the card, with `hero_label`
        naming it above ("CEO SOLD"). The session change % moves to a small
        chip beside the ticker.

        The card used to give its biggest type to change_pct unconditionally,
        so a video about a $28.2 million insider sale led with "-0.56%" while
        the number the script was actually about appeared only in small body
        text. Falls back to the old change-led layout when no hero is supplied.
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

        hero = str(hero_number).strip()
        if hero:
            # Hero-led layout: story number dominates, ticker and change shrink
            # to identifying marks. Geometry differs per orientation because the
            # long card puts the chart in the right half, halving the text width.
            if is_shorts:
                tick_size, tick_y = 96, 150
                label_y, label_size = 292, 36
                hero_y, hero_max = 336, 200
                title_y, title_size, title_wrap, title_lines = 570, 42, 38, 3
                avail = width - 96
            else:
                tick_size, tick_y = 76, 150
                label_y, label_size = 250, 30
                hero_y, hero_max = 288, 140
                title_y, title_size, title_wrap, title_lines = 470, 34, 34, 3
                avail = layout["chart_box"][0] - 96

            draw.text((48, tick_y), ticker, font=_font(tick_size), fill=(248, 250, 252, 255))
            # Change chip sits on the ticker's baseline, right of the symbol
            chip_x = 48 + draw.textlength(ticker, font=_font(tick_size)) + 28
            chip_size = round(tick_size * 0.46)
            draw.text((chip_x, tick_y + tick_size - chip_size - 6), change_text,
                      font=_font(chip_size), fill=change_color)

            if hero_label:
                draw.text((48, label_y), hero_label.upper()[:28],
                          font=_font(label_size), fill=(148, 163, 184, 255))

            # Shrink to fit rather than overflow the card — hero strings vary
            # from "+290%" to "$1.56 MILLION"
            hero_size = hero_max
            while hero_size > 60 and draw.textlength(hero, font=_font(hero_size)) > avail:
                hero_size -= 4
            draw.text((48, hero_y), hero, font=_font(hero_size), fill=(248, 250, 252, 255))
        elif is_shorts:
            draw.text((48, 160), ticker, font=_font(190), fill=(248, 250, 252, 255))
            draw.text((48, 390), change_text, font=_font(130), fill=change_color)
            title_y, title_size, title_wrap, title_lines = 580, 42, 38, 3
        else:
            draw.text((48, 150), ticker, font=_font(140), fill=(248, 250, 252, 255))
            draw.text((48, 330), change_text, font=_font(96), fill=change_color)
            title_y, title_size, title_wrap, title_lines = 470, 34, 34, 3

        y = title_y
        for line in textwrap.wrap(title, width=title_wrap)[:title_lines]:
            draw.text((48, y), line, font=_font(title_size, bold=False), fill=(148, 163, 184, 255))
            y += round(title_size * 1.38)

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

        # Neon glow: widening translucent copies under the main line
        glow_lines = [
            ax.plot([], [], color=line_color, linewidth=lw, alpha=a,
                    solid_capstyle='round', zorder=2)[0]
            for lw, a in ((14, 0.08), (9, 0.16), (6, 0.30))
        ]
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
            for gl in glow_lines:
                gl.set_data(xs, ys)
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

    def _bg_chain(self, clips: List[str], width: int, height: int,
                  audio_dur: float) -> tuple[List[str], str]:
        """FFmpeg inputs + filter chain producing [bg] from stock-footage clips.

        One clip loops for the whole video. Several clips are cut into equal
        segments that cross-fade into each other, so a 5-6 minute recap gets a
        scene change per script section instead of the same twelve seconds of
        b-roll cycling for six minutes. Every clip is looped first, because
        Pexels footage is usually 10-20 seconds and a segment is over a minute.

        The last segment is frame-cloned open-ended (`tpad`) so a rounding error
        in the segment maths can never end the background before the voiceover.
        """
        fit = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
               f"crop={width}:{height},fps=30")

        d = BG_XFADE_SECONDS
        n = len(clips)
        seg = 0.0
        if n > 1:
            if audio_dur <= 0:
                # Nothing to divide into segments — loop one clip instead of
                # cutting to `trim=0:0` and rendering an empty background.
                n = 1
            else:
                # Drop scenes rather than let them get short: cutting every few
                # seconds under a static card reads as flicker, not as pacing.
                n = max(1, min(n, int((audio_dur + 1.0) // MIN_BG_SCENE_SECONDS)))
                if n > 1:
                    seg = (audio_dur + 1.0 + (n - 1) * d) / n

        if n == 1:
            inputs = ["-stream_loop", "-1", "-i", clips[0]]
            return inputs, f"[0:v]{fit},{BG_LOOK}[bg]; "

        inputs: List[str] = []
        chain = ""
        for i in range(n):
            inputs += ["-stream_loop", "-1", "-i", clips[i]]
            chain += f"[{i}:v]{fit},trim=0:{seg:.3f},setpts=PTS-STARTPTS[s{i}]; "

        d = BG_XFADE_SECONDS
        prev = "[s0]"
        for i in range(1, n):
            # Running length after i-1 fades, minus the fade itself
            offset = i * seg - i * d
            out = "[bg_mix]" if i == n - 1 else f"[x{i}]"
            chain += (f"{prev}[s{i}]xfade=transition=fade:duration={d:.3f}:"
                      f"offset={offset:.3f}{out}; ")
            prev = out
        chain += f"[bg_mix]{BG_LOOK},tpad=stop_mode=clone:stop=-1[bg]; "
        return inputs, chain

    def render_video(self, audio_path: str, ass_sub_path: str, output_filename: str,
                     card_img_path: str, chart_video_path: Optional[str] = None,
                     is_shorts: bool = True,
                     bg_video_path: Optional[str] | List[str] = None) -> str:
        """Final MP4: HD background (stock footage or animated gradient) +
        glassmorphism stock card + left-to-right chart animation + subtitles.

        `bg_video_path` takes a single clip path or a list of them; a list of
        two or more is cross-faded across the video (see `_bg_chain`).
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

        # Check for background music and SFX audio assets
        bg_music_file = BASE_DIR / "assets" / "music" / "bg_music.wav"
        whoosh_file = BASE_DIR / "assets" / "sfx" / "whoosh.wav"

        zoom = (
            f"zoompan=z='min(1+0.00008*on,1.10)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps=30"
        )

        def build_cmd(bg_inputs: List[str], bg_filter: str, n_bg: int) -> List[str]:
            """`bg_filter` consumes inputs 0..n_bg-1 and must produce [bg].

            Every other input index is derived from n_bg, so the background can
            occupy one input (gradient, single clip) or several (cross-faded
            scenes) without the card/chart/audio maps drifting out of sync.
            """
            cur_idx = n_bg
            inputs = [*bg_inputs, "-i", card_img_path]
            card_idx = cur_idx
            cur_idx += 1

            if chart_video_path:
                inputs += ["-i", chart_video_path]
                chart_idx = cur_idx
                cur_idx += 1
                # The card and chart stay on screen for the whole video.
                #
                # This used to hide both between t=4s and t=15s for a "cinematic
                # full-screen B-roll" beat. Audience-retention data killed that
                # idea: the four most-viewed videos each lost ~60% of viewers
                # between second 3 and second 14 — precisely the blackout window.
                # What the viewer got there was a blurred, darkened stock clip
                # with no ticker, no number and no subtitle: eleven seconds of
                # nothing to hold on to.
                #
                # Scene changes now happen in the background layer only (see
                # `_bg_chain`), underneath a card that never leaves.
                chart_chain = (
                    f"[{chart_idx}:v]scale={chart_w}:{chart_h},tpad=stop_mode=clone:stop=-1[chart]; "
                    f"[v1][chart]overlay={chart_x}:{chart_y}[v2]; "
                )
            else:
                chart_chain = "[v1]null[v2]; "

            inputs += ["-i", audio_path]
            audio_idx = cur_idx
            cur_idx += 1

            audio_mix_filter = ""
            audio_map = f"{audio_idx}:a"
            if bg_music_file.exists():
                inputs += ["-stream_loop", "-1", "-i", str(bg_music_file)]
                music_idx = cur_idx
                cur_idx += 1
                if whoosh_file.exists():
                    inputs += ["-i", str(whoosh_file)]
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

            filter_complex = (
                f"{bg_filter}"
                f"[{card_idx}:v]scale={scaled_w}:-1[card]; "
                f"[bg][card]overlay={card_x}:{card_y}[v1]; "
                f"{chart_chain}"
                f"[v2]{zoom}[v3]; "
                f"[v3]ass={ass_sub_path}[outv]"
            )

            return [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_complex + audio_mix_filter,
                "-map", "[outv]", "-map", audio_map,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-t", max_dur,
                out_video,
            ]

        logger.info(f"Rendering video to: {out_video}")

        # Try stock-footage background first if any clips were fetched
        raw = bg_video_path or []
        clips = [raw] if isinstance(raw, str) else list(raw)
        clips = [c for c in clips if c and Path(c).exists()]
        if clips:
            logger.info(f"Using {len(clips)} background clip(s): {', '.join(clips)}")
            bg_inputs, bg_filter = self._bg_chain(clips, width, height, audio_dur)
            result = subprocess.run(build_cmd(bg_inputs, bg_filter, len(clips)),
                                    capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Video render with stock-footage background completed successfully!")
                return out_video
            logger.warning(f"Stock-footage render failed, falling back to gradient: {result.stderr[-400:]}")

        plain_bg = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps=30[bg]; "
        )

        # Gradient fallback
        gradient_src = (
            f"gradients=s={width}x{height}:c0=0x0f172a:c1=0x1e3a5f:"
            f"speed=0.08:rate=30"
        )
        result = subprocess.run(build_cmd(["-f", "lavfi", "-i", gradient_src], plain_bg, 1),
                                capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Video render with gradient completed successfully!")
            return out_video

        # Solid fallback
        solid_src = f"color=c=0x0f172a:s={width}x{height}:r=30"
        fb = subprocess.run(build_cmd(["-f", "lavfi", "-i", solid_src], plain_bg, 1),
                            capture_output=True, text=True)
        if fb.returncode != 0:
            logger.error(f"Fallback render also failed: {fb.stderr[-800:]}")
            return ""
        return out_video


if __name__ == "__main__":
    ve = VideoEngine()
    print("Video Engine initialized.")

