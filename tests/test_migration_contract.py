import tests  # enforce the no-real-inference unit-test boundary
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import os

ROOT = Path(__file__).resolve().parents[1]


class MigrationContractTests(unittest.TestCase):
    def test_production_workflow_ownership_runner_venv_secrets_and_crons(self):
        text = (ROOT/'.github/workflows/youtube_auto.yml').read_text()
        self.assertIn("vars.YT_EXECUTOR == 'local-hermes'", text)
        self.assertIn('runs-on: [yt-hermes]', text)
        self.assertIn('/home/zeynel/.local/share/yt-hermes-runner/venv',text)
        self.assertNotIn('apt-get',text)
        for obsolete in ['OPENROUTER_API_KEY','GEMINI_API_KEY','GROQ_API_KEY','secrets.YOUTUBE_TOKEN_JSON','secrets.YOUTUBE_CLIENT_SECRET_JSON']:
            self.assertNotIn(obsolete,text)
        for secret in ['YT_LOCAL_TOKEN_JSON','YT_LOCAL_CLIENT_SECRET_JSON']: self.assertIn('secrets.'+secret,text)
        self.assertEqual([line.split("'")[1] for line in text.splitlines() if '- cron:' in line],
                         ['30 12 * * 1-5','0 17 * * 1-5','30 0 * * 2-6','35 13 * * 1-5','5 20 * * 1-5','5 21 * * 1-5','0 15 * * 0'])
        self.assertIn('group: yt-pipeline',text)
        self.assertIn('mark-success',text)

    def test_pr_ci_remains_hosted_and_offline(self):
        text = (ROOT/'.github/workflows/checks.yml').read_text()
        self.assertIn('runs-on: ubuntu-latest',text)
        self.assertIn('YT_OFFLINE_TESTS',text)
        self.assertNotIn('yt-hermes',text)

    def test_smoke_main_only_dedicated_runner_no_secrets_no_production(self):
        text = (ROOT/'.github/workflows/local-hermes-smoke.yml').read_text()
        self.assertIn('workflow_dispatch:',text); self.assertNotIn('schedule:',text)
        self.assertIn('runs-on: [yt-hermes]',text)
        self.assertIn("github.ref == 'refs/heads/main'",text)
        self.assertNotIn('secrets.',text)
        self.assertIn('smoke_llm.py',text)
        self.assertNotIn('main_scheduler.py',text)
        self.assertIn('mark-success',text)

    def test_historical_rerun_disabled_under_local_ownership(self):
        text = (ROOT/'.github/workflows/retry_on_infra_failure.yml').read_text()
        self.assertIn("vars.YT_EXECUTOR != 'local-hermes'",text)

    def test_slot_loss_alert_stays_hosted_and_detects_unreached_pipeline(self):
        text = (ROOT/'.github/workflows/alert_on_slot_loss.yml').read_text()
        # Notification credentials must never reach the local runner.
        self.assertIn('runs-on: ubuntu-latest',text)
        self.assertNotIn('runs-on: [yt-hermes]',text)  # comments may name the runner; the selector may not
        self.assertIn('workflows: ["US Stock Market Daily YouTube Automation"]',text)
        for secret in ['TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID']: self.assertIn('secrets.'+secret,text)
        # A pre-job hook rejection leaves "Run Pipeline" skipped, not null, so a
        # `!= null` reachability test would misfile the one silent failure class
        # this workflow exists to catch. Keep the explicit conclusion allowlist.
        self.assertNotIn('.conclusion != null',text)
        self.assertIn('not-reached',text)
        for concluded in ['"success"','"failure"','"cancelled"']:
            self.assertIn('.conclusion == '+concluded,text)

    def test_smoke_uses_only_synthetic_facts_and_both_real_writers(self):
        import smoke_llm
        from script_generator import ScriptGenerator
        from comment_responder import ReplyWriter
        self.assertIn('synthetic',smoke_llm.FACTS.lower())
        self.assertEqual(smoke_llm.ScriptGenerator,ScriptGenerator)
        self.assertEqual(smoke_llm.ReplyWriter,ReplyWriter)
        text = (ROOT/'smoke_llm.py').read_text()
        for unsafe in ['requests','YouTubePublisher','Telegram','data_fetcher','main_scheduler','respond(']:
            self.assertNotIn(unsafe,text)
        # Smoke is never invoked here; mocking inference would invalidate it.

    def test_unit_suite_guard_never_launches_real_inference(self):
        import llm_transport
        with patch.dict(os.environ, {'YT_OFFLINE_TESTS':'1'}), patch('llm_transport.subprocess.run') as run:
            with self.assertRaises(llm_transport.InferenceError): llm_transport.complete([])
            run.assert_not_called()


class CleanStopContractTests(unittest.TestCase):
    """A slot that declines to publish must not wedge the guarded runner.

    A missing intraday quote took the channel off air for eight slots on
    2026-10-22: the abort exited 1, the workflow skipped mark-success, and the
    runner claim stayed unresolved until an operator reconciled it by hand.
    """

    def test_abort_before_publishing_exits_distinctly_from_a_crash(self):
        import main_scheduler
        with patch('main_scheduler.TelegramApprovalBot') as bot:
            bot.return_value.send_text.return_value = True
            with self.assertRaises(SystemExit) as clean:
                main_scheduler.abort_pipeline('no intraday data', clean=True)
            with self.assertRaises(SystemExit) as crash:
                main_scheduler.abort_pipeline('unexpected error')
        self.assertEqual(clean.exception.code, main_scheduler.CLEAN_STOP_EXIT)
        self.assertEqual(crash.exception.code, 1)
        self.assertNotEqual(main_scheduler.CLEAN_STOP_EXIT, 1)
        # The operator is told either way; only the runner claim differs.
        self.assertEqual(bot.return_value.send_text.call_count, 2)

    def test_every_abort_before_the_upload_step_is_a_clean_stop(self):
        source = (ROOT/'main_scheduler.py').read_text()
        upload_at = source.index('yp.upload_video(')
        calls = [(m.start(), m.group()) for m in
                 re.finditer(r'abort_pipeline\([^\n]*\)', source)]
        self.assertTrue(calls)
        for position, call in calls:
            if source[max(0, position - 4):position] == 'def ':
                continue   # the definition itself, not a call site
            if position < upload_at:
                self.assertIn('clean=True', call,
                              f'abort before upload must close the job cleanly: {call}')
            else:
                # After an upload attempt a delivery may be ambiguous; the claim
                # must stay unresolved for an operator rather than auto-close.
                self.assertNotIn('clean=True', call,
                                 f'abort after upload must not auto-close: {call}')

    def test_workflow_lets_a_clean_stop_reach_the_success_marker(self):
        text = (ROOT/'.github/workflows/youtube_auto.yml').read_text()
        self.assertIn('run_pipeline()', text)
        self.assertIn('"75"', text)
        # Production modes route through the wrapper...
        for mode in ('run_pipeline shorts', 'run_pipeline "$MODE"'):
            self.assertIn(mode, text)
        self.assertNotIn('python main_scheduler.py shorts\n', text)
        # ...but event-check keeps its own 0/1/2 contract and must not be wrapped.
        self.assertIn('python main_scheduler.py event-check', text)
        self.assertNotIn('run_pipeline event-check', text)
        # The marker step still gates on success and stays last.
        self.assertIn('mark-success', text)
        self.assertLess(text.index('run_pipeline()'), text.index('mark-success'))
