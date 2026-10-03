import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from channel_status import build_status, METRICS
from outlier_scanner import preceding_baseline
from script_generator import ScriptGenerator, _PROVIDER_DEAD


class MaintenanceTests(unittest.TestCase):
    def test_independent_provider_survives_rejection_and_dead_account_stays_skipped(self):
        writer = ScriptGenerator(openrouter_key='test', gemini_key='other', groq_key='')
        writer.last_error = 'openrouter: HTTP 402 account rejected'
        with patch.object(writer, '_chat', side_effect=[_PROVIDER_DEAD, json.dumps({'full_script': 'valid'}),
                                                       json.dumps({'full_script': 'again'})]) as chat:
            self.assertEqual(writer._call_llm('prompt', 'title')['full_script'], 'valid')
            self.assertEqual(writer._call_llm('prompt', 'title')['full_script'], 'again')
        self.assertEqual([call.args[0] for call in chat.call_args_list], ['openrouter', 'gemini', 'gemini'])

    def test_breakout_baseline_excludes_candidate_newer_uploads_streams_and_other_durations(self):
        def video(vid, published, duration='PT1M', **extra):
            return dict(id=vid, snippet={'publishedAt': published}, contentDetails={'duration': duration},
                        statistics={'viewCount': '100'}, **extra)
        target = video('target', '2026-10-01T00:00:00Z')
        uploads = [target, video('old', '2026-09-30T00:00:00Z'),
                   video('newer', '2026-10-02T00:00:00Z'),
                   video('long', '2026-09-29T00:00:00Z', 'PT10M'),
                   video('stream', '2026-09-29T00:00:00Z', liveStreamingDetails={})]
        self.assertEqual([r['id'] for r in preceding_baseline(target, uploads)], ['old'])

    def test_weekly_periods_follow_available_date_and_preserve_missing_dates(self):
        names = ['day'] + METRICS.split(',')
        end = datetime(2026, 10, 1).date()
        rows = [[str(end - timedelta(days=i)), 10, 4, 3, 1, 0] for i in range(14) if i != 3]
        api = MagicMock()
        api.reports().query().execute.side_effect = [
            {'columnHeaders': [{'name': n} for n in names], 'rows': rows},
            *[{'rows': []} for _ in range(2)]]
        result = build_status(api, datetime(2026, 10, 3, 20, tzinfo=timezone.utc))
        self.assertEqual(result['latest_analytics_date'], '2026-10-01')
        self.assertEqual(result['periods']['current']['missing_dates'], ['2026-09-28'])
        self.assertEqual(result['periods']['current']['totals']['views'], 60)
        self.assertIsNone(result['periods']['current']['formats']['shorts'])
