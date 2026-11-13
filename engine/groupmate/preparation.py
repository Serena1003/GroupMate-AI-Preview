"""Version-bound AI suggestions, explicit teacher decisions and clean activity reuse."""
import copy
import re
from .domain import DomainError,identifier
from .review import unwrap,hashed
from .sources import Sources

FIELDS={'title','goals','case','source','roles','questions','task','assessment','runtime','feedback'}
def case_headings(documents):
    """Locate explicit case headings in supplied text; no inferred case facts."""
    found=[]
    pattern=re.compile(r'^\s*(?:mini[\s\-–—‐‑]*case|case)\s+(\d+(?:\.\d+)?)[:.\s–—-]+([^\n]+)',re.I|re.M)
    for document in documents:
        for span in document['spans']:
            for match in pattern.finditer(span['text']):
                found.append({'title':match.group(0).strip(),'source_id':document['id'],
                              'filename':document['filename'],'heading_span_id':span['span_id'],
                              'heading_pdf_page':span.get('pdf_page'),
                              'opening_excerpt':span['text'][match.start():match.start()+1000]})
    return found

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
            course=d['packet'].get('course_context',{})
            course_ids=course.get('source_ids',[])
            if not isinstance(course_ids,list) or len(course_ids)>2:raise DomainError('COURSE_CONTEXT_INVALID')
            course_documents=[self.sources.get(token,sid) for sid in course_ids]
            rejected=[p['proposal_patch'] for p in self.app._all('proposal') if p['draft_id']==draft_id and p['decision']=='REJECT']
            tid=identifier('prep-task');binding={'task_id':tid,'draft_id':draft_id,'draft_revision':d['revision'],'stage':stage}
            value={'workflow_binding':binding,'draft_revision':d['revision'],'requested_fields':fields,'requested_nodes':[{'roles':'N4','questions':'N5','task':'N5','assessment':'N6','runtime':'N7','feedback':'N8'}.get(k,k) for k in fields],'source_route':d['packet']['source']['route'],'current_packet':d['packet'],'protected_fields':{k:v for k,v in d['packet'].items() if k not in fields},'source_documents':[{k:s[k] for k in ['id','filename','sha256','spans']} for s in documents],'requirements':requirements,'rejected_proposals':rejected,'output_contract':{'workflow_binding':'原样复制输入同名对象','proposal_patch':'Only requested_fields. Preserve source route and rubric anchors. If the selected material cannot support a proposal, return an empty object and explain the missing material in limitations.','limitations':'Array of English strings. Explain unknowns and missing case text; never invent page references.'}}
            if stage=='SOURCE':
                # Source selection does not need two copies of the full competency rubric.
                packet=d['packet']
                value['current_packet']={k:copy.deepcopy(packet[k]) for k in ['title','goals','source','case','runtime']}
                value['protected_fields']=list(value['protected_fields'])
                value={'workflow_binding':binding,'source_case_sections':case_headings(documents),
                       'source_processing_rule':"Read source_documents[].spans[].text as the actual uploaded material. TEACHER_CASE includes teacher-selected textbook excerpts; do not reject them because of their filename or authorship. An empty current_packet.case is the destination to fill, not evidence that uploaded sources are absent. If several real cases are present and no title is specified, propose one suitable case for teacher review, identify its title and source pages, and list the other available cases as alternatives in limitations. Do not claim the teacher already selected or approved your proposed case.",
                       **{k:v for k,v in value.items() if k!='workflow_binding'}}
                value['case_completion_contract']={
                    'case_schema':{'public':'The complete student-facing case, not an abstract or an opening excerpt.','teacher_only':'Separate teacher notes or an empty string.','unknowns':['Only genuine unresolved information.']},
                    'rule':'Return the complete scenario in one response: context, stakeholders, relevant facts and constraints, decision to discuss. Preserve all supplied case facts and the ending. Do not use ellipses, placeholders, to be continued, or refer students to an omitted attachment. For TEACHER_CASE, retain the supplied case in full unless the teacher explicitly requests adaptation. Do not fabricate missing pages or pretend incomplete material is complete; explain missing material in limitations.',
                    'source_rule':'Copy current_packet.source.route exactly. Cite the actual source span IDs used. Keep classroom additions in source.simulation and teacher notes out of case.public.'}
                value['output_contract']['source_evidence']='For a case extracted from uploaded documents, source.source_span_ids must cite actual supplied span_id values and source.references must identify the real source. A statement that case text is missing is a limitation, not a public case. If genuinely unable to propose a case, return proposal_patch={} with limitations.'
            value['course_context']={'title':course.get('title',''),'teacher_summary':course.get('summary',''),'documents':[{k:doc[k] for k in ['id','filename','spans']} for doc in course_documents],'rule':'Use the module specification or handbook to align learning goals and discussion tasks. Course context is not case evidence; do not invent case facts from a syllabus.'}
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
            if not isinstance(patch,dict) or not set(patch)<=set(task['fields']) or not isinstance(v['limitations'],list) or any(not isinstance(x,str) for x in v['limitations']):raise DomainError('PROPOSAL_SCOPE_INVALID')
            if not patch and not any(v['limitations']):raise DomainError('PROPOSAL_EXPLANATION_REQUIRED')
            if 'case' in patch:
                case=patch['case']
                if not isinstance(case,dict) or not isinstance(case.get('public'),str) or not case['public'].strip():raise DomainError('CASE_CONTENT_REQUIRED')
                patch['case']={**draft['packet']['case'],**case}
            self._check_source_case(task,patch)
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
            proposal={'id':identifier('proposal'),'owner':task['owner'],'task_id':task_id,'draft_id':task['draft_id'],'base_revision':task['draft_revision'],'proposal_patch':copy.deepcopy(patch),'limitations':v['limitations'],'output_hash':hashed(v),'decision':'PENDING' if patch else 'NOT_APPLICABLE','status':'PROPOSED' if patch else 'NO_CHANGES','at':self.app.clock(),'provenance':'MANUAL_NATIVE_OUTPUT_NOT_AUTOMATICALLY_ATTESTED'}
            with self.app.transaction():self.app._put(proposal,'proposal')
            return proposal
    def _check_source_case(self,task,patch):
        if task['stage']!='SOURCE' or 'case' not in patch or not task['input']['source_documents']:return
        source=patch.get('source',{})
        span_ids=source.get('source_span_ids',[]) if isinstance(source,dict) else []
        allowed={span['span_id'] for doc in task['input']['source_documents'] for span in doc['spans']}
        if not isinstance(span_ids,list) or not span_ids or any(not isinstance(sid,str) or sid not in allowed for sid in span_ids) or not source.get('references'):
            raise DomainError('SOURCE_CASE_EVIDENCE_REQUIRED')
    def decide(self,token,proposal_id,decision):
        with self.app.lock:
            p=self.app._get(proposal_id);self.app._teacher(token,p['owner'])
            if decision in ['ACCEPT','REJECT'] and p['decision']==decision:return p
            if p['decision']!='PENDING' or decision not in ['ACCEPT','REJECT']:raise DomainError('PROPOSAL_ALREADY_DECIDED')
            if decision=='ACCEPT':
                self._check_source_case(self.app._get(p['task_id']),p['proposal_patch'])
                self.app.update_draft(token,p['draft_id'],p['base_revision'],p['proposal_patch'])
            with self.app.transaction():p.update(decision=decision,decided_at=self.app.clock());self.app._put(p,'proposal')
            return p
