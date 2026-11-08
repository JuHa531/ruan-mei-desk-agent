'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const BASE='http://127.0.0.1:7788';
function toolkitRoot(){
  const candidates=[process.env.RM_TOOLKIT_ROOT,path.resolve(__dirname,'../..')];
  let parent=path.dirname(process.execPath);
  for(let i=0;i<7;i++){candidates.push(parent);parent=path.dirname(parent);}
  const found=candidates.find(p=>p&&fs.existsSync(path.join(p,'app','agent_server.py')));
  if(!found)throw new Error('未找到梅梅应用目录，请设置 RM_TOOLKIT_ROOT。');
  return found;
}
function appPython(){return process.env.RM_APP_PYTHON||'D:\\ai\\envs\\meimei-app\\Scripts\\python.exe';}
function ensureMeimei(){
  const root=toolkitRoot();fs.mkdirSync(path.join(root,'logs'),{recursive:true});
  const fd=fs.openSync(path.join(root,'logs','pet-services.log'),'a');
  const child=spawn(appPython(),[path.join(root,'scripts','start_pet_services.py')],
    {cwd:root,windowsHide:true,stdio:['ignore',fd,fd]});
  fs.closeSync(fd);child.on('error',e=>console.error('MeiMei startup:',e.message));
  return child;
}
function openMeimei(){
  const root=toolkitRoot();
  const child=spawn(appPython().replace(/python\.exe$/i,'pythonw.exe'),[path.join(root,'app','desktop.py')],
    {cwd:root,windowsHide:true,stdio:'ignore'});
  child.on('error',e=>console.error('Open MeiMei:',e.message));return true;
}
async function meimeiFetch(_url,options={}){
  const requestId=require('node:crypto').randomUUID();
  const cancelTask=()=>fetch(BASE+'/api/agent-cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId})}).catch(()=>{});
  options.signal?.addEventListener('abort',cancelTask,{once:true});
  const body=JSON.parse(options.body||'{}');
  const messages=(body.messages||[]).filter(m=>['user','assistant'].includes(m.role))
    .map(m=>({role:m.role,content:m.content}));
  const upstream=await fetch(BASE+'/api/agent',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({messages,request_id:requestId}),signal:options.signal,redirect:'error'});
  if(!upstream.ok)return upstream;
  const encoder=new TextEncoder();
  const stream=new ReadableStream({
    async start(controller){
      const reader=upstream.body.getReader();const decoder=new TextDecoder();let pending='',finished=false;
      const event=value=>controller.enqueue(encoder.encode('data: '+JSON.stringify(value)+'\n\n'));
      const consume=async line=>{
        if(!line.trim()||finished)return;const item=JSON.parse(line);
        if(item.type==='text')event({choices:[{index:0,delta:{content:item.content||''},finish_reason:null}]});
        if(item.type==='approval'){
          const {dialog}=require('electron');
          const answer=await dialog.showMessageBox({type:'question',title:'梅梅 · 请求批准',message:'需要你批准：'+item.name,
            detail:JSON.stringify(item.args,null,2),buttons:['拒绝','批准这一次'],defaultId:0,cancelId:0,noLink:true});
          const response=await fetch(BASE+'/api/approve',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({token:item.token,allow:answer.response===1}),signal:options.signal});
          if(!response.ok)throw new Error('批准请求已失效，请重试。');
        }
        if(item.type==='error')throw new Error(item.content||'梅梅暂时无法回复。');
        if(item.type==='done'){event({choices:[{index:0,delta:{},finish_reason:'stop'}]});finished=true;}
      };
      try{
        while(!finished){const packet=await reader.read();if(packet.done){pending+=decoder.decode();break;}
          pending+=decoder.decode(packet.value,{stream:true});if(pending.length>2*1024*1024)throw new Error('回复过长。');
          let at;while((at=pending.indexOf('\n'))>=0){await consume(pending.slice(0,at));pending=pending.slice(at+1);}}
        if(pending.trim()&&!finished)await consume(pending);
        if(!finished)throw new Error('梅梅回复中断，请重试。');controller.close();
      }catch(error){await cancelTask();controller.error(error);}finally{options.signal?.removeEventListener('abort',cancelTask);await reader.cancel().catch(()=>{});}
    },cancel(){return upstream.body.cancel().catch(()=>{});}
  });
  return new Response(stream,{headers:{'Content-Type':'text/event-stream'}});
}
function createMeimeiSetup({onChange=()=>{}},kind='chat'){
  let state={phase:'idle',busy:false,ready:false,serverReady:false,runtimeReady:true,modelReady:true,
    canCancel:false,error:null,message:'复用本机梅梅服务，无需另外下载模型。',completedBytes:0,totalBytes:0};
  function getState(){return structuredClone(state);}
  async function inspect(){
    state={...state,phase:'checking',busy:true};onChange(getState());
    try{const response=await fetch(kind==='voice'?'http://127.0.0.1:9881/healthz':BASE+'/api/status',
      {signal:AbortSignal.timeout(5000)});if(!response.ok)throw new Error();
      state={...state,phase:'ready',busy:false,ready:true,serverReady:true,error:null,message:'已连接梅梅本机'+(kind==='voice'?'阮·梅语音。':'AI；人设、记忆和工具由梅梅统一处理。')};
    }catch{state={...state,phase:'error',busy:false,ready:false,serverReady:false,error:'梅梅服务正在启动或尚未就绪，请稍后点击检测。',message:'等待梅梅本机服务。'};}
    onChange(getState());return getState();
  }
  function install(){ensureMeimei();return inspect();}
  return {getState,inspect,install,installChatModel:install,ensureInstalledServer:inspect,
    cancel:()=>({ok:true,state:getState()}),dispose(){},getProjectRoot:toolkitRoot};
}
module.exports={BASE,toolkitRoot,appPython,ensureMeimei,openMeimei,meimeiFetch,createMeimeiSetup};
