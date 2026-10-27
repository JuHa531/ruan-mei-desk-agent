"""Regression checks; all writable data stays in temporary directories."""
import concurrent.futures
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / p) for p in ('app', 'voice')]
import agent_server as agent
import tts_server as tts
import office_tools as office
import asr_server as asr


class Regressions(unittest.TestCase):
    def test_music_commands_do_not_become_song_names(self):
        for text, action in [('帮我放点音乐', 'play'), ('换一首', 'next'), ('暂停音乐', 'pause'),
                             ('我的听歌习惯', 'taste'), ('我最近都听了什么', 'taste')]:
            self.assertEqual(agent.parse_music_command(text), action)
            self.assertIsNone(agent.parse_music_request(text))
        self.assertIsNone(agent.parse_music_command('记住我爱听周杰伦'))
        self.assertEqual(agent.parse_music_request('播放周杰伦的晴天'), ('song', '周杰伦 晴天', '晴天'))

    def test_tools_follow_context_and_have_file_access(self):
        names = lambda q, h=None: {t['function']['name'] for t in agent.select_tools(q, h)}
        self.assertIn('make_dayplan', names('帮我安排一下明天'))
        self.assertIn('edit_video', names('把刚才那段剪短一点'))
        self.assertTrue({'see_image', 'list_dir'} <= names('读取图片'))
        self.assertIn('edit_video', names('继续', [{'role':'user', 'content':'剪辑这个视频'}]))
        self.assertEqual(names('你好'), set())

    def test_listening_records_are_atomic_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(agent, 'LISTEN_FILE', os.path.join(tmp, 'listen.json')):
            with concurrent.futures.ThreadPoolExecutor(8) as pool:
                list(pool.map(lambda _: agent.note_playing('同一首', '歌手'), range(30)))
            data = agent._load_listen()
            self.assertEqual(data['tracks'][0]['plays'], 1)
            self.assertEqual(data['tracks'][0]['source'], 'QQMusic')
            agent.note_playing('第二首', '歌手')
            agent.note_playing('同一首', '歌手')
            self.assertEqual(agent._load_listen()['tracks'][0]['plays'], 2)

    def test_habit_record_and_recall(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(agent,'HABITS_FILE',str(Path(tmp)/'habits.md')):
            result=agent.exec_tool('remember',{'text':'测试时晚上十一点睡觉','section':'作息'},tmp)
            self.assertNotIn('[工具出错]',result)
            result=agent.exec_tool('recall',{},tmp)
            self.assertIn('测试时晚上十一点睡觉',result)

    def test_speed_and_truncation_estimation(self):
        output = io.BytesIO()
        with wave.open(output, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b'\x00\x00' * 16000 * 2)
        self.assertTrue(tts.looks_truncated(output.getvalue(), '这是一段明显应该说得更长的中文测试文本。'))
        self.assertFalse(tts.looks_truncated(output.getvalue(), 'Hello, Python and JSON!'))

    def test_android_target_selection(self):
        with patch.object(agent, 'adb_run', return_value=(0, 'List of devices attached\nphone device\ntablet device\n', '')):
            with self.assertRaisesRegex(ValueError, '多台'):
                agent.select_android_serial()
            self.assertEqual(agent.select_android_serial('tablet'), 'tablet')
        with patch.object(agent, 'adb_run', return_value=(0, '* daemon started successfully\nList of devices attached\n', '')):
            self.assertIn('没有连上', agent.adb_devices())
            with self.assertRaisesRegex(ValueError, '没有可用设备'):
                agent.select_android_serial()

    def test_tts_rejects_long_silence_and_clipping(self):
        import math
        import struct
        def wav(values):
            output=io.BytesIO()
            with wave.open(output,'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
                w.writeframes(struct.pack('<%dh' % len(values),*values))
            return output.getvalue()
        # A duration-only check accepts 26 seconds of silence for a short sentence.
        self.assertEqual(tts.wav_quality_issue(wav([0]*16000*26),'你好。'),'近乎静音')
        self.assertEqual(tts.wav_quality_issue(wav([32767,-32768]*8000),'你好。'),'严重削波')
        voice=[int(6000*math.sin(2*math.pi*220*i/16000)) for i in range(16000)]
        self.assertIsNone(tts.wav_quality_issue(wav(voice),'你好。'))
        self.assertEqual(tts.wav_quality_issue(b'broken','你好。'),'无效 WAV')

    def test_tts_http_retries_silent_result_and_rejects_repeated_failure(self):
        import math
        import struct
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer
        def wav(values):
            out=io.BytesIO()
            with wave.open(out,'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
                w.writeframes(struct.pack('<%dh' % len(values),*values))
            return out.getvalue()
        silent=wav([0]*16000)
        valid=wav([int(6000*math.sin(2*math.pi*220*i/16000)) for i in range(16000)])
        class TestHandler(tts.Handler):
            cfg={'backend':{'base_url':'http://unused'},'voices':{'test':{}},'default_voice':'test','max_retry':2}
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:%d/v1/audio/speech' % server.server_port
        request=lambda:urllib.request.Request(url,data=b'{"input":"Hello"}',headers={'Content-Type':'application/json'})
        try:
            with patch.object(tts,'build_request',return_value={}),patch.object(tts,'use_post_speed',return_value=False):
                with patch.object(tts,'call_backend_retry',side_effect=[silent,valid]) as backend:
                    with urllib.request.urlopen(request(),timeout=5) as r:
                        self.assertEqual(r.read(),valid)
                    self.assertEqual(backend.call_count,2)
                    self.assertEqual(backend.call_args.args[1]['seed'],-1)
                with patch.object(tts,'call_backend_retry',return_value=silent):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request(),timeout=5)
                    self.assertEqual(error.exception.code,502)
        finally:
            server.shutdown();server.server_close();thread.join(5)

    def test_image_attachment_history_is_text_for_chat_model(self):
        original={'role':'user','content':'看图','images':['attachments/test.jpg']}
        messages,_=agent.trim_history([original,{'role':'user','content':'谢谢'}],1000)
        self.assertNotIn('images',messages[0])
        self.assertIn('attachments/test.jpg',messages[0]['content'])
        self.assertIn('images',original)

    def test_video_validation_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'source.mp4'; src.write_bytes(b'preserve')
            result = office.edit_video('trim', [str(src)], str(src), start='0', end='1')
            self.assertIn('不能与输入相同', result)
            self.assertEqual(src.read_bytes(), b'preserve')
            result = office.edit_video('trim', [str(src)], str(Path(tmp)/'out.mp4'), start='2', end='1')
            self.assertIn('结束时间必须大于', result)

    def test_silent_video_can_change_speed(self):
        if not office.FFMPEG or not office.FFPROBE:
            self.skipTest('FFmpeg / ffprobe unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = str(Path(tmp)/'silent.mp4'), str(Path(tmp)/'fast.mp4')
            rc, log = office._run_ffmpeg(['-f','lavfi','-i','color=c=blue:s=160x90:r=30',
                                        '-t','2','-an','-c:v','libx264',src])
            self.assertEqual(rc,0,log)
            result = office.edit_video('speed',[src],dst,speed='2')
            self.assertNotIn('[工具出错]',result)
            self.assertAlmostEqual(office._probe(dst)['duration'],1,delta=.15)
            self.assertFalse(office._has_audio(dst))

    def test_asr_normalizes_wav_and_cleans_temporary_file(self):
        if not os.path.isfile(asr.FFMPEG):
            self.skipTest('FFmpeg unavailable')
        audio=io.BytesIO()
        with wave.open(audio,'wb') as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
            w.writeframes(b'\x00\x00' * 48000 * 2)
        seen=[]
        class FakeModel:
            def generate(self,path,**kwargs):
                with wave.open(path) as w:
                    if w.getframerate()!=16000 or w.getnchannels()!=1:
                        raise AssertionError('Audio was not normalized')
                seen.append(path)
                return [{'text':'<|zh|>测试'}]
        with patch.object(asr,'get_model',return_value=FakeModel()):
            self.assertEqual(asr.transcribe(audio.getvalue(),'wav'),'测试')
        self.assertFalse(os.path.exists(seen[0]))


    def test_role_cadence_preserves_words_and_quoted_titles(self):
        text='亲爱的，我查了下。《你为什么不说话？》已经加入播放列表。我们可以慢慢听。'
        segmented=tts.role_speech_segments(text)
        self.assertEqual(segmented.replace('\n',''),text)
        self.assertIn('《你为什么不说话？》',segmented)
        self.assertTrue(segmented.splitlines()[0].endswith('。'))
        long='亲爱的，'+('这是一段较长的说明，'*12)+'现在已经说完。'
        chunks=tts.role_speech_segments(long).splitlines()
        self.assertEqual(''.join(chunks),long)
        self.assertTrue(all(len(part)<=48 for part in chunks))
        opening='亲爱的，不必着急。手边这些事，我替你看着。'
        self.assertEqual(tts.role_speech_segments(opening),opening,
                         'keep a short address with its sentence context')
        self.assertEqual(tts.role_speech_segments('亲爱的。'), '亲爱的。',
                         'a short complete reply must still be spoken')
        tail='今天先把已经列好的安排逐项核对，然后再决定下一步。晚安。'
        self.assertNotIn('\n晚安。',tts.role_speech_segments(tail),
                         'do not leave a tiny trailing segment when it fits')
        cfg={'backend':{'type':'gpt_sovits'}}
        voice={'speed':.86,'speed_mode':'native','post_filter':'','ref_audio_path':'local.wav','text_split_method':'role_sentences'}
        payload=tts.build_gptsovits_payload(cfg,voice,text,1,'wav')
        self.assertEqual(payload['speed_factor'],.86)
        self.assertEqual(payload['text_split_method'],'cut0')
        self.assertEqual(payload['text'],segmented)
        self.assertFalse(tts.use_post_speed(cfg,voice,'wav'))

    def test_pause_spacing_preserves_every_original_spoken_sample(self):
        import array
        rate=16000
        values=[6000]*(rate//2)+[0]*(rate//5)+[-7000]*(rate*3//5)+[0]*(rate*4//5)+[8000]*(rate*3//5)
        def encode(samples):
            output=io.BytesIO()
            with wave.open(output,'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
                w.writeframes(array.array('h',samples).tobytes())
            return output.getvalue()
        original=encode(values)
        padded=tts.space_speech_pauses(original,'亲爱的，不必着急。',.12,.70)
        with wave.open(io.BytesIO(padded)) as w:
            result=array.array('h',w.readframes(w.getnframes()))
        self.assertEqual([v for v in result if v],[v for v in values if v],
                         'pause insertion must not change any spoken sample')
        runs=[];start=None
        for i,value in enumerate(list(result)+[1]):
            if value==0 and start is None:start=i
            elif value!=0 and start is not None:
                runs.append((i-start)/rate);start=None
        self.assertAlmostEqual(runs[0],.70,places=3)
        self.assertAlmostEqual(runs[1],.92,places=3)
        self.assertAlmostEqual(tts.wav_duration(padded)-tts.wav_duration(original),.62,places=3)
        self.assertEqual(tts.space_speech_pauses(original,'亲爱的，',0,0),original)
        plain=tts.space_speech_pauses(original,'今天，不必着急。',.12,.70)
        self.assertAlmostEqual(tts.wav_duration(plain)-tts.wav_duration(original),.24,places=3)

    def test_pause_spacing_leaves_unreliable_and_unsupported_audio_alone(self):
        import array
        def wav(channels,values):
            output=io.BytesIO()
            with wave.open(output,'wb') as w:
                w.setnchannels(channels);w.setsampwidth(2);w.setframerate(16000)
                w.writeframes(array.array('h',values).tobytes())
            return output.getvalue()
        for data in (b'broken',wav(2,[0]*32000),wav(1,[3000]*16000),
                     wav(1,[0]*8000+[3000]*16000+[0]*8000),
                     wav(1,[3000]*8000+[0]*1600+[3000]*8000)):
            self.assertEqual(tts.space_speech_pauses(data,'亲爱的，',.12,.70),data)

    def test_custom_stickers_survive_folder_import(self):
        import import_asset_folders as assets
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'custom.png').write_bytes(b'image')
            (root/'stickers.custom.json').write_text(json.dumps([
                {'id':101,'file':'assets/custom.png','mood':'倾听'},
                {'id':102,'file':'assets/missing.png'},
                {'id':103,'file':'assets/../outside.png'}]),encoding='utf-8')
            merged=assets.merge_custom_stickers([{'id':1,'file':'assets/original.jpg'}],tmp)
            self.assertEqual([item['id'] for item in merged],[1,101])
            self.assertEqual(len(assets.merge_custom_stickers(merged,tmp)),2)

if __name__ == '__main__':
    unittest.main()
