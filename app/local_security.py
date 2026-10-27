"""Shared guards for the desktop assistant's loopback HTTP services and files."""
import ipaddress
import os
import fnmatch
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


def canonical_path(path):
    return os.path.realpath(os.path.abspath(os.fspath(path)))


def path_within(path, root):
    path=os.path.normcase(canonical_path(path))
    root=os.path.normcase(canonical_path(root))
    try:
        return os.path.commonpath((path,root))==root
    except ValueError:
        return False


def trusted_desktop_origin(uri, port):
    try:
        parsed=urlsplit(uri)
        return (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1')
                and parsed.port==port and not parsed.username and not parsed.password)
    except ValueError:
        return False


def bounded_matches(root, pattern, max_entries=20000):
    """Walk without following directory links/junctions or leaving root."""
    normalized=pattern.replace('\\','/')
    patterns=[normalized]
    while normalized.startswith('**/'):
        normalized=normalized[3:];patterns.append(normalized)
    count=0
    for current,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not os.path.islink(os.path.join(current,d))
                 and not getattr(os.path,'isjunction',lambda p:False)(os.path.join(current,d))
                 and path_within(os.path.join(current,d),root)]
        for name in dirs+files:
            count+=1
            if count>max_entries:
                raise ValueError('搜索范围超过2万项，请指定更小的目录')
            path=os.path.join(current,name)
            relative=os.path.relpath(path,root).replace('\\','/')
            if path_within(path,root) and any(fnmatch.fnmatch(name,p) or fnmatch.fnmatch(relative,p) for p in patterns):
                yield canonical_path(path)


def request_error(client_ip,port,method,path,headers):
    """Return a rejection before either HTTP implementation consumes a body."""
    try:
        if not ipaddress.ip_address(client_ip).is_loopback:
            return 403,'Loopback clients only'
        hosts=headers.get_all('Host',[])
        if len(hosts)!=1:return 400,'Exactly one Host header required'
        host=urlsplit('http://'+hosts[0])
        if (host.hostname not in ('127.0.0.1','localhost','::1') or host.port!=port
                or host.username or host.password or host.path or host.query or host.fragment):
            return 403,'Untrusted Host'
        origins=headers.get_all('Origin',[])
        if len(origins)>1:return 403,'Untrusted Origin'
        if origins:
            origin=urlsplit(origins[0])
            if (origin.scheme!='http' or origin.hostname!=host.hostname or origin.port!=port
                    or origin.username or origin.password or origin.path or origin.query or origin.fragment):
                return 403,'Untrusted Origin'
        if headers.get('Sec-Fetch-Site','')=='cross-site':return 403,'Cross-site requests refused'
        if headers.get('Transfer-Encoding'):return 400,'Transfer-Encoding not supported'
        lengths=headers.get_all('Content-Length',[])
        if len(lengths)>1 or (lengths and not lengths[0].isdigit()):return 400,'Invalid Content-Length'
        size=int(lengths[0]) if lengths else 0
        path=path.split('?',1)[0]
        limit=32*1024*1024 if path in ('/api/asr','/asr') else 4*1024*1024
        if path=='/api/upload_image':limit=15*1024*1024
        if size>limit:return 413,'Request body too large'
        if method=='POST' and not lengths:return 411,'Content-Length required'
        if (method=='POST' and path not in ('/api/asr','/asr','/api/upload_image')
                and headers.get_content_type()!='application/json'):
            return 415,'JSON content type required'
    except ValueError:
        return 400,'Invalid request headers'
    return None


class LocalRequestHandler(BaseHTTPRequestHandler):
    """Reject browser CSRF/rebinding and oversized bodies before reading them.

    These endpoints control a local computer; unauthenticated LAN exposure is
    deliberately refused.  Remote use needs a separate authenticated gateway.
    Native loopback callers without Origin remain supported.
    """
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def parse_request(self):
        if not super().parse_request():
            return False
        self.close_connection=True
        error=request_error(self.client_address[0],self.server.server_address[1],
                            self.command,self.path,self.headers)
        if error:
            self.send_error(*error);return False
        return True

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cross-Origin-Resource-Policy','same-origin')
        if getattr(self,'path','').split('?',1)[0].lower().endswith('.svg'):
            self.send_header('Content-Security-Policy',"sandbox; default-src 'none'; style-src 'unsafe-inline'")
        else:
            self.send_header('Content-Security-Policy',"frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
        super().end_headers()


class LoopbackASGIGuard:
    """The same pre-body guard for the separately installed GPT-SoVITS API."""
    def __init__(self,app):self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        from email.message import Message
        headers=Message()
        for name,value in scope.get('headers',[]):
            headers[name.decode('latin1')]=value.decode('latin1')
        error=request_error((scope.get('client') or ('',0))[0],
                            (scope.get('server') or ('',0))[1],scope['method'],scope['path'],headers)
        if error:
            code,message=error;body=message.encode('utf-8')
            await send({'type':'http.response.start','status':code,
                        'headers':[(b'content-type',b'text/plain; charset=utf-8'),(b'content-length',str(len(body)).encode())]})
            return await send({'type':'http.response.body','body':body})
        return await self.app(scope,receive,send)
