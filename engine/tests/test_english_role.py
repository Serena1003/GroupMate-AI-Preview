"""Core English role delivery, using the three-sentence live-demo response."""
import unittest
import test_domain as fixtures
from groupmate.manual_roles import ManualRoles

class EnglishRoleFlow(unittest.TestCase):
    setUp=fixtures.DomainTests.setUp
    tearDown=fixtures.DomainTests.tearDown
    publish=fixtures.DomainTests.publish
    room=fixtures.DomainTests.room

    def test_three_sentence_english_role_response_is_preserved(self):
        r,a,b=self.room();self.app.message(a['token'],r['id'],'one','Who can authorise a charging change?')
        service=ManualRoles(self.app);task=service.prepare(self.teacher,r['id'],'maya');value={k:task['input'][k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']}
        text="From the business operations side, I can describe our workflow needs, but I cannot approve any pay-per-use charging change or speak for other departments. My department has not finished a workflow impact review, so any pilot needs a named person responsible for checking how printing changes affect daily tasks before we treat results as business sign-off. I also need the approval boundary made explicit so technical testing is not mistaken for authority to change charging rules."
        value.update(role_id='maya',should_speak=True,text=text,responding_to_ids=task['input']['responding_to_ids'],used_fact_ids=['BASE'],help_kind='CLARIFICATION')
        result=service.import_result(self.teacher,task['id'],value)
        self.assertEqual(result['status'],'DELIVERED');self.assertEqual(result['event']['text'],text)
