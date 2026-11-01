const bridge=window.ruanmeiChat;
const mic=document.querySelector('#chat-mic'),status=document.querySelector('#chat-mic-status'),input=document.querySelector('#chat-input');
let recorder=null,stream=null,timer=null,pending=false;
const micIcon=mic.innerHTML;
document.querySelector('#chat-open-meimei').addEventListener('click',()=>bridge.openMeimei());
mic.addEventListener('click',async()=>{
  if(pending)return;
  if(recorder?.state==='recording'){recorder.stop();return;}
  try{
    stream=await navigator.mediaDevices.getUserMedia({audio:true,video:false});
    const chunks=[];recorder=new MediaRecorder(stream,{mimeType:'audio/webm'});
    recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
    recorder.onstop=async()=>{
      clearTimeout(timer);stream?.getTracks().forEach(t=>t.stop());stream=null;mic.innerHTML=micIcon;
      pending=true;mic.disabled=true;status.textContent='正在识别…';
      try{
        const bytes=new Uint8Array(await new Blob(chunks,{type:'audio/webm'}).arrayBuffer());
        const result=await bridge.transcribe(bytes);
        input.value+=(input.value?'\n':'')+(result.text||'');input.dispatchEvent(new Event('input'));input.focus();
        status.textContent=result.text?'识别完成，按 Enter 发送。':'没有听清，请重试。';
      }catch(error){status.textContent=error.message||'识别失败，请重试。';}
      finally{pending=false;mic.disabled=false;recorder=null;}
    };
    recorder.start();mic.textContent='■';status.textContent='正在听，再点一次结束。';timer=setTimeout(()=>recorder?.state==='recording'&&recorder.stop(),60000);
  }catch(error){stream?.getTracks().forEach(t=>t.stop());status.textContent='无法使用麦克风，请检查 Windows 麦克风权限。';}
});
window.addEventListener('pagehide',()=>{clearTimeout(timer);stream?.getTracks().forEach(t=>t.stop());});
