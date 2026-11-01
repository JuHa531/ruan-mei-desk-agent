/** Ruan Mei artwork, independent expressions/actions, and a retargeted desktop rig. */
import {createMeshRig} from './mesh-rig.mjs';
import {motionAmplitude,motionTime} from './motion-settings.mjs';
import {createFacialLayers} from './facial-rig.mjs';
import {exposureSamples} from './motion-blur.mjs';
import {BONE,drawSkeleton} from './skeleton.mjs';
import {createCleanBody,createPuppetArt,puppetFrame,drawPuppet,puppetMotionPixels} from './puppet-art.mjs';
const W=1090,H=1443;
export const RIG=Object.freeze({width:W,height:H,x:38,y:68,scale:.48,gazeX:288,gazeY:310});
const poseIndex={idle:0,cake:1,tea:2};
const canvas=()=>Object.assign(document.createElement('canvas'),{width:W,height:H});
function accessories(ctx,state){
  if(state.cat){
    ctx.lineWidth=8;ctx.strokeStyle='#302f37';ctx.fillStyle='#4a414c';
    for(const [x,flip]of[[245,-1],[780,1]]){
      ctx.beginPath();ctx.moveTo(x-70,190);ctx.quadraticCurveTo(x-50,65,x+flip*45,40);
      ctx.quadraticCurveTo(x+80,125,x+70,205);ctx.closePath();ctx.fill();ctx.stroke();
      ctx.fillStyle='#79aaa6';ctx.beginPath();ctx.moveTo(x-35,163);ctx.lineTo(x+flip*32,80);ctx.lineTo(x+40,172);ctx.closePath();ctx.fill();ctx.fillStyle='#4a414c';
    }
  }
}
export function composeCharacterFrame(images,state){
  const result=canvas(),ctx=result.getContext('2d');
  const target=images.body||images.neutral;
  ctx.drawImage(target,0,0,W,H);
  accessories(ctx,state);return result;
}
export async function loadCharacter(){
  const load=async name=>{const img=new Image();img.src=new URL('../assets/character/'+name,import.meta.url).href;await img.decode();return img;};
  const neutral=await load('ruanmei-neutral.png');
  const [clean,parts,hands,arms,leftForkHand]=await Promise.all([load('ruanmei-body-clean-v1.png'),load('ruanmei-puppet-parts-v1.png'),load('ruanmei-hands-v2.png'),load('ruanmei-continuous-arms-v3.png'),load('ruanmei-fork-left-dorsal-v3.png')]);
  const body=createCleanBody(neutral,clean),puppet=createPuppetArt(parts,hands,arms,leftForkHand),images={neutral,body,poses:Object.fromEntries(Object.keys(poseIndex).map(p=>[p,body]))};
  const mesh=createMeshRig();return{images,mesh,renderer:mesh,cache:new Map(),normal:mesh,
    puppet,assetsReady:true};
}
/** Upload the shared body before interaction; props and limbs are already decoded. */
export async function warmCharacterPoses(rigs,settings={}){
 for(const pose of ['idle']){
  const state={pose,cat:settings.cat===true,gaze:{x:0,y:0},head:{x:0,y:0},time:0,blink:0},key=JSON.stringify([pose,state.cat]);
  let source=rigs.cache.get(key);if(!source){source=composeCharacterFrame(rigs.images,state);rigs.cache.set(key,source);}
  rigs.mesh.draw(source,key,state,settings);await new Promise(resolve=>setTimeout(resolve,0));
 }
}
export function drawCharacter(ctx,rigs,state,settings={}){
  // Rasterize for the visible size, with 1.5× oversampling. A small pet does not
  // need several full 1090×1443 GPU/Canvas copies for every temporal sample.
  const tr=ctx.getTransform(),visible=Math.max(Math.hypot(tr.a,tr.b),Math.hypot(tr.c,tr.d))*RIG.scale;
  const resolution=Math.min(1,Math.max(.25,Math.ceil(visible*1.5*8)/8));
  if(rigs.resolution!==resolution){
    rigs.resolution=resolution;rigs.mesh.setResolution(resolution);rigs.puppet.armRenderer.setResolution(resolution);
    for(const name of['sampleLayer','exposure']){rigs[name]??=canvas();rigs[name].width=Math.round(W*resolution);rigs[name].height=Math.round(H*resolution);}
  }
  const currentAction=puppetFrame(rigs.puppet,state,settings);
  const sourceFor=(pose,sample)=>{
    const key=JSON.stringify([pose,sample.cat]);let source=rigs.cache.get(key);
    if(!source){source=composeCharacterFrame(rigs.images,{...sample,pose});rigs.cache.set(key,source);if(rigs.cache.size>8)rigs.cache.delete(rigs.cache.keys().next().value);}
    return{key,source};
  };
  const renderSample=(image,imageKey,sample)=>{
    const action=Math.abs(sample.time-state.time)<1e-9?currentAction:puppetFrame(rigs.puppet,sample,settings);
    const raw=rigs.mesh.draw(image,imageKey,{...sample,pose:'idle',mouthOpen:action.scene.mouthOpen,chew:action.scene.chew},settings,sample.expression!=='dizzy');
    const sc=rigs.sampleLayer.getContext('2d');sc.setTransform(rigs.sampleLayer.width/W,0,0,rigs.sampleLayer.height/H,0,0);sc.clearRect(0,0,W,H);drawPuppet(sc,rigs.puppet,action,{...settings,bodyLayer:raw});rigs.actionFrame=action;
    if(sample.glasses){
      sc.save();
      const transform=rigs.mesh.skeleton?.matrices[BONE.head];if(transform)sc.transform(...transform);
      const points=createFacialLayers(image).eyes;sc.strokeStyle='#b29b68';sc.lineWidth=6;
      for(const[x,y]of points){sc.beginPath();sc.ellipse(x,y,70,49,-.12,0,Math.PI*2);sc.stroke();}
      if(points.length===2){sc.beginPath();sc.moveTo(points[0][0]+70,points[0][1]-8);sc.quadraticCurveTo((points[0][0]+points[1][0])/2,points[1][1]-16,points[1][0]-70,points[1][1]);sc.stroke();}
      sc.restore();
    }
    if(settings.skeletonPreview&&rigs.mesh.skeleton)drawSkeleton(sc,rigs.mesh.skeleton,{excludeArmChains:true});
    sc.save();sc.setTransform(1/RIG.scale,0,0,1/RIG.scale,-RIG.x/RIG.scale,-RIG.y/RIG.scale);drawCharacterDecorations(sc,rigs.images,sample,settings);sc.restore();return rigs.sampleLayer;
  };
  const poseFrame=sample=>{
    const{source,key}=sourceFor('idle',sample);return renderSample(source,key,sample);
  };
  const samples=exposureSamples(rigs.previousFrame,state,settings,{pixels:puppetMotionPixels(rigs.previousActionFrame,currentAction),scale:visible});
  rigs.previousActionFrame=currentAction;
  let frame;
  if(samples.length===1)frame=poseFrame(state);
  else{
    rigs.exposure??=canvas();const ec=rigs.exposure.getContext('2d');ec.clearRect(0,0,W,H);ec.globalCompositeOperation='lighter';
    for(const sample of samples){
      ec.globalAlpha=sample.weight;ec.drawImage(poseFrame(sample.state),sample.x*resolution,sample.y*resolution);
    }
    ec.globalAlpha=1;ec.globalCompositeOperation='source-over';frame=rigs.exposure;
  }
  rigs.previousFrame={...state,gaze:{...state.gaze},head:{...state.head},facial:state.facial?.slice(),dragVelocity:{...state.dragVelocity}};
  ctx.clearRect(0,0,600,800);ctx.save();ctx.translate(RIG.x,RIG.y);ctx.scale(RIG.scale,RIG.scale);
  ctx.drawImage(frame,0,0,W,H);
  ctx.restore();
}
export function drawCharacterDecorations(ctx,_images,state,settings={}){
  const drift=Math.sin(motionTime(state,settings)) * 3 * motionAmplitude(settings);
  ctx.save();ctx.fillStyle='#59968f';ctx.font='italic 24px Georgia';
  if(state.expression==='sleep')ctx.fillText('z z',125,115+drift);
  if(state.expression==='dizzy'){ctx.font='25px Georgia';ctx.fillText('✧  ·  ✧',210,95+drift);}
  ctx.restore();
}
