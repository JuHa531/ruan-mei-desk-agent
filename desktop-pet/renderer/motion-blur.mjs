/** Short temporal exposure. Static frames stay sharp; no persistent trails. */
import {poseIsChanging} from './pose-transition.mjs';
export function exposureSamples(previous,current,settings={},paintMotion=null){
 const strength=Number.isFinite(settings.motionBlurStrength)?Math.max(0,Math.min(1,settings.motionBlurStrength)):.6;
 const dt=current.time-(previous?.time??current.time);
 if(settings.motionBlur===false||!strength||!previous||dt<=0||dt>.09)return[{state:current,weight:1,x:0,y:0}];
 const drag=current.dragVelocity||{x:0,y:0};
 const measured=paintMotion&&Number.isFinite(paintMotion.pixels);
 const movement=(measured?paintMotion.pixels:(poseIsChanging(current)||poseIsChanging(previous)?dt*60:0))+Math.abs(current.gaze.x-previous.gaze.x)*5+Math.abs(current.gaze.y-previous.gaze.y)*6+
  Math.abs((current.head?.x||0)-(previous.head?.x||0))*24+Math.abs((current.head?.y||0)-(previous.head?.y||0))*12+
  Math.abs(current.blink-previous.blink)*35+(current.facial||[]).reduce((n,v,i)=>n+Math.abs(v-(previous.facial?.[i]??v))*15,0)+
  (settings.hairMotion===false?0:Math.abs((current.motionTime??current.time)-(previous.motionTime??previous.time))*4)+Math.hypot(drag.x,drag.y)*dt;
 // Subpixel sways do not need three whole-character GPU renders. Keep temporal
 // exposure for visible limb movement, blinks, expressions and cursor following.
 if(movement*(measured?paintMotion.scale:1)<(measured ? .35 : .025)&&current.pose===previous.pose)return[{state:current,weight:1,x:0,y:0}];
 const shutter=Math.min(dt,.018)*strength,span=shutter/dt;
 const phases=measured&&dt>1/45?[0,1]:[0,.5,1],weights=phases.length===2?[.4,.6]:[.25,.4,.35];
 return phases.map((v,index)=>{
  const t=1-span*(1-v),lerp=(a,b)=>a+(b-a)*t;
  const state={...current,time:lerp(previous.time,current.time),actionTime:lerp(previous.actionTime??previous.time,current.actionTime??current.time),motionTime:lerp(previous.motionTime??previous.time,current.motionTime??current.time),
   gaze:{x:lerp(previous.gaze.x,current.gaze.x),y:lerp(previous.gaze.y,current.gaze.y)},blink:lerp(previous.blink,current.blink),
   head:{x:lerp(previous.head?.x||0,current.head?.x||0),y:lerp(previous.head?.y||0,current.head?.y||0)},
   facial:current.facial?.map((value,i)=>lerp(previous.facial?.[i]??value,value))};
  return{state,weight:weights[index],x:Math.max(-16,Math.min(16,-drag.x*shutter*(1-v))),y:Math.max(-16,Math.min(16,-drag.y*shutter*(1-v)))};
 });
}
