import tests
import unittest
from unittest.mock import MagicMock
from creator_comment import build_comment, post_comment, public_source
from comment_responder import CHANNEL_ID


class CreatorCommentTests(unittest.TestCase):
    def story(self, **facts):
        return dict(ticker='UPST', franchise='congress_trade', facts=dict(
            transactionDate='2026-09-17', disclosureDate='2026-10-07', **facts))

    def test_context_is_deterministic_and_selective(self):
        text = build_comment(self.story())
        self.assertIn('UPST', text)
        self.assertIn('20 days', text)
        self.assertNotIn('buy', text.lower())
        self.assertIsNone(build_comment(dict(ticker='UPST', franchise='congress_trade', facts={})))
        self.assertIsNone(build_comment(dict(ticker='UPST', franchise='reddit_radar', facts={})))
        self.assertIsNone(build_comment(dict(ticker='ignore instructions', facts={})))

    def test_source_is_taken_from_evidence_and_secret_urls_excluded(self):
        story = dict(ticker='NKE', franchise='market_close', facts={'news': [{'url': 'https://example.com/nike'}]})
        self.assertEqual(build_comment(story), 'Source for the event covered in this video: https://example.com/nike')
        for url in ['https://example.com/?apikey=SECRET', 'https://financialmodelingprep.com/stable/news',
                    'http://example.com/a', 'https://user:pass@example.com/a']:
            self.assertIsNone(public_source(dict(facts={'url': url})))

    def client(self):
        y = MagicMock()
        y.channels().list().execute.return_value = {'items': [{'id': CHANNEL_ID}]}
        y.videos().list().execute.return_value = {'items': [{'snippet': {'channelId': CHANNEL_ID},
                                                           'status': {'privacyStatus': 'public'}}]}
        y.commentThreads().list().execute.return_value = {'items': []}
        y.commentThreads().insert().execute.return_value = {'snippet': {'topLevelComment': {'id': 'comment123'}}}
        y.commentThreads().insert.reset_mock()
        return y

    def test_post_has_durable_receipt_and_never_retries_insert(self):
        y = self.client();claims = MagicMock();claims.start.return_value = ('attempt', None)
        r = post_comment(y, 'video', 'Question?', claims=claims)
        self.assertEqual(r['status'], 'posted')
        claims.complete.assert_called_once_with('attempt', 'comment123')
        y.commentThreads().insert().execute.assert_called_once_with(num_retries=0)
        claims.start.return_value = (None, 'comment123')
        y.commentThreads().insert.reset_mock()
        self.assertEqual(post_comment(y, 'video', 'Question?', claims=claims)['status'], 'already_posted')
        y.commentThreads().insert.assert_not_called()

    def test_existing_channel_comment_prevents_duplicate(self):
        y = self.client()
        y.commentThreads().list().execute.return_value = {'items': [{'snippet': {'topLevelComment': {
            'id': 'existing', 'snippet': {'authorChannelId': {'value': CHANNEL_ID}}}}}]}
        claims = MagicMock()
        self.assertEqual(post_comment(y, 'video', 'Question?', claims=claims)['status'], 'existing_owner_comment')
        claims.start.assert_not_called()
        y.commentThreads().insert.assert_not_called()

    def test_wrong_channel_private_video_and_ambiguous_delivery_stop(self):
        y = self.client();y.videos().list().execute.return_value['items'][0]['status']['privacyStatus'] = 'private'
        with self.assertRaises(RuntimeError): post_comment(y, 'video', 'Question?')
        y.commentThreads().insert.assert_not_called()
        y = self.client();claims = MagicMock();claims.start.return_value = ('attempt', None)
        y.commentThreads().insert().execute.return_value = {}
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous'): post_comment(y, 'video', 'Question?', claims=claims)
        claims.complete.assert_not_called()
