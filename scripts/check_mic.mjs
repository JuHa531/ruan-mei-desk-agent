// 用无头 Edge 探一下"这台机器到底允不允许网页用麦克风"，把系统级拦截和浏览器级提示分开看。
// 关键参数 --use-fake-ui-for-media-stream 会让浏览器自动同意网页的权限申请，
// 所以剩下的失败只可能来自 Windows 的隐私开关。
//
// 用法：node check_mic.mjs [url] [调试端口]

const PORT = Number(process.argv[3] || 9222);
const URL_ = process.argv[2] || 'http://127.0.0.1:7788/';

async function findPage() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find(t => t.type === 'page');
      if (page) return page;
    } catch (e) { /* 还没起来 */ }
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error('调试端口没起来');
}

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const waiters = [];
  ws.addEventListener('message', ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    else if (m.method) waiters.splice(0).forEach(fn => fn(m));
  });
  const ready = new Promise((res, rej) => {
    ws.addEventListener('open', res);
    ws.addEventListener('error', rej);
  });
  const send = (method, params = {}) => new Promise(res => {
    const n = ++id;
    pending.set(n, res);
    ws.send(JSON.stringify({id: n, method, params}));
  });
  const once = method => new Promise(res => waiters.push(m => m.method === method && res(m)));
  return {ready, send, once, close: () => ws.close()};
}

const cdp = connect((await findPage()).webSocketDebuggerUrl);
await cdp.ready;
await cdp.send('Page.enable');
await cdp.send('Runtime.enable');
const loaded = cdp.once('Page.loadEventFired');
await cdp.send('Page.navigate', {url: URL_});
await Promise.race([loaded, new Promise(r => setTimeout(r, 8000))]);

const ev = async expr => {
  const r = await cdp.send('Runtime.evaluate',
    {expression: expr, returnByValue: true, awaitPromise: true});
  if (r.result && r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.text);
  return r.result.result.value;
};

const devices = await ev(`navigator.mediaDevices.enumerateDevices().then(
  ds => ds.filter(d => d.kind === 'audioinput').map(d => d.label || '(无名)').join(' | ') || '(一个都没有)')`);
console.log('系统里的录音设备：', devices);

const res = await ev(`navigator.mediaDevices.getUserMedia({audio: true})
  .then(st => { st.getTracks().forEach(t => t.stop()); return 'OK'; })
  .catch(e => e.name + ': ' + e.message)`);
console.log('浏览器申请麦克风的结果：', res);

cdp.close();
