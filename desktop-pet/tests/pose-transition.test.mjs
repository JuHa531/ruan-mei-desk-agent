import test from 'node:test';
import assert from 'node:assert/strict';
import {createPetState,applyAction,advance} from '../renderer/state.mjs';
import {ACTIONS,actionScene,solveArm,actionSpeed} from '../renderer/action-motion.mjs';
import {poseIsChanging} from '../renderer/pose-transition.mjs';
import {exposureSamples} from '../renderer/motion-blur.mjs';
import {sampleSkeleton,BONE,transform} from '../renderer/skeleton.mjs';
import host from '../electron/host-policy.cjs';
import {forkTip,attachment,CUP_GRIP,CUP_SUPPORT,DESSERT_SUPPORT} from '../renderer/daily-actions.mjs';
const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const tick=(s,seconds,settings={})=>{for(let i=0;i<seconds*120;i++)advance(s,1/120,settings);};
test('dessert stays attached to the supporting palm throughout its reachable side carry',()=>{
 const s=createPetState();applyAction(s,{type:'pose',id:'cake'});
 const points=[];for(let t=0;t<=2.2;t+=1/120){const scene=actionScene({...s,actionTime:t});if(scene.prop.opacity>.5){points.push(scene.prop.x);assert.ok(distance(scene.left,[scene.prop.x+DESSERT_SUPPORT[0],scene.prop.y+DESSERT_SUPPORT[1]])<.01,'Never slide the tray independently across its supporting hand');}assert.equal(scene.bite,null);}
 assert.ok(Math.max(...points)-Math.min(...points)>85,'Carry inward from a reachable shelf, without extending the support arm down and outward');tick(s,2.4);assert.equal(poseIsChanging(s),false);
 const hold=actionScene(s);assert.ok(distance(hold.left,attachment(hold.prop,DESSERT_SUPPORT))<1);
});
test('fork enters the cake downward from above, lifts a bite, and withdraws after eating',()=>{
 const s={...createPetState(),pose:'cake'};
 const scoop=actionScene({...s,actionTime:2.85}),bite=actionScene({...s,actionTime:4.2}),chew=actionScene({...s,actionTime:4.7}),rest=actionScene({...s,actionTime:8});
 assert.ok(scoop.bite&&scoop.bite.y<scoop.prop.y-60);assert.ok(bite.bite&&distance([bite.bite.x,bite.bite.y],[491,585])<3&&bite.mouthOpen>.99);
 assert.equal(chew.bite,null);assert.ok(chew.chew>0);assert.ok(rest.right[1]>rest.prop.y+80&&rest.mouthOpen===0,'Lower the fork hand clear of the supporting palm during the quiet hold');
 let lastTip;for(let t=1.9;t<2.5;t+=1/120){const scene=actionScene({...s,actionTime:t}),tip=forkTip(scene.fork);assert.ok(scene.right[1]<tip[1]-70,'Fingers hold the handle above the downward-pointing tines');if(lastTip)assert.ok(tip[1]>=lastTip[1]);lastTip=tip;}
 for(let t=2.7;t<4.2;t+=.1){const scene=actionScene({...s,actionTime:t});assert.ok(distance(forkTip(scene.fork),[scene.bite.x,scene.bite.y])<1e-8,'Food follows the real tines rather than an unrelated fixed offset');}
 const repeated=actionScene({...s,actionTime:14.7}).bite;assert.ok(distance([bite.bite.x,bite.bite.y],[repeated.x,repeated.y])<1e-8);
});
test('cup materializes after the hands arrive, then periodically reaches and leaves the lips',()=>{
 const s=createPetState();applyAction(s,{type:'pose',id:'tea'});
 const hidden=actionScene(s),forming=actionScene({...s,actionTime:.7});assert.equal(hidden.prop.opacity,0);assert.ok(forming.prop.opacity>0&&forming.prop.opacity<1&&forming.materialize>0);
 tick(s,1.6);assert.equal(poseIsChanging(s),false);
 const hold=actionScene({...s,poseMotion:null,actionStartedAt:0,actionTime:0}),sip=actionScene({...s,poseMotion:null,actionStartedAt:0,actionTime:4}),rest=actionScene({...s,poseMotion:null,actionStartedAt:0,actionTime:8});
 assert.ok(hold.prop.y-sip.prop.y>120&&sip.sip>.99);assert.equal(rest.prop.y,hold.prop.y);
 for(let t=0;t<10;t+=.05){const current=actionScene({...s,poseMotion:null,actionStartedAt:0,actionTime:t});assert.ok(distance(current.right,attachment(current.prop,CUP_GRIP))<1e-8);assert.equal(current.leftKind,'support');assert.equal(current.cupSupport,1);assert.ok(distance(current.left,attachment(current.prop,CUP_SUPPORT))<1e-8,'Support palm follows the cup base through the full lift, not the crossed-hands idle target');}
});

