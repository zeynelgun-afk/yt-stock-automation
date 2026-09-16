import json
import unittest
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from editorial_policy import qualify, repeated_event, publication_tags, validate_editorial_script
from growth_experiment import measurement_window, summarize
from publication_history import fetch_upload_history, HistoryUnavailable
from script_generator import ScriptGenerator, ProviderAccountError, _PROVIDER_DEAD
from story_selector import StorySelector

TODAY = date(2026, 9, 16)


def analyst(**changes):
    facts = dict(symbol='LEU', analyst='Jane Smith', priceTarget=270,
                 priceWhenPosted=162.93, publishedDate='2026-09-16T10:00:00Z',
                 headline='Northland Cuts Centrus Energy Price Target to $270')
    facts.update(changes)
    return dict(ticker='LEU', franchise='analyst_shock', score=70,
                headline='LEU target $270', facts=facts, reasons=[])


class EligibilityTests(unittest.TestCase):
    def test_market_price_and_generated_title_do_not_change_event_identity(self):
        first, second = analyst(), analyst(priceWhenPosted=170)
        second['headline'] = 'Different generated packaging'
        self.assertEqual(qualify(first, today=TODAY), '')
        self.assertEqual(qualify(second, today=TODAY), '')
        self.assertEqual(first['event_ids'], second['event_ids'])
        self.assertTrue(repeated_event(second, {'event_ids': first['event_ids']}))
        third = analyst(publishedDate='2026-09-15', priceTarget=240)
        qualify(third, today=TODAY)
        self.assertNotEqual(first['event_ids'], third['event_ids'])

    def test_stale_future_undated_and_weak_events_rejected(self):
        for day in ('', 'invalid', '2026-09-01', '2026-09-17'):
            self.assertTrue(qualify(analyst(publishedDate=day), today=TODAY))
        weak = analyst(); weak['score'] = 54
        self.assertTrue(qualify(weak, today=TODAY))

    def test_discussion_and_generic_recap_are_not_stories(self):
        for kind, symbol in [('reddit_radar', 'SPY'), ('fear_gauge', '^VIX'), ('market_close', '^GSPC')]:
            self.assertTrue(qualify(dict(franchise=kind, ticker=symbol, facts={}, score=100), today=TODAY))

    def test_mover_needs_fresh_linked_news_and_event_survives_reordering(self):
        c = dict(franchise='market_close', ticker='TEST', score=80, facts={'news': []})
        self.assertTrue(qualify(c, today=TODAY))
        news = [dict(title='Earnings released', url='https://issuer.example/results', publishedDate='2026-09-16'),
                dict(title='Old', url='https://issuer.example/old', publishedDate='2026-08-01')]
        c['facts']['news'] = news
        self.assertEqual(qualify(c, today=TODAY), '')
        self.assertEqual(len(c['facts']['news']), 1)
        other = dict(franchise='market_close', ticker='TEST', score=80,
                     facts={'news': [news[0], dict(title='New coverage', url='https://source.example/story', publishedDate='2026-09-16')]})
        qualify(other, today=TODAY)
        self.assertTrue(repeated_event(other, {'event_ids': c['event_ids']}))

    def test_disclosure_lag_cannot_be_negative(self):
        c = dict(franchise='congress_trade', ticker='TEST', score=80,
                 facts=dict(politician='Person', type='Purchase', disclosureDate='2026-09-15', transactionDate='2026-09-16'))
        self.assertTrue(qualify(c, today=TODAY))

    def test_no_repeat_fallback_when_every_candidate_is_covered(self):
        c = analyst(); c['facts']['name'] = 'Centrus Energy'
        self.assertEqual(StorySelector._drop_recently_covered([c], ['Centrus Energy target cut']), [])

    def test_legacy_company_name_missing_in_candidate_still_matches_source(self):
        self.assertTrue(StorySelector._legacy_headline_match(analyst(), ["Centrus Energy's Lowered Target Is Still $107 Away"]))
        self.assertFalse(StorySelector._legacy_headline_match(analyst(), ['Northland Cuts Micron Price Target']))

    def test_empty_candidates_skip_without_llm_trends_or_learning(self):
        selector = StorySelector(Mock())
        with patch.object(selector, 'eligible_candidates', return_value=[]), \
                patch.object(selector, '_llm_pick') as llm, patch('outlier_scanner.recent_market_trends') as trends:
            self.assertIsNone(selector.select({}))
        llm.assert_not_called(); trends.assert_not_called()

    def test_history_outage_prevents_selection(self):
        selector = StorySelector(Mock())
        with patch('story_selector.fetch_upload_history', side_effect=HistoryUnavailable('outage')), \
                patch.object(selector, 'build_candidates') as build:
            with self.assertRaises(HistoryUnavailable):
                selector.eligible_candidates({})
        build.assert_not_called()

    def test_company_cooldown_applies_across_formats_even_for_distinct_events(self):
        selector = StorySelector(Mock())
        selector.recent_uploads = [dict(title='Other company event', event_ids=['different'],
                                       published_at=datetime.now(timezone.utc).isoformat(), machine={'sym': 'LEU', 'fmt': 'long'})]
        with patch.object(selector, '_recent_upload_titles', return_value=[]), \
                patch.object(selector, 'build_candidates', return_value=[analyst()]), \
                patch('data_fetcher.ny_now', return_value=datetime(2026, 9, 16)):
            self.assertEqual(selector.eligible_candidates({}), [])
        self.assertIn('48 hours', selector.decision_log[0]['reason'])

    def test_script_rejects_known_unrelated_market_pattern(self):
        self.assertTrue(validate_editorial_script(dict(title='LEU target changed as VIX rose', full_script='Text'), analyst()))
        self.assertEqual(validate_editorial_script(dict(title='Centrus target changed', full_script='An analyst target is an opinion.'), analyst()), [])


