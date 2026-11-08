import test from 'node:test';
import assert from 'node:assert/strict';
import {createPetState,setGazeTarget,advance} from '../renderer/state.mjs';
import {deformPoint,meshPointMotionBounds,MESH_GRID} from '../renderer/mesh-rig.mjs';
import {BONES,BONE,skinBinding,sampleSkeleton,transform} from '../renderer/skeleton.mjs';
import {sourceAtMeshPoint} from '../renderer/body-regions.mjs';
test('eyes lead a bounded smooth head response; disabling tracking returns it gently',()=>{
 const s=createPetState();setGazeTarget(s,1,1);advance(s,1/60);
 assert.equal(s.gaze.x,1);assert.ok(s.head.x>0&&s.head.x<.15);
 for(let i=0;i<90;i++)advance(s,1/60);assert.ok(s.head.x>.999);
 const before=s.head.x;advance(s,1/60,{headTracking:false});assert.ok(s.head.x<before&&s.head.x>0);
 for(let i=0;i<90;i++)advance(s,1/60,{eyeTracking:false});assert.ok(s.head.x<.001);
});
test('all 28 bones preserve scale, orthogonality and parent-child bind lengths',()=>{
 assert.equal(BONES.length,28);
 for(const pose of['idle','cake','tea'])for(const x of[-1,0,1])for(const y of[-1,0,1]){
  const rig=sampleSkeleton(2,{head:{x,y},pose,amplitude:2});
  for(const bone of rig.bones){
   const m=rig.matrices[bone.id];assert.ok(Math.abs(m[0]*m[3]-m[1]*m[2]-1)<1e-10);
   assert.ok(Math.abs(Math.hypot(m[0],m[1])-1)<1e-10&&Math.abs(Math.hypot(m[2],m[3])-1)<1e-10,'Bones cannot squash or scale');
   if(bone.parent<0)continue;
   const parent=rig.bones[bone.parent],p=transform(m,...bone.pivot),q=transform(rig.matrices[parent.id],...parent.pivot);
   assert.ok(Math.abs(Math.hypot(p[0]-q[0],p[1]-q[1])-Math.hypot(bone.pivot[0]-parent.pivot[0],bone.pivot[1]-parent.pivot[1]))<1e-9);
  }
 }
});
test('head tracking preserves facial proportions and allows only a small coordinated shoulder rotation',()=>{
 const face=[[350,515],[450,510],[590,465],[710,510],[531,580]];
 const body=[[435,700],[610,700],[495,650],[530,650],[500,735],[560,780],[520,812],[500,950]];
 for(const pose of['idle','cake','tea'])for(const x of[-1,0,1])for(const y of[-1,0,1]){
  const head={x,y},draw=p=>deformPoint(...p,0,false,false,pose,0,head);
  for(const p of body)assert.ok(Math.hypot(draw(p)[0]-p[0],draw(p)[1]-p[1])<1.5,pose+' body '+p);
  for(let i=1;i<face.length;i++){
   const a=draw(face[0]),b=draw(face[i]);
   assert.ok(Math.abs(Math.hypot(a[0]-b[0],a[1]-b[1])-Math.hypot(face[0][0]-face[i][0],face[0][1]-face[i][1]))<.001,'Head must remain a rigid shape');
  }
 }
 const moved=deformPoint(500,400,0,false,false,'idle',0,{x:1,y:0});assert.ok(Math.hypot(moved[0]-500,moved[1]-400)>5,'Head must actually turn');
});
test('each vertex uses four finite nonnegative normalized bone weights',()=>{
 for(const pose of['idle','cake','tea'])for(let y=0;y<1443;y+=23)for(let x=0;x<1090;x+=23){
  const b=skinBinding(x,y,pose);assert.ok(Math.abs([...b.weights].reduce((s,v)=>s+v,0)-1)<1e-6);
  assert.ok([...b.weights].every(v=>Number.isFinite(v)&&v>=0));
  assert.ok([...b.ids].every(id=>Number.isInteger(id)&&id>=0&&id<BONES.length));
 }
});
test('downward gaze bends the neck and lowers the rigid head while preserving the collar',()=>{
 for(const pose of['idle','cake','tea']){
  const rig=sampleSkeleton(0,{enabled:false,head:{x:0,y:1},pose}),p=transform(rig.matrices[BONE.head],525,500);
  assert.ok(p[1]-500>2.5&&p[1]-500<5,'Downward head arc must be visible but restrained');
  const collar=deformPoint(530,650,0,false,false,pose,0,{x:0,y:1});assert.deepEqual(collar,[530,650]);
 }
});
test('skinned picking and analytic native bounds follow head bones with idle disabled',()=>{
 for(const pose of['idle','cake','tea'])for(const[x,y]of[[120,150],[500,500],[750,610],[530,715],[530,800],[530,900]]){
  const bounds=meshPointMotionBounds(x,y,false,false,pose,1,true);
  for(const hx of[-1,0,1])for(const hy of[-1,0,1]){
   const q=deformPoint(x,y,0,false,false,pose,1,{x:hx,y:hy});
   assert.ok(q[0]>=x+bounds[0]-.001&&q[0]<=x+bounds[2]+.001&&q[1]>=y+bounds[1]-.001&&q[1]<=y+bounds[3]+.001);
  }
 }
 const head={x:1,y:-1},p=deformPoint(500,500,0,false,false,'idle',0,head);
 const hit=sourceAtMeshPoint(...p,{time:0,head,pose:'idle'},{hairMotion:false,headTracking:true});
 assert.ok(Math.abs(hit.x-500)<.01&&Math.abs(hit.y-500)<.01);
});
test('combined skeleton and extreme gaze keep the production triangles connected and facing forward',()=>{
 const {width,height,columns:nx,rows:ny}=MESH_GRID,dx=width/nx,dy=height/ny;
 const area=(a,b,c)=>((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/(dx*dy);
 for(const pose of['idle','cake','tea'])for(const head of[{x:1,y:1},{x:-1,y:-1},{x:-1,y:1},{x:1,y:-1}]){
  const grid=Array.from({length:ny+1},(_,j)=>Array.from({length:nx+1},(_,i)=>deformPoint(i*dx,j*dy,Math.PI/1.8,true,false,pose,2,head)));
  for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
   const a=grid[j][i],b=grid[j][i+1],c=grid[j+1][i],d=grid[j+1][i+1];
   assert.ok(Math.min(area(a,b,c),area(b,d,c))>.15,pose+' folded '+i+','+j);
  }
 }
});
