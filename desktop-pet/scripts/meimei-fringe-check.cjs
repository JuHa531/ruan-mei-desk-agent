/** Pixel ownership check: eyelid animation must never move original fringe pixels. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createServer}=require('node:http'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'artifacts');
const server=createServer((req,res)=>{
 const file=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);
 if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',({'.mjs':'text/javascript','.html':'text/html','.css':'text/css','.png':'image/png'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage();await page.goto(`http://127.0.0.1:${server.address().port}/renderer/index.html`);await page.waitForSelector('html[data-ready="true"]');
  const report=await page.evaluate(async()=>{
   const{loadCharacter,composeCharacterFrame}=await import('./faithful-character.mjs');
   const{createFacialLayers,facialTarget}=await import('./facial-rig.mjs');
   const rig=await loadCharacter(),source=composeCharacterFrame(rig.images,{pose:'idle'}),layers=createFacialLayers(source),W=1090,H=1443;
   const raw=source.getContext('2d').getImageData(0,0,W,H).data,base=layers.base.getContext('2d').getImageData(0,0,W,H).data;
   const detail=layers.eye.getContext('2d').getImageData(0,0,W,H).data,front=layers.foreground.getContext('2d').getImageData(0,0,W,H).data;
   const read=Object.assign(document.createElement('canvas'),{width:W,height:H}),rc=read.getContext('2d',{willReadFrequently:true});
   const sheet=Object.assign(document.createElement('canvas'),{width:1100,height:1350}),ctx=sheet.getContext('2d');ctx.fillStyle='#eaf3ee';ctx.fillRect(0,0,sheet.width,sheet.height);
   const cases=[['original',0,null],['open',0,null],['half',.5,null],['near',.85,null],['closed',1,null],['wink',0,'wink'],['sleep',0,'sleep'],['angry',0,'angry']];
   const checks=[],hair=[],candidates=new Set(),connected=new Set(),queue=[];
   // Source-colour core plus its immediate warm antialias rim. No generated matte is trusted here.
   for(let y=390;y<590;y++)for(let x=290;x<755;x++){
    const p=(y*W+x)*4,[r,g,b,a]=raw.subarray(p,p+4);
    if(a<250||r>180||g<r*.74||b<g*.88||b>r+15||g>r+12)continue;
    const k=y*W+x;candidates.add(k);
    if(y===390||x===290||x===754){queue.push(k);connected.add(k);}
   }
   for(let i=0;i<queue.length;i++)for(const d of[-W-1,-W,-W+1,-1,1,W-1,W,W+1]){
    const k=queue[i]+d;if(candidates.has(k)&&!connected.has(k)){connected.add(k);queue.push(k);}
   }
   for(const k of connected){const x=k%W,y=Math.floor(k/W);if(layers.eyes.some(([cx,cy])=>Math.abs(x-cx)<98&&Math.abs(y-cy)<76))hair.push([x,y]);}
   let featureHairPixels=0,baseHairChanges=0;const badHairSamples=[];
   for(const[x,y]of hair){const p=(y*W+x)*4;if(detail[p+3]>4){featureHairPixels++;if(badHairSamples.length<20)badHairSamples.push({x,y,source:[...raw.slice(p,p+4)],base:[...base.slice(p,p+4)],front:[...front.slice(p,p+4)]});}if([0,1,2].some(c=>Math.abs(base[p+c]-raw[p+c])>2))baseHairChanges++;}
   for(const[i,[name,blink,expression]]of cases.entries()){
    const image=name==='original'?source:rig.mesh.draw(source,'fringe-review',{pose:'idle',expression,facial:facialTarget(expression),time:0,blink,gaze:{x:0,y:0},head:{x:0,y:0}},{hairMotion:false,headTracking:false});
    rc.clearRect(0,0,W,H);rc.drawImage(image,0,0);const pixels=rc.getImageData(0,0,W,H).data;
    let changed=0,maxError=0,total=0;
    for(const[x,y]of hair){const p=(y*W+x)*4,e=Math.max(...[0,1,2].map(c=>Math.abs(pixels[p+c]-raw[p+c])));maxError=Math.max(maxError,e);total+=e;if(e>3)changed++;}
    checks.push({name,changed,maxError,meanError:total/hair.length});
    const x=i%2*550,y=Math.floor(i/2)*330;ctx.fillStyle='#214b43';ctx.font='18px sans-serif';ctx.fillText(name,x+8,y+23);ctx.drawImage(read,285,335,485,270,x+8,y+30,534,297);
   }
   const debug={};for(const name of['base','eye','foreground']){
    const c=Object.assign(document.createElement('canvas'),{width:1000,height:600});
    c.getContext('2d').drawImage(layers[name],280,320,500,300,0,0,1000,600);debug[name]=c.toDataURL();
   }
   const grid=Object.assign(document.createElement('canvas'),{width:1200,height:720}),gc=grid.getContext('2d');
   gc.drawImage(source,280,350,500,300,0,0,1200,720);gc.font='11px sans-serif';
   for(let x=280;x<=780;x+=20){gc.strokeStyle='#09f5';gc.beginPath();gc.moveTo((x-280)*2.4,0);gc.lineTo((x-280)*2.4,720);gc.stroke();gc.fillStyle='#03b';gc.fillText(x,(x-280)*2.4,12);}
   for(let y=350;y<=650;y+=20){gc.strokeStyle='#09f5';gc.beginPath();gc.moveTo(0,(y-350)*2.4);gc.lineTo(1200,(y-350)*2.4);gc.stroke();gc.fillStyle='#03b';gc.fillText(y,0,(y-350)*2.4);}
   debug.grid=grid.toDataURL();
   const{BONE,transform}=await import('./skeleton.mjs');const tracking=[];
   for(const head of[{x:-1,y:1},{x:1,y:1},{x:-1,y:-1},{x:1,y:-1}]){
    const draw=blink=>{rc.clearRect(0,0,W,H);rc.drawImage(rig.mesh.draw(source,'fringe-review',{pose:'idle',facial:facialTarget(null),time:0,blink,gaze:head,head},{hairMotion:false,headTracking:true}),0,0);return rc.getImageData(0,0,W,H).data;};
    const open=draw(0),matrix=rig.mesh.skeleton.matrices[BONE.head];
    for(const blink of[.5,1]){
     const image=draw(blink);let maxError=0,changed=0;
     for(const[x,y]of hair){const q=transform(matrix,x,y),p=(Math.round(q[1])*W+Math.round(q[0]))*4;if(p<0||p>=image.length)continue;const e=Math.max(...[0,1,2].map(c=>Math.abs(image[p+c]-open[p+c])));maxError=Math.max(maxError,e);if(e>3)changed++;}
     tracking.push({head,blink,changed,maxError});
    }
   }
   return{eyes:layers.eyes,hairPixels:hair.length,featureHairPixels,baseHairChanges,badHairSamples,checks,tracking,debug,sheet:sheet.toDataURL()};
  });
  fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'meimei-fringe-review.png'),Buffer.from(report.sheet.split(',')[1],'base64'));delete report.sheet;
  for(const[name,data]of Object.entries(report.debug))fs.writeFileSync(path.join(out,`fringe-layer-${name}.png`),Buffer.from(data.split(',')[1],'base64'));delete report.debug;
  fs.writeFileSync(path.join(out,'meimei-fringe-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  assert.equal(report.featureHairPixels,0,'Hair ink must not belong to the moving eyelid');
  assert.ok(report.hairPixels>10000,'Review must retain a meaningful original hair region');
  assert.equal(report.baseHairChanges,0,'Cleaning the face must not repaint hair');
  for(const row of report.checks)assert.ok(row.maxError<=3,`${row.name}: original hair changed by ${row.maxError}`);
  for(const row of report.tracking)assert.ok(row.maxError<=3,`Tracked head ${JSON.stringify(row.head)}: blink changed the fringe by ${row.maxError}`);
  if(process.argv.includes('--record')){
   const video=await page.evaluate(async()=>{
    const{loadCharacter,composeCharacterFrame}=await import('./faithful-character.mjs');
    const{facialTarget,blinkClosure}=await import('./facial-rig.mjs');
    const rig=await loadCharacter(),source=composeCharacterFrame(rig.images,{pose:'idle'});
    const canvas=Object.assign(document.createElement('canvas'),{width:1000,height:680}),ctx=canvas.getContext('2d');
    document.body.append(canvas);const chunks=[],recorder=new MediaRecorder(canvas.captureStream(30),{mimeType:'video/webm;codecs=vp9',videoBitsPerSecond:2500000});
    recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};const done=new Promise(r=>recorder.onstop=r);recorder.start();
    await new Promise(resolve=>{let start;function tick(now){start??=now;const t=(now-start)/1000,head={x:Math.sin(t*.9)*.8,y:Math.sin(t*.6)*.8};
     const image=rig.mesh.draw(source,'blink-video',{pose:'idle',facial:facialTarget(null),time:t,blink:blinkClosure(t%1.6),gaze:head,head},{hairMotion:true,headTracking:true});
     ctx.fillStyle='#edf3ef';ctx.fillRect(0,0,1000,680);ctx.drawImage(image,280,300,500,340,0,0,1000,680);
     if(t<5)requestAnimationFrame(tick);else resolve();}requestAnimationFrame(tick);});
    recorder.stop();await done;const bytes=new Uint8Array(await new Blob(chunks).arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);
   });
   fs.writeFileSync(path.join(out,'meimei-fringe-blink.webm'),Buffer.from(video,'base64'));
  }
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
