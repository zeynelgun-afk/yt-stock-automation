import tests  # enforce the no-real-inference unit-test boundary
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import multiprocessing
import sqlite3
import unittest
from unittest.mock import MagicMock, patch


def race_claim(db, queue):
    from delivery_claims import DeliveryClaims, DeliveryBlocked
    try:
        DeliveryClaims(db).start('comment', ['channel:parent'])
        queue.put('claimed')
    except DeliveryBlocked:
        queue.put('blocked')


class ClaimTests(unittest.TestCase):
    def test_attempt_durable_reopen_completion_and_replay(self):
        from delivery_claims import DeliveryClaims, DeliveryBlocked
        with TemporaryDirectory() as tmp:
            db = Path(tmp)/'claims.sqlite'
            claims = DeliveryClaims(db)
            token, receipt = claims.start('upload', ['channel:ev1', 'channel:ev2'])
            self.assertIsNone(receipt)
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute('select status from attempts').fetchone()[0], 'attempted')
            with self.assertRaises(DeliveryBlocked): DeliveryClaims(db).start('upload', ['channel:ev2'])
            # Conservatively refuse a new upload too, until ambiguity reconciled.
            with self.assertRaises(DeliveryBlocked): claims.start('upload', ['channel:ev3'])
            claims.complete(token, 'video-id')
            self.assertEqual(DeliveryClaims(db).start('upload', ['channel:ev2'])[1], 'video-id')
            with self.assertRaises(DeliveryBlocked): claims.complete(token, 'different-id')
            self.assertEqual(db.stat().st_mode & 0o777, 0o600)

    def test_completed_replay_binds_new_aliases_without_resending(self):
        from delivery_claims import DeliveryClaims
        with TemporaryDirectory() as tmp:
            claims = DeliveryClaims(Path(tmp)/'claims.sqlite')
            token, _ = claims.start('upload', ['ev:original'])
            claims.complete(token, 'video-id')
            self.assertEqual(claims.start('upload', ['ev:original','ev:added'])[1], 'video-id')
            self.assertEqual(claims.start('upload', ['ev:added'])[1], 'video-id')

    def test_operator_reconciliation_is_durable_and_required_before_retry(self):
        from delivery_claims import DeliveryClaims, DeliveryBlocked
        with TemporaryDirectory() as tmp:
            claims = DeliveryClaims(Path(tmp)/'claims.sqlite')
            token,_ = claims.start('comment',['channel:parent'])
            for note in ['', 'too short']:
                with self.assertRaises(DeliveryBlocked): claims.reconcile(token,'not-delivered',note)
            claims.reconcile(token,'not-delivered','Operator verified complete remote thread and no insert occurred')
            token2,_ = DeliveryClaims(claims.path).start('comment',['channel:parent'])
            self.assertNotEqual(token,token2)
            claims.reconcile(token2,'delivered','Operator found matching remote reply and confirmed channel identity','reply-id')
            self.assertEqual(DeliveryClaims(claims.path).start('comment',['channel:parent'])[1], 'reply-id')
            with sqlite3.connect(claims.path) as db:
                self.assertEqual(db.execute('select count(*) from reconciliations').fetchone()[0],2)
                self.assertEqual(db.execute('select count(*) from attempts').fetchone()[0],2)

    def test_concurrent_processes_only_one_sender(self):
        with TemporaryDirectory() as tmp:
            db = str(Path(tmp)/'claims.sqlite')
            from delivery_claims import DeliveryClaims
            DeliveryClaims(db)
            queue = multiprocessing.Queue()
            workers = [multiprocessing.Process(target=race_claim, args=(db,queue)) for _ in range(4)]
            for worker in workers: worker.start()
            for worker in workers:
                worker.join(10); self.assertEqual(worker.exitcode, 0)
            self.assertEqual(sorted(queue.get(timeout=2) for _ in workers), ['blocked']*3+['claimed'])

    def test_receipt_requires_valid_identifier_and_attempt_ownership(self):
        from delivery_claims import DeliveryClaims, DeliveryBlocked
        with TemporaryDirectory() as tmp:
            claims = DeliveryClaims(Path(tmp)/'claims.sqlite')
            token, _ = claims.start('comment', ['channel:parent'])
            for bad in ['', None, 5]:
                with self.assertRaises(DeliveryBlocked): claims.complete(token, bad)
            with self.assertRaises(DeliveryBlocked): claims.complete('foreign-token', 'reply-id')
            with self.assertRaises(DeliveryBlocked): claims.start('comment', ['channel:parent'])

    def test_checkout_state_forbidden(self):
        from delivery_claims import DeliveryClaims, DeliveryBlocked
        with self.assertRaises(DeliveryBlocked): DeliveryClaims(Path(__file__).resolve().parents[1]/'claims.sqlite')