class HistoryTests(unittest.TestCase):
    def client(self):
        client = MagicMock()
        client.channels().list().execute.return_value = {'items': [{'contentDetails': {'relatedPlaylists': {'uploads': 'uploads'}}}]}
        return client

    def test_all_pages_and_multiple_event_tags_read(self):
        client = self.client()
        client.playlistItems().list().execute.side_effect = [
            {'items': [{'contentDetails': {'videoId': 'a'}}], 'nextPageToken': 'second'},
            {'items': [{'contentDetails': {'videoId': 'b'}}]}]
        client.videos().list().execute.return_value = {'items': [
            dict(id=vid, snippet=dict(title=vid, publishedAt='2026-09-16T10:00:00Z', tags=['ev:first', 'ev:second', 'sym:TEST']),
                 status={'privacyStatus': 'public'}, contentDetails={'duration': 'PT35S'}) for vid in ('a', 'b')]}
        result = fetch_upload_history(client=client, now=datetime(2026, 9, 16, tzinfo=timezone.utc))
        self.assertEqual({r['video_id'] for r in result}, {'a', 'b'})
        self.assertEqual(result[0]['event_ids'], ['first', 'second'])
        self.assertTrue(any(c.kwargs.get('pageToken') == 'second' for c in client.playlistItems().list.call_args_list))

    def test_partial_metadata_is_failure_not_empty_history(self):
        client = self.client()
        client.playlistItems().list().execute.return_value = {'items': [{'contentDetails': {'videoId': 'missing'}}]}
        client.videos().list().execute.return_value = {'items': []}
        with self.assertRaises(HistoryUnavailable):
            fetch_upload_history(client=client)

    def test_history_exception_does_not_expose_response_body(self):
        client = self.client()
        client.playlistItems().list().execute.side_effect = RuntimeError('secret-key-in-response')
        with self.assertRaises(HistoryUnavailable) as error:
            fetch_upload_history(client=client)
        self.assertNotIn('secret-key', str(error.exception))


