"""English routing must not change Chinese or break synthesis on worker failure."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'voice'))
import english_client
import english_worker
import tts_server as tts


class EnglishRoute(unittest.TestCase):
    def setUp(self):
        self.cfg={'backend':{'base_url':'http://127.0.0.1:9880'},
                  'english':{'enabled':True,'reference':'target.wav'}}
        self.payload={'text':'Take your time.','text_lang':'en','media_type':'wav',
                      'ref_audio_path':'target.wav','speed_factor':.84}

    def test_chinese_never_starts_worker_and_payload_is_unchanged(self):
        chinese=dict(self.payload,text='亲爱的，慢慢来。',text_lang='all_zh')
        with patch.object(english_client,'synthesize') as worker, \
                patch.object(tts.urllib.request,'urlopen',return_value=io.BytesIO(b'original')) as upstream:
            self.assertEqual(tts.call_backend(self.cfg,chinese),b'original')
        worker.assert_not_called()
        self.assertEqual(json.loads(upstream.call_args.args[0].data),chinese)

    def test_english_uses_worker_without_calling_gpt(self):
        with patch.object(english_client,'synthesize',return_value=b'new') as worker, \
                patch.object(tts.urllib.request,'urlopen') as upstream:
            self.assertEqual(tts.call_backend(self.cfg,self.payload),b'new')
        upstream.assert_not_called()
        self.assertEqual(worker.call_args.args[1],self.payload)

    def test_worker_failure_falls_back_without_losing_text(self):
        with patch.object(english_client,'synthesize',side_effect=RuntimeError('GPU full')), \
                patch.object(tts.urllib.request,'urlopen',return_value=io.BytesIO(b'fallback')) as upstream:
            self.assertEqual(tts.call_backend(self.cfg,self.payload),b'fallback')
        self.assertEqual(json.loads(upstream.call_args.args[0].data),self.payload)

    def test_other_voice_formats_and_disabled_do_not_use_worker(self):
        for change in ({'ref_audio_path':'different.wav'},{'media_type':'ogg'},{'text_lang':'zh'}):
            self.assertFalse(english_client.eligible(self.cfg['english'],dict(self.payload,**change)))
        self.assertFalse(english_client.eligible({},self.payload))

    def test_sentences_preserve_words_numbers_and_abbreviations(self):
        self.assertEqual(english_worker.sentences('Dr. Smith paid 3.5 dollars. Take your time.'),
                         ['Dr. Smith paid 3.5 dollars.','Take your time.'])
        long=' '.join(['carefully']*60)
        pieces=english_worker.sentences(long)
        self.assertEqual(' '.join(pieces),long)
        self.assertTrue(all(len(p)<=180 for p in pieces))

    def test_u1_applies_to_you_without_changing_your_or_contractions(self):
        cfg={'you_profile':'u1'}
        for text in ('I can play some music for you.','You can take your time.', 'I am here for “you”.'):
            self.assertEqual(english_worker.pronunciation_profile(text,cfg),('u1',.75))
        for text in ('Take your time.',"You're welcome.",'You’re welcome.','Your music is ready.','Open YouTube.'):
            self.assertEqual(english_worker.pronunciation_profile(text,cfg),('d1',.90))

    def test_u1_is_optional_and_selection_is_per_sentence(self):
        self.assertEqual(english_worker.pronunciation_profile('I am here for you.',{}),('d1',.90))
        parts=english_worker.sentences('Take your time. I can play some music for you.')
        self.assertEqual([english_worker.pronunciation_profile(p,{'you_profile':'u1'})[0] for p in parts],['d1','u1'])

    def test_invalid_optional_config_does_not_break_chinese_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'voices.json').write_text(json.dumps({'backend':{'base_url':'local'},'voices':{'test':{}}}))
            (root/'english.local.json').write_text('{')
            self.assertNotIn('english',tts.load_config(root/'voices.json'))

    def test_windows_timeout_reaps_only_owned_worker_tree(self):
        client=english_client.EnglishClient({})
        process=MagicMock(pid=12345)
        process.poll.side_effect=[None,0]
        client.process=process
        with patch.object(english_client.os,'name','nt'), patch.object(english_client.subprocess,'run') as kill:
            client._close()
        self.assertEqual(kill.call_args.args[0],['taskkill','/PID','12345','/T','/F'])
        process.wait.assert_called_once()
        self.assertIsNone(client.process)


if __name__=='__main__': unittest.main()
