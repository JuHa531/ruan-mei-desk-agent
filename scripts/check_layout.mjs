// 用 CDP 量真实布局，不需要肉眼看截图。
// 用法：node check_layout.mjs [url] [宽] [高]
// 先起一个带调试端口的 Edge：
//   msedge.exe --headless=new --remote-debugging-port=9222 --user-data-dir=%TEMP%\edge_cdp about:blank

const PORT = Number(process.env.CDP_PORT || 9222);   // 想连别的调试端口就设 CDP_PORT
const url = process.argv[2] || 'http://127.0.0.1:7788/';
const width = Number(process.argv[3] || 390);
const height = Number(process.argv[4] || 844);

const MEASURE = `(() => {
  const box = el => { const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return {x: Math.round(b.x), w: Math.round(b.width), h: Math.round(b.height),
            display: cs.display, pos: cs.position, onscreen: b.width > 0 && b.right > 0}; };
  const q = s => document.querySelector(s);
  return {
    viewport: [document.documentElement.clientWidth, document.documentElement.clientHeight],
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    aside: box(q('aside')),
    menu: box(q('#menu')),
    header: box(q('header')),
    log: box(q('#log')),
    footer: box(q('footer')),
    textareaW: Math.round(q('#inp').getBoundingClientRect().width),
    drawer: box(q('#drawer')),
    bodyClass: document.body.className
  };
})()`;

async function findTarget() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find(t => t.type === 'page');
      if (page) return page;
    } catch (e) { /* 端口还没起来 */ }
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error('CDP 端口 9222 没起来');
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

const target = await findTarget();
const cdp = connect(target.webSocketDebuggerUrl);
await cdp.ready;
console.log('已连上 CDP 目标:', target.url);
await cdp.send('Page.enable');
await cdp.send('Runtime.enable');
await cdp.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 2, mobile: true});
const loaded = cdp.once('Page.loadEventFired');
await cdp.send('Page.navigate', {url});
await Promise.race([loaded, new Promise(r => setTimeout(() => r('load 事件没等到，直接往下走'), 8000))]);

const ev = async expr => {
  const r = await cdp.send('Runtime.evaluate', {expression: expr, returnByValue: true});
  if (r.result && r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.text);
  return r.result.result.value;
};

// 等前端自己把 /api/config、外观这些请求跑完
for (let i = 0; i < 20; i++) {
  const st = await ev(`document.readyState + '|' + (document.getElementById('sModel') ? document.getElementById('sModel').textContent : '')`);
  if (st.startsWith('complete') && !st.includes('检查中')) break;
  await new Promise(r => setTimeout(r, 500));
}

console.log('viewport =', width + 'x' + height);
console.log('== 加载后（侧栏应藏在屏幕外）==');
console.log(JSON.stringify(await ev(MEASURE), null, 1));

await ev(`document.getElementById('menu').click(); 'ok'`);
await new Promise(r => setTimeout(r, 400));
const opened = await ev(MEASURE);
console.log('== 点 ☰ 之后 ==');
console.log(JSON.stringify({aside: opened.aside, bodyClass: opened.bodyClass, overflowX: opened.overflowX}, null, 1));

await ev(`document.getElementById('sideBack').click(); 'ok'`);
await new Promise(r => setTimeout(r, 400));
const closed = await ev(MEASURE);
console.log('== 点遮罩收起后 ==');
console.log(JSON.stringify({aside: closed.aside, bodyClass: closed.bodyClass}, null, 1));

cdp.close();