class AccountTests(unittest.TestCase):
    def test_account_limit_stops_before_other_provider_or_second_generation(self):
        sg = ScriptGenerator(openrouter_key='test', gemini_key='other', groq_key='')
        sg.last_error = 'openrouter: HTTP 403 account rejected'
        with patch.object(sg, '_chat', return_value=_PROVIDER_DEAD) as chat:
            for _ in range(2):
                with self.assertRaises(ProviderAccountError):
                    sg._call_llm('prompt', 'title')
        self.assertEqual(chat.call_count, 1)

    def test_http_error_body_is_not_logged(self):
        sg = ScriptGenerator(openrouter_key='test')
        with patch('script_generator.requests.post', return_value=Mock(status_code=403, text='private-account-reference')), \
                self.assertLogs('script_generator', level='WARNING') as logs:
            self.assertIs(sg._chat('openrouter', 'model', 'prompt'), _PROVIDER_DEAD)
        self.assertNotIn('private-account-reference', '\n'.join(logs.output))
        self.assertNotIn('private-account-reference', sg.last_error)


class WindowTests(unittest.TestCase):
    def test_pacific_date_not_utc_date_and_dst(self):
        self.assertEqual(measurement_window('2026-09-16T04:00:00Z'), (date(2026, 9, 16), date(2026, 9, 18)))
        self.assertEqual(measurement_window('2026-10-31T15:00:00Z'), (date(2026, 11, 1), date(2026, 11, 3)))

    def test_missing_metrics_not_zero_and_medians_not_lifetime_views(self):
        rows = [{'status': 'pending', 'metrics': None}, {'status': 'no_analytics_rows', 'metrics': None},
                {'status': 'available', 'metrics': dict(views=10, engagedViews=5, averageViewDuration=20, subscribersGained=1)}]
        result = summarize(rows)
        self.assertEqual(result['available'], 1)
        self.assertEqual(result['median_views'], 10)
        self.assertIsNone(summarize(rows[:2])['median_views'])


class PipelineSkipTests(unittest.TestCase):
    def test_empty_slate_never_generates_audio_or_publishes(self):
        import main_scheduler as main
        with TemporaryDirectory() as directory, ExitStack() as stack:
            mocks = {name: stack.enter_context(patch.object(main, name)) for name in (
                'FMPDataFetcher', 'StoryPoolCollector', 'StorySelector', 'ScriptGenerator',
                'VoiceGenerator', 'YouTubePublisher', 'summarize_pool')}
            stack.enter_context(patch.object(main, 'OUTPUT_DIR', Path(directory)))
            mocks['summarize_pool'].return_value = ''
            mocks['StorySelector'].return_value.select.return_value = None
            mocks['StorySelector'].return_value.decision_log = [{'eligible': False}]
            main.run_pipeline()
            mocks['ScriptGenerator'].return_value.generate_shorts_script.assert_not_called()
            mocks['VoiceGenerator'].assert_not_called(); mocks['YouTubePublisher'].assert_not_called()
            self.assertTrue((Path(directory) / 'editorial_decision.json').exists())

class ReportIntegrationTests(unittest.TestCase):
    def test_frozen_baseline_and_pending_experiment_do_not_get_replaced(self):
        from growth_experiment import build_report, STARTED_AT
        from editorial_policy import EXPERIMENT_ID
        api = MagicMock()
        api.reports().query().execute.side_effect = [
            {'rows': [['newbaseline', 10]]},
        ]
        history = [dict(video_id='newbaseline', title='Should not replace missing baseline',
                        privacy='public', machine={'fmt': 'shorts'}, published_at='2026-09-10T12:00:00Z'),
                   dict(video_id='experiment', title='Fresh experimental video', privacy='public',
                        machine={'fmt': 'shorts', 'exp': EXPERIMENT_ID}, published_at='2026-09-16T11:00:00Z')]
        previous = {'experiment_id': EXPERIMENT_ID, 'videos': [
            dict(cohort='baseline', video_id='deleted', title='Deleted video', published_at='2026-09-09T12:00:00Z')]}
        report = build_report(history=history, analytics=api, previous=previous,
                              now=datetime(2026, 9, 16, 12, tzinfo=timezone.utc))
        self.assertEqual([(r['video_id'], r['status']) for r in report['videos']],
                         [('deleted', 'unavailable_video'), ('experiment', 'pending')])
        self.assertEqual(report['status'], 'collecting_insufficient_sample')
        self.assertEqual(api.reports().query().execute.call_count, 1)

    def test_measured_window_excludes_lifetime_counts(self):
        from growth_experiment import build_report, METRICS
        api = MagicMock()
        api.reports().query().execute.side_effect = [
            {'rows': [['old', 99999]]},
            {'columnHeaders': [{'name': name} for name in METRICS.split(',')], 'rows': [[12, 7, 25, 70, 0]]}]
        history = [dict(video_id='old', title='Old', privacy='public', machine={'fmt': 'shorts'},
                        published_at='2026-09-01T12:00:00Z', views=99999)]
        report = build_report(history=history, analytics=api,
                              now=datetime(2026, 9, 16, 12, tzinfo=timezone.utc))
        self.assertEqual(report['cohorts']['baseline']['median_views'], 12)
        calls = [c.kwargs for c in api.reports().query.call_args_list if c.kwargs.get('filters', '').startswith('video==')]
        self.assertEqual(calls[0]['startDate'], '2026-09-02')
        self.assertEqual(calls[0]['endDate'], '2026-09-04')


