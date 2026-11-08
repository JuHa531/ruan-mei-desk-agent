const {chromium}=require('../desktop-pet/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1280,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));let submitted;
 await page.route('**/api/agent',route=>{submitted=route.request().postDataJSON();return route.fulfill({contentType:'application/x-ndjson',body:JSON.stringify({type:'text',content:'我在这里，慢慢说。'})+'\n'+JSON.stringify({type:'done'})+'\n'});});
 await page.goto('http://127.0.0.1:7788/',{waitUntil:'domcontentloaded'});
 await page.evaluate(()=>{localStorage.setItem('rm_voice','0');localStorage.setItem('rm_sessions',JSON.stringify([
  {id:'old',title:'保留的旧对话',items:[{role:'user',text:'过去的讨论'},{role:'assistant',text:'过去的回复',done:true}]},
  {id:'empty',title:'新的对话',items:[]}
 ]));});
 await page.reload({waitUntil:'domcontentloaded'});
 const count=()=>page.evaluate(()=>JSON.parse(localStorage.getItem('rm_sessions')).length);
 if(await page.locator('#title').textContent()!=='新的对话')throw Error('opened old conversation');
 if(await count()!==1)throw Error('empty legacy item retained');
 for(let i=0;i<4;i++)await page.locator('#new').click();
 if(await count()!==1||await page.locator('#sessions .sess').count()!==1)throw Error('blank drafts in history');
 await page.locator('#inp').fill('亲爱的');await page.locator('#send').click();
 if(await count()!==1)throw Error('wake-only conversation persisted');
 await page.locator('#new').click();
 await page.locator('#inp').fill('今天想聊一会儿');await page.locator('#send').click();
 await page.waitForFunction(()=>!document.querySelector('#send').disabled);
 if(await count()!==2)throw Error('real chat not retained');
 if(submitted.messages.some(m=>m.content==='过去的讨论'))throw Error('new chat leaks old context');
 await page.reload({waitUntil:'domcontentloaded'});
 if(await page.locator('#title').textContent()!=='新的对话'||await count()!==2)throw Error('reopen failed');
 await page.locator('#sessions .sess').filter({hasText:'保留的旧对话'}).click();
 if(!await page.locator('#log').textContent().then(t=>t.includes('过去的回复')))throw Error('history not accessible');
 await page.reload({waitUntil:'domcontentloaded'});
 if(await page.locator('#title').textContent()!=='新的对话'||await count()!==2)throw Error('history reopened on boot');
 if(errors.length)throw Error(errors.join('\n'));
 console.log(JSON.stringify({passed:true,checks:['fresh boot','legacy empty cleanup','repeated new draft','wake-only draft','real chat saved','context isolation','reload stable','history reopen'],pageErrors:errors}));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
