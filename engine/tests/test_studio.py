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
