'use strict';
const {createServer}=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'artifacts');
const server=createServer((req,res)=>{
 const file=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);
 if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',({'.mjs':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json','.png':'image/png'})[path.extname(file)]||'text/plain');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:600,height:800}});await page.goto(`http://127.0.0.1:${server.address().port}/renderer/index.html`);await page.waitForSelector('html[data-ready="true"]');
  const result=await page.evaluate(async()=>{
   const {loadCharacter,drawCharacter}=await import('./faithful-character.mjs'),{createPetState,advance,setGazeTarget}=await import('./state.mjs');
   const rig=await loadCharacter(),state=createPetState(),canvas=document.createElement('canvas'),character=document.createElement('canvas');
   canvas.width=character.width=600;canvas.height=character.height=800;
   const ctx=canvas.getContext('2d'),cc=character.getContext('2d'),chunks=[],settings={hairMotion:true,eyeTracking:true,motionBlur:true,motionBlurStrength:.6};
   const recorder=new MediaRecorder(canvas.captureStream(60),{mimeType:'video/webm;codecs=vp9',videoBitsPerSecond:3500000});
   recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};const done=new Promise(resolve=>recorder.onstop=resolve);recorder.start();
   let start,last,frames=0;const blinkFrames=[];
   await new Promise(resolve=>{
    function tick(now){
     start??=now;last??=now;const time=(now-start)/1000,dt=(now-last)/1000;last=now;
     state.pose=['idle','megaphone','cake','tea'][Math.min(3,Math.floor(time/3))];
     state.expression=time>8?null:time>6?'smile':time>4?'angry':null;
     setGazeTarget(state,Math.sin(time*2),Math.sin(time*.7)*.5);advance(state,dt,settings);drawCharacter(cc,rig,state,settings);
     ctx.fillStyle='#edf3ef';ctx.fillRect(0,0,600,800);ctx.drawImage(character,0,0);frames++;
     if(state.blink>0)blinkFrames.push(state.blink);
     if(time<12)requestAnimationFrame(tick);else resolve();
    }requestAnimationFrame(tick);
   });
   recorder.stop();await done;
   if(!blinkFrames.some(x=>x>.99)||blinkFrames.filter(x=>x>0&&x<.99).length<10)throw new Error('Incomplete blink cycle');
   const bytes=new Uint8Array(await new Blob(chunks,{type:'video/webm'}).arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
   return{data:btoa(binary),frames,blinkFrames:blinkFrames.length};
  });
  fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'meimei-animation.webm'),Buffer.from(result.data,'base64'));delete result.data;console.log(JSON.stringify(result));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
