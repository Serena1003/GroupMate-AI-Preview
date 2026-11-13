"""Core web journey with labelled synthetic transport, not live XIPU."""
import tempfile,threading,unittest
from pathlib import Path
from groupmate.domain import Classroom
from groupmate.server import make_server
import test_http as fixtures
class SyntheticWorkflow:
    def run(self,v,user_id):
        if 'frozen_log_id' in v and 'participants' in v:
            out={'evidence_candidates':[]}
        elif 'participant_id' in v and 'selected_dimensions' in v:
            from groupmate.observer import prepare
            out=prepare(v)['template']
        elif 'requested_fields' in v:

            out={'workflow_binding':v['workflow_binding'],'proposal_patch':{'title':'Synthetic suggestion'},'limitations':['Synthetic transport test']}
        elif 'assigned_role' in v:
            out={k:v[k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']}
            out.update(role_id=v['assigned_role']['role_id'],should_speak=True,text='What evidence supports this proposal?',used_fact_ids=['BASE'],responding_to_ids=v['responding_to_ids'],help_kind='NONE')
        else:
            out={'workflow_binding':v['workflow_binding'],'body':{'submission_version':(v['frozen_submission'] or {}).get('version'),'summary':'Synthetic summary','reasoning':'Based on frozen proposal','disagreement_handling':'No claim beyond records','knowledge_strengths_difficulties':'Insufficient evidence','evidence_ids':[],'limitations':['Synthetic transport test']}}
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

    def test_simple_discussion_reflection_and_published_outcome(self):
        t,r=self.setup_room();student=self.req('/api/join',{'code':r['join_code'],'name':'Synthetic student'})[1]
        self.req('/api/control',{'room_id':r['id'],'action':'start'},t)
        self.req('/api/message',{'room_id':r['id'],'client_id':'chat','text':'Check who can approve the pilot.'},student['token'])
        self.req('/api/control',{'room_id':r['id'],'action':'end'},t)
        _,task=self.req('/api/review/task',{'room_id':r['id'],'kind':'GROUP'},t)
        self.assertEqual(task['input']['synthesis_basis'],'FROZEN_DISCUSSION')
        code,result=self.req('/api/automation/run',{'task_id':task['id']},t);self.assertEqual(code,200,result)
        self.req('/api/review/publish',{'report_id':result['record_ids'][0]},t)
        before=self.req('/api/review?room_id='+r['id'],token=student['token'])[1]
        self.assertNotIn('outcome',before)
        self.req('/api/reflection',{'room_id':r['id'],'text':'We identified an approval gap.'},student['token'])
        after=self.req('/api/review?room_id='+r['id'],token=student['token'])[1]
        self.assertEqual(after['outcome']['status'],'PUBLISHED')
        self.assertEqual(after['outcome']['message_count'],1)
        self.assertIsNone(self.app._get(r['id'])['frozen_submission'])
        _,session=self.req('/api/v1/teacher/sessions',{'title':'Simple classroom','room_ids':[r['id']],'data_mode':'SYNTHETIC'},t)
        code,dash=self.req('/api/v1/teacher/sessions/'+session['id']+'/dashboard',token=t)
        self.assertEqual(code,200,dash);self.assertEqual(dash['outcomes'][0]['report_id'],result['record_ids'][0])

    def test_module_document_is_context_and_not_case_material(self):
        import base64
        from test_domain import packet
        t=self.req('/api/login',{'secret':'test-owner'})[1]['token']
        _,draft=self.req('/api/drafts',{'packet':packet()},t)
        code,doc=self.req('/api/sources/upload',{'filename':'module-spec.txt','content':base64.b64encode(b'Learning outcome: analyse stakeholder engagement.').decode(),'purpose':'COURSE_CONTEXT'},t)
        self.assertEqual(code,200,doc)
        code,draft=self.req('/api/update',{'draft_id':draft['id'],'revision':draft['revision'],'patch':{'course_context':{'title':'IOM420','summary':'Stakeholder engagement','source_ids':[doc['id']]}}},t)
        self.assertEqual(code,200,draft)
        _,task=self.req('/api/preparation/task',{'draft_id':draft['id'],'stage':'SOURCE','fields':['source','case'],'source_ids':[],'requirements':{}},t)
        self.assertEqual(task['input']['source_documents'],[])
        self.assertEqual(task['input']['course_context']['documents'][0]['id'],doc['id'])

    def test_generate_all_dimensions_then_review_and_publish(self):
        t,r=self.setup_room()
        students=[self.req('/api/join',{'code':r['join_code'],'name':n})[1] for n in ['Alex','River']]
        self.req('/api/control',{'room_id':r['id'],'action':'start'},t)
        for i,student in enumerate(students):
            self.req('/api/message',{'room_id':r['id'],'client_id':str(i),'text':'Check approval authority before implementation.'},student['token'])
        self.req('/api/control',{'room_id':r['id'],'action':'end'},t)
        for kind,person in [('EVIDENCE',None)]+[('ASSESSMENT',s['participant_id']) for s in students]+[('GROUP',None)]:
            code,task=self.req('/api/review/task',{'room_id':r['id'],'kind':kind,'participant_id':person,'require_teacher_review':True},t)
            self.assertEqual(code,200,task)
            code,result=self.req('/api/automation/run',{'task_id':task['id']},t)
            self.assertEqual(code,200,result)
        data=self.req('/api/v1/teacher/groups/'+r['id'],token=t)[1]
        self.assertEqual(len(data['assessments']),2)
        self.assertEqual(len(data['assessments'][0]['dimensions']),6)
        a=data['assessments'][0]
        code,adoption=self.req('/api/v1/teacher/assessment-reviews',{'assessment_id':a['id'],'expected_adopted_id':a['id'],'dimensions':a['dimensions'],'excluded_dimensions':['C2'],'note':'Teacher review'},t)
        self.assertEqual(code,200,adoption)
        self.assertEqual(adoption['excluded_dimensions'],['C2'])
        updated=self.req('/api/v1/teacher/groups/'+r['id'],token=t)[1]
        self.assertEqual(updated['assessments'][0]['excluded_dimensions'],['C2'])
        report=next(x for x in updated['reports'] if x['kind']=='GROUP')
        self.assertEqual(report['status'],'DRAFT')
        self.assertEqual(self.req('/api/review/publish',{'report_id':report['id']},t)[0],200)
        student=students[0]
        self.req('/api/reflection',{'room_id':r['id'],'text':'We checked the approval gap.'},student['token'])
        self.assertEqual(self.req('/api/review?room_id='+r['id'],token=student['token'])[1]['outcome']['status'],'PUBLISHED')
