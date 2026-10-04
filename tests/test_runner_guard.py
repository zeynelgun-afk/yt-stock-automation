import tests  # enforce the no-real-inference unit-test boundary
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest
from unittest.mock import patch


SHA = 'a'*40

def context(workspace):
    return dict(GITHUB_REPOSITORY='zeynelgun-afk/yt-stock-automation', GITHUB_REF='refs/heads/main',
                GITHUB_EVENT_NAME='schedule', GITHUB_WORKFLOW='US Stock Market Daily YouTube Automation',
                GITHUB_JOB='build-and-generate', GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1', GITHUB_SHA=SHA, GITHUB_WORKFLOW_SHA=SHA,
                GITHUB_WORKFLOW_REF='zeynelgun-afk/yt-stock-automation/.github/workflows/youtube_auto.yml@refs/heads/main',
                GITHUB_WORKSPACE=str(workspace))


class RunnerGuardTests(unittest.TestCase):
    def fixture(self):
        from ops import local_runner_guard as guard
        tmp = Path(self.enterContext(TemporaryDirectory()))
        state, workspace = tmp/'state', tmp/'workspace'; state.mkdir(); workspace.mkdir()
        return guard, state, workspace, context(workspace)

    def completed_run(self, **changes):
        return dict(id=123, run_attempt=1, head_sha=SHA, status='completed',
                    conclusion='success', path='.github/workflows/youtube_auto.yml',
                    repository={'full_name': 'zeynelgun-afk/yt-stock-automation'}) | changes

    def pending(self):
        guard, state, workspace, env = self.fixture()
        guard.start(state, env); guard.mark_success(state, env)
        with patch.object(guard, 'fetch_run', create=True) as fetch:
            guard.finish(state, env)
            fetch.assert_not_called()
        self.assertEqual(json.loads((state/'active.json').read_text())['status'], 'pending-confirmation')
        return guard, state, workspace, env

    def test_confirmation_rejects_failed_cancelled_mismatched_and_incomplete_runs(self):
        for changes in [{'conclusion':'failure'}, {'conclusion':'cancelled'}, {'id':124},
                        {'head_sha':'b'*40}, {'run_attempt':2}, {'status':'in_progress'},
                        {'repository':{'full_name':'other/repo'}}, {'path':'.github/workflows/other.yml'},
                        {'id':'123'}, {'run_attempt':True}]:
            with self.subTest(changes=changes):
                guard, state, workspace, env = self.pending()
                with patch.object(guard, 'fetch_run', return_value=self.completed_run(**changes)):
                    with self.assertRaises(RuntimeError): guard.confirm(state, '123')
                self.assertTrue((state/'active.json').exists())
                self.assertEqual(json.loads((state/'123.json').read_text())['status'], 'pending-confirmation')
                with patch.object(guard, 'fetch_run', return_value=self.completed_run(**changes)):
                    with self.assertRaises(RuntimeError): guard.start(state, {**env,'GITHUB_RUN_ID':'124'})
                self.assertFalse((state/'124.json').exists())

    def test_api_failure_and_malformed_response_fail_closed(self):
        for response in [None, [], {}, {'repository':None}]:
            guard, state, workspace, env = self.pending()
            with patch.object(guard, 'fetch_run', return_value=response):
                with self.assertRaises(RuntimeError): guard.confirm(state, '123')
            self.assertTrue((state/'active.json').exists())
        guard, state, workspace, env = self.pending()
        with patch.object(guard, 'fetch_run', side_effect=OSError('sensitive upstream detail')):
            with self.assertRaisesRegex(RuntimeError, '^Cannot verify GitHub run; fail closed$'):
                guard.confirm(state, '123')
        self.assertTrue((state/'active.json').exists())

    def test_success_auto_confirmation_accepts_new_run(self):
        guard, state, workspace, env = self.pending()
        with patch.object(guard, 'fetch_run', return_value=self.completed_run()) as fetch:
            guard.start(state, {**env, 'GITHUB_RUN_ID':'124'})
            fetch.assert_called_once_with('123')
        self.assertEqual(json.loads((state/'123.json').read_text())['status'], 'success')
        self.assertEqual(json.loads((state/'active.json').read_text())['run_id'], '124')

    def test_failed_pipeline_cannot_confirm_and_never_queries_api(self):
        guard, state, workspace, env = self.fixture()
        guard.start(state, env)
        with self.assertRaises(RuntimeError): guard.finish(state, env)
        with patch.object(guard, 'fetch_run') as fetch:
            with self.assertRaises(RuntimeError): guard.confirm(state, '123')
            with self.assertRaises(RuntimeError): guard.start(state, {**env,'GITHUB_RUN_ID':'124'})
            fetch.assert_not_called()

    def test_confirmation_requires_original_marker_and_no_ambiguous_delivery(self):
        from delivery_claims import DeliveryClaims
        for failure in ['marker', 'delivery', 'wrong-id']:
            guard, state, workspace, env = self.pending()
            if failure == 'marker': (state/'123-success.json').write_text('{}')
            if failure == 'delivery': DeliveryClaims(state.parent/'delivery.sqlite').start('comment',['channel:parent'])
            with patch.object(guard, 'fetch_run', return_value=self.completed_run()):
                with self.assertRaises(RuntimeError): guard.confirm(state, '124' if failure == 'wrong-id' else '123')
            self.assertTrue((state/'active.json').exists())

    def test_public_api_boundary_is_bounded_credential_free_and_sanitized(self):
        guard, state, workspace, env = self.fixture()
        with patch.object(guard, 'urlopen') as fetch:
            fetch.return_value.__enter__.return_value.read.return_value = json.dumps(self.completed_run()).encode()
            self.assertEqual(guard.fetch_run('123'), self.completed_run())
            request = fetch.call_args.args[0]
            self.assertEqual(request.full_url, 'https://api.github.com/repos/zeynelgun-afk/yt-stock-automation/actions/runs/123')
            self.assertNotIn('Authorization', request.headers)
            self.assertLessEqual(fetch.call_args.kwargs['timeout'], 15)
        for body in [b'not json', b'x'*1_048_577]:
            with patch.object(guard, 'urlopen') as fetch:
                fetch.return_value.__enter__.return_value.read.return_value = body
                with self.assertRaisesRegex(RuntimeError, '^Cannot verify GitHub run; fail closed$'):
                    guard.fetch_run('123')
        for failure in [OSError('private detail'), ValueError('private detail')]:
            with patch.object(guard, 'urlopen', side_effect=failure):
                with self.assertRaisesRegex(RuntimeError, '^Cannot verify GitHub run; fail closed$'):
                    guard.fetch_run('123')

    def test_allowlist_and_workflow_revision_fail_closed(self):
        guard,state,workspace,env = self.fixture()
        guard.validate_context(env,state)
        for key,bad in [('GITHUB_REPOSITORY','other/repo'),('GITHUB_REF','refs/pull/1/merge'),
                        ('GITHUB_EVENT_NAME','pull_request'),('GITHUB_WORKFLOW','Unknown'),
                        ('GITHUB_JOB','other'),('GITHUB_RUN_ID','../123'),('GITHUB_RUN_ATTEMPT','2'),
                        ('GITHUB_RUN_ATTEMPT','0'),('GITHUB_SHA','bad'),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_WORKFLOW_REF','historical')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                guard.validate_context({**env,key:bad},state)
        # Automated data-only commits must not require reapproving every SHA.
        guard.validate_context({**env,'GITHUB_SHA':'b'*40,'GITHUB_WORKFLOW_SHA':'b'*40},state)

    def test_success_archives_only_explicit_safe_files_then_blocks_replay(self):
        guard,state,workspace,env = self.fixture()
        (workspace/'output').mkdir(); (workspace/'reports').mkdir(); (workspace/'.git').mkdir()
        (workspace/'output/editorial_selection.json').write_text('{"safe":true}')
        (workspace/'output/editorial_secret.json').write_text('private')
        (workspace/'output/llm_smoke.json').write_text('{"safe":true}')
        (workspace/'reports/channel-status.json').write_text('{"safe":true}')
        (workspace/'token.json').write_text('credential')
        (workspace/'output/token.json').write_text('credential')
        (workspace/'.env').write_text('credential')
        (workspace/'output/editorial_publication.json').symlink_to(workspace/'token.json')
        guard.start(state,env)
        guard.mark_success(state,env)
        guard.finish(state,env)
        archive = next(state.glob('*.tar.gz'))
        with tarfile.open(archive) as tar:
            self.assertEqual(set(tar.getnames()), {'output/editorial_selection.json','output/llm_smoke.json','reports/channel-status.json'})
        self.assertEqual(json.loads((state/'active.json').read_text())['status'], 'pending-confirmation')
        with patch.object(guard, 'fetch_run', return_value=self.completed_run()):
            guard.confirm(state, '123')
        self.assertFalse((state/'active.json').exists())
        with self.assertRaises(RuntimeError): guard.start(state,env)
        with self.assertRaises(RuntimeError): guard.start(state,{**env,'GITHUB_RUN_ATTEMPT':'2'})

    def test_failure_missing_mark_retains_claim_and_blocks_different_run(self):
        guard,state,workspace,env = self.fixture()
        guard.start(state,env)
        with self.assertRaises(RuntimeError): guard.finish(state,env)
        self.assertTrue((state/'active.json').exists())
        with self.assertRaises(RuntimeError): guard.start(state,{**env,'GITHUB_RUN_ID':'124'})

    def test_missing_workspace_archive_failure_or_foreign_finish_remains_unresolved(self):
        for failure in ['missing','archive','foreign']:
            with self.subTest(failure=failure):
                guard,state,workspace,env = self.fixture()
                guard.start(state,env); guard.mark_success(state,env)
                if failure == 'missing':
                    workspace.rmdir()
                    with self.assertRaises(RuntimeError): guard.finish(state,env)
                elif failure == 'foreign':
                    with self.assertRaises(RuntimeError): guard.finish(state,{**env,'GITHUB_RUN_ID':'124'})
                else:
                    with patch.object(guard,'archive_artifacts',side_effect=OSError('disk full')):
                        with self.assertRaises(OSError): guard.finish(state,env)
                self.assertTrue((state/'active.json').exists())

    def test_smoke_manual_main_allowed_schedule_denied(self):
        guard,state,workspace,env = self.fixture()
        smoke = {**env,'GITHUB_WORKFLOW':'YouTube Local Hermes Smoke','GITHUB_JOB':'inference-smoke',
                 'GITHUB_WORKFLOW_REF':'zeynelgun-afk/yt-stock-automation/.github/workflows/local-hermes-smoke.yml@refs/heads/main',
                 'GITHUB_EVENT_NAME':'workflow_dispatch'}
        guard.validate_context(smoke,state)
        with self.assertRaises(RuntimeError): guard.validate_context({**smoke,'GITHUB_EVENT_NAME':'schedule'},state)

    def test_unresolved_delivery_prevents_job_success_and_next_job(self):
        import sqlite3
        from delivery_claims import DeliveryClaims
        guard,state,workspace,env = self.fixture()
        guard.start(state,env)
        claims = DeliveryClaims(state.parent/'delivery.sqlite')
        claims.start('comment',['channel:parent'])
        with self.assertRaises(RuntimeError): guard.mark_success(state,env)
        with self.assertRaises(RuntimeError): guard.finish(state,env)
        self.assertTrue((state/'active.json').exists())
        # Even an operator-resolved job journal cannot hide a pending delivery.
        (state/'active.json').unlink()
        with self.assertRaises(RuntimeError): guard.start(state,{**env,'GITHUB_RUN_ID':'124'})

    def test_operator_job_reconciliation_keeps_replay_guard_and_records_note(self):
        guard,state,workspace,env = self.fixture()
        guard.start(state,env)
        with self.assertRaises(RuntimeError): guard.finish(state,env)
        with self.assertRaises(RuntimeError): guard.reconcile(state,'123','')
        guard.reconcile(state,'123','Operator inspected archive and reconciled all external side effects')
        self.assertTrue((state/'123-reconciliation.json').exists())
        self.assertFalse((state/'active.json').exists())
        with self.assertRaises(RuntimeError): guard.start(state,env)
        guard.start(state,{**env,'GITHUB_RUN_ID':'124'})

    def test_crash_after_first_start_write_leaves_durable_receipt_and_forbids_replay(self):
        guard, state, workspace, env = self.fixture()
        write = guard.atomic_json
        writes = []
        def interrupted(path, data):
            write(path, data)
            writes.append(path.name)
            raise OSError('interrupted after first durable journal write')
        with patch.object(guard, 'atomic_json', side_effect=interrupted):
            with self.assertRaises(OSError): guard.start(state, env)
        self.assertEqual(writes, ['123.json'])
        self.assertFalse((state/'active.json').exists())
        receipt = json.loads((state/'123.json').read_text())
        self.assertEqual(receipt['sha'], SHA)
        with self.assertRaisesRegex(RuntimeError, 'replay forbidden'): guard.start(state, env)

    def test_legacy_active_only_reconciliation_restores_original_receipt_before_clear(self):
        guard, state, workspace, env = self.fixture()
        guard.start(state, env)
        original = json.loads((state/'active.json').read_text())
        (state/'123.json').unlink()
        guard.archive_artifacts(state, workspace, '123')
        guard.reconcile(state, '123', 'Operator inspected original interrupted run evidence')
        self.assertTrue((state/'123.json').exists())
        self.assertEqual(json.loads((state/'123.json').read_text()), original)
        self.assertFalse((state/'active.json').exists())
        with self.assertRaisesRegex(RuntimeError, 'replay forbidden'): guard.start(state, env)

    def test_reconciliation_receipt_write_interruption_retains_active_and_replay_guard(self):
        guard, state, workspace, env = self.fixture()
        guard.start(state, env)
        original = json.loads((state/'active.json').read_text())
        (state/'123.json').unlink()
        guard.archive_artifacts(state, workspace, '123')
        write = guard.atomic_json
        def interrupted(path, data):
            write(path, data)
            raise OSError('interrupted after first reconciliation journal write')
        with patch.object(guard, 'atomic_json', side_effect=interrupted):
            with self.assertRaises(OSError):
                guard.reconcile(state, '123', 'Operator inspected original interrupted run evidence')
        self.assertTrue((state/'123.json').exists())
        self.assertEqual(json.loads((state/'123.json').read_text()), original)
        self.assertTrue((state/'active.json').exists())
        guard.reconcile(state, '123', 'Operator inspected original interrupted run evidence')
        with self.assertRaisesRegex(RuntimeError, 'replay forbidden'): guard.start(state, env)

    def test_reconciliation_conflicting_receipt_fails_closed_without_overwrite(self):
        for key, value in [('run_id', '124'), ('attempt', '2'), ('repository', 'other/repo'),
                           ('workflow_path', '.github/workflows/other.yml'), ('workflow', 'Other'),
                           ('job', 'other'), ('sha', 'b'*40), ('started_at', 'other')]:
            with self.subTest(key=key):
                guard, state, workspace, env = self.fixture()
                guard.start(state, env)
                receipt = state/'123.json'
                conflicting = json.loads(receipt.read_text()) | {key: value}
                guard.atomic_json(receipt, conflicting)
                before = receipt.read_bytes()
                guard.archive_artifacts(state, workspace, '123')
                with self.assertRaisesRegex(RuntimeError, 'Conflicting run receipt'):
                    guard.reconcile(state, '123', 'Operator inspected original interrupted run evidence')
                self.assertEqual(receipt.read_bytes(), before)
                self.assertTrue((state/'active.json').exists())
                self.assertFalse((state/'123-reconciliation.json').exists())

    def test_start_receipt_failure_never_leaves_active_without_tombstone(self):
        guard, state, workspace, env = self.fixture()
        write = guard.atomic_json
        def interrupt(path, data):
            if path.name == '123.json':
                raise OSError('interrupted receipt write')
            write(path, data)
        with patch.object(guard, 'atomic_json', side_effect=interrupt):
            with self.assertRaises(OSError): guard.start(state, env)
        self.assertFalse((state/'active.json').exists())

    def test_start_active_partial_write_retains_receipt_and_rejects_replay(self):
        for persisted in [False, True]:
            with self.subTest(persisted=persisted):
                guard, state, workspace, env = self.fixture()
                write = guard.atomic_json
                def interrupt(path, data):
                    if path.name == 'active.json':
                        if persisted: write(path, data)
                        raise OSError('interrupted active write')
                    write(path, data)
                with patch.object(guard, 'atomic_json', side_effect=interrupt):
                    with self.assertRaises(OSError): guard.start(state, env)
                self.assertTrue((state/'123.json').exists())
                with self.assertRaisesRegex(RuntimeError, 'replay forbidden'): guard.start(state, env)
                if persisted:
                    with self.assertRaises(RuntimeError): guard.start(state, {**env, 'GITHUB_RUN_ID':'124'})

    def legacy_interrupted(self):
        guard, state, workspace, env = self.fixture()
        guard.start(state, env)
        # Legacy crash snapshot: active was durable before the receipt write.
        original = (state/'123.json').read_bytes()
        (state/'123.json').unlink()
        guard.archive_artifacts(state, workspace, '123')
        return guard, state, workspace, env, original

    def test_reconciliation_restores_legacy_missing_receipt_before_clear(self):
        guard, state, workspace, env, original = self.legacy_interrupted()
        guard.reconcile(state, '123', 'Operator inspected preserved interrupted workspace evidence')
        self.assertEqual(json.loads((state/'123.json').read_text()), json.loads(original))
        self.assertFalse((state/'active.json').exists())
        with self.assertRaisesRegex(RuntimeError, 'replay forbidden'): guard.start(state, env)

    def test_reconciliation_partial_writes_retain_quarantine_and_receipt(self):
        for target in ['123.json', '123-reconciliation.json']:
            for persisted in [False, True]:
                with self.subTest(target=target, persisted=persisted):
                    guard, state, workspace, env, original = self.legacy_interrupted()
                    write = guard.atomic_json
                    def interrupt(path, data):
                        if path.name == target:
                            if persisted: write(path, data)
                            raise OSError('interrupted reconciliation write')
                        write(path, data)
                    with patch.object(guard, 'atomic_json', side_effect=interrupt):
                        with self.assertRaises(OSError):
                            guard.reconcile(state, '123', 'Operator inspected preserved interrupted workspace evidence')
                    self.assertTrue((state/'active.json').exists())
                    with self.assertRaises(RuntimeError): guard.start(state, env)
                    with self.assertRaises(RuntimeError): guard.start(state, {**env, 'GITHUB_RUN_ID':'124'})
                    guard.reconcile(state, '123', 'Operator inspected preserved interrupted workspace evidence')
                    self.assertEqual(json.loads((state/'123.json').read_text()), json.loads(original))
                    with self.assertRaises(RuntimeError): guard.start(state, env)

    def test_reconciliation_preserves_original_receipt_and_delivery_quarantine(self):
        from delivery_claims import DeliveryClaims
        guard, state, workspace, env = self.fixture()
        guard.start(state, env)
        original = (state/'123.json').read_bytes()
        guard.archive_artifacts(state, workspace, '123')
        DeliveryClaims(state.parent/'delivery.sqlite').start('comment', ['channel:parent'])
        with self.assertRaises(RuntimeError):
            guard.reconcile(state, '123', 'Operator inspected preserved interrupted workspace evidence')
        self.assertTrue((state/'active.json').exists())
        self.assertEqual((state/'123.json').read_bytes(), original)
        # Independently verify receipt preservation without unresolved deliveries.
        guard, state, workspace, env = self.fixture()
        guard.start(state, env)
        original = (state/'123.json').read_bytes()
        guard.archive_artifacts(state, workspace, '123')
        guard.reconcile(state, '123', 'Operator inspected preserved interrupted workspace evidence')
        self.assertEqual((state/'123.json').read_bytes(), original)
        with self.assertRaises(RuntimeError): guard.start(state, env)

    def test_parent_symlink_never_archives_credentials(self):
        guard,state,workspace,env = self.fixture()
        outside = state/'private'; outside.mkdir(); (outside/'editorial_selection.json').write_text('credential')
        (workspace/'output').symlink_to(outside, target_is_directory=True)
        guard.start(state,env); guard.mark_success(state,env); guard.finish(state,env)
        with tarfile.open(next(state.glob('*.tar.gz'))) as tar: self.assertEqual(tar.getnames(), [])
