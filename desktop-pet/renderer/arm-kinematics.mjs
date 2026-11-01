/** Fixed-length 3D arm joints with orthographic projection and an anatomical elbow pole. */
const add=(a,b)=>a.map((v,i)=>v+b[i]),sub=(a,b)=>a.map((v,i)=>v-b[i]),mul=(a,k)=>a.map(v=>v*k);
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0),length=a=>Math.hypot(...a),unit=a=>mul(a,1/(length(a)||1));
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export const SHOULDER_ROOTS=Object.freeze({L:Object.freeze([443,687]),R:Object.freeze([597,686])});
export const angleDifference=(a,b)=>Math.atan2(Math.sin(a-b),Math.cos(a-b));
export const handPoseAngle=name=>name==='support'||name==='relaxedL'?0:Math.PI;
export function solveLimb3D(root,target,pole,upper=150,lower=110){
 const offset=sub(target,root),raw=length(offset),direction=raw<1e-8?[0,1,0]:unit(offset),d=clamp(raw,Math.abs(upper-lower)+.001,upper+lower-.001);
 let normal=sub(pole,mul(direction,dot(pole,direction)));if(length(normal)<1e-5)normal=sub([0,0,1],mul(direction,direction[2]));normal=unit(normal);
 const along=(upper*upper+d*d-lower*lower)/(2*d),height=Math.sqrt(Math.max(0,upper*upper-along*along));
 return{root:[...root],elbow:add(root,add(mul(direction,along),mul(normal,height))),wrist:add(root,mul(direction,d)),upper,lower};
}
/** Elbow points outward/down; wrist follows the forearm with at most 25 degrees of flex. */
export function anatomicalArm(root2,grip2,side,depth=75,desiredHandAngle=Math.PI/2,poleHint=null){
 const root=[...root2,0],target=[...grip2,Math.max(15,depth)],relativeY=grip2[1]-root2[1],raise=clamp((200-relativeY)/300,0,1),front=raise*raise*(3-2*raise),face=clamp((-20-relativeY)/80,0,1),nearFace=face*face*(3-2*face);
 // Build the elbow plane from orthogonal outward/down directions. A fixed
 // diagonal pole became nearly parallel to the reaching arm, then flipped its
 // normalized plane. This basis stays defined because target depth is positive.
 const signSide=side==='L'?-1:1,direction=unit(sub(target,root)),axis=[signSide,0,0];
 const outward=unit(sub(axis,mul(direction,dot(axis,direction)))),down=mul(cross(direction,outward),signSide);
 // The passive/support arm stays tucked; the active utensil arm opens its
 // elbow gradually before rising beside the face. Both use the same basis.
 const restRoll=side==='L'?25+15*front:40*front,roll=(restRoll+(60-restRoll)*nearFace)*Math.PI/180;
 const pole=poleHint||add(mul(outward,Math.cos(roll)),mul(down,Math.sin(roll))),handLength=45;
 const evaluate=beta=>{
  const combined=Math.sqrt(110**2+45**2+2*110*45*Math.cos(beta)),joint=solveLimb3D(root,target,pole,150,combined),forward=unit(sub(joint.wrist,joint.elbow)),xy=Math.hypot(forward[0],forward[1]);
  const tangent=xy<1e-6?[1,0,0]:[-forward[1]/xy,forward[0]/xy,0],delta=Math.atan2(45*Math.sin(beta),110+45*Math.cos(beta));
  const fore=add(mul(forward,Math.cos(delta)),mul(tangent,-Math.sin(delta))),hand=add(mul(forward,Math.cos(beta-delta)),mul(tangent,Math.sin(beta-delta)));
  const wrist=add(joint.elbow,mul(fore,110)),grip=add(wrist,mul(hand,45)),foreAngle=Math.atan2(fore[1],fore[0]),handAngle=Math.atan2(hand[1],hand[0]);
  return{root:joint.root,elbow:joint.elbow,wrist,grip,upper:150,lower:110,handLength,handAngle,foreAngle,wristFlex:angleDifference(handAngle,foreAngle),target,reachError:length(sub(grip,target))};
 };
 const initial=evaluate(0),error=angleDifference(desiredHandAngle,initial.handAngle),sign=Math.sign(error)||1;
 // A global facing preference has no anatomical meaning when it opposes the
 // forearm. Relax the wrist continuously there, instead of changing from +25°
 // to -25° when the wrapped angle crosses ±π (a visible one-frame hand flip).
 const opposed=clamp((Math.abs(error)-Math.PI/2)/(Math.PI/2),0,1),relax=1-opposed*opposed*(3-2*opposed);
 let lo=0,hi=25*Math.PI/180*relax,best=initial;
 // Solve a scalar, bounded wrist angle. Unlike iterative endpoint IK, this cannot
 // jump between two folded wrist solutions while the hand passes the shoulder.
 for(let i=0;i<15;i++){
  const mid=(lo+hi)/2,candidate=evaluate(sign*mid),travel=angleDifference(candidate.handAngle,initial.handAngle)*sign;
  if(Math.abs(candidate.wristFlex)>25*Math.PI/180||travel>Math.abs(error)||candidate.reachError>initial.reachError+.001)hi=mid;
  else{lo=mid;best=candidate;}
 }return best;
}
