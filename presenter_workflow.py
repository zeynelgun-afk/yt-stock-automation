"""Prepare exact speech excerpts for Creator UI; assemble downloaded avatar clips.

No provider calls, browser credentials, or publication. All package paths are
relative, so the package survives temp cleanup and can move between machines.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

from config import ASSETS_DIR
from subtitle_generator import SubtitleGenerator


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, timeout=kwargs.pop('timeout', 600), **kwargs)
    if result.returncode:
        raise ValueError(f"{args[0]} failed: {result.stderr.decode(errors='replace')[-1000:]}")
    return result.stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', str(path)], timeout=30))


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def words_from_srt(path):
    def seconds(t):
        h, m, s = t.replace(',', '.').split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    words = []
    for block in re.split(r'\n\s*\n', Path(path).read_text().strip()):
        lines = block.splitlines()
        if len(lines) < 3 or ' --> ' not in lines[1]:
            raise ValueError('Expected measured word-level SRT')
        a, b = map(seconds, lines[1].split(' --> '))
        if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b):
            raise ValueError('Invalid subtitle timing')
        if words and a < words[-1]['end'] - 0.002:
            raise ValueError('Overlapping/out-of-order subtitles')
        words.append(dict(start=a, end=b, text=' '.join(lines[2:])))
    if not words:
        raise ValueError('Empty subtitles')
    return words


def plan_segments(words, duration, is_shorts):
    """Keep a strict cost ceiling, favoring sentence boundaries within it."""
    if not math.isfinite(duration) or duration <= 0 or words[-1]['end'] > duration + 0.1:
        raise ValueError('Subtitles extend beyond narration')

    def segment(name, index, limit, start=None):
        start = words[index]['start'] if start is None else start
        candidates = [w for w in words[index:] if w['end'] <= min(start + limit, duration)]
        if not candidates:
            return None
        sentences = [w for w in candidates if re.search(r'[.!?]["\u201d\u2019]*$', w['text'])]
        end = (sentences[-1] if sentences else candidates[-1])['end']
        text = ' '.join(w['text'] for w in candidates if w['end'] <= end)
        return dict(name=name, start=start, end=end, text=text,
                    audio=f'{name}.wav', clip=f'{name}.mp4')

    result = []
    intro = segment('intro', 0, 6 if is_shorts else 8, start=0.0)
    if intro:
        result.append(intro)
    if not is_shorts and duration >= 45:
        # Transition begins on a sentence boundary after the midpoint.
        for i in range(1, len(words)):
            if (duration * .5 <= words[i]['start'] <= duration * .75
                    and re.search(r'[.!?]["\u201d\u2019]*$', words[i-1]['text'])):
                transition = segment('transition', i, 5)
                if transition:
                    result.append(transition)
                break
    return result


def prepare_package(base_video, audio, srt, package, *, is_shorts=True,
                    metadata=None):
    base, audio, srt, package = map(Path, (base_video, audio, srt, package))
    info = probe(audio)
    duration = float(info['format']['duration'])
    base_info = probe(base)
    if (not any(s['codec_type'] == 'video' for s in base_info['streams'])
            or not any(s['codec_type'] == 'audio' for s in base_info['streams'])
            or abs(float(base_info['format']['duration']) - duration) > .6):
        raise ValueError('Base video must contain the complete narration timeline')
    segments = plan_segments(words_from_srt(srt), duration, is_shorts)
    if not segments:
        raise ValueError('No speech fits the short presenter budget')
    package.mkdir(parents=True, exist_ok=False)
    for source, dest in ((base, 'base.mp4'), (audio, 'narration' + audio.suffix),
                         (srt, 'narration.srt')):
        shutil.copy2(source, package / dest)
    reference = ASSETS_DIR / 'characters/deniz/deniz-reference-v1.png'
    if reference.exists():
        shutil.copy2(reference, package / 'deniz-reference.png')
    narration = 'narration' + audio.suffix
    for item in segments:
        run(['ffmpeg', '-v', 'error', '-y', '-i', str(audio), '-ss', str(item['start']),
             '-t', str(item['end'] - item['start']), '-vn', '-c:a', 'pcm_s16le',
             str(package / item['audio'])])
        item['audio_sha256'] = sha(package / item['audio'])
    manifest = dict(version=1, is_shorts=is_shorts, duration=duration,
                    narration=narration, narration_sha256=sha(audio),
                    base_sha256=sha(base), srt_sha256=sha(srt), segments=segments,
                    metadata=metadata or {})
    (package / 'presenter.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    (package / 'README.txt').write_text(
        'Creator: ElevenLabs Image & Video > Lip sync. Deniz referansını ve her\n'
        'bölümün WAV dosyasını kullan. Yeni ses üretme, hızını değiştirme.\n'
        f'Kadraj: {"9:16" if is_shorts else "16:9"}; tek üretim, 720p.\n'
        'İndirilen klipleri intro.mp4 / varsa transition.mp4 olarak buraya koy.\n'
        'Eksik klip yerine grafik kalır; yanlış sesli klip birleştirilmez.\n'
        'Proje kökünden: python presenter_workflow.py finish PAKET_KLASORU\n'
        'final.mp4 ve publication.json oluşur; otomatik yayın yapılmaz.\n')
    return package


def pcm(path, duration):
    return np.frombuffer(run(['ffmpeg', '-v', 'error', '-i', str(path), '-t', str(duration),
                              '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-']), dtype=np.float32)


def validate_clip(clip, expected, duration):
    info = probe(clip)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if video is None or not any(s['codec_type'] == 'audio' for s in info['streams']):
        raise ValueError(f'{clip.name}: video and original speech audio required')
    clip_duration = float(video.get('duration') or info['format']['duration'])
    if not duration - .08 <= clip_duration <= duration + .5:
        raise ValueError(f'{clip.name}: duration differs from exported speech')
    a, b = pcm(expected, duration), pcm(clip, duration)
    n = min(len(a), len(b))
    if n < 1000 or abs(len(a) - len(b)) > 1280:
        raise ValueError(f'{clip.name}: incomplete speech audio')
    # Exact WAV -> avatar audio is re-encoded, but should retain the waveform.
    # A strict check is deliberate: never silently pair unrelated lip motion.
    correlation = float(np.corrcoef(a[:n], b[:n])[0, 1])
    if not math.isfinite(correlation) or correlation < .9:
        raise ValueError(f'{clip.name}: speech mismatch or timing shift ({correlation:.3f})')
    return correlation


def finish_package(package):
    package = Path(package).resolve()
    manifest = json.loads((package / 'presenter.json').read_text())
    if manifest.get('version') != 1:
        raise ValueError('Unsupported package version')
    # Only contained regular files may be named by this local manifest.
    def file(name):
        p = (package / name).resolve()
        if p.parent != package:
            raise ValueError('Package file must stay inside package directory')
        return p
    for name, expected in [('base.mp4', manifest['base_sha256']),
                           (manifest['narration'], manifest['narration_sha256']),
                           ('narration.srt', manifest['srt_sha256'])]:
        if sha(file(name)) != expected:
            raise ValueError(f'{name}: changed since preparation; prepare a new package')
    expected_plan = plan_segments(words_from_srt(file('narration.srt')),
                                  manifest['duration'], manifest['is_shorts'])
    if not expected_plan:
        raise ValueError('No valid presenter scenes')
    actual_plan = [{k: s[k] for k in expected_plan[0]} for s in manifest['segments']]
    if actual_plan != expected_plan:
        raise ValueError('Scene timings differ from the prepared speech plan')
    selected = []
    for item in manifest['segments']:
        if sha(file(item['audio'])) != item['audio_sha256']:
            raise ValueError('Exported speech changed; prepare a new package')
        clip = file(item['clip'])
        if clip.exists():
            correlation = validate_clip(clip, file(item['audio']), item['end']-item['start'])
            selected.append((item, correlation))
    base, final = file('base.mp4'), file('final.mp4')
    if not selected:
        shutil.copy2(base, final)
    else:
        info = probe(base)
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        width, height = video['width'], video['height']
        if not SubtitleGenerator.srt_to_ass(
                str(file('narration.srt')), str(file('captions.ass')),
                is_shorts=manifest['is_shorts']):
            raise ValueError('Could not generate presenter captions')
        inputs, filters, prev = ['-i', 'base.mp4'], [], '[0:v]'
        for i, (item, _) in enumerate(selected, 1):
            inputs += ['-i', item['clip']]
            start, end = item['start'], item['end']
            filters.append(
                f'[{i}:v]trim=duration={end-start},setpts=PTS-STARTPTS,'
                f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
                f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x0f172a,setsar=1,'
                f'setpts=PTS+{start}/TB,ass=captions.ass[p{i}]')
            filters.append(f'{prev}[p{i}]overlay=eof_action=pass:repeatlast=0:'
                           f"enable='gte(t,{start})*lt(t,{end})'[v{i}]")
            prev = f'[v{i}]'
        run(['ffmpeg', '-v', 'error', '-y', '-filter_complex_threads', '1', *inputs,
             '-filter_complex', ';'.join(filters), '-map', prev, '-map', '0:a:0',
             '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
             '-c:a', 'copy', '-t', str(info['format']['duration']), 'final.pending.mp4'],
            cwd=package, timeout=max(600, manifest['duration'] * 8))
        file('final.pending.mp4').replace(final)
    publication = dict(manifest.get('metadata', {}))
    publication.update(video='final.mp4', published=False,
                       contains_synthetic_media=bool(selected) or bool(publication.get('contains_synthetic_media')),
                       presenter_segments=[dict(name=s['name'], start=s['start'], end=s['end'],
                                                audio_correlation=c) for s, c in selected])
    file('publication.json').write_text(json.dumps(publication, ensure_ascii=False, indent=2) + '\n')
    return final


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    finish = sub.add_parser('finish', help='Merge downloaded avatar clips; never publishes')
    finish.add_argument('package', type=Path)
    args = parser.parse_args()
    print(finish_package(args.package))
