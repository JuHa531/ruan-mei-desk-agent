"""D1/U1 English: sentence source -> content tokens -> original acoustic voice.

Private stdin/stdout worker; no listening port or user-controlled file paths.
Heavy dependencies are isolated in the configured English Python environment.
"""
import base64
import dataclasses
import io
import json
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
import time


def sentences(text, limit=180):
    # Protect common abbreviations; decimal periods do not match whitespace.
    marked = re.sub(r'\b(Mr|Mrs|Ms|Dr|Prof|St)\.', lambda m:m.group(0)[:-1]+'\0', text)
    parts = []
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', marked):
        sentence = sentence.replace('\0', '.').strip()
        while len(sentence)>limit:
            cut = sentence.rfind(' ', 0, limit+1)
            if cut<1: raise ValueError('English word exceeds sentence limit')
            parts.append(sentence[:cut]); sentence=sentence[cut:].strip()
        if sentence: parts.append(sentence)
    return parts


def pronunciation_profile(text, settings):
    """Use the selected U1 source only for the whole word 'you'."""
    words=re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)*",text)
    if settings.get('you_profile')=='u1' and any(word.lower()=='you' for word in words):
        return 'u1', .75
    return 'd1', .90


class Engine:
    def __init__(self, cfg):
        started = time.perf_counter()
        print('English: importing model runtime', flush=True)
        import torch
        torch.set_num_threads(4)
        from qwen_tts import Qwen3TTSModel
        print('English timing: runtime imports %.2fs' % (time.perf_counter()-started), flush=True)
        if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 2700*1024**2:
            raise RuntimeError('Insufficient free GPU memory for English model')
        self.cfg = cfg
        model_started = time.perf_counter()
        self.qwen = Qwen3TTSModel.from_pretrained(cfg['model_dir'], device_map='cuda:0',
                    dtype=torch.bfloat16, attn_implementation='sdpa', local_files_only=True)
        print('English timing: model load %.2fs' % (time.perf_counter()-model_started), flush=True)
        print('English: Qwen ready, building reference', flush=True)
        self.prompt = self.qwen.create_voice_clone_prompt(ref_audio=cfg['reference'],
                      ref_text=cfg['reference_text'], x_vector_only_mode=False)
        self.you_prompt=[dataclasses.replace(self.prompt[0],ref_code=None,ref_text=None,
                         x_vector_only_mode=True,icl_mode=False)]
        gs = Path(cfg['gptsovits_root'])
        os.chdir(gs)
        sys.path[:0] = [str(gs),str(gs/'GPT_SoVITS')]
        from tools.portable_runtime import activate
        activate()
        import nltk
        nltk.data.path.insert(0, cfg['nltk_data'])
        from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
        import yaml
        class AcousticOnly(TTS):
            def _init_models(inner):
                inner.init_vits_weights(inner.configs.vits_weights_path)
                inner.init_cnhuhbert_weights(inner.configs.cnhuhbert_base_path)
        self.temp = tempfile.TemporaryDirectory(prefix='meimei-english-')
        config_path = Path(self.temp.name)/'acoustic.yaml'
        config_path.write_text(yaml.safe_dump({'custom':dict(device='cpu',is_half=False,
            version='v2ProPlus',vits_weights_path=cfg['acoustic_weights'],
            cnhuhbert_base_path='GPT_SoVITS/pretrained_models/chinese-hubert-base',
            bert_base_path='GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large',
            t2s_weights_path='GPT_weights_v2/ruanmei_refine_20261027-e10.ckpt')}),encoding='utf8')
        self.acoustic = AcousticOnly(TTS_Config(str(config_path)))
        with torch.inference_mode():
            self.spec, ref = self.acoustic._get_ref_spec(cfg['reference'])
            self.speaker = self.acoustic.sv_model.compute_embedding3(ref)
        print('English: acoustic model ready; initialization %.2fs' % (time.perf_counter()-started), flush=True)

    def generate(self, text, speed):
        import numpy as np
        import soundfile as sf
        import torch
        import torchaudio
        from tts_server import join_speech_wavs, wav_quality_issue
        clips=[]
        parts=sentences(text)
        with torch.no_grad():
            for index,sentence in enumerate(parts):
                sentence_started = time.perf_counter()
                profile,native_speed=pronunciation_profile(sentence,self.cfg)
                prompt=self.you_prompt if profile=='u1' else self.prompt
                torch.manual_seed(20261028)
                sources, sr = self.qwen.generate_voice_clone(text=sentence, language='English',
                    voice_clone_prompt=prompt, non_streaming_mode=True, temperature=.9,
                    max_new_tokens=min(512,max(128,len(sentence)*4)))
                # Match the accepted experiment's PCM16 source before extraction.
                buf=io.BytesIO(); sf.write(buf,sources[0],sr,format='WAV',subtype='PCM_16')
                buf.seek(0); source, sr=sf.read(buf,dtype='float32')
                wav16=torchaudio.functional.resample(torch.from_numpy(source).reshape(1,-1),sr,16000)
                phones,_,_=self.acoustic.text_preprocessor.get_phones_and_bert(sentence,'en',self.acoustic.configs.version)
                phones=torch.tensor(phones,dtype=torch.long).unsqueeze(0)
                torch.manual_seed(20261028)
                features=self.acoustic.cnhuhbert_model.model(wav16)['last_hidden_state'].transpose(1,2)
                codes=self.acoustic.vits_model.extract_latent(features)
                audio=self.acoustic.vits_model.decode(codes,phones,[self.spec],sv_emb=[self.speaker],
                            speed=native_speed*speed)[0,0].cpu().numpy()
                print('English sentence: profile=%s chars=%d source=%.2fs reconstructed=%.2fs elapsed=%.2fs' %
                      (profile,len(sentence),len(sources[0])/sr,len(audio)/32000,
                       time.perf_counter()-sentence_started),flush=True)
                # Preserve the initial and final margins of the utterance. Only
                # adjoining sentence margins are replaced by the fixed pause.
                hop=320
                energy=np.sqrt(np.mean(audio[:len(audio)//hop*hop].reshape(-1,hop)**2,axis=1))
                active=np.flatnonzero(energy>=max(.003,float(energy.max())*.02))
                if len(active):
                    start=0 if index==0 else max(0,int(active[0]*hop)-1280)
                    end=len(audio) if index==len(parts)-1 else min(len(audio),int((active[-1]+1)*hop)+1280)
                    audio=audio[start:end]
                buf=io.BytesIO(); sf.write(buf,audio,32000,format='WAV',subtype='PCM_16')
                data=buf.getvalue()
                issue=wav_quality_issue(data,sentence)
                if issue: raise RuntimeError('English sentence: '+issue)
                clips.append(data)
        # 40ms margins + 470ms gap + adapter's 120ms padding = D's 670ms pause.
        return join_speech_wavs(clips,gap_seconds=.47)


def main():
    cfg=json.loads(Path(sys.argv[1]).read_text('utf8'))
    protocol=sys.stdout
    sys.stdout=sys.stderr  # Upstream model diagnostics must never enter JSON protocol.
    import faulthandler
    faulthandler.enable()
    faulthandler.dump_traceback_later(60, repeat=True)
    # Initialize native numerical libraries before creating a blocking stdin
    # reader thread (Windows DLL initialization can otherwise stall).
    try:
        engine=Engine(cfg)
        faulthandler.cancel_dump_traceback_later()
    except Exception as error:
        import traceback
        traceback.print_exc()
        protocol.write(json.dumps({'error':str(error)})+'\n'); protocol.flush()
        return
    incoming=queue.Queue()
    def read_input():
        for line in sys.stdin: incoming.put(line)
        incoming.put(None)
    threading.Thread(target=read_input,daemon=True).start()
    while True:
        try: line=incoming.get(timeout=cfg.get('idle_seconds',45) if engine is not None else None)
        except queue.Empty:
            # Keep imported DLLs warm, but release model weights between turns.
            import gc
            import torch
            engine=None
            gc.collect()
            torch.cuda.empty_cache()
            print('English: idle models released; allocated=%d reserved=%d' %
                  (torch.cuda.memory_allocated(),torch.cuda.memory_reserved()),flush=True)
            continue
        if line is None: break
        print('English: request received', flush=True)
        try:
            request=json.loads(line)
            text=request['text']; speed=float(request.get('speed',1))
            if not isinstance(text,str) or not text.strip() or len(text)>1200 or not .5<=speed<=2:
                raise ValueError('Invalid English request')
            if engine is None: engine=Engine(cfg)
            result={'wav':base64.b64encode(engine.generate(text,speed)).decode('ascii')}
        except Exception as error:
            import traceback
            traceback.print_exc()
            result={'error':str(error)}
        protocol.write(json.dumps(result)+'\n'); protocol.flush()
        print('English: response sent', flush=True)
        if result.get('error'): break  # Release GPU on failure; adapter can fall back.


if __name__=='__main__': main()
