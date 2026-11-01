const fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url'),{chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'..'),browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:430,height:80},deviceScaleFactor:2});
  await page.goto(pathToFileURL(path.join(root,'renderer/speech.html')).href);
  await page.evaluate(async()=>{
   await document.fonts.ready;
   const speech=document.querySelector('#speech');speech.dataset.layout='ready';speech.dataset.side='left';
   document.querySelector('#line').textContent='我会在这里，陪你慢慢把今天的事理清。';
  });
  fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});await page.screenshot({path:path.join(root,'artifacts/meimei-speech-theme.png'),omitBackground:true});
  console.log('Speech bubble preview saved.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
