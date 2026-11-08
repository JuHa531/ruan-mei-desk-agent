import sys,json,tempfile,threading,urllib.request,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import agent_server as agent
from agent_permissions import PermissionStore,tool_limits,authorized,approval_scope
class Controls(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=PermissionStore(Path(self.tmp.name)/'permissions.json')
  self.patch=patch.object(agent,'PERMISSIONS',self.store);self.patch.start();self.addCleanup(self.patch.stop)
  root=self.tmp.name
  class Handler(agent.Handler):
   cfg={'model':'test','ollama':'http://unused','workdir':root}
   def log_message(self,*args):pass
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
  self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
 def post(self,path,body):
  r=urllib.request.Request('http://127.0.0.1:%s%s'%(self.server.server_port,path),data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  return urllib.request.urlopen(r,timeout=10)
 def run_task(self,mode='auto',count=1,allow=True,text='列出文件',name='list_dir'):
  self.store.save(mode)
  calls=[{'message':{'tool_calls':[{'id':str(i),'function':{'name':name,'arguments':{'path':'.'} if name=='list_dir' else {'command':'echo test'}}}]}} for i in range(count)]
  calls.append({'message':{'content':'处理完成。'}})
  events=[]
  with patch.object(agent,'model_chat',side_effect=calls),patch.object(agent,'exec_tool',return_value='完成') as execute,patch.object(agent,'select_tools',return_value=agent.TOOLS):
   with self.post('/api/agent',{'messages':[{'role':'user','content':text}],'request_id':'testing-1234'}) as response:
    for raw in response:
     item=json.loads(raw);events.append(item)
     if item['type']=='approval':
      with self.post('/api/approve',{'token':item['token'],'allow':allow}) as answer:answer.read()
     if item['type']=='done':break
   return events,execute.call_count
 def test_unbounded_over_eight(self):
  events,n=self.run_task(count=10);self.assertEqual(n,10);self.assertFalse([e for e in events if e['type']=='error'])
 def test_request_approval_and_deny(self):
  events,n=self.run_task(mode='ask',allow=False);self.assertEqual(n,0);self.assertEqual(events[0]['type'],'approval')
 def test_request_and_action_approval(self):
  events,n=self.run_task(mode='ask');self.assertEqual(n,1);self.assertEqual(len([e for e in events if e['type']=='approval']),2)
 def test_sensitive_auto_and_full(self):
  events,n=self.run_task(name='run_cmd');self.assertEqual(n,1);self.assertEqual(len([e for e in events if e['type']=='approval']),1)
  events,n=self.run_task(mode='full',name='run_cmd');self.assertEqual(n,1);self.assertFalse([e for e in events if e['type']=='approval'])
 def test_limits(self):
  events,n=self.run_task(count=5,text='列出文件，最多2轮');self.assertEqual(n,2)
  events,n=self.run_task(count=5,text='列出文件，最多调用三次工具');self.assertEqual(n,3)
  self.assertEqual(tool_limits('正常做完'),(None,None))
 def test_scope_and_persistence(self):
  self.assertFalse(authorized())
  with approval_scope():self.assertTrue(authorized())
  self.assertFalse(authorized());self.store.save('full');self.assertEqual(PermissionStore(self.store.path).mode,'full')
 def test_cancel_wait_and_reuse(self):
  event=self.store.begin('cancel-1234');events=[]
  def emit(item):
   events.append(item)
   if item['type']=='approval':self.store.cancel('cancel-1234')
  with self.assertRaises(RuntimeError):self.store.ask('cancel-1234','test',{},emit,event)
  with self.assertRaises(ValueError):self.store.decide(events[0]['token'],True)
if __name__=='__main__':unittest.main()
