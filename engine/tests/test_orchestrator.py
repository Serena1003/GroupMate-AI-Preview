import threading
import unittest
import test_domain as fixtures


class OrchestratorTests(unittest.TestCase):
    setUp=fixtures.DomainTests.setUp
    tearDown=fixtures.DomainTests.tearDown
    publish=fixtures.DomainTests.publish
    room=fixtures.DomainTests.room
    def test_role_call_uses_whitelist_and_preserves_real_result(self):
        from groupmate.orchestrator import RoleOrchestrator
        r,a,b=self.room(); self.app.set_goal(a['token'],r['id'],'PRIVATE_GOAL')
        self.app.message(a['token'],r['id'],'m','请Maya说明需要哪些业务确认？')
        received=[]
        class TestOnlyClient:
            def run(inner,value,user):
                received.append(value)
                return {'value':{**{k:value[k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']},'role_id':'maya','should_speak':True,'text':'请先说明本部门的业务影响。','responding_to_ids':value['responding_to_ids'],'used_fact_ids':['BASE'],'help_kind':'追问依据'},'run_id':'test-fixture','cost_ms':12}
        o=RoleOrchestrator(self.app,self.teacher,TestOnlyClient())
        first=o.invite(a['token'],r['id'],'maya','request-1')
        second=o.invite(a['token'],r['id'],'maya','request-1')
        self.assertEqual(first,second); self.assertEqual(len(received),1)
        self.assertNotIn('PRIVATE_GOAL',str(received)); self.assertNotIn('延期两年',str(received)); self.assertNotIn('按使用量计费',str(received))
        self.assertEqual(first['event']['author_type'],'AI')

    def test_pause_during_real_call_boundary_discards_old_response(self):
        from groupmate.orchestrator import RoleOrchestrator
        r,a,b=self.room(); self.app.message(a['token'],r['id'],'m','请说明影响')
        app=self.app; teacher=self.teacher
        class TestOnlyClient:
            def run(inner,value,user):
                app.control(teacher,r['id'],'pause')
                return {'value':{**{k:value[k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']},'role_id':'maya','should_speak':True,'text':'这条不应送达。','responding_to_ids':value['responding_to_ids'],'used_fact_ids':['BASE']}}
        o=RoleOrchestrator(self.app,self.teacher,TestOnlyClient())
        out=o.invite(a['token'],r['id'],'maya','request-1')
        self.assertEqual(out['status'],'STALE')
        self.assertFalse([m for m in self.app.room_view(a['token'],r['id'])['events'] if m.get('author_type')=='AI'])

    def test_interrupted_request_reconciled_on_restart_without_replaying(self):
        from groupmate.orchestrator import RoleOrchestrator
        from groupmate.domain import Classroom
        r,a,b=self.room(); self.app.message(a['token'],r['id'],'m','请说明影响')
        class InterruptedClient:
            def run(inner,value,user): raise SystemExit('simulated process exit')
        o=RoleOrchestrator(self.app,self.teacher,InterruptedClient())
        with self.assertRaises(SystemExit): o.invite(a['token'],r['id'],'maya','crashed')
        self.app.close(); self.app=Classroom(self.db,clock=lambda:self.now)
        class NoSpeakClient:
            def run(inner,value,user):
                return {'value':{**{k:value[k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']},'role_id':'maya','should_speak':False,'responding_to_ids':value['responding_to_ids'],'used_fact_ids':[]}}
        o=RoleOrchestrator(self.app,self.teacher,NoSpeakClient())
        self.assertEqual(o.invite(a['token'],r['id'],'maya','crashed')['status'],'INTERRUPTED_UNCERTAIN')
        self.assertEqual(o.invite(a['token'],r['id'],'maya','new-explicit-request')['status'],'NO_RESPONSE_NEEDED')

    def test_wrong_returned_version_rejected_before_delivery(self):
        from groupmate.orchestrator import RoleOrchestrator
        r,a,b=self.room(); self.app.message(a['token'],r['id'],'m','请说明影响')
        class TestOnlyClient:
            def run(inner,value,user):
                return {'value':{**{k:value[k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']},'epoch':999,'role_id':'maya','should_speak':True,'text':'不应送达','responding_to_ids':value['responding_to_ids'],'used_fact_ids':['BASE']}}
        result=RoleOrchestrator(self.app,self.teacher,TestOnlyClient()).invite(a['token'],r['id'],'maya','wrong-version')
        self.assertEqual(result['status'],'FAILED')

    def test_missing_connector_never_creates_ai_message(self):
        from groupmate.orchestrator import RoleOrchestrator
        from groupmate.domain import DomainError
        r,a,b=self.room()
        o=RoleOrchestrator(self.app,self.teacher,None)
        with self.assertRaises(DomainError): o.invite(a['token'],r['id'],'maya','request-1')
