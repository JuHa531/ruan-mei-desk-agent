"""Exercise the real main window from a worker, like the desktop pet pipe."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from window_focus import _native, focus_existing_window

api, _ = _native()
handles = []
callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def visit(hwnd, _):
    title = ctypes.create_unicode_buffer(512)
    api.GetWindowTextW(hwnd, title, 512)
    if title.value == '梅梅': handles.append(hwnd)
    return True


api.EnumWindows(callback(visit), 0)
assert len(handles) == 1, 'Start the normal MeiMei application first'
hwnd = handles[0]
api.IsZoomed.argtypes, api.IsZoomed.restype = [wintypes.HWND], wintypes.BOOL
was_maximized = bool(api.IsZoomed(hwnd))
checks = []
for minimized in (False, True):
    if minimized:
        api.ShowWindow(hwnd, 6)
        assert api.IsIconic(hwnd)
    before = api.GetForegroundWindow()
    result = []
    worker = threading.Thread(target=lambda: result.append(focus_existing_window()), daemon=True)
    worker.start()
    worker.join(5)
    assert not worker.is_alive(), 'Native activation must not hang the pet pipe'
    assert result == [True] and api.GetForegroundWindow() == hwnd
    assert not api.IsIconic(hwnd)
    assert bool(api.IsZoomed(hwnd)) == was_maximized, 'Keep the maximized state'
    assert not api.GetWindowLongW(hwnd, -20) & 8, 'Main window must not remain permanently topmost'
    checks.append({'minimizedBefore': minimized, 'foregroundBefore': before,
                   'foregroundAfter': api.GetForegroundWindow(), 'mainTopmost': False})
    time.sleep(.2)
print(json.dumps({'workerActivation': checks, 'preservedMaximizedState': was_maximized}))
