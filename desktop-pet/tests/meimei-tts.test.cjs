const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const {toolkitRoot,appPython}=require('../electron/meimei-bridge.cjs');
test('private speech protocol delegates to MeiMei, waits for acknowledgement and never loads another model',()=>{
 const code=[
  'import importlib.util,sys,io,json,wave,base64',
  "spec=importlib.util.spec_from_file_location('pettts',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)",
  "root=sys.argv[2];sys.argv=['pettts','--project-root',root]",
  "buf=io.BytesIO();w=wave.open(buf,'wb');w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\\0\\0'*1600);w.close();audio=buf.getvalue()",
  "items=iter([{'type':'warmup'},{'type':'speak','text':'Hello.'},{'type':'next'},None]);m.read=lambda:next(items)",
  "packets=[];m.emit=packets.append",
  'def open_url(req,timeout):\n if isinstance(req,str):\n  assert req==\'http://127.0.0.1:9881/healthz\';return io.BytesIO(b\'{"ok":true}\')\n assert req.full_url==\'http://127.0.0.1:7788/api/tts\'\n payload=json.loads(req.data);assert payload=={\'text\':\'Hello.\',\'voice\':\'ruanmei:calm\'}\n return io.BytesIO(audio)',
  "m.urllib.request.urlopen=open_url;m.main()",
  "assert [p['type'] for p in packets]==['ready','synthesizing','audio','done'],packets",
  "assert base64.b64decode(packets[2]['base64'])==audio",
  "assert 'torch' not in sys.modules",
 ].join('\n');
 const result=spawnSync(appPython(),['-c',code,path.resolve(__dirname,'../electron/chat-tts-worker.py'),toolkitRoot()],{encoding:'utf8',windowsHide:true});
 assert.equal(result.status,0,result.stderr);
});
