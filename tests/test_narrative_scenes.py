import tests
import copy
import json
import unittest
from unittest.mock import patch

from narrative_scenes import validate_scene_plan, align_scenes, figures
from script_generator import ScriptGenerator, ScriptGenerationError


def example():
    scenes = [
        dict(kind='event', narration='Example Widget reported higher quarterly revenue.', emphasis='higher quarterly revenue'),
        dict(kind='comparison', narration='Revenue was $12 million versus $10 million a year earlier.', emphasis='$12 million'),
        dict(kind='explanation', narration='Management said higher unit sales contributed to growth.', emphasis='higher unit sales'),
        dict(kind='caveat', narration="But we don't have profit figures. More sales might still come with higher costs.", emphasis="we don't have profit figures"),
        dict(kind='takeaway', narration="Sales grew. Whether the business earned more is still unknown.", emphasis='still unknown'),
    ]
    return dict(title='Example Widget revenue', full_script=' '.join(s['narration'] for s in scenes), scenes=scenes)


def measured(script):
    # Deliberately non-uniform real-looking timings with a pause at every scene.
    words, time = [], .2
    for scene in script['scenes']:
        for word in scene['narration'].split():
            duration = .09 + len(word) * .012
            words.append(dict(text=word, start=time, end=time + duration))
            time += duration + .03
        time += .65
    return words, time


class NarrativeSceneTests(unittest.TestCase):
    def test_displayed_figures_preserve_signs_repeated_values_and_exclude_sentence_punctuation(self):
        self.assertEqual(figures('A loss of -$0.32 versus -$0.20.'), ['-$0.32', '-$0.20'])
        self.assertEqual(figures('It stayed at $12 million versus $12 million.'), ['$12 million', '$12 million'])
        self.assertEqual(figures('Down -23 percent versus +2.5 percent.'), ['-23 percent', '+2.5 percent'])

    def test_boundaries_use_spoken_words_including_pauses_and_cover_final_tail(self):
        script = example()
        words, duration = measured(script)
        timeline = align_scenes(validate_scene_plan(script), words, duration)
        self.assertEqual(timeline[0]['start'], 0)
        boundary = len(script['scenes'][0]['narration'].split())
        self.assertEqual(timeline[1]['start'], words[boundary]['start'])
        self.assertEqual(timeline[0]['end'], timeline[1]['start'])
        self.assertEqual(timeline[-1]['end'], duration)
        self.assertEqual(timeline[1]['figures'], ['$12 million', '$10 million'])
        focus = next(w for w in words[boundary:] if w['text'] == '$12')
        self.assertEqual(timeline[1]['emphasisStart'], focus['start'])

    def test_changed_words_numbers_omitted_scene_or_invented_screen_claim_rejected(self):
        for mutation in (
            lambda s: s['scenes'][1].update(narration='Revenue was $20 million versus $10 million a year earlier.'),
            lambda s: s['scenes'].pop(2),
            lambda s: s['scenes'][2].update(emphasis='profits surged'),
            lambda s: s['scenes'][0].update(headline='guaranteed gains'),
            lambda s: s['scenes'][3].update(kind='explanation'),
            lambda s: s['scenes'][2].update(kind='comparison'),
            lambda s: s['scenes'][2].update(emphasis='contribut'),
        ):
            script = example(); mutation(script)
            with self.assertRaises(ValueError): validate_scene_plan(script)

    def test_tts_mismatch_and_out_of_bounds_end_cannot_get_guessed_timestamps(self):
        script = example(); words, duration = measured(script)
        altered = copy.deepcopy(words); altered[0]['text'] = 'Different'
        with self.assertRaisesRegex(ValueError, 'does not match'):
            align_scenes(script['scenes'], altered, duration)
        with self.assertRaisesRegex(ValueError, 'exceed'):
            align_scenes(script['scenes'], words, words[-1]['end'] - .3)

    def test_repeated_phrase_is_aligned_in_its_own_scene(self):
        script = example()
        script['scenes'][-1]['narration'] = 'Sales grew. Higher quarterly revenue does not establish better profitability.'
        script['scenes'][-1]['emphasis'] = 'Higher quarterly revenue'
        script['full_script'] = ' '.join(s['narration'] for s in script['scenes'])
        words, duration = measured(script)
        timeline = align_scenes(validate_scene_plan(script), words, duration)
        self.assertGreater(timeline[-1]['emphasisStart'], timeline[-1]['start'])

    def test_sentence_subtitles_cannot_supply_an_invented_word_boundary(self):
        script = example(); words, duration = measured(script)
        count = len(script['scenes'][0]['narration'].split()) + 1
        combined = dict(text=' '.join(w['text'] for w in words[:count]),
                        start=words[0]['start'], end=words[count-1]['end'])
        with self.assertRaisesRegex(ValueError, 'cannot split'):
            align_scenes(script['scenes'], [combined, *words[count:]], duration)

    def test_invalid_plan_gets_bounded_correction_and_never_returns_static_fallback(self):
        good = example(); bad = copy.deepcopy(good)
        bad['scenes'][1]['emphasis'] = '$99 million'
        writer = ScriptGenerator()
        with patch.object(writer, '_chat', side_effect=[json.dumps(bad), json.dumps(good)]) as chat:
            result = writer._call_llm('Source facts', 'title', 40, 100, scene_bounds=(4, 7))
            self.assertEqual(result, good)
            self.assertIn('SCENE CORRECTION', chat.call_args.args[-1])
        with patch.object(writer, '_chat', return_value=json.dumps(bad)) as chat:
            with self.assertRaises(ScriptGenerationError):
                writer._call_llm('Source facts', 'title', 40, 100, scene_bounds=(4, 7))
            self.assertEqual(chat.call_count, 3)


if __name__ == '__main__': unittest.main()
