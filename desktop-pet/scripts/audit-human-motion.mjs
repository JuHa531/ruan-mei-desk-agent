import {anatomicalArm,SHOULDER_ROOTS,handPoseAngle,angleDifference} from '../renderer/arm-kinematics.mjs';
import {actionScene} from '../renderer/action-motion.mjs';
import {createPetState,applyAction,advance} from '../renderer/state.mjs';
import assert from 'node:assert/strict';
const arm=(scene,key)=>{const side=key==='left'?'L':'R',weights=scene[key+'Grips']||{[scene[key+'Kind']]:1};const a=anatomicalArm(SHOULDER_ROOTS[side],scene[key],side,scene[key+'Depth'],Object.entries(weights).reduce((v,[kind,w])=>v+handPoseAngle(kind)*w,0));assert.ok(a.reachError<.002,JSON.stringify({side,target:scene[key],depth:scene[key+'Depth'],phase:scene.phase,reachError:a.reachError}));return a;};
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
function audit(label,states){
 const row={label,maxPalmDegreesPerFrame:0,maxElbowPixelsPerFrame:0,minHandProjection:1e9,maxSupportTilt:0,worst:null};let previous;
 for(const [time,scene]of states){const arms=['left','right'].map(k=>arm(scene,k));for(let i=0;i<2;i++){const a=arms[i];assert.ok(Math.abs(distance(a.root,a.elbow)-150)<1e-6);assert.ok(Math.abs(distance(a.elbow,a.wrist)-110)<1e-6);assert.ok(Math.abs(distance(a.wrist,a.grip)-45)<1e-6);assert.ok(Math.abs(a.wristFlex)<=25.01*Math.PI/180);assert.ok(a.reachError<.002);row.minHandProjection=Math.min(row.minHandProjection,Math.hypot(a.grip[0]-a.wrist[0],a.grip[1]-a.wrist[1]));if(i===0&&scene.prop?.kind==='cake'&&scene.prop.opacity>.05)row.maxSupportTilt=Math.max(row.maxSupportTilt,Math.abs(a.handAngle)*180/Math.PI);if(previous){const angle=Math.abs(angleDifference(a.handAngle,previous[i].handAngle))*180/Math.PI;if(angle>row.maxPalmDegreesPerFrame){row.maxPalmDegreesPerFrame=angle;row.worst={time,side:i===0?'L':'R',phase:scene.phase};}row.maxElbowPixelsPerFrame=Math.max(row.maxElbowPixelsPerFrame,distance(a.elbow,previous[i].elbow));}}previous=arms;}
 return row;
}
const poses=['idle','cake','tea'],result=[];
for(const pose of poses)result.push(audit(pose,Array.from({length:1321},(_,i)=>[i/120,actionScene({pose,actionTime:i/120})])));
for(const from of poses)for(const to of poses){if(from===to)continue;for(const interruption of[0,.4,.7,1.4,2.4,3.6,4.2,6]){
 const state={...createPetState(),pose:from,actionTime:interruption};applyAction(state,{type:'pose',id:to});const states=[[0,actionScene(state)]];for(let i=1;i<=600;i++){advance(state,1/120);states.push([i/120,actionScene(state)]);}result.push(audit(`${from}@${interruption}->${to}`,states));
}}
const sorted=[...result].sort((a,b)=>b.maxPalmDegreesPerFrame-a.maxPalmDegreesPerFrame);
for(const entering of['cake','tea'])for(const at of[.2,.6,1.3])for(const next of poses){if(next===entering)continue;
 const s=createPetState();applyAction(s,{type:'pose',id:entering});for(let i=0;i<Math.round(at*120);i++)advance(s,1/120);applyAction(s,{type:'pose',id:next});const states=[[0,actionScene(s)]];for(let i=1;i<=600;i++){advance(s,1/120);states.push([i/120,actionScene(s)]);}result.push(audit(`enter-${entering}@${at}->${next}`,states));
}
sorted.splice(0,sorted.length,...[...result].sort((a,b)=>b.maxPalmDegreesPerFrame-a.maxPalmDegreesPerFrame));
for(const row of result){assert.ok(row.maxSupportTilt<5,JSON.stringify(row));assert.ok(row.maxPalmDegreesPerFrame<5,JSON.stringify(row));assert.ok(row.maxElbowPixelsPerFrame<6,JSON.stringify(row));assert.ok(row.minHandProjection>=20,JSON.stringify(row));}
console.log(JSON.stringify({ok:true,framesPerSecond:120,actionSpeed:1,sequences:result.length,maxTilt:Math.max(...result.map(r=>r.maxSupportTilt)),worst:sorted.slice(0,12),results:result},null,2));
