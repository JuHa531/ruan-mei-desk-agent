"""Local permission preferences and request-scoped, single-use approvals."""
import json
import os
from pathlib import Path
import re
import threading
import uuid
from contextlib import contextmanager

CONTEXT = threading.local()
MODES = ('ask', 'auto', 'full')


def authorized():
    return bool(getattr(CONTEXT, 'approved', False))


@contextmanager
def approval_scope():
    previous = authorized()
    CONTEXT.approved = True
    try:
        yield
    finally:
        CONTEXT.approved = previous


class PermissionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.mode = 'auto'
        self.pending = {}
        self.turns = {}
        try:
            mode = json.loads(self.path.read_text(encoding='utf-8')).get('mode')
            if mode in MODES:
                self.mode = mode
        except (OSError, ValueError):
            pass

    def save(self, mode):
        if mode not in MODES:
            raise ValueError('无效的权限模式')
        with self.lock:
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'mode': mode}), encoding='utf-8')
            os.replace(tmp, self.path)
            self.mode = mode
        return {'mode': mode}

    def begin(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request_id):
            raise ValueError('无效的请求 ID')
        with self.lock:
            if request_id in self.turns:
                raise ValueError('请求已在运行')
            event = self.turns[request_id] = threading.Event()
        return event

    def finish(self, request_id):
        with self.lock:
            self.turns.pop(request_id, None)
            for token, item in list(self.pending.items()):
                if item['request_id'] == request_id:
                    self.pending.pop(token, None)

    def cancel(self, request_id):
        with self.lock:
            event = self.turns.get(request_id)
            if event:
                event.set()

    def decide(self, token, allow):
        if type(allow) is not bool:
            raise ValueError('批准结果必须为布尔值')
        with self.lock:
            item = self.pending.get(token)
            if item is None or item['event'].is_set():
                raise ValueError('批准请求已失效')
            item['allow'] = allow
            item['event'].set()

    def ask(self, request_id, name, args, emit, cancelled):
        token = uuid.uuid4().hex
        item = dict(request_id=request_id, event=threading.Event(), allow=False)
        with self.lock:
            self.pending[token] = item
        try:
            emit(dict(type='approval', token=token, name=name, args=args))
            while not item['event'].wait(1):
                if cancelled.is_set():
                    raise RuntimeError('任务已停止')
                emit({'type': 'heartbeat'})  # Detect a closed client while waiting.
            if cancelled.is_set() or not item['allow']:
                raise RuntimeError('你已拒绝本次操作，任务已停止')
        finally:
            with self.lock:
                self.pending.pop(token, None)


def sensitive(name, args, workdir, high_risk_command):
    if name == 'run_cmd':
        return high_risk_command(args.get('command'))
    if name in ('install_app', 'forget'):
        return True
    if name == 'app' and args.get('action') in ('close', '关闭', 'press', 'keys', '按键'):
        return True
    if name in ('android', 'phone', 'adb') and args.get('action') not in ('devices', 'status', 'list', 'screenshot'):
        return True
    writes = {'write_file', 'make_docx', 'make_pptx', 'make_xlsx', 'make_dayplan', 'edit_video'}
    for key in ('path', 'output', 'output_path'):
        value = args.get(key)
        if isinstance(value, str):
            path = os.path.realpath(os.path.join(workdir, value))
            try:
                outside = os.path.commonpath([path, os.path.realpath(workdir)]) != os.path.realpath(workdir)
            except ValueError:
                outside = True
            if outside or (name in writes and os.path.exists(path)):
                return True
    return False


def tool_limits(text):
    """Only explicit maximum/limit phrasing changes the unbounded default."""
    number = r'(\d+|[一二两三四五六七八九十百]+)'
    def parse(value):
        if value.isdigit():
            return int(value)
        digits = dict(zip('一二两三四五六七八九', [1,2,2,3,4,5,6,7,8,9]))
        total = current = 0
        for char in value:
            if char in '十百':
                total += (current or 1) * (10 if char == '十' else 100)
                current = 0
            else:
                current = digits[char]
        return total + current
    prefix = r'(?:最多|至多|不超过|限定|限制(?:为)?|仅限|只(?:能)?(?:允许)?)\s*(?:调用|使用|执行)?\s*'
    rounds = re.search(prefix + number + r'\s*轮', text)
    calls = re.search(prefix + number + r'\s*(?:次工具(?:调用)?|个工具|次调用)', text)
    return (parse(rounds[1]) if rounds else None, parse(calls[1]) if calls else None)


SETTINGS = PermissionStore(Path(__file__).with_name('permissions.local.json'))
