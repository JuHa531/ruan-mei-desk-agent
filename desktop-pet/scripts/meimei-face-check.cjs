'use strict';
const {createServer}=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright'),root=path.resolve(__dirname,'..'),out=path.join(root,'artifacts');
const server=createServer((req,res)=>{
 const file=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);
 if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',({'.mjs':'text/javascript','.html':'text/html','.css':'text/css','.png':'image/png'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:600,height:800}});await page.goto(`http://127.0.0.1:${server.address().port}/renderer/index.html`);await page.waitForSelector('html[data-ready="true"]');
  const report=await page.evaluate(async()=>{
   const{loadCharacter,composeCharacterFrame}=await import('./faithful-character.mjs'),{createFacialLayers,facialTarget}=await import('./facial-rig.mjs');
   const rig=await loadCharacter(),canvas=document.createElement('canvas'),read=document.createElement('canvas');canvas.width=1000;canvas.height=1700;read.width=1090;read.height=1443;
   const ctx=canvas.getContext('2d'),rc=read.getContext('2d',{willReadFrequently:true}),result={poses:{},closeups:{}};
   const cases=[['original',null,0,0],['neutral',null,0,0],['down',null,1,0],['down 200%',null,1,0],['up',null,-1,0],['angry','angry',1,0],['smile','smile',0,0],['wink','wink',0,0],['blink half',null,0,.5],['closed',null,0,1],['surprise','surprise',0,0]];
   for(const[poseIndex,pose]of['idle','megaphone','cake','tea'].entries()){
    const source=composeCharacterFrame(rig.images,{pose}),layers=createFacialLayers(source),original=source.getContext('2d').getImageData(0,0,1090,1443).data;
    const fg=layers.iris.getContext('2d').getImageData(0,0,1090,1443).data,mask=layers.mask.getContext('2d').getImageData(0,0,1090,1443).data;
    result.poses[pose]={caps:[],neutralError:0,downCapPixels:[]};
    for(const[cx,cy]of layers.eyes){
     let first=-1;const x=Math.round(cx);
     for(let y=Math.floor(cy-60);y<cy+30;y++){const p=(y*1090+x)*4;if(fg[p+3]>240&&mask[p+3]){first=y;break;}}
     let cap=0;for(let y=first-16;y<first;y++){const p=(y*1090+x)*4;if(fg[p+3]>240&&!mask[p+3])cap++;}
     result.poses[pose].caps.push(cap);
    }
    for(const[index,[label,expression,gy,blink]]of cases.entries()){
     const state={pose,expression,gaze:{x:0,y:gy},head:{x:0,y:0},time:0,blink,facial:facialTarget(expression)};
     const image=label==='original'?source:rig.mesh.draw(source,pose,state,{hairMotion:false,headTracking:false,eyeWarpStrength:label==='down 200%'?2:1});
     rc.clearRect(0,0,1090,1443);rc.drawImage(image,0,0);const pixels=rc.getImageData(0,0,1090,1443).data;
     if(pose==='idle'&&['neutral','closed','angry','down 200%'].includes(label)){
      const close=document.createElement('canvas');close.width=920;close.height=370;close.getContext('2d').drawImage(read,290,395,460,185,0,0,920,370);result.closeups[label]=close.toDataURL();
     }
     if(label==='neutral'){
      let error=0,n=0;for(let y=395;y<580;y++)for(let x=290;x<750;x++){const p=(y*1090+x)*4;for(let c=0;c<3;c++){error+=Math.abs(pixels[p+c]-original[p+c]);n++;}}
      result.poses[pose].neutralError=error/n;
     }
     if(label==='down 200%')for(const[cx,cy]of layers.eyes){
      const x=Math.round(cx);let first=-1;for(let y=Math.floor(cy-60);y<cy+30;y++){const p=(y*1090+x)*4;if(fg[p+3]>240&&mask[p+3]){first=y;break;}}
      result.poses[pose].downCapPixels.push(Array.from(pixels.slice(((first+1)*1090+x)*4,((first+1)*1090+x)*4+4)));
     }
     const left=poseIndex%2*500,top=Math.floor(poseIndex/2)*850+index*76;
     ctx.fillStyle='#edf3ef';ctx.fillRect(left,top,500,76);ctx.fillStyle='#12352c';ctx.font='12px sans-serif';ctx.fillText(`${pose} · ${label}`,left+4,top+13);
     ctx.drawImage(read,290,395,460,185,left+180,top+2,312,72);
    }
   }
   result.contactSheet=canvas.toDataURL();return result;
  });
  fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'meimei-face-check.png'),Buffer.from(report.contactSheet.split(',')[1],'base64'));delete report.contactSheet;
  for(const[name,data]of Object.entries(report.closeups))fs.writeFileSync(path.join(out,'face-'+name.replaceAll(' ','-')+'.png'),Buffer.from(data.split(',')[1],'base64'));delete report.closeups;
  fs.writeFileSync(path.join(out,'meimei-face-check.json'),JSON.stringify(report,null,2));
  for(const[pose,values]of Object.entries(report.poses)){
   assert.ok(values.neutralError<2.5,`${pose}: original neutral face must be retained (${values.neutralError})`);
   assert.ok(values.caps.every(n=>n>=10),`${pose}: hidden upper iris must be complete (${values.caps})`);
   assert.ok(values.downCapPixels.every(p=>p[0]<185&&p[3]===255),`${pose}: looking down must not expose a white/transparent gap`);
  }
  console.log(JSON.stringify(report));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
