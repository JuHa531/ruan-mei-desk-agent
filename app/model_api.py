"""Cloud text providers; local speech and tool execution stay in MeiMei."""
import base64
import copy
import ctypes
import json
import os
import re
from pathlib import Path
import threading
import urllib.request
import urllib.error
from urllib.parse import urlsplit

DEFAULTS = {
    'local': {'base_url': '', 'model': ''},
    'openai': {'base_url': 'https://api.openai.com/v1', 'model': ''},
    'deepseek': {'base_url': 'https://api.deepseek.com', 'model': ''},
    'claude': {'base_url': 'https://api.anthropic.com/v1', 'model': ''},
    'compatible': {'base_url': '', 'model': ''},
}


def crypt(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('密钥加密保存需要 Windows DPAPI')
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
        raise ValueError('无法读取或保存密钥，请在当前 Windows 账户重新填写')
    try:
        return ctypes.string_at(dst.data, dst.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(dst.data, ctypes.c_void_p))


class Settings:
    def __init__(self, path=None):
        self.path = Path(path or Path(__file__).with_name('model-api.local.json'))
        self.lock = threading.RLock()

    def read(self):
        with self.lock:
            if not self.path.exists():
                return {'active': 'local', 'profiles': copy.deepcopy(DEFAULTS)}
            try:
                return json.loads(self.path.read_text(encoding='utf-8'))
            except Exception:
                raise ValueError('模型配置读取失败，请检查 model-api.local.json') from None

    def public(self):
        data = self.read()
        profiles = {}
        for name, default in DEFAULTS.items():
            p = data['profiles'].get(name, default)
            profiles[name] = {k: p.get(k, default[k]) for k in ('base_url', 'model')}
            profiles[name]['has_key'] = bool(p.get('secret'))
            profiles[name]['models'] = list(dict.fromkeys([p.get('model', '')] + p.get('models', [])))[:12]
        return {'active': data['active'], 'profiles': profiles}

    def prepare(self, req):
        if not isinstance(req, dict):
            raise ValueError('模型配置必须是 JSON 对象')
        name = req.get('provider')
        if name not in DEFAULTS:
            raise ValueError('请选择支持的模型服务')
        data = self.read()
        old = data['profiles'].get(name, DEFAULTS[name])
        p = {k: str(req.get(k, old.get(k, ''))).strip() for k in ('base_url', 'model')}
        p['secret'] = old.get('secret', '')
        if req.get('clear_key'):
            p['secret'] = ''
            data['profiles'][name] = p
            data['active'] = 'local'
            return data
        key = str(req.get('api_key') or '').strip()
        if key:
            if len(key) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise ValueError('API 密钥格式不正确')
            p['secret'] = base64.b64encode(crypt(key.encode())).decode()
        if name != 'local':
            u = urlsplit(p['base_url'])
            if (u.scheme != 'https' or not u.hostname or u.username or u.password
                    or u.query or u.fragment):
                raise ValueError('API 基础地址必须是 HTTPS 地址，不含密钥、查询参数或账号')
            p['base_url'] = p['base_url'].rstrip('/')
            if p['base_url'].endswith(('/chat/completions', '/messages')):
                raise ValueError('请填写基础地址，不要包含 /chat/completions 或 /messages')
            if not p['model'] or len(p['model']) > 200:
                raise ValueError('请填写平台提供的准确模型 ID')
            if not p['secret']:
                raise ValueError('请填写 API 密钥')
            if p['base_url'] != old.get('base_url') and old.get('secret') and not key:
                raise ValueError('更换 API 地址时请重新填写密钥，避免把旧密钥发送到新地址')
        p['models'] = list(dict.fromkeys([p['model']] + old.get('models', []) + [old.get('model', '')]))[:12]
        data['profiles'][name] = p
        data['active'] = name
        return data

    def save(self, req):
        with self.lock:
            data = self.prepare(req)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temp, self.path)
            return self.public()

    def snapshot(self, data=None):
        data = data or self.read()
        name = data['active']
        p = dict(data['profiles'].get(name, DEFAULTS[name]))
        p['provider'] = name
        if name != 'local':
            p['api_key'] = crypt(base64.b64decode(p.pop('secret')), True).decode()
        return p


