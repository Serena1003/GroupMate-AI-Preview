"""Version-bound AI suggestions, explicit teacher decisions and clean activity reuse."""
import copy
from .domain import DomainError,identifier
from .review import unwrap,hashed
from .sources import Sources

FIELDS={'title','goals','case','source','roles','questions','task','assessment','runtime','feedback'}
class Preparation:
    def __init__(self,app):self.app=app;self.sources=Sources(app)
    def library(self,token):
        with self.app.lock:
            actor=self.app._teacher(token)
            return {kind:[{k:v.get(k) for k in (['id','revision','confirmations'] if kind=='draft' else ['id','draft_revision','at'])}|{'title':v['packet']['title']} for v in self.app._all(kind) if v['owner']==actor['actor_id']] for kind in ['draft','snapshot']}
    def reuse(self,token,snapshot_id):
        snapshot=self.app.get_snapshot(token,snapshot_id)
        return self.app.create_draft(token,snapshot['packet'])
    def task(self,token,draft_id,stage,fields,source_ids,requirements):
        with self.app.lock:
            d=self.app.get_draft(token,draft_id)
            if stage not in ['SOURCE','DESIGN'] or not isinstance(fields,list) or not fields or not set(fields)<=FIELDS:raise DomainError('PREP_FIELDS_INVALID')
            if stage=='SOURCE' and set(fields)!={'source','case'}:raise DomainError('SOURCE_FIELDS_REQUIRED')
            if not isinstance(source_ids,list) or len(source_ids)>5 or not isinstance(requirements,dict):raise DomainError('PREP_INPUT_INVALID')
            documents=[self.sources.get(token,sid) for sid in source_ids]
            if len(str(documents))+len(str(d['packet']))>150000:raise DomainError('PREP_INPUT_TOO_LARGE')
            rejected=[p['proposal_patch'] for p in self.app._all('proposal') if p['draft_id']==draft_id and p['decision']=='REJECT']
            tid=identifier('prep-task');binding={'task_id':tid,'draft_id':draft_id,'draft_revision':d['revision'],'stage':stage}
            value={'workflow_binding':binding,'draft_revision':d['revision'],'requested_fields':fields,'requested_nodes':[{'roles':'N4','questions':'N5','task':'N5','assessment':'N6','runtime':'N7','feedback':'N8'}.get(k,k) for k in fields],'source_route':d['packet']['source']['route'],'current_packet':d['packet'],'protected_fields':{k:v for k,v in d['packet'].items() if k not in fields},'source_documents':[{k:s[k] for k in ['id','filename','sha256','spans']} for s in documents],'requirements':requirements,'rejected_proposals':rejected,'output_contract':{'workflow_binding':'原样复制输入同名对象','proposal_patch':'仅requested_fields字段；来源路径保持不变；不改rubric四档原文','limitations':'字符串数组；未知明确列出；无来源不编页码。'}}
            task={'id':tid,'owner':d['owner'],'draft_id':draft_id,'draft_revision':d['revision'],'stage':stage,'fields':fields,'input':copy.deepcopy(value),'input_hash':hashed(value),'status':'AWAITING_RESULT','at':self.app.clock()}
            with self.app.transaction():self.app._put(task,'prep-task')
            return task
    def import_result(self,token,task_id,output):
        with self.app.lock:
            task=self.app._get(task_id);self.app._teacher(token,task['owner']);draft=self.app.get_draft(token,task['draft_id'])
            if draft['revision']!=task['draft_revision']:raise DomainError('PREP_TASK_STALE')
            v=unwrap(output)
            if set(v)!={'workflow_binding','proposal_patch','limitations'} or v['workflow_binding']!=task['input']['workflow_binding']:raise DomainError('PREP_BINDING_MISMATCH')
            patch=v['proposal_patch']
            if not isinstance(patch,dict) or not patch or not set(patch)<=set(task['fields']) or not isinstance(v['limitations'],list) or any(not isinstance(x,str) for x in v['limitations']):raise DomainError('PROPOSAL_SCOPE_INVALID')
            if 'assessment' in patch:
                if not isinstance(patch['assessment'],dict) or patch['assessment'].get('rubric',draft['packet']['assessment'].get('rubric'))!=draft['packet']['assessment'].get('rubric'):raise DomainError('RUBRIC_CHANGE_FORBIDDEN')
                patch['assessment']={**draft['packet']['assessment'],**patch['assessment']}
            if 'source' in patch:
                if not isinstance(patch['source'],dict) or patch['source'].get('route')!=draft['packet']['source']['route']:raise DomainError('SOURCE_ROUTE_CHANGED')
                if patch['source']['route']=='TEXTBOOK_NEW' and not patch['source'].get('simulation'):raise DomainError('SIMULATION_LABEL_REQUIRED')
            existing=[p for p in self.app._all('proposal') if p['task_id']==task_id]
            if existing:
                if existing[0]['output_hash']!=hashed(v):raise DomainError('PROPOSAL_ALREADY_IMPORTED')
                return existing[0]
            proposal={'id':identifier('proposal'),'owner':task['owner'],'task_id':task_id,'draft_id':task['draft_id'],'base_revision':task['draft_revision'],'proposal_patch':copy.deepcopy(patch),'limitations':v['limitations'],'output_hash':hashed(v),'decision':'PENDING','at':self.app.clock(),'provenance':'MANUAL_NATIVE_OUTPUT_NOT_AUTOMATICALLY_ATTESTED'}
            with self.app.transaction():self.app._put(proposal,'proposal')
            return proposal
    def decide(self,token,proposal_id,decision):
        with self.app.lock:
            p=self.app._get(proposal_id);self.app._teacher(token,p['owner'])
            if p['decision']!='PENDING' or decision not in ['ACCEPT','REJECT']:raise DomainError('PROPOSAL_ALREADY_DECIDED')
            if decision=='ACCEPT':self.app.update_draft(token,p['draft_id'],p['base_revision'],p['proposal_patch'])
            with self.app.transaction():p.update(decision=decision,decided_at=self.app.clock());self.app._put(p,'proposal')
            return p
