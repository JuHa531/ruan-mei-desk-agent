/** Regression checks for continuous, cursor-independent idle movement. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { jointPose, deformPoint, MESH_GRID } from '../renderer/mesh-rig.mjs';
import { createPetState, advance } from '../renderer/state.mjs';
import {sampleSkeleton,BONE,transform} from '../renderer/skeleton.mjs';

test('hair, fabric and legs keep moving with a stationary cursor, and can be disabled', () => {
  const frames = Array.from({ length: 241 }, (_, frame) => jointPose(frame / 30));
  for (let joint = 0; joint < frames[0].length; joint++) {
    const values = frames.map(frame => frame[joint]);
    assert.ok(Math.max(...values) - Math.min(...values) > .005, `Joint ${joint} must visibly move while idle`);
    const limit = joint === 0 ? .004 : joint === 10 ? .061 : joint === 1 || joint === 2 ? .033 : .042;
    assert.ok(values.every(value => Number.isFinite(value) && Math.abs(value) < limit), 'Idle rotation must remain gentle');
    assert.ok(values.slice(1).every((value, i) => Math.abs(value - values[i]) < .002), 'No discontinuous jumps between frames');
  }
  assert.ok([...jointPose(2.3, false)].every(value => value === 0));
});

test('whole shoes and loose hems travel gently in the default 420 by 560 window', () => {
  // The source is placed at .48 in a 600-wide logical canvas, displayed at 420.
  const sourceToScreen = .48 * 420 / 600;
  const landmarks = {
    leftToe: [500,1370], leftHeel: [492,1334], leftEdge: [535,1350],
    rightToe: [615,1360], rightHeel: [620,1290], rightEdge: [635,1340],
    leftRibbon: [330,1220], rightRibbon: [790,1250], skirtHem: [420,1060],
  };
  for (const [name, point] of Object.entries(landmarks)) {
    const xs = Array.from({length:241}, (_,frame) => deformPoint(...point, frame/30)[0]);
    const travel = (Math.max(...xs)-Math.min(...xs))*sourceToScreen;
    assert.ok(travel >= .25 && travel <= 5, `${name} must keep a small visible skeletal sway, got ${travel.toFixed(2)} pixels`);
    assert.deepEqual(deformPoint(...point, 2.3, false), point, 'Disabling idle movement restores source geometry');
  }
});

// Sample the actual triangle interpolation used by WebGL. Applying the CPU
// weight field directly at an arbitrary pixel would miss mesh interpolation.
function screenPoint(point, time, enabled = true, cat = false, pose = 'idle') {
  const {width,height,columns,rows}=MESH_GRID;
  const gx=point[0]*columns/width,gy=point[1]*rows/height;
  const i=Math.floor(gx),j=Math.floor(gy),u=gx-i,v=gy-j;
  const vertices=u+v<=1 ? [[i,j,1-u-v],[i+1,j,u],[i,j+1,v]]
    : [[i+1,j,1-v],[i+1,j+1,u+v-1],[i,j+1,1-u]];
  return vertices.reduce((sum,[ix,iy,weight])=>{
    const p=deformPoint(ix*width/columns,iy*height/rows,time,enabled,cat,pose);
    return [sum[0]+p[0]*weight,sum[1]+p[1]*weight];
  },[0,0]);
}

const synchronousLandmarks={
  crown:[550,100],topTuft:[925,145],
  leftOuterLock:[200,650],rightOuterLock:[920,620],
  leftInnerLock:[365,400],rightInnerLock:[780,550],fringe:[500,475],
  leftBackHair:[220,1250],rightBackHair:[980,920],
  leftCloak:[290,1210],rightCloak:[815,1188],skirt:[420,1060],
  leftLeg:[534,1357],rightLeg:[663,1300],
};

test('independent skeletal branches keep bounded continuous velocities throughout long idle sessions',()=>{
  const offsets=[0,41.3,3600.7,86400.1],step=1/120;
  let checked=0;
  for(const cat of [false,true])for(const pose of ['idle','tea','cake']) {
    for(const offset of offsets)for(let frame=0;frame<180;frame++) {
      const time=offset+frame/20;
      const velocity=point=>screenPoint(point,time+step,true,cat,pose)[0]-screenPoint(point,time-step,true,cat,pose)[0];
      for(const [name,point]of Object.entries(synchronousLandmarks)) {
        const speed=velocity(point)/(2*step);
        assert.ok(Number.isFinite(speed)&&Math.abs(speed)<25,
          `${name} jumped during skeletal sway at ${time}s, cat=${cat}, pose=${pose}`);
        checked++;
      }
    }
  }
  assert.ok(checked>50000,'Audit must cover all poses and several early/long-running cycles');
  for(const point of Object.values(synchronousLandmarks)) {
    for(const time of [0,.7,9,3601,86400]) {
      const stationary=screenPoint(point,time,false);
      assert.ok(Math.hypot(stationary[0]-point[0],stationary[1]-point[1])<1e-10,
        'Disabling movement must leave every upper and lower landmark stationary');
    }
  }
});

test('hair and lower-body motion keep the entire mesh connected and facing forward', () => {
  // Check the entire production grid, including fringe/face and hip/skirt joins.
  // An inverted triangle would fold an edge even without a topological gap.
  const nx=66, ny=88, dx=1090/nx, dy=1443/ny;
  const area = (a,b,c) => ((b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1]))/(dx*dy);
  for (const [cat,pose] of [false,true].flatMap(cat=>['idle','tea','cake'].map(pose=>[cat,pose]))) for (let time=0; time<8; time+=.2) {
    const rows = Array.from({length:ny+1}, (_,j) => Array.from({length:nx+1}, (_,i) => deformPoint(i*dx,j*dy,time,true,cat,pose)));
    for (let j=0; j<rows.length-1; j++) for (let i=0; i<nx; i++) {
      const a=rows[j][i], b=rows[j][i+1], c=rows[j+1][i], d=rows[j+1][i+1];
      assert.ok(Math.min(area(a,b,c),area(b,d,c)) > .25, `Folded or collapsed mesh at ${i},${j}, time ${time}, cat ${cat}, pose ${pose}`);
    }
  }
});

test('Ruan Mei side locks move while her fringe remains restrained', () => {
 for(const [name,point,min,max] of [
  ['left lock',[200,650],.5,5],['right lock',[920,620],.5,5],
  ['upper fringe',[500,350],.1,1.5],['right hair beside face',[800,520],.5,4],
  ['inner right lock',[780,550],.5,4]]) {
  const xs=Array.from({length:241},(_,frame)=>deformPoint(...point,frame/30)[0]);
  const travel=(Math.max(...xs)-Math.min(...xs))*.336;
  assert.ok(travel>=min&&travel<=max,`${name}: ${travel}`);
 }
});

test('the face and cat ears follow rigid body balance without facial distortion', () => {
  const face=[[413,555],[647,520],[350,515],[450,510],[590,465],[710,510],[531,587],[535,639],[367,619],[667,603]];
  for(let time=0;time<8;time+=.2){
    const rig=sampleSkeleton(time);for(const point of face){const a=deformPoint(...point,time),b=transform(rig.matrices[BONE.head],...point);assert.ok(Math.hypot(a[0]-b[0],a[1]-b[1])<.001,`Facial point ${point} must follow one rigid head`);}
    for(const point of [[222,110],[230,210],[300,180],[842,70],[825,150],[857,210]]) {
      const a=deformPoint(...point,time,true,true),b=transform(rig.matrices[BONE.head],...point);assert.ok(Math.hypot(a[0]-b[0],a[1]-b[1])<.001,`Cat ear ${point} must stay attached to head`);
    }
  }
});

test('sweeping the cursor changes gaze without introducing hair impulses', () => {
  const still = createPetState(), moving = createPetState();
  for (let i = 0; i < 360; i++) {
    moving.target = { x: Math.sin(i * .3) * 6, y: Math.cos(i * .2) * 4 };
    advance(still, 1 / 60); advance(moving, 1 / 60);
    assert.equal(still.hair, moving.hair);
    assert.deepEqual(jointPose(still.time), jointPose(moving.time));
  }
  assert.notDeepEqual(still.gaze, moving.gaze);
});
