'use strict';
const {createServer}=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright'),root=path.resolve(__dirname,'..'),out=path.join(root,'artifacts');
const server=createServer((req,res)=>{const url=new URL(req.url,'http://localhost');if(url.pathname==='/review.html'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><body></body>');return;}const file=path.resolve(root,'.'+url.pathname);if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}try{res.setHeader('Content-Type',({'.mjs':'text/javascript','.png':'image/png'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage();await page.goto(`http://127.0.0.1:${server.address().port}/review.html`);
 const report=await page.evaluate(async()=>{
  const {loadCharacter,drawCharacter}=await import('/renderer/faithful-character.mjs'),{createPetState,applyAction}=await import('/renderer/state.mjs'),{forkTip,attachment,CUP_GRIP,CUP_RIM,CUP_BASE}=await import('/renderer/daily-actions.mjs'),{actionScene}=await import('/renderer/action-motion.mjs'),{BONE,transform}=await import('/renderer/skeleton.mjs');
  const {drawPuppet}=await import('/renderer/puppet-art.mjs');
  const {HAND_GRASPS,insideContour}=await import('/renderer/grasp-binding.mjs');
  const rig=await loadCharacter(),c=Object.assign(document.createElement('canvas'),{width:1200,height:1600}),ctx=c.getContext('2d');ctx.scale(2,2);
  const sheet=Object.assign(document.createElement('canvas'),{width:1600,height:2400}),sc=sheet.getContext('2d');sc.fillStyle='#edf3ef';sc.fillRect(0,0,1600,2400);const checks=[];
  const close=Object.assign(document.createElement('canvas'),{width:1200,height:1100}),cc=close.getContext('2d'),closeCases=[['cake-enter',1.5],['cake',0],['cake',2.45],['tea',0]];cc.fillStyle='#edf3ef';cc.fillRect(0,0,1200,1100);
  const grasp=Object.assign(document.createElement('canvas'),{width:1200,height:550}),gc=grasp.getContext('2d');gc.fillStyle='#edf3ef';gc.fillRect(0,0,1200,550);
  const cupReview=Object.assign(document.createElement('canvas'),{width:1200,height:830}),cr=cupReview.getContext('2d');cr.fillStyle='#edf3ef';cr.fillRect(0,0,1200,830);
  const mapped=(m,p)=>[m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]],distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
  const canvasFor=layers=>{const c=Object.assign(document.createElement('canvas'),{width:1090,height:1443}),cx=c.getContext('2d');for(const l of layers){cx.save();cx.transform(...l.m);cx.globalAlpha=l.opacity;cx.drawImage(rig.puppet[l.name].image,0,0);cx.restore();}return c;};
  const cases=[['idle',2],['cake',0],['cake',1.6],['cake',2.05],['cake',2.45],['cake',2.85],['cake',3.6],['cake',4.2],['cake',5.1],['tea',0],['tea',4.2],['cake-enter',.7],['cake-enter',1.5],['cake-exit',.65],['tea-exit',.7],['cake',1.4],['cake',5.9],['cake-exit',.73],['tea',2.8]];
  for(const [index,[pose,time]] of cases.entries()){
   const s={...createPetState(),pose:pose.split('-')[0],time,actionTime:time,motionTime:0};
   if(pose==='cake-enter'){s.pose='idle';s.time=s.actionTime=0;applyAction(s,{type:'pose',id:'cake'});s.time=s.actionTime=time;}
   if(pose.endsWith('-exit')){s.time=s.actionTime=4.2;applyAction(s,{type:'pose',id:'idle'});s.time=s.actionTime=4.2+time;}
   drawCharacter(ctx,rig,s,{motionBlur:false,hairMotion:true});sc.drawImage(c,index%4*400,Math.floor(index/4)*480,400,450);sc.fillStyle='#22584d';sc.font='17px sans-serif';sc.fillText(`${pose} / ${time}s`,index%4*400+12,Math.floor(index/4)*480+472);
   const ci=closeCases.findIndex(([p,t])=>p===pose&&t===time);if(ci>=0){cc.drawImage(c,2*(38+280*.48),2*(68+630*.48),500*.96,410*.96,ci%2*600,Math.floor(ci/2)*550,600,492);cc.fillStyle='#22584d';cc.font='20px sans-serif';cc.fillText(`${pose} / ${time}s`,ci%2*600+15,Math.floor(ci/2)*550+530);}
   const gi=pose==='cake'&&time===2.45?0:pose==='tea'&&time===0?1:-1;if(gi>=0){gc.drawImage(c,2*(38+280*.48),2*(68+630*.48),500*.96,410*.96,gi*600,0,600,492);gc.fillStyle='#22584d';gc.font='20px Microsoft YaHei';gc.fillText(gi===0?'取点心：指间握柄':'持杯：手指扣住杯柄',gi*600+15,530);}
   if(pose==='tea'&&(time===0||time===4.2)){const i=time===0?0:1;cr.drawImage(c,2*(38+280*.48),2*(68+420*.48),500*.96,640*.96,i*600,0,600,768);cr.fillStyle='#22584d';cr.font='20px Microsoft YaHei';cr.fillText(i===0?'端杯：一手握柄，一手托底':'喝咖啡：两手随杯子一起抬起',i*600+15,805);}
   const frame=rig.actionFrame,check={pose,time,phase:frame.scene.phase};
   for(const name of['hand-fork','hand-cup'])if(frame.layers.some(l=>l.name===name&&l.opacity>.99)){const p=rig.puppet[name];check.gripGapAlpha=p.data[(Math.round(p.b[1])*p.image.width+Math.round(p.b[0]))*4+3];}
   const hands=frame.layers.filter(l=>l.part==='hand'),joints=canvasFor(hands),jc=joints.getContext('2d');jc.globalCompositeOperation='destination-over';jc.drawImage(rig.puppet.armRenderer.draw(frame.surfaces),0,0,1090,1443);const jp=jc.getImageData(0,0,1090,1443).data;
   check.wristAnchorError=0;check.gripAnchorError=0;check.minWristAlpha=255;check.minHandDeterminant=Infinity;
   for(const l of hands){const arm=l.group.startsWith('L')?frame.left:frame.right,p=rig.puppet[l.name];check.wristAnchorError=Math.max(check.wristAnchorError,distance(mapped(l.m,p.a),arm.wrist));check.gripAnchorError=Math.max(check.gripAnchorError,distance(mapped(l.m,p.b),arm.grip));check.minHandDeterminant=Math.min(check.minHandDeterminant,l.m[0]*l.m[3]-l.m[1]*l.m[2]);}
   for(const arm of[frame.left,frame.right])for(const t of[-.08,0,.08]){const x=Math.round(arm.wrist[0]+(arm.grip[0]-arm.wrist[0])*t),y=Math.round(arm.wrist[1]+(arm.grip[1]-arm.wrist[1])*t);check.minWristAlpha=Math.min(check.minWristAlpha,jp[(y*1090+x)*4+3]);}
   if(frame.scene.prop?.kind==='cake'&&frame.scene.prop.opacity>.05){const chest=frame.skeleton.matrices[BONE.chest];check.supportPalmTilt=Math.abs(Math.atan2(frame.left.grip[1]-frame.left.wrist[1],frame.left.grip[0]-frame.left.wrist[0])-Math.atan2(chest[1],chest[0]))*180/Math.PI;}
   if(frame.scene.fork){const l=frame.layers.find(l=>l.name==='forkProp');if(l)check.actualForkTipError=distance(mapped(l.m,rig.puppet.forkProp.tip),forkTip(frame.scene.fork));}
   const forkLayer=frame.layers.find(l=>l.name==='forkProp'),forkHand=frame.layers.find(l=>l.name==='hand-fork'&&l.opacity>.99);
   if(forkLayer?.opacity>.99&&forkHand){
    const fp=rig.puppet.forkProp,fy=Math.round(fp.pivot[1]),fx=Math.round(fp.pivot[0]);let lo=fx,hi=fx;
    while(lo>0&&fp.data[(fy*fp.image.width+lo-1)*4+3]>128)lo--;while(hi<fp.image.width-1&&fp.data[(fy*fp.image.width+hi+1)*4+3]>128)hi++;check.shaftWidthAtGrip=hi-lo+1;
    const isolated=Object.assign(document.createElement('canvas'),{width:1090,height:1443}),ic=isolated.getContext('2d');drawPuppet(ic,rig.puppet,{...frame,surfaces:[],layers:[forkHand,forkLayer],scene:{...frame.scene,prop:null,bite:null,materialize:0}});
    const metal=canvasFor([forkLayer]).getContext('2d').getImageData(0,0,1090,1443).data,hand=canvasFor([forkHand]).getContext('2d').getImageData(0,0,1090,1443).data,final=ic.getImageData(0,0,1090,1443).data;let pixels=0,error=0,thumbPixels=0,thumbError=0;
    const [a,b,c,d,e,f]=forkHand.m,det=a*d-b*c;
    const frontWorld=HAND_GRASPS.fork.front.map(poly=>poly.map(p=>mapped(forkHand.m,p)));
    const edgeDistance=p=>Math.min(...frontWorld.flatMap(poly=>poly.map((a,j)=>{const b=poly[(j+1)%poly.length],dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)));return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);})));
    for(let y=Math.round(frame.right.grip[1])-10;y<=Math.round(frame.right.grip[1])+10;y++)for(let x=Math.round(frame.right.grip[0])-10;x<=Math.round(frame.right.grip[0])+10;x++){
     const i=(y*1090+x)*4,sx=(d*(x+.5-e)-c*(y+.5-f))/det,sy=(-b*(x+.5-e)+a*(y+.5-f))/det;
     if(metal[i+3]>=245&&hand[i+3]>=200&&insideContour([sx,sy],HAND_GRASPS.fork.farGrip)&&!HAND_GRASPS.fork.front.some(poly=>insideContour([sx,sy],poly))&&edgeDistance([x+.5,y+.5])>.9){thumbPixels++;const ma=metal[i+3]/255,ha=hand[i+3]/255,alpha=ma+ha*(1-ma);for(let k=0;k<3;k++){const expected=(metal[i+k]*ma+hand[i+k]*ha*(1-ma))/alpha;thumbError=Math.max(thumbError,Math.abs(final[i+k]-expected));}}
    }
    for(let y=Math.round(frame.right.grip[1])-5;y<=Math.round(frame.right.grip[1])+5;y++)for(let x=Math.round(frame.right.grip[0])-5;x<=Math.round(frame.right.grip[0])+5;x++){const i=(y*1090+x)*4;if(metal[i+3]>=245&&hand[i+3]<=1){pixels++;for(let k=0;k<3;k++)error=Math.max(error,Math.abs(final[i+k]-metal[i+k]));}}
    check.exposedShaftPixelsInGrip=pixels;check.exposedShaftColorError=error;check.farGripBehindShaftPixels=thumbPixels;check.farGripBehindShaftError=thumbError;
   }
   if(frame.scene.prop?.kind==='cup'){
    const l=frame.layers.find(l=>l.name==='cupProp');if(l){const actual=mapped(l.m,[301-70,1240-1160]);check.actualHandleGripError=distance(actual,frame.right.grip.slice(0,2));const p=rig.puppet.cupProp;check.cupHandleHoleAlpha=p.data[((1240-1160)*p.image.width+301-70)*4+3];}
    check.supportHandKind=frame.scene.leftKind;const support=frame.layers.find(l=>l.name==='hand-support'&&l.group?.startsWith('L'));
    const palm=rig.puppet['hand-support'],px=Math.round(palm.contact[0]),py=Math.round(palm.contact[1]),cup=rig.puppet.cupProp,bx=179-70,by=1369-1160;
    check.palmSurfaceAlpha=palm.data[(py*palm.image.width+px)*4+3];check.abovePalmAlpha=palm.data[((py-2)*palm.image.width+px)*4+3];check.cupBaseAlpha=cup.data[(by*cup.image.width+bx)*4+3];check.belowCupBaseAlpha=cup.data[((by+2)*cup.image.width+bx)*4+3];
    if(support&&frame.scene.cupSupport>.999)check.actualSupportContactError=distance(mapped(support.m,rig.puppet['hand-support'].contact),attachment(frame.scene.prop,CUP_BASE.map(v=>v*(frame.scene.prop.scale||1))));
   }
   if(frame.scene.prop?.kind==='cake'&&frame.scene.prop.opacity>.99){
    const plate=canvasFor(frame.layers.filter(l=>l.name==='cake')).getContext('2d').getImageData(0,0,1090,1443).data,bite=canvasFor(frame.layers.filter(l=>l.name==='bite')).getContext('2d').getImageData(0,0,1090,1443).data,final=rig.sampleLayer.getContext('2d').getImageData(0,0,1090,1443).data;let pixels=0,error=0;
    for(let i=0;i<plate.length;i+=4)if(plate[i+3]>=254&&bite[i+3]<=1){pixels++;for(let k=0;k<3;k++)error=Math.max(error,Math.abs(final[i+k]-plate[i+k]));}
    check.trayOpaquePixels=pixels;check.visibleHandOrForkThroughTrayError=error;
   }checks.push(check);
  }
  const tracking=[];
  for(const pose of['cake','tea'])for(const x of[-1,0,1])for(const y of[-1,0,1]){
   const s={...createPetState(),pose,time:4.2,actionTime:4.2,motionTime:0,head:{x,y},gaze:{x,y}};drawCharacter(ctx,rig,s,{motionBlur:false,hairMotion:true});const f=rig.actionFrame;
   const contact=pose==='tea'?attachment(f.scene.prop,CUP_RIM):pose==='cake'?forkTip(f.scene.fork):f.right.grip.slice(0,2),target=f.mouth,check={pose,x,y,mouthError:distance(contact,target),gripReachError:f.right.reachError};
   if(pose==='tea'){const support=f.layers.find(l=>l.name==='hand-support'&&l.group?.startsWith('L'));check.supportContactError=distance(mapped(support.m,rig.puppet['hand-support'].contact),attachment(f.scene.prop,CUP_BASE));check.supportReachError=f.left.reachError;}tracking.push(check);
  }
  return{checks,tracking,sheet:sheet.toDataURL(),close:close.toDataURL(),grasp:grasp.toDataURL(),cupReview:cupReview.toDataURL()};
 });
 fs.mkdirSync(out,{recursive:true});
 for(const[key,name]of[['sheet','meimei-human-actions.png'],['close','meimei-palm-closeups.png'],['grasp','meimei-grasp-closeups.png'],['cupReview','meimei-cup-support-closeups.png']]){fs.writeFileSync(path.join(out,name),Buffer.from(report[key].split(',')[1],'base64'));delete report[key];}
 fs.writeFileSync(path.join(out,'meimei-human-actions.json'),JSON.stringify(report,null,2));
 for(const r of report.checks){if(r.gripGapAlpha!=null)assert.ok(r.gripGapAlpha<=16,JSON.stringify(r));assert.ok(r.wristAnchorError<.001&&r.gripAnchorError<.001,JSON.stringify(r));assert.ok(r.minWristAlpha>=200,JSON.stringify(r));assert.ok(r.minHandDeterminant>0,JSON.stringify(r));if(r.supportPalmTilt!=null)assert.ok(r.supportPalmTilt<5,JSON.stringify(r));if(r.actualForkTipError!=null)assert.ok(r.actualForkTipError<.01,JSON.stringify(r));if(r.actualHandleGripError!=null)assert.ok(r.actualHandleGripError<1,JSON.stringify(r));if(r.trayOpaquePixels){assert.ok(r.trayOpaquePixels>1000);assert.ok(r.visibleHandOrForkThroughTrayError<=3,JSON.stringify(r));}}
 for(const r of report.tracking){assert.ok(r.mouthError<.01,JSON.stringify(r));assert.ok(r.gripReachError<.01,JSON.stringify(r));}
 for(const r of report.checks){if(r.supportHandKind){assert.equal(r.supportHandKind,'support');assert.ok(r.palmSurfaceAlpha>=180&&r.abovePalmAlpha<128&&r.cupBaseAlpha>=180&&r.belowCupBaseAlpha<128,JSON.stringify(r));}if(r.actualSupportContactError!=null)assert.ok(r.actualSupportContactError<.02,JSON.stringify(r));}
 for(const r of report.tracking){if(r.supportContactError!=null)assert.ok(r.supportContactError<.02&&r.supportReachError<.01,JSON.stringify(r));}
 for(const r of report.checks){if(r.shaftWidthAtGrip!=null){assert.ok(r.shaftWidthAtGrip>=5&&r.shaftWidthAtGrip<=25,JSON.stringify(r));assert.ok(r.exposedShaftColorError<=4,JSON.stringify(r));assert.ok(r.farGripBehindShaftError<=4,JSON.stringify(r));}if(r.cupHandleHoleAlpha!=null)assert.ok(r.cupHandleHoleAlpha<=16,JSON.stringify(r));}
 assert.ok(report.checks.reduce((n,r)=>n+(r.farGripBehindShaftPixels||0),0)>=2,'The render must exercise shaft-in-front-of-far-side grip details, rather than testing landmarks only');
 console.log(JSON.stringify({poses:report.checks.length,headDirections:report.tracking.length,maxTrayError:Math.max(...report.checks.map(c=>c.visibleHandOrForkThroughTrayError||0)),maxMouthError:Math.max(...report.tracking.map(c=>c.mouthError))}));
 }finally{await browser.close();server.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
