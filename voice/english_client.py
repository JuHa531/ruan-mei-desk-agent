"""Lazy, local English worker. No model dependencies in the desktop adapter."""
import base64
import collections
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


def eligible(settings, payload):
    return (settings.get('enabled', False) and payload.get('text_lang') == 'en'
            and payload.get('media_type', 'wav') == 'wav'
            and os.path.normcase(os.path.abspath(payload.get('ref_audio_path', '')))
            == os.path.normcase(os.path.abspath(settings.get('reference', ''))))


class EnglishClient:
    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.responses = None
        self.cache = collections.OrderedDict()
        self.retry_after = 0
        self.last_error = None
        self.lock = threading.Lock()

    def _start(self):
        if self.process is not None and self.process.poll() is None:
            return
        cfg = self.settings
        log_path = Path(cfg['_config_path']).parent.parent/'logs/english-worker.log'
        log_path.parent.mkdir(exist_ok=True)
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1',
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='4', MKL_NUM_THREADS='4',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
        with log_path.open('ab') as log:
            self.process = subprocess.Popen(
                [cfg['python'], '-u', str(Path(__file__).with_name('english_worker.py')),
                 cfg['_config_path']], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=log, text=True, encoding='utf-8', env=env,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.responses = queue.Queue()
        process, responses = self.process, self.responses
        def receive():
            try:
                for line in process.stdout:
                    responses.put(line)
            finally:
                responses.put(None)
        threading.Thread(target=receive, daemon=True).start()

    def _close(self):
        if self.process is not None:
            if self.process.poll() is None:
                if os.name=='nt':
                    # Windows venv launchers have a base-interpreter child.
                    # Terminate only this worker tree, including that child.
                    subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if self.process.poll() is None: self.process.kill()
            self.process.wait(timeout=10)
            for stream in (self.process.stdin, self.process.stdout):
                if stream: stream.close()
        self.process = None

    def synthesize(self, payload):
        speed = float(payload.get('speed_factor', .84)) / self.settings.get('chinese_base_speed', .84)
        key = (payload['text'], round(speed, 4))
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            if time.monotonic() < self.retry_after:
                raise RuntimeError('English worker cooling down after failure: '+str(self.last_error))
            try:
                for attempt in range(2):
                    self._start()
                    try:
                        self.process.stdin.write(json.dumps({'text':key[0], 'speed':speed})+'\n')
                        self.process.stdin.flush()
                        line = self.responses.get(timeout=self.settings.get('timeout_seconds', 180))
                    except (BrokenPipeError, OSError):
                        line = None
                    if line is None:
                        self._close()
                        if attempt == 0: continue  # Worker may have just exited on idle timeout.
                        raise RuntimeError('English worker exited; see logs/english-worker.log')
                    reply = json.loads(line)
                    if reply.get('error'): raise RuntimeError(reply['error'])
                    data = base64.b64decode(reply['wav'], validate=True)
                    from tts_server import wav_quality_issue
                    issue = wav_quality_issue(data, key[0])
                    if issue: raise RuntimeError(issue)
                    self.cache[key] = data
                    while len(self.cache)>16: self.cache.popitem(last=False)
                    self.last_error = None
                    return data
            except Exception as error:
                if isinstance(error, queue.Empty):
                    error = TimeoutError('English worker timed out; see logs/english-worker.log')
                self.last_error = str(error)
                self.retry_after = time.monotonic()+60
                self._close()
                raise RuntimeError('English D1: '+str(error)) from error


_clients = {}
def status(settings):
    client=_clients.get(settings.get('_config_path'))
    return {'enabled':bool(settings.get('enabled')),
            'you_profile':settings.get('you_profile','d1'),
            'worker_running':bool(client and client.process and client.process.poll() is None),
            'last_error':client.last_error if client else None}

def synthesize(settings, payload):
    key = settings['_config_path']
    if key not in _clients: _clients[key] = EnglishClient(settings)
    return _clients[key].synthesize(payload)
