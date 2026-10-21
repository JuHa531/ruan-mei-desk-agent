// 盯着页面看：后端被拔掉再拉回来之后，背景视频会不会自己活过来。
// 用法：先起无头 Edge，再
//   node check_backend_recover.mjs [url] [观察秒数]
// 跑起来之后，在另一个窗口把 7788 的进程杀掉，看下面这个时间线里
// 后端标志、提示文字、视频位置怎么变。

const PORT = Number(process.env.CDP_PORT || 9222);
const URL_ = process.argv[2] || 'http://127.0.0.1:7788/';
const SECONDS = Number(process.argv[3] || 100);
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function findPage() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find(t => t.type === 'page');
      if (page) return page;
    } catch (e) { /* 还没起来 */ }
    await sleep(250);
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
const ev = async (expr, awaitPromise = false) => {
  const r = await cdp.send('Runtime.evaluate',
    {expression: expr, returnByValue: true, awaitPromise});
  if (r.result && r.result.exceptionDetails) return 'EXC';
  return r.result.result.value;
};
const p = cdp.once('Page.loadEventFired');
await cdp.send('Page.navigate', {url: URL_});
await Promise.race([p, sleep(8000)]);
await sleep(2000);

const t0 = Date.now();
const snap = () => ev(`(() => {
  const v = document.getElementById('bglayer').querySelector('video');
  return JSON.stringify({
    秒: Math.round((Date.now() - ${t0}) / 100) / 10,
    后端标志: typeof backendDown === 'undefined' ? '(旧代码没有)' : backendDown,
    提示: document.getElementById('hint').textContent.slice(0, 22),
    视频暂停: v ? v.paused : null,
    位置: v ? Math.round(v.currentTime * 10) / 10 : null,
  });
})()`);

console.log('开始观察，现在去另一个窗口杀掉 7788 的进程');
while (Date.now() - t0 < SECONDS * 1000) {
  console.log(await snap());
  await sleep(3000);
}
cdp.close();
