import json
import os
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import requests

from pipeline_schedule import resolve_mode
from story_pool import StoryPoolCollector
from telegram_bot import TelegramApprovalBot


class ScheduleTests(unittest.TestCase):
    def test_delayed_september_runs_keep_exactly_one_recap(self):
        self.assertEqual(resolve_mode('schedule', {'schedule': '5 20 * * 1-5'},
                                      '2026-09-10T22:29:53Z'), 'long')
        self.assertEqual(resolve_mode('schedule', {'schedule': '5 21 * * 1-5'},
                                      '2026-09-10T23:04:32Z'), 'skip')

    def test_both_dst_transitions(self):
        for day, active_hour in [('2026-03-06', 21), ('2026-03-09', 20),
                                 ('2026-10-30', 20), ('2026-11-02', 21)]:
            for hour in (20, 21):
                with self.subTest(day=day, hour=hour):
                    self.assertEqual(resolve_mode('schedule', {'schedule': f'5 {hour} * * 1-5'},
                                                  f'{day}T23:30:00Z'),
                                     'long' if hour == active_hour else 'skip')

    def test_overnight_delay_and_rerun_use_original_occurrence(self):
        # Friday's job was not created until Saturday UTC. A later retry must
        # use the same creation timestamp, even across the DST switch Sunday.
        event = {'schedule': '5 20 * * 1-5'}
        with patch('pipeline_schedule.datetime') as clock:
            clock.fromisoformat.side_effect = datetime.fromisoformat
            clock.now.side_effect = AssertionError('Resolver must not read the retry clock')
            self.assertEqual(resolve_mode('schedule', event, '2026-10-31T01:00:00Z'), 'long')

    def test_other_modes_and_invalid_events(self):
        for mode in ('shorts', 'long', 'analytics'):
            self.assertEqual(resolve_mode('workflow_dispatch', {'inputs': {'mode': mode}}), mode)
        self.assertEqual(resolve_mode('schedule', {'schedule': '35 13 * * 1-5'}), 'event-shorts')
        self.assertEqual(resolve_mode('schedule', {'schedule': '0 15 * * 0'}), 'analytics')
        with self.assertRaises(ValueError):
            resolve_mode('schedule', {'schedule': 'unknown'})
        with self.assertRaises(ValueError):
            resolve_mode('schedule', {'schedule': '5 20 * * 1-5'}, '2026-09-10T22:00:00')


class InsiderTests(unittest.TestCase):
    @staticmethod
    def row(day, name='CEO', shares=100000, kind='S-Sale'):
        return dict(transactionDate=day, reportingName=name, symbol='TEST',
                    securitiesTransacted=shares, price=10, transactionType=kind,
                    typeOfOwner='Chief Executive Officer')

    def collect(self, rows):
        fetcher = Mock()
        fetcher.get_insider_trades.return_value = rows
        with patch('story_pool.ny_now', return_value=datetime(2026, 9, 11, tzinfo=ZoneInfo('America/New_York'))):
            return StoryPoolCollector(fetcher)._insider_trades()

    def test_different_dates_remain_separate_and_same_day_legs_combine(self):
        result = self.collect([self.row('2026-09-08'), self.row('2026-09-09'),
                               self.row('2026-09-09')])
        by_date = {r['transactionDate']: r for r in result['big_trades']}
        self.assertEqual(by_date['2026-09-08']['value_usd'], 1000000)
        self.assertEqual(by_date['2026-09-08']['transactions'], 1)
        self.assertEqual(by_date['2026-09-09']['value_usd'], 2000000)
        self.assertEqual(by_date['2026-09-09']['transactions'], 2)

    def test_cluster_excludes_old_future_unnamed_and_zero_value_buys(self):
        rows = [self.row('2026-09-11', 'A', kind='P-Purchase'),
                self.row('2026-09-05', 'B', kind='P-Purchase'),
                self.row('2026-09-04', 'OLD', kind='P-Purchase'),
                self.row('2026-09-12', 'FUTURE', kind='P-Purchase'),
                self.row('2026-09-11', None, kind='P-Purchase'),
                self.row('2026-09-11', 'ZERO', shares=0, kind='P-Purchase')]
        self.assertEqual(self.collect(rows)['cluster_buys'], [])
        self.assertEqual(self.collect(rows + [self.row('2026-09-10', 'C', kind='P-Purchase')])['cluster_buys'], ['TEST'])

    def test_invalid_date_cannot_be_attributed_to_another_trade(self):
        result = self.collect([self.row('invalid'), self.row('2026-09-11')])
        self.assertEqual(len(result['big_trades']), 1)
        self.assertEqual(result['big_trades'][0]['value_usd'], 1000000)


