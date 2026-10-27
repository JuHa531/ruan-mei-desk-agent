// Role-aware tone, reply-based sticker matching, and replay timing regressions.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const html=fs.readFileSync(new URL('../app/agent.html',import.meta.url),'utf8');
const stickerItems=JSON.parse(fs.readFileSync(new URL('../app/assets/stickers.json',import.meta.url),'utf8'));
const ctx={stickerItems};vm.createContext(ctx);
vm.runInContext(html.slice(html.indexOf('function pickTone('),html.indexOf('const player = new Audio'))+
  html.slice(html.indexOf('function pickSticker('),html.indexOf('function fillStickerGrid('))+
  '\nthis.tone=pickTone;this.sticker=pickSticker;',ctx);
assert.equal(ctx.tone('我喜欢这首歌','亲爱的，我喜欢这段旋律呢。'),'calm');
assert.equal(ctx.tone('奖励机制报错','亲爱的，检查命令返回了错误。'),'calm');
assert.equal(ctx.tone('','亲爱的，晚安。好好休息。'),'warm');
assert.equal(ctx.tone('','亲爱的，做得不错。要什么奖励，可以慢慢想。'),'wry');
assert.equal(ctx.tone('','亲爱的，没有奖励。'),'calm');
console.log('PASS: restrained role tone; ordinary particles do not trigger excitement');

const mood=(user,reply)=>ctx.sticker(user,reply)?.mood ?? null;
assert.equal(mood('我好累','亲爱的，我在听。慢慢说。'),'倾听','user sentiment must not override reply');
assert.equal(mood('为什么这么累','亲爱的，先停一会儿，喝杯清茶。'),'悠闲');
assert.equal(mood('我无语了','亲爱的，已经整理完成。'),'认可');
assert.equal(mood('','亲爱的，没有疑惑，一切已经安排好了。'),'认可');
assert.equal(mood('','亲爱的，还没完成，需要确认哪一个？'),'疑惑');
assert.equal(mood('','亲爱的，晚安。好好休息。'),'晚安');
assert.equal(mood('','亲爱的，要什么奖励？'),'疑问');
assert.equal(mood('','亲爱的，我记得。'),'倾听','ordinary replies have a quiet default');
assert.equal(mood('','亲爱的，《晚安》已经播放。'),'悠闲','song titles must not classify farewell');
assert.equal(ctx.sticker('','亲爱的，先喝杯清茶。').blush,false,
  'prefer an unblushed alternative within the same reply intent');
assert.equal(mood('','```python\nprint("hi")\n```'),null);
assert.equal(mood('家人去世了','亲爱的，我在听。'),null);
assert.equal(mood('','（连接失败：timeout）'),null);
assert.equal(mood('发个无语表情包',''),'无语');
console.log('PASS: stickers follow reply meaning, with quoted-title and sensitive-context handling');

const speech={sp:{on:true,buf:'',tone:'',userText:'',chunks:0,lastLen:0,seq:0},
  SP_FIRST:28,SP_CHUNK:120,SP_GROW:1.5,SP_HARD:180,SP_MINLEN:48,fenceOdd:()=>false,
  pickTone:ctx.tone,synthChunk(){}};
vm.createContext(speech);
vm.runInContext(html.slice(html.indexOf('function takeChunk('),html.indexOf('async function synthChunk('))+
  html.slice(html.indexOf('function speechFeed('),html.indexOf('/* 用户第一次点击'))+
  '\nthis.feed=speechFeed;this.finish=speechFinish;',speech);
speech.feed('亲');assert.equal(speech.sp.tone,'','do not lock tone from the first token');
speech.feed('爱的，晚安。好好休息，明天再慢慢安排。');speech.finish();
assert.equal(speech.sp.tone,'warm');
console.log('PASS: streaming waits for meaningful text before selecting tone');

const buffer=()=>{const data=new Float32Array(1000);data.fill(.5,100,801);return {sampleRate:1000,length:1000,getChannelData:()=>data};};
let cached;
const cache={SP_SEAM:Number(html.match(/const SP_SEAM\s*=\s*([\d.]+)/)[1]),SP_FADE:.025,sp:{cached:false,fullText:'我在听，慢慢说。',tone:'calm',
  decoded:new Map([[0,buffer()],[1,buffer()]]),parts:['我在听，','慢慢说。'],
  ctx:{createBuffer:(_channels,n,sr)=>{const data=new Float32Array(n);return {length:n,sampleRate:sr,getChannelData:()=>data};}}},
  cachePut:(_key,value)=>cached=value,ttsKey:()=>''};
vm.createContext(cache);
vm.runInContext(html.slice(html.indexOf('function trimSilence('),html.indexOf('/* 从缓冲区里切'))+
  html.slice(html.indexOf('function speechPause('),html.indexOf('/* 把一块音频排到时间轴上'))+
  '\nthis.save=cacheStreamedSpeech;this.pause=speechPause;',cache);
assert.equal(cache.pause('“晚安。”'),cache.SP_SEAM);
assert.equal(cache.pause('稍等，'),.42);
cache.save();assert.equal(cached.buffer.length,2142,'replay must use trimmed frames and actual comma pause');
console.log('PASS: replay preserves the same trimmed audio and punctuation pauses as live playback');
