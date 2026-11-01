'use strict';
const{createServer}=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const{chromium}=require('playwright'),root=path.resolve(__dirname,'..'),out=path.join(root,'artifacts');
const server=createServer((req,res)=>{
 const file=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',({'.mjs':'text/javascript','.html':'text/html','.css':'text/css','.png':'image/png'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:600,height:800}});await page.goto(`http://127.0.0.1:${server.address().port}/renderer/index.html`);await page.waitForSelector('html[data-ready="true"]');
  const report=await page.evaluate(async()=>{
   const{loadCharacter,composeCharacterFrame,drawCharacter}=await import('./faithful-character.mjs'),{createPetState,advance,setGazeTarget}=await import('./state.mjs'),{BONE,BONES}=await import('./skeleton.mjs');
   const rig=await loadCharacter();if(!rig.mesh.accelerated)throw new Error('GPU skeleton unavailable');
   const read=document.createElement('canvas');read.width=1090;read.height=1443;const rc=read.getContext('2d',{willReadFrequently:true});
   const reference=read.cloneNode(),ref=reference.getContext('2d',{willReadFrequently:true}),report={bones:BONES.length,poses:{}};
   for(const pose of['idle','megaphone','cake','tea']){
    const source=composeCharacterFrame(rig.images,{pose}),state={pose,time:0,gaze:{x:0,y:0},head:{x:0,y:0},blink:0};
    rc.clearRect(0,0,1090,1443);rc.drawImage(rig.mesh.draw(source,pose,state,{hairMotion:false}),0,0);
    const baseline=rc.getImageData(0,0,1090,1443),baseCanvas=read.cloneNode();baseCanvas.getContext('2d').putImageData(baseline,0,0);report.poses[pose]=[];
    for(const head of[{x:1,y:1},{x:-1,y:-1},{x:0,y:1}]){
     rc.clearRect(0,0,1090,1443);rc.drawImage(rig.mesh.draw(source,pose,{...state,head},{hairMotion:false}),0,0);const drawn=rc.getImageData(0,0,1090,1443).data;
     const m=rig.mesh.skeleton.matrices[BONE.head];ref.setTransform(1,0,0,1,0,0);ref.clearRect(0,0,1090,1443);ref.transform(...m);ref.drawImage(baseCanvas,0,0);const expected=ref.getImageData(0,0,1090,1443).data;
     let bodyError=0,faceError=0,bn=0,fn=0;
     for(const[x0,y0,x1,y1]of[[450,675,600,825],[425,690,465,735],[600,690,635,735],[485,640,560,675]])
      for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++){const p=(y*1090+x)*4;for(let c=0;c<3;c++){bodyError+=Math.abs(drawn[p+c]-baseline.data[p+c]);bn++;}}
     for(let y=415;y<575;y++)for(let x=345;x<710;x++){const p=(y*1090+x)*4;for(let c=0;c<3;c++){faceError+=Math.abs(drawn[p+c]-expected[p+c]);fn++;}}
     report.poses[pose].push({head,bodyError:bodyError/bn,rigidHeadError:faceError/fn});
    }
   }
   const state=createPetState(),normal=document.createElement('canvas'),debug=document.createElement('canvas'),canvas=document.createElement('canvas');normal.width=debug.width=600;normal.height=debug.height=800;canvas.width=1200;canvas.height=800;
   const ctx=canvas.getContext('2d'),nc=normal.getContext('2d'),dc=debug.getContext('2d'),settings={hairMotion:true,eyeTracking:true,headTracking:true,motionBlur:false},chunks=[];
   const recorder=new MediaRecorder(canvas.captureStream(60),{mimeType:'video/webm;codecs=vp9',videoBitsPerSecond:4500000});recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};const done=new Promise(r=>recorder.onstop=r);recorder.start();
   let start,last,frames=0,stills={};
   await new Promise(resolve=>{function tick(now){start??=now;last??=now;const t=(now-start)/1000,dt=(now-last)/1000;last=now;
    state.pose=t<6?'idle':t<8?'megaphone':t<10?'cake':'tea';
    const down=t>=2&&t<4,gx=down?0:Math.sin(t*1.2),gy=down?1:Math.sin(t*.7);setGazeTarget(state,gx,gy);advance(state,dt,settings);
    drawCharacter(nc,rig,state,settings);drawCharacter(dc,rig,state,{...settings,skeletonPreview:true});ctx.fillStyle='#edf3ef';ctx.fillRect(0,0,1200,800);ctx.drawImage(normal,0,0);ctx.drawImage(debug,600,0);
    ctx.fillStyle='#22584d';ctx.font='18px "Microsoft YaHei",sans-serif';ctx.fillText('阮梅 · 骨骼动作',24,30);ctx.fillText('关节预览（可关闭）',624,30);
    const px=300+gx*180,py=310+gy*380;ctx.beginPath();ctx.arc(px,py,5,0,Math.PI*2);ctx.fill();ctx.font='13px "Microsoft YaHei",sans-serif';ctx.fillText(down?'指针在下方':'指针方向',px+10,py+4);frames++;
    if(t>1.5&&!stills.right)stills.right=canvas.toDataURL();if(t>4.5&&!stills.left)stills.left=canvas.toDataURL();
    if(t<12)requestAnimationFrame(tick);else resolve();}requestAnimationFrame(tick);});
   recorder.stop();await done;const bytes=new Uint8Array(await new Blob(chunks).arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
   return{...report,frames,video:btoa(binary),stills};
  });
  fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'meimei-skeleton.webm'),Buffer.from(report.video,'base64'));delete report.video;
  for(const[name,data]of Object.entries(report.stills))fs.writeFileSync(path.join(out,'skeleton-'+name+'.png'),Buffer.from(data.split(',')[1],'base64'));delete report.stills;
  fs.writeFileSync(path.join(out,'meimei-skeleton-check.json'),JSON.stringify(report,null,2));
  for(const[pose,frames]of Object.entries(report.poses))for(const frame of frames){assert.ok(frame.bodyError<.1,`${pose}: shoulder/chest must stay fixed (${frame.bodyError})`);assert.ok(frame.rigidHeadError<2.5,`${pose}: head must match a rigid rotation (${frame.rigidHeadError})`);}
  console.log(JSON.stringify(report));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
