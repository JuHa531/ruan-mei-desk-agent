/** Traced lid silhouette from the user's closed-eye reference. Ink only, no skin patch. */
export function createClosedEyes(eyes,width,height){
 const canvas=Object.assign(document.createElement('canvas'),{width,height}),ctx=canvas.getContext('2d');
 for(const[index,[x,y]]of eyes.entries()){
  ctx.save();ctx.translate(x,y);ctx.scale(index===0?1:-1,1);ctx.fillStyle='#38232d';
  ctx.beginPath();ctx.moveTo(-64,-2);ctx.bezierCurveTo(-43,3,-4,7,56,-3);
  ctx.lineTo(54,3);ctx.quadraticCurveTo(52,5,49,6);ctx.bezierCurveTo(22,11,-23,13,-62,6);
  ctx.quadraticCurveTo(-68,3,-70,-4);ctx.quadraticCurveTo(-66,-3,-64,-2);ctx.closePath();ctx.fill();
  for(const[a,b,c,d,e,f]of[[-56,6,-59,12,-49,10],[-39,10,-41,14,-33,11],[-23,11,-24,13,-18,11]]){
   ctx.beginPath();ctx.moveTo(a,b);ctx.quadraticCurveTo(c+2,d-2,c,d);ctx.quadraticCurveTo(e-2,f+1,e,f);ctx.closePath();ctx.fill();
  }
  ctx.restore();
 }
 return canvas;
}
