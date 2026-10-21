// 验证两件事（都不用耳朵听）：
//   ① 点「重播」第二次是不是直接用缓存 —— 数一下 /api/tts 到底被打了几次；
//   ② 朗读期间背景视频有没有被按住（dataset.hold='1' 且 paused=true），说完有没有放开。
//   ③ 顺带验证流式朗读读完之后，分块音频会被拼成一条缓存起来。
//
// 用法：先起无头 Edge（带 --autoplay-policy=no-user-gesture-required），再
//   node check_voice_cache.mjs [url]

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
const load = async () => {
  const p = cdp.once('Page.loadEventFired');
  await cdp.send('Page.navigate', {url: URL_});
  await Promise.race([p, sleep(8000)]);
  await sleep(1500);
};

await load();

// 塞一条现成的会话进去（省得为了测试真跑一轮模型），然后重载
await ev(`localStorage.setItem('rm_sessions', JSON.stringify([{
  id: 't1', title: '缓存自检', opener: '…',
  items: [{role: 'user', text: '测试'},
          {role: 'assistant', text: '这是一句用来测重播缓存的短句。', done: true}]
}])); 'ok'`);
await load();

// 数 /api/tts 的调用次数
await ev(`(() => {
  window.__tts = 0;
  if (!window.__origFetch) window.__origFetch = window.fetch;
  window.fetch = function(...a) {
    if (String(a[0]).indexOf('/api/tts') >= 0) window.__tts++;
    return window.__origFetch.apply(this, a);
  };
  return 'hooked';
})()`);

const btn = `(() => {
  const bs = [...document.querySelectorAll('.opts button')];
  const b = bs.find(x => x.textContent.indexOf('重播') >= 0);
  if (b) b.click();
  return !!b;
})()`;
console.log('找到「重播」按钮 :', await ev(btn));
// 合成要几秒，这里在请求还在飞的时候采样，才能抓到"背景被按住"的状态
for (const ms of [200, 500, 1200]) {
  await sleep(ms === 200 ? 200 : ms - 200);
  console.log(`  点后 ${ms}ms —— 背景视频 :`, await ev(`(() => {
  const v = document.getElementById('bglayer').querySelector('video');
  return v ? JSON.stringify({paused: v.paused, hold: v.dataset.hold || ''}) : '(没有视频)';
})()`));
}
console.log('第一次点击后 —— /api/tts 次数 :', await ev('window.__tts'));

// 等它念完（短句 + 本地合成，一般几秒）
for (let i = 0; i < 40; i++) {
  await sleep(1000);
  const st = await ev(`document.getElementById('sayState').textContent`);
  if (!st) break;
}
console.log('念完之后 —— 背景视频 :', await ev(`(() => {
  const v = document.getElementById('bglayer').querySelector('video');
  return v ? JSON.stringify({paused: v.paused, hold: v.dataset.hold || ''}) : '(没有视频)';
})()`));

const before = await ev('window.__tts');
console.log('第二次点击（应该吃缓存）:', await ev(btn));
await sleep(3000);
const after = await ev('window.__tts');
console.log(`再点一次后 —— /api/tts 次数 : ${after}（这次新增 ${after - before}，0 = 走了缓存）`);

// 流式朗读那条路：喂两块真音频，看读完会不会拼成一条缓存
console.log('\n---- 流式朗读缓存 ----');
await ev(`(() => {
  speechBegin();
  sp.fullText = '第一句测试。第二句测试。';   // 必须在 speechBegin 之后设：它会清空
  synthChunk('第一句测试。', sp.seq++);       // 真实流程里序号也是调用方递增的
  synthChunk('第二句测试。', sp.seq++);
  return 'started';
})()`);
for (let i = 0; i < 40; i++) {
  await sleep(1000);
  if (await ev('sp.cached')) break;
}
console.log('缓存状态 :', await ev(`JSON.stringify({
  cached: sp.cached, decoded: sp.decoded.size,
  kind: (ttsCache.get(ttsKey(sp.fullText)) || {}).kind || '(没有缓存)',
  缓存条数: ttsCache.size
})`));

cdp.close();
