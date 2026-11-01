/** Human contact constraints: relaxed folded hands, top-down fork, one cup handle. */
import {FORK_ART,CUP_ART} from './grasp-binding.mjs';
const clamp=v=>Math.max(0,Math.min(1,v));
const ease=v=>{v=clamp(v);return v*v*v*(v*(v*6-15)+10);};
const ramp=(t,a,b)=>ease((t-a)/(b-a)),mix=(a,b,t)=>a+(b-a)*t;
const point=(a,b,t)=>a.map((v,i)=>mix(v,b[i],t));
const cubic=(a,b,c,d,t)=>a.map((v,i)=>(1-t)**3*v+3*(1-t)**2*t*b[i]+3*(1-t)*t*t*c[i]+t**3*d[i]);
const prop=(kind,p,angle=0,opacity=1,scale=1)=>({kind,x:p[0],y:p[1],angle,opacity,scale});
export const FORK_REACH=(FORK_ART.grip[1]-FORK_ART.tip[1])*FORK_ART.scale;
export const CUP_GRIP=Object.freeze(CUP_ART.grip.map((v,i)=>(v-CUP_ART.pivot[i])*CUP_ART.scale));
export const CUP_RIM=Object.freeze([-20,-53]);
export const CUP_BASE=Object.freeze(CUP_ART.base.map((v,i)=>(v-CUP_ART.pivot[i])*CUP_ART.scale));
// Nominal grip below the actual palm contact; renderer refines the contact
// against the real hand transform when the wrist is tilted/foreshortened.
export const CUP_SUPPORT=Object.freeze([CUP_BASE[0]-9.31,CUP_BASE[1]+5.54]);
export const CUP_HOLD=Object.freeze([520,780]);
// Keep the support forearm across the abdomen, rather than reaching down to
// the thighs. That old reach exhausted wrist flex and tipped the palm sideways.
export const DESSERT_HOLD=Object.freeze([525,803]);
export const DESSERT_PICKUP=Object.freeze([425,805]);
export const DESSERT_SUPPORT=Object.freeze([0,57]);
const READY_TIP=[600,900+FORK_REACH],CUT_OFFSET=[33,-25];
export const rotate=(p,a)=>[p[0]*Math.cos(a)-p[1]*Math.sin(a),p[0]*Math.sin(a)+p[1]*Math.cos(a)];
export function attachment(p,offset){const q=rotate(offset,p.angle);return[p.x+q[0],p.y+q[1]];}
export const forkTip=p=>attachment(p,[0,-FORK_REACH]);
function forkAt(tip,angle,opacity=1){const v=rotate([0,-FORK_REACH],angle);return prop('fork',[tip[0]-v[0],tip[1]-v[1]],angle,opacity);}
const gripWeights=kind=>({[kind]:1});
const blendGrips=(a,b,t)=>Object.fromEntries([...new Set([...Object.keys(a),...Object.keys(b)])].map(k=>[k,(a[k]||0)*(1-t)+(b[k]||0)*t]).filter(([,v])=>v>1e-9));
export function relaxedRest(t=0,enabled=true){
 const a=enabled?1:0,x=Math.sin(t*.65)*a,y=Math.sin(t*.9+.4)*a;
 return{left:[541+x*.8,897+y*1.2],right:[509+x*.8,887+y*1.2],leftDepth:55,rightDepth:90,leftKind:'relaxedL',rightKind:'relaxedR',leftAngle:0,rightAngle:Math.PI,rightBend:-1,
  prop:null,fork:null,bite:null,mouthOpen:0,chew:0,phase:'folded-rest'};
}
export function dessertScene(age=0,enabled=true){
 const t=enabled?Math.max(0,age):0,c=t%10.5,s=relaxedRest(t,enabled),sway=enabled?Math.sin(t*.6)*1.2:0;
 s.prop=prop('cake',[DESSERT_HOLD[0]+sway,DESSERT_HOLD[1]]);
 s.left=attachment(s.prop,DESSERT_SUPPORT);s.leftDepth=75;s.leftKind='support';s.leftAngle=0;s.rightKind='fork';s.rightAngle=Math.PI;s.rightDepth=65;
 const cut=[s.prop.x+CUT_OFFSET[0],s.prop.y+CUT_OFFSET[1]],above=[cut[0],cut[1]-40],raised=[cut[0],cut[1]-65];
 let tip=READY_TIP,angle=Math.PI,phase='hold-dessert';
 if(c>=1&&c<1.9){const u=ramp(c,1,1.9);tip=cubic(READY_TIP,[660,830],[630,700],above,u);phase='approach-fork';}
 else if(c>=1.9&&c<2.5){tip=point(above,cut,ramp(c,1.9,2.5));phase='pierce';}
 else if(c>=2.5&&c<2.95){tip=point(cut,raised,ramp(c,2.5,2.95));phase='lift-bite';}
 else if(c>=2.95&&c<4.2){const u=ramp(c,2.95,4.2);tip=cubic(raised,[635,780],[615,620],[491,585],u);angle=mix(Math.PI,Math.PI*1.5,u);phase='bite';}
 else if(c>=4.2&&c<4.65){tip=[491,585];angle=Math.PI*1.5;phase='bite';}
 else if(c>=4.65&&c<5.35){tip=point([491,585],[555,680],ramp(c,4.65,5.35));angle=Math.PI*1.5;phase='withdraw-fork';}
 else if(c>=5.35&&c<6.6){const u=ramp(c,5.35,6.6);angle=mix(Math.PI*1.5,Math.PI,u);const grip=cubic([555+FORK_REACH,680],[680,760],[640,880],[600,900],u);tip=attachment(prop('fork',grip,angle),[0,-FORK_REACH]);phase='lower-fork';}
 s.fork=forkAt(tip,angle);s.right=[s.fork.x,s.fork.y];s.phase=phase;
 // The bite appears only after separation, follows the actual tines, and is
 // removed at the lips before the fork is withdrawn. The fork enters from ABOVE.
 if(c>=2.5&&c<4.48)s.bite=prop('bite',tip,0,ramp(c,2.5,2.68)*(1-ramp(c,4.23,4.48)));
 s.mouthFollow=ramp(c,3.4,4.2)*(1-ramp(c,4.65,5.35));
 s.rightDepth=125;
 s.mouthOpen=ramp(c,3.98,4.2)*(1-ramp(c,4.45,4.68));
 s.chew=ramp(c,4.45,4.7)*(1-ramp(c,6.25,6.65))*(.35+.4*Math.sin(c*12)**2);
 s.contact={cakeTop:cut,forkTip:tip};return s;
}
export function coffeeScene(age=0,enabled=true){
 const t=enabled?Math.max(0,age):0,c=t%10,lift=ramp(c,2,3.65)*(1-ramp(c,4.9,6.5)),s=relaxedRest(t,enabled);
 s.prop=prop('cup',point(CUP_HOLD,[521,634],lift),-.12*lift);
 s.left=attachment(s.prop,CUP_SUPPORT);s.leftKind='support';s.leftDepth=75+65*lift;s.cupSupport=1;
 s.right=attachment(s.prop,CUP_GRIP);s.rightKind='cup';s.rightAngle=Math.PI;s.rightDepth=65+60*lift;
 // One hand grips the handle; the other supports the base throughout the sip.
 s.sip=lift;s.mouthOpen=ramp(c,3.5,3.65)*(1-ramp(c,4.75,5))*.16;s.phase=lift>.01?'sip':'hold-cup';
 return s;
}
export function enterDessert(age,from){
 const end=dessertScene(0,false),s={...end},reach=ramp(age,0,.65),carry=ramp(age,.65,1.85),ready=ramp(age,1.1,2.2);
 s.left=age<.65?point(from.left,DESSERT_PICKUP,reach):point(DESSERT_PICKUP,end.left,carry);
 s.left[1]-=Math.sin(carry*Math.PI)*12;
 s.leftDepth=mix(from.leftDepth||55,75,ramp(age,0,.65));
 s.right=point(from.right,end.right,ready);s.rightDepth=mix(from.rightDepth||90,end.rightDepth,ready);
 s.prop=prop('cake',[s.left[0],s.left[1]-DESSERT_SUPPORT[1]],0,ramp(age,.64,.78));
 s.fork=ready>.001?prop('fork',s.right,Math.PI,ready):null;
 s.phase=age<.65?'reach-dessert':'carry-dessert';return s;
}
export function enterCoffee(age,from){
 const end=coffeeScene(0,false),ready=ramp(age,0,.8),appear=ramp(age,.68,1.3),s={...end};
 s.left=point(from.left,end.left,ready);s.right=point(from.right,end.right,ready);
 s.leftDepth=mix(from.leftDepth||55,end.leftDepth,ready);s.rightDepth=mix(from.rightDepth||90,end.rightDepth,ready);
 s.prop={...end.prop,opacity:appear,scale:.86+.14*appear};
 // Formation completes only after the fingers reach the handle contact point.
 const contact=attachment(s.prop,CUP_GRIP.map(v=>v*s.prop.scale));
 s.right=point(s.right,contact,ramp(age,.68,.8));
 const support=ramp(age,.68,.8);s.left=point(s.left,attachment(s.prop,CUP_SUPPORT.map(v=>v*s.prop.scale)),support);s.cupSupport=support;
 s.materialize=appear>0&&appear<1?Math.sin(appear*Math.PI):0;s.phase='materialize-cup';return s;
}
export function exitMeal(from,age){
 const d=1.4,r=ramp(age,0,d),rest=relaxedRest(0,false),s={...rest,left:point(from.left,rest.left,r),right:point(from.right,rest.right,r),leftDepth:mix(from.leftDepth||55,rest.leftDepth,r),rightDepth:mix(from.rightDepth||90,rest.rightDepth,r)};
 const release=from.prop.kind==='cup'?ramp(age,1.05,1.4):ramp(age,1.3,1.4);
 s.leftGrips=blendGrips(from.leftGrips||gripWeights(from.leftKind),gripWeights(rest.leftKind),release);
 const rightRelease=from.prop.kind==='cake'?ramp(age,1.2,1.4):release;
 s.rightGrips=blendGrips(from.rightGrips||gripWeights(from.rightKind),gripWeights(rest.rightKind),rightRelease);
 s.leftKind=release<.5?from.leftKind:rest.leftKind;s.rightKind=release<.5?from.rightKind:rest.rightKind;
 if(from.prop.kind==='cake'){
  const carry=ramp(age,.38,1.2);s.left=point(from.left,DESSERT_PICKUP,carry);s.leftDepth=mix(from.leftDepth||75,75,carry);
  s.prop={...from.prop,x:s.left[0],y:s.left[1]-DESSERT_SUPPORT[1],opacity:from.prop.opacity*(1-ramp(age,1.05,1.3))};
  const ready=dessertScene(0,false),raised=clamp((820-from.right[1])/180),aside=[mix(from.right[0],Math.max(660,from.right[0]),raised),mix(from.right[1],Math.max(680,from.right[1]),raised)];
  const withdraw=ramp(age,0,.55),lower=ramp(age,.55,1.15);
  s.right=age<.55?point(from.right,aside,withdraw):point(aside,ready.right,lower);s.rightDepth=mix(from.rightDepth||125,ready.rightDepth,lower);
  const returnHand=ramp(age,.8,1.4);s.right=point(s.right,rest.right,returnHand);s.rightDepth=mix(s.rightDepth,rest.rightDepth,returnHand);
  if(from.fork){const angle=mix(from.fork.angle,Math.PI,lower);s.fork=prop('fork',s.right,angle,from.fork.opacity*(1-ramp(age,1.05,1.2)));}
  s.phase='put-away-dessert';
 }else{
  const lower=ramp(age,0,.7),p=point([from.prop.x,from.prop.y],CUP_HOLD,lower);s.prop={...from.prop,x:p[0],y:p[1],angle:mix(from.prop.angle,0,lower),opacity:from.prop.opacity*(1-ramp(age,.7,1.05))};
  const contact=attachment(s.prop,CUP_GRIP.map(v=>v*(s.prop.scale||1))),original=attachment(from.prop,CUP_GRIP.map(v=>v*(from.prop.scale||1))),grasp=ramp(age,0,.15);
  // An interrupted materialization may not yet have reached its grip. Preserve
  // that first frame, then finish the short approach before putting the cup down.
  s.right=point(contact.map((v,i)=>v+(from.right[i]-original[i])*(1-grasp)),rest.right,release);
  const support=attachment(s.prop,CUP_SUPPORT.map(v=>v*(s.prop.scale||1))),originalSupport=attachment(from.prop,CUP_SUPPORT.map(v=>v*(from.prop.scale||1)));
  s.left=point(support.map((v,i)=>v+(from.left[i]-originalSupport[i])*(1-grasp)),rest.left,release);
  s.leftDepth=mix(mix(from.leftDepth||75,75,lower),rest.leftDepth,release);s.cupSupport=mix(from.cupSupport||0,1,grasp)*(1-release);
  s.sip=(from.sip||0)*(1-lower);s.phase='put-away-cup';
 }
 s.mouthOpen=(from.mouthOpen||0)*(1-ramp(age,0,.25));s.chew=(from.chew||0)*(1-ramp(age,0,.25));
 s.mouthFollow=(from.mouthFollow||0)*(1-ramp(age,0,.38));s.materialize=(from.materialize||0)*(1-ramp(age,0,.25));
 if(from.bite&&s.fork){const p=forkTip(s.fork);s.bite={...from.bite,x:p[0],y:p[1],opacity:from.bite.opacity*(1-ramp(age,0,.3))};}
 return s;
}
