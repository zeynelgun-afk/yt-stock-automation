import re
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _ass_timestamp(seconds: float) -> str:
    """Seconds -> ASS `H:MM:SS.cc`.

    ASS uses one-digit hours and CENTIseconds, so an SRT stamp cannot be reused
    by slicing it: the old code produced "00:00:0..2" from "00:00:01,234" and
    libass silently dropped every malformed Dialogue line — the reason no video
    has ever rendered a subtitle.
    """
    cs = max(0, int(round(seconds * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


class SubtitleGenerator:
    """Parses SRT subtitles and converts them into YouTube Shorts style ASS (Advanced SubStation Alpha) format with highlighted words."""

    @staticmethod
    def srt_to_ass(srt_file_path: str, ass_output_path: str, is_shorts: bool = True) -> str:
        """Converts standard SRT into stylish ASS subtitles with bold centered text and outline."""
        if not Path(srt_file_path).exists():
            logger.error(f"SRT file not found: {srt_file_path}")
            return ""

        # ASS Header with Custom Fonts & Colors (Vibrant Yellow text on dark shadow)
        # Alignment=2 (bottom-center) for all, MarginV=240 for Shorts to avoid YT overlay UI
        alignment = 2
        # 56pt was ~3% of a 1920px frame — legible on a monitor, invisible on a
        # phone held at arm's length. Shorts subtitles carry the retention, so
        # they get ~5% of frame height; MarginV keeps them clear of the YT UI.
        font_size = 96 if is_shorts else 52
        margin_v = 240 if is_shorts else 60
        
        # PlayResX/Y are mandatory: without them libass assumes a 384x288 script
        # canvas and scales everything by 1920/288 = 6.7x — the 56pt font became
        # ~370px tall and the 240px margin became ~1600px, pushing every line off
        # the bottom of the frame. They must match the render resolution.
        play_res_x, play_res_y = (1080, 1920) if is_shorts else (1920, 1080)

        ass_header = f"""[Script Info]
Title: US Stock Market Daily Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{font_size},&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,{alignment},20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        try:
            with open(srt_file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Simple SRT parser regex
            pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:.|\n)*?)(?=\n\d+|\Z)')
            matches = pattern.findall(content)
            if not matches:
                logger.error(f"No subtitle cues parsed from {srt_file_path} — "
                             "the video would render with no subtitles.")
                return ""

            def to_sec(ts: str) -> float:
                parts = ts.replace(',', '.').split(':')
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

            # Edge-TTS now emits one cue per word, which would flash a single
            # word at a time. Group them into short phrases — the karaoke
            # highlight below still lands on the individual word.
            words_per_cue = 3 if is_shorts else 5
            groups = []
            for i in range(0, len(matches), words_per_cue):
                chunk = matches[i:i + words_per_cue]
                groups.append((
                    to_sec(chunk[0][1]),
                    to_sec(chunk[-1][2]),
                    " ".join(c[3].replace('\n', ' ').strip() for c in chunk),
                ))

            dialogues = []
            for st_sec, et_sec, raw_text in groups:
                text = raw_text.upper()
                dur_sec = max(0.2, et_sec - st_sec)

                start_ass = _ass_timestamp(st_sec)
                end_ass = _ass_timestamp(et_sec)

                words = text.split()
                if words:
                    w_cs = max(6, int((dur_sec * 100) / len(words)))
                    k_words = [f"{{\\k{w_cs}}}{w}" for w in words]
                    styled_text = " ".join(k_words)
                else:
                    styled_text = f"{{\\c&H0000FFFF&}}{text}{{\\r}}"

                line = f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{styled_text}"
                dialogues.append(line)

            with open(ass_output_path, "w", encoding="utf-8") as f:
                f.write(ass_header + "\n".join(dialogues))

            logger.info(f"Hormozi animated ASS subtitles created: {ass_output_path}")
            return ass_output_path
        except Exception as e:
            logger.error(f"Error converting SRT to ASS: {e}")
            return ""

if __name__ == "__main__":
    sg = SubtitleGenerator()
    sg.srt_to_ass("temp/test_sub.srt", "temp/test_sub.ass", is_shorts=True)
