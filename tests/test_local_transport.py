import tests  # enforce the no-real-inference unit-test boundary
import json
import os
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from script_generator import ScriptGenerator, ScriptGenerationError
from comment_responder import ReplyWriter


def protocol(payload=None):
    return '\n'.join(json.dumps(e) for e in [
        {'type': 'system', 'subtype': 'init', 'model': 'gpt-6-astra', 'session_id': 'fresh'},
        {'type': 'text', 'text': '{}'},
        {'type': 'result', 'exit_code': 0, 'session_id': 'fresh', 'text': json.dumps(payload or {'answer': 'ok'})}])


class TransportTests(unittest.TestCase):
    def setUp(self):
        # Boundary tests mock subprocess or complete, never launch Hermes.
        self.enterContext(patch.dict(os.environ, {'YT_OFFLINE_TESTS': '0'}))

    def test_fixed_subscription_and_fresh_stdin_sanitized_environment(self):
        import llm_transport as t
        dirs = []
        def run(command, **kw):
            self.assertTrue(Path(kw['cwd']).is_dir())
            self.assertEqual(list(Path(kw['cwd']).iterdir()), [])
            dirs.append(kw['cwd'])
            self.assertNotIn('viewer fact', ' '.join(command))
            self.assertIn('viewer fact', kw['input'])
            self.assertEqual(command[1:], ['chat', '--query-file', '-', '--oneshot', '--format',
                'stream-json', '--safe-mode', '--provider', 'openai-codex', '--model',
                'gpt-6-astra', '--toolsets', 'none', '--max-turns', '1', '--run-budget', '180', '--source', 'tool'])
            self.assertEqual(kw['timeout'], 195)
            self.assertNotIn('OPENROUTER_API_KEY', kw['env'])
            self.assertNotIn('YT_LOCAL_TOKEN_JSON', kw['env'])
            self.assertNotIn('HERMES_INFERENCE_PROVIDER', kw['env'])
            return SimpleNamespace(returncode=0, stdout=protocol(), stderr='private')
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'private', 'YT_LOCAL_TOKEN_JSON': 'private',
                                   'HERMES_INFERENCE_PROVIDER': 'paid'}), patch('llm_transport.subprocess.run', side_effect=run):
            for _ in range(2):
                self.assertEqual(json.loads(t.complete([{'role': 'user', 'content': 'viewer fact'}])), {'answer': 'ok'})
        self.assertNotEqual(*dirs)
        self.assertTrue(all(not Path(d).exists() for d in dirs))

    def test_strict_protocol_rejects_tools_unknown_order_duplicates_errors_and_bad_json(self):
        import llm_transport as t
        events = [json.loads(line) for line in protocol().splitlines()]
        invalid = ['noise', '[]', '', protocol() + '\n' + json.dumps(events[-1])]
        for index, updates in [(0, {'model': 'paid'}), (0, {'subtype': 'other'}),
                               (1, {'type': 'tool_use'}), (1, {'type': 'tool_result'}),
                               (1, {'type': 'unknown'}), (2, {'exit_code': 1}),
                               (2, {'exit_code': False}), (2, {'error': 'private'}),
                               (2, {'session_id': ''}), (2, {'text': '```json\n{}\n```'}),
                               (2, {'text': '[]'}), (2, {'text': '{"x":NaN}'}),
                               (2, {'text': '{"x":1,"x":2}'})]:
            copy = [dict(e) for e in events]; copy[index].update(updates)
            invalid.append('\n'.join(json.dumps(e) for e in copy))
        invalid.append('\n'.join(json.dumps(e) for e in reversed(events)))
        for output in invalid:
            with self.subTest(output=output), patch('llm_transport.subprocess.run', return_value=SimpleNamespace(
                    returncode=0, stdout=output, stderr='private-secret')):
                with self.assertRaises(t.InferenceError) as error:
                    t.complete([])
                self.assertNotIn('private', str(error.exception))

    def test_json_overflow_and_unrecognized_protocol_metadata_fail_closed(self):
        import llm_transport as t
        with self.assertRaises(ValueError): t.strict_json('{"number":1e999}')
        for index,extra in [(0,{'provider':'paid'}),(1,{'tool_calls':[]}), (2,{'model':'paid'})]:
            events = [json.loads(line) for line in protocol().splitlines()]
            events[index].update(extra)
            with patch('llm_transport.subprocess.run',return_value=SimpleNamespace(
                    returncode=0,stdout='\n'.join(json.dumps(e) for e in events),stderr='')):
                with self.assertRaises(t.InferenceError): t.complete([])

    def test_process_failures_are_sanitized_no_retry(self):
        import llm_transport as t
        for exc in [OSError('private'), subprocess.TimeoutExpired('private', 195)]:
            with patch('llm_transport.subprocess.run', side_effect=exc) as run:
                with self.assertRaises(t.InferenceError) as error:
                    t.complete([])
                self.assertNotIn('private', str(error.exception)); run.assert_called_once()
        with patch('llm_transport.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='private')):
            with self.assertRaises(t.InferenceError): t.complete([])

    def test_all_callers_fixed_pair_and_old_keys_ignored(self):
        import llm_transport as t
        for writer in [ScriptGenerator('private', 'private', 'private'), ReplyWriter('private')]:
            self.assertEqual(writer._providers(), [('openai-codex', 'gpt-6-astra')])
            self.assertNotIn('private', repr(vars(writer)))
            with patch('llm_transport.complete', return_value='{"answer":"ok"}') as complete:
                self.assertEqual(writer._chat('openrouter', 'paid', 'facts'), '{"answer":"ok"}')
                self.assertEqual(complete.call_args.args[0][0]['content'], writer.SYSTEM_MSG)
        with patch('llm_transport.complete', side_effect=t.InferenceError('unavailable')) as complete:
            with self.assertRaises(ScriptGenerationError): ScriptGenerator()._call_llm('facts', 'title')
            complete.assert_called_once()

    def test_reply_uses_same_adapter_and_existing_reply_validation(self):
        text = 'Thanks for watching the explanation. The supplied facts do not establish a cause for that change.'
        with patch('llm_transport.complete', return_value=json.dumps({'action':'reply','language':'en','text':text})) as run:
            self.assertEqual(ReplyWriter().draft('helpful!', {'title':'Example'}, []), text)
            run.assert_called_once()
        with patch('llm_transport.complete', return_value='{"action":"skip","language":"en","text":""}'):
            self.assertIsNone(ReplyWriter().draft('helpful!', {}, []))

    def test_script_json_is_strict_and_correction_limit_preserved(self):
        for raw in ['```json\n{}\n```', '{"full_script":"one\ntwo"}', '{"x":NaN}', '{"x":1,"x":2}']:
            with patch.object(ScriptGenerator, '_chat', return_value=raw):
                with self.assertRaises(ScriptGenerationError): ScriptGenerator()._call_llm('facts', 'title')
        with patch.object(ScriptGenerator, '_chat', return_value='{"title":"Valid","full_script":"short"}') as chat:
            with self.assertRaises(ScriptGenerationError): ScriptGenerator()._call_llm('facts','title',2,3)
            self.assertEqual(chat.call_count, 3)
