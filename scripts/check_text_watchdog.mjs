// 验证：语音合成卡住（不出声）时，文字还会不会出来。
// 模拟方式：开始一次流式朗读，喂进"模型已经产出的文字"，但不给任何音频。
// 看 8 秒后 asst.shown 有没有被看门狗推出来。

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

const before = await ev(`JSON.stringify({shown: (cur() && cur().items.slice(-1)[0] || {}).shown || '',
  提示: document.getElementById('sayState').textContent})`);
console.log('模拟前 :', before);

console.log(await ev(`(() => {
  window.__seen = [];
  sp.revealFn = (s) => { window.__seen.push(s); };
  speechBegin();                       // 开始朗读（但永远不给音频）
  sp.parts = ['这是模型已经写出来的第一句。', '这是第二句。'];
  return '模拟：文字已到、语音不来';
})()`));

for (const t of [3000, 6000, 9000, 12000]) {
  await sleep(t === 3000 ? 3000 : 3000);
  console.log(`  ${t}ms :`, await ev(`JSON.stringify({
    已推出的文字: window.__seen.join(''),
    提示: document.getElementById('sayState').textContent})`));
}

console.log(await ev(`(() => { speechAbort(); return '收尾'; })()`));
cdp.close();
