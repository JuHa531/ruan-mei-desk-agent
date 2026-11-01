"""Private playback bridge to existing MeiMei TTS; never owns its models."""
import argparse,base64,ctypes,json,os,sys,threading,urllib.request
from pathlib import Path
def emit(value):print(json.dumps(value,ensure_ascii=False),flush=True)
def read():
    raw=sys.stdin.buffer.readline(131073)
    if not raw:return None
    if len(raw)>131072:raise ValueError('input too large')
    return json.loads(raw.decode('utf8'))
def watch_parent(pid):
    if os.name!='nt' or not pid:return
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
    handle=kernel.OpenProcess(0x00100000,False,pid)
    if not handle:return
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    def wait():
        kernel.WaitForSingleObject(handle,0xffffffff);os._exit(0)
    threading.Thread(target=wait,daemon=True).start()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--project-root',required=True);ap.add_argument('--parent-pid',type=int);args=ap.parse_args()
    root=Path(args.project_root)
    if not (root/'voice/tts_server.py').is_file():raise ValueError('MeiMei project missing')
    sys.path.insert(0,str(root/'voice'))
    from tts_server import clean_for_speech,role_speech_segments
    sys.stdout.reconfigure(encoding='utf8');watch_parent(args.parent_pid)
    while True:
        message=read()
        if message is None:return
        if message=={'type':'warmup'}:
            with urllib.request.urlopen('http://127.0.0.1:9881/healthz',timeout=15) as response:
                if not json.load(response).get('ok'):raise ValueError('TTS unavailable')
            emit({'type':'ready','emotion':'neutral'});continue
        if message.get('type')!='speak' or not isinstance(message.get('text'),str) or len(message['text'])>16000:raise ValueError('invalid request')
        text=clean_for_speech(message['text'])
        if not text:emit({'type':'error','code':'no_speech'});continue
        for segment in role_speech_segments(text).splitlines():
            emit({'type':'synthesizing','emotion':'neutral'})
            request=urllib.request.Request('http://127.0.0.1:7788/api/tts',data=json.dumps({'text':segment,'voice':'ruanmei:calm'}).encode('utf8'),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=240) as response:audio=response.read(9*1024*1024+1)
            if len(audio)>9*1024*1024:raise ValueError('audio too large')
            emit({'type':'audio','mime':'audio/wav','emotion':'neutral','base64':base64.b64encode(audio).decode('ascii')})
            ack=read()
            if ack is None:return
            if ack!={'type':'next'}:raise ValueError('invalid acknowledgement')
        emit({'type':'done','emotion':'neutral'})
if __name__=='__main__':
    try:main()
    except (BrokenPipeError,EOFError):pass
    except Exception as error:
        print(str(error),file=sys.stderr);emit({'type':'error','code':'runtime_unavailable'})
