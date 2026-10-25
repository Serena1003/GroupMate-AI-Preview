import unittest
import test_domain as fixtures
from groupmate.domain import DomainError


class FeedbackTests(unittest.TestCase):
    setUp=fixtures.DomainTests.setUp
    tearDown=fixtures.DomainTests.tearDown
    publish=fixtures.DomainTests.publish
    room=fixtures.DomainTests.room

    def discussion(self):
        r,a,b=self.room(); self.app.set_goal(a['token'],r['id'],'PRIVATE_GOAL')
        m=self.app.message(a['token'],r['id'],'m','应先确认受影响部门意见和批准权限。')
        self.app.control(self.teacher,r['id'],'end')
        return r,a,b,m

    def test_independent_context_excludes_goal_reflection_and_has_real_evidence(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); self.app.reflect(a['token'],r['id'],'PRIVATE_REFLECTION')
        f=FeedbackService(self.app)
        ev=f.evidence(self.teacher,r['id'],a['participant_id'],m['id'],'批准权限')
        context=f.assessment_context(self.teacher,r['id'],a['participant_id'])
        self.assertNotIn('PRIVATE_GOAL',str(context)); self.assertNotIn('PRIVATE_REFLECTION',str(context))
        self.assertEqual(context['verified_evidence'][0]['evidence_id'],ev['evidence_id'])
        with self.assertRaises(DomainError): f.evidence(self.teacher,r['id'],b['participant_id'],m['id'],'批准权限')

    def test_student_feedback_gate_is_individual_and_teacher_not_blocked(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); f=FeedbackService(self.app)
        report=f.stage_report(self.teacher,r['id'],'GROUP',{'submission_version':None,'summary':'没有完整小组提交，无法评价结论。','evidence_ids':[],'limitations':['合成测试草案，证据不足']})
        f.publish_report(self.teacher,report['id'])
        self.assertEqual(f.get_report(self.teacher,report['id'])['status'],'PUBLISHED')
        with self.assertRaises(DomainError): f.get_report(a['token'],report['id'])
        self.app.reflect(a['token'],r['id'],'',skip=True)
        self.assertEqual(f.get_report(a['token'],report['id'])['id'],report['id'])
        with self.assertRaises(DomainError): f.get_report(b['token'],report['id'])

    def test_personal_report_excludes_other_student_and_old_reflection_is_stale(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); f=FeedbackService(self.app)
        self.app.reflect(a['token'],r['id'],'初次自评')
        report=f.stage_report(self.teacher,r['id'],'PERSONAL',{'strength':None,'priority_improvement':None,'next_action':'下次明确依据','limitations':['证据不足']},participant_id=a['participant_id'])
        f.publish_report(self.teacher,report['id'])
        self.assertEqual(f.get_report(a['token'],report['id'])['id'],report['id'])
        self.app.reflect(b['token'],r['id'],'乙的自评')
        with self.assertRaises(DomainError): f.get_report(b['token'],report['id'])
        self.app.reflect(a['token'],r['id'],'更新后的自评')
        with self.assertRaises(DomainError): f.get_report(a['token'],report['id'])

    def assessment_payload(self,context):
        from groupmate.observer import prepare
        return prepare(context)['template']

    def test_record_assessment_rejects_wrong_missing_data_reason(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); f=FeedbackService(self.app)
        context=f.assessment_context(self.teacher,r['id'],a['participant_id']); value=self.assessment_payload(context)
        value['dimensions'][1]['status']='INSUFFICIENT_OPPORTUNITY'
        with self.assertRaises(DomainError): f.record_assessment(self.teacher,r['id'],a['participant_id'],value)

    def test_independent_assessment_is_immutable_and_unaffected_by_self_reflection(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); f=FeedbackService(self.app)
        context=f.assessment_context(self.teacher,r['id'],a['participant_id'])
        value=self.assessment_payload(context)
        baseline=f.record_assessment(self.teacher,r['id'],a['participant_id'],value)
        self.app.reflect(a['token'],r['id'],'PRIVATE_UPDATED_REFLECTION')
        after=f.assessment_context(self.teacher,r['id'],a['participant_id'])
        self.assertEqual(context['input_hash'],after['input_hash'])
        self.assertEqual(f.record_assessment(self.teacher,r['id'],a['participant_id'],value)['id'],baseline['id'])
        self.assertNotIn('PRIVATE_UPDATED_REFLECTION',str(baseline))

    def test_observed_level_requires_real_evidence_and_available_rubric(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); f=FeedbackService(self.app)
        context=f.assessment_context(self.teacher,r['id'],a['participant_id'])
        value=self.assessment_payload(context); value['dimensions'][1].update(status='OBSERVED',level=4,evidence_ids=['fake'])
        with self.assertRaises(DomainError): f.record_assessment(self.teacher,r['id'],a['participant_id'],value)
        ev=f.evidence(self.teacher,r['id'],a['participant_id'],m['id'],'批准权限')
        context=f.assessment_context(self.teacher,r['id'],a['participant_id']); value=self.assessment_payload(context)
        value['dimensions'][1].update(status='OBSERVED',level=4,evidence_ids=[ev['id']])
        with self.assertRaises(DomainError): f.record_assessment(self.teacher,r['id'],a['participant_id'],value)

    def test_assessment_rejects_wrong_input_hash_and_aggregate_score(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); f=FeedbackService(self.app)
        context=f.assessment_context(self.teacher,r['id'],a['participant_id']); value=self.assessment_payload(context)
        value['input_hash']='wrong'
        with self.assertRaises(DomainError): f.record_assessment(self.teacher,r['id'],a['participant_id'],value)
        value=self.assessment_payload(context); value['total_score']=98
        with self.assertRaises(DomainError): f.record_assessment(self.teacher,r['id'],a['participant_id'],value)

    def graded_case(self,anchors=None):
        from groupmate.feedback import FeedbackService
        p=fixtures.packet(); p['assessment']['rubric']={'dimensions':[{'dimension':'C2','levels':anchors or {str(n):'Synthetic anchor '+str(n) for n in range(1,5)}}]}
        d=self.app.create_draft(self.teacher,p)
        for n in range(1,10): self.app.confirm(self.teacher,d['id'],n,1)
        snap=self.app.publish(self.teacher,d['id'],1); room=self.app.create_room(self.teacher,snap['id'],'graded fixture')
        a=self.app.join(room['join_code'],'synthetic participant'); self.app.control(self.teacher,room['id'],'start')
        msg=self.app.message(a['token'],room['id'],'m','I understand your concern and propose a shared criterion.')
        self.app.control(self.teacher,room['id'],'end'); self.app.reflect(a['token'],room['id'],'synthetic reflection')
        f=FeedbackService(self.app); ev=f.evidence(self.teacher,room['id'],a['participant_id'],msg['id'],'shared criterion')
        context=f.assessment_context(self.teacher,room['id'],a['participant_id']); value=self.assessment_payload(context)
        value['dimensions'][1].update(status='OBSERVED',level=4,evidence_ids=[ev['id']])
        return f,room,a,value

    def test_empty_anchor_values_cannot_authorize_observed_level(self):
        f,r,a,value=self.graded_case({str(n):None for n in range(1,5)})
        with self.assertRaises(DomainError): f.record_assessment(self.teacher,r['id'],a['participant_id'],value)

    def test_report_is_stale_when_independent_baseline_is_superseded(self):
        import copy
        f,r,a,value=self.graded_case(); baseline=f.record_assessment(self.teacher,r['id'],a['participant_id'],value)
        body={'dimension_details':copy.deepcopy(baseline['dimensions']),'strength':None,'priority_improvement':None,'limitations':['synthetic']}
        released=f.stage_report(self.teacher,r['id'],'PERSONAL',body,participant_id=a['participant_id']); f.publish_report(self.teacher,released['id'])
        draft=f.stage_report(self.teacher,r['id'],'PERSONAL',body,participant_id=a['participant_id'])
        changed=copy.deepcopy(value); changed['dimensions'][1]['level']=1
        f.record_assessment(self.teacher,r['id'],a['participant_id'],changed)
        with self.assertRaises(DomainError): f.publish_report(self.teacher,draft['id'])
        with self.assertRaises(DomainError): f.get_report(a['token'],released['id'])

    def test_unobserved_details_must_also_copy_the_independent_baseline(self):
        import copy
        f,r,a,value=self.graded_case(); baseline=f.record_assessment(self.teacher,r['id'],a['participant_id'],value)
        details=copy.deepcopy(baseline['dimensions']); details[2]['status']='INSUFFICIENT_OPPORTUNITY'
        with self.assertRaises(DomainError): f.stage_report(self.teacher,r['id'],'PERSONAL',{'dimension_details':details},participant_id=a['participant_id'])

    def test_personal_report_is_stale_after_goal_edit(self):
        f,r,a,value=self.graded_case(); baseline=f.record_assessment(self.teacher,r['id'],a['participant_id'],value)
        report=f.stage_report(self.teacher,r['id'],'PERSONAL',{'dimension_details':baseline['dimensions']},participant_id=a['participant_id'])
        f.publish_report(self.teacher,report['id'])
        self.app.set_goal(a['token'],r['id'],'changed goal')
        with self.assertRaises(DomainError):f.get_report(a['token'],report['id'])
        self.app.set_goal(a['token'],r['id'],'')
        with self.assertRaises(DomainError):f.get_report(a['token'],report['id'])

    def test_synthesis_cannot_invent_judgment_outside_independent_baseline(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion();self.app.reflect(a['token'],r['id'],'self reflection')
        f=FeedbackService(self.app);ev=f.evidence(self.teacher,r['id'],a['participant_id'],m['id'],'批准权限')
        cx=f.assessment_context(self.teacher,r['id'],a['participant_id']);baseline=f.record_assessment(self.teacher,r['id'],a['participant_id'],self.assessment_payload(cx))
        body={'dimension_details':baseline['dimensions'],'strength':{'text':'new diagnosis absent from baseline','evidence_ids':[ev['id']],'limitations':[]},'priority_improvement':None}
        with self.assertRaises(DomainError):f.stage_report(self.teacher,r['id'],'PERSONAL',body,participant_id=a['participant_id'])

    def test_group_report_stales_when_verified_evidence_changes(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion();f=FeedbackService(self.app)
        report=f.stage_report(self.teacher,r['id'],'GROUP',{'submission_version':None,'summary':'limited evidence','evidence_ids':[],'limitations':[]})
        f.publish_report(self.teacher,report['id'])
        f.evidence(self.teacher,r['id'],a['participant_id'],m['id'],'批准权限')
        with self.assertRaises(DomainError):f.get_report(self.teacher,report['id'])

    def test_dimension_detail_cannot_bypass_selection_or_evidence(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); f=FeedbackService(self.app); self.app.reflect(a['token'],r['id'],'我的自评')
        for dimension in ['C6','C2']:
            with self.subTest(dimension=dimension), self.assertRaises(DomainError):
                f.stage_report(self.teacher,r['id'],'PERSONAL',{'dimension_details':[{'dimension':dimension,'level':4,'judgment':'Excellent without evidence'}]},participant_id=a['participant_id'])

    def test_report_cannot_reference_fake_evidence_or_invent_total_score(self):
        from groupmate.feedback import FeedbackService
        r,a,b,m=self.discussion(); f=FeedbackService(self.app)
        for body in [{'summary':'优秀','evidence_ids':['made-up']},{'summary':'优秀','total_score':99,'evidence_ids':[]}]:
            with self.assertRaises(DomainError): f.stage_report(self.teacher,r['id'],'GROUP',body)
