"""Activate MeiMei from a user click in the separately owned pet process."""
import ctypes
from ctypes import wintypes


def _native():
    api = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    for name, args, result in [
        ('GetForegroundWindow', [], wintypes.HWND),
        ('GetWindowThreadProcessId', [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        ('AttachThreadInput', [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL], wintypes.BOOL),
        ('GetWindowLongW', [wintypes.HWND, ctypes.c_int], ctypes.c_long),
        ('SetWindowPos', [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
        ('ShowWindow', [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
        ('IsIconic', [wintypes.HWND], wintypes.BOOL),
        ('BringWindowToTop', [wintypes.HWND], wintypes.BOOL),
        ('SetForegroundWindow', [wintypes.HWND], wintypes.BOOL),
        ('SetActiveWindow', [wintypes.HWND], wintypes.HWND),
        ('SetFocus', [wintypes.HWND], wintypes.HWND),
        ('PeekMessageW', [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
        ('GetWindowTextW', [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
    ]:
        fn = getattr(api, name)
        fn.argtypes, fn.restype = args, result
    kernel.GetCurrentThreadId.restype = wintypes.DWORD
    return api, kernel


def raise_native_window(hwnd, api=None, kernel=None):
    if api is None:
        api, kernel = _native()
    attached = []
    was_topmost = bool(api.GetWindowLongW(hwnd, -20) & 8)
    pulse = False
    try:
        # The pipe listener has no GUI queue until it requests one.
        message = wintypes.MSG()
        api.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        current = kernel.GetCurrentThreadId()
        foreground = api.GetForegroundWindow()
        threads = {api.GetWindowThreadProcessId(hwnd, None)}
        if foreground:
            threads.add(api.GetWindowThreadProcessId(foreground, None))
        for thread in threads:
            if thread and thread != current and api.AttachThreadInput(current, thread, True):
                attached.append((current, thread))
        api.ShowWindow(hwnd, 9 if api.IsIconic(hwnd) else 5)
        if not was_topmost:
            pulse = bool(api.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x43))
        api.BringWindowToTop(hwnd)
        api.SetForegroundWindow(hwnd)
        api.SetActiveWindow(hwnd)
        api.SetFocus(hwnd)
        return api.GetForegroundWindow() == hwnd
    finally:
        try:
            if pulse:
                api.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x13)
        finally:
            for current, thread in reversed(attached):
                api.AttachThreadInput(current, thread, False)


def focus_existing_window(title='梅梅', process_id=None):
    try:
        api, kernel = _native()
        found = []
        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def visit(hwnd, _):
            text = ctypes.create_unicode_buffer(512)
            api.GetWindowTextW(hwnd, text, 512)
            if text.value == title:
                pid = wintypes.DWORD()
                api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if process_id is None or pid.value == process_id:
                    found.append(hwnd)
            return True

        api.EnumWindows(callback(visit), 0)
        return any(raise_native_window(hwnd, api, kernel) for hwnd in found)
    except Exception as error:
        print('[窗口] 置前失败：%s' % error)
        return False
