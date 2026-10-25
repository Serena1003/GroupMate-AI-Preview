"""Teacher review and manual native-workflow bridge, independent of API access."""
import copy
import json
from .domain import DomainError, digest, identifier
from .feedback import FeedbackService
from .observer import strings
from .class_reports import ClassReports
from .assessment_reviews import adopted


def hashed(value):
    return digest(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')))


def unwrap(value):
    for _ in range(6):
        if isinstance(value,str):
            try: value=json.loads(value)
            except ValueError: raise DomainError('WORKFLOW_JSON_REQUIRED')
        elif isinstance(value,dict) and set(value)=={'output'}: value=value['output']
        else: break
    if not isinstance(value,dict): raise DomainError('WORKFLOW_OBJECT_REQUIRED')
    return value


def check_report_body(kind,value):
    if not isinstance(value,dict): raise DomainError('INVALID_REPORT_BODY')
    group={'submission_version','summary','reasoning','disagreement_handling','knowledge_strengths_difficulties','evidence_ids','limitations'}
    personal={'goal_review','self_reflection_comparison','strength','priority_improvement','next_action','dimension_details','knowledge_observations','limitations'}
    if set(value)!=(group if kind=='GROUP' else personal) or not strings(value.get('limitations')): raise DomainError('REPORT_BODY_FIELDS')
    if kind=='GROUP':
        if any(not isinstance(value[k],str) for k in ['summary','reasoning','disagreement_handling','knowledge_strengths_difficulties']) or not value['summary'].strip() or not strings(value['evidence_ids']): raise DomainError('REPORT_BODY_TYPES')
    else:
        if any(not isinstance(value[k],str) for k in ['goal_review','self_reflection_comparison','next_action']) or not isinstance(value['dimension_details'],list) or len(value['dimension_details'])!=6 or not isinstance(value['knowledge_observations'],list): raise DomainError('REPORT_BODY_TYPES')
        for k in ['strength','priority_improvement']:
            item=value[k]
            if item is not None and (not isinstance(item,dict) or set(item)!={'text','evidence_ids','limitations'} or not isinstance(item['text'],str) or not item['text'].strip() or not strings(item['evidence_ids']) or not item['evidence_ids'] or not strings(item['limitations'])): raise DomainError('REPORT_JUDGMENT_FIELDS')


class ReviewWorkspace:
    def __init__(self,app): self.app=app; self.feedback=FeedbackService(app); self.classes=ClassReports(app)

    def rooms(self,token):
        with self.app.lock:
            actor=self.app._teacher(token)
            return [{'id':r['id'],'name':r['name'],'state':r['state'],'snapshot_id':r['snapshot_id'],'archived':r.get('archived',False),'member_count':len(r['members']),'reflected_count':sum(bool(v['reflection']) for v in r['learning'].values()),'message_count':sum(e.get('author_type')=='STUDENT' for e in r['events'])} for r in self.app._all('room') if r['owner']==actor['actor_id']]

    def record_conditions(self,token,room_id,participant_id,value):
        app=self.app
        with app.transaction():
            room=app._get(room_id);app._teacher(token,room['owner'])
            if room['state']!='ENDED' or participant_id not in room['learning']:raise DomainError('OBSERVATION_NOT_OPEN')
            if not isinstance(value,dict) or set(value)!={'data_complete','opportunity','note'} or type(value['data_complete']) is not bool or not isinstance(value['opportunity'],dict) or not isinstance(value['note'],str) or len(value['note'])>2000:raise DomainError('INVALID_OBSERVATION_CONDITIONS')
            if any(k not in ['C1','C2','C3','C4','C5','C6'] or v not in ['NONE','PRESENT','UNKNOWN'] for k,v in value['opportunity'].items()):raise DomainError('INVALID_OBSERVATION_CONDITIONS')
            if (not value['data_complete'] or 'NONE' in value['opportunity'].values()) and not value['note'].strip():raise DomainError('OBSERVATION_REASON_REQUIRED')
            previous=room.get('observation_conditions',{}).get(participant_id)
            if previous and all(previous[k]==value[k] for k in value):return previous
            record={'id':identifier('observation-condition'),'room_id':room_id,'participant_id':participant_id,'owner':room['owner'],'version':previous['version']+1 if previous else 1,'at':app.clock(),**copy.deepcopy(value)}
            room.setdefault('observation_conditions',{})[participant_id]=record
            app._put(room,'room');app._put(record,'observation-condition');return record

    def _input(self,room,kind,participant_id,room_ids=None):
        app=self.app; f=self.feedback
        if room['state']!='ENDED': raise DomainError('DISCUSSION_NOT_ENDED')
        if kind=='CLASS': return self.classes._context(room['owner'],room_ids if room_ids is not None else [room['id']])
        packet=app._get(room['snapshot_id'])['packet']
        messages=[{**e,'phase':'DISCUSSION'} for e in room['events'] if e['type']=='MESSAGE' and e['seq']<=room['end_seq']]
        registry=[e for e in app._all('evidence') if e['room_id']==room['id']]
        if kind=='EVIDENCE':
            return {'room_id':room['id'],'snapshot_id':room['snapshot_id'],'frozen_log_id':room['id']+':end:'+str(room['end_seq']),'participants':room['members'],'messages':messages,'selected_dimensions':packet['assessment']['selected'],'rubric':packet['assessment'].get('rubric'),'knowledge_definitions':packet['assessment'].get('knowledge',[]),'limitations':[]}
        if kind=='ASSESSMENT': return f._context(room,participant_id)
        if kind=='PERSONAL':
            context=f._context(room,participant_id)
            baselines=[a for a in app._all('assessment') if a['room_id']==room['id'] and a['participant_id']==participant_id and a['status']=='VALIDATED' and a['input_hash']==context['input_hash']]
            if not baselines: raise DomainError('INDEPENDENT_ASSESSMENT_REQUIRED')
            learning=room['learning'][participant_id]
            if not learning['reflection']: raise DomainError('REFLECTION_REQUIRED')
            return {'mode':'PERSONAL','participant_id':participant_id,'assessment_contract_version':2,'feedback_contract':{'dimension_details_source':'adopted_assessment.dimensions','knowledge_observations_source':'adopted_assessment.knowledge_observations','rule':'复制当前采用版本；independent_assessment仅用于原始AI基线回溯，目标和自评不能重定等级。'},'independent_assessment':baselines[-1],'adopted_assessment':adopted(app,baselines[-1]),'ai_baseline_reference':baselines[-1]['id'],'goal':{'text':learning['goal'],'version':learning.get('goal_version',0),'strategy':next((s.get('strategy','') for s in app._all('learning-state') if s['room_id']==room['id'] and s['participant_id']==participant_id),'')},'reflection':learning['reflection'],'feedback_preferences':packet['feedback'],'verified_evidence':context['verified_evidence'],'limitations':[]}
        if kind=='GROUP':
            return {'mode':'GROUP','room_id':room['id'],'snapshot_id':room['snapshot_id'],'frozen_submission':room['frozen_submission'],'members':room['members'],'confirmations':(room['frozen_submission'] or {}).get('acks',{}),'messages':messages,'public_case':packet['case']['public'],'knowledge':packet['assessment'].get('knowledge',[]),'feedback_preferences':packet['feedback'],'verified_evidence':registry,'limitations':[]}
        raise DomainError('INVALID_WORKFLOW_TASK')

    def create_task(self,token,room_id,kind,participant_id=None,room_ids=None):
        app=self.app
        with app.transaction():
            room=app._get(room_id); actor=app._teacher(token,room['owner'])
            value=self._input(room,kind,participant_id,room_ids)
            task={'id':identifier('review-task'),'owner':actor['actor_id'],'room_id':room_id,'kind':kind,'participant_id':participant_id,'scope_room_ids':value['scope']['room_ids'] if kind=='CLASS' else None,'input':copy.deepcopy(value),'input_hash':hashed(value),'created_at':app.clock(),'status':'AWAITING_MANUAL_WORKFLOW_RESULT','transport':'MANUAL_NATIVE_WORKFLOW'}
            if kind in ['PERSONAL','GROUP','CLASS']:
                task['input']['workflow_binding']={k:task[k] for k in ['kind','room_id','participant_id','input_hash']}
                task['input']['workflow_binding']['task_id']=task['id']
            app._put(task,'review-task'); return task

    def get_task(self,token,task_id):
        with self.app.lock:
            task=self.app._get(task_id); self.app._teacher(token,task['owner'])
            if task.get('transport')!='MANUAL_NATIVE_WORKFLOW': raise DomainError('NOT_FOUND',status=404)
            return task

    def import_result(self,token,task_id,output):
        app=self.app
        with app.lock:
            task=app._get(task_id); app._teacher(token,task['owner'])
            if task.get('kind') not in ['EVIDENCE','ASSESSMENT','PERSONAL','GROUP','CLASS']: raise DomainError('INVALID_WORKFLOW_TASK')
            value=unwrap(output); output_hash=hashed(value)
            if task['status']=='IMPORTED':
                if task['output_hash']!=output_hash: raise DomainError('TASK_ALREADY_IMPORTED',status=409)
                return task['result']
            room=app._get(task['room_id'])
            if hashed(self._input(room,task['kind'],task['participant_id'],task.get('scope_room_ids')))!=task['input_hash']: raise DomainError('WORKFLOW_INPUT_STALE',status=409)
            if task['kind'] in ['PERSONAL','GROUP','CLASS']:
                if set(value)!={'workflow_binding','body'} or value['workflow_binding']!=task['input'].get('workflow_binding'):
                    raise DomainError('WORKFLOW_BINDING_MISMATCH')
                value=value['body']
            ids=[]
            if task['kind']=='EVIDENCE':
                candidates=value.get('evidence_candidates')
                if not isinstance(candidates,list) or len(candidates)>200: raise DomainError('EVIDENCE_CANDIDATES_REQUIRED')
                checked=[]
                for e in candidates:
                    if not isinstance(e,dict) or not {'participant_id','message_id','quote'}.issubset(e): raise DomainError('INVALID_EVIDENCE_CANDIDATE')
                    result=app.validate_evidence(token,room['id'],e['participant_id'],e['message_id'],e['quote'])
                    eid='evidence-'+digest(json.dumps([room['id'],e['participant_id'],e['message_id'],e['quote']],ensure_ascii=False))[:32]
                    checked.append({'id':eid,'evidence_id':eid,'room_id':room['id'],'snapshot_id':room['snapshot_id'],**result})
                # Validate the whole batch first; a wrong author never leaves partial records.
                with app.transaction():
                    for record in checked: app._put(record,'evidence'); ids.append(record['id'])
            elif task['kind']=='ASSESSMENT':
                if 'ok' in value:
                    if value.get('ok') is not True or value.get('errors')!=[]: raise DomainError('NATIVE_OBSERVER_REJECTED')
                    value=value.get('assessment')
                record=self.feedback.record_assessment(token,room['id'],task['participant_id'],value); ids=[record['id']]
            elif task['kind']=='CLASS':
                record=self.classes.stage(token,task['scope_room_ids'],task['input']['input_hash'],value,source_task_id=task_id); ids=[record['id']]
            else:
                check_report_body(task['kind'],value)
                record=self.feedback.stage_report(token,room['id'],task['kind'],value,task['participant_id'],source_task_id=task_id); ids=[record['id']]
            automatic=task['kind'] in ['PERSONAL','GROUP'] and app._get(room['snapshot_id'])['packet']['feedback'].get('mode')=='auto'
            if automatic:
                self.feedback.publish_report(token,ids[0])
            result={'release':'AUTO_POLICY_PUBLISHED' if automatic else 'REVIEW_REQUIRED','task_id':task_id,'status':'IMPORTED_FOR_REVIEW','record_ids':ids,'provenance':'MANUAL_WORKFLOW_IMPORT_EXECUTION_NOT_AUTOMATICALLY_VERIFIED'}
            with app.transaction():
                task.update(status='IMPORTED',output_hash=output_hash,raw_output=copy.deepcopy(output),result=result,imported_at=app.clock())
                app._put(task,'review-task')
            return result

    def dashboard(self,token,room_id):
        app=self.app
        with app.lock:
            room=app._get(room_id); actor=app._member(token,room)
            teacher=actor['role']=='TEACHER'
            result={'room_id':room_id,'reports':[],'reflection_required':not teacher and not room['learning'][actor['actor_id']]['reflection']}
            for report in app._all('report'):
                if report.get('room_id')!=room_id: continue
                if not teacher and (report['kind']=='PERSONAL' and report['participant_id']!=actor['actor_id']): continue
                if not teacher and report['kind']=='GROUP' and not app._get(room['snapshot_id'])['packet']['feedback'].get('share_group'): continue
                current=True
                try: self.feedback._report_source_current(report,room)
                except DomainError: current=False
                item={k:report.get(k) for k in ['id','kind','participant_id','created_at','source_task_id']}
                item['status']='STALE' if not current else report['status']
                if teacher: item['body']=copy.deepcopy(report['body'])
                elif current and report['status']=='PUBLISHED' and not result['reflection_required']: item['body']=copy.deepcopy(report['body'])
                result['reports'].append(item)
            if teacher:
                result['evidence']=[e for e in app._all('evidence') if e['room_id']==room_id]
                result['assessments']=[a for a in app._all('assessment') if a['room_id']==room_id]
                for a in result['assessments']:
                    if a['status']=='VALIDATED' and a['input_hash']!=self.feedback._context(room,a['participant_id'])['input_hash']: a['status']='STALE'
                result['tasks']=[{k:t.get(k) for k in ['id','kind','participant_id','status','created_at','result']} for t in app._all('review-task') if t['room_id']==room_id]
                for record in app._all('class-report'):
                    if record['owner']==room['owner'] and room_id in record['room_ids']:
                        result['reports'].append({'id':record['id'],'kind':'CLASS','participant_id':None,'created_at':record['created_at'],'source_task_id':record.get('source_task_id'),'status':record['status'] if self.classes.current(record) else 'STALE','body':record['body'],'statistics':record['context']['statistics'],'authorized_fragments':record['context']['authorized_fragments']})
            return result

    def revise_report(self,token,report_id,body):
        with self.app.lock:
            record=self.app._get(report_id)
            if record.get('kind')=='CLASS':
                self.app._teacher(token,record['owner'])
                return self.classes.stage(token,record['room_ids'],record['source_hash'],body,supersedes=report_id)
            previous=self.feedback.get_report(token,report_id)
            self.app._teacher(token,previous['owner'])
            check_report_body(previous['kind'],body)
            return self.feedback.stage_report(token,previous['room_id'],previous['kind'],body,previous['participant_id'],supersedes=report_id)

    def publish_report(self,token,report_id):
        with self.app.lock:
            record=self.app._get(report_id)
            return self.classes.publish(token,report_id) if record.get('kind')=='CLASS' else self.feedback.publish_report(token,report_id)
