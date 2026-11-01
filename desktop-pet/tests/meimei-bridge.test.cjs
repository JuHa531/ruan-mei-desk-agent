const test=require('node:test'),assert=require('node:assert/strict');
const {meimeiFetch}=require('../electron/meimei-bridge.cjs');
test('MeiMei keeps its own persona and receives user/assistant history; NDJSON becomes streamed text',async()=>{
 const previous=global.fetch;let sent;
 global.fetch=async(url,request)=>{sent={url,body:JSON.parse(request.body)};return new Response([
  JSON.stringify({type:'tool',name:'music'}),JSON.stringify({type:'text',content:'亲爱的，'}),
  JSON.stringify({type:'text',content:'我在听。'}),JSON.stringify({type:'done'})].join('\n')+'\n');};
 try{
  const result=await meimeiFetch('http://untrusted.invalid',{body:JSON.stringify({messages:[
   {role:'system',content:'wrong persona'},{role:'assistant',content:'上一句'},{role:'user',content:'你好'}]})});
  const data=await result.text();assert.equal(sent.url,'http://127.0.0.1:7788/api/agent');
  assert.deepEqual(sent.body.messages,[{role:'assistant',content:'上一句'},{role:'user',content:'你好'}]);
  assert.ok(data.includes('亲爱的，')&&data.includes('我在听。')&&data.includes('"finish_reason":"stop"'));
 }finally{global.fetch=previous;}
});
test('backend errors cannot become a successful completed reply',async()=>{
 const previous=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({type:'error',content:'offline'})+'\n');
 try{const response=await meimeiFetch('',{body:'{}'});await assert.rejects(()=>response.text(),/offline/);}
 finally{global.fetch=previous;}
});
test('reference character assets and voices are not used; generated Ruan Mei packs are complete',()=>{
 const {loadVoiceAssets,loadInteractionAssets}=require('../electron/voice-assets.cjs');
 const path=require('node:path'),fs=require('node:fs'),root=path.resolve(__dirname,'..');
 const daily=loadVoiceAssets(root),interaction=loadInteractionAssets(root);
 assert.equal(daily.available,true,daily.error);assert.equal(daily.lines.size,36);
 assert.equal(interaction.available,true,interaction.error);assert.equal(interaction.lines.size,18);
 for(const line of [...daily.lines.values(),...interaction.lines.values()])assert.ok(!line.text.includes('爱莉希雅'));
 const character=fs.readdirSync(path.join(root,'assets/character'));
 assert.ok(character.every(name=>name.startsWith('ruanmei-')));
 assert.ok(character.includes('ruanmei-actions.png')&&character.includes('ruanmei-neutral.png'));
 assert.ok(!fs.readFileSync(path.join(root,'renderer/faithful-character.mjs'),'utf8').includes('ruanmei-expressions.png'),'Expressions must not replace the face with another image');
});