test('canceling a partly formed cup preserves its first frame and finishes the grip approach',()=>{
 const s=createPetState();applyAction(s,{type:'pose',id:'tea'});tick(s,.74);const before=actionScene(s);assert.ok(before.prop.opacity>0&&before.prop.opacity<1);
 applyAction(s,{type:'pose',id:'idle'});const after=actionScene(s);
 assert.ok(distance(before.right,after.right)<1e-8);assert.ok(distance(before.left,after.left)<1e-8);
 tick(s,.2);const lowering=actionScene(s);assert.ok(distance(lowering.right,attachment(lowering.prop,CUP_GRIP.map(v=>v*lowering.prop.scale)))<1e-6);
 assert.ok(distance(lowering.left,attachment(lowering.prop,CUP_SUPPORT.map(v=>v*lowering.prop.scale)))<1e-6);assert.equal(lowering.cupSupport,1);
});

test('the supporting hand stays under the cup until the cup is put down and gone',()=>{
 const s={...createPetState(),pose:'tea',actionTime:4.2};applyAction(s,{type:'pose',id:'idle'});
 for(let i=0;i<125;i++){const scene=actionScene(s);if(scene.prop?.opacity>.01){assert.equal(scene.leftKind,'support');assert.ok(scene.cupSupport>.99);assert.ok(distance(scene.left,attachment(scene.prop,CUP_SUPPORT.map(v=>v*(scene.prop.scale||1))))<1e-6);}advance(s,1/120);}
 tick(s,2);assert.equal(actionScene(s).leftKind,'relaxedL');
});

