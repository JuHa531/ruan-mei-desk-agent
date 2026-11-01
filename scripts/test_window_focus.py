"""Verify explicit pet-to-main activation without leaving main always on top."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from window_focus import raise_native_window


class Native:
    def __init__(self, *, iconic=False, topmost=False, fail=None):
        self.iconic, self.topmost, self.fail = iconic, topmost, fail
        self.foreground, self.calls = 99, []

    def GetWindowLongW(self, *_): return 8 if self.topmost else 0
    def PeekMessageW(self, *_): self.calls.append(('queue',))
    def GetCurrentThreadId(self): return 10
    def GetWindowThreadProcessId(self, hwnd, _): return {77: 20, 99: 30}[hwnd]
    def GetForegroundWindow(self): return self.foreground
    def AttachThreadInput(self, a, b, enabled):
        self.calls.append(('attach', a, b, enabled))
        return True
    def IsIconic(self, _): return self.iconic
    def ShowWindow(self, hwnd, how): self.calls.append(('show', hwnd, how))
    def SetWindowPos(self, hwnd, after, *_):
        self.calls.append(('layer', after))
        if after == -2 and self.fail == 'cleanup': raise RuntimeError('cleanup')
        return True
    def BringWindowToTop(self, hwnd): self.calls.append(('raise', hwnd))
    def SetForegroundWindow(self, hwnd):
        if self.fail == 'activate': raise RuntimeError('activate')
        if self.fail != 'denied': self.foreground = hwnd
        return self.fail != 'denied'
    def SetActiveWindow(self, hwnd): self.calls.append(('active', hwnd))
    def SetFocus(self, hwnd): self.calls.append(('focus', hwnd))


class FocusTests(unittest.TestCase):
    def test_restore_or_preserve_maximized_and_release_topmost(self):
        for iconic in (False, True):
            api = Native(iconic=iconic)
            self.assertTrue(raise_native_window(77, api, api))
            self.assertIn(('show', 77, 9 if iconic else 5), api.calls)
            self.assertEqual([c for c in api.calls if c[0] == 'layer'], [('layer', -1), ('layer', -2)])
            self.assertIn(('focus', 77), api.calls)
            attached = [c[2] for c in api.calls if c[0] == 'attach' and c[3]]
            detached = [c[2] for c in api.calls if c[0] == 'attach' and not c[3]]
            self.assertEqual(set(attached), {20, 30})
            self.assertEqual(detached, attached[::-1])

    def test_existing_topmost_policy_preserved(self):
        api = Native(topmost=True)
        self.assertTrue(raise_native_window(77, api, api))
        self.assertFalse(any(c[0] == 'layer' for c in api.calls))

    def test_focus_denial_reported_from_actual_foreground(self):
        api = Native(fail='denied')
        self.assertFalse(raise_native_window(77, api, api))

    def test_activation_or_layer_cleanup_failure_still_detaches(self):
        for failure in ('activate', 'cleanup'):
            api = Native(fail=failure)
            with self.assertRaisesRegex(RuntimeError, failure): raise_native_window(77, api, api)
            self.assertIn(('layer', -2), api.calls)
            self.assertEqual(len([c for c in api.calls if c[0] == 'attach' and not c[3]]), 2)


if __name__ == '__main__': unittest.main()