SETTINGS = Settings()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def error_detail(response, headers):
    """Expose bounded diagnostic identifiers, never a reflected request or key."""
    try:
        data = json.loads(response.read(16384))
        err = data.get('error', data)
        if not isinstance(err, dict):
            return ''
        secrets = [v.removeprefix('Bearer ') for k, v in headers.items()
                   if k.lower() in ('authorization', 'x-api-key')]
        details = []
        for field in ('code', 'type', 'param'):
            value = str(err.get(field) or '')
            if (re.fullmatch(r'[A-Za-z0-9_.\[\]-]{1,96}', value)
                    and not any(secret and secret in value for secret in secrets)
                    and not value.startswith(('sk-', 'sk_'))):
                details.append(field + '=' + value)
        message = str(err.get('message') or '').lower()
        if 'model' in message and any(s in message for s in ('not found', 'does not exist', 'invalid model', 'unknown model')):
            details.append('模型 ID 不存在或当前账号无权访问')
        elif 'balance' in message or 'credit' in message or 'quota' in message:
            details.append('请检查账户余额或调用额度')
        elif 'unsupported' in message and ('endpoint' in message or 'chat/completions' in message):
            details.append('此模型不支持当前接口协议')
        return '；' + '；'.join(details) if details else ''
    except (ValueError, OSError, AttributeError):
        return ''


def request_json(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', **headers})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        hints = {401: '密钥无效或已过期', 403: '账号或模型访问权限不足',
                 404: '请检查基础地址和模型 ID', 429: '额度不足或请求过于频繁',
                 400: '服务商拒绝请求，请核对服务类型、API 基础地址和模型 ID'}
        detail = error_detail(e, headers)
        raise RuntimeError('模型 API HTTP %s：%s%s' % (e.code, hints.get(e.code, '服务暂时不可用'), detail)) from None
    except (OSError, ValueError):
        raise RuntimeError('模型 API 连接失败或响应无效，请检查网络和基础地址') from None


def cloud_chat(profile, payload, timeout=120):
    provider = profile['provider']
    headers = {}
    messages = payload['messages']
    if provider == 'claude':
        converted = []
        for m in messages:
            if m['role'] == 'system':
                continue
            if m['role'] == 'tool':
                role, content = 'user', [{'type': 'tool_result', 'tool_use_id': m['tool_call_id'], 'content': m['content']}]
            elif m.get('_claude_content'):
                role, content = 'assistant', m['_claude_content']
            else:
                role, content = m['role'], [{'type': 'text', 'text': m.get('content') or ' ' }]
            if converted and converted[-1]['role'] == role:
                converted[-1]['content'].extend(content)
            else:
                converted.append({'role': role, 'content': content})
        body = {'model': profile['model'], 'max_tokens': 4096, 'messages': converted,
                'system': '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')}
        if payload.get('tools'):
            body['tools'] = [{'name': t['function']['name'], 'description': t['function'].get('description', ''),
                              'input_schema': t['function']['parameters']} for t in payload['tools']]
        headers = {'x-api-key': profile['api_key'], 'anthropic-version': '2023-06-01'}
        raw = request_json(profile['base_url'] + '/messages', body, headers, timeout)
        blocks = raw.get('content', [])
        msg = {'role': 'assistant', 'content': ''.join(b.get('text', '') for b in blocks if b['type'] == 'text'),
               '_claude_content': blocks,
               'tool_calls': [{'id': b['id'], 'type': 'function', 'function': {'name': b['name'], 'arguments': b['input']}}
                              for b in blocks if b['type'] == 'tool_use']}
        if raw.get('stop_reason') == 'max_tokens':
            raise RuntimeError('模型输出达到长度上限，请缩小本轮任务范围')
    else:
        converted = []
        for m in messages:
            item = {k: copy.deepcopy(v) for k, v in m.items()
                    if k in ('role', 'content', 'tool_calls', 'tool_call_id', 'reasoning_content')}
            for tc in item.get('tool_calls') or []:
                if not isinstance(tc['function']['arguments'], str):
                    tc['function']['arguments'] = json.dumps(tc['function']['arguments'], ensure_ascii=False)
            converted.append(item)
        body = {'model': profile['model'], 'messages': converted, 'stream': False}
        if payload.get('tools'):
            body['tools'] = payload['tools']
        raw = request_json(profile['base_url'] + '/chat/completions', body,
                           {'Authorization': 'Bearer ' + profile['api_key']}, timeout)
        if not raw.get('choices'):
            raise RuntimeError('模型 API 未返回回复')
        choice = raw['choices'][0]
        if choice.get('finish_reason') in ('length', 'content_filter'):
            raise RuntimeError('模型回复被截断或拦截，请调整请求后重试')
        msg = {k: v for k, v in choice['message'].items()
               if k in ('role', 'content', 'tool_calls', 'reasoning_content')}
    if not msg.get('content') and not msg.get('tool_calls'):
        raise RuntimeError('模型没有返回可显示的正文')
    for tc in msg.get('tool_calls') or []:
        try:
            args = tc['function']['arguments']
            args = json.loads(args) if isinstance(args, str) else args
            if not isinstance(args, dict) or not tc.get('id'):
                raise ValueError()
            tc['function']['arguments'] = args
        except (KeyError, ValueError, TypeError):
            raise RuntimeError('模型返回了无效的工具参数，本轮未执行') from None
    return {'message': msg}
