import re
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        font_size = 56 if is_shorts else 36
        margin_v = 240 if is_shorts else 60
        
        ass_header = f"""[Script Info]
Title: US Stock Market Daily Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

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

            dialogues = []
            for m in matches:
                start_raw = m[1]
                end_raw = m[2]
                text = m[3].replace('\n', ' ').strip().upper()

                # Parse timestamps
                def to_sec(ts: str) -> float:
                    parts = ts.replace(',', '.').split(':')
                    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

                st_sec = to_sec(start_raw)
                et_sec = to_sec(end_raw)
                dur_sec = max(0.2, et_sec - st_sec)

                start_ass = f"{m[1].replace(',', '.')[:7]}.{m[1].replace(',', '.')[8:10]}"
                end_ass = f"{m[2].replace(',', '.')[:7]}.{m[2].replace(',', '.')[8:10]}"

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
