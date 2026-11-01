import test from 'node:test';
import assert from 'node:assert/strict';
import {armSurface,skinArmPoint} from '../renderer/arm-skin.mjs';
import {puppetPaintPlan} from '../renderer/puppet-art.mjs';
const part={a:[0,0],elbow:[0,150],b:[0,260]};
const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
function surface(angle){
 const c=Math.cos(angle),s=Math.sin(angle);
 return armSurface(part,[1,0,0,1,100,200],[c,s,-s,c,100+s*150,350-c*150]);
}
test('one continuous arm has a shared elbow and preserves width in deep bends',()=>{
 for(const angle of[-Math.PI,-2.5,-1,0,1,2.5,Math.PI]){
  const skinned=surface(angle);
  assert.ok(distance(skinArmPoint(skinned,0,150),[100,350])<1e-8);
  assert.ok(Math.abs(distance(skinArmPoint(skinned,-10,150),skinArmPoint(skinned,10,150))-20)<1e-8,'Elbow must not collapse like matrix blending');
  for(let y=130;y<=170;y+=.1)assert.ok(distance(skinArmPoint(skinned,10,y),skinArmPoint(skinned,10,y+.001))<.02,'No split or jump across the elbow blend');
 }
});
test('shoulder and wrist stay bound to their own bones outside the blend',()=>{
 for(const angle of[-2.5,-1,0,1,2.5]){
  const s=surface(angle);assert.ok(distance(skinArmPoint(s,0,0),[100,200])<1e-8);
  assert.ok(distance(skinArmPoint(s,0,260),[100-Math.sin(angle)*110,350+Math.cos(angle)*110])<1e-8);
 }
});
test('tray covers the supporting palm; only distal gripping fingers overlap props',()=>{
 const layers=['hand-support','hand-cup','hand-fork','cake','cupProp','hand-relaxedR'].map((name,i)=>({name,group:'hand'+i,part:['cake','cupProp'].includes(name)?'prop':'hand'}));
 const plan=puppetPaintPlan({layers}),tray=plan.findIndex(l=>l.name==='cake'),cup=plan.findIndex(l=>l.name==='cupProp');
 assert.equal(plan.filter(l=>l.name==='hand-support').length,1);
 assert.ok(plan.findIndex(l=>l.name==='hand-support')<tray);
 for(const name of['hand-cup','hand-fork']){
  const passes=plan.filter(l=>l.name===name);assert.equal(passes.length,2);
  assert.ok(plan.indexOf(passes[0])<tray);assert.ok(plan.indexOf(passes[1])>cup);
  assert.equal(passes[1].clip,'grasp');assert.equal(passes[1].worldClip,undefined);assert.notEqual(passes[0].group,passes[1].group);
 }
});
