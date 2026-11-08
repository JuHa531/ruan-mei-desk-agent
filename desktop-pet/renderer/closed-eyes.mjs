/** Individually drawn closed lids in source coordinates; no mirrored strip or face patch. */
function screenLeft(ctx){
 // Character's right eye: a longer low arc, lifted outer corner and fine inner tip.
 ctx.moveTo(-73,-9);
 ctx.bezierCurveTo(-59,-2,-40,3,-19,4);
 ctx.bezierCurveTo(9,6,37,2,60,-5);
 ctx.quadraticCurveTo(56,1,49,4);
 ctx.bezierCurveTo(29,12,-1,15,-25,11);
 // Small outer lashes belong to the lower contour, rather than floating marks.
 ctx.lineTo(-31,15);ctx.lineTo(-33,10);
 ctx.quadraticCurveTo(-44,8,-49,5);
 ctx.lineTo(-56,11);ctx.lineTo(-56,2);
 ctx.quadraticCurveTo(-67,-1,-73,-9);
}
function screenRight(ctx){
 // Character's left eye: foreshortened nasal end, shallower arc and raised temporal wing.
 ctx.moveTo(-53,-4);
 ctx.bezierCurveTo(-36,-1,-15,-2,2,-5);
 ctx.bezierCurveTo(24,-8,41,-15,55,-21);
 ctx.quadraticCurveTo(53,-12,46,-7);
 ctx.lineTo(48,-1);ctx.lineTo(41,-4);
 ctx.quadraticCurveTo(36,-1,31,0);
 ctx.lineTo(31,4);ctx.lineTo(25,2);
 ctx.bezierCurveTo(3,8,-22,10,-44,2);
 ctx.quadraticCurveTo(-51,0,-53,-4);
}
export function createClosedEyes(eyes,width,height){
 const canvas=Object.assign(document.createElement('canvas'),{width,height}),ctx=canvas.getContext('2d');
 for(const[index,[x,y]]of eyes.entries()){
  ctx.save();ctx.translate(x,y);ctx.fillStyle='#413134';
  ctx.beginPath();(index===0?screenLeft:screenRight)(ctx);ctx.closePath();ctx.fill();
  ctx.restore();
 }
 return canvas;
}
