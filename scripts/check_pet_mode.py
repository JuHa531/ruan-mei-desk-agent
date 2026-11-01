"""Run the real packaged renderer as a MeiMei-owned component, then stop it."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import tempfile
import time
import os
import subprocess
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from pet_controller import PetController
from window_focus import _native


def wait(check, name):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.1)
    raise AssertionError(name)


if '--owner-crash' in sys.argv:
    probe = PetController(ROOT, profile_directory=ROOT / 'work/pet-owner-probe')
    probe.start()
    wait(lambda: probe.status()['ready'], 'owner probe ready')
    print(json.dumps({'pid': probe.process.pid}), flush=True)
    os._exit(0)

with tempfile.TemporaryDirectory(prefix='meimei-pet-check-') as temporary:
    actions = []
    controller = PetController(ROOT, actions.append, temporary)
    try:
        assert controller.start()['enabled']
        process = controller.process
        wait(lambda: controller.status()['ready'], 'owned renderer ready')
        settings = ROOT / 'app/desktop-profile/pet/settings.json'
        def startup_size():
            try:
                return (controller.status()['scale'] == 1 and
                        json.loads(settings.read_text('utf-8'))['settings']['scale'] == 1)
            except (OSError, ValueError, KeyError):
                return False
        wait(startup_size, 'owner size overrides stale renderer settings')
        controller.resize(75)
        def resized():
            try:
                return json.loads(settings.read_text('utf-8'))['settings']['scale'] == .75
            except (OSError, ValueError, KeyError):
                return False
        wait(resized, 'native resize persisted')
        api, _ = _native()
        settings_handles = []
        controller.settings()
        def own_settings_window():
            found = []
            callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def visit(hwnd, extra):
                pid = wintypes.DWORD()
                api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                title = ctypes.create_unicode_buffer(256)
                api.GetWindowTextW(hwnd, title, 256)
                if pid.value == process.pid and title.value in ('设置', '梅梅 · 桌宠设置'):
                    found.append(hwnd)
                return True
            api.EnumWindows(callback(visit), 0)
            settings_handles[:] = found
            return bool(found)
        wait(own_settings_window, 'owned settings window')
        panel = settings_handles[0]
        def settings_activated():
            return (api.GetForegroundWindow() == panel and not api.IsIconic(panel)
                    and bool(api.GetWindowLongW(panel, -20) & 8))
        wait(settings_activated, 'settings automatically activates and stays topmost')
        # The pet periodically raises itself; it must leave its open settings above it.
        time.sleep(2)
        assert settings_activated(), 'pet maintenance must not steal settings focus'
        api.ShowWindow(panel, 6)
        wait(lambda: api.IsIconic(panel), 'settings minimized')
        controller.settings()
        try:
            wait(settings_activated, 'reopening settings restores and activates it')
        except AssertionError:
            print(json.dumps({'settingsRestoreFailure': {'panel': panel,
                  'foreground': api.GetForegroundWindow(), 'minimized': bool(api.IsIconic(panel)),
                  'topmost': bool(api.GetWindowLongW(panel, -20) & 8)}}), flush=True)
            raise
        controller._send({'type': 'chat'})
        wait(lambda: actions == ['chat'], 'chat returns to main MeiMei')
        controller.stop()
        assert process.poll() == 0 and not controller.status()['enabled']
        print(json.dumps({'owned': True, 'resize': 75, 'settings': True,
                          'settingsTopmostAndForeground': True, 'settingsRestore': True,
                          'sharedChatRoute': True, 'cleanExit': True}))
    finally:
        controller.stop()

probe_result = subprocess.run([sys.executable, __file__, '--owner-crash'], capture_output=True, text=True, timeout=35, check=True)
orphan_pid = json.loads(probe_result.stdout)['pid']
wait(lambda: not psutil.pid_exists(orphan_pid), 'renderer must exit after abrupt owner loss')
print(json.dumps({'abruptOwnerExitCleansRenderer': True}))
