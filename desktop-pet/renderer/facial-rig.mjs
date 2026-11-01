/** A single-illustration facial rig. No expression-picture replacement. */
import {createClosedEyes} from './closed-eyes.mjs';
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
export const BLINK_DURATION=.34;
export function blinkClosure(age){
 const ease=x=>{x=clamp(x,0,1);return x*x*(3-2*x);};
 if(age<0||age>=BLINK_DURATION)return 0;
 if(age<.105)return ease(age/.105);
 if(age<.145)return 1;
 return 1-ease((age-.145)/.195);
}
export function facialTarget(expression){
 const values={blush:[.94,.94,-.015,.015,-.8],angry:[.72,.72,.085,-.085,1.2],sleep:[.025,.025,0,0,0],surprise:[1.09,1.09,0,0,0],dizzy:[.83,.83,-.035,.035,0],wink:[.025,.96,0,0,-.6],cry:[.78,.78,-.075,.075,.8],heart:[.94,.94,-.015,.015,-.8],smile:[.84,.84,-.01,.01,-1.2],awkward:[.84,1.02,-.045,.025,.4]};
 return values[expression]?.slice()||[1,1,0,0,0];
}
const cache=new WeakMap();
const makeCanvas=(w,h)=>Object.assign(document.createElement('canvas'),{width:w,height:h});
const cyan=(r,g,b)=>r<160&&g>130&&b>130&&g>r*1.2&&b>r*1.2;
const apertureColor=(r,g,b)=>b>r+15||g>r+12||(Math.min(r,g,b)>170&&Math.max(r,g,b)-Math.min(r,g,b)<24&&b>=r-5);
const irisColor=(r,g,b)=>Math.max(r,g,b)-Math.min(r,g,b)>24&&(b>r+8||g>r+8);
const skinColor=(r,g,b)=>r>210&&g>165&&b>145&&r>b+8&&r-g>12&&r-g<55&&g-b<34;
const inside=(x,y,points)=>{let value=false;for(let i=0,j=points.length-1;i<points.length;j=i++){const[a,b]=points[i],[c,d]=points[j];if((b>y)!==(d>y)&&x<(c-a)*(y-b)/(d-b)+a)value=!value;}return value;};
/** Restore only eye ink, never replace an oval of intact skin with a flat patch.
 * Nearby original skin samples preserve the painted lighting across a closed eye. */
function skinField(data,W,H,cx,cy,outline){
 const samples=[];
 for(let y=Math.max(0,Math.floor(cy-76));y<Math.min(H,cy+90);y+=4)
  for(let x=Math.max(0,Math.floor(cx-103));x<Math.min(W,cx+104);x+=4){
   const p=(y*W+x)*4;
   if(!inside(x,y,outline)&&data[p]>240&&data[p+1]>203&&data[p+2]>185&&skinColor(data[p],data[p+1],data[p+2]))samples.push([x,y,data[p],data[p+1],data[p+2]]);
  }
 return(x,y)=>{
  const sum=[0,0,0];let total=0;
  for(const[sx,sy,r,g,b]of samples){const w=1/((x-sx)**2+(y-sy)**2+24)**2;total+=w;sum[0]+=r*w;sum[1]+=g*w;sum[2]+=b*w;}
  return total?sum.map(v=>v/total):[255,235,224];
 };
}
/** Keep the connected fringe, not isolated grey antialias specks from an eye. */
function foregroundHair(data,ap,W,H,cx,cy,outline){
 const mask=new Uint8Array(W*H),candidate=new Set(),queue=[];
 for(let y=Math.max(0,Math.floor(cy-80));y<Math.min(H,cy+85);y++)for(let x=Math.max(0,Math.floor(cx-108));x<Math.min(W,cx+108);x++){
  const k=y*W+x,p=k*4,r=data[p],g=data[p+1],b=data[p+2];
  if(!ap.data[p+3]&&r<205&&g>r*.76&&b>g*.95){candidate.add(k);if(!inside(x,y,outline)){mask[k]=1;queue.push(k);}}
 }
 for(let i=0;i<queue.length;i++)for(const k of[queue[i]-1,queue[i]+1,queue[i]-W,queue[i]+W]){
  if(!mask[k]&&candidate.has(k)){mask[k]=1;queue.push(k);}
 }
 return mask;
}
/** Recover the hidden iris above the upper lid. A downward glance must reveal
 * its dark cap, rather than transparent texels / white holes from a cropped eye. */