class LearningOutageTests(unittest.TestCase):
    def refresh(self, stats_result=None, error=None):
        from learning_engine import run_weekly_learning
        with TemporaryDirectory() as directory, ExitStack() as stack:
            path = Path(directory) / 'learnings.json'
            before = {'updated_at': '2026-09-06T12:00:00', 'weights_version': 2,
                      'franchise_weights': {'congress_trade': 1.3},
                      'section_updated_at': {'franchise_weights': '2026-09-06T12:00:00'}}
            path.write_text(json.dumps(before))
            stack.enter_context(patch('learning_engine.LEARNINGS_FILE', path))
            stack.enter_context(patch('learning_engine.TelegramApprovalBot'))
            stack.enter_context(patch('analytics_reporter.fetch_video_stats', return_value=stats_result, side_effect=error))
            stack.enter_context(patch('outlier_scanner.scan_outliers', return_value=[]))
            run_weekly_learning()
            return before, json.loads(path.read_text())

    def test_outage_preserves_weights_and_their_actual_age(self):
        before, after = self.refresh(error=RuntimeError('simulated outage'))
        self.assertEqual(after['franchise_weights'], before['franchise_weights'])
        self.assertEqual(after['section_updated_at']['franchise_weights'],
                         before['section_updated_at']['franchise_weights'])
        self.assertIn('previous weights retained', after['section_status']['weights'])

    def test_successful_empty_report_resets_weights_to_neutral(self):
        before, after = self.refresh(stats_result=[])
        self.assertEqual(after['franchise_weights'], {})
        self.assertNotEqual(after['section_updated_at']['franchise_weights'],
                            before['section_updated_at']['franchise_weights'])


class TelegramLogTests(unittest.TestCase):
    def test_text_and_video_connection_errors_do_not_log_token(self):
        token = 'DEMO_SECRET_TOKEN'
        bot = TelegramApprovalBot(token=token, chat_id='test')
        with TemporaryDirectory() as directory:
            video = Path(directory) / 'video.mp4'
            video.write_bytes(b'test')
            for send in (lambda: bot.send_text('test'), lambda: bot.send_video_notification(str(video), 'test')):
                with self.subTest(send=send), patch('telegram_bot.requests.post', side_effect=requests.ConnectionError(bot.api_url)), self.assertLogs('telegram_bot', level='ERROR') as logs:
                    self.assertFalse(send())
                self.assertNotIn(token, '\n'.join(logs.output))

    def test_video_error_body_is_not_logged(self):
        bot = TelegramApprovalBot(token='DEMO_SECRET_TOKEN', chat_id='test')
        with TemporaryDirectory() as directory:
            video = Path(directory) / 'video.mp4'
            video.write_bytes(b'test')
            with patch('telegram_bot.requests.post', return_value=Mock(status_code=401, text=bot.api_url)), self.assertLogs('telegram_bot', level='ERROR') as logs:
                self.assertFalse(bot.send_video_notification(str(video), 'test'))
            self.assertNotIn('DEMO_SECRET_TOKEN', '\n'.join(logs.output))
            self.assertIn('401', '\n'.join(logs.output))


class TrendOAuthTests(unittest.TestCase):
    def test_env_only_credentials_work_without_publisher_side_effect(self):
        from outlier_scanner import _build_client
        # A syntactically valid test credential; discovery is mocked, no network.
        token = dict(client_id='test', client_secret='test', refresh_token='test',
                     token='test', expiry='2099-01-01T00:00:00Z',
                     scopes=['https://www.googleapis.com/auth/youtube.readonly'])
        with TemporaryDirectory() as directory, patch('outlier_scanner.BASE_DIR', Path(directory)), \
                patch('outlier_scanner.YOUTUBE_API_KEY', ''), \
                patch.dict(os.environ, {'YOUTUBE_TOKEN_JSON': json.dumps(token)}), \
                patch('googleapiclient.discovery.build') as build:
            self.assertIs(_build_client(), build.return_value)
            creds = build.call_args.kwargs['credentials']
            self.assertIn('https://www.googleapis.com/auth/youtube.readonly', creds.scopes)
            self.assertFalse((Path(directory) / 'token.json').exists())

    def test_missing_readonly_scope_is_rejected(self):
        from outlier_scanner import _build_client
        token = dict(client_id='test', client_secret='test', refresh_token='test', scopes=[])
        with TemporaryDirectory() as directory, patch('outlier_scanner.BASE_DIR', Path(directory)), \
                patch('outlier_scanner.YOUTUBE_API_KEY', ''), \
                patch.dict(os.environ, {'YOUTUBE_TOKEN_JSON': json.dumps(token)}):
            with self.assertRaises(RuntimeError):
                _build_client()
