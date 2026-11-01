import test from 'node:test';
import assert from 'node:assert/strict';
import {blinkClosure,BLINK_DURATION,facialTarget} from '../renderer/facial-rig.mjs';
import {createPetState,advance} from '../renderer/state.mjs';
import {exposureSamples} from '../renderer/motion-blur.mjs';
test('blink has complete closure, a hold, and slower reopening with continuous endpoints',()=>{
 assert.equal(blinkClosure(0),0);assert.equal(blinkClosure(.12),1);assert.equal(blinkClosure(.14),1);assert.equal(blinkClosure(BLINK_DURATION),0);
 assert.ok(blinkClosure(.06)>blinkClosure(BLINK_DURATION-.06));
 const frames=Array.from({length:22},(_,i)=>blinkClosure(i/60));
 assert.ok(frames.filter(x=>x>0&&x<1).length>=14);
 assert.ok(Math.max(...frames.slice(1).map((x,i)=>Math.abs(x-frames[i])))<.25);
});
test('interaction expressions ease from the original facial parameters without replacing a texture',()=>{
 const state=createPetState();state.expression='angry';advance(state,.016);
 assert.ok(state.facial[0]<1&&state.facial[0]>facialTarget('angry')[0]);
 state.expression=null;for(let i=0;i<60;i++)advance(state,.016);
 assert.ok(Math.abs(state.facial[0]-1)<.001);
});
test('short exposure covers gaze, blinking, body motion and dragging; disabled and static frames stay sharp',()=>{
 const before={...createPetState(),time:1,motionTime:1};
 const still={...before,time:1.016,motionTime:1.016};
 assert.equal(exposureSamples(before,still,{hairMotion:false}).length,1);
 for(const patch of[{gaze:{x:1,y:0}},{blink:.4},{facial:facialTarget('angry')},{dragVelocity:{x:1000,y:-400}}]){
  const samples=exposureSamples(before,{...still,...patch},{hairMotion:false});
  assert.equal(samples.length,3);assert.equal(samples.reduce((n,s)=>n+s.weight,0),1);
  assert.ok(samples.every(s=>Math.abs(s.x)<=16&&Math.abs(s.y)<=16));
 }
 assert.equal(exposureSamples(before,still,{}).length,3);
 assert.equal(exposureSamples(before,{...still,blink:.5},{motionBlur:false}).length,1);
 assert.equal(exposureSamples(before,{...still,time:3,blink:.5},{}).length,1);
});
