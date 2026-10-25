"""Actual native WF03 results can enter a running room without API transport."""
from .domain import DomainError,identifier
from .review import unwrap,hashed
from .learning import record_help

class ManualRoles:
    def __init__(self,app):self.app=app
    def prepare(self,token,room_id,role_id):
        with self.app.lock:
            context=self.app.role_context(token,room_id,role_id);room=self.app._get(room_id)
            if not any(m['author_type']=='STUDENT' for m in context['messages']):raise DomainError('STUDENT_MESSAGE_REQUIRED')
            facts=[{'id':'BASE','text':context['public_case']},{'id':'UNKNOWNS','text':'未知信息：'+'；'.join(context['unknowns'])}]+[{'id':e['id'],'text':e['text']} for e in context['public_events']]
            packet=self.app._get(room['snapshot_id'])['packet']
            safe={'room_id':room_id,'snapshot_id':context['snapshot_id'],'epoch':context['epoch'],'context_revision':context['context_seq'],'public_fact_version':context['fact_version'],'assigned_role':{**context['assigned_role'],'role_id':role_id},'public_facts':facts,'public_messages':context['messages'],'responding_to_ids':[m['id'] for m in context['messages'] if m['author_type']=='STUDENT'][-1:],'remaining_seconds':context['remaining'],'allowed_help':packet['runtime'].get('help_policy','角色内简短追问、澄清；不替学生回答。')}
            safe.update(learning_goals=packet['goals'],discussion_questions=packet['questions'],student_task=packet['task'])
            safe['discussion_rules']={k:packet['runtime'].get(k) for k in ['difficulty','prompt_intensity','role_pacing','help_policy']}
            if packet['runtime'].get('prompt_intensity')=='无额外提示':safe['allowed_help']='只回应角色顾虑和学生询问；不给概念解释、分析步骤或答案线索。'
            task={'id':identifier('manual-role'),'owner':room['owner'],'room_id':room_id,'context':context,'input':safe,'result':None}
            with self.app.transaction():self.app._put(task,'manual-role')
            return task
    def import_result(self,token,task_id,output):
        with self.app.lock:
            task=self.app._get(task_id);self.app._teacher(token,task['owner']);v=unwrap(output);safe=task['input'];checksum=hashed(v)
            if task['result']:
                if task['output_hash']!=checksum:raise DomainError('ROLE_TASK_ALREADY_IMPORTED')
                return task['result']
            if any(v.get(k)!=safe[k] for k in ['room_id','snapshot_id','epoch','context_revision','public_fact_version']) or v.get('role_id')!=safe['assigned_role']['role_id'] or type(v.get('should_speak')) is not bool:raise DomainError('ROLE_VERSION_OR_ID_INVALID')
            for key,allowed in [('used_fact_ids',{f['id'] for f in safe['public_facts']}),('responding_to_ids',set(safe['responding_to_ids']))]:
                if not isinstance(v.get(key),list) or any(not isinstance(x,str) or x not in allowed for x in v[key]):raise DomainError('ROLE_REFERENCE_INVALID')
            if not isinstance(v.get('help_kind','NONE'),str) or len(v.get('help_kind','NONE'))>80:raise DomainError('HELP_INVALID')
            if v['should_speak']:
                event=self.app.deliver_role(token,task['room_id'],task['context'],v.get('text'))
                with self.app.transaction():record_help(self.app,self.app._get(task['room_id']),event,v.get('help_kind','UNCLASSIFIED'))
                result={'status':'DELIVERED','event':event,'transport':'MANUAL_NATIVE_WORKFLOW'}
            else:
                # Check freshness even for a no-response decision.
                room=self.app._get(task['room_id'])
                if room['state']!='RUNNING' or room['epoch']!=safe['epoch'] or len(room['events'])!=safe['context_revision']:raise DomainError('STALE_MODEL_RESULT')
                result={'status':'NO_RESPONSE_NEEDED','transport':'MANUAL_NATIVE_WORKFLOW'}
            with self.app.transaction():task.update(result=result,output_hash=checksum);self.app._put(task,'manual-role')
            return result
