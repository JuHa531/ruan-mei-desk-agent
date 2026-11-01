/** Hierarchical skeleton skinning over the original illustration, shared with CPU picking. */
import {motionAmplitude,motionTime} from './motion-settings.mjs';
import {eyeWarpStrength} from './gaze-settings.mjs';
import {createFacialLayers,facialTarget} from './facial-rig.mjs';
import {BONES,BONE,sampleSkeleton,skinBinding,deformSkinPoint,skinMotionBounds} from './skeleton.mjs';
import {poseGesture} from './pose-transition.mjs';
const W=1090,H=1443,clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export const MESH_GRID=Object.freeze({width:W,height:H,columns:66,rows:176});
const idleJoints=['crown','hair-left','hair-right','hair-tail','ribbon-left','sleeve-left','sleeve-right','skirt','thigh-left','thigh-right','bangs','tuft'];
export function jointPose(time=0,enabled=true,amplitude=1){
 const rig=sampleSkeleton(time,{enabled,amplitude});
 return Float32Array.from(idleJoints,name=>rig.localAngles[BONE[name]]);
}
export function deformPoint(x,y,time=0,enabled=true,cat=false,pose='idle',amplitude=1,head={},gesture={}){
 return deformSkinPoint(x,y,sampleSkeleton(time,{enabled,amplitude,pose,head,gesture}),pose,cat);
}
export function meshPointMotionBounds(x,y,enabled=true,cat=false,pose='idle',amplitude=1,headTracking=false){
 return skinMotionBounds(x,y,{enabled,amplitude,pose,cat,headTracking});
}
const vertexSource="\nprecision highp float;\nattribute vec2 a_position;\nattribute vec4 a_ids;\nattribute vec4 a_weights;\nuniform mat3 u_bones[BONE_COUNT];\nvarying vec2 v_uv;\nvoid main(){\n vec3 p=vec3(a_position,1.0);\n vec2 delta=(u_bones[int(a_ids.x)]*p-p).xy*a_weights.x+\n  (u_bones[int(a_ids.y)]*p-p).xy*a_weights.y+\n  (u_bones[int(a_ids.z)]*p-p).xy*a_weights.z+\n  (u_bones[int(a_ids.w)]*p-p).xy*a_weights.w;\n v_uv=a_position/vec2(1090.0,1443.0);\n vec2 target=(a_position+delta)/vec2(1090.0,1443.0);\n gl_Position=vec4(target*vec2(2.0,-2.0)+vec2(-1.0,1.0),0.0,1.0);\n}".replace('BONE_COUNT',BONES.length);
const fragmentSource = `
precision highp float;
uniform sampler2D u_image;
uniform sampler2D u_iris;
uniform sampler2D u_aperture;
uniform sampler2D u_eyeImage;
uniform sampler2D u_foreground;
uniform sampler2D u_closedLids;
uniform vec2 u_gaze;
uniform float u_gazeStrength;
uniform vec4 u_eyes[2];
uniform vec2 u_eyeOpen;
uniform vec2 u_eyeTilt;
uniform float u_mouthCurve;
uniform float u_mouthOpen;
uniform float u_chew;
varying vec2 v_uv;
vec4 paintedEye(vec4 color,vec2 p,vec4 eye,float openness,float tilt){
 vec2 q=p-eye.xy;
 if(abs(q.x)>eye.z+3.0||abs(q.y)>eye.w*1.2)return color;
 float opening=clamp(openness,.018,1.12);
 vec2 uv=(eye.xy+vec2(q.x,(q.y-tilt*q.x)/opening))/vec2(1090.0,1443.0);
 vec4 feature=texture2D(u_eyeImage,uv);
 float aperture=texture2D(u_aperture,uv).a*feature.a;
 vec4 iris=texture2D(u_iris,uv-u_gaze*vec2(5.0,6.0)*u_gazeStrength/vec2(1090.0,1443.0));
 feature.rgb=feature.rgb*(1.0-iris.a*aperture)+iris.rgb*aperture;
 float close=1.0-smoothstep(.055,.24,opening);
 color=color*(1.0-feature.a*(1.0-close))+feature*(1.0-close);
 vec4 lid=texture2D(u_closedLids,(eye.xy+vec2(q.x,q.y-tilt*q.x))/vec2(1090.0,1443.0));
 return color*(1.0-lid.a*close)+lid*close;
}
void main() {
  vec2 p = v_uv*vec2(1090.0,1443.0);
  vec2 skinPoint=p;
  vec2 browL=p-(u_eyes[0].xy+vec2(-12.0,-56.0)),browR=p-(u_eyes[1].xy+vec2(-28.0,-54.0));
  skinPoint.y+=u_eyeTilt.x*smoothstep(.1,.45,u_eyeOpen.x)*browL.x*(1.0-smoothstep(.5,1.0,length(browL/vec2(45.0,13.0))));
  skinPoint.y+=u_eyeTilt.y*smoothstep(.1,.45,u_eyeOpen.y)*browR.x*(1.0-smoothstep(.5,1.0,length(browR/vec2(45.0,13.0))));
  vec2 mouth=p-vec2((u_eyes[0].x+u_eyes[1].x)*.5,(u_eyes[0].y+u_eyes[1].y)*.5+92.0);
  float area=(1.0-smoothstep(20.0,34.0,abs(mouth.x)))*(1.0-smoothstep(7.0,18.0,abs(mouth.y)));
  vec4 color=texture2D(u_image,(skinPoint-vec2(0.0,u_mouthCurve*(1.0-pow(clamp(mouth.x/28.0,-1.0,1.0),2.0))*area))/vec2(1090.0,1443.0));
  color=paintedEye(color,p,u_eyes[0],u_eyeOpen.x,u_eyeTilt.x);
  color=paintedEye(color,p,u_eyes[1],u_eyeOpen.y,u_eyeTilt.y);
  vec4 fringe=texture2D(u_foreground,v_uv);
  color=color*(1.0-fringe.a)+fringe;
  vec2 lip=p-vec2(491.0,585.0);
  float opening=max(u_mouthOpen,u_chew*.16);
  if(opening>.001){
   float interior=(1.0-smoothstep(.8,1.0,length(lip/vec2(10.0+opening*3.0,2.0+opening*7.0))))*opening;
   color.rgb=mix(color.rgb,vec3(.27,.12,.16),interior);
  }
  gl_FragColor=color;
}`;

