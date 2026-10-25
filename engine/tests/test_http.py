import concurrent.futures
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from groupmate.domain import Classroom
from test_domain import packet


class HttpTests(unittest.TestCase):
    def setUp(self):
        from groupmate.server import make_server
        self.tmp=tempfile.TemporaryDirectory()
        self.app=Classroom(str(Path(self.tmp.name)/'db'))
        self.server=make_server(self.app,'test-owner',port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.app.close(); self.tmp.cleanup()

    def req(self,path,data=None,token=None,origin=None):
        headers={'Content-Type':'application/json'}
        if token: headers['Authorization']='Bearer '+token
        if origin: headers['Origin']=origin
        request=urllib.request.Request(self.base+path,None if data is None else json.dumps(data).encode(),headers=headers)
        try:
            with urllib.request.urlopen(request) as r: return r.status,json.load(r)
        except urllib.error.HTTPError as e: return e.code,json.load(e)

    def setup_room(self):
        _,auth=self.req('/api/login',{'secret':'test-owner'}); t=auth['token']
        _,d=self.req('/api/drafts',{'packet':packet()},t)
        for n in range(1,10): self.req('/api/confirm',{'draft_id':d['id'],'revision':1,'node':n},t)
        _,s=self.req('/api/publish',{'draft_id':d['id'],'revision':1},t)
        _,r=self.req('/api/rooms',{'snapshot_id':s['id'],'name':'A组'},t)
        return t,r

    def test_real_concurrent_members_have_unique_order_and_ownership(self):
        t,r=self.setup_room()
        students=[self.req('/api/join',{'code':r['join_code'],'name':'同名'})[1] for _ in range(4)]
        self.req('/api/control',{'room_id':r['id'],'action':'start'},t)
        def post(i): return self.req('/api/message',{'room_id':r['id'],'client_id':'one','text':'成员'+str(i)},students[i]['token'])
        with concurrent.futures.ThreadPoolExecutor() as pool: out=list(pool.map(post,range(4)))
        self.assertTrue(all(code==200 for code,_ in out))
        self.assertEqual(len({v['seq'] for _,v in out}),4)
        self.assertEqual(len({v['author_id'] for _,v in out}),4)
        _,view=self.req('/api/room?room_id='+r['id'],token=students[0]['token'])
        self.assertEqual(len([m for m in view['events'] if m['type']=='MESSAGE']),4)
        self.assertNotIn('learning',view)

    def test_unauthorized_and_cross_origin_rejected(self):
        self.assertEqual(self.req('/api/rooms',{'snapshot_id':'x','name':'x'})[0],401)
        self.assertEqual(self.req('/api/login',{'secret':'wrong'})[0],401)
        self.assertEqual(self.req('/api/login',{'secret':'test-owner'},origin='https://other.example')[0],403)

    def test_sample_packet_is_teacher_only_not_in_static_javascript(self):
        self.assertEqual(self.req('/api/sample')[0],401)
        _,auth=self.req('/api/login',{'secret':'test-owner'})
        code,p=self.req('/api/sample',token=auth['token'])
        self.assertEqual(code,200)
        self.assertIn('teacher_only',p['case'])
        with urllib.request.urlopen(self.base+'/app.js') as response:
            script=response.read().decode()
        self.assertNotIn('约两年延期',script)
        self.assertNotIn('新增教学模拟事件：项目组正式提议',script)
        self.assertNotIn('teacher_only:',script)

    def test_json_error_does_not_leak_traceback(self):
        code,body=self.req('/api/control',{})
        self.assertIn(code,[400,401]); self.assertNotIn('Traceback',json.dumps(body))

    def test_review_routes_preserve_teacher_approval_and_each_student_gate(self):
        t,r=self.setup_room(); _,a=self.req('/api/join',{'code':r['join_code'],'name':'A'})
        _,b=self.req('/api/join',{'code':r['join_code'],'name':'B'})
        self.req('/api/control',{'room_id':r['id'],'action':'start'},t)
        self.req('/api/control',{'room_id':r['id'],'action':'end'},t)
        code,task=self.req('/api/review/task',{'room_id':r['id'],'kind':'GROUP'},t)
        self.assertEqual(code,200)
        self.assertEqual(self.req('/api/review/task',{'room_id':r['id'],'kind':'GROUP'},a['token'])[0],403)
        body={'submission_version':None,'summary':'REVIEW_ONLY_SECRET','reasoning':'No original submission.','disagreement_handling':'No evidence.','knowledge_strengths_difficulties':'No evidence.','evidence_ids':[],'limitations':['Synthetic fixture']}
        code,result=self.req('/api/review/import',{'task_id':task['id'],'output':{'workflow_binding':task['input']['workflow_binding'],'body':body}},t)
        self.assertEqual(code,200)
        rid=result['record_ids'][0]
        self.assertNotIn('REVIEW_ONLY_SECRET',str(self.req('/api/review?room_id='+r['id'],token=a['token'])))
        self.assertEqual(self.req('/api/review/publish',{'report_id':rid},a['token'])[0],403)
        self.assertEqual(self.req('/api/review/publish',{'report_id':rid},t)[0],200)
        self.assertNotIn('REVIEW_ONLY_SECRET',str(self.req('/api/review?room_id='+r['id'],token=a['token'])))
        self.req('/api/reflection',{'room_id':r['id'],'text':'reflection'},a['token'])
        self.assertIn('REVIEW_ONLY_SECRET',str(self.req('/api/review?room_id='+r['id'],token=a['token'])))
        self.assertNotIn('REVIEW_ONLY_SECRET',str(self.req('/api/review?room_id='+r['id'],token=b['token'])))
        self.assertEqual(len(self.req('/api/rooms',token=t)[1]),1)
