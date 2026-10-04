import tests  # enforce the no-real-inference unit-test boundary
from pathlib import Path
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
