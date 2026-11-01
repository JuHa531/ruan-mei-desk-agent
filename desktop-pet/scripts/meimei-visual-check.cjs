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
  const page=await browser.newPage({viewport:{width:600,height:800}}),errors=[];
  page.on('pageerror',e=>{errors.push(e.message);console.error(e.stack);});
  page.on('console',m=>{if(m.type()==='error')console.error('BROWSER',m.text());});
  await page.goto(`http://127.0.0.1:${server.address().port}/renderer/index.html`);
  try{await page.waitForSelector('html[data-ready="true"]',{timeout:20000});}
  catch(error){console.error('LOADING',await page.locator('body').innerText());throw error;}
  const report=await page.evaluate(()=>({rendering:window.ruanmeiPreview.rendering,state:window.ruanmeiPreview.snapshot()}));
  for(const pose of ['idle','megaphone','cake','tea']){
    const data=await page.evaluate(p=>window.ruanmeiPreview.render({pose:p,time:1.2}),pose);
    fs.writeFileSync(path.join(out,`meimei-${pose}.png`),Buffer.from(data.split(',')[1],'base64'));
  }
  for(const expression of ['sleep','surprise','smile','angry','wink']){
    const data=await page.evaluate(expression=>window.ruanmeiPreview.render({expression,time:1.2}),expression);
    fs.writeFileSync(path.join(out,`meimei-${expression}.png`),Buffer.from(data.split(',')[1],'base64'));
  }
  if(errors.length)throw new Error(errors.join('\n'));
  console.log(JSON.stringify(report));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