test('canceling before a prop appears does not wait through an invisible put-away action',()=>{
 for(const id of['cake','tea']){const s=createPetState();applyAction(s,{type:'pose',id});tick(s,.2);assert.equal(actionScene(s).prop.opacity,0);applyAction(s,{type:'pose',id:'idle'});tick(s,1.05);assert.equal(poseIsChanging(s),false);assert.equal(actionScene(s).prop,null);}
});
test('all action pairs and rapid interruptions preserve hand positions with no queue',()=>{
 for(const from of ACTIONS)for(const to of ACTIONS){const s={...createPetState(),pose:from,actionTime:4.2};const before=actionScene(s);applyAction(s,{type:'pose',id:to});const after=actionScene(s);
  assert.ok(distance(before.left,after.left)<1e-8&&distance(before.right,after.right)<1e-8,`${from} to ${to}`);tick(s,4);assert.equal(poseIsChanging(s),false);assert.equal(s.pose,to);}
 const s=createPetState();for(let i=0;i<30;i++){tick(s,.15);const before=actionScene(s);applyAction(s,{type:'pose',id:ACTIONS[(i+1)%4]});const after=actionScene(s);assert.ok(distance(before.left,after.left)<1e-8&&distance(before.right,after.right)<1e-8);assert.ok(!s.poseMotion?.queue);}
});
test('two-bone limbs retain exact lengths through all poses including unreachable targets',()=>{
 for(const pose of ACTIONS)for(let t=0;t<11;t+=.03){const scene=actionScene({pose,actionTime:t});for(const[root,target,bend]of[[[423,697],scene.left,1],[[620,697],scene.right,scene.rightBend]]){const arm=solveArm(root,target,bend);assert.ok(Math.abs(distance(arm.root,arm.elbow)-150)<1e-7&&Math.abs(distance(arm.elbow,arm.hand)-165)<1e-7);}}
 const arm=solveArm([0,0],[10000,0],1);assert.ok(distance(arm.root,arm.hand)<315);
});
test('daily idle has small hand and rigid body rotations; disabling idle stops the usage loops',()=>{
 const hands=Array.from({length:180},(_,i)=>actionScene({pose:'idle',actionTime:i/20}));const travel=Math.max(...hands.map(s=>s.left[0]))-Math.min(...hands.map(s=>s.left[0]));assert.ok(travel>.5&&travel<3);
 for(const s of hands){assert.ok(s.left[0]>s.right[0]&&Math.abs(s.left[1]-s.right[1])<15,'Palms remain softly crossed, not swinging apart');assert.ok(s.left[1]>880&&s.left[1]<915);}
 const a=sampleSkeleton(0),b=sampleSkeleton(2);assert.ok(distance(transform(a.matrices[BONE.chest],500,750),transform(b.matrices[BONE.chest],500,750))>.3);
 for(const pose of ACTIONS){const s={pose,actionTime:1};assert.deepEqual(actionScene(s,1,{hairMotion:false}),actionScene(s,8,{hairMotion:false}));}
});
test('action speed has a continuous clock, validated settings, and does not change gaze/blink timing',()=>{
 for(const value of[undefined,NaN,Infinity,'1',0,.8,1,3])assert.equal(actionSpeed({actionSpeed:value}),host.sanitizeSettings({actionSpeed:value}).actionSpeed);
 const a=createPetState(),b=createPetState();tick(a,2,{actionSpeed:.6});tick(b,2,{actionSpeed:1.6});assert.equal(a.blink,b.blink);assert.ok(b.actionTime>a.actionTime*2.5);const before=a.actionTime;advance(a,0,{actionSpeed:1.6});assert.equal(a.actionTime,before);
});
test('short exposure samples action time during movement and leaves a quiet hold sharp',()=>{
 const s=createPetState();applyAction(s,{type:'pose',id:'cake'});tick(s,.9);const previous=structuredClone(s);advance(s,1/60,{hairMotion:false});
 const samples=exposureSamples(previous,s,{hairMotion:false});assert.equal(samples.length,3);assert.ok(samples[0].state.actionTime<samples[2].state.actionTime);
 assert.equal(exposureSamples(previous,s,{motionBlur:false}).length,1);tick(s,4,{hairMotion:false});const settled=structuredClone(s);advance(s,1/60,{hairMotion:false});assert.equal(exposureSamples(settled,s,{hairMotion:false}).length,1);
});

test('visible motion keeps temporal blur while subpixel idle sway avoids redundant full renders',()=>{
 const previous=createPetState(),s=structuredClone(previous);advance(s,1/60);
 assert.equal(exposureSamples(previous,s,{}, {pixels:.05,scale:.25}).length,1);
 assert.equal(exposureSamples(previous,s,{}, {pixels:8,scale:.25}).length,3);
 const slow=structuredClone(previous);advance(slow,1/20);
 const samples=exposureSamples(previous,slow,{}, {pixels:20,scale:.25});assert.equal(samples.length,2);
 assert.ok(Math.abs(samples.reduce((v,s)=>v+s.weight,0)-1)<1e-8);
 assert.equal(samples.at(-1).state.time,slow.time);assert.ok(samples[0].state.time<slow.time);
});
