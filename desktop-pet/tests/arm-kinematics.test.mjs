import test from 'node:test';
import assert from 'node:assert/strict';
import {anatomicalArm,solveLimb3D,SHOULDER_ROOTS,handPoseAngle} from '../renderer/arm-kinematics.mjs';
import {actionScene,actionClock} from '../renderer/action-motion.mjs';
import {createPetState,applyAction,advance} from '../renderer/state.mjs';
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
const direction=handPoseAngle;
function arm(scene,side){const key=side==='L'?'left':'right',weights=scene[key+'Grips']||{[scene[key+'Kind']]:1},desired=Object.entries(weights).reduce((n,[kind,w])=>n+direction(kind)*w,0);return anatomicalArm(SHOULDER_ROOTS[side],scene[key],side,scene[key+'Depth'],desired);}
test('production arm keeps upper arm, forearm and palm lengths fixed in 3D',()=>{
 for(const pose of['idle','cake','tea'])for(let t=0;t<11;t+=.025)for(const side of['L','R']){
  const a=arm(actionScene({pose,actionTime:t}),side);assert.ok(Math.abs(distance(a.root,a.elbow)-150)<1e-7);assert.ok(Math.abs(distance(a.elbow,a.wrist)-110)<1e-7);assert.ok(Math.abs(distance(a.wrist,a.grip)-45)<1e-7);assert.ok(a.reachError<.001);
  assert.ok(Math.hypot(a.root[0]-a.elbow[0],a.root[1]-a.elbow[1])<=150.001,'Projection can shorten, never stretch a bone');
 }
});
test('palms stay within 25 degrees of their own forearm through usage and every action pair',()=>{
 for(const from of['idle','cake','tea'])for(const to of['idle','cake','tea']){
  const s={...createPetState(),pose:from,actionTime:4.2};applyAction(s,{type:'pose',id:to});
  for(let frame=0;frame<360;frame++){advance(s,1/120);for(const side of['L','R']){const a=arm(actionScene(s),side);assert.ok(Math.abs(a.wristFlex)<25.01*Math.PI/180,`${from}→${to}/${side}: no wrist reversal`);assert.ok(a.reachError<.002);}}
 }
});
test('anatomical depth places the sipping elbow below the hand rather than above the head',()=>{
 const s=actionScene({pose:'tea',actionTime:4.2}),a=arm(s,'R');assert.ok(a.elbow[0]>a.root[0]&&a.elbow[1]>a.root[1]+30);assert.ok(a.grip[1]<a.elbow[1]-60);
 const b=arm(actionScene({pose:'cake',actionTime:4.2}),'R');assert.ok(b.elbow[1]>b.root[1]&&b.elbow[0]>b.root[0]);
});
test('unreachable coordinates clamp inside the reachable sphere without negative or stretched bones',()=>{
 for(const target of[[0,0,0],[10000,0,0],[0,0,10000]]){const a=solveLimb3D([0,0,0],target,[1,1,0]);assert.ok(a.elbow.every(Number.isFinite)&&a.wrist.every(Number.isFinite));assert.ok(Math.abs(distance(a.root,a.elbow)-150)<1e-7);assert.ok(Math.abs(distance(a.elbow,a.wrist)-110)<1e-7);}
});
