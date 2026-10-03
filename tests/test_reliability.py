import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import requests

from content_checks import validate_hero_number
from data_fetcher import FMPDataError, FMPDataFetcher
from analytics_reporter import compute_franchise_weights
from script_generator import ScriptGenerator, ScriptGenerationError


class FigureTests(unittest.TestCase):
    def test_generated_text_is_not_evidence(self):
        self.assertEqual(validate_hero_number('$99B', {
            'facts': {'price': 10}, 'headline': '$99B'}, '$99B', '+1'), '')

    def test_full_value_scale_and_direction(self):
        story = {'facts': {'value_usd': 28171450, 'changesPercentage': -23.45}}
        for hero, expected in [('$28.2M', '$28.2M'), ('$28.2B', ''),
                               ('+23.5%', ''), ('-23.5%', '-23.5%'), ('28171450%', '')]:
            with self.subTest(hero=hero):
                self.assertEqual(validate_hero_number(hero, story, '', '+1'), expected)

    def test_unrelated_units_and_nonfinite_values(self):
        self.assertEqual(validate_hero_number('$99M', {'facts': {'shares': 99000000}}, '', '1'), '')
        self.assertEqual(validate_hero_number('99%', {'facts': {'price': 99}}, '', 'NaN'), '')


class DataTests(unittest.TestCase):
    def test_request_exception_does_not_expose_key(self):
        fetcher = FMPDataFetcher('private-test-key')
        with patch('data_fetcher.requests.get', side_effect=requests.ConnectionError(
                'https://example.org?apikey=private-test-key')), patch('data_fetcher.time.sleep'):
            with self.assertRaises(FMPDataError) as error:
                fetcher.get_index_quotes()
        self.assertNotIn('private-test-key', str(error.exception))

    def test_chart_rejects_missing_or_invalid_prices(self):
        fetcher = FMPDataFetcher('test')
        for data in [[{}], [{'date': '2026-09-10 09:30:00', 'open': 0, 'close': 10},
                            {'date': '2026-09-10 09:35:00', 'open': 10, 'close': 11}]]:
            with self.subTest(data=data), patch.object(fetcher, '_get', return_value=data):
                with self.assertRaises(FMPDataError):
                    fetcher.get_intraday_chart('TEST')


class LearningTests(unittest.TestCase):
    def test_refreshing_weights_does_not_revive_stale_patterns(self):
        from learning_engine import load_learnings
        with TemporaryDirectory() as directory:
            file = Path(directory) / 'learnings.json'
            file.write_text(json.dumps({
                'updated_at': datetime.now().isoformat(),
                'franchise_weights': {'a': 1.1},
                'own_patterns': {'winning_patterns': ['stale']},
                'section_updated_at': {'own_patterns': (datetime.now() - timedelta(days=20)).isoformat()},
            }))
            with patch('learning_engine.LEARNINGS_FILE', file):
                learned = load_learnings()
            self.assertEqual(learned['franchise_weights'], {'a': 1.1})
            self.assertNotIn('own_patterns', learned)

    def test_long_and_tiny_replay_samples_cannot_bias_shorts_weights(self):
        def row(fr, engaged=30, apv=70, is_long=False):
            return dict(franchise=fr, engaged_views=engaged, views=100,
                        avg_view_pct=apv, is_long=is_long)
        baseline = [row('a'), row('a'), row('b'), row('b')]
        noisy = baseline + [row('a', 5, 6118.8), row('b', 9999, 95, True)]
        self.assertEqual(compute_franchise_weights(stats=baseline),
                         compute_franchise_weights(stats=noisy))

    def test_replay_credit_is_capped(self):
        rows = [dict(franchise=f, engaged_views=50, avg_view_pct=pct, is_long=False)
                for f, pct in [('a', 100), ('a', 100), ('b', 6000), ('b', 6000)]]
        self.assertEqual(compute_franchise_weights(stats=rows), {'a': 1.0, 'b': 1.0})

    def test_trend_interest_never_becomes_source_facts(self):
        from story_selector import StorySelector
        facts = {'name': 'Bloom Energy', 'value_usd': 1000000}
        candidate = dict(ticker='BE', score=70, facts=facts.copy(), reasons=[])
        weak = dict(ticker='BE', score=40, facts=facts.copy(), reasons=[])
        unrelated = dict(ticker='TEST', score=70, facts={'name': 'Example'}, reasons=[])
        StorySelector._apply_market_trends([candidate, weak, unrelated], [
            {'title': 'Bloom Energy stock: unsupported claim', 'url': 'https://youtube.com/watch?v=test'}])
        self.assertEqual(candidate['score'], 75)
        self.assertEqual(candidate['facts'], facts)
        self.assertEqual(weak['score'], 40)
        self.assertEqual(unrelated['score'], 70)


