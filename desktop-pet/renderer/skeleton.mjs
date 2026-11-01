/** Hierarchical 2D bones. Every local transform is a rotation, with a fixed bind length. */
import {lookAngles,lookAngleLimits,neckLandmarks} from './head-tracking.mjs';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export const smooth=(a,b,v)=>{const t=clamp((v-a)/(b-a),0,1);return t*t*(3-2*t);};
const identity=()=>[1,0,0,1,0,0];
export function multiply(a,b){return[a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]];}
export const transform=(m,x,y)=>[m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5]];
const rotation=(x,y,a)=>{const c=Math.cos(a),s=Math.sin(a);return[c,s,-s,c,x-c*x+s*y,y-s*x-c*y];};
// Rest positions are in the original artwork's 1090 x 1443 coordinates.
const definitions=[
 ['hips',-1,535,1030,.008],['spine',0,520,820,-.013],['chest',1,520,715,.009],
 ['neck',2,520,642,0],['head',3,536,619,0],
 ['bangs',4,505,250,.020],['hair-left',4,315,310,.018],['hair-right',4,780,310,.018],['hair-tail',4,850,720,.022],
 ['upper-arm-left',2,423,697,.002],['forearm-left',9,397,835,.003],['hand-left',10,466,923,.002],
 ['upper-arm-right',2,620,697,.002],['forearm-right',12,648,834,.003],['hand-right',13,566,925,.002],
 ['thigh-left',0,470,1040,.005],['shin-left',15,502,1180,.009],['foot-left',16,508,1330,.004],
 ['thigh-right',0,575,1040,.005],['shin-right',18,595,1170,.009],['foot-right',19,615,1330,.004],
 ['skirt',0,530,880,.015],['ribbon-left',0,390,1000,.022],['ribbon-right',0,700,1040,.022],
 ['sleeve-left',9,420,730,.012],['sleeve-right',12,620,730,.012],['tuft',4,832,202,-.016],['crown',4,540,180,-.006],
];
export const BONES=Object.freeze(definitions.map(([name,parent,x,y,sway],id)=>Object.freeze({id,name,parent,pivot:Object.freeze([x,y]),sway})));
export const BONE=Object.freeze(Object.fromEntries(BONES.map(b=>[b.name,b.id])));
export function restSkeleton(pose='idle'){
 const landmarks=neckLandmarks(pose),bones=BONES.map(b=>({...b,pivot:[...b.pivot]}));
 bones[BONE.neck].pivot=landmarks.neck;bones[BONE.head].pivot=landmarks.head;
 const arms={
  cake:[[650,696],[669,816],[604,866],[414,695],[392,765],[416,704]],
  tea:[[650,695],[668,796],[589,778],[414,695],[396,796],[474,777]],
 }[pose];
 if(arms)for(const[index,p]of[[12,0],[13,1],[14,2],[9,3],[10,4],[11,5]])bones[index].pivot=arms[p];
 for(const side of['left','right']){
  const a=bones[BONE['upper-arm-'+side]].pivot,b=bones[BONE['forearm-'+side]].pivot;
  bones[BONE['sleeve-'+side]].pivot=[a[0]+(b[0]-a[0])*.25,a[1]+(b[1]-a[1])*.25];
 }
 return bones;
}
const poseCache=new Map();
/** Global * inverse-bind matrices, shared by GPU, picking, accessories and the preview. */
export function sampleSkeleton(time=0,{enabled=true,amplitude=1,head={},pose='idle',gesture={}}={}){
 time=Number.isFinite(time)?time:0;amplitude=enabled?clamp(Number.isFinite(amplitude)?amplitude:1,0,2):0;
 const angles=lookAngles(head,pose),key=[time,amplitude,angles.neck,angles.head,pose,JSON.stringify(gesture)].join(':');
 if(poseCache.has(key))return poseCache.get(key);
 const bones=restSkeleton(pose),matrices=[],localAngles=[];
 const phase=Math.sin(time*.9)*.55*amplitude;
 for(const bone of bones){
  let angle=bone.sway*phase;
  if(bone.name==='neck')angle=angles.neck;
  if(bone.name==='head')angle=angles.head;
  angle+=Math.max(-.03,Math.min(.03,gesture[bone.name]||0));
  localAngles.push(angle);
  const local=angle?rotation(...bone.pivot,angle):identity();
  matrices.push(bone.parent<0?local:multiply(matrices[bone.parent],local));
 }
 const gpu=new Float32Array(bones.length*9);
 matrices.forEach((m,i)=>gpu.set([m[0],m[1],0,m[2],m[3],0,m[4],m[5],1],i*9));
 const result={bones,matrices,localAngles,gpu};poseCache.set(key,result);
 if(poseCache.size>192)poseCache.delete(poseCache.keys().next().value);
 return result;
}
function polygon(x,y,points,feather=18){
 let inside=false,distance=Infinity;
 for(let i=0,j=points.length-1;i<points.length;j=i++){
  const[a,b]=points[j],[c,d]=points[i];if((b>y)!==(d>y)&&x<(c-a)*(y-b)/(d-b)+a)inside=!inside;
  const dx=c-a,dy=d-b,t=clamp(((x-a)*dx+(y-b)*dy)/(dx*dx+dy*dy),0,1);distance=Math.min(distance,Math.hypot(x-a-t*dx,y-b-t*dy));
 }
 return smooth(-feather,feather,inside?distance:-distance);
}
const FACE=[[280,440],[360,395],[470,420],[560,380],[690,380],[760,480],[735,595],[630,650],[430,650],[300,590]];
const TORSO=[[463,644],[576,644],[630,664],[669,730],[710,845],[653,985],[626,1060],[410,1060],[370,980],[337,835],[373,735],[409,665]];
const hairParts=[
 ['bangs',[[365,277],[575,241],[645,286],[650,420],[620,480],[541,517],[470,535],[420,510],[382,437],[363,373]],290,390,40],
 ['hair-left',[[130,200],[370,220],[410,450],[405,632],[430,720],[332,790],[145,778],[100,600]],210,365,55],
 ['hair-right',[[665,235],[1015,230],[1075,675],[885,765],[660,710],[645,565],[670,390]],215,365,55],
 ['hair-tail',[[827,699],[978,728],[1060,845],[1057,993],[931,1090],[823,1147],[777,1085],[898,1006],[936,902],[875,783]],700,810,25],
 ['tuft',[[765,130],[856,113],[897,118],[941,111],[966,140],[950,204],[889,240],[799,226]],100,160,24],
];
const ribbonParts=[
 ['ribbon-left',[[300,1010],[424,1035],[409,1120],[365,1250],[253,1385],[245,1260],[285,1120]],1020,1100],
 ['ribbon-right',[[652,1030],[755,1045],[790,1170],[902,1370],[802,1350],[690,1210]],1030,1120],
];
const bindingCache=new Map();
/** Four normalized influences. Head ownership ends before the collar, never across the chest. */
export function skinBinding(x,y,pose='idle',cat=false){
 const key=[pose,cat,x,y].join(':');if(bindingCache.has(key))return bindingCache.get(key);
 const bones=restSkeleton(pose),landmarks=neckLandmarks(pose),jaw=landmarks.head[1],neck=landmarks.neck[1],weights=new Map();
 const add=(id,v)=>{if(v>1e-9)weights.set(id,(weights.get(id)||0)+v);};
 const mix=(id,value)=>{value=clamp(value,0,1);if(value<1e-9)return;for(const[k,v]of weights)weights.set(k,v*(1-value));add(id,value);};
 const bodyGuard=Math.max(0,1-2*polygon(x,y,TORSO,18));
 // Away from the narrow neck, release transparent space/hair over a longer arc.
 // Torso ownership is exact: this transition never pulls the shoulders or chest.
 const outer=smooth(60,200,Math.abs(x-landmarks.neck[0]));
 const head=(1-smooth(jaw+3,jaw+13+outer*70,y))*bodyGuard,neckCore=(1-smooth(8,20,Math.abs(x-landmarks.neck[0])));
 const neckWeight=(1-head)*(1-smooth(jaw+10,neck-1,y))*neckCore;
 add(BONE.head,head);add(BONE.neck,neckWeight);add(y<980?BONE.chest:BONE.hips,1-head-neckWeight);
 const faceGuard=Math.max(0,1-2*polygon(x,y,FACE,34));
 for(const[name,outline,a,b,feather]of hairParts){
  let influence=polygon(x,y,outline,feather)*smooth(a,b,y)*faceGuard*bodyGuard;
  if(cat&&y<280)influence=0;
  mix(BONE[name],influence*.92);
 }
 if(!cat)mix(BONE.crown,(1-smooth(320,395,y))*.35);
 // Arm chains follow the actual rest pose. Cup, fork and cake stay with their hands.
 const capsule=(a,b,r)=>{const dx=b[0]-a[0],dy=b[1]-a[1],t=clamp(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy),0,1);return{t,w:1-smooth(r-14,r+14,Math.hypot(x-a[0]-t*dx,y-a[1]-t*dy))};};
 for(const side of['left','right']){
  const upper=BONE['upper-arm-'+side],fore=BONE['forearm-'+side],hand=BONE['hand-'+side];
  const a=bones[upper].pivot,b=bones[fore].pivot,c=bones[hand].pivot;
  const shoulder=capsule(a,b,42),lower=capsule(b,c,43);
  // Respect the face/neck and leave the chest's central artwork on its own bone.
  const permitted=smooth(landmarks.head[1]+18,landmarks.head[1]+44,y);
  mix(upper,shoulder.w*(1-smooth(.68,1,shoulder.t))*.85*permitted);
  mix(fore,Math.max(shoulder.w*smooth(.7,1,shoulder.t),lower.w*(1-smooth(.72,1,lower.t)))*.88*permitted);
  mix(hand,lower.w*smooth(.65,1,lower.t)*.94*permitted);
  mix(BONE['sleeve-'+side],shoulder.w*smooth(.2,.65,shoulder.t)*(1-smooth(.8,1,shoulder.t))*.45*permitted);
 }
 // The long ribbons attach to the hips, not the head. Sleeves attach to the arm chain.
 for(const[name,outline,a,b]of ribbonParts)mix(BONE[name],polygon(x,y,outline,20)*smooth(a,b,y)*.94);
 mix(BONE.skirt,polygon(x,y,[[400,945],[675,945],[725,1045],[614,1100],[402,1100],[340,1040]],24)*smooth(950,1020,y)*.8);
 for(const side of['left','right']){
  const thigh=BONE['thigh-'+side],shin=BONE['shin-'+side],foot=BONE['foot-'+side];
  const a=bones[thigh].pivot,b=bones[shin].pivot,c=bones[foot].pivot;
  const leg=capsule(a,c,side==='left'?59:58),start=smooth(1020,1080,y);
  mix(thigh,leg.w*(1-smooth(b[1]-35,b[1]+35,y))*start);
  mix(shin,leg.w*smooth(b[1]-35,b[1]+35,y)*(1-smooth(c[1]-40,c[1]+12,y))*start);
  mix(foot,leg.w*smooth(c[1]-40,c[1]+12,y)*start);
 }
 const entries=[...weights].filter(([,v])=>v>1e-7).sort((a,b)=>b[1]-a[1]).slice(0,4),total=entries.reduce((s,[,v])=>s+v,0);
 const ids=new Float32Array(4),values=new Float32Array(4);entries.forEach(([id,v],i)=>{ids[i]=id;values[i]=v/total;});
 const result={ids,weights:values};bindingCache.set(key,result);return result;
}
export function deformSkinPoint(x,y,skeleton,pose='idle',cat=false){
 const binding=skinBinding(x,y,pose,cat);let dx=0,dy=0;
 for(let i=0;i<4;i++){
  const w=binding.weights[i];if(!w)continue;const q=transform(skeleton.matrices[binding.ids[i]],x,y);dx+=(q[0]-x)*w;dy+=(q[1]-y)*w;
 }
 return[x+dx,y+dy];
}
function rotationBounds(x,y,a){
 const result=[0,0,0,0];
 for(let axis=0;axis<2;axis++){
  const value=t=>axis===0?(Math.cos(t)-1)*x-Math.sin(t)*y:Math.sin(t)*x+(Math.cos(t)-1)*y;
  let lo=Math.min(0,value(-a),value(a)),hi=Math.max(0,value(-a),value(a));
  const critical=axis===0?Math.atan2(-y,x):Math.atan2(x,y);
  for(let n=-2;n<=2;n++){const angle=critical+n*Math.PI;if(angle>-a&&angle<a){lo=Math.min(lo,value(angle));hi=Math.max(hi,value(angle));}}
  result[axis]=lo;result[axis+2]=hi;
 }
 return result;
}
/** Analytic bounds over the joint chain, including rotation of every child pivot. */
export function skinMotionBounds(x,y,{enabled=true,amplitude=1,headTracking=false,pose='idle',cat=false}={}){
 const bones=restSkeleton(pose),binding=skinBinding(x,y,pose,cat),result=[0,0,0,0],look=lookAngleLimits(pose);
 for(let i=0;i<4;i++){
  const weight=binding.weights[i];if(!weight)continue;
  const chain=[];for(let id=binding.ids[i];id>=0;id=bones[id].parent)chain.unshift(id);
  let idleAngle=0,lookAngle=0;
  for(let j=0;j<chain.length;j++){
   const bone=bones[chain[j]],next=j+1<chain.length?bones[chain[j+1]].pivot:[x,y];
   if(headTracking&&bone.name==='neck')lookAngle=look.neck;
   else if(headTracking&&bone.name==='head')lookAngle=look.combined;
   idleAngle+=Math.abs(bone.sway)*.55*(enabled?clamp(amplitude,0,2):0);
   const angle=idleAngle+lookAngle;
   const bounds=rotationBounds(next[0]-bone.pivot[0],next[1]-bone.pivot[1],angle);
   for(let k=0;k<4;k++)result[k]+=bounds[k]*weight;
  }
 }
 return result;
}
export function drawSkeleton(ctx,skeleton,{excludeArmChains=false}={}){
 ctx.save();ctx.lineWidth=2.5;ctx.font='16px sans-serif';
 for(const bone of skeleton.bones){
  if(bone.parent<0||(excludeArmChains&&([9,10,11,12,13,14,24,25].includes(bone.id))))continue;
  const p=transform(skeleton.matrices[bone.id],...bone.pivot),parent=skeleton.bones[bone.parent],q=transform(skeleton.matrices[parent.id],...parent.pivot);
  ctx.strokeStyle=bone.name==='head'||bone.name==='neck'?'#ffca68':'#39d3c3';ctx.beginPath();ctx.moveTo(...q);ctx.lineTo(...p);ctx.stroke();
  ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.arc(...p,4,0,Math.PI*2);ctx.fill();
 }
 ctx.restore();
}
