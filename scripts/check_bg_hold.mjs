// 走一次真实的问答流程（真发消息 + 真流式朗读），每 2 秒采一次背景视频的状态，
// 看它到底是被"让路"机制按住了，还是自己卡住的。
//
// 用法：先起无头 Edge（--autoplay-policy=no-user-gesture-required），再
//   node check_bg_hold.mjs [url] ["要问的问题"]

const PORT = Number(process.env.CDP_PORT || 9222);
const URL_ = process.argv[2] || 'http://127.0.0.1:7788/';
const QUESTION = process.argv[3] || '你是谁？一句话就行。';
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

console.log('让路开关 :', await ev(`JSON.stringify({
  开关勾了: document.getElementById('pauseBgChk').checked,
  分块朗读: document.getElementById('streamChk').checked,
  自动朗读: document.getElementById('voice').classList.contains('on')})`));

// 把问题填进输入框并点发送（跟真人操作同一条路）
await ev(`(() => {
  const t = document.getElementById('inp');
  t.value = ${JSON.stringify(QUESTION)};
  document.getElementById('send').click();
  return 'sent';
})()`);

const sample = () => ev(`(() => {
  const v = document.getElementById('bglayer').querySelector('video');
  return JSON.stringify({
    t: Math.round(performance.now() / 100) / 10,
    paused: v ? v.paused : null,
    hold: v ? (v.dataset.hold || '') : '',
    位置秒: v ? Math.round(v.currentTime * 10) / 10 : null,
    readystate: v ? v.readyState : null,
    正在合成: sp.active, 已排到: sp.next, 已送合成: sp.seq,
    状态: document.getElementById('sayState').textContent,
    发送键: document.getElementById('send').disabled ? '忙' : '空闲',
  });
})()`);

for (let i = 0; i < 45; i++) {
  await sleep(2000);
  console.log(await sample());
  const st = await ev(`document.getElementById('send').disabled ? 'busy' : 'idle'`);
  const held = await ev(`(() => { const v = document.getElementById('bglayer').querySelector('video');
     return v && (v.paused || v.dataset.hold === '1') ? 'held' : 'free'; })()`);
  if (st === 'idle' && held === 'free') {
    console.log('已经回到空闲、背景也自由了');
    break;
  }
}

console.log('\n---- 最终 ----');
console.log(await sample());
cdp.close();
