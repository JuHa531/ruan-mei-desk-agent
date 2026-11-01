"""Music state and speech dependency regressions, without real playback."""
import contextlib
import http.client
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch
import urllib.error

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / p) for p in ('app', 'voice')]
import agent_server as agent
import tts_server as tts


class Recovery(unittest.TestCase):
    def test_cold_player_waits_for_controls_and_resumes_before_playing_a_playlist(self):
        play = Mock(ControlTypeName='ButtonControl', Name='播放')
        playlist = Mock(ControlTypeName='ButtonControl', Name='播放全部')
        win = object()
        auto = types.SimpleNamespace(UIAutomationInitializerInThread=contextlib.nullcontext)
        with patch.dict(sys.modules, {'uiautomation': auto}), \
                patch.object(agent, '_ensure_qqmusic', return_value=(True, '')), \
                patch.object(agent, '_uia_window', side_effect=[None, None, win]) as window, \
                patch.object(agent, '_uia_walk', return_value=[playlist, play]), \
                patch.object(agent.time, 'sleep'), \
                patch.object(agent, 'music_control', side_effect=[{'STATUS':'Opened'}, {'STATUS':'Playing'}]):
            self.assertEqual(agent._start_music_without_session('play'), '')
        self.assertEqual(window.call_count, 3)
        play.GetInvokePattern.return_value.Invoke.assert_called_once()
        playlist.GetInvokePattern.return_value.Invoke.assert_not_called()

    def test_invoke_exception_after_playback_is_not_failure(self):
        button = Mock(ControlTypeName='ButtonControl', Name='播放全部')
        button.GetInvokePattern.return_value.Invoke.side_effect = RuntimeError('COM provider failed')
        auto = types.SimpleNamespace(UIAutomationInitializerInThread=contextlib.nullcontext)
        with patch.dict(sys.modules, {'uiautomation': auto}), \
                patch.object(agent, '_ensure_qqmusic', return_value=(True, '')), \
                patch.object(agent, '_uia_window', return_value=object()), \
                patch.object(agent, '_uia_walk', return_value=[button]), \
                patch.object(agent.time, 'sleep'), \
                patch.object(agent, 'music_control', side_effect=[{'STATUS':'Opened'}, {'STATUS':'Playing'}]):
            self.assertEqual(agent._start_music_without_session('play'), '')
        button.GetInvokePattern.return_value.Invoke.assert_called_once()

    def test_opened_session_is_recovered_and_recorded(self):
        opened = {'COUNT':'1', 'STATUS':'Opened', 'AFTER_STATUS':'Opened', 'RESULT':'True'}
        playing = {'COUNT':'1', 'STATUS':'Playing', 'TITLE':'测试歌曲', 'ARTIST':'歌手'}
        with patch.object(agent, 'music_control', side_effect=[opened, playing, playing]), \
                patch.object(agent, '_start_music_without_session', return_value='') as start, \
                patch.object(agent, 'note_playing') as note:
            result = agent.music('play')
        start.assert_called_once_with('play')
        self.assertIn('开始放了', result)
        self.assertIn('测试歌曲', result)
        note.assert_called_once_with('测试歌曲', '歌手', None)

    def test_no_false_success_or_raw_com_exception(self):
        opened = {'COUNT':'1', 'STATUS':'Opened', 'AFTER_STATUS':'Opened', 'RESULT':'True'}
        with patch.object(agent, 'music_control', return_value=opened), \
                patch.object(agent, '_start_music_without_session', side_effect=RuntimeError('(-2146233079, None)')):
            result = agent.music('play')
        self.assertIn('还没开始播放', result)
        self.assertNotIn('开始放了', result)
        self.assertNotIn('2146233079', result)

    def test_pause_failure_does_not_announce_success(self):
        playing = {'COUNT':'1', 'STATUS':'Playing', 'AFTER_STATUS':'Playing', 'RESULT':'True'}
        with patch.object(agent, 'music_control', return_value=playing), patch.object(agent, 'note_playing'):
            self.assertIn('没有接受', agent.music('pause'))

    def request_handler(self, handler, method, path, data=None):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            body = json.dumps(data).encode() if data is not None else None
            conn.request(method, path, body, {'Content-Type':'application/json'})
            response = conn.getresponse()
            result = response.status, json.loads(response.read())
            conn.close()
            return result
        finally:
            server.shutdown(); server.server_close(); thread.join(3)

    def test_tts_proxy_preserves_backend_explanation(self):
        class Handler(agent.Handler):
            cfg = {'tts':'http://unused', 'voice':'ruanmei'}
            def log_message(self, *args): pass
        detail = '缺少 averaged_perceptron_tagger_eng'
        def fail(*args, **kwargs):
            raise urllib.error.HTTPError('http://unused', 502, 'failed', {},
                                         io.BytesIO(json.dumps({'error':detail}).encode()))
        with patch.object(agent.urllib.request, 'urlopen', side_effect=fail):
            status, body = self.request_handler(Handler, 'POST', '/api/tts', {'text':'测试', 'voice':'ruanmei:calm'})
        self.assertEqual(status, 502)
        self.assertEqual(body['error'], detail)

    def test_missing_speech_resources_mark_health_unready(self):
        class Handler(tts.Handler):
            cfg = {'backend':{'base_url':'http://unused'}, 'voices':{'test':{}}}
            def log_message(self, *args): pass
        error = urllib.error.HTTPError('http://unused', 503, 'missing resources', {}, io.BytesIO(b'{}'))
        with patch.object(tts.urllib.request, 'urlopen', side_effect=error) as upstream:
            status, body = self.request_handler(Handler, 'GET', '/healthz')
        self.assertEqual(status, 503)
        self.assertFalse(body['ok'])
        upstream.assert_called_once()

    def test_active_synthesis_does_not_look_offline(self):
        class Handler(tts.Handler):
            cfg = {'backend':{'base_url':'http://unused'}, 'voices':{'test':{}}}
            def log_message(self, *args): pass
        with patch.object(tts, '_BACKEND_LAST_OK', time.monotonic()), \
                patch.object(tts, '_BACKEND_LOCK') as lock, \
                patch.object(tts.urllib.request, 'urlopen') as upstream:
            lock.locked.return_value = True
            status, body = self.request_handler(Handler, 'GET', '/healthz')
        self.assertEqual(status, 200)
        self.assertTrue(body['busy'])
        upstream.assert_not_called()


if __name__ == '__main__':
    unittest.main()
