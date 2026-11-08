import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const html=fs.readFileSync(new URL('../app/agent.html',import.meta.url),'utf8');
const code=html.slice(html.indexOf('let manualSpeech ='),html.indexOf('/* ---------------- 流式朗读'));
let fetchCount=0,putCount=0;const player={play:async()=>{},pause(){},onended:null};
const c={sp:{on:false},player,AbortController,setTimeout,clearTimeout,URL,Blob,document:{querySelectorAll:()=>[]},
 toast(){},sayState(){},pickTone:()=> 'calm',ttsKey:t=>t,cacheGet:()=>null,cachePut:()=>putCount++,bgHoldStart:()=>0,bgHoldEndNow(){},
 fetch:async()=>{fetchCount++;return {ok:true,blob:async()=>new Blob(['audio'])}}};vm.createContext(c);
vm.runInContext(code+'\nthis.speak=speak;this.speechOccupied=speechOccupied;',c);
const a=c.speak('第一句');await new Promise(r=>setTimeout(r,10));assert.equal(c.speechOccupied(),true);
await c.speak('第二句');assert.equal(fetchCount,1);assert.equal(putCount,1);
player.onended();await a;assert.equal(c.speechOccupied(),false);
c.sp.on=true;await c.speak('流式期间不得重播');assert.equal(fetchCount,1);
console.log('PASS manual playback stays locked until ended; blocks replay during stream');
let cached=0;const d={sp:{cached:false,fullText:'第一句。第二句。',ctx:{},failed:0,active:0,buf:'',seq:2,parts:['第一句。','第二句。'],decoded:new Map([[0,{}]])},cachePut(){cached++}};
vm.createContext(d);vm.runInContext(html.slice(html.indexOf('function cacheStreamedSpeech(){'),html.indexOf('/* 把一块音频排到时间轴上'))+'\ncacheStreamedSpeech();',d);assert.equal(cached,0);assert.equal(d.sp.cached,false);
console.log('PASS incomplete streamed speech cannot become a full reply replay cache');
const t={};vm.createContext(t);vm.runInContext(html.slice(html.indexOf('function trimSilence(buffer){'),html.indexOf('/* 从缓冲区'))+'\nthis.trimSilence=trimSilence;',t);
const samples=new Float32Array(1000);samples[200]=.2;samples[998]=.0001;
assert.equal(t.trimSilence({sampleRate:1000,getChannelData:()=>samples}).end,1000);
console.log('PASS quiet final phonemes retained');
