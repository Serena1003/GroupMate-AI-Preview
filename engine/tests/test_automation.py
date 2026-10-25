"""Core web journey with labelled synthetic transport, not live XIPU."""
import tempfile,threading,unittest
from pathlib import Path
from groupmate.domain import Classroom
from groupmate.server import make_server
import test_http as fixtures
class SyntheticWorkflow:
    def run(self,v,user_id):
        if 'requested_fields' in v:
            out={'workflow_binding':v['workflow_binding'],'proposal_patch':{'title':'Synthetic suggestion'},'limitations':['Synthetic transport test']}
        elif 'assigned_role' in v:
            out={k:v[k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']}
            out.update(role_id=v['assigned_role']['role_id'],should_speak=True,text='What evidence supports this proposal?',used_fact_ids=['BASE'],responding_to_ids=v['responding_to_ids'],help_kind='NONE')
        else:
            out={'workflow_binding':v['workflow_binding'],'body':{'submission_version':v['frozen_submission']['version'],'summary':'Synthetic summary','reasoning':'Based on frozen proposal','disagreement_handling':'No claim beyond records','knowledge_strengths_difficulties':'Insufficient evidence','evidence_ids':[],'limitations':['Synthetic transport test']}}
        return {'value':out,'run_id':'synthetic-run'}
class AutomationJourney(unittest.TestCase):
    req=fixtures.HttpTests.req
    setup_room=fixtures.HttpTests.setup_room
    tearDown=fixtures.HttpTests.tearDown
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Classroom(str(Path(self.tmp.name)/'db'))
        self.server=make_server(self.app,'test-owner',port=0,workflow_client=SyntheticWorkflow())
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
    def test_role_and_report_generation_then_teacher_publication(self):
        t,r=self.setup_room();student=self.req('/api/join',{'code':r['join_code'],'name':'Synthetic student'})[1]
        self.req('/api/control',{'room_id':r['id'],'action':'start'},t)
        self.req('/api/message',{'room_id':r['id'],'client_id':'one','text':'Please verify approval before proceeding.'},student['token'])
        role=self.app._get(r['snapshot_id'])['packet']['roles'][0]['id']
        _,task=self.req('/api/manual-role/prepare',{'room_id':r['id'],'role_id':role},t)
        code,result=self.req('/api/automation/run',{'task_id':task['id']},t)
        self.assertEqual(code,200,result);self.assertEqual(result['status'],'DELIVERED')
        self.req('/api/submit',{'room_id':r['id'],'raw':'Original proposal unchanged','expected_version':0},student['token'])
        self.req('/api/control',{'room_id':r['id'],'action':'end'},t)
        _,task=self.req('/api/review/task',{'room_id':r['id'],'kind':'GROUP'},t)
        code,result=self.req('/api/automation/run',{'task_id':task['id']},t)
        self.assertEqual(code,200,result);rid=result['record_ids'][0]
        self.assertNotEqual(self.app._get(rid)['status'],'PUBLISHED')
        self.assertEqual(self.req('/api/review/publish',{'report_id':rid},t)[0],200)
        self.assertEqual(self.app._get(r['id'])['frozen_submission']['raw'],'Original proposal unchanged')
    def test_preparation_keeps_teacher_adoption(self):
        from test_domain import packet
        t=self.req('/api/login',{'secret':'test-owner'})[1]['token'];draft=self.req('/api/drafts',{'packet':packet()},t)[1]
        _,task=self.req('/api/preparation/task',{'draft_id':draft['id'],'stage':'DESIGN','fields':['title'],'source_ids':[],'requirements':{}},t)
        code,p=self.req('/api/automation/run',{'task_id':task['id']},t);self.assertEqual(code,200,p)
        self.assertEqual(self.app._get(draft['id'])['packet']['title'],draft['packet']['title'])
        self.assertEqual(self.req('/api/preparation/decide',{'proposal_id':p['id'],'decision':'ACCEPT'},t)[0],200)
        self.assertEqual(self.app._get(draft['id'])['packet']['title'],'Synthetic suggestion')
