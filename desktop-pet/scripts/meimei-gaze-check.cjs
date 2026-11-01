'use strict';
const {createServer}=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'artifacts');fs.mkdirSync(out,{recursive:true});
const server=createServer((req,res)=>{
 const file=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);
 if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',({'.mjs':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json','.png':'image/png'})[path.extname(file)]||'text/plain');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:600,height:800}});
  await page.goto(`http://127.0.0.1:${server.address().port}/renderer/index.html`);
  await page.waitForSelector('html[data-ready="true"]');
  const result=await page.evaluate(async()=>{
   const {loadCharacter,composeCharacterFrame}=await import('./faithful-character.mjs');
   const {createFacialLayers}=await import('./facial-rig.mjs');
   const rigs=await loadCharacter(),result={tracking:{},downward:{}};
   const face=document.createElement('canvas');face.width=940;face.height=380;
   face.getContext('2d').drawImage(rigs.images.neutral,280,390,470,190,0,0,940,380);result.face=face.toDataURL();
   const layers=createFacialLayers(composeCharacterFrame(rigs.images,{pose:'idle'}));
   for(const id of ['base','eye','iris','mask']){face.getContext('2d').clearRect(0,0,940,380);face.getContext('2d').drawImage(layers[id],280,390,470,190,0,0,940,380);result[id]=face.toDataURL();}
   for(const pose of ['idle','megaphone','cake','tea']){
    const source=composeCharacterFrame(rigs.images,{pose,expression:null});
    const W=source.width,H=source.height,data=source.getContext('2d').getImageData(0,0,W,H).data;
    const groups=[[],[]];
    for(let y=400;y<555;y++)for(let x=320;x<710;x++){
     const p=(y*W+x)*4,r=data[p],g=data[p+1],b=data[p+2];
     if(data[p+3]>200&&r<160&&g>130&&b>130&&g>r*1.2&&b>r*1.2)groups[x<520?0:1].push([x,y]);
    }
    result[pose]=groups.map(points=>({n:points.length,x:points.reduce((v,p)=>v+p[0],0)/points.length,y:points.reduce((v,p)=>v+p[1],0)/points.length,bounds:[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))]}));
    result.tracking[pose]=[];const shots=[];
    const read=document.createElement('canvas');read.width=W;read.height=H;const rc=read.getContext('2d',{willReadFrequently:true});
    for(const x of [-1,0,1]){
     const drawn=rigs.mesh.draw(source,pose,{pose,gaze:{x,y:0},time:0,blink:0},{hairMotion:false});rc.clearRect(0,0,W,H);rc.drawImage(drawn,0,0);
     const pixels=rc.getImageData(0,0,W,H).data,eyes=[[],[]];
     shots.push(pixels);
     for(let y=400;y<555;y++)for(let k=320;k<710;k++){const p=(y*W+k)*4,r=pixels[p],g=pixels[p+1],b=pixels[p+2];if(r<160&&g>130&&b>130&&g>r*1.2&&b>r*1.2)eyes[k<520?0:1].push([k,y]);}
     result.tracking[pose].push(eyes.map(points=>({x:points.reduce((n,p)=>n+p[0],0)/points.length,width:Math.max(...points.map(p=>p[0]))-Math.min(...points.map(p=>p[0])),height:Math.max(...points.map(p=>p[1]))-Math.min(...points.map(p=>p[1])),count:points.length})));
    }
    const layers=createFacialLayers(source),clip=layers.mask.getContext('2d').getImageData(0,0,W,H).data,feature=layers.eye.getContext('2d').getImageData(0,0,W,H).data;
    for(const[index,shift]of[[0,-5],[2,5]])for(let eye=0;eye<2;eye++){
     let error=0,count=0;
     for(let y=400;y<555;y++)for(let x=eye?520:320;x<(eye?710:520);x++){
      const p=(y*W+x)*4,q=(y*W+x+shift)*4,r=shots[1][p],g=shots[1][p+1],b=shots[1][p+2];
      if(r<160&&g>130&&b>130&&g>r*1.2&&b>r*1.2&&Math.abs(x-result[pose][eye].x)<17&&Math.abs(y-result[pose][eye].y)<12){for(let c=0;c<3;c++)error+=Math.abs(shots[1][p+c]-shots[index][q+c]);count++;}
     }
     result.tracking[pose][index][eye].translationError=error/Math.max(1,count*3);result.tracking[pose][index][eye].comparedPixels=count;
    }
   }
   for(const pose of ['idle','megaphone','cake','tea']){
    const source=composeCharacterFrame(rigs.images,{pose}),read=document.createElement('canvas');read.width=1090;read.height=1443;const rc=read.getContext('2d',{willReadFrequently:true}),positions=[];
    for(const y of [0,1]){
     rc.clearRect(0,0,1090,1443);rc.drawImage(rigs.mesh.draw(source,pose,{pose,gaze:{x:0,y},time:0,blink:0},{hairMotion:false,headTracking:false}),0,0);
     const pixels=rc.getImageData(0,0,1090,1443).data,eyes=[[],[]];
     for(let row=400;row<555;row++)for(let x=320;x<710;x++){const p=(row*1090+x)*4,r=pixels[p],g=pixels[p+1],b=pixels[p+2];if(r<160&&g>130&&b>130&&g>r*1.2&&b>r*1.2)eyes[x<520?0:1].push(row);}
     positions.push(eyes.map(values=>values.reduce((sum,value)=>sum+value,0)/values.length));
    }
    result.downward[pose]=positions[1].map((value,i)=>value-positions[0][i]);
   }
   return result;
  });
  for(const[x,label]of[[-1,'left'],[0,'center'],[1,'right']]){
   const data=await page.evaluate(x=>window.ruanmeiPreview.render({gaze:{x,y:0},time:0,resolutionScale:2}),x);
   fs.writeFileSync(path.join(out,`gaze-${label}.png`),Buffer.from(data.split(',')[1],'base64'));
  }
  fs.writeFileSync(path.join(out,'gaze-source-eyes.png'),Buffer.from(result.face.split(',')[1],'base64'));delete result.face;
  for(const id of ['base','eye','iris','mask']){fs.writeFileSync(path.join(out,`gaze-${id}.png`),Buffer.from(result[id].split(',')[1],'base64'));delete result[id];}
  const assert=require('node:assert/strict');
  for(const[pose,eyes]of Object.entries(result.downward))assert.ok(eyes.every(dy=>dy>3),`${pose}: both irises must clearly move down (${eyes})`);
  fs.writeFileSync(path.join(out,'meimei-gaze.json'),JSON.stringify(result,null,2));
  for(const[pose,frames]of Object.entries(result.tracking))for(let eye=0;eye<2;eye++){
   assert.ok(frames[2][eye].x-frames[0][eye].x>8,`${pose} eye ${eye}: iris must move in both directions`);
   for(const f of[frames[0][eye],frames[2][eye]]){assert.ok(f.comparedPixels>60,`${pose} eye ${eye}: enough interior iris pixels (${f.comparedPixels})`);assert.ok(f.translationError<1.5,`${pose} eye ${eye}: translated iris pixels must retain their shape/colors (${f.translationError})`);}
  }
  fs.writeFileSync(path.join(out,'meimei-gaze.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
