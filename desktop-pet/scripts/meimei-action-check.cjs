'use strict';
const {createServer}=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright'),root=path.resolve(__dirname,'..'),out=path.join(root,'artifacts');
const server=createServer((req,res)=>{const pathname=new URL(req.url,'http://localhost').pathname;if(pathname==='/review.html'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><body style="margin:0;background:#edf3ef"></body>');return;}
 const file=path.resolve(root,'.'+pathname);if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',({'.mjs':'text/javascript','.png':'image/png'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1200,height:1600}});await page.goto(`http://127.0.0.1:${server.address().port}/review.html`);
 const report=await page.evaluate(async(record)=>{
  const{loadCharacter,warmCharacterPoses,drawCharacter,RIG}=await import('/renderer/faithful-character.mjs'),{puppetFrame,pickPuppet}=await import('/renderer/puppet-art.mjs');
  const{createPetState,applyAction,advance}=await import('/renderer/state.mjs'),{actionScene}=await import('/renderer/action-motion.mjs');
  const{createCharacterHitRegion}=await import('/renderer/hit-region.mjs');
  const rig=await loadCharacter(),settings={hairMotion:true,motionBlur:true,actionSpeed:1,poseTransition:true},c=document.createElement('canvas');c.width=600;c.height=800;const ctx=c.getContext('2d',{willReadFrequently:true});await warmCharacterPoses(rig,settings);
  const sheet=document.createElement('canvas');sheet.width=1200;sheet.height=1800;const sc=sheet.getContext('2d');sc.fillStyle='#edf3ef';sc.fillRect(0,0,1200,1800);
  const cases=[['idle',2],['cake',0],['cake',4.25],['tea',0],['tea',4.2]],frames=[];
  for(const[i,[pose,time]]of cases.entries()){
   const s={...createPetState(),pose,time,actionTime:time};drawCharacter(ctx,rig,s,{...settings,motionBlur:false});sc.drawImage(c,i%3*400,Math.floor(i/3)*600,400,533);sc.fillStyle='#22584d';sc.font='18px sans-serif';sc.fillText(pose+' '+time+'s',i%3*400+15,Math.floor(i/3)*600+560);
   const frame=rig.actionFrame;frames.push({pose,time,scene:frame.scene,left:frame.left,right:frame.right,mouth:frame.mouth});
  }
  const s=createPetState();applyAction(s,{type:'pose',id:'cake'});s.time=s.actionTime=1.12;drawCharacter(ctx,rig,s,{...settings,motionBlur:false});sc.drawImage(c,0,1200,400,533);
  const report={frames,coverage:[],transitions:[],sheet:sheet.toDataURL()};
  for(const pose of['idle','cake','tea'])for(const time of[0,1,2.8,4.2,5.8,9]){
   const s={...createPetState(),pose,time,actionTime:time};drawCharacter(ctx,rig,s,settings);
   const region=createCharacterHitRegion(rig,s,settings),mask=new Uint8Array(600*800);for(const r of region.rects)for(let y=Math.max(0,r.y);y<Math.min(800,r.y+r.height);y++)mask.fill(1,y*600+Math.max(0,r.x),y*600+Math.min(600,r.x+r.width));
   const pixels=ctx.getImageData(0,0,600,800).data;let missing=0;for(let y=0;y<800;y+=2)for(let x=0;x<600;x+=2)if(pixels[(y*600+x)*4+3]>32&&!mask[y*600+x])missing++;report.coverage.push({pose,time,missing,rectangles:region.rects.length});
  }
  for(const from of['idle','cake','tea'])for(const to of['idle','cake','tea']){
   if(from===to)continue;const state={...createPetState(),pose:from,time:4.2,actionTime:4.2,motionTime:0},still={...settings,hairMotion:true,motionBlur:false};
   drawCharacter(ctx,rig,state,still);const before=ctx.getImageData(0,0,600,800).data;applyAction(state,{type:'pose',id:to},still);drawCharacter(ctx,rig,state,still);const after=ctx.getImageData(0,0,600,800).data;
   let firstFrameError=0;for(let i=0;i<before.length;i++)firstFrameError+=Math.abs(before[i]-after[i]);report.transitions.push({from,to,firstFrameError});
   for(const t of[.3,.65,1.1,1.7,2.2]){
    const current={...state,actionTime:4.2+t,time:4.2+t};drawCharacter(ctx,rig,current,settings);const region=createCharacterHitRegion(rig,current,settings),pixels=ctx.getImageData(0,0,600,800).data;
    const mask=new Uint8Array(600*800);for(const r of region.rects)for(let y=Math.max(0,r.y);y<Math.min(800,r.y+r.height);y++)mask.fill(1,y*600+Math.max(0,r.x),y*600+Math.min(600,r.x+r.width));
    let missing=0;for(let y=0;y<800;y+=3)for(let x=0;x<600;x+=3)if(pixels[(y*600+x)*4+3]>32&&!mask[y*600+x])missing++;report.coverage.push({from,pose:to,time:t,missing,rectangles:region.rects.length});
   }
  }
  if(record){
   const chunks=[],output=document.createElement('canvas');output.width=600;output.height=800;document.body.append(output);const oc=output.getContext('2d');
   const recorder=new MediaRecorder(output.captureStream(30),{mimeType:'video/webm;codecs=vp9',videoBitsPerSecond:3500000});recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};const done=new Promise(r=>recorder.onstop=r);recorder.start();
   const state=createPetState(),timeline=[[3,'cake'],[17,'tea'],[31,'idle']];let started,last,next=0,frames=0;
   await new Promise(resolve=>{function tick(now){started??=now;last??=now;const t=(now-started)/1000,dt=(now-last)/1000;last=now;
    if(next<timeline.length&&t>=timeline[next][0])applyAction(state,{type:'pose',id:timeline[next++][1]},settings);advance(state,dt,settings);drawCharacter(ctx,rig,state,settings);oc.fillStyle='#edf3ef';oc.fillRect(0,0,600,800);oc.drawImage(c,0,0);oc.font='17px Microsoft YaHei';oc.fillStyle='#22584d';oc.fillText('阮梅 · '+({idle:'日常待机',cake:'拿点心 / 进食',tea:'变出杯子 / 喝茶'}[state.pose]),16,28);frames++;if(t<35)requestAnimationFrame(tick);else resolve();}requestAnimationFrame(tick);});recorder.stop();await done;
   const bytes=new Uint8Array(await new Blob(chunks).arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));report.video=btoa(binary);report.videoFrames=frames;
  }return report;
 },process.argv.includes('--record'));
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'meimei-action-sheet.png'),Buffer.from(report.sheet.split(',')[1],'base64'));delete report.sheet;
 if(report.video){fs.writeFileSync(path.join(out,'meimei-actions.webm'),Buffer.from(report.video,'base64'));delete report.video;}
 fs.writeFileSync(path.join(out,'meimei-action-check.json'),JSON.stringify(report,null,2));
 for(const r of report.coverage)assert.equal(r.missing,0,`native shape clips ${r.pose}@${r.time}: ${r.missing}`);
 for(const r of report.transitions)assert.equal(r.firstFrameError,0,`action selection jumps at ${r.from} to ${r.to}`);
 console.log(JSON.stringify({coverageSamples:report.coverage.length,missing:report.coverage.reduce((n,v)=>n+v.missing,0),transitions:report.transitions,videoFrames:report.videoFrames}));
 }finally{await browser.close();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
