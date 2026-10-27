"""Read-only diagnostics. Run with the application's llm Python environment."""
import importlib.util
import json
import os
import shutil
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import office_tools


def check_url(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.load(response)
        return {'ok': data.get('ok', True), 'detail': data}
    except urllib.error.HTTPError as error:
        return {'ok': False, 'status': error.code}
    except Exception as error:
        return {'ok': False, 'error': str(error)[:180]}


def diagnose():
    result = {'python':sys.executable, 'packages':{}, 'binaries':{}, 'services':{}, 'references':{}}
    for name in ('docx', 'pptx', 'openpyxl', 'PIL', 'uiautomation', 'psutil','webview','clr','lxml'):
        result['packages'][name] = importlib.util.find_spec(name) is not None
    for key, path in [('ffmpeg',office_tools.FFMPEG), ('ffprobe',office_tools.FFPROBE), ('adb',r'C:\platform-tools\adb.exe')]:
        result['binaries'][key] = {'ok':bool(path and os.path.isfile(path)), 'path':path}
    for name, url in [('agent','http://127.0.0.1:7788/api/status'), ('tts','http://127.0.0.1:9881/healthz'),
                      ('asr','http://127.0.0.1:9882/healthz'), ('ollama','http://127.0.0.1:11434/api/tags')]:
        check = check_url(url)
        if name == 'ollama' and check['ok']:
            check['detail'] = {'models':[m['name'] for m in check['detail'].get('models',[])]}
        result['services'][name] = check
    config={}
    config_path = ROOT / 'voice/voices.json'
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding='utf-8'))
        for name, voice in config.get('voices',{}).items():
            refs = [(name,voice)] + [(name+':'+k,v) for k,v in voice.get('emotions',{}).items() if isinstance(v,dict)]
            for key, voice_config in refs:
                path = voice_config.get('ref_audio_path','')
                result['references'][key] = {'ok':os.path.isfile(path), 'path':path}
    # The speech environment is distinct from the desktop environment. Do not
    # call a module missing merely because it is not installed in this Python.
    tts_python=os.getenv('RM_TTS_PYTHON',r'D:\ai\envs\tts\python.exe')
    result['tts_environment']={'python':tts_python,'ok':False}
    if os.path.isfile(tts_python):
        code="import importlib.util,json,sys; names=['torch','torchaudio','funasr','transformers','librosa','soundfile','yaml','onnxruntime']; print(json.dumps({'python':sys.version.split()[0],'packages':{n:importlib.util.find_spec(n) is not None for n in names}}))"
        try:
            p=office_tools.run_hidden([tts_python,'-c',code],capture_output=True,text=True,timeout=20)
            detail=json.loads(p.stdout)
            result['tts_environment'].update(ok=p.returncode==0 and all(detail['packages'].values()),**detail)
        except Exception as e:result['tts_environment']['error']=str(e)[:180]
    import agent_server
    qq=agent_server.find_music_exe()
    for key,path in [('qqmusic',qq),('powershell',shutil.which('powershell.exe')),
                     ('winget',shutil.which('winget.exe')),
                     ('tailscale',shutil.which('tailscale.exe') or r'C:\Program Files\Tailscale\tailscale.exe')]:
        result['binaries'][key]={'ok':bool(path and os.path.isfile(path)),'path':path or ''}
    adb=result['binaries']['adb']
    if adb['ok']:
        try:
            p=office_tools.run_hidden([adb['path'],'devices'],capture_output=True,text=True,timeout=10)
            states=[line.split()[1] for line in p.stdout.splitlines()[1:] if len(line.split())>=2]
            result['android']={'available':states.count('device'),'unauthorized':states.count('unauthorized'),'ok':p.returncode==0}
        except Exception as e:result['android']={'ok':False,'error':str(e)[:120]}
    tailscale=result['binaries']['tailscale']
    if tailscale['ok']:
        try:
            p=office_tools.run_hidden([tailscale['path'],'status','--json'],capture_output=True,text=True,timeout=10)
            d=json.loads(p.stdout)
            result['tailscale']={'backend_state':d.get('BackendState'),'online':bool((d.get('Self') or {}).get('Online')),
                                 'peers':len(d.get('Peer') or {}),'ok':p.returncode==0}
        except Exception as e:result['tailscale']={'ok':False,'error':str(e)[:120]}
    gs=Path(os.getenv('RM_GPTSOVITS_ROOT',r'G:\ai\GPT-SoVITS\GPT-SoVITS-main'))
    try:
        import yaml
        selected=yaml.safe_load((gs/'GPT_SoVITS/configs/tts_infer.yaml').read_text(encoding='utf-8'))['custom']
        result['weights']={k:{'path':selected[k],'ok':(gs/selected[k]).is_file()} for k in ('t2s_weights_path','vits_weights_path')}
        result['speech_version']=selected.get('version')
    except Exception as e:result['weights']={'error':str(e)[:180]}
    is_index=config.get('backend',{}).get('type')=='index_tts'
    result['optional_backends']={'index_tts':{'selected':is_index,'required_for_current_voice':is_index}}
    result['integration_model']='Built-in local tools; no external skill/plugin loader is required for current features.'
    try:
        import psutil
        result['listeners']=[{'port':c.laddr.port,'address':c.laddr.ip} for c in psutil.net_connections('tcp')
                             if c.status=='LISTEN' and c.laddr.port in (7788,9880,9881,9882,11434)]
    except Exception as e:result['listeners_error']=str(e)[:120]
    return result


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(diagnose(), ensure_ascii=False, indent=2))
