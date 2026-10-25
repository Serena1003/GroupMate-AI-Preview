import unittest
import test_domain as fixtures
from groupmate.domain import DomainError
from groupmate.review import ReviewWorkspace
try:
    from groupmate.learning import Learning
    from groupmate.manual_roles import ManualRoles
    from groupmate.operations import Operations
except ImportError:
    Learning=ManualRoles=Operations=None

class ProductFlowTests(unittest.TestCase):
    setUp=fixtures.DomainTests.setUp
    tearDown=fixtures.DomainTests.tearDown
    publish=fixtures.DomainTests.publish
    room=fixtures.DomainTests.room
    def test_manual_role_real_output_versions_and_all_member_help_audience(self):
        self.assertIsNotNone(ManualRoles)
        r,a,b=self.room();self.app.message(a['token'],r['id'],'one','为什么需要确认授权？')
        service=ManualRoles(self.app);task=service.prepare(self.teacher,r['id'],'maya');v={k:task['input'][k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']}
        v.update(role_id='maya',should_speak=True,text='请说明谁有权批准业务规则，以及哪些影响仍需确认。',responding_to_ids=task['input']['responding_to_ids'],used_fact_ids=['BASE'],help_kind='CLARIFICATION')
        with self.assertRaises(DomainError):service.import_result(b['token'],task['id'],v)
        result=service.import_result(self.teacher,task['id'],v)
        self.assertEqual(result['event']['author_type'],'AI')
        self.assertEqual(set(self.app._all('help-exposure')[0]['audience_ids']),{a['participant_id'],b['participant_id']})
        self.assertEqual(service.import_result(self.teacher,task['id'],v)['event']['id'],result['event']['id'])
        stale=service.prepare(self.teacher,r['id'],'maya');self.app.control(self.teacher,r['id'],'pause')
        with self.assertRaises(DomainError):service.import_result(self.teacher,stale['id'],v)
    def test_strategy_and_next_action_are_private_and_do_not_change_observer(self):
        self.assertIsNotNone(Learning)
        r,a,b=self.room();s=Learning(self.app)
        s.save(a['token'],r['id'],'strategy','PRIVATE_STRATEGY')
        self.assertNotIn('PRIVATE_STRATEGY',str(self.app.room_view(b['token'],r['id'])))
        self.app.control(self.teacher,r['id'],'end');before=ReviewWorkspace(self.app).feedback.assessment_context(self.teacher,r['id'],a['participant_id'])
        self.app.reflect(a['token'],r['id'],'Synthetic reflection');s.save(a['token'],r['id'],'next_action','PRIVATE_NEXT_ACTION')
        self.assertEqual(before,ReviewWorkspace(self.app).feedback.assessment_context(self.teacher,r['id'],a['participant_id']))
        self.assertIn('PRIVATE_NEXT_ACTION',str(s.view(a['token'],r['id'])))
        self.assertNotIn('PRIVATE_NEXT_ACTION',str(s.view(b['token'],r['id'])))
    def test_export_restore_is_credentials_free_owned_and_non_destructive(self):
        self.assertIsNotNone(Operations)
        r,a,b=self.room();self.app.control(self.teacher,r['id'],'end');s=Operations(self.app)
        bundle=s.export_room(self.teacher,r['id'])
        self.assertNotIn(a['token'],str(bundle));self.assertNotIn('join_code',str(bundle));self.assertNotIn('auth-',str(bundle))
        with self.assertRaises(DomainError):s.export_room(a['token'],r['id'])
        archive=s.restore(self.teacher,bundle)
        self.assertEqual(archive['status'],'READ_ONLY_RESTORED_COPY');self.assertEqual(self.app._get(r['id'])['id'],r['id'])
        self.assertNotEqual(archive['id'],r['id'])
    def test_public_help_reaches_silent_member_context_and_withdrawal_stops_new_posts(self):
        self.assertIsNotNone(Learning)
        r,a,b=self.room();s=Learning(self.app)
        s.help(self.teacher,r['id'],'请区分技术认可和业务批准。','CONCEPT')
        self.app.control(self.teacher,r['id'],'end')
        context=ReviewWorkspace(self.app).feedback.assessment_context(self.teacher,r['id'],b['participant_id'])
        self.assertEqual(context['help_exposures'][0]['kind'],'CONCEPT')
        r,a,b=self.room();s.save(a['token'],r['id'],'participation','WITHDRAWN')
        with self.assertRaises(DomainError):self.app.message(a['token'],r['id'],'after-exit','should not send')
        s.save(a['token'],r['id'],'participation','ACTIVE');self.app.message(a['token'],r['id'],'after-return','Returned voluntarily')
