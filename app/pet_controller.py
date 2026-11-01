"""MeiMei-owned transparent renderer: one app, one chat, one lifetime."""
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
import secrets
import ctypes
from ctypes import wintypes
from window_focus import focus_existing_window


def owned_process_job(process):
    """Windows closes the entire renderer tree if its MeiMei owner disappears."""
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                    ('max_ws', ctypes.c_size_t), ('active', wintypes.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                    ('scheduling', wintypes.DWORD)]
    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                    ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                    ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, int(process._handle)):
        error = ctypes.get_last_error()
        if job:
            kernel.CloseHandle(job)
        process.terminate()
        raise ctypes.WinError(error)
    return job


class PetController:
    def __init__(self, root, on_action=None, profile_directory=None):
        self.root = Path(root)
        self.executable = self.root / 'desktop-pet/release/win-unpacked/梅梅桌宠.exe'
        self.preferences_file = Path(profile_directory or self.root / 'app/desktop-profile') / 'pet-mode.json'
        self.on_action = on_action or (lambda action: None)
        self.process = None
        self.command_pipe = None
        self.pending_commands = []
        self.job_handle = None
        self.lock = threading.RLock()
        self.error = None
        self.ready = False
        self.preferences = {'enabled': False, 'scale': 1.0}
        try:
            value = json.loads(self.preferences_file.read_text('utf-8'))
            self.preferences['enabled'] = value.get('enabled') is True
            scale = value.get('scale')
            if isinstance(scale, (int, float)) and math.isfinite(scale) and scale >= .01:
                self.preferences['scale'] = scale
        except (OSError, ValueError, TypeError):
            pass

    def _save(self):
        self.preferences_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.preferences_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.preferences), 'utf-8')
        for attempt in range(6):
            try:
                temporary.replace(self.preferences_file)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.02 * 2 ** attempt)

    def status(self):
        with self.lock:
            return {'enabled': self.process is not None and self.process.poll() is None,
                    'ready': self.ready, 'scale': self.preferences['scale'],
                    'available': self.executable.is_file(), 'error': self.error}

    def _send(self, command):
        with self.lock:
            if not self.status()['enabled']:
                return False
            try:
                if self.command_pipe is None:
                    self.pending_commands.append(command)
                    return True
                self.command_pipe.write((json.dumps(command) + '\n').encode('utf-8'))
                return True
            except (OSError, ValueError):
                return False

    def _listen(self, process):
        logfile = self.root / 'logs/pet-renderer.log'
        logfile.parent.mkdir(exist_ok=True)
        try:
            with logfile.open('a', encoding='utf-8') as log:
                for line in process.stdout:
                    if self.process is not process:
                        break
                    if not line.startswith('MEIMEI_PET_EVENT:'):
                        log.write(line); log.flush()
                        continue
                    event = json.loads(line.split(':', 1)[1])
                    log.write(line); log.flush()
                    if event.get('type') == 'ready':
                        self.command_pipe = open(self.pipe_name, 'wb', buffering=0)
                        self._send({'type': 'resize', 'scale': self.preferences['scale']})
                        for command in self.pending_commands:
                            self._send(command)
                        self.pending_commands.clear()
                        self.ready = True
                    elif event.get('type') == 'state':
                        # The owner's saved size wins over the renderer's startup snapshot.
                        if not self.ready:
                            continue
                        scale = event.get('scale')
                        if isinstance(scale, (int, float)) and math.isfinite(scale) and scale >= .01:
                            with self.lock:
                                self.preferences['scale'] = scale
                                self._save()
                    elif event.get('type') == 'settings-opened':
                        focused = focus_existing_window('梅梅 · 桌宠设置', process_id=process.pid)
                        log.write('MEIMEI_PET_SETTINGS_FOCUS: %s\n' % focused); log.flush()
                    elif event.get('type') in ('chat', 'show-main'):
                        self.on_action('chat')
                    elif event.get('type') == 'hide':
                        self.stop()
        except (OSError, ValueError) as exc:
            self.error = str(exc)
        finally:
            with self.lock:
                if self.process is process:
                    self.ready = False

    def start(self):
        with self.lock:
            if self.status()['enabled']:
                self._send({'type': 'recover'})
                return self.status()
            if not self.executable.is_file():
                self.error = '桌宠渲染组件尚未构建，请在 desktop-pet 目录运行 npm run package。'
                return self.status()
            env = dict(os.environ)
            env.pop('ELECTRON_RUN_AS_NODE', None)
            env['RM_TOOLKIT_ROOT'] = str(self.root)
            import sys
            env['RM_APP_PYTHON'] = sys.executable
            self.pipe_name = rf'\\.\pipe\meimei-pet-{os.getpid()}-{secrets.token_hex(16)}'
            self.command_pipe = None
            self.pending_commands.clear()
            self.process = subprocess.Popen(
                [str(self.executable), '--meimei-managed', '--owner-pid', str(os.getpid()), '--owner-pipe', self.pipe_name],
                cwd=self.executable.parent, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace', bufsize=1,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.job_handle = owned_process_job(self.process)
            self.error = None
            self.ready = False
            self.preferences['enabled'] = True
            self._save()
            threading.Thread(target=self._listen, args=(self.process,), daemon=True).start()
            return self.status()

    def stop(self, remember=True):
        with self.lock:
            process = self.process
            if remember:
                self.preferences['enabled'] = False
                self._save()
            if process and process.poll() is None:
                self._send({'type': 'quit'})
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.terminate()
            self.process = None
            if self.job_handle:
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle(self.job_handle)
                self.job_handle = None
            if self.command_pipe:
                self.command_pipe.close()
                self.command_pipe = None
            self.ready = False
            return self.status()

    def toggle(self):
        return self.stop() if self.status()['enabled'] else self.start()

    def settings(self):
        result = self.start()
        self._send({'type': 'settings'})
        return result

    def resize(self, percent):
        if isinstance(percent, bool) or not isinstance(percent, (int, float)) or not math.isfinite(percent) or not 1 <= percent <= 1000:
            return {**self.status(), 'error': '请输入 1% 至 1000% 的大小。'}
        with self.lock:
            self.preferences['scale'] = percent / 100
            self._save()
            self._send({'type': 'resize', 'scale': percent / 100})
        return self.status()
