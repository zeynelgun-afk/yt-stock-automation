import tests
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from analytics_reporter import analytics_window, build_report, send_weekly_report
from telegram_bot import TelegramApprovalBot
from outlier_scanner import outside_stock_niche
import weekly_runner


class WeeklyReportingFixTests(unittest.TestCase):
    def test_delayed_analytics_moves_window_and_exposes_missing_day(self):
        api = MagicMock()
        api.reports().query().execute.return_value = {
            'columnHeaders': [{'name': 'day'}, {'name': 'views'}],
            'rows': [[str(datetime(2026, 10, 7).date()-timedelta(days=i)), 10]
                     for i in range(10) if i != 2]}
        window = analytics_window(api, 7, datetime(2026, 10, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(window, dict(start='2026-10-01', end='2026-10-07',
            requested_through='2026-10-08', missing_dates=['2026-10-05']))
        api.reports().query().execute.return_value = {'rows': []}
        with self.assertRaisesRegex(RuntimeError, 'window unavailable'): analytics_window(api, 7)

    def test_report_labels_actual_dates(self):
        row = dict(analytics_window=dict(start='2026-10-01', end='2026-10-07', missing_dates=['2026-10-05']),
            views=100, subs_gained=1, avg_view_pct=80, avg_view_seconds=30,
            engaged_views=40, title='Test', is_long=False)
        with patch('analytics_reporter.fetch_video_stats', return_value=[row]), \
             patch('analytics_reporter.compute_franchise_weights', return_value={}):
            report = build_report()
        self.assertIn('2026-10-01 – 2026-10-07', report)
        self.assertIn('Eksik günler: 2026-10-05', report)

    def test_generation_error_is_failure_even_when_alert_delivered(self):
        with patch('analytics_reporter.build_report', side_effect=RuntimeError('API outage')), \
             patch('analytics_reporter.TelegramApprovalBot.send_text', return_value=True):
            self.assertFalse(send_weekly_report())

    def test_failed_delivery_still_runs_learning_and_records_failure(self):
        with TemporaryDirectory() as d, patch.object(weekly_runner, 'STATUS_PATH', Path(d)/'status.json'), \
             patch.object(weekly_runner, 'send_weekly_report', return_value=False), \
             patch.object(weekly_runner, 'run_weekly_learning', return_value=True) as learn:
            report = weekly_runner.run()
            self.assertFalse(report['success'])
            learn.assert_called_once()
            self.assertEqual(json.loads(weekly_runner.STATUS_PATH.read_text())['steps'],
                dict(performance_report=False, learning=True))

    def test_text_delivery_rejections_are_visible_and_acceptance_has_receipt(self):
        bot = TelegramApprovalBot(token='SECRET_TEST_TOKEN', chat_id='test')
        for code, payload in [(400, {'description': 'SECRET_TEST_TOKEN'}), (200, {'ok': False})]:
            response = MagicMock(status_code=code);response.json.return_value=payload
            with patch('telegram_bot.requests.post', return_value=response), self.assertLogs('telegram_bot',level='ERROR') as logs:
                self.assertFalse(bot.send_text('test'))
            self.assertNotIn('SECRET_TEST_TOKEN',str(logs.output))
        response = MagicMock(status_code=200);response.json.return_value={'ok': True,'result': {'message_id': 123}}
        with patch('telegram_bot.requests.post',return_value=response), self.assertLogs('telegram_bot',level='INFO') as logs:
            self.assertTrue(bot.send_text('test'))
        self.assertIn('message_id=123',str(logs.output))

    def test_other_market_context_excludes_generic_clips_but_preserves_us_coverage(self):
        video = lambda title: {'snippet': {'title': title}}
        india = {'snippet': {'country': 'IN', 'description': 'Indian stock market investing'}}
        crypto = {'snippet': {'title': 'Cryptonary', 'description': 'Crypto investing'}}
        self.assertTrue(outside_stock_niche(video('Fear&Greed vs CPT'), crypto))
        self.assertTrue(outside_stock_niche(video('5 Small Cap Stocks With Massive Order Books'), india))
        self.assertTrue(outside_stock_niche(video('Top Mutual Funds for SIP in 2026'), {}))
        self.assertFalse(outside_stock_niche(video('Nvidia Stock Earnings'), india))
        self.assertFalse(outside_stock_niche(video('Tesla Stock Valuation'), crypto))


class EngagementSignalTests(unittest.TestCase):
    """The watch / comment / share funnel needs three measured outcomes, not one."""

    def test_video_stats_request_and_expose_comment_share_like_counts(self):
        from analytics_reporter import fetch_video_stats
        api, data = MagicMock(), MagicMock()
        names = ['video', 'views', 'engagedViews', 'estimatedMinutesWatched',
                 'averageViewDuration', 'averageViewPercentage', 'subscribersGained',
                 'comments', 'shares', 'likes']

        def query(**kw):
            # The Shorts-classifier call asks only for views; the main call is the
            # one that must carry the engagement metrics.
            rows = ([['v1', 120, 60, 4.0, 20.0, 57.0, 2, 9, 4, 30]]
                    if 'engagedViews' in kw.get('metrics', '') else [])
            self.assertNotIn('dislikes', kw.get('metrics', ''))
            return MagicMock(execute=MagicMock(return_value={
                'columnHeaders': [{'name': n} for n in names], 'rows': rows}))

        api.reports().query.side_effect = query
        data.videos().list().execute.return_value = {'items': [{
            'id': 'v1', 'snippet': {'title': 'T', 'publishedAt': '2026-10-20T12:00:00Z', 'tags': ['fr:insider_watch']},
            'contentDetails': {'duration': 'PT35S'}}]}
        with patch('googleapiclient.discovery.build', side_effect=[api, data]), \
             patch('analytics_reporter._get_credentials'), \
             patch('analytics_reporter.analytics_window',
                   return_value={'start': '2026-10-01', 'end': '2026-10-07', 'missing_dates': []}):
            stats = fetch_video_stats(7)
        metrics = api.reports().query.call_args_list[0].kwargs['metrics']
        for metric in ('comments', 'shares', 'likes'):
            self.assertIn(metric, metrics)
        self.assertEqual((stats[0]['comments'], stats[0]['shares'], stats[0]['likes']), (9, 4, 30))

    def test_engagement_rates_normalise_by_reach_and_keep_missing_distinct_from_zero(self):
        from learning_engine import _per_1k
        self.assertEqual(_per_1k(9, 1000), 9.0)
        # Same raw count, 10x the reach -> a tenth of the rate. Raw counts alone
        # would always rank the widest-reaching video first.
        self.assertEqual(_per_1k(9, 10000), 0.9)
        self.assertEqual(_per_1k(0, 1000), 0.0)          # a real zero stays 0.0
        self.assertIsNone(_per_1k(None, 1000))           # absent metric is not zero
        self.assertIsNone(_per_1k(9, 99))                # denominator too thin to mean anything

    def test_distilled_comment_and_share_drivers_reach_the_script_prompt(self):
        import script_generator
        learned = {'own_patterns': {'winning_patterns': ['named the company first'],
                                    'comment_drivers': ['stated a real limitation'],
                                    'share_drivers': ['one self-contained quotable line']}}
        with patch.object(script_generator, '_learnings', return_value=learned):
            block = script_generator._own_channel_block()
        self.assertIn('Earned comments: stated a real limitation', block)
        self.assertIn('Earned shares: one self-contained quotable line', block)
        # Retention lessons must stay distinguishable from engagement lessons.
        self.assertIn('Held OUR viewers: named the company first', block)
