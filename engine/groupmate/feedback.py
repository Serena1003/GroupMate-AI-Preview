"""Evidence registry and feedback release gates, independent of model provider.

This stores real model drafts when available. It does not manufacture assessment
or report text when no provider has run.
"""
import copy
import json
from .domain import DomainError, digest, identifier
from .observer import validate_candidate
from .assessment_reviews import adopted


class FeedbackService:
    def __init__(self,app): self.app=app

    def evidence(self,token,room_id,participant_id,message_id,quote):
        app=self.app
        with app.lock:
            checked=app.validate_evidence(token,room_id,participant_id,message_id,quote)
            with app.transaction():
                room=app._get(room_id)
                eid='evidence-'+digest(json.dumps([room_id,participant_id,message_id,quote],ensure_ascii=False))[:32]
                record={'id':eid,'evidence_id':eid,'room_id':room_id,'snapshot_id':room['snapshot_id'],**checked}
                app._put(record,'evidence'); return record

    def _context(self,room,participant_id):
        app=self.app
        if room['state']!='ENDED': raise DomainError('DISCUSSION_NOT_ENDED')
        if participant_id not in {m['id'] for m in room['members']}: raise DomainError('PARTICIPANT_NOT_FOUND')
        packet=app._get(room['snapshot_id'])['packet']
        context={'room_id':room['id'],'snapshot_id':room['snapshot_id'],'frozen_log_id':room['id']+':end:'+str(room['end_seq']),'participant_id':participant_id,'public_case':packet['case']['public'],'events':[e for e in room['events'] if e['seq']<=room['end_seq'] and e['type'] in ['MESSAGE','CASE_EVENT']],'selected_dimensions':packet['assessment']['selected'],'rubric':packet['assessment'].get('rubric'),'rubric_version':packet['assessment']['rubric_version'],'knowledge':packet['assessment'].get('knowledge',[]),'verified_evidence':sorted([e for e in app._all('evidence') if e['room_id']==room['id'] and e['participant_id']==participant_id],key=lambda e:e['id'])}
        help_records=[h for h in app._all('help-exposure') if h['room_id']==room['id'] and participant_id in h['audience_ids']]
        if help_records:context['help_exposures']=sorted(help_records,key=lambda h:h['id'])
        conditions=room.get('observation_conditions',{}).get(participant_id)
        if conditions:context.update(data_complete=conditions['data_complete'],opportunity=copy.deepcopy(conditions['opportunity']),limitations=[conditions['note']] if conditions['note'] else [])
        context['input_hash']=digest(json.dumps(context,ensure_ascii=False,sort_keys=True,separators=(',',':')))
        return context

    def assessment_context(self,token,room_id,participant_id):
        with self.app.transaction():
            room=self.app._get(room_id); self.app._teacher(token,room['owner'])
            return self._context(room,participant_id)

    def _group_hash(self,room):
        source={'snapshot_id':room['snapshot_id'],'end_seq':room['end_seq'],'submission':room['frozen_submission'],'evidence':sorted([e for e in self.app._all('evidence') if e['room_id']==room['id']],key=lambda e:e['id'])}
        return digest(json.dumps(source,ensure_ascii=False,sort_keys=True,separators=(',',':')))

    def record_assessment(self,token,room_id,participant_id,value):
        """Validate an independent model draft; never infer levels from counts."""
        app=self.app
        with app.transaction():
            room=app._get(room_id); app._teacher(token,room['owner'])
            context=self._context(room,participant_id)
            required={'snapshot_id','frozen_log_id','participant_id','input_hash','rubric_version','dimensions','knowledge_observations','limitations'}
            if not isinstance(value,dict) or not required.issubset(value) or set(value)-required-{'assessment_id','knowledge_spec_id','status'}: raise DomainError('INVALID_ASSESSMENT')
            if any(value[k]!=context[k] for k in ['snapshot_id','frozen_log_id','participant_id','input_hash','rubric_version']): raise DomainError('ASSESSMENT_INPUT_STALE')
            checked=validate_candidate(context,{k:value[k] for k in required})
            if not checked['ok']: raise DomainError('OBSERVER_RULES_REJECTED:'+','.join(checked['errors']))
            dimensions=value['dimensions']
            if not isinstance(dimensions,list) or len(dimensions)!=6: raise DomainError('SIX_DIMENSIONS_REQUIRED')
            registry={e['id']:e for e in context['verified_evidence']}
            selected=set(context['selected_dimensions']); seen=set()
            rubric=context['rubric']
            rubric_dims={r.get('dimension'):r.get('levels') for r in rubric.get('dimensions',[]) if isinstance(r,dict)} if isinstance(rubric,dict) else {}
            statuses={'NOT_SELECTED','INSUFFICIENT_OPPORTUNITY','INSUFFICIENT_EVIDENCE','DATA_INCOMPLETE','OBSERVED'}
            fields={'dimension','status','level','evidence_ids','counter_evidence_ids','explanation','limitations'}
            for item in dimensions:
                if not isinstance(item,dict) or set(item)!=fields: raise DomainError('INVALID_DIMENSION_DETAIL')
                dim=item['dimension']; status=item['status']
                if dim not in {'C1','C2','C3','C4','C5','C6'} or dim in seen or status not in statuses: raise DomainError('INVALID_DIMENSION')
                seen.add(dim)
                if (dim in selected and status=='NOT_SELECTED') or (dim not in selected and status!='NOT_SELECTED'): raise DomainError('DIMENSION_NOT_SELECTED')
                for key in ['evidence_ids','counter_evidence_ids']:
                    ids=item[key]
                    if not isinstance(ids,list) or any(not isinstance(eid,str) or eid not in registry for eid in ids): raise DomainError('ASSESSMENT_EVIDENCE_INVALID')
                if not isinstance(item['explanation'],str) or not item['explanation'].strip() or not isinstance(item['limitations'],list): raise DomainError('ASSESSMENT_EXPLANATION_REQUIRED')
                if status=='OBSERVED':
                    if type(item['level']) is not int or not 1<=item['level']<=4 or not item['evidence_ids']: raise DomainError('JUDGMENT_EVIDENCE_REQUIRED')
                    anchors=rubric_dims.get(dim)
                    if not isinstance(anchors,dict) or set(anchors)!={'1','2','3','4'} or not all(isinstance(t,str) and t.strip() for t in anchors.values()): raise DomainError('RUBRIC_TEXT_REQUIRED')
                elif item['level'] is not None: raise DomainError('NO_LEVEL_FOR_UNOBSERVED')
            knowledge=value['knowledge_observations']
            if not isinstance(knowledge,list) or not isinstance(value['limitations'],list): raise DomainError('INVALID_ASSESSMENT')
            for item in knowledge:
                if not isinstance(item,dict) or set(item)!={'tag','status','evidence_ids','explanation'}: raise DomainError('INVALID_KNOWLEDGE_OBSERVATION')
                if item['tag'] not in context['knowledge'] or item['status'] not in ['SUPPORTED','MISUSE','NOT_OBSERVED','UNCERTAIN']: raise DomainError('INVALID_KNOWLEDGE_OBSERVATION')
                if not isinstance(item['evidence_ids'],list) or any(eid not in registry for eid in item['evidence_ids']): raise DomainError('ASSESSMENT_EVIDENCE_INVALID')
                if item['status'] in ['SUPPORTED','MISUSE'] and not item['evidence_ids']: raise DomainError('JUDGMENT_EVIDENCE_REQUIRED')
            payload={k:copy.deepcopy(value[k]) for k in required}
            output_hash=digest(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')))
            for prior in app._all('assessment'):
                if prior['room_id']==room_id and prior['participant_id']==participant_id and prior.get('output_hash')==output_hash and prior['status']=='VALIDATED': return prior
            # Preserve superseded records, rather than overwrite a baseline.
            for prior in app._all('assessment'):
                if prior['room_id']==room_id and prior['participant_id']==participant_id and prior['status']=='VALIDATED':
                    prior['status']='SUPERSEDED'; app._put(prior,'assessment')
            record={'id':identifier('assessment'),'room_id':room_id,'owner':room['owner'],**payload,'output_hash':output_hash,'status':'VALIDATED','validation_scope':'STRUCTURE_AND_SOURCE_REFERENCES_ONLY','created_at':app.clock()}
            app._put(record,'assessment'); return record

    def stage_report(self,token,room_id,kind,body,participant_id=None,source_task_id=None,supersedes=None):
        app=self.app
        with app.transaction():
            room=app._get(room_id); app._teacher(token,room['owner'])
            if source_task_id:
                prior=[r for r in app._all('report') if r.get('source_task_id')==source_task_id]
                if prior: return prior[0]
            if room['state']!='ENDED': raise DomainError('DISCUSSION_NOT_ENDED')
            if kind not in ['PERSONAL','GROUP']: raise DomainError('INVALID_REPORT_KIND')
            if supersedes:
                previous=app._get(supersedes)
                if any(previous.get(k)!=v for k,v in [('room_id',room_id),('kind',kind),('participant_id',participant_id)]) or previous['status'] not in ['DRAFT','PUBLISHED']: raise DomainError('REVISION_SOURCE_CHANGED',status=409)
                self._report_source_current(previous,room)
            if not isinstance(body,dict): raise DomainError('INVALID_REPORT')
            allowed={'PERSONAL':{'goal_review','self_reflection_comparison','strength','priority_improvement','next_action','dimension_details','knowledge_observations','limitations'},'GROUP':{'submission_version','summary','reasoning','disagreement_handling','knowledge_strengths_difficulties','evidence_ids','limitations'}}[kind]
            if set(body)-allowed: raise DomainError('UNSUPPORTED_REPORT_FIELDS')
            # Reject prohibited aggregate fields wherever a provider nests them.
            def scan(value):
                if isinstance(value,dict):
                    if set(value)&{'total_score','ranking','rank','srl_score','C7','hire_probability','average_level'}: raise DomainError('PROHIBITED_REPORT_AGGREGATE')
                    for v in value.values(): scan(v)
                elif isinstance(value,list):
                    for v in value: scan(v)
            scan(body)
            ref_version=None
            baseline_id=None
            if kind=='PERSONAL':
                if participant_id not in room['learning']: raise DomainError('PARTICIPANT_NOT_FOUND')
                ref=room['learning'][participant_id]['reflection']
                if not ref: raise DomainError('REFLECTION_REQUIRED')
                ref_version=ref['version']
                details=body.get('dimension_details',[])
                if not isinstance(details,list): raise DomainError('INVALID_DIMENSION_DETAILS')
                selected=app._get(room['snapshot_id'])['packet']['assessment']['selected']
                active=[v for v in app._all('assessment') if v['room_id']==room_id and v['participant_id']==participant_id and v['status']=='VALIDATED' and v['input_hash']==self._context(room,participant_id)['input_hash']]
                baseline=adopted(app,active[-1]) if active else None
                baseline_id=baseline['id'] if baseline else None
                if 'knowledge_observations' in body and (not baseline or body['knowledge_observations']!=baseline['knowledge_observations']):raise DomainError('INDEPENDENT_KNOWLEDGE_REQUIRED')
                seen=set()
                required={'dimension','status','level','evidence_ids','explanation','limitations'}
                for item in details:
                    if not isinstance(item,dict) or not required.issubset(item) or set(item)-required-{'counter_evidence_ids'}: raise DomainError('INVALID_DIMENSION_DETAIL')
                    dim=item['dimension']; status=item['status']
                    if dim not in {'C1','C2','C3','C4','C5','C6'} or dim in seen: raise DomainError('INVALID_DIMENSION')
                    seen.add(dim)
                    if not baseline or item not in baseline['dimensions']: raise DomainError('INDEPENDENT_ASSESSMENT_REQUIRED')
                    if dim not in selected and status!='NOT_SELECTED': raise DomainError('DIMENSION_NOT_SELECTED')
                    if dim in selected and status not in ['OBSERVED','INSUFFICIENT_OPPORTUNITY','INSUFFICIENT_EVIDENCE','DATA_INCOMPLETE']: raise DomainError('INVALID_OBSERVATION_STATUS')
                    if status=='OBSERVED':
                        if type(item['level']) is not int or not 1<=item['level']<=4 or not item['evidence_ids']: raise DomainError('JUDGMENT_EVIDENCE_REQUIRED')
                    elif item['level'] is not None: raise DomainError('NO_LEVEL_FOR_UNOBSERVED')
                for field in ['strength','priority_improvement']:
                    item=body.get(field)
                    if item is not None and (not isinstance(item,dict) or not item.get('evidence_ids')): raise DomainError('JUDGMENT_EVIDENCE_REQUIRED')
                    if item is not None:
                        permitted=set()
                        if baseline:
                            for d in baseline['dimensions']:
                                if field=='strength' and d['status']=='OBSERVED':permitted.update(d['evidence_ids'])
                                if field=='priority_improvement':
                                    permitted.update(d['counter_evidence_ids'])
                                    if d['status']=='OBSERVED' and d['level']<=2:permitted.update(d['evidence_ids'])
                            for k in baseline['knowledge_observations']:
                                if k['status']==('SUPPORTED' if field=='strength' else 'MISUSE'):permitted.update(k['evidence_ids'])
                        if not isinstance(item['evidence_ids'],list) or any(not isinstance(e,str) or e not in permitted for e in item['evidence_ids']):raise DomainError('INDEPENDENT_JUDGMENT_REQUIRED')
            else:
                submission=room['frozen_submission']
                if body.get('submission_version')!=(submission['version'] if submission else None): raise DomainError('REPORT_SUBMISSION_STALE')
            registry={e['id']:e for e in app._all('evidence') if e['room_id']==room_id}
            def validate_refs(value):
                if isinstance(value,dict):
                    for key,item in value.items():
                        if key in ['evidence_ids','counter_evidence_ids']:
                            if not isinstance(item,list): raise DomainError('INVALID_EVIDENCE_IDS')
                            for eid in item:
                                if eid not in registry or (kind=='PERSONAL' and registry[eid]['participant_id']!=participant_id): raise DomainError('REPORT_EVIDENCE_INVALID')
                        else: validate_refs(item)
                elif isinstance(value,list):
                    for v in value: validate_refs(v)
            validate_refs(body)
            learning_hash=digest(json.dumps(room['learning'][participant_id],ensure_ascii=False,sort_keys=True)) if kind=='PERSONAL' else None
            report={'id':identifier('report'),'room_id':room_id,'owner':room['owner'],'snapshot_id':room['snapshot_id'],'kind':kind,'participant_id':participant_id,'reflection_version':ref_version,'learning_hash':learning_hash,'assessment_id':baseline_id,'source_task_id':source_task_id,'supersedes':supersedes,'end_seq':room['end_seq'],'body':copy.deepcopy(body),'status':'DRAFT','created_at':app.clock()}
            if kind=='GROUP':report['group_source_hash']=self._group_hash(room)
            app._put(report,'report'); return report

    def _report_source_current(self,report,room):
        if report['kind']=='GROUP':
            if report.get('group_source_hash')!=self._group_hash(room):raise DomainError('REPORT_STALE')
            return
        if report['kind']!='PERSONAL': return
        ref=room['learning'][report['participant_id']]['reflection']
        if not ref or ref['version']!=report['reflection_version']: raise DomainError('REPORT_STALE')
        if report.get('learning_hash')!=digest(json.dumps(room['learning'][report['participant_id']],ensure_ascii=False,sort_keys=True)): raise DomainError('REPORT_STALE')
        current=[a for a in self.app._all('assessment') if a['room_id']==room['id'] and a['participant_id']==report['participant_id'] and a['status']=='VALIDATED']
        baseline=adopted(self.app,current[-1]) if current else None
        if report.get('assessment_id')!=(baseline['id'] if baseline else None): raise DomainError('REPORT_STALE')
        if baseline and baseline['input_hash']!=self._context(room,report['participant_id'])['input_hash']: raise DomainError('REPORT_STALE')

    def publish_report(self,token,report_id):
        app=self.app
        with app.transaction():
            report=app._get(report_id); app._teacher(token,report['owner'])
            if report['status'] not in ['DRAFT','PUBLISHED']: raise DomainError('REPORT_NOT_PUBLISHABLE',status=409)
            room=app._get(report['room_id'])
            self._report_source_current(report,room)
            if report.get('supersedes'):
                previous=app._get(report['supersedes'])
                if previous['status']=='SUPERSEDED' and report['status']!='PUBLISHED': raise DomainError('REVISION_SOURCE_CHANGED',status=409)
                previous['status']='SUPERSEDED'; app._put(previous,'report')
            report['status']='PUBLISHED'; report['reviewed_at']=app.clock()
            app._put(report,'report'); return report

    def get_report(self,token,report_id):
        app=self.app
        with app.transaction():
            report=app._get(report_id); room=app._get(report['room_id']); actor=app._member(token,room)
            self._report_source_current(report,room)
            if actor['role']!='TEACHER':
                if report['status']!='PUBLISHED': raise DomainError('REPORT_NOT_RELEASED',status=403)
                if report['kind']=='PERSONAL' and report['participant_id']!=actor['actor_id']: raise DomainError('FORBIDDEN',status=403)
                if report['kind']=='GROUP' and not app._get(room['snapshot_id'])['packet']['feedback'].get('share_group'): raise DomainError('GROUP_REPORT_PRIVATE',status=403)
                if not room['learning'][actor['actor_id']]['reflection']: raise DomainError('REFLECTION_REQUIRED',status=403)
            return report