/** Up to four normalized bone influences per vertex, with fixed-length rigid bone matrices. */
export function createMeshRig(){
 const canvas=document.createElement('canvas');canvas.width=W;canvas.height=H;
 const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:true,preserveDrawingBuffer:true,depth:false});
 let available=false,previousSource=null,previousKey=null,previousBinding=null,skeleton=null,program,bonesUniform,bindAttributes,createTextureSet;
 let eyesUniform,eyeOpen,eyeTilt,mouthCurve,mouthOpen,chew,gaze,gazeStrength,count=0;
 const textureCache=new Map(),vertexCache=new Map();
 canvas.addEventListener('webglcontextlost',()=>{available=false;});
 try{
  if(!gl)throw new Error('WebGL unavailable');
  const compile=(type,source)=>{const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;};
  program=gl.createProgram();gl.attachShader(program,compile(gl.VERTEX_SHADER,vertexSource));gl.attachShader(program,compile(gl.FRAGMENT_SHADER,fragmentSource));gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));gl.useProgram(program);
  const attributes=[['position',2,0],['ids',4,2],['weights',4,6]].map(([name,size,offset])=>({attribute:gl.getAttribLocation(program,'a_'+name),size,offset}));
  for(const{attribute}of attributes)gl.enableVertexAttribArray(attribute);
  bindAttributes=buffer=>{gl.bindBuffer(gl.ARRAY_BUFFER,buffer);for(const{attribute,size,offset}of attributes)gl.vertexAttribPointer(attribute,size,gl.FLOAT,false,40,offset*4);};
  createTextureSet=()=>Array.from({length:6},()=>{
   const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);return texture;
  });
  for(const[unit,name]of['u_image','u_iris','u_aperture','u_eyeImage','u_foreground','u_closedLids'].entries()){
   gl.uniform1i(gl.getUniformLocation(program,name),unit);
  }
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);
  bonesUniform=gl.getUniformLocation(program,'u_bones[0]');
  eyesUniform=gl.getUniformLocation(program,'u_eyes[0]');eyeOpen=gl.getUniformLocation(program,'u_eyeOpen');eyeTilt=gl.getUniformLocation(program,'u_eyeTilt');mouthCurve=gl.getUniformLocation(program,'u_mouthCurve');
  gaze=gl.getUniformLocation(program,'u_gaze');gazeStrength=gl.getUniformLocation(program,'u_gazeStrength');
  mouthOpen=gl.getUniformLocation(program,'u_mouthOpen');chew=gl.getUniformLocation(program,'u_chew');
  gl.viewport(0,0,W,H);gl.disable(gl.BLEND);gl.disable(gl.DEPTH_TEST);gl.clearColor(0,0,0,0);available=true;
 }catch(error){console.warn('Skeleton renderer unavailable:',error.message);}
 return{
  mode:'mesh',
  get skeleton(){return skeleton;},
  get boneCount(){return BONES.length;},
  get eyeTrackingAvailable(){return available;},
  get accelerated(){return available;},
  setResolution(scale=1){const width=Math.max(1,Math.round(W*scale)),height=Math.max(1,Math.round(H*scale));if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;gl?.viewport(0,0,width,height);}},
  draw(source,key,state,settings={},allowGaze=true){
   if(!available||gl.isContextLost()){available=false;return source;}
   const pose=state.pose||'idle',bindingKey=pose+':'+!!state.cat,track=allowGaze&&settings.eyeTracking!==false;
   skeleton=sampleSkeleton(motionTime(state,settings),{enabled:settings.hairMotion!==false,amplitude:motionAmplitude(settings),pose,gesture:poseGesture(state),head:track&&settings.headTracking!==false?state.head:{}});
   if(previousBinding!==bindingKey){
    let entry=vertexCache.get(bindingKey);
    if(!entry){
     const data=[],{columns:nx,rows:ny}=MESH_GRID;
     const add=(i,j)=>{const x=W*i/nx,y=H*j/ny,binding=skinBinding(x,y,pose,!!state.cat);data.push(x,y,...binding.ids,...binding.weights);};
     for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){add(i,j);add(i+1,j);add(i,j+1);add(i+1,j);add(i+1,j+1);add(i,j+1);}
     const vertices=new Float32Array(data),buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,vertices,gl.STATIC_DRAW);
     entry={buffer,count:vertices.length/10};vertexCache.set(bindingKey,entry);
    }
    bindAttributes(entry.buffer);count=entry.count;previousBinding=bindingKey;
   }
   if(previousSource!==source||previousKey!==key){
    let entry=textureCache.get(key);
    if(entry&&entry.source!==source){for(const t of entry.textures)gl.deleteTexture(t);textureCache.delete(key);entry=null;}
    if(!entry){
     const layers=createFacialLayers(source),textures=createTextureSet();
     for(const[unit,image]of[layers.base,layers.iris,layers.mask,layers.eye,layers.foreground,layers.closed].entries()){
      gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,textures[unit]);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
     }
     entry={source,textures,eyes:layers.eyes};
    }
    textureCache.delete(key);textureCache.set(key,entry);
    if(textureCache.size>4){const oldKey=textureCache.keys().next().value;for(const t of textureCache.get(oldKey).textures)gl.deleteTexture(t);textureCache.delete(oldKey);}
    entry.textures.forEach((texture,unit)=>{gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,texture);});
    gl.uniform4fv(eyesUniform,Float32Array.from(entry.eyes.length===2?entry.eyes.flat():[388,507,78,66,594,480,78,66]));previousSource=source;previousKey=key;
   }
   gl.uniformMatrix3fv(bonesUniform,false,skeleton.gpu);
   gl.uniform2f(gaze,track?clamp(state.gaze?.x||0,-1,1):0,track?clamp(state.gaze?.y||0,-1,1):0);gl.uniform1f(gazeStrength,eyeWarpStrength(settings));
   const face=state.facial||facialTarget(state.expression),blink=clamp(state.blink||0,0,1);
   gl.uniform2f(eyeOpen,face[0]*(1-blink),face[1]*(1-blink));gl.uniform2f(eyeTilt,face[2],face[3]);gl.uniform1f(mouthCurve,face[4]);
   gl.uniform1f(mouthOpen,clamp(state.mouthOpen||0,0,1));gl.uniform1f(chew,clamp(state.chew||0,0,1));
   gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLES,0,count);return canvas;
  },
 };
}
