"""Core real HTTP journey only: read, teacher review, publish, student visibility."""
import copy
import json
from pathlib import Path
from test_domain import packet
import unittest
import test_http as http_fixtures
from groupmate.feedback import FeedbackService
from groupmate.observer import prepare
from groupmate.class_reports import SECTION_KEYS


class DashboardJourney(unittest.TestCase):
    setUp=http_fixtures.HttpTests.setUp
    tearDown=http_fixtures.HttpTests.tearDown
    req=http_fixtures.HttpTests.req
    setup_room=http_fixtures.HttpTests.setup_room

    def activity(self):
        t=self.req('/api/login',{'secret':'test-owner'})[1]['token']
        p=packet();p['assessment']['rubric']=json.loads(Path('groupmate/sample.json').read_text())['assessment']['rubric']
        d=self.req('/api/drafts',{'packet':p},t)[1]
        for n in range(1,10):self.req('/api/confirm',{'draft_id':d['id'],'revision':1,'node':n},t)
        snap=self.req('/api/publish',{'draft_id':d['id'],'revision':1},t)[1]
        r=self.req('/api/rooms',{'snapshot_id':snap['id'],'name':'核心流程验证组'},t)[1]
        a=self.req('/api/join',{'code':r['join_code'],'name':'蓝舟'})[1]
        b=self.req('/api/join',{'code':r['join_code'],'name':'蓝舟'})[1]
        self.req('/api/control',{'room_id':r['id'],'action':'start'},t)
        m=self.req('/api/message',{'room_id':r['id'],'client_id':'one','text':'请先核实部门批准权限，再讨论试点。'},a['token'])[1]
        self.req('/api/submit',{'room_id':r['id'],'raw':'原始学生建议：先确认授权。','expected_version':0},a['token'])
        self.req('/api/control',{'room_id':r['id'],'action':'end'},t)
        f=FeedbackService(self.app)
        f.evidence(t,r['id'],a['participant_id'],m['id'],'批准权限')
        cx=f.assessment_context(t,r['id'],a['participant_id']);value=prepare(cx)['template']
        value['dimensions'][1].update(status='OBSERVED',level=3,evidence_ids=[cx['verified_evidence'][0]['id']],explanation='合成夹具：先核实部门批准权限。')
        baseline=f.record_assessment(t,r['id'],a['participant_id'],value)
        return t,r,a,b,baseline

    def session(self,t,r):
        code,s=self.req('/api/v1/teacher/sessions',{'title':'核心流程合成课堂','room_ids':[r['id']],'data_mode':'SYNTHETIC'},t)
        self.assertEqual(code,200,s)
        return s

    def test_dashboard_reads_real_counts_original_and_evidence(self):
        t,r,a,b,baseline=self.activity();s=self.session(t,r)
        code,d=self.req('/api/v1/teacher/sessions/'+s['id']+'/dashboard',token=t)
        self.assertEqual(code,200,d)
        self.assertEqual(d['scope']['joined_students'],2)
        self.assertEqual(d['scope']['submitted_groups'],1)
        self.assertEqual(d['scope']['assessments_ready'],1)
        self.assertEqual(d['scope']['registered_students'],None)
        self.assertEqual(len(d['groups']),1)
        self.assertEqual(d['dimensions'][0]['data_incomplete'],0)
        self.assertEqual(d['dimensions'][0]['pending'],1)
        self.assertEqual(d['dimensions'][0]['observed'],1)
        _,g=self.req('/api/v1/teacher/groups/'+r['id'],token=t)
        self.assertEqual(g['original_submission']['raw'],'原始学生建议：先确认授权。')
        self.assertNotEqual(g['members'][0]['id'],g['members'][1]['id'])
        e=g['evidence'][0]
        _,cx=self.req('/api/v1/teacher/evidence/'+e['id']+'/context',token=t)
        self.assertEqual(cx['evidence']['quote'],'批准权限')
        self.assertIn('请先核实',cx['messages'][0]['text'])

    def test_teacher_review_then_report_revision_publish_and_reload(self):
        t,r,a,b,baseline=self.activity();s=self.session(t,r)
        dimensions=copy.deepcopy(baseline['dimensions']);dimensions[1].update(level=4,explanation='教师合成夹具：对照锚点与本人证据采用L4，仅验证修订传输。')
        code,review=self.req('/api/v1/teacher/assessment-reviews',{'assessment_id':baseline['id'],'expected_adopted_id':baseline['id'],'dimensions':dimensions,'note':'核查完成'},t)
        self.assertEqual(code,200,review)
        self.assertEqual(self.app._get(baseline['id'])['dimensions'],baseline['dimensions'])
        adopted=self.req('/api/v1/teacher/groups/'+r['id'],token=t)[1]['assessments'][0]
        self.assertEqual(adopted['dimensions'][1]['level'],4)
        self.req('/api/reflection',{'room_id':r['id'],'text':'我先核实了授权，下一次会解释原因。'},a['token'])
        _,task=self.req('/api/review/task',{'room_id':r['id'],'kind':'PERSONAL','participant_id':a['participant_id']},t)
        self.assertEqual(task['input']['adopted_assessment']['id'],review['id'])
        self.assertEqual(task['input']['independent_assessment']['id'],baseline['id'])
        body={'goal_review':'本次目标回顾','self_reflection_comparison':'对照实际记录','strength':None,'priority_improvement':None,'next_action':'下次明确批准条件。','dimension_details':dimensions,'knowledge_observations':[],'limitations':['合成流程验证，不是正式成绩']}
        code,result=self.req('/api/review/import',{'task_id':task['id'],'output':{'workflow_binding':task['input']['workflow_binding'],'body':body}},t)
        self.assertEqual(code,200,result);rid=result['record_ids'][0]
        _,edited=self.req('/api/review/revise',{'report_id':rid,'body':{**body,'next_action':'教师确认：下次先说明批准条件。'}},t)
        self.assertEqual(self.req('/api/review/publish',{'report_id':edited['id']},t)[0],200)
        _,detail=self.req('/api/v1/teacher/reports/'+edited['id'],token=t)
        self.assertEqual(detail['status'],'PUBLISHED')
        self.assertEqual(detail['body']['next_action'],'教师确认：下次先说明批准条件。')
        _,student=self.req('/api/review?room_id='+r['id'],token=a['token'])
        self.assertIn('教师确认',str(student))
        self.assertNotIn('教师确认',str(self.req('/api/review?room_id='+r['id'],token=b['token'])))
        _,ct=self.req('/api/review/task',{'room_id':r['id'],'kind':'CLASS','room_ids':[r['id']]},t)
        cb={'sections':[{'key':k,'text':'本节来自本次实际冻结记录。','claims':[]} for k in SECTION_KEYS],'limitations':['合成课堂']}
        cb['sections'][0]['claims']=[{'text':'本次选维评价覆盖可回查统计。','stat_ids':[ct['input']['statistics'][0]['stat_id']],'evidence_ids':[],'counterexample_ids':[],'limitations':['仅限本次范围']}]
        _,cr=self.req('/api/review/import',{'task_id':ct['id'],'output':{'workflow_binding':ct['input']['workflow_binding'],'body':cb}},t)
        self.assertEqual(self.req('/api/review/publish',{'report_id':cr['record_ids'][0]},t)[0],200)
        highlight=self.req('/api/v1/teacher/sessions/'+s['id']+'/dashboard',token=t)[1]['highlight']
        self.assertEqual(highlight.get('referenced_statistics',[]),[ct['input']['statistics'][0]])
        dimensions[1]['explanation']='教师第二次核查并保留证据不足结论。'
        self.req('/api/v1/teacher/assessment-reviews',{'assessment_id':baseline['id'],'expected_adopted_id':review['id'],'dimensions':dimensions,'note':'更新解释'},t)
        self.assertEqual(self.req('/api/v1/teacher/reports/'+edited['id'],token=t)[1]['status'],'STALE')
        self.assertEqual(self.req('/api/v1/teacher/reports/'+cr['record_ids'][0],token=t)[1]['status'],'STALE')

if __name__=='__main__':unittest.main()