function extendHiddenIris(fg,ap,W,H,cx,cy){
 for(let x=Math.max(0,Math.floor(cx-80));x<Math.min(W,cx+81);x++){
  let first=-1;
  for(let y=Math.max(0,Math.floor(cy-63));y<Math.min(H,cy+70);y++){
   const p=(y*W+x)*4;
   if(fg.data[p+3]>240){first=y;break;}
  }
  if(first<0)continue;
  const p=(first*W+x)*4;
  const cap=[fg.data[p],fg.data[p+1],fg.data[p+2]];
  if(cap[0]>120||cap[2]<cap[0]+18){cap[0]=52;cap[1]=67;cap[2]=111;}
  for(let y=Math.max(0,first-30);y<first;y++){
   const q=(y*W+x)*4;
   if(!ap.data[q+3])fg.data.set([...cap,255],q);
  }
 }
}
/** Same original illustration: separate complete iris, white, and eyelash ink.
 * The skin has no moving opaque contour; all facial layers share one head mesh. */
export function createFacialLayers(source){
 if(cache.has(source))return cache.get(source);
 const W=source.width,H=source.height,data=source.getContext('2d').getImageData(0,0,W,H).data,groups=[[],[]];
 for(let y=400;y<555;y++)for(let x=320;x<710;x++){
  const p=(y*W+x)*4;if(data[p+3]>200&&cyan(data[p],data[p+1],data[p+2]))groups[x<520?0:1].push([x,y]);
 }
 const base=makeCanvas(W,H),iris=makeCanvas(W,H),mask=makeCanvas(W,H),eye=makeCanvas(W,H),foreground=makeCanvas(W,H);
 const bc=base.getContext('2d'),ic=iris.getContext('2d'),mc=mask.getContext('2d');
 const bg=new ImageData(new Uint8ClampedArray(data),W,H),cleared=new Uint8ClampedArray(data);
 const fg=ic.createImageData(W,H),ap=mc.createImageData(W,H),detail=mc.createImageData(W,H),front=mc.createImageData(W,H),eyes=[];
 for(const points of groups){
  if(points.length<30)continue;
  const cx=points.reduce((n,p)=>n+p[0],0)/points.length,minY=Math.min(...points.map(p=>p[1])),maxY=Math.max(...points.map(p=>p[1])),cy=(minY+maxY)/2-15;
  const left=Math.max(0,Math.floor(cx-85)),right=Math.min(W-1,Math.ceil(cx+85)),rows=[];
  eyes.push([cx,cy,78,66]);
  for(let y=Math.max(0,minY-48);y<=Math.min(H-1,maxY+9);y++){
   let lo=right,hi=left;
   for(let x=left;x<=right;x++){const p=(y*W+x)*4;if(apertureColor(data[p],data[p+1],data[p+2])){lo=Math.min(lo,x);hi=Math.max(hi,x);}}
   if(hi-lo>=3)rows.push([y,lo,hi]);
  }
  for(const[y,lo,hi]of rows){
   let il=hi,ir=lo,white=[0,0,0,0];
   for(let x=lo;x<=hi;x++){
    const p=(y*W+x)*4,r=data[p],g=data[p+1],b=data[p+2];
    if(irisColor(r,g,b)){il=Math.min(il,x);ir=Math.max(ir,x);}
    else if(Math.min(r,g,b)>175&&Math.max(r,g,b)-Math.min(r,g,b)<30){white[0]+=r;white[1]+=g;white[2]+=b;white[3]++;}
   }
   for(let x=lo;x<=hi;x++)ap.data.set([255,255,255,255],(y*W+x)*4);
   if(ir<il)continue;
   for(let x=il;x<=ir;x++){
    const p=(y*W+x)*4;fg.data.set(data.subarray(p,p+4),p);
    for(let c=0;c<3;c++)cleared[p+c]=white[3]?Math.round(white[c]/white[3]):[242,244,247][c];
   }
  }
  extendHiddenIris(fg,ap,W,H,cx,cy);
  const outline=(eyes.length===1?
   [[-79,-22],[-59,-43],[-56,-48],[-46,-45],[-30,-42],[5,-41],[28,-34],[36,-17],[43,14],[32,44],[0,54],[-44,53],[-66,39],[-74,15],[-79,-2]]:
   [[-72,-16],[-51,-33],[-22,-43],[2,-47],[8,-54],[22,-43],[50,-34],[60,-17],[68,7],[57,32],[29,49],[-10,52],[-47,35],[-64,10]]).map(([x,y])=>[cx+x,cy+y+(eyes.length===1&&y<0?-4:0)]);
  const skin=skinField(data,W,H,cx,cy,outline);
  const hairMask=foregroundHair(data,ap,W,H,cx,cy,outline);
  for(let y=Math.max(1,Math.floor(cy-65));y<Math.min(H-1,cy+65);y++)for(let x=Math.max(1,Math.floor(cx-90));x<Math.min(W-1,cx+90);x++){
   const k=y*W+x,p=k*4;
   const edge=!ap.data[p+3]&&data[p]<210&&[k-1,k+1,k-W,k+W].some(q=>hairMask[q]);
   if(hairMask[k]||edge){front.data.set(data.subarray(p,p+4),p);if(!hairMask[k])front.data[p+3]=180;}
  }
  for(let y=Math.max(0,Math.floor(cy-59));y<Math.min(H,maxY+21);y++)for(let x=Math.max(0,Math.floor(cx-82));x<Math.min(W,cx+73);x++){
   if(!inside(x,y,outline))continue;
   const p=(y*W+x)*4,r=data[p],g=data[p+1],b=data[p+2];
   // Keep skin and the fringe on their original surface. Only eye ink moves.
   if(hairMask[y*W+x])continue;
   let nearEye=false;
   if(!ap.data[p+3]&&skinColor(r,g,b)){
    for(let dy=-4;dy<=4&&!nearEye;dy++)for(let dx=-4;dx<=4;dx++){
     const q=((y+dy)*W+x+dx)*4;
     if(ap.data[q+3]||(data[q]<195&&data[q]-data[q+1]>12&&inside(x+dx,y+dy,outline))){nearEye=true;break;}
    }
    if(!nearEye)continue;
   }
   const restored=skin(x,y);
   for(let c=0;c<3;c++)bg.data[p+c]=Math.round(restored[c]);
   let alpha=ap.data[p+3]?1:0;
   for(let c=0;c<3;c++){
    const target=cleared[p+c],ground=bg.data[p+c];
    alpha=Math.max(alpha,target<ground?(ground-target)/Math.max(1,ground):(target-ground)/Math.max(1,255-ground));
   }
   if(alpha<.005)continue;
   detail.data[p+3]=Math.round(alpha*255);
   for(let c=0;c<3;c++)detail.data[p+c]=clamp(Math.round((cleared[p+c]-bg.data[p+c]*(1-alpha))/alpha),0,255);
  }
 }
 bc.putImageData(bg,0,0);ic.putImageData(fg,0,0);mc.putImageData(ap,0,0);eye.getContext('2d').putImageData(detail,0,0);
 foreground.getContext('2d').putImageData(front,0,0);
 const closed=createClosedEyes(eyes,W,H);
 const result={base,iris,mask,eye,foreground,closed,eyes};cache.set(source,result);return result;
}
