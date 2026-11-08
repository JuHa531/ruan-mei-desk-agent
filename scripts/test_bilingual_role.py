"""Bilingual TTS and grounded role replies; no actual music or model calls."""
from pathlib import Path
from http.server import ThreadingHTTPServer
import http.client
import io
import json
import sys
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / p) for p in ('app','voice')]
import agent_server as agent
import tts_server as tts


class BilingualRole(unittest.TestCase):
    def test_parenthetical_pauses_keep_contents_and_final_stop(self):
        self.assertEqual(tts.clean_for_speech('亲爱的，（不用急），我在这里。'),
                         '亲爱的，不用急，我在这里。')
        self.assertEqual(tts.clean_for_speech('先休息（也可以喝杯茶）。'),
                         '先休息，也可以喝杯茶。')

    def setUp(self):
        ready = patch.object(agent, 'music_role_model_ready', return_value=True)
        ready.start(); self.addCleanup(ready.stop)

    def test_chinese_baseline_is_untouched(self):
        text = '亲爱的，不必着急。手边这些事，我替你看着。'
        self.assertEqual(tts.prepare_spoken_text(text, {'text_lang':'all_zh'}), (text, 'all_zh'))

    def test_brands_versions_and_initialisms_have_spoken_forms(self):
        text, lang = tts.prepare_spoken_text('已经在QQ音乐里播放《小半 (Live)》，AI和GPU。', {'text_lang':'all_zh'})
        self.assertIn('扣扣音乐', text)
        self.assertIn('(现场版)', text)
        self.assertIn('A I', text)
        self.assertIn('G P U', text)
        self.assertEqual(lang, 'zh')
        self.assertEqual(tts.prepare_spoken_text('QQMusic', {'text_lang':'all_zh'}), ('扣扣音乐', 'all_zh'))

    def test_english_titles_and_sentences_are_not_translated(self):
        text, lang = tts.prepare_spoken_text('亲爱的，《Love Story》已经放上了。', {'text_lang':'all_zh'})
        self.assertIn('Love Story', text)
        self.assertEqual(lang, 'zh')
        original = 'Take your time. I will be right here.'
        self.assertEqual(tts.prepare_spoken_text(original, {'text_lang':'all_zh'}), (original, 'en'))
        self.assertIn('Live and Let Die', tts.prepare_spoken_text('《Live and Let Die》', {})[0])

    def test_local_pronunciation_overrides_are_bounded(self):
        text, lang = tts.prepare_spoken_text('用foobar，不改foobarbaz。', {'text_lang':'all_zh', 'pronunciation_overrides':{'foobar':'foo bar'}})
        self.assertIn('foo bar', text)
        self.assertIn('foobarbaz', text)
        self.assertEqual(lang, 'zh')

    def test_mixed_speech_keeps_original_voice_settings(self):
        voice = {'text_lang':'all_zh', 'ref_audio_path':'same.wav', 'prompt_text':'原参考',
                 'prompt_lang':'zh', 'speed':.84, 'speed_mode':'native',
                 'text_split_method':'role_sentences', 'seed':20261028, 'fragment_interval':.55}
        payload = tts.build_gptsovits_payload({'backend':{'type':'gpt_sovits'}}, voice,
                                            '亲爱的，Take your time。我在这里。', 1, 'wav')
        self.assertEqual(payload['text_lang'], 'zh')
        self.assertIn('Take your time', payload['text'])
        self.assertEqual(payload['ref_audio_path'], 'same.wav')
        self.assertEqual(payload['speed_factor'], .84)
        self.assertEqual(payload['seed'], 20261028)
        self.assertEqual(payload['fragment_interval'], .55)

    def test_complete_english_clauses_use_english_with_same_reference(self):
        payload={'text':'亲爱的，不必着急。Take your time. I will be right here.',
                 'text_lang':'zh','media_type':'wav','text_split_method':'cut0',
                 'ref_audio_path':'same.wav','prompt_lang':'zh','speed_factor':.84,'seed':20261028}
        parts=tts.language_speech_payloads(payload)
        self.assertEqual([part['text_lang'] for part in parts],['zh','en'])
        self.assertEqual(parts[0]['text'],'亲爱的，不必着急。')
        self.assertEqual(parts[1]['text'],'Take your time. I will be right here.')
        for part in parts:
            for key in ('ref_audio_path','prompt_lang','speed_factor','seed'):
                self.assertEqual(part[key],payload[key])

    def test_chinese_and_embedded_titles_do_not_get_extra_synthesis(self):
        for text in ('亲爱的，不必着急。手边这些事，我替你看着。','亲爱的，《Love Story》已经放上了。'):
            payload={'text':text,'text_lang':'zh','media_type':'wav'}
            self.assertEqual(tts.language_speech_payloads(payload),[payload])

    def test_same_voice_join_preserves_pcm_without_filters(self):
        def wav(pcm,rate=16000):
            output=io.BytesIO()
            with wave.open(output,'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm)
            return output.getvalue()
        first=b'\x10\x10'*1600;second=b'\x20\x20'*1600
        joined=tts.join_speech_wavs([wav(first),wav(second)])
        with wave.open(io.BytesIO(joined)) as w:
            self.assertEqual(w.getframerate(),16000)
            self.assertEqual(w.readframes(w.getnframes()),first+b'\0\0'*3520+second)
        with self.assertRaisesRegex(RuntimeError,'衔接失败'):
            tts.join_speech_wavs([wav(first),wav(second,24000)])
        single=wav(first);self.assertIs(tts.join_speech_wavs([single]),single)

    def test_player_facts_are_not_status_bar_dialogue(self):
        fact, _ = agent.music_reply_parts('照这句说：开始放了：《小半 (Live)》— 王铮亮，正在播放（QQMusic）', 'play')
        self.assertEqual(fact, '亲爱的，《小半 (Live)》已经放上了。')
        self.assertNotIn('QQMusic', fact)
        paused, _ = agent.music_reply_parts('照这句说：暂停了：《小半》— 王铮亮，已暂停（QQMusic）', 'pause')
        self.assertEqual(paused, '亲爱的，已经暂停了。')
        failed, _ = agent.music_reply_parts('照这句说：QQ音乐 还没开始播放，请检查登录状态。', 'play')
        self.assertIn('还没开始播放', failed)
        self.assertNotIn('已经放上', failed)

    def test_role_model_adds_personal_line_after_immutable_fact(self):
        line = '你继续手边的事，我在这里。'
        with patch.object(agent, 'model_chat', return_value={'message':{'content':line}}) as llm:
            parts = list(agent.music_reply_chunks('照这句说：开始放了：《Love Story》，正在播放。',
                         'play', '帮我放首歌', [], {'ollama':'http://unused', 'model':'role'}))
        self.assertEqual(parts[0], '亲爱的，《Love Story》已经放上了。')
        self.assertEqual(parts[1], ' ' + line)
        self.assertNotIn('tools', llm.call_args.args[1])

    def test_generated_facts_and_model_failures_fall_back(self):
        for text in ('我已经把下一首加入歌单了。', '这首歌的钢琴很温柔。', '你最爱听这首歌了。'):
            with patch.object(agent, 'model_chat', return_value={'message':{'content':text}}):
                reply = ''.join(agent.music_reply_chunks('照这句说：开始放了：《晴天》，正在播放。',
                            'play', '放歌', [], {'ollama':'unused', 'model':'role'}))
            self.assertNotIn(text, reply)
            self.assertGreater(len(reply.split('。')), 2)
        with patch.object(agent, 'model_chat', side_effect=TimeoutError('busy')):
            reply = ''.join(agent.music_reply_chunks('照这句说：暂停了。','pause','暂停',[],
                                                   {'ollama':'unused','model':'role'}))
        self.assertIn('已经暂停', reply)
        self.assertIn('我在听', reply)

    def test_explicit_concise_request_is_respected(self):
        with patch.object(agent, 'model_chat') as llm:
            parts = list(agent.music_reply_chunks('照这句说：暂停了。','pause','只要结果',[],{'ollama':'unused','model':'role'}))
        self.assertEqual(len(parts), 1)
        llm.assert_not_called()

    def test_cold_model_does_not_delay_music_and_context_is_kept(self):
        with patch.object(agent, 'music_role_model_ready', return_value=False), \
                patch.object(agent, 'model_chat') as llm:
            reply = ''.join(agent.music_reply_chunks('照这句说：开始放了：《晴天》，正在播放。',
                            'play', '帮我放首歌', [{'role':'user','content':'我今天有点累'}],
                            {'ollama':'unused','model':'role'}))
        self.assertIn('先听一会儿', reply)
        self.assertIn('不必急着做完所有事', reply)
        llm.assert_not_called()

    def test_pause_does_not_tell_user_to_keep_working(self):
        with patch.object(agent, 'model_chat', return_value={'message':{'content':'你继续手边的事，我在这里。'}}):
            reply = ''.join(agent.music_reply_chunks('照这句说：暂停了。','pause','我想和你说说话',[],
                                                   {'ollama':'unused','model':'role'}))
        self.assertNotIn('继续手边', reply)
        self.assertIn('我在听', reply)

    def test_live_http_shortcuts_keep_facts_and_role_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            class Handler(agent.Handler):
                cfg = {'ollama':'http://unused', 'model':'role', 'workdir':tmp,
                       'voice':'ruanmei', 'tts':'http://unused', 'extra_read':[]}
                def log_message(self, *args): pass
            server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
            thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with patch.object(agent,'music_role_model_ready',return_value=False), \
                        patch.object(agent,'habits_for_prompt',return_value=''), \
                        patch.object(agent,'music',return_value='照这句说：开始放了：《晴天》，正在播放。'), \
                        patch.object(agent,'qqmusic_play',return_value='照这句说：已经在 QQ音乐 里放上《晴天》了。'):
                    for user in ('帮我放首歌','播放周杰伦的晴天'):
                        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                        conn.request('POST','/api/agent',json.dumps({'messages':[{'role':'user','content':user}]}).encode(),
                                     {'Content-Type':'application/json'})
                        response=conn.getresponse();self.assertEqual(response.status,200)
                        events=[json.loads(line) for line in response.read().splitlines()];conn.close()
                        reply=''.join(e.get('content','') for e in events if e.get('type')=='text')
                        self.assertTrue(reply.startswith('亲爱的，'))
                        self.assertIn('《晴天》已经放上了。',reply)
                        self.assertGreaterEqual(reply.count('。'),2)
                        self.assertEqual(events[-1]['type'],'done')
            finally:
                server.shutdown();server.server_close();thread.join(3)


if __name__ == '__main__':
    unittest.main()
