// Regression checks for queue release and interrupted synthesis, without a TTS model.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const html = fs.readFileSync(new URL('../app/agent.html', import.meta.url), 'utf8');
const source = html.slice(html.indexOf('async function synthChunk('), html.indexOf('/* 队列排空'));
let requests = [];
const sp = {on:true, generation:1, controllers:new Set(), parts:[], active:0, audio:new Map(), failed:0};
const context = {
  sp, SP_CONC:1, AbortController, setTimeout, clearTimeout,
  fetch: async (_url, options) => new Promise((resolve, reject) => {
    requests.push({resolve: () => resolve({ok:true, arrayBuffer:async () => new ArrayBuffer(16)}), reject});
    options.signal.addEventListener('abort', () => reject(new Error('aborted')));
  }),
  pumpSpeech(){}, speechMaybeDone(){}, pickTone(){return 'calm';}
};
vm.createContext(context);
vm.runInContext(source + '\nthis.synthChunk = synthChunk;', context);
const waitFor = async (check) => {
  for(let i=0; i<50 && !check(); i++) await new Promise(r=>setTimeout(r,10));
  assert.ok(check(), 'queue did not advance');
};
const first = context.synthChunk('第一句。',0,'calm');
const second = context.synthChunk('第二句。',1,'calm');
await waitFor(()=>requests.length===1);
requests[0].resolve(); await first;
assert.equal(sp.active,0, 'successful synthesis must release the queue');
await waitFor(()=>requests.length===2);
requests[1].resolve(); await second;
assert.equal(sp.active,0);
assert.equal(sp.audio.size,2);

const old = context.synthChunk('旧回复。',2,'calm');
await waitFor(()=>requests.length===3);
sp.generation++;
sp.controllers.forEach(c=>c.abort()); sp.controllers.clear();
sp.active=0; sp.audio.clear();
const fresh = context.synthChunk('新回复。',0,'calm');
await waitFor(()=>requests.length===4);
await old;
assert.equal(sp.active,1, 'old reply must not release a new reply slot');
assert.equal(sp.audio.size,0, 'old audio must not enter a new reply');
requests[3].resolve(); await fresh;
assert.equal(sp.active,0);
assert.equal(sp.audio.size,1);
console.log('PASS: queue advances; interrupted audio cannot contaminate a new reply');

const decoding = [], scheduled = [];
const playbackState = {on:true, generation:1, next:0, audio:new Map([[0,new ArrayBuffer(4)]]), decoded:new Map()};
const playback = {sp:playbackState,
  speechCtx:()=>({state:'running', decodeAudioData:()=>new Promise(resolve=>decoding.push(resolve))}),
  scheduleBuffer:(buffer)=>scheduled.push(buffer), revealUpTo(){}, sayState(){}};
vm.createContext(playback);
vm.runInContext(html.slice(html.indexOf('let spPumping ='),html.indexOf('function speechFeed(')) + '\nthis.pumpSpeech = pumpSpeech;',playback);
const pending = playback.pumpSpeech();
await waitFor(()=>decoding.length===1);
playbackState.generation++;
playbackState.next=0;
playbackState.audio=new Map([[0,new ArrayBuffer(8)]]);
await playback.pumpSpeech();
decoding[0]('old'); await pending;
await waitFor(()=>decoding.length===2);
assert.deepEqual(scheduled,[],'old decoded audio must not be scheduled');
decoding[1]('new');
await waitFor(()=>scheduled.length===1);
assert.deepEqual(scheduled,['new']);
console.log('PASS: interrupted audio decoding is discarded; the new queue resumes');

const chunkState={buf:'',chunks:0,lastLen:0};
const chunks={sp:chunkState,SP_FIRST:28,SP_CHUNK:120,SP_GROW:1.5,SP_HARD:180,SP_MINLEN:48,fenceOdd:()=>false};
vm.createContext(chunks);
vm.runInContext(html.slice(html.indexOf('function takeChunk('),html.indexOf('async function synthChunk('))+'\nthis.takeChunk=takeChunk;',chunks);
const phrase='亲爱的，我查了下。周杰伦的《听妈妈的话》和周品的《我的未来不是梦》应该也符合你的口味。';
const emitted=[];
for(const char of phrase){
  chunkState.buf+=char;
  const part=chunks.takeChunk(false);
  if(part){emitted.push(part);chunkState.chunks++;}
}
const rest=chunks.takeChunk(true);if(rest)emitted.push(rest);
assert.equal(emitted.join(''),phrase,'streaming must retain every character');
assert.ok(emitted[0].length>=12,'a short greeting must not become its own TTS request');
assert.ok(emitted.every(part=>!part.endsWith('《')),'do not stop at an opening song title mark');
chunkState.buf='晚安。';chunkState.chunks=0;
assert.equal(chunks.takeChunk(false),null);
assert.equal(chunks.takeChunk(true),'晚安。','short complete replies must still be spoken');
console.log('PASS: song recommendations retain text; short intros stay with their sentence');
