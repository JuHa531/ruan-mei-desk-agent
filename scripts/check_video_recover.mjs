// 复现"后端死了 → 背景视频卡在最后一帧"这个现象，并验证它能不能自己活过来。
//
// 做法：把网络限速到 150KB/s（这样 10MB 的背景视频会一边下一边播，不会一次缓存完），
// 加载页面，然后在下载途中把 7788 的后端杀掉。看护会把后端拉回来，页面这边
// 应该自己把视频重新挂一遍继续播 —— 全程只靠采样，不用肉眼看。
//
// 用法：node check_video_recover.mjs [url] [总观察秒数]
// 跑起来后，去另一个窗口杀掉 7788 的进程（脚本会提示什么时候杀）。

const PORT = Number(process.env.CDP_PORT || 9222);
const URL_ = process.argv[2] || 'http://127.0.0.1:7788/';
const SECONDS = Number(process.argv[3] || 120);
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
await cdp.send('Network.enable');
// 限速：让视频"边下边播"，这样后端一断，它立刻就缺数据
await cdp.send('Network.emulateNetworkConditions', {
  offline: false, latency: 20,
  downloadThroughput: 150 * 1024, uploadThroughput: 150 * 1024,
});
const ev = async (expr, awaitPromise = false) => {
  const r = await cdp.send('Runtime.evaluate',
    {expression: expr, returnByValue: true, awaitPromise});
  if (r.result && r.result.exceptionDetails) return 'EXC';
  return r.result.result.value;
};
const p = cdp.once('Page.loadEventFired');
await cdp.send('Page.navigate', {url: URL_});
await Promise.race([p, sleep(15000)]);
await sleep(2000);

const t0 = Date.now();
const snap = () => ev(`(() => {
  const v = document.getElementById('bglayer').querySelector('video');
  if (!v) return '{"没有视频元素"}';
  return JSON.stringify({
    秒: Math.round((Date.now() - ${t0}) / 100) / 10,
    位置: Math.round(v.currentTime * 10) / 10,
    readyState: v.readyState,
    暂停: v.paused,
    缓冲到秒: v.buffered.length ? Math.round(v.buffered.end(v.buffered.length - 1)) : 0,
    重试次数: v.dataset.retries || '0',
    提示: document.getElementById('hint').textContent.slice(0, 14),
  });
})()`);

console.log('现在开始观察 —— 请在 15 秒内去另一个窗口杀掉 7788 的进程');
while (Date.now() - t0 < SECONDS * 1000) {
  console.log(await snap());
  await sleep(3000);
}
cdp.close();
