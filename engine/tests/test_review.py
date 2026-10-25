import copy
import unittest
import test_domain as fixtures
from groupmate.domain import DomainError
from groupmate.observer import prepare
try:
    from groupmate.review import ReviewWorkspace
except ImportError:
    ReviewWorkspace=None


class ReviewTests(unittest.TestCase):
    setUp=fixtures.DomainTests.setUp
    tearDown=fixtures.DomainTests.tearDown
    publish=fixtures.DomainTests.publish
    room=fixtures.DomainTests.room

    def bound(self,task,body):
        return {'workflow_binding':task['input']['workflow_binding'],'body':body}

    def group_body(self,summary):
        return {'submission_version':None,'summary':summary,'reasoning':'No original submission.','disagreement_handling':'Not enough evidence.','knowledge_strengths_difficulties':'Not enough evidence.','evidence_ids':[],'limitations':['Synthetic teacher-imported fixture']}

    def workspace(self):
        self.assertIsNotNone(ReviewWorkspace,'Review workspace is not implemented')
        r,a,b=self.room(); m=self.app.message(a['token'],r['id'],'one','先确认部门的批准条件，再决定试点。')
        self.app.set_goal(a['token'],r['id'],'PRIVATE_GOAL')
        self.app.control(self.teacher,r['id'],'end')
        return ReviewWorkspace(self.app),r,a,b,m

    def test_teacher_exports_only_frozen_public_data_and_student_is_denied(self):
        w,r,a,b,m=self.workspace()
        task=w.create_task(self.teacher,r['id'],'EVIDENCE')
        self.assertNotIn('PRIVATE_GOAL',str(task['input']))
        self.assertEqual(task['input']['messages'][0]['phase'],'DISCUSSION')
        self.assertEqual(task['input']['messages'][0]['author_id'],a['participant_id'])
        with self.assertRaises(DomainError):w.create_task(a['token'],r['id'],'EVIDENCE')

    def test_evidence_batch_is_atomic_and_same_import_is_idempotent(self):
        w,r,a,b,m=self.workspace(); task=w.create_task(self.teacher,r['id'],'EVIDENCE')
        good={'participant_id':a['participant_id'],'message_id':m['id'],'quote':'批准条件'}
        with self.assertRaises(DomainError):w.import_result(self.teacher,task['id'],{'evidence_candidates':[good,{**good,'participant_id':b['participant_id']}]})
        self.assertEqual(self.app._all('evidence'),[])
        result=w.import_result(self.teacher,task['id'],{'evidence_candidates':[good]})
        self.assertEqual(w.import_result(self.teacher,task['id'],{'evidence_candidates':[good]}),result)
        self.assertEqual(len(self.app._all('evidence')),1)

    def test_observer_import_rechecks_gate_and_does_not_read_private_learning(self):
        w,r,a,b,m=self.workspace(); task=w.create_task(self.teacher,r['id'],'ASSESSMENT',a['participant_id'])
        self.assertNotIn('PRIVATE_GOAL',str(task['input']))
        payload=prepare(task['input'])['template']
        bad=copy.deepcopy(payload); bad['dimensions'][1].update(status='OBSERVED',level=4,evidence_ids=['fake'])
        with self.assertRaises(DomainError):w.import_result(self.teacher,task['id'],{'ok':True,'assessment':bad,'errors':[]})
        self.assertEqual(self.app._all('assessment'),[])
        w.import_result(self.teacher,task['id'],{'ok':True,'assessment':payload,'errors':[]})
        self.assertEqual(len(self.app._all('assessment')),1)

    def test_personal_task_is_stale_after_reflection_or_goal_edit(self):
        w,r,a,b,m=self.workspace()
        self.app.reflect(a['token'],r['id'],'first reflection')
        task=w.create_task(self.teacher,r['id'],'ASSESSMENT',a['participant_id'])
        w.import_result(self.teacher,task['id'],prepare(task['input'])['template'])
        p=w.create_task(self.teacher,r['id'],'PERSONAL',a['participant_id'])
        self.app.set_goal(a['token'],r['id'],'NEW_GOAL')
        with self.assertRaises(DomainError):w.import_result(self.teacher,p['id'],{'strength':None,'priority_improvement':None,'limitations':['no evidence']})
        p=w.create_task(self.teacher,r['id'],'PERSONAL',a['participant_id'])
        self.app.reflect(a['token'],r['id'],'second reflection')
        with self.assertRaises(DomainError):w.import_result(self.teacher,p['id'],{'strength':None,'priority_improvement':None,'limitations':['no evidence']})

    def test_teacher_group_review_not_blocked_and_student_release_gate_is_private(self):
        w,r,a,b,m=self.workspace(); task=w.create_task(self.teacher,r['id'],'GROUP')
        self.assertNotIn('PRIVATE_GOAL',str(task['input']))
        body=self.group_body('TEACHER_DRAFT_SECRET')
        result=w.import_result(self.teacher,task['id'],self.bound(task,body)); rid=result['record_ids'][0]
        self.assertIn('TEACHER_DRAFT_SECRET',str(w.dashboard(self.teacher,r['id'])))
        self.assertNotIn('TEACHER_DRAFT_SECRET',str(w.dashboard(a['token'],r['id'])))
        w.feedback.publish_report(self.teacher,rid)
        self.assertNotIn('TEACHER_DRAFT_SECRET',str(w.dashboard(a['token'],r['id'])))
        self.app.reflect(a['token'],r['id'],'',skip=True)
        self.assertIn('TEACHER_DRAFT_SECRET',str(w.dashboard(a['token'],r['id'])))
        self.assertNotIn('TEACHER_DRAFT_SECRET',str(w.dashboard(b['token'],r['id'])))

    def test_workflow_error_wrapper_and_cross_room_task_are_rejected(self):
        w,r,a,b,m=self.workspace(); task=w.create_task(self.teacher,r['id'],'ASSESSMENT',a['participant_id'])
        with self.assertRaises(DomainError):w.import_result(self.teacher,task['id'],{'ok':False,'errors':['STATUS_C2'],'assessment':None})
        with self.assertRaises(DomainError):w.import_result(a['token'],task['id'],{})

    def test_teacher_revision_keeps_original_and_needs_new_review(self):
        w,r,a,b,m=self.workspace(); task=w.create_task(self.teacher,r['id'],'GROUP')
        body=self.group_body('original')
        result=w.import_result(self.teacher,task['id'],self.bound(task,body)); old_id=result['record_ids'][0]
        w.feedback.publish_report(self.teacher,old_id)
        revised=w.revise_report(self.teacher,old_id,{**body,'summary':'revised'})
        self.assertEqual(self.app._get(old_id)['body']['summary'],'original')
        self.assertEqual(self.app._get(old_id)['status'],'PUBLISHED')
        self.assertEqual(revised['status'],'DRAFT')
        self.assertEqual(revised['supersedes'],old_id)
        w.feedback.publish_report(self.teacher,revised['id'])
        self.assertEqual(self.app._get(old_id)['status'],'SUPERSEDED')
        with self.assertRaises(DomainError): w.feedback.publish_report(self.teacher,old_id)

    def test_empty_or_wrong_report_shape_never_enters_review(self):
        w,r,a,b,m=self.workspace(); task=w.create_task(self.teacher,r['id'],'GROUP')
        for value in [{},{**self.group_body('x'),'summary':[]},{**self.group_body('x'),'evidence_ids':[{}]}]:
            with self.assertRaises(DomainError):w.import_result(self.teacher,task['id'],self.bound(task,value))
        self.assertEqual(self.app._all('report'),[])

    def test_class_task_and_report_are_teacher_only_without_self_reflection(self):
        from groupmate.class_reports import SECTION_KEYS
        w,r,a,b,m=self.workspace();task=w.create_task(self.teacher,r['id'],'CLASS',room_ids=[r['id']])
        body={'sections':[{'key':k,'text':'CLASS_TEACHER_SECRET','claims':[]} for k in SECTION_KEYS],'limitations':['Synthetic']}
        result=w.import_result(self.teacher,task['id'],self.bound(task,body));rid=result['record_ids'][0]
        w.publish_report(self.teacher,rid)
        self.assertIn('CLASS_TEACHER_SECRET',str(w.dashboard(self.teacher,r['id'])))
        self.assertNotIn('CLASS_TEACHER_SECRET',str(w.dashboard(a['token'],r['id'])))
        with self.assertRaises(DomainError):w.publish_report(a['token'],rid)

    def test_teacher_recorded_conditions_change_observer_input_and_stale_old_task(self):
        w,r,a,b,m=self.workspace();task=w.create_task(self.teacher,r['id'],'ASSESSMENT',a['participant_id'])
        conditions={'data_complete':False,'opportunity':{'C2':'NONE'},'note':'Synthetic connection gap and no response opportunity'}
        with self.assertRaises(DomainError):w.record_conditions(a['token'],r['id'],a['participant_id'],conditions)
        w.record_conditions(self.teacher,r['id'],a['participant_id'],conditions)
        now=w.feedback.assessment_context(self.teacher,r['id'],a['participant_id'])
        self.assertFalse(now['data_complete']);self.assertEqual(now['opportunity']['C2'],'NONE')
        self.assertIn(conditions['note'],now['limitations'])
        with self.assertRaises(DomainError):w.import_result(self.teacher,task['id'],prepare(task['input'])['template'])

    def test_report_import_requires_binding_and_rejects_cross_task_replay(self):
        w,r,a,b,m=self.workspace()
        one=w.create_task(self.teacher,r['id'],'GROUP')
        two=w.create_task(self.teacher,r['id'],'GROUP')
        body=self.group_body('Synthetic old output')
        envelope={'workflow_binding':{'task_id':one['id'],'kind':'GROUP','room_id':r['id'],'participant_id':None,'input_hash':one['input_hash']},'body':body}
        for output in [body,envelope]:
            with self.assertRaises(DomainError):w.import_result(self.teacher,two['id'],output)
        self.assertEqual(self.app._all('report'),[])
        self.assertEqual(one['input']['workflow_binding'],envelope['workflow_binding'])
        w.import_result(self.teacher,one['id'],envelope)

    def test_personal_output_cannot_replay_across_students_or_goal_versions(self):
        w,r,a,b,m=self.workspace();tasks=[]
        for student in [a,b]:
            self.app.reflect(student['token'],r['id'],'Synthetic reflection')
            assessment=w.create_task(self.teacher,r['id'],'ASSESSMENT',student['participant_id'])
            w.import_result(self.teacher,assessment['id'],prepare(assessment['input'])['template'])
            tasks.append(w.create_task(self.teacher,r['id'],'PERSONAL',student['participant_id']))
        one,two=tasks
        body={'goal_review':'PRIVATE_GOAL','self_reflection_comparison':'Synthetic','strength':None,'priority_improvement':None,'next_action':'Collect evidence','dimension_details':one['input']['independent_assessment']['dimensions'],'knowledge_observations':[],'limitations':[]}
        output=self.bound(one,body)
        with self.assertRaises(DomainError):w.import_result(self.teacher,two['id'],output)
        self.app.set_goal(a['token'],r['id'],'UPDATED_GOAL')
        fresh=w.create_task(self.teacher,r['id'],'PERSONAL',a['participant_id'])
        with self.assertRaises(DomainError):w.import_result(self.teacher,fresh['id'],output)
        self.assertEqual(self.app._all('report'),[])
