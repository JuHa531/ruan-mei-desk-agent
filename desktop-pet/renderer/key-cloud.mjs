/** One transient printable keystroke, using MeiMei's jade/teal interface palette. */
export const KEY_CLOUD_PALETTE=Object.freeze({
  top:'#183e36',middle:'#102e27',bottom:'#071b17',border:'#7ee0c6',
  detail:'#4ba99e',highlight:'#b1eee0',glyph:'#eaf7f1',glyphOutline:'#a3e5d7',
});
export const KEY_CLOUD=Object.freeze({x:422,y:354,holdSeconds:.7,fadeSeconds:.3});
// The character remains 600×800; only the transparent effect canvas extends left.
export const KEY_EFFECT_BOUNDS=Object.freeze({left:140,width:740,height:800});
/** Hold briefly, then fade at the same position for every supported action. */
export function keyCloudFrame(display){
  const age=Math.max(0,Number.isFinite(display?.age)?display.age:0);
  const duration=KEY_CLOUD.holdSeconds+KEY_CLOUD.fadeSeconds;
  const progress=Math.min(1,age/duration);
  return {x:KEY_CLOUD.x,y:KEY_CLOUD.y,scale:1,
    opacity:Math.max(0,Math.min(display?.opacity??1,(duration-age)/KEY_CLOUD.fadeSeconds)),progress};
}

/** Only a single letter, digit, punctuation mark or ordinary space can be shown. */
export function isDisplayCharacter(value){
  return typeof value==='string'&&([...value].length===1)&&(/^[\x20-\x7e]$/.test(value)||/^\p{P}$/u.test(value));
}

/** Keep the latest character only; no input history survives a clear or timeout. */
export function createKeyDisplay(){
  let character=null,receivedAt=0;
  return {
    receive(value,now){
      if(!isDisplayCharacter(value)||!Number.isFinite(now))return false;
      character=value;receivedAt=now;return true;
    },
    clear(){character=null;receivedAt=0;},
    snapshot(now){
      if(character===null)return null;
      const age=Math.max(0,(now-receivedAt)/1000),duration=KEY_CLOUD.holdSeconds+KEY_CLOUD.fadeSeconds;
      if(age>=duration){character=null;receivedAt=0;return null;}
      return {character,age,opacity:Math.min(1,(duration-age)/KEY_CLOUD.fadeSeconds)};
    },
  };
}

function outline(ctx){
  ctx.beginPath();ctx.moveTo(-41,-7);
  ctx.bezierCurveTo(-51,-27,-29,-44,-17,-35);
  ctx.bezierCurveTo(-7,-53,20,-50,26,-33);
  ctx.bezierCurveTo(47,-38,58,-14,44,0);
  ctx.bezierCurveTo(56,17,41,37,25,33);
  ctx.bezierCurveTo(20,51,-7,52,-17,36);
  ctx.bezierCurveTo(-35,45,-51,28,-42,14);
  ctx.bezierCurveTo(-54,9,-53,-3,-41,-7);ctx.closePath();
}

/** Vector artwork stays crisp as the desktop pet is resized, without changing its source art. */
export function drawKeyCloud(ctx,display,{silhouette=false}={}){
  if(!display||!isDisplayCharacter(display.character))return;
  const frame=keyCloudFrame(display);
  if(!silhouette&&frame.opacity<=0)return;
  ctx.save();ctx.globalAlpha=silhouette?1:frame.opacity;
  ctx.translate(frame.x,frame.y);ctx.scale(frame.scale,frame.scale);
  ctx.lineJoin='round';ctx.lineCap='round';
  outline(ctx);
  const fill=ctx.createLinearGradient(0,-45,0,46);
  fill.addColorStop(0,KEY_CLOUD_PALETTE.top);fill.addColorStop(.65,KEY_CLOUD_PALETTE.middle);fill.addColorStop(1,KEY_CLOUD_PALETTE.bottom);
  ctx.fillStyle=silhouette?'#fff':fill;ctx.fill();
  ctx.strokeStyle=silhouette?'#fff':KEY_CLOUD_PALETTE.border;ctx.lineWidth=2.5;ctx.stroke();
  if(!silhouette){
    ctx.beginPath();ctx.moveTo(-35,24);ctx.bezierCurveTo(-30,32,-23,33,-16,29);
    ctx.bezierCurveTo(-6,45,15,44,21,28);ctx.bezierCurveTo(31,33,41,25,42,18);
    ctx.strokeStyle=KEY_CLOUD_PALETTE.detail;ctx.lineWidth=2.1;ctx.stroke();
    ctx.beginPath();ctx.moveTo(-36,-16);ctx.bezierCurveTo(-36,-25,-28,-30,-22,-27);
    ctx.strokeStyle=KEY_CLOUD_PALETTE.highlight;ctx.lineWidth=3.2;ctx.stroke();
    ctx.beginPath();ctx.moveTo(-5,-36);ctx.bezierCurveTo(3,-41,15,-37,18,-30);ctx.stroke();
  }
  if(!silhouette){
    const value=display.character;
    ctx.strokeStyle=KEY_CLOUD_PALETTE.glyphOutline;ctx.fillStyle=KEY_CLOUD_PALETTE.glyph;ctx.lineWidth=.65;
    if(value===' '){
      // Draw the open-box space symbol explicitly so it never becomes a missing-font square.
      ctx.beginPath();ctx.moveTo(-15,-1);ctx.lineTo(-15,9);ctx.quadraticCurveTo(-15,12,-12,12);
      ctx.lineTo(12,12);ctx.quadraticCurveTo(15,12,15,9);ctx.lineTo(15,-1);ctx.lineWidth=3.6;ctx.stroke();
    }else{
      ctx.font='bold 39px "Comic Sans MS", "Microsoft YaHei", sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
      ctx.strokeText(value,0,1);ctx.fillText(value,0,1);
    }
  }
  ctx.restore();
}