class PrepublicationTests(unittest.TestCase):
    def test_publication_rechecks_new_upload(self):
        selector = StorySelector(Mock())
        candidate = analyst(); qualify(candidate, today=TODAY)
        def refresh():
            selector.recent_uploads = [dict(event_ids=candidate['event_ids'])]
            return []
        with patch.object(selector, '_recent_upload_titles', side_effect=refresh) as read:
            self.assertFalse(selector.publication_allowed(candidate))
        read.assert_called_once()

class ProviderProbeTests(unittest.TestCase):
    def test_quota_exhausted_without_leaking_key_metadata(self):
        import provider_status
        response = Mock(status_code=200)
        response.json.return_value = {'data': {'limit_remaining': 0, 'limit_reset': 'monthly', 'label': 'secret-label', 'hash': 'secret-hash'}}
        with patch.object(provider_status, 'OPENROUTER_API_KEY', 'test'), \
                patch('provider_status.requests.get', return_value=response):
            result = provider_status.inspect_openrouter()
        self.assertEqual(result['status'], 'quota_exhausted')
        self.assertNotIn('secret', json.dumps(result))
        self.assertFalse(result['generation_tested'])

    def test_audit_mode_is_explicitly_read_only(self):
        from pipeline_schedule import resolve_mode
        self.assertEqual(resolve_mode('workflow_dispatch', {'inputs': {'mode': 'audit'}}), 'audit')

class CompletedLowSampleTests(unittest.TestCase):
    def test_fixed_low_view_baseline_does_not_wait_forever_for_more_views(self):
        from growth_experiment import build_report, METRICS
        from editorial_policy import EXPERIMENT_ID
        api = MagicMock()
        api.reports().query().execute.side_effect = [
            {'rows': [[f'b{i}', 1] for i in range(10)]},
            *[{'columnHeaders': [{'name': name} for name in METRICS.split(',')],
               'rows': [[1, 1, 20, 60, 0]]} for _ in range(20)]]
        history = [dict(video_id=f'b{i}', title='Baseline', privacy='public', machine={'fmt': 'shorts'},
                        published_at=f'2026-09-{i+1:02d}T12:00:00Z') for i in range(10)]
        history += [dict(video_id=f'e{i}', title='Experiment', privacy='public',
                         machine={'fmt': 'shorts', 'exp': EXPERIMENT_ID},
                         published_at=f'2026-09-{i+17:02d}T12:00:00Z') for i in range(10)]
        report = build_report(history=history, analytics=api, now=datetime(2026, 10, 3, tzinfo=timezone.utc))
        self.assertEqual(report['status'], 'ready_for_comparison')
        self.assertTrue(report['thin_sample'])

class DisclosureWordingTests(unittest.TestCase):
    def test_reporting_lag_is_not_an_established_deadline_violation(self):
        story = {'franchise': 'congress_trade', 'ticker': 'MSFT'}
        self.assertTrue(validate_editorial_script({'title': 'Microsoft buy surfaced 32 days late', 'full_script': ''}, story))
        self.assertFalse(validate_editorial_script({'title': 'Microsoft buy disclosed 32 days later', 'full_script': ''}, story))