class CommentClaimTests(unittest.TestCase):
    def test_ambiguous_comment_persists_and_blocks_new_process_retry(self):
        from delivery_claims import DeliveryClaims, DeliveryBlocked
        from comment_responder import respond
        from test_comment_responder import service, NOW, REPLY
        with TemporaryDirectory() as tmp:
            db = Path(tmp)/'claims.sqlite'
            yt, writer = service(), MagicMock(); writer.draft.return_value = REPLY
            yt.comments().insert().execute.side_effect = TimeoutError()
            yt.reset_mock()
            with self.assertRaises(TimeoutError): respond(yt, writer, publish=True, now=NOW, claims=DeliveryClaims(db))
            with self.assertRaises(DeliveryBlocked): respond(yt,writer,publish=True,now=NOW,claims=DeliveryClaims(db))
            self.assertEqual(yt.comments().insert.call_count, 1)

    def test_completed_comment_receipt_blocks_insert_even_with_empty_remote_read(self):
        from delivery_claims import DeliveryClaims
        from comment_responder import respond
        from test_comment_responder import service, NOW, REPLY
        with TemporaryDirectory() as tmp:
            db = Path(tmp)/'claims.sqlite'
            yt, writer = service(), MagicMock(); writer.draft.return_value = REPLY
            self.assertEqual(respond(yt,writer,publish=True,now=NOW,claims=DeliveryClaims(db))['posted'], 1)
            self.assertEqual(respond(yt,writer,publish=True,now=NOW,claims=DeliveryClaims(db))['posted'], 0)
            self.assertEqual(yt.comments().insert.call_count, 1)


class UploadClaimTests(unittest.TestCase):
    def publisher(self, tmp):
        from youtube_publisher import YouTubePublisher
        publisher = YouTubePublisher.__new__(YouTubePublisher)
        publisher.client_secret_path = Path(tmp)/'client.json'; publisher.client_secret_path.write_text('{}')
        publisher.token_path = Path(tmp)/'token.json'; publisher.token_path.write_text('{}')
        publisher.last_error = ''
        return publisher

    def upload(self, publisher, client):
        from comment_responder import CHANNEL_ID
        creds = MagicMock(valid=True); creds.scopes = ['https://www.googleapis.com/auth/youtube.upload']
        client.channels().list().execute.return_value = {'items':[{'id':CHANNEL_ID}]}
        with patch('google.oauth2.credentials.Credentials.from_authorized_user_file',return_value=creds), \
             patch('googleapiclient.discovery.build',return_value=client), patch('googleapiclient.http.MediaFileUpload'):
            return publisher.upload_video('synthetic.mp4','Title','Description',[],extra_tags=['ev:stable-event'])

    def test_ambiguous_upload_never_retries_insert_or_execute(self):
        from delivery_claims import DeliveryClaims
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {'YT_DELIVERY_DB':str(Path(tmp)/'claims.sqlite')}):
            publisher = self.publisher(tmp); client = MagicMock()
            client.videos().insert().execute.side_effect = TimeoutError(); client.reset_mock()
            self.assertEqual(self.upload(publisher,client), '')
            self.assertEqual(self.upload(self.publisher(tmp),client), '')
            client.videos().insert.assert_called_once()
            client.videos().insert().execute.assert_called_once_with(num_retries=0)
            with sqlite3.connect(Path(tmp)/'claims.sqlite') as db:
                self.assertEqual(db.execute('select status from attempts').fetchone()[0],'attempted')

    def test_completed_upload_replay_returns_receipt_without_second_insert(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {'YT_DELIVERY_DB':str(Path(tmp)/'claims.sqlite')}):
            publisher = self.publisher(tmp); client = MagicMock()
            client.videos().insert().execute.return_value = {'id':'video-id'}; client.reset_mock()
            self.assertEqual(self.upload(publisher,client),'video-id')
            self.assertEqual(self.upload(self.publisher(tmp),client),'video-id')
            client.videos().insert.assert_called_once()
            client.videos().insert().execute.assert_called_once_with(num_retries=0)

    def test_upload_claim_is_synced_before_send_receipt_before_thumbnail(self):
        import delivery_claims
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {'YT_DELIVERY_DB':str(Path(tmp)/'claims.sqlite')}):
            publisher = self.publisher(tmp); client = MagicMock(); events = []
            original_sync = delivery_claims.fsync_path
            def sync(path):
                original_sync(path)
                with sqlite3.connect(path) as db:
                    events.extend(row[0] for row in db.execute('select status from attempts'))
            def send(**kw):
                self.assertEqual(events[-1], 'attempted')
                return {'id':'video-id'}
            client.videos().insert().execute.side_effect = send
            with patch('delivery_claims.fsync_path',side_effect=sync):
                self.assertEqual(self.upload(publisher,client),'video-id')
            self.assertEqual(events[-1], 'completed')

    def test_wrong_upload_channel_and_missing_event_never_send(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {'YT_DELIVERY_DB':str(Path(tmp)/'claims.sqlite')}):
            publisher = self.publisher(tmp); client = MagicMock()
            creds = MagicMock(valid=True); creds.scopes = ['https://www.googleapis.com/auth/youtube.upload']
            with patch('google.oauth2.credentials.Credentials.from_authorized_user_file',return_value=creds), \
                 patch('googleapiclient.discovery.build',return_value=client):
                for channels in [[{'id':'wrong'}],[{'id':'UCuIeHEWGJoDhiGLNBrwscZw'}]]:
                    client.channels().list().execute.return_value = {'items':channels}
                    self.assertEqual(publisher.upload_video('synthetic.mp4','Title','Description',[]),'')
            client.videos().insert.assert_not_called()

    def test_missing_id_is_ambiguous_no_thumbnail_or_retry(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {'YT_DELIVERY_DB':str(Path(tmp)/'claims.sqlite')}):
            client = MagicMock(); client.videos().insert().execute.return_value = {}; client.reset_mock()
            self.assertEqual(self.upload(self.publisher(tmp),client),'')
            self.assertEqual(self.upload(self.publisher(tmp),client),'')
            client.videos().insert.assert_called_once(); client.thumbnails().set.assert_not_called()
