"""No paid API calls; verify credential storage and multi-turn wire formats."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import model_api as api


class ModelAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = api.Settings(Path(self.temp.name) / 'settings.json')
        self.req = {'provider': 'openai', 'base_url': 'https://api.openai.com/v1',
                    'model': 'test-model', 'api_key': 'test-secret-not-real'}

    def test_encrypted_persistence_and_public_redaction(self):
        public = self.store.save(self.req)
        self.assertNotIn('test-secret', self.store.path.read_text())
        self.assertNotIn('secret', json.dumps(public))
        self.assertTrue(public['profiles']['openai']['has_key'])
        self.assertEqual(api.Settings(self.store.path).snapshot()['api_key'], self.req['api_key'])

    def test_blank_retains_clear_removes_and_switch_preserves(self):
        self.store.save(self.req)
        self.store.save(dict(self.req, api_key=''))
        self.assertEqual(self.store.snapshot()['api_key'], self.req['api_key'])
        self.store.save({'provider': 'local'})
        self.assertTrue(self.store.public()['profiles']['openai']['has_key'])
        public = self.store.save(dict(self.req, api_key='', clear_key=True))
        self.assertFalse(public['profiles']['openai']['has_key'])
        self.assertEqual(public['active'], 'local')

    def test_invalid_save_is_atomic_and_changed_host_needs_new_key(self):
        self.store.save(self.req)
        before = self.store.path.read_bytes()
        for url in ('http://example.com', 'https://user:pass@example.com',
                    'https://example.com?key=secret', 'https://example.com/chat/completions'):
            with self.assertRaises(ValueError):
                self.store.save(dict(self.req, base_url=url))
        with self.assertRaises(ValueError):
            self.store.save(dict(self.req, base_url='https://elsewhere.example/v1', api_key=''))
        self.assertEqual(before, self.store.path.read_bytes())

    def test_openai_and_deepseek_tool_roundtrip(self):
        for provider in ('openai', 'deepseek', 'compatible'):
            p = {'provider': provider, 'base_url': 'https://example.com/v1', 'model': 'test', 'api_key': 'secret'}
            tool = {'id': 'call-1', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path":"a"}'}}
            raw = {'choices': [{'message': {'role': 'assistant', 'content': None,
                                           'reasoning_content': 'private reasoning', 'tool_calls': [tool]}}]}
            payload = {'messages': [{'role': 'system', 'content': 'persona'}, {'role': 'user', 'content': 'read'}]}
            with patch.object(api, 'request_json', return_value=raw):
                msg = api.cloud_chat(p, payload)['message']
            self.assertEqual(msg['tool_calls'][0]['function']['arguments'], {'path': 'a'})
            payload['messages'] += [msg, {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'actual file'}]
            with patch.object(api, 'request_json', return_value={'choices': [{'message': {'role': 'assistant', 'content': 'done'}}]}) as send:
                api.cloud_chat(p, payload)
                wire = send.call_args.args[1]
            self.assertEqual(wire['messages'][-1]['tool_call_id'], 'call-1')
            self.assertEqual(wire['messages'][-2]['reasoning_content'], 'private reasoning')
            self.assertEqual(wire['messages'][0]['content'], 'persona')
            self.assertIsInstance(wire['messages'][-2]['tool_calls'][0]['function']['arguments'], str)

    def test_claude_parallel_tool_result_and_content_preserved(self):
        p = {'provider': 'claude', 'base_url': 'https://api.anthropic.com/v1', 'model': 'test', 'api_key': 'secret'}
        blocks = [{'type': 'text', 'text': 'checking'},
                  {'type': 'tool_use', 'id': 'a', 'name': 'read_file', 'input': {'path': 'a'}},
                  {'type': 'tool_use', 'id': 'b', 'name': 'read_file', 'input': {'path': 'b'}}]
        payload = {'messages': [{'role': 'system', 'content': 'persona'}, {'role': 'user', 'content': 'read'}]}
        with patch.object(api, 'request_json', return_value={'content': blocks}):
            msg = api.cloud_chat(p, payload)['message']
        payload['messages'] += [msg, {'role': 'tool', 'tool_call_id': 'a', 'content': 'A'},
                               {'role': 'tool', 'tool_call_id': 'b', 'content': 'B'}]
        with patch.object(api, 'request_json', return_value={'content': [{'type': 'text', 'text': 'done'}]}) as send:
            api.cloud_chat(p, payload)
            wire = send.call_args.args[1]
        self.assertEqual(wire['system'], 'persona')
        self.assertEqual(wire['messages'][-2]['content'], blocks)
        self.assertEqual([b['tool_use_id'] for b in wire['messages'][-1]['content']], ['a', 'b'])

    def test_malformed_tool_arguments_are_not_executed(self):
        p = {'provider': 'openai', 'base_url': 'https://example.com', 'model': 'test', 'api_key': 'secret'}
        for args in ('{broken', '[]'):
            raw = {'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': 'a', 'function': {'name': 'run_cmd', 'arguments': args}}]}}]}
            with patch.object(api, 'request_json', return_value=raw), self.assertRaises(RuntimeError):
                api.cloud_chat(p, {'messages': []})

    def test_redirect_is_refused(self):
        self.assertIsNone(api.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))

    def test_http_settings_test_and_agent_tool_loop(self):
        import agent_server as agent
        from http.server import ThreadingHTTPServer
        class Handler(agent.Handler):
            cfg = {'model': 'ruanmei', 'ollama': 'http://127.0.0.1:11434', 'workdir': self.temp.name}
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def post(path, body):
            req = urllib.request.Request('http://127.0.0.1:%d%s' % (server.server_port, path),
                  data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read().decode()
        with patch.object(agent, 'MODEL_SETTINGS', self.store):
            public = json.loads(post('/api/model-settings', self.req))
            self.assertEqual(public['active'], 'openai')
            self.assertNotIn('secret', json.dumps(public))
            answer = {'choices': [{'message': {'role': 'assistant', 'content': 'OK'}}]}
            with patch.object(api, 'request_json', return_value=answer) as send:
                self.assertTrue(json.loads(post('/api/model-test', dict(self.req, api_key='')))['ok'])
                self.assertEqual(send.call_args.args[1]['messages'], [{'role': 'user', 'content': 'Reply with OK only.'}])
            tool = {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'call-1', 'type': 'function', 'function': {'name': 'list_dir', 'arguments': '{"path":"."}'}}]}}]}
            answer = {'choices': [{'message': {'role': 'assistant', 'content': '目录里有一份说明文件。'}}]}
            with patch.object(api, 'request_json', side_effect=[tool, answer]) as send, \
                    patch.object(agent, 'exec_tool', return_value='README.md') as execute:
                events = [json.loads(line) for line in post('/api/agent', {'messages': [
                    {'role': 'user', 'content': '列出当前目录文件'}]}).splitlines()]
                self.assertFalse([e for e in events if e['type'] == 'error'], events)
                self.assertTrue([e for e in events if e['type'] == 'text'], events)
                execute.assert_called_once()
                wire = send.call_args.args[1]
                self.assertEqual(wire['messages'][-1]['tool_call_id'], 'call-1')
                self.assertIn('阮', wire['messages'][0]['content'])


if __name__ == '__main__':
    unittest.main()
