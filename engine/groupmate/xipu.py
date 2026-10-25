"""Official XIPU workflow API transport. No browser cookies or hidden APIs.

Contract read from platform /platform/doc/api-sdk/api/agent-api-call/
agent-api-documentation, SyncRunAppWorkflow section (2026-10-24).
"""
import json
import urllib.request

ENDPOINT='https://aiagent.xjtlu.edu.cn/api/proxy/api/v1/sync_run_app_workflow'


class XipuError(Exception): pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise XipuError('API_REDIRECT_REJECTED')


class XipuWorkflowClient:
    def __init__(self,api_key,timeout=55):
        if not isinstance(api_key,str) or not api_key.strip(): raise XipuError('API_KEY_REQUIRED')
        self._key=api_key; self.timeout=timeout

    def _request(self,request,timeout):
        try:
            opener=urllib.request.build_opener(NoRedirect())
            with opener.open(request,timeout=timeout) as response:
                raw=response.read(1000001)
                if len(raw)>1000000: raise XipuError('API_RESPONSE_TOO_LARGE')
                return json.loads(raw)
        except XipuError: raise
        except Exception: raise XipuError('API_TRANSPORT_FAILED') from None

    def run(self,value,user_id):
        if not isinstance(user_id,str) or not 1<=len(user_id)<=20: raise XipuError('INVALID_API_USER_ID')
        # InputData is a JSON string containing workflow Start.input (also Str).
        body={'UserID':user_id,'NoDebug':True,'InputData':json.dumps({'input':json.dumps(value,ensure_ascii=False)},ensure_ascii=False)}
        req=urllib.request.Request(ENDPOINT,data=json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Apikey':self._key},method='POST')
        result=self._request(req,self.timeout)
        if not isinstance(result,dict) or result.get('status')!='success': raise XipuError('API_WORKFLOW_NOT_SUCCESSFUL')
        try:
            output=result['output']
            for _ in range(3):
                if isinstance(output,str): output=json.loads(output)
                elif isinstance(output,dict) and set(output)=={'output'}: output=output['output']
                else: break
            if isinstance(output,str): output=json.loads(output)
            if not isinstance(output,dict): raise ValueError()
        except (KeyError,ValueError,TypeError): raise XipuError('API_OUTPUT_INVALID') from None
        return {'value':output,'run_id':result.get('runId'),'cost_ms':result.get('costMs'),'cost_token':result.get('costToken')}