class ScriptTests(unittest.TestCase):
    def test_invalid_publication_schema_fails_before_render(self):
        sg = ScriptGenerator(openrouter_key='', gemini_key='', groq_key='')
        for payload in [dict(title=None, full_script='one two'),
                        dict(title='Title', full_script=['one', 'two']),
                        dict(title='Title', full_script='one two', tags='stocks')]:
            with self.subTest(payload=payload), patch.object(sg, '_providers', return_value=[('test', 'model')]), \
                    patch.object(sg, '_chat', return_value=json.dumps(payload)):
                with self.assertRaises(ScriptGenerationError):
                    sg._call_llm('prompt', 'fallback', min_words=2, max_words=3)


class PipelineTests(unittest.TestCase):
    def run_mock_pipeline(self, uploaded, prepare_presenter=False, rejected_drafts=0):
        import main_scheduler as main
        events = []
        story = dict(ticker='TEST', headline='Test', score=80, facts={'value_usd': 1000000},
                     franchise='insider_watch', franchise_name='Insider Watch',
                     franchise_style='', why_it_matters='', angle='')
        pool = {'movers': {'gainers': [{'symbol': 'TEST'}]}}
        with TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(patch.object(main, "OUTPUT_DIR", Path(directory)))
            mocked = {name: stack.enter_context(patch.object(main, name)) for name in [
                'FMPDataFetcher', 'StoryPoolCollector', 'StorySelector', 'ScriptGenerator',
                'VoiceGenerator', 'SubtitleGenerator', 'VideoEngine', 'TelegramApprovalBot',
                'YouTubePublisher', 'summarize_pool', 'cleanup_temp', 'get_audio_duration']}
            mocked['summarize_pool'].return_value = ''
            mocked['StoryPoolCollector'].return_value.collect.return_value = pool
            mocked['StorySelector'].return_value.select.return_value = story
            mocked['ScriptGenerator'].return_value.generate_shorts_script.return_value = {
                'title': 'Test', 'full_script': 'Test script', 'hero_number': '$1M'}
            if rejected_drafts:
                valid = {'title': 'Test', 'full_script': 'Test script', 'hero_number': '$1M'}
                invalid = {'title': 'Test vs Nasdaq', 'full_script': 'Test script', 'hero_number': '$1M'}
                mocked['ScriptGenerator'].return_value.generate_shorts_script.side_effect = [invalid] * rejected_drafts + [valid]
            mocked['FMPDataFetcher'].return_value.get_intraday_chart.return_value = [
                {'open': 10, 'close': 10}, {'open': 10, 'close': 11}]
            mocked['VoiceGenerator'].return_value.generate_audio.return_value = ('a.mp3', 's.srt')
            mocked['SubtitleGenerator'].srt_to_ass.return_value = 's.ass'
            mocked['get_audio_duration'].return_value = 35
            mocked['VideoEngine'].return_value.render_video.return_value = 'video.mp4'
            def upload(**kwargs):
                events.append('upload')
                return 'id' if uploaded else ''
            mocked['YouTubePublisher'].return_value.upload_video.side_effect = upload
            mocked['TelegramApprovalBot'].return_value.send_video_notification.side_effect = lambda **kw: events.append('preview')
            if prepare_presenter:
                with patch('presenter_workflow.prepare_package', return_value='package') as prepare:
                    self.assertEqual(main.run_pipeline(prepare_presenter=True), 'package')
                    prepare.assert_called_once()
                mocked['YouTubePublisher'].assert_not_called()
                mocked['TelegramApprovalBot'].assert_not_called()
                self.assertFalse(mocked['VoiceGenerator'].return_value.generate_audio.call_args.kwargs['allow_fallback'])
            elif rejected_drafts == 2:
                with self.assertRaises(SystemExit):
                    main.run_pipeline()
                mocked['VoiceGenerator'].assert_not_called()
                mocked['YouTubePublisher'].assert_not_called()
            elif uploaded:
                main.run_pipeline()
            else:
                with self.assertRaises(SystemExit) as error:
                    main.run_pipeline()
                self.assertEqual(error.exception.code, 1)
        return events

    def test_editorial_correction_can_recover_before_publication(self):
        self.assertEqual(self.run_mock_pipeline(True, rejected_drafts=1), ['upload', 'preview'])

    def test_repeated_editorial_rejection_stops_before_voice_or_upload(self):
        self.assertEqual(self.run_mock_pipeline(False, rejected_drafts=2), [])

    def test_upload_failure_is_a_failed_process(self):
        self.assertEqual(self.run_mock_pipeline(False), ['upload'])

    def test_preview_happens_after_publication(self):
        self.assertEqual(self.run_mock_pipeline(True), ['upload', 'preview'])

    def test_presenter_preparation_stops_before_publication(self):
        self.assertEqual(self.run_mock_pipeline(False, prepare_presenter=True), [])


if __name__ == '__main__':
    unittest.main()
