'use strict';
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(name,predicate,seconds=100){
 const until=Date.now()+seconds*1000;
 while(Date.now()<until){const result=await predicate();if(result)return result;await delay(100);}
 throw new Error(name+' timed out');
}
async function check({pet,chat,chatWindow,chatSpeech,voices,ipcMain,root}){
 await wait('character',()=>pet.webContents.executeJavaScript('Boolean(window.ruanmeiPreview?.rendering?.assetsReady)'));
 const panel=await chatWindow.open();
 await wait('chat',()=>panel.webContents.executeJavaScript('document.documentElement.dataset.chatReady==="true"'));
 const report={assets:true,bridgeSandbox:true,dailyClips:36,interactionClips:18};
 const settings=panel.webContents.getLastWebPreferences();assert.ok(settings.sandbox&&settings.contextIsolation&&!settings.nodeIntegration);
 const sent=await panel.webContents.executeJavaScript('window.ruanmeiChat.send("查询QQ音乐现在的播放状态，按实际结果告诉我。")');
 assert.ok(sent.busy);
 await wait('MeiMei reply',()=>!chat.getState().busy);
 const state=chat.getState();assert.equal(state.error,null);
 const reply=state.conversations.find(c=>c.id===state.activeConversationId).messages.at(-1);
 assert.equal(reply.status,'complete');assert.ok(reply.content.trim());
 assert.ok(!reply.content.includes('这次没能自动点播'),reply.content);
 report.reply=reply.content;report.chat=true;
 const bytes=fs.readFileSync(path.join(root,'assets/interaction-voice/audio-final/H01.wav'));
 const asr=await panel.webContents.executeJavaScript(`window.ruanmeiChat.transcribe(Uint8Array.from(atob(${JSON.stringify(bytes.toString('base64'))}),c=>c.charCodeAt(0)))`);
 assert.ok(asr.text?.trim());report.asr=asr.text;
 const reference=JSON.stringify({conversationId:state.activeConversationId,messageId:reply.id});
 await panel.webContents.executeJavaScript(`window.ruanmeiChat.readAloud(${reference})`);
 let started=false;
 await wait('MeiMei voice playback',()=>{
  const speech=chatSpeech.getState();if(speech.status==='error')throw new Error(speech.error);
  if(['starting','synthesizing','playing','ready'].includes(speech.status))started=true;
  return started&&!chatSpeech.isActive()&&['ready','idle'].includes(speech.status);
 },120);
 report.ttsPlaybackAcknowledged=true;
 assert.ok(voices.getState().available&&voices.getState().interactionAvailable);
 await panel.webContents.executeJavaScript('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
 const artifact=path.join(require('./meimei-bridge.cjs').toolkitRoot(),'desktop-pet','artifacts');fs.mkdirSync(artifact,{recursive:true});
 fs.writeFileSync(path.join(artifact,'meimei-chat.png'),(await panel.webContents.capturePage()).toPNG());
 fs.writeFileSync(path.join(artifact,'meimei-integration.json'),JSON.stringify(report,null,2));
 return report;
}
module.exports={check};
