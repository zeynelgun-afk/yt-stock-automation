"""Remotion renderer bridged to the existing Python publication pipeline."""

import json
import logging
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from config import OUTPUT_DIR, BASE_DIR
from video_engine import VideoEngine
from thumbnail_design import DENIZ_ART
from narrative_scenes import validate_scene_plan, align_scenes

logger = logging.getLogger(__name__)
REMOTION_DIR = BASE_DIR / 'remotion'
SRT_CUE = re.compile(
    r'\d+\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*'
    r'(\d{2}:\d{2}:\d{2},\d{3})\s*\n(.+?)(?=\n\s*\n|\Z)', re.DOTALL,
)


def _seconds(stamp):
    hours, minutes, seconds = stamp.replace(',', '.').split(':')
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def read_words(srt_path):
    """Measured word timings from the existing voice provider's SRT output."""
    cues = SRT_CUE.findall(Path(srt_path).read_text(encoding='utf-8'))
    words = []
    for start, end, content in cues:
        beginning, finish = _seconds(start), _seconds(end)
        value = ' '.join(content.split())
        if not value or finish <= beginning or (words and beginning < words[-1]['end'] - 0.02):
            raise ValueError('Invalid or overlapping subtitle timings')
        words.append({'start': beginning, 'end': finish, 'text': value})
    if not words:
        raise ValueError('No measured subtitle words in SRT')
    return words


class RemotionVideoEngine(VideoEngine):
    """Keep source-footage and thumbnail helpers; render the video in Remotion."""

    def render_video(self, audio_path, srt_path, output_filename, *, title, ticker,
                     change_pct, intraday, franchise='', franchise_name='',
                     hero_number='', hero_label='', is_shorts=True, bg_video_path=None,
                     scenes=None, full_script=''):
        audio_duration = self._probe_duration(audio_path)
        if not 0 < audio_duration <= 900:
            raise RuntimeError('Voiceover duration is missing or exceeds 900 seconds')
        if len(intraday) < 2:
            raise RuntimeError('At least two real intraday candles are required')
        try:
            closes = [float(candle['close']) for candle in intraday]
            session_open = float(intraday[0]['open'])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError('Invalid intraday chart values') from exc
        if not all(math.isfinite(value) and value > 0 for value in [session_open, *closes]):
            raise RuntimeError('Invalid intraday chart values')
        words = read_words(srt_path)
        checked_scenes = validate_scene_plan({'full_script': full_script, 'scenes': scenes},
                                            (4, 7) if is_shorts else (8, 32),
                                            max_words=28)
        timeline = align_scenes(checked_scenes, words, audio_duration)
        if not (REMOTION_DIR / 'node_modules' / '.bin' / 'remotion').exists():
            raise RuntimeError('Remotion dependencies missing; run npm ci --prefix remotion')

        raw = bg_video_path or []
        clips = [raw] if isinstance(raw, str) else list(raw)
        clips = [Path(clip) for clip in clips if clip and Path(clip).is_file()
                 and self._probe_duration(clip) > 0]
        if not is_shorts:
            clips = clips[:min(5, max(1, int((audio_duration + 1) // 25)))]
        else:
            clips = clips[:1]

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / output_filename
        with tempfile.TemporaryDirectory(prefix='yt-remotion-') as stage_name:
            stage = Path(stage_name)
            audio_name = 'voice' + Path(audio_path).suffix
            shutil.copy2(audio_path, stage / audio_name)
            backgrounds = []
            for index, clip in enumerate(clips):
                name = f'background-{index}{clip.suffix.lower()}'
                shutil.copy2(clip, stage / name)
                backgrounds.append(name)
            host = None
            if DENIZ_ART.is_file():
                host = 'deniz.png'
                shutil.copy2(DENIZ_ART, stage / host)
            music = BASE_DIR / 'assets/music/bg_music.wav'
            whoosh = BASE_DIR / 'assets/sfx/whoosh.wav'
            for name, source in [('music.wav', music), ('whoosh.wav', whoosh)]:
                if source.is_file():
                    shutil.copy2(source, stage / name)
            props = {
                'title': title, 'ticker': ticker, 'changePct': change_pct,
                'franchise': franchise, 'franchiseName': franchise_name,
                'heroNumber': hero_number, 'heroLabel': hero_label,
                'isShorts': is_shorts, 'closes': closes, 'sessionOpen': session_open,
                'sessionDate': str(intraday[-1].get('date', ''))[:10],
                'words': words, 'audio': audio_name, 'backgrounds': backgrounds,
                'scenes': timeline,
                'host': host, 'music': 'music.wav' if music.is_file() else None,
                'whoosh': 'whoosh.wav' if whoosh.is_file() else None,
            }
            props_path = stage / 'props.json'
            props_path.write_text(json.dumps(props, ensure_ascii=False), encoding='utf-8')
            cmd = [str(REMOTION_DIR / 'node_modules/.bin/remotion'), 'render',
                   str(REMOTION_DIR / 'src/index.jsx'), 'StockStory', str(out_path),
                   '--props', str(props_path), '--public-dir', str(stage),
                   '--duration', str(math.ceil((audio_duration + 0.3) * 30)),
                   '--width', '1080' if is_shorts else '1920',
                   '--height', '1920' if is_shorts else '1080',
                   '--fps', '30', '--concurrency', '2', '--codec', 'h264',
                   '--pixel-format', 'yuv420p', '--log', 'error']
            logger.info('Rendering %s with Remotion', out_path)
            try:
                result = subprocess.run(cmd, cwd=REMOTION_DIR, capture_output=True,
                                        text=True, timeout=max(600, audio_duration * 8))
            except (OSError, subprocess.TimeoutExpired) as exc:
                out_path.unlink(missing_ok=True)
                raise RuntimeError('Remotion render did not complete') from exc
            if result.returncode != 0 and backgrounds:
                logger.warning('Background media render failed; retrying Remotion with its gradient')
                out_path.unlink(missing_ok=True)
                props['backgrounds'] = []
                props_path.write_text(json.dumps(props, ensure_ascii=False), encoding='utf-8')
                try:
                    result = subprocess.run(cmd, cwd=REMOTION_DIR, capture_output=True,
                                            text=True, timeout=max(600, audio_duration * 8))
                except (OSError, subprocess.TimeoutExpired) as exc:
                    out_path.unlink(missing_ok=True)
                    raise RuntimeError('Remotion gradient render did not complete') from exc
            if result.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
                out_path.unlink(missing_ok=True)
                raise RuntimeError(f'Remotion render failed: {result.stderr[-1200:]}')
        (OUTPUT_DIR / 'editorial_scene_timeline.json').write_text(json.dumps({
            'video': out_path.name, 'audio_duration': audio_duration,
            'timing_source': 'measured_voice_srt', 'scenes': timeline,
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return str(out_path)
