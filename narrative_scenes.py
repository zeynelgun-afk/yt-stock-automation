"""Source-preserving scene plans and measured speech alignment."""
import re

KINDS = {'event', 'comparison', 'explanation', 'caveat', 'takeaway'}
TOKEN = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?", re.I)
FIGURE = re.compile(
    r"[+\-−]?[$€£]\s?[+\-−]?\d[\d,]*(?:\.\d+)?(?:\s+(?:million|billion|trillion|thousand))?"
    r"|[+\-−]?\b\d[\d,]*(?:\.\d+)?\s*(?:percent|%|million|billion|trillion|days?|cents?)", re.I)


def tokens(text):
    return [m.group().lower().replace('’', "'") for m in TOKEN.finditer(text)]


def figures(text):
    return [m.group().strip() for m in FIGURE.finditer(text)]


def validate_scene_plan(script, bounds=(4, 32), max_words=28):
    """Every displayed phrase must be an exact excerpt of the spoken script."""
    scenes = script.get('scenes')
    if not isinstance(script.get('full_script'), str) or not script['full_script'].strip():
        raise ValueError('Scene plan requires a complete spoken script')
    if not isinstance(scenes, list) or not bounds[0] <= len(scenes) <= bounds[1]:
        raise ValueError(f'Scene plan requires {bounds[0]}–{bounds[1]} scenes')
    for index, scene in enumerate(scenes):
        if (not isinstance(scene, dict) or set(scene) - {'kind', 'narration', 'emphasis'}
                or scene.get('kind') not in KINDS
                or not isinstance(scene.get('narration'), str)
                or not 4 <= len(scene['narration'].split()) <= max_words
                or not tokens(scene['narration'])
                or not isinstance(scene.get('emphasis', ''), str)):
            raise ValueError(f'Scene {index + 1} requires a valid kind, exact narration and 4–{max_words} words')
        if bounds[1] == 7 and index == 0 and len(scene['narration'].split()) > 14:
            raise ValueError('Shorts opening scene must contain at most 14 spoken words')
        emphasis = scene.get('emphasis', '')
        if len(emphasis) > 65 or len(emphasis.split()) > 7 or (emphasis and emphasis not in scene['narration']):
            raise ValueError('Scene emphasis must be an exact short narration excerpt')
        if emphasis:
            phrase, spoken = tokens(emphasis), tokens(scene['narration'])
            if not phrase or not any(spoken[i:i+len(phrase)] == phrase
                                     for i in range(len(spoken) - len(phrase) + 1)):
                raise ValueError('Scene emphasis must contain complete spoken words')
        if scene['kind'] == 'comparison' and len(figures(scene['narration'])) < 2:
            raise ValueError('Comparison requires two narrated quantities')
    if ' '.join(' '.join(s['narration'].split()) for s in scenes) != ' '.join(script['full_script'].split()):
        raise ValueError('Scenes must partition the complete script without changing words')
    kinds = [s['kind'] for s in scenes]
    if kinds[0] != 'event' or kinds[-1] != 'takeaway' or 'caveat' not in kinds:
        raise ValueError('Scene plan requires opening event, limitation and final takeaway')
    return scenes


def align_scenes(scenes, words, audio_duration):
    """Match actual TTS tokens; never guess timestamps for a mismatched script."""
    measured = [(token, word) for word in words for token in tokens(word['text'])]
    expected = [token for scene in scenes for token in tokens(scene['narration'])]
    if expected != [token for token, _ in measured]:
        raise ValueError('Scene narration does not match measured subtitle words')
    if not measured or measured[-1][1]['end'] > audio_duration + .1:
        raise ValueError('Subtitle words exceed the voiceover duration')
    timeline, cursor = [], 0
    for index, scene in enumerate(scenes):
        count = len(tokens(scene['narration']))
        chunk = measured[cursor:cursor + count]
        if cursor + count < len(measured) and measured[cursor + count][1] is chunk[-1][1]:
            raise ValueError('Scene boundaries cannot split a subtitle cue')
        start = 0.0 if index == 0 else chunk[0][1]['start']
        end = measured[cursor + count][1]['start'] if cursor + count < len(measured) else audio_duration
        if end <= start:
            raise ValueError('Scene boundaries cannot share a subtitle cue')
        timed = dict(scene, start=start, end=end)
        focus = scene.get('emphasis', '')
        if focus:
            phrase = tokens(focus)
            if not phrase:
                raise ValueError('Scene emphasis must contain spoken words')
            offset = next((i for i in range(count - len(phrase) + 1)
                           if expected[cursor+i:cursor+i+len(phrase)] == phrase), None)
            if offset is None:
                raise ValueError('Scene emphasis could not be aligned')
            timed['emphasisStart'] = chunk[offset][1]['start']
            timed['emphasisEnd'] = chunk[offset + len(phrase) - 1][1]['end']
        timed['figures'] = figures(scene['narration'])[:2]
        timeline.append(timed)
        cursor += count
    return timeline


def scene_prompt(shorts):
    count, size = ('4–7', '28') if shorts else ('8–32', '28')
    opening = 'The Shorts opening event scene contains at most 14 words.' if shorts else ''
    return f"""SPEECH-ALIGNED SCENES:
Return a scenes array with {count} entries, each 4–{size} spoken words.
Each entry has ONLY kind, narration, emphasis. Allowed kinds: event, comparison,
explanation, caveat, takeaway. First is event; last is takeaway; include a caveat.
narration is an EXACT consecutive excerpt of full_script. Joining every scene's
narration with spaces MUST reproduce full_script word for word, with punctuation.
Split at natural thought boundaries, usually one or two short sentences. Long
explanations need several scenes. Do not add padding to reach the scene count.
{opening}
emphasis is an exact substring of that scene's narration (max 7 words and 65 characters),
or an empty string. It will be displayed prominently; preserve qualifiers.
Use comparison only when that scene actually compares at least two dollar,
percent, million/billion, day or cent quantities stated in the supplied facts.
When a before/after numeric comparison is central to the supplied event, put
both quantities together in a comparison scene after the opening event.
Scene labels and figures are derived locally; do not add separate screen claims.
If you rewrite full_script, regenerate scenes to match the new wording exactly.
"""
