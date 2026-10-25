"""Version-checked role execution, with durable request deduplication.

No synthetic provider is selected by runtime. Tests inject clearly named fixtures.
"""
from .domain import DomainError, digest
from .xipu import XipuError
from .learning import record_help


class RoleOrchestrator:
    def __init__(self,app,teacher_token,client):
        self.app=app; self.teacher_token=teacher_token; self.client=client
        # A new single-server runtime cannot still own a previous pending call.
        # Keep its id deduplicated; never resubmit an uncertain paid request.
        with app.transaction():
            for pending in app._all('ai_request'):
                if pending['result'] is not None or pending.get('runtime_id')==app.runtime_id: continue
                job=app._get(pending['context_id'])
                if job.get('delivered'):
                    pending['result']={'status':'DELIVERED','event':job['delivered'],'recovered':True}
                else:
                    pending['result']={'status':'INTERRUPTED_UNCERTAIN','error':'PREVIOUS_RUNTIME_ENDED_NO_AUTOMATIC_RETRY'}
                app._put(pending,'ai_request')


    def invite(self,token,room_id,role_id,request_id):
        if not self.client: raise DomainError('AI_NOT_CONNECTED',status=503)
        if not isinstance(request_id,str) or not 1<=len(request_id)<=120: raise DomainError('REQUEST_ID_REQUIRED')
        app=self.app
        # Lock until both authorization and the durable request reservation exist.
        with app.lock:
            with app.transaction():
                room=app._get(room_id); actor=app._member(token,room)
                key='ai-request-'+digest(room_id+':'+actor['actor_id']+':'+request_id)
                existing=[j for j in app._all('ai_request') if j['id']==key]
                if existing:
                    old=existing[0]
                    if old['role_id']!=role_id: raise DomainError('REQUEST_ID_CONFLICT',status=409)
                    return old['result'] or {'status':'RUNNING_OR_UNCERTAIN','request_id':request_id}
                if any(j['room_id']==room_id and j['result'] is None for j in app._all('ai_request')): raise DomainError('AI_JOB_IN_PROGRESS',status=409)
                if not any(e.get('author_type')=='STUDENT' and e['type']=='MESSAGE' for e in room['events']): raise DomainError('STUDENT_MESSAGE_REQUIRED')
            context=app.role_context(self.teacher_token,room_id,role_id)
            with app.transaction():
                request={'id':key,'room_id':room_id,'actor_id':actor['actor_id'],'role_id':role_id,'context_id':context['id'],'runtime_id':app.runtime_id,'result':None}
                app._put(request,'ai_request')
        facts=[{'id':'BASE','text':context['public_case']},{'id':'UNKNOWNS','text':'未知信息：'+'；'.join(context['unknowns'])}]
        facts.extend({'id':e['id'],'text':e['text']} for e in context['public_events'])
        responding=[m['id'] for m in context['messages'] if m['author_type']=='STUDENT'][-1:]
        safe={'room_id':room_id,'snapshot_id':context['snapshot_id'],'epoch':context['epoch'],'context_revision':context['context_seq'],'public_fact_version':context['fact_version'],'assigned_role':{**context['assigned_role'],'role_id':role_id},'public_facts':facts,'public_messages':context['messages'],'responding_to_ids':responding,'remaining_seconds':context['remaining'],'allowed_help':'仅按已确认角色简短追问依据、影响、取舍与权限，不讲标准答案。'}
        with app.lock:packet=app._get(context['snapshot_id'])['packet'];runtime=packet['runtime']
        safe.update(learning_goals=packet['goals'],discussion_questions=packet['questions'],student_task=packet['task'])
        safe['discussion_rules']={k:runtime.get(k) for k in ['difficulty','prompt_intensity','role_pacing','help_policy']}
        safe['allowed_help']=runtime.get('help_policy',safe['allowed_help'])
        if runtime.get('prompt_intensity')=='无额外提示':safe['allowed_help']='只回应角色顾虑和学生询问；不给概念解释、分析步骤或答案线索。'
        try:
            response=self.client.run(safe,digest(room_id+actor['actor_id'])[:20]); value=response['value']
            if any(value.get(k)!=safe[k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']): raise XipuError('MODEL_VERSION_INVALID')
            if value.get('role_id')!=role_id or type(value.get('should_speak')) is not bool: raise XipuError('MODEL_ROLE_INVALID')
            if not isinstance(value.get('responding_to_ids'),list) or not set(value['responding_to_ids']).issubset(set(responding)): raise XipuError('MODEL_REPLY_TARGET_INVALID')
            if not isinstance(value.get('used_fact_ids'),list) or not set(value['used_fact_ids']).issubset({f['id'] for f in facts}): raise XipuError('MODEL_FACT_ID_INVALID')
            if value['should_speak']:
                event=app.deliver_role(self.teacher_token,room_id,context,value['text'])
                with app.transaction():record_help(app,app._get(room_id),event,value.get('help_kind','UNCLASSIFIED'))
                result={'status':'DELIVERED','event':event,'run_id':response.get('run_id'),'cost_ms':response.get('cost_ms')}
            else: result={'status':'NO_RESPONSE_NEEDED','run_id':response.get('run_id')}
        except DomainError as error:
            result={'status':'STALE' if error.code=='STALE_MODEL_RESULT' else 'REJECTED','error':error.code}
        except (XipuError,KeyError,TypeError,ValueError):
            result={'status':'FAILED','error':'AI_CALL_OR_VALIDATION_FAILED'}
        with app.transaction():
            request['result']=result; app._put(request,'ai_request')
        return result
