import base64
import unittest
import test_domain as fixtures
from groupmate.domain import DomainError
try:
    from groupmate.sources import Sources
    from groupmate.preparation import Preparation
except ImportError:
    Sources=Preparation=None

class StudioTests(unittest.TestCase):
    setUp=fixtures.DomainTests.setUp
    tearDown=fixtures.DomainTests.tearDown
    publish=fixtures.DomainTests.publish
    room=fixtures.DomainTests.room
    def test_private_source_upload_has_real_spans_and_failure_is_explicit(self):
        self.assertIsNotNone(Sources)
        service=Sources(self.app)
        source=service.upload(self.teacher,'case.md',base64.b64encode('真实案例：先确认授权。'.encode()).decode(),1,1)
        self.assertEqual(source['spans'][0]['text'],'真实案例：先确认授权。')
        self.assertEqual(source['status'],'TEXT_EXTRACTED_NOT_CASE_VERIFIED')
        other=self.app.bootstrap_teacher('other-owner')
        with self.assertRaises(DomainError):service.get(other,source['id'])
        with self.assertRaises(DomainError):service.upload(self.teacher,'bad.pdf',base64.b64encode(b'bad').decode(),1,2)
    def test_proposal_accept_is_scoped_reviewed_and_old_revision_rejected(self):
        self.assertIsNotNone(Preparation)
        service=Preparation(self.app);draft=self.app.create_draft(self.teacher,fixtures.packet())
        task=service.task(self.teacher,draft['id'],'DESIGN',['roles'],[],{})
        body={'workflow_binding':task['input']['workflow_binding'],'proposal_patch':{'roles':fixtures.packet()['roles']},'limitations':[]}
        proposal=service.import_result(self.teacher,task['id'],body)
        self.assertEqual(self.app.get_draft(self.teacher,draft['id'])['revision'],1)
        self.assertEqual(service.decide(self.teacher,proposal['id'],'REJECT')['decision'],'REJECT')
        with self.assertRaises(DomainError):service.decide(self.teacher,proposal['id'],'ACCEPT')
        newer=service.task(self.teacher,draft['id'],'DESIGN',['roles'],[],{})
        self.assertTrue(newer['input']['rejected_proposals'])
        body['workflow_binding']=newer['input']['workflow_binding'];body['proposal_patch']['task']=['unrequested override']
        with self.assertRaises(DomainError):service.import_result(self.teacher,newer['id'],body)
        body['proposal_patch'].pop('task');p=service.import_result(self.teacher,newer['id'],body)
        self.app.update_draft(self.teacher,draft['id'],1,{'title':'teacher edit'})
        with self.assertRaises(DomainError):service.decide(self.teacher,p['id'],'ACCEPT')
    def test_snapshot_reuse_contains_no_student_data(self):
        self.assertIsNotNone(Preparation)
        s=self.publish();service=Preparation(self.app)
        copy=service.reuse(self.teacher,s['id'])
        self.assertEqual(copy['packet'],s['packet']);self.assertEqual(copy['confirmations'],{})
        self.assertNotIn('members',copy);self.assertNotEqual(copy['id'],s['draft_id'])

    def test_missing_case_returns_explanation_without_an_adoptable_patch(self):
        service=Preparation(self.app);draft=self.app.create_draft(self.teacher,fixtures.packet())
        task=service.task(self.teacher,draft['id'],'SOURCE',['source','case'],[],{})
        output={'workflow_binding':task['input']['workflow_binding'],'proposal_patch':{},'limitations':['The selected materials contain a syllabus and contents pages, not a complete case.']}
        result=service.import_result(self.teacher,task['id'],output)
        self.assertEqual(result['status'],'NO_CHANGES')
        self.assertEqual(result['decision'],'NOT_APPLICABLE')
        self.assertEqual(self.app.get_draft(self.teacher,draft['id'])['revision'],draft['revision'])
        with self.assertRaises(DomainError):service.decide(self.teacher,result['id'],'ACCEPT')

    def test_uploaded_textbook_case_is_explicit_and_requires_real_source_refs(self):
        service=Preparation(self.app);draft=self.app.create_draft(self.teacher,fixtures.packet())
        raw='Mini-case 4 Eat the packaging\nA project develops edible wrapping with consumers and professional kitchens.'
        source=Sources(self.app).upload(self.teacher,'textbook-excerpt.txt',base64.b64encode(raw.encode()).decode())
        task=service.task(self.teacher,draft['id'],'SOURCE',['source','case'],[source['id']],{})
        self.assertEqual(task['input']['source_case_sections'][0]['title'],'Mini-case 4 Eat the packaging')
        self.assertNotIn('assessment',task['input']['current_packet'])
        patch={'source':{'route':'TEACHER_CASE','references':[],'source_span_ids':[]},'case':{'public':'No case was supplied.','teacher_only':'','unknowns':[]}}
        out={'workflow_binding':task['input']['workflow_binding'],'proposal_patch':patch,'limitations':[]}
        with self.assertRaisesRegex(DomainError,'SOURCE_CASE_EVIDENCE_REQUIRED'):service.import_result(self.teacher,task['id'],out)
        patch['source'].update(references=['textbook-excerpt.txt'],source_span_ids=[source['spans'][0]['span_id']])
        patch['case']['public']='An edible-wrapping project needs to engage consumers and professional kitchens.'
        result=service.import_result(self.teacher,task['id'],out)
        self.assertEqual(result['decision'],'PENDING')
        self.assertEqual(self.app.get_draft(self.teacher,draft['id'])['revision'],1)

    def test_accepting_same_proposal_twice_does_not_reapply_patch(self):
        service=Preparation(self.app);draft=self.app.create_draft(self.teacher,fixtures.packet())
        task=service.task(self.teacher,draft['id'],'DESIGN',['title'],[],{})
        p=service.import_result(self.teacher,task['id'],{'workflow_binding':task['input']['workflow_binding'],'proposal_patch':{'title':'Accepted title'},'limitations':[]})
        first=service.decide(self.teacher,p['id'],'ACCEPT')
        second=service.decide(self.teacher,p['id'],'ACCEPT')
        self.assertEqual(first,second)
        current=self.app.get_draft(self.teacher,draft['id'])
        self.assertEqual(current['revision'],2)
        self.assertEqual(current['packet']['title'],'Accepted title')
        with self.assertRaises(DomainError):service.decide(self.teacher,p['id'],'REJECT')
