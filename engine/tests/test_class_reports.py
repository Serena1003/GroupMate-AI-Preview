import copy
import unittest
import test_domain as fixtures
from groupmate.domain import DomainError
from groupmate.feedback import FeedbackService
from groupmate.observer import prepare
try:
    from groupmate.class_reports import ClassReports, SECTION_KEYS
except ImportError:
    ClassReports=None
    SECTION_KEYS=[]


class ClassReportTests(unittest.TestCase):
    setUp=fixtures.DomainTests.setUp
    tearDown=fixtures.DomainTests.tearDown
    publish=fixtures.DomainTests.publish
    room=fixtures.DomainTests.room

    def groups(self):
        self.assertIsNotNone(ClassReports,'Class statistics are not implemented')
        p=fixtures.packet();p['assessment']['knowledge']=['授权'];p['assessment']['selected']=['C2']
        p['assessment']['rubric']={'dimensions':[{'dimension':'C2','levels':{str(n):'anchor '+str(n) for n in range(1,5)}}]}
        d=self.app.create_draft(self.teacher,p)
        for n in range(1,10):self.app.confirm(self.teacher,d['id'],n,1)
        snap=self.app.publish(self.teacher,d['id'],1); rooms=[]; participants=[]
        for name in ['A','B']:
            r=self.app.create_room(self.teacher,snap['id'],name)
            people=[self.app.join(r['join_code'],'同名') for _ in range(2)]
            self.app.control(self.teacher,r['id'],'start')
            messages=[self.app.message(a['token'],r['id'],'one','应先确认批准权限。') for a in people]
            self.app.control(self.teacher,r['id'],'end')
            rooms.append(r);participants.append((people,messages))
        f=FeedbackService(self.app)
        for a,m in zip(*participants[0]):
            f.evidence(self.teacher,rooms[0]['id'],a['participant_id'],m['id'],'批准权限')
            c=f.assessment_context(self.teacher,rooms[0]['id'],a['participant_id']);v=prepare(c)['template'];eid=c['verified_evidence'][0]['id']
            v['dimensions'][1].update(status='OBSERVED',level=3,evidence_ids=[eid],explanation='synthetic judgment')
            v['knowledge_observations']=[{'tag':'授权','status':'SUPPORTED','evidence_ids':[eid],'explanation':'synthetic knowledge observation'}]
            f.record_assessment(self.teacher,rooms[0]['id'],a['participant_id'],v)
        return ClassReports(self.app),rooms,participants

    def candidate(self,context):
        return {'sections':[{'key':k,'text':'Synthetic review draft','claims':[]} for k in SECTION_KEYS],'limitations':['Synthetic test only']}

    def test_units_denominators_and_group_deduplication(self):
        c,rooms,people=self.groups();ctx=c.context(self.teacher,[r['id'] for r in rooms])
        group=next(s for s in ctx['statistics'] if s['metric']=='knowledge_supported_groups')
        self.assertEqual((group['unit'],group['numerator'],group['denominator'],group['missing_count']),('GROUP',1,2,1))
        coverage=next(s for s in ctx['statistics'] if s['metric']=='dimension_observed')
        self.assertEqual((coverage['unit'],coverage['numerator'],coverage['denominator'],coverage['missing_count']),('STUDENT',2,4,2))
        level=next(s for s in ctx['statistics'] if s['metric']=='dimension_level' and s['level']==3)
        self.assertEqual((level['numerator'],level['denominator']), (2,2))
        self.assertNotIn('average_level',str(ctx));self.assertNotIn('reflection',str(ctx))

    def test_duplicate_scope_not_double_counted_and_student_denied(self):
        c,rooms,people=self.groups()
        ctx=c.context(self.teacher,[rooms[0]['id'],rooms[0]['id']])
        self.assertEqual(ctx['scope']['group_count'],1)
        with self.assertRaises(DomainError):c.context(people[0][0][0]['token'],[rooms[0]['id']])

    def test_different_conditions_are_not_merged(self):
        c,rooms,people=self.groups()
        with self.app.transaction():
            r=self.app._get(rooms[1]['id']); r['elapsed_base']=300;self.app._put(r,'room')
        ctx=c.context(self.teacher,[r['id'] for r in rooms])
        self.assertEqual(len(ctx['strata']),2)

    def test_six_sections_unknown_ids_and_model_rewritten_statistics_rejected(self):
        c,rooms,people=self.groups();ctx=c.context(self.teacher,[rooms[0]['id']]);body=self.candidate(ctx)
        for change in ['sections','refs','stats']:
            bad=copy.deepcopy(body)
            if change=='sections':bad['sections'].pop()
            if change=='refs':bad['sections'][0]['claims']=[{'text':'claim','stat_ids':['fake'],'evidence_ids':[],'counterexample_ids':[],'limitations':[]}]
            if change=='stats':bad['statistics']=[]
            with self.assertRaises(DomainError):c.stage(self.teacher,ctx['scope']['room_ids'],ctx['input_hash'],bad)

    def test_source_change_stales_report_but_self_reflection_does_not(self):
        c,rooms,people=self.groups();scope=[rooms[0]['id']];ctx=c.context(self.teacher,scope)
        record=c.stage(self.teacher,scope,ctx['input_hash'],self.candidate(ctx));c.publish(self.teacher,record['id'])
        a=people[0][0][0];self.app.reflect(a['token'],rooms[0]['id'],'PRIVATE_REFLECTION')
        self.assertTrue(c.current(record))
        f=FeedbackService(self.app);cx=f.assessment_context(self.teacher,rooms[0]['id'],a['participant_id']);v=prepare(cx)['template']
        f.record_assessment(self.teacher,rooms[0]['id'],a['participant_id'],v)
        self.assertFalse(c.current(record))
        with self.assertRaises(DomainError):c.publish(self.teacher,record['id'])

    def test_identical_evidence_registration_does_not_stale_report(self):
        c,rooms,people=self.groups();scope=[rooms[0]['id']];ctx=c.context(self.teacher,scope)
        record=c.stage(self.teacher,scope,ctx['input_hash'],self.candidate(ctx))
        a=people[0][0][0];m=people[0][1][0]
        FeedbackService(self.app).evidence(self.teacher,rooms[0]['id'],a['participant_id'],m['id'],'批准权限')
        self.assertTrue(c.current(record))

    def test_missing_per_tag_and_partial_assessments_remain_missing(self):
        c,rooms,people=self.groups();scope=[rooms[0]['id']]
        for a in self.app._all('assessment'):
            a['knowledge_observations']=[];self.app._put(a,'assessment')
        stat=next(s for s in c.context(self.teacher,scope)['statistics'] if s['metric']=='knowledge_supported_groups')
        self.assertEqual((stat['missing_count'],stat['not_observed_count']),(1,0))
        assessments=self.app._all('assessment')
        assessments[0]['knowledge_observations']=[{'tag':'授权','status':'NOT_OBSERVED','evidence_ids':[],'explanation':'Synthetic explicit no observation'}]
        self.app._put(assessments[0],'assessment')
        stat=next(s for s in c.context(self.teacher,scope)['statistics'] if s['metric']=='knowledge_supported_groups')
        self.assertEqual((stat['missing_count'],stat['partial_count'],stat['not_observed_count']),(1,1,0))
        assessments[1]['knowledge_observations']=assessments[0]['knowledge_observations'];self.app._put(assessments[1],'assessment')
        stat=next(s for s in c.context(self.teacher,scope)['statistics'] if s['metric']=='knowledge_supported_groups')
        self.assertEqual((stat['missing_count'],stat['partial_count'],stat['not_observed_count']),(0,0,1))
