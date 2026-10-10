import tests
import unittest
from collections import Counter
from unittest.mock import MagicMock, patch
from outlier_scanner import fetch_baseline_uploads, finance_context, scan_outliers


def video(vid, date='2026-09-20T00:00:00Z', views=100, title='Tesla update', description='US stock investing', duration='PT8M'):
    return {'id': vid, 'snippet': {'publishedAt': date, 'title': title, 'description': description,
            'channelId': 'channel', 'channelTitle': 'Finance Channel', 'defaultLanguage': 'en'},
            'statistics': {'viewCount': str(views)}, 'contentDetails': {'duration': duration}}


class OutlierDiscoveryTests(unittest.TestCase):
    def test_baseline_reads_past_newer_first_page(self):
        yt = MagicMock()
        yt.playlistItems().list().execute.side_effect = [
            {'items': [{'contentDetails': {'videoId': 'new'}}], 'nextPageToken': 'second'},
            {'items': [{'contentDetails': {'videoId': 'old'}}]}]
        yt.videos().list().execute.side_effect = [
            {'items': [video('new', '2026-10-09T00:00:00Z')]}, {'items': [video('old')]}]
        channel = {'contentDetails': {'relatedPlaylists': {'uploads': 'uploads'}}}
        result = fetch_baseline_uploads(yt, channel, video('target', '2026-10-01T00:00:00Z'), Counter())
        self.assertEqual([v['id'] for v in result], ['new', 'old'])
        self.assertEqual(yt.playlistItems().list.call_args.kwargs['pageToken'], 'second')

    def test_company_only_title_uses_finance_context_without_accepting_cricket(self):
        self.assertTrue(finance_context(video('tesla')))
        self.assertFalse(finance_context(video('sports', title='India wins', description='Cricket highlights')))

    def test_relaxed_candidate_is_labeled_emerging_and_search_errors_fail(self):
        yt = MagicMock()
        yt.search().list().execute.return_value = {'items': [{'id': {'videoId': 'target'}}]}
        yt.videos().list().execute.return_value = {'items': [video('target', '2026-10-01T00:00:00Z', 1500)]}
        yt.channels().list().execute.return_value = {'items': [{'id': 'channel',
            'statistics': {'subscriberCount': '70000'}, 'snippet': {'description': 'US stock investing'}}]}
        with patch('outlier_scanner._build_client', return_value=yt), \
             patch('outlier_scanner.fetch_baseline_uploads', return_value=[video(str(i), views=500) for i in range(3)]):
            result = scan_outliers(queries=['Tesla stock'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['signal_tier'], 'emerging')
        self.assertEqual(result[0]['ratio'], 3)
        self.assertEqual({c.kwargs['order'] for c in yt.search().list.call_args_list if 'order' in c.kwargs}, {'relevance', 'viewCount'})
        yt.search().list().execute.side_effect = RuntimeError('quota')
        with patch('outlier_scanner._build_client', return_value=yt):
            with self.assertRaisesRegex(RuntimeError, 'previous evidence retained'):
                scan_outliers(queries=['Tesla stock'])

    def test_finance_keyword_on_political_channel_is_not_enough(self):
        yt = MagicMock()
        yt.search().list().execute.return_value = {'items': [{'id': {'videoId': 'target'}}]}
        yt.videos().list().execute.return_value = {'items': [video('target', '2026-10-01T00:00:00Z', 9000, title='Congress stock trading') ]}
        yt.channels().list().execute.return_value = {'items': [{'id': 'channel',
            'statistics': {'subscriberCount': '1000'}, 'snippet': {'description': 'Political speeches'}}]}
        previous = [video(str(i), title='Political speech', description='Government news') for i in range(5)]
        with patch('outlier_scanner._build_client', return_value=yt), \
             patch('outlier_scanner.fetch_baseline_uploads', return_value=previous):
            self.assertEqual(scan_outliers(queries=['Congress stocks']), [])

    def test_non_stock_markets_are_excluded_from_finance_candidates(self):
        from outlier_scanner import OUTSIDE_US_STOCK_NICHE
        for title in ['The New Pokemon Fear and Greed Index', 'Nifty 50 Stocks', '₹1 Lakh Invested']:
            self.assertTrue(OUTSIDE_US_STOCK_NICHE.search(title))
        self.assertFalse(OUTSIDE_US_STOCK_NICHE.search('Nike Stock Earnings $NKE'))
