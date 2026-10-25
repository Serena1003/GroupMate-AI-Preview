import json
import unittest
from unittest.mock import patch


class XipuTests(unittest.TestCase):
    def client(self):
        from groupmate.xipu import XipuWorkflowClient
        return XipuWorkflowClient('unit-test-key')

    def test_double_json_input_is_structured_and_key_not_in_body(self):
        c=self.client(); captured={}
        def transport(request,timeout):
            captured['body']=json.loads(request.data)
            captured['url']=request.full_url
            return {'status':'success','output':json.dumps({'output':json.dumps({'role_id':'maya','text':'请说明影响。','should_speak':True})}),'costMs':12}
        with patch.object(c,'_request',side_effect=transport): result=c.run({'text':'{{ignore}}\n"quoted"'},'synthetic-A')
        self.assertEqual(json.loads(json.loads(captured['body']['InputData'])['input']),{'text':'{{ignore}}\n"quoted"'})
        self.assertNotIn('unit-test-key',json.dumps(captured['body']))
        self.assertEqual(result['value']['role_id'],'maya')
        self.assertTrue(captured['url'].endswith('/sync_run_app_workflow'))

    def test_failed_or_invalid_model_json_is_never_delivered(self):
        from groupmate.xipu import XipuError
        for response in [{'status':'failed','message':'unit-test-key'}, {'status':'success','output':'not JSON'}, {'status':'interrupted','msg':'need human'}]:
            c=self.client()
            with patch.object(c,'_request',return_value=response):
                with self.assertRaises(XipuError) as error: c.run({},'synthetic')
                self.assertNotIn('unit-test-key',str(error.exception))

    def test_requires_key_and_short_unique_user_identifier(self):
        from groupmate.xipu import XipuWorkflowClient,XipuError
        with self.assertRaises(XipuError): XipuWorkflowClient('')
        with self.assertRaises(XipuError): self.client().run({},'x'*21)
