// 看看界面上的"外观"到底生效了没有：侧栏那行字、背景是图还是视频、视频有没有真的在放。
//
// 用法：node check_appearance.mjs [url]        （需要先起一个带调试端口的无头 Edge）

const PORT = Number(process.env.CDP_PORT || 9222);
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
await Promise.race([loaded, new Promise(r => setTimeout(r, 10000))]);
await new Promise(r => setTimeout(r, 3000));      // 给视频一点加载时间

const ev = async (expr, awaitPromise = false) => {
  const r = await cdp.send('Runtime.evaluate',
    {expression: expr, returnByValue: true, awaitPromise});
  if (r.result && r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.text);
  return r.result.result.value;
};

console.log('侧栏那行字 :', await ev(`document.querySelector('.brand small').textContent`));
console.log('背景元素   :', await ev(`(() => {
  const b = document.getElementById('bglayer');
  const v = b.querySelector('video');
  if (v) return 'video  ' + (v.currentSrc || v.src).split('/').pop();
  const i = b.querySelector('img');
  return i ? 'image  ' + (i.src || '').split('/').pop() : '(空)';
})()`));
console.log('视频状态   :', await ev(`(() => {
  const v = document.getElementById('bglayer').querySelector('video');
  if (!v) return '(不是视频背景)';
  return JSON.stringify({readyState: v.readyState, 宽: v.videoWidth, 高: v.videoHeight,
                         时长秒: Math.round(v.duration * 10) / 10, 静音: v.muted,
                         循环: v.loop, 暂停: v.paused, 已播秒: Math.round(v.currentTime * 10) / 10});
})()`));
console.log('外观配置   :', JSON.stringify(await ev(
  `fetch('/api/config').then(r => r.json()).then(c =>
     ({bg_type: c.bg_type, bg_file: c.bg_file, 图标: c.icon}))`, true)));
console.log('三块面板   :', await ev(`(() => {
  const cs = s => getComputedStyle(document.querySelector(s)).backgroundColor;
  const v  = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  return JSON.stringify({顶栏: cs('header'), 底部: cs('footer'),
                         侧栏左边缘: v('--side-a0'), 侧栏右边缘: v('--side-a1')});
})()`));
console.log('滑块位置   :', await ev(`(() => {
  const g = i => (document.getElementById(i) || {}).value;
  return JSON.stringify({左栏: g('sideOp'), 底部: g('footOp'), 顶栏: g('headOp'),
                         融入: g('blend'), 明暗: g('dim')});
})()`));

// 循环测试：跳到快结束的位置，看它会不会自己绕回开头接着放。
// 正常表现：currentTime 变小（绕回 0 附近）、paused=false、ended 事件一次都没触发。
await ev(`(() => {
  const v = document.getElementById('bglayer').querySelector('video');
  if (!v) return 'no video';
  window.__loop = {ended: 0, err: null};
  v.addEventListener('ended', () => window.__loop.ended++);
  v.addEventListener('error', () => window.__loop.err = (v.error || {}).code);
  v.currentTime = Math.max(0, v.duration - 0.5);   // 贴近结尾，省得等它慢慢解码
  return 'seeking';
})()`);
await new Promise(r => setTimeout(r, 9000));
console.log('循环测试   :', await ev(`(() => {
  const v = document.getElementById('bglayer').querySelector('video');
  if (!v) return '(不是视频背景)';
  return JSON.stringify({时长: Math.round(v.duration * 10) / 10,
                         现在位置: Math.round(v.currentTime * 10) / 10,
                         暂停: v.paused, 已结束: v.ended,
                         ended事件: window.__loop.ended, 错误码: window.__loop.err});
})()`));

cdp.close();
