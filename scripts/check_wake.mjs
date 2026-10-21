// 验证唤醒词：说到「亲爱的」时
//   ① 只说这两个字 → 梅梅立刻答应，**不打模型**（数一下 /api/agent 的请求数）
//   ② 后面带要求 → 照常走完整流程（会打模型）
//   ③ 回复里不该把「亲爱的」理解错（服务端加的那句提示在起作用）
//
// 用法：先起无头 Edge，再 node check_wake.mjs [url]

const PORT = Number(process.env.CDP_PORT || 9222);
const URL_ = process.argv[2] || 'http://127.0.0.1:7788/';
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
  if (r.result && r.result.exceptionDetails) return 'EXC: ' + r.result.exceptionDetails.text;
  return r.result.result.value;
};
const p = cdp.once('Page.loadEventFired');
await cdp.send('Page.navigate', {url: URL_});
await Promise.race([p, sleep(8000)]);
await sleep(1500);

await ev(`(() => {
  window.__agent = 0;
  if (!window.__of) window.__of = window.fetch;
  window.fetch = function(...a) {
    if (String(a[0]).indexOf('/api/agent') >= 0) window.__agent++;
    return window.__of.apply(this, a);
  };
  localStorage.setItem('rm_sessions', '[]');
  return 'hooked';
})()`);

const say = async text => {
  await ev(`(() => {
    const t = document.getElementById('inp');
    t.value = ${JSON.stringify('')} + ${JSON.stringify(text)};
    document.getElementById('send').click();
    return 'sent';
  })()`);
};
const last = () => ev(`(() => {
  const s = JSON.parse(localStorage.getItem('rm_sessions') || '[]');
  const it = (s[0] && s[0].items) || [];
  const a = it.filter(x => x.role === 'assistant').slice(-1)[0];
  const u = it.filter(x => x.role === 'user').slice(-1)[0];
  return JSON.stringify({你说: u && u.text, 她答: a && a.text});
})()`);

console.log('---- ① 只说唤醒词 ----');
await say('亲爱的');
await sleep(2500);
console.log('聊天记录 :', await last());
console.log('打了模型吗:', await ev('window.__agent'), '次（0 = 没打，直接答应的）');

console.log('\n---- ② 唤醒词 + 要求 ----');
await say('亲爱的，一句话说清你是谁。');
await sleep(30000);
console.log('聊天记录 :', await last());
console.log('打了模型吗:', await ev('window.__agent'), '次（≥1 = 走了完整流程）');

cdp.close();
