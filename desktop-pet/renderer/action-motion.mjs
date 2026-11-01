/** Hand targets and attached props in neutral artwork coordinates. */
import {relaxedRest,dessertScene,coffeeScene,enterDessert,enterCoffee,exitMeal} from './daily-actions.mjs';
export const ACTIONS=['idle','cake','tea'];
export const clamp=v=>Math.max(0,Math.min(1,v));
export const ease=v=>{v=clamp(v);return v*v*v*(v*(v*6-15)+10);};
const mix=(a,b,t)=>a+(b-a)*t,point=(a,b,t)=>a.map((v,i)=>mix(v,b[i],t));
const ramp=(t,a,b)=>ease((t-a)/(b-a));
export const actionClock=s=>Number.isFinite(s.actionTime)?s.actionTime:s.time||0;
export const actionSpeed=s=>Math.max(.6,Math.min(1.6,Number.isFinite(s.actionSpeed)?s.actionSpeed:1));
const durations={idle:.9,cake:2.2,tea:1.4};
const idle=relaxedRest;
/** Periodic usage leaves several seconds of quiet hold between bites/sips. */
export function settledAction(id,age=0,{idleActions=true}={}){
 const s=idle(age,idleActions),t=idleActions?Math.max(0,age):0;
 if(id==='cake'){
  Object.assign(s,dessertScene(t,idleActions));
 }else if(id==='tea'){
  Object.assign(s,coffeeScene(t,idleActions));
 }return{...s,leftGrips:{[s.leftKind]:1},rightGrips:{[s.rightKind]:1}};
}
function blendHands(a,b,t){return{...b,left:point(a.left,b.left,t),right:point(a.right,b.right,t),leftDepth:mix(a.leftDepth||45,b.leftDepth||45,t),rightDepth:mix(a.rightDepth||45,b.rightDepth||45,t)};}
function grips(from,to,t){const r={};for(const k of new Set([...Object.keys(from),...Object.keys(to)])){const v=(from[k]||0)*(1-t)+(to[k]||0)*t;if(v>1e-9)r[k]=v;}return r;}
/** Incoming props have explicit spatial trajectories; body art never switches. */
export function enterAction(id,age,from,settings={}){
 const end=settledAction(id,0,settings),u=Math.max(0,age),d=durations[id]||.9;
 let s=blendHands(from,end,ramp(u,0,d));
 if(id==='cake'){
  s=enterDessert(u,from);
 }else if(id==='tea'){
  s=enterCoffee(u,from);
 }
 const leftBlend=ramp(u,0,id==='tea'?.8:.5),rightBlend=id==='cake'?ramp(u,1.1,2.2):ramp(u,0,id==='tea'?.8:.7);
 s.leftGrips=grips(from.leftGrips||{[from.leftKind]:1},{[s.leftKind]:1},leftBlend);s.rightGrips=grips(from.rightGrips||{[from.rightKind]:1},{[s.rightKind]:1},rightBlend);return s;
}
function exitAction(from,age){
 if(from.prop)return exitMeal(from,age);
 const duration=.9,r=ramp(age,0,duration),s=blendHands(from,idle(0,false),r);
 s.leftKind=from.leftKind;s.rightKind=from.rightKind;
 s.leftGrips=from.leftGrips;s.rightGrips=from.rightGrips;s.sip=(from.sip||0)*(1-r);s.materialize=(from.materialize||0)*(1-r);
 s.fork=from.fork?{...from.fork,x:s.right[0],y:s.right[1],opacity:from.fork.opacity*(1-r)}:null;
 s.bite=from.bite?{...from.bite,opacity:from.bite.opacity*(1-ramp(age,0,.25))}:null;s.mouthOpen=from.mouthOpen*(1-ramp(age,0,.3));s.chew=from.chew*(1-ramp(age,0,.3));
 return s;
}
export function actionScene(state,time=actionClock(state),settings={}){
 const m=state.poseMotion,opts={idleActions:settings.hairMotion!==false};
 if(!m)return settledAction(state.pose||'idle',Math.max(0,time-(state.actionStartedAt||0)),opts);
 const age=Math.max(0,time-m.startedAt);if(age<m.exitDuration)return exitAction(m.from,age);
 const start=m.exitDuration?exitAction(m.from,m.exitDuration):m.from,enterAge=age-m.exitDuration;
 return enterAge<m.entryDuration?enterAction(m.to,enterAge,start,opts):settledAction(m.to,enterAge-m.entryDuration,opts);
}
export function startAction(state,id,settings={}){
 if(!ACTIONS.includes(id)||state.pose===id)return false;
 const now=actionClock(state),from=actionScene(state,now,settings),exitDuration=from.prop?.opacity>.001?1.4:0;
 state.pose=id;const entryDuration=durations[id];
 state.poseMotion=settings.poseTransition===false?null:{from,to:id,startedAt:now,exitDuration,entryDuration,duration:exitDuration+entryDuration};
 state.actionStartedAt=now+(state.poseMotion?.duration||0);return true;
}
/** Two-bone IK keeps bind lengths fixed, clamping unreachable hand targets. */
export function solveArm(root,target,bend=1,upper=150,lower=165){
 const dx=target[0]-root[0],dy=target[1]-root[1],raw=Math.hypot(dx,dy)||1,d=Math.max(Math.abs(upper-lower)+.001,Math.min(upper+lower-.001,raw));
 const a=Math.atan2(dy,dx),b=Math.acos(Math.max(-1,Math.min(1,(upper*upper+d*d-lower*lower)/(2*upper*d)))),angle=a+b*bend;
 return{root:[...root],elbow:[root[0]+Math.cos(angle)*upper,root[1]+Math.sin(angle)*upper],hand:[root[0]+dx/raw*d,root[1]+dy/raw*d],upper,lower};
}
