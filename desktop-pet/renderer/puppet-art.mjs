/** Separately painted limbs/props, bound to fixed-length IK bones. No whole-pose sprites. */
import {actionScene,actionClock} from './action-motion.mjs';
import {anatomicalArm,SHOULDER_ROOTS,handPoseAngle} from './arm-kinematics.mjs';
import {attachment,CUP_RIM,CUP_GRIP,CUP_BASE} from './daily-actions.mjs';
import {createArmSkinRenderer,armSurface,skinArmPoint,armHitPoint} from './arm-skin.mjs';
import {BONE,sampleSkeleton,transform} from './skeleton.mjs';
import {motionTime,motionAmplitude} from './motion-settings.mjs';
import {FORK_ART,CUP_ART,SUPPORT_PALM,HAND_GRASPS,insideContour} from './grasp-binding.mjs';
const make=(w,h)=>Object.assign(document.createElement('canvas'),{width:w,height:h});
// Atlas anchors are authored in its original 1086×1448 image coordinates.
const PARTS={
 upperL:{rect:[50,45,285,358],a:[260,89],b:[277,364]},upperR:{rect:[460,45,268,357],a:[535,89],b:[521,363]},
 relaxedL:{rect:[795,32,235,375],a:[864,67],wrist:[934,252],b:[951,335]},relaxedR:{rect:[88,424,180,354],a:[213,466],wrist:[145,625],b:[143,716]},
 support:{rect:[420,424,228,341],a:[536,467],wrist:[592,631],b:[542,708]},fork:{rect:[807,424,193,353],a:[952,466],wrist:[922,613],b:[884,709]},
 cup:{rect:[110,780,167,305],a:[170,824],wrist:[225,978],b:[184,1021]},
 cake:{rect:[744,852,322,192],size:265,pivot:[906,963]},cupProp:{rect:[70,1160,277,224],size:168,pivot:[205,1275]},
 forkProp:{rect:[514,1099,78,316],size:150,pivot:FORK_ART.grip,tip:FORK_ART.tip},bite:{rect:[830,1192,162,178],size:27,pivot:[912,1277]},
};
const HANDS={
 'hand-support':{rect:[45,180,560,210],a:SUPPORT_PALM.wrist,b:SUPPORT_PALM.grip,contact:SUPPORT_PALM.contact},
 'hand-fork':{rect:[0,0,1536,1024],a:[1158,635],b:HAND_GRASPS.fork.grip,frontContours:HAND_GRASPS.fork.front,source:'left-fork'},
 'hand-cup':{rect:[1090,135,418,277],a:[1390,305],b:HAND_GRASPS.cup.grip,frontContours:HAND_GRASPS.cup.front},
 'hand-relaxedL':{rect:[665,482,273,463],a:[801,560],b:[804,775]},
 'hand-relaxedR':{rect:[1120,484,260,460],a:[1255,567],b:[1240,788]},
};
const ARMS={armL:{rect:[300,30,370,945],a:[503,115],elbow:[575,493],b:[515,943]},armR:{rect:[865,30,370,945],a:[1025,115],elbow:[955,493],b:[1021,943]}};
export function createCleanBody(neutral,clean){
 const c=make(1090,1443),ctx=c.getContext('2d');ctx.drawImage(neutral,0,0,1090,1443);
 // Only the formerly occluded torso band is replaced. Original head/hair/legs stay intact.
 ctx.save();ctx.beginPath();const p=[[409,660],[626,660],[657,702],[714,800],[706,904],[637,1016],[421,1016],[332,904],[300,843],[326,776],[370,708]];
 p.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.clip();ctx.clearRect(0,0,1090,1443);ctx.drawImage(clean,0,0,1090,1443);ctx.restore();
 // The moving continuous arm owns the deltoid. Retain the inner clavicle/collar only.
 ctx.save();ctx.globalCompositeOperation='destination-out';
 for(const cap of[[[415,665],[447,656],[463,671],[444,699],[435,739],[415,718]],[[578,670],[597,658],[623,668],[641,716],[601,740],[585,699]]]){ctx.beginPath();cap.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fill();}ctx.restore();return c;
}
export function createPuppetArt(atlas,handAtlas,armAtlas,leftForkHand){
 const parts={};
 for(const[name,spec]of Object.entries({...PARTS,...HANDS,...ARMS})){
  const [x,y,w,h]=spec.rect,c=make(w,h),ctx=c.getContext('2d',{willReadFrequently:true});
  ctx.drawImage(spec.source==='left-fork'?leftForkHand:name.startsWith('hand-')?handAtlas:name.startsWith('arm')?armAtlas:atlas,x,y,w,h,0,0,w,h);const data=ctx.getImageData(0,0,w,h).data,rows=[];
  let minX=w,minY=h,maxX=0,maxY=0;
  for(let sy=0;sy<h;sy+=12){let lo=w,hi=-1;for(let py=sy;py<Math.min(h,sy+12);py++)for(let px=0;px<w;px++)if(data[(py*w+px)*4+3]>32){lo=Math.min(lo,px);hi=Math.max(hi,px);minY=Math.min(minY,py);maxY=Math.max(maxY,py);}
   if(hi>=lo){rows.push([lo,sy,hi-lo+1,Math.min(12,h-sy)]);minX=Math.min(minX,lo);maxX=Math.max(maxX,hi);}}
  parts[name]={...spec,image:c,data,rows,bounds:[minX,minY,maxX-minX+1,maxY-minY+1],a:spec.a?.map((v,i)=>v-[x,y][i]),b:spec.b?.map((v,i)=>v-[x,y][i]),elbow:spec.elbow?.map((v,i)=>v-[x,y][i]),wrist:spec.wrist?.map((v,i)=>v-[x,y][i]),pivot:spec.pivot?.map((v,i)=>v-[x,y][i]),tip:spec.tip?.map((v,i)=>v-[x,y][i]),contact:spec.contact?.map((v,i)=>v-[x,y][i]),frontContours:spec.frontContours?.map(poly=>poly.map(p=>[p[0]-x,p[1]-y]))};
 }parts.armRenderer=createArmSkinRenderer();return parts;
}
const matrix=(angle,scale,src,dst)=>{const c=Math.cos(angle)*scale,s=Math.sin(angle)*scale;return[c,s,-s,c,dst[0]-c*src[0]+s*src[1],dst[1]-s*src[0]-c*src[1]];};
// Orthographic foreshortening acts along the limb; its transverse width stays constant.
const between=(p,a,b,restLength)=>{
 const sx=p.b[0]-p.a[0],sy=p.b[1]-p.a[1],sl=Math.hypot(sx,sy),dx=b[0]-a[0],dy=b[1]-a[1],dl=Math.hypot(dx,dy)||.001,u=[sx/sl,sy/sl],v=[-u[1],u[0]],q=[dx/dl,dy/dl],n=[-q[1],q[0]],along=dl/sl,across=(restLength||dl)/sl;
 const m=[q[0]*along*u[0]+n[0]*across*v[0],q[1]*along*u[0]+n[1]*across*v[0],q[0]*along*u[1]+n[0]*across*v[1],q[1]*along*u[1]+n[1]*across*v[1],0,0];m[4]=a[0]-m[0]*p.a[0]-m[2]*p.a[1];m[5]=a[1]-m[1]*p.a[0]-m[3]*p.a[1];return m;
};
export function puppetFrame(parts,state,settings={},skel=null){
 const skeleton=skel||sampleSkeleton(motionTime(state,settings),{enabled:settings.hairMotion!==false,amplitude:motionAmplitude(settings),pose:'idle',head:settings.headTracking!==false&&settings.eyeTracking!==false?state.head:{}});
 const s=actionScene(state,actionClock(state),settings),chest=skeleton.matrices[BONE.chest],head=skeleton.matrices[BONE.head],world=p=>transform(chest,...p),mouth=transform(head,491,585);
 const scene={...s,left:world(s.left),right:world(s.right)},baseAngle=Math.atan2(chest[1],chest[0]);
 for(const name of['prop','fork','bite'])if(s[name]){const p=world([s[name].x,s[name].y]);scene[name]={...s[name],x:p[0],y:p[1],angle:s[name].angle+baseAngle};}
 // At the lips, utensils follow the actual head bone, including downward cursor tracking.
 if(s.sip&&scene.prop){
  const rim=attachment(scene.prop,CUP_RIM),dx=(mouth[0]-rim[0])*s.sip,dy=(mouth[1]-rim[1])*s.sip;
  scene.prop.x+=dx;scene.prop.y+=dy;scene.right[0]+=dx;scene.right[1]+=dy;
  if(s.cupSupport){scene.left[0]+=dx*s.cupSupport;scene.left[1]+=dy*s.cupSupport;}
 }
 if(s.mouthFollow){
  const lift=s.mouthFollow,nominal=world([491,585]);
  const dx=(mouth[0]-nominal[0])*lift,dy=(mouth[1]-nominal[1])*lift;
  scene.right[0]+=dx;scene.right[1]+=dy;for(const n of['fork','bite'])if(scene[n]){scene[n].x+=dx;scene[n].y+=dy;}
 }
 const layers=[],arms=[],surfaces=[];
 const add=(name,m,part='hand',opacity=1,clip=null,group=null)=>layers.push({name,m,part,opacity,clip,group});
 for(const[side,root,target,kind,weights,depth]of[['L',world(SHOULDER_ROOTS.L),scene.left,s.leftKind,s.leftGrips,s.leftDepth],['R',world(SHOULDER_ROOTS.R),scene.right,s.rightKind,s.rightGrips,s.rightDepth]]){
  const variants=Object.entries(weights||{[kind]:1}),desired=baseAngle+variants.reduce((sum,[name,weight])=>sum+handPoseAngle(name)*weight,0);
  let grip=[...target],arm=anatomicalArm(root,grip,side,depth,desired);
  if(side==='L'&&s.cupSupport&&scene.prop?.kind==='cup'&&scene.prop.opacity>.001){
   const hand=parts['hand-support'],base=attachment(scene.prop,CUP_BASE.map(v=>v*(scene.prop.scale||1)));
   for(let i=0;i<5;i++){
    const m=between(hand,arm.wrist,arm.grip,45),p=transform(m,...hand.contact),dx=base[0]-p[0],dy=base[1]-p[1];
    if(Math.hypot(dx,dy)<.0001)break;
    grip[0]+=dx*s.cupSupport;grip[1]+=dy*s.cupSupport;arm=anatomicalArm(root,grip,side,depth,desired);
   }
   scene.left=grip;
  }
  arms.push(arm);
  const p=parts['arm'+side],upper=between({...p,b:p.elbow},arm.root,arm.elbow,150),fore=between({...p,a:p.elbow},arm.elbow,arm.wrist,110);surfaces.push(armSurface(p,upper,fore));
  for(const[name,weight]of variants){const hand='hand-'+name;add(hand,between(parts[hand],arm.wrist,arm.grip,45),'hand',weight,null,side+'hand');}
 }
 for(const n of['prop','fork','bite']){
  const p=scene[n];if(!p||p.opacity<=.001)continue;
  const name=p.kind==='cup'?'cupProp':p.kind==='fork'?'forkProp':p.kind,sprite=parts[name],scale=sprite.size/sprite.bounds[2]*(p.scale||1);
  // Fork sizing is by height; other props by width.
  const k=name==='forkProp'?FORK_ART.scale*(p.scale||1):name==='cupProp'?CUP_ART.scale*(p.scale||1):scale;
  add(name,matrix(p.angle,k,sprite.pivot,[p.x,p.y]),'prop',p.opacity);
 }
 return{scene,layers,surfaces,skeleton,left:arms[0],right:arms[1],mouth};
}
function clippedPolygon(p,clip,polygon){
 if(clip==='grasp')return polygon;
 if(!clip)return polygon;const fingers=clip==='fingers',origin=fingers?p.a:p.wrist,dx=(fingers?p.b[0]:p.wrist[0])-p.a[0],dy=(fingers?p.b[1]:p.wrist[1])-p.a[1],len=Math.hypot(dx,dy),sign=fingers||clip==='hand'?1:-1;
 const value=v=>sign*((v[0]-origin[0])*dx+(v[1]-origin[1])*dy)/len+(fingers?-len*.6:7),out=[];
 for(let i=0;i<polygon.length;i++){const a=polygon[i],b=polygon[(i+1)%polygon.length],va=value(a),vb=value(b);if(va>=0)out.push(a);if((va>=0)!==(vb>=0)){const t=va/(va-vb);out.push([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]);}}return out;
}
export function puppetPaintPlan(frame){
 const back=[],front=[],props=frame.layers.filter(l=>l.part==='prop');
 for(const l of frame.layers.filter(l=>l.part==='hand')){
  if(l.name==='hand-support')back.push({...l,group:l.group+':back'});
  else if(l.name==='hand-cup'||l.name==='hand-fork'){
   back.push({...l,group:l.group+':back'});
   front.push({...l,clip:'grasp',group:l.group+':front'});
  }
  else front.push({...l,group:l.group+':front'});
 }
 // The entire tray (including its cake) occludes wrists, palms and the fork
 // while it enters the food. Only the detached bite is in front of the tray.
 if(frame.scene?.prop?.kind==='cake')return[...back,...props.filter(p=>!['cake','bite'].includes(p.name)),...front,...props.filter(p=>p.name==='cake'),...props.filter(p=>p.name==='bite')];
 return[...back,...props,...front];
}
export function drawPuppet(ctx,parts,frame,{skeletonPreview=false,bodyLayer=null}={}){
 // Shoulder roots extend under the clavicle. Forearms stay in front of the body.
 if(bodyLayer){ctx.drawImage(parts.armRenderer.draw(frame.surfaces,0),0,0,1090,1443);ctx.drawImage(bodyLayer,0,0,1090,1443);ctx.drawImage(parts.armRenderer.draw(frame.surfaces,1),0,0,1090,1443);}
 else ctx.drawImage(parts.armRenderer.draw(frame.surfaces),0,0,1090,1443);
 const draw=(layer,target=ctx)=>{
  const p=parts[layer.name];target.save();target.transform(...layer.m);target.globalAlpha=layer.opacity;
  if(layer.clip==='grasp'){
   target.beginPath();
   for(const contour of p.frontContours){contour.forEach(([x,y],i)=>i?target.lineTo(x,y):target.moveTo(x,y));target.closePath();}
   target.clip();
  }else if(layer.clip){
   const polygon=clippedPolygon(p,layer.clip,[[0,0],[p.image.width,0],[p.image.width,p.image.height],[0,p.image.height]]);
   target.beginPath();polygon.forEach(([x,y],i)=>i?target.lineTo(x,y):target.moveTo(x,y));target.closePath();target.clip();
  }
  target.drawImage(p.image,0,0);target.restore();
 };
 const ordered=puppetPaintPlan(frame),done=new Set();
 for(const layer of ordered){if(!layer.group){draw(layer);continue;}if(done.has(layer.group))continue;done.add(layer.group);const group=ordered.filter(l=>l.group===layer.group);
  if(group.length===1){draw(layer);continue;}const tr=ctx.getTransform(),w=Math.max(1,Math.round(1090*Math.hypot(tr.a,tr.b))),h=Math.max(1,Math.round(1443*Math.hypot(tr.c,tr.d)));parts.mixCanvas??=make(w,h);if(parts.mixCanvas.width!==w||parts.mixCanvas.height!==h){parts.mixCanvas.width=w;parts.mixCanvas.height=h;}const mix=parts.mixCanvas.getContext('2d');mix.setTransform(w/1090,0,0,h/1443,0,0);mix.clearRect(0,0,1090,1443);mix.globalCompositeOperation='lighter';group.forEach(l=>draw(l,mix));mix.globalCompositeOperation='source-over';ctx.drawImage(parts.mixCanvas,0,0,1090,1443);
 }
 if(frame.scene.materialize){ctx.save();ctx.globalAlpha=frame.scene.materialize*.65;ctx.fillStyle='#8dded8';for(let i=0;i<6;i++){const a=i*Math.PI/3+frame.scene.materialize,r=58+15*Math.sin(i);ctx.beginPath();ctx.ellipse(frame.scene.prop.x+Math.cos(a)*r,frame.scene.prop.y+Math.sin(a)*r,2,5,a,0,Math.PI*2);ctx.fill();}ctx.restore();}
 if(skeletonPreview){ctx.save();ctx.strokeStyle='#e8bb55';ctx.fillStyle='#e8bb55';ctx.lineWidth=3;for(const arm of[frame.left,frame.right]){ctx.beginPath();ctx.moveTo(arm.root[0],arm.root[1]);for(const p of[arm.elbow,arm.wrist,arm.grip])ctx.lineTo(p[0],p[1]);ctx.stroke();for(const p of[arm.root,arm.elbow,arm.wrist,arm.grip]){ctx.beginPath();ctx.arc(p[0],p[1],5,0,Math.PI*2);ctx.fill();}}ctx.restore();}
}
/** Largest visible limb/prop displacement, in original artwork pixels. */
export function puppetMotionPixels(previous,current){
 if(!previous)return 0;let distance=0;
 for(const side of['left','right'])for(const point of['root','elbow','wrist','grip'])distance=Math.max(distance,Math.hypot(current[side][point][0]-previous[side][point][0],current[side][point][1]-previous[side][point][1]));
 for(const name of['prop','fork','bite']){const a=previous.scene[name],b=current.scene[name];if(a&&b)distance=Math.max(distance,Math.hypot(a.x-b.x,a.y-b.y)+Math.abs(a.angle-b.angle)*80+Math.abs((a.scale??1)-(b.scale??1))*100+Math.abs(a.opacity-b.opacity)*80);}
 return distance;
}
export function pickPuppet(parts,frame,x,y){
 if(!frame)return null;
 const order=puppetPaintPlan(frame);
 for(const l of order.toReversed()){
  if(l.worldClip&&((x-l.worldClip.x)/l.worldClip.rx)**2+((y-l.worldClip.y)/l.worldClip.ry)**2>1)continue;
  if(l.opacity<.1)continue;const[a,b,c,d,e,f]=l.m,det=a*d-b*c,px=(d*(x-e)-c*(y-f))/det,py=(-b*(x-e)+a*(y-f))/det,ix=Math.floor(px),iy=Math.floor(py);
  const p=parts[l.name];if(l.clip==='grasp'&&!p.frontContours.some(poly=>insideContour([px,py],poly)))continue;
  if(l.clip==='fingers'){const dx=p.b[0]-p.a[0],dy=p.b[1]-p.a[1],v=((px-p.a[0])*dx+(py-p.a[1])*dy)/(dx*dx+dy*dy);if(v<.6)continue;}
  if(ix>=0&&iy>=0&&ix<p.image.width&&iy<p.image.height&&p.data[(iy*p.image.width+ix)*4+3]>=32)return l.part==='shaft'?'hand':l.part;
 }for(const surface of frame.surfaces.toReversed()){const hit=armHitPoint(surface,x,y);if(hit)return hit;}return null;
}
/** Compact moving silhouette: transformed alpha strips rather than a large prop rectangle. */
export function puppetRectangles(parts,frame,rig,padding=3){
 const rects=[];
 for(const surface of frame.surfaces)for(const[x,y,w,h]of surface.part.rows){
  const points=[];for(const sy of[y,y+h/2,y+h])for(const sx of[x,x+w/2,x+w])points.push(skinArmPoint(surface,sx,sy));
  const xs=points.map(p=>p[0]*rig.scale+rig.x),ys=points.map(p=>p[1]*rig.scale+rig.y),left=Math.max(0,Math.floor((Math.min(...xs)-padding)/4)*4),top=Math.max(0,Math.floor((Math.min(...ys)-padding)/4)*4),right=Math.min(600,Math.ceil((Math.max(...xs)+padding)/4)*4),bottom=Math.min(800,Math.ceil((Math.max(...ys)+padding)/4)*4);if(right>left&&bottom>top)rects.push({x:left,y:top,width:right-left,height:bottom-top});
 }
 if(frame.scene.materialize&&frame.scene.prop){const p=frame.scene.prop;rects.push({x:rig.x+(p.x-80)*rig.scale,y:rig.y+(p.y-80)*rig.scale,width:160*rig.scale,height:160*rig.scale});}
 for(const l of frame.layers)if(l.opacity>.001)for(const[x,y,w,h]of parts[l.name].rows){
  const polygon=clippedPolygon(parts[l.name],l.clip,[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]);if(!polygon.length)continue;
  const p=polygon.map(v=>transform(l.m,...v)),xs=p.map(v=>v[0]*rig.scale+rig.x),ys=p.map(v=>v[1]*rig.scale+rig.y);
  const left=Math.max(0,Math.floor((Math.min(...xs)-padding)/4)*4),top=Math.max(0,Math.floor((Math.min(...ys)-padding)/4)*4),right=Math.min(600,Math.ceil((Math.max(...xs)+padding)/4)*4),bottom=Math.min(800,Math.ceil((Math.max(...ys)+padding)/4)*4);
  if(right>left&&bottom>top)rects.push({x:left,y:top,width:right-left,height:bottom-top});
 }return rects;
}
