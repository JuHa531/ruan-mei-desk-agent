import {anatomicalArm,SHOULDER_ROOTS,handPoseAngle,angleDifference} from '../renderer/arm-kinematics.mjs';
import {actionScene} from '../renderer/action-motion.mjs';
import {createPetState,applyAction,advance} from '../renderer/state.mjs';
const unit=a=>{const l=Math.hypot(...a);return a.map(v=>v/l);},dot=(a,b)=>a.reduce((v,x,i)=>v+x*b[i],0),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],clamp=v=>Math.max(0,Math.min(1,v));
const sequences=[];
for(const pose of['cake','tea'])sequences.push(Array.from({length:1321},(_,i)=>actionScene({pose,actionTime:i/120})));
for(const from of['idle','megaphone','cake','tea'])for(const to of['idle','megaphone','cake','tea']){if(from===to)continue;for(const at of[1.4,3.6,4.2]){const s={...createPetState(),pose:from,actionTime:at};applyAction(s,{type:'pose',id:to});const frames=[actionScene(s)];for(let i=0;i<360;i++){advance(s,1/120);frames.push(actionScene(s));}sequences.push(frames);}}
const rows=[];
for(const low of[0,15,25,40,50])for(const high of[40,55,70])for(const span of[100,200,300]){
 let maxAngle=0,maxElbow=0,minProjection=45;const root=SHOULDER_ROOTS.R;
 for(const frames of sequences){let prev;for(const s of frames){const v=unit([s.right[0]-root[0],s.right[1]-root[1],s.rightDepth]),out=unit([1-v[0]*v[0],-v[0]*v[1],-v[0]*v[2]]),down=cross(v,out),u=clamp((200-(s.right[1]-root[1]))/span),phi=(low+(high-low)*u*u*(3-2*u))*Math.PI/180,pole=out.map((v,i)=>v*Math.cos(phi)+down[i]*Math.sin(phi)),weights=s.rightGrips||{[s.rightKind]:1},desired=Object.entries(weights).reduce((v,[k,w])=>v+handPoseAngle(k)*w,0),a=anatomicalArm(root,s.right,'R',s.rightDepth,desired,pole);
  minProjection=Math.min(minProjection,Math.hypot(a.grip[0]-a.wrist[0],a.grip[1]-a.wrist[1]));if(prev){maxAngle=Math.max(maxAngle,Math.abs(angleDifference(a.handAngle,prev.handAngle))*180/Math.PI);maxElbow=Math.max(maxElbow,Math.hypot(...a.elbow.map((v,i)=>v-prev.elbow[i])));}prev=a;
 }}rows.push({low,high,span,maxAngle,maxElbow,minProjection,score:maxAngle*5+maxElbow*2+Math.max(0,28-minProjection)*3});
}
rows.sort((a,b)=>a.score-b.score);console.log(JSON.stringify(rows.slice(0,10),null,2));
