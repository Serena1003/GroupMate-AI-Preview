"""Deterministic scoped statistics and teacher-only class report drafts."""
import copy
import json
from .domain import DomainError, digest, identifier
from .feedback import FeedbackService
from .assessment_reviews import adopted
from .observer import strings

SECTION_KEYS=['activity_evidence_scope','knowledge_application','dimension_commonalities','key_issues','representative_fragments','follow_up_teaching_suggestions']


def hashed(value): return digest(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')))


class ClassReports:
    def __init__(self,app):self.app=app;self.feedback=FeedbackService(app)

    def context(self,token,room_ids):
        with self.app.lock:
            actor=self.app._teacher(token)
            return self._context(actor['actor_id'],room_ids)

    def _context(self,owner,room_ids):
        app=self.app
        if not isinstance(room_ids,list) or not room_ids or not strings(room_ids):raise DomainError('CLASS_SCOPE_REQUIRED')
        room_ids=sorted(set(room_ids)); rooms=[app._get(rid) for rid in room_ids]
        if any(r.get('owner')!=owner for r in rooms):raise DomainError('FORBIDDEN',status=403)
        if any(r.get('state')!='ENDED' for r in rooms):raise DomainError('CLASS_SCOPE_NOT_ENDED')
        registry=sorted([e for e in app._all('evidence') if e['room_id'] in room_ids],key=lambda e:e['id'])
        active={}; assessments=app._all('assessment'); sources=[]; strata={}
        for room in rooms:
            packet=app._get(room['snapshot_id'])['packet']
            conditions={'snapshot_id':room['snapshot_id'],'configured_seconds':packet['runtime']['seconds'],'actual_seconds':min(packet['runtime']['seconds'],int(room['elapsed_base'])),'support_recording':'UNRECORDED','mode':'REAL_STUDENT_GROUP'}
            help_records=[h for h in app._all('help-exposure') if h['room_id']==room['id']]
            conditions['difficulty']=packet['runtime'].get('difficulty','标准');conditions['prompt_intensity']=packet['runtime'].get('prompt_intensity','轻量')
            if help_records:conditions.update(support_recording='PUBLIC_AVAILABILITY_RECORDED_NOT_ATTENTION',help_kinds=sorted({h['kind'] for h in help_records}))
            sid='stratum-'+hashed(conditions)[:20]
            strata.setdefault(sid,{'stratum_id':sid,'conditions':conditions,'rooms':[]})['rooms'].append(room)
            input_hashes={}
            for member in room['members']:
                cx=self.feedback._context(room,member['id']);input_hashes[member['id']]=cx['input_hash']
                candidates=[a for a in assessments if a['room_id']==room['id'] and a['participant_id']==member['id'] and a['status']=='VALIDATED' and a['input_hash']==cx['input_hash']]
                if candidates: active[member['id']]=adopted(app,candidates[-1])
            sources.append({'room_id':room['id'],'snapshot_id':room['snapshot_id'],'end_seq':room['end_seq'],'members':[m['id'] for m in room['members']],'assessment_input_hashes':input_hashes,'assessment_ids':[active[m['id']]['id'] for m in room['members'] if m['id'] in active]})
        statistics=[]
        def stat(metric,sid,unit,numerator,denominator,eligible,missing,not_observed,eids,**extra):
            label={k:extra.get(k) for k in ['dimension','level','tag'] if k in extra}
            statistics.append({'stat_id':'stat-'+hashed([metric,sid,label])[:24],'metric':metric,'stratum_id':sid,'unit':unit,'numerator':numerator,'denominator':denominator,'eligible_count':eligible,'missing_count':missing,'not_observed_count':not_observed,'evidence_ids':sorted(set(eids)),**extra})
        for sid,stratum in strata.items():
            selected=app._get(stratum['rooms'][0]['snapshot_id'])['packet']['assessment']
            members=[m for r in stratum['rooms'] for m in r['members']]
            for dim in selected['selected']:
                details=[];missing=0
                for m in members:
                    baseline=active.get(m['id'])
                    if not baseline:missing+=1;continue
                    detail=next(d for d in baseline['dimensions'] if d['dimension']==dim)
                    details.append(detail)
                observed=[d for d in details if d['status']=='OBSERVED'];not_observed=sum(d['status'] in ['INSUFFICIENT_EVIDENCE','INSUFFICIENT_OPPORTUNITY'] for d in details)
                reasons={status:sum(d['status']==status for d in details) for status in ['INSUFFICIENT_EVIDENCE','INSUFFICIENT_OPPORTUNITY','DATA_INCOMPLETE']}
                evidence=[e for d in observed for e in d['evidence_ids']]
                stat('dimension_observed',sid,'STUDENT',len(observed),len(members),len(members),missing,not_observed,evidence,dimension=dim,not_observed_by_reason=reasons)
                for level in range(1,5):
                    hits=[d for d in observed if d['level']==level]
                    stat('dimension_level',sid,'STUDENT',len(hits),len(observed),len(members),missing,not_observed,[e for d in hits for e in d['evidence_ids']],dimension=dim,level=level)
            for tag in selected.get('knowledge',[]):
                supported=0;missing=0;partial=0;uncertain=0;not_observed=0;evidence=[];counter=[]
                for room in stratum['rooms']:
                    baselines=[active[m['id']] for m in room['members'] if m['id'] in active]
                    per_member=[[v for v in a['knowledge_observations'] if v['tag']==tag] for a in baselines]
                    covered=sum(bool(v) for v in per_member)
                    complete=covered==len(room['members']) and bool(room['members'])
                    if not complete:
                        missing+=1
                        if covered:partial+=1
                    observations=[v for rows in per_member for v in rows]
                    hits=[v for v in observations if v['status']=='SUPPORTED']
                    if hits:supported+=1;evidence.extend(e for v in hits for e in v['evidence_ids'])
                    elif complete and all(v['status']=='NOT_OBSERVED' for v in observations):not_observed+=1
                    if any(v['status']=='UNCERTAIN' for v in observations):uncertain+=1
                    counter.extend(e for v in observations if v['status']=='MISUSE' for e in v['evidence_ids'])
                stat('knowledge_supported_groups',sid,'GROUP',supported,len(stratum['rooms']),len(stratum['rooms']),missing,not_observed,evidence,tag=tag,partial_count=partial,uncertain_count=uncertain,counterexample_ids=sorted(set(counter)))
        group_reports=[{'report_id':r['id'],'room_id':r['room_id'],'body':r['body']} for r in app._all('report') if r['room_id'] in room_ids and r['kind']=='GROUP' and r['status']=='PUBLISHED']
        current_group_reports=[]
        for report in group_reports:
            try:self.feedback._report_source_current(app._get(report['report_id']),app._get(report['room_id']))
            except DomainError:continue
            current_group_reports.append(report)
        group_reports=current_group_reports
        fragments=[{'evidence_id':e['id'],'room_id':e['room_id'],'participant_id':e['participant_id'],'text':e['quote'],'pseudonym':next(m['name'] for r in rooms for m in r['members'] if m['id']==e['participant_id'])} for e in registry]
        value={'scope':{'room_ids':room_ids,'group_count':len(rooms),'student_count':sum(len(r['members']) for r in rooms),'label':'当前单组观察' if len(rooms)==1 else '教师所选小组范围'},'strata':[{'stratum_id':sid,'conditions':s['conditions'],'room_ids':[r['id'] for r in s['rooms']]} for sid,s in sorted(strata.items())],'statistics':statistics,'authorized_fragments':fragments,'group_reports':sorted(group_reports,key=lambda r:r['report_id']),'source_index':sources,'limitations':['统计仅基于本次冻结记录及当前通过结构/引用校验的独立评价，尚未完成教学效度验证。','等级为序位，只展示档位分布，不计算平均或排名。','帮助暴露当前未完整记录，不据此比较教学效果；不同快照与实际时长分别分层。','知识统计按标签核对每名成员覆盖；缺失含部分覆盖，未观察仅指全员有该标签明确NOT_OBSERVED。支持数为至少一人有支持证据的小组数，可与缺失覆盖重叠。','未观察或缺失不等于低表现；单组不能外推全班。','假名原话仅供教师内部回查，不属于彻底匿名公开材料。']}
        value['feedback_preferences_by_room']=[{'room_id':r['id'],'preferences':app._get(r['snapshot_id'])['packet']['feedback']} for r in rooms]
        value['input_hash']=hashed(value); return value

    def check_body(self,context,body):
        if not isinstance(body,dict) or set(body)!={'sections','limitations'} or not strings(body['limitations']):raise DomainError('CLASS_REPORT_FIELDS')
        sections=body['sections']
        if not isinstance(sections,list) or len(sections)!=6:raise DomainError('CLASS_SIX_SECTIONS_REQUIRED')
        stats={s['stat_id'] for s in context['statistics']}; evidence={e['evidence_id'] for e in context['authorized_fragments']}
        for expected,section in zip(SECTION_KEYS,sections):
            if not isinstance(section,dict) or set(section)!={'key','text','claims'} or section['key']!=expected or not isinstance(section['text'],str) or not isinstance(section['claims'],list):raise DomainError('CLASS_SECTION_INVALID')
            for claim in section['claims']:
                if not isinstance(claim,dict) or set(claim)!={'text','stat_ids','evidence_ids','counterexample_ids','limitations'} or not isinstance(claim['text'],str) or not claim['text'].strip() or not strings(claim['limitations']):raise DomainError('CLASS_CLAIM_INVALID')
                for key,allowed in [('stat_ids',stats),('evidence_ids',evidence),('counterexample_ids',evidence)]:
                    if not strings(claim[key]) or any(v not in allowed for v in claim[key]):raise DomainError('CLASS_REFERENCE_INVALID')

    def stage(self,token,room_ids,input_hash,body,source_task_id=None,supersedes=None):
        app=self.app
        with app.transaction():
            actor=app._teacher(token);context=self._context(actor['actor_id'],room_ids)
            if input_hash!=context['input_hash']:raise DomainError('CLASS_INPUT_STALE',status=409)
            self.check_body(context,body)
            if source_task_id:
                existing=[r for r in app._all('class-report') if r.get('source_task_id')==source_task_id]
                if existing:return existing[0]
            if supersedes:
                old=app._get(supersedes)
                if old.get('owner')!=actor['actor_id'] or old.get('room_ids')!=context['scope']['room_ids'] or old['status'] not in ['DRAFT','PUBLISHED']:raise DomainError('REVISION_SOURCE_CHANGED')
            record={'id':identifier('class-report'),'owner':actor['actor_id'],'kind':'CLASS','room_ids':context['scope']['room_ids'],'source_hash':input_hash,'context':context,'body':copy.deepcopy(body),'source_task_id':source_task_id,'supersedes':supersedes,'status':'DRAFT','created_at':app.clock()}
            app._put(record,'class-report');return record

    def current(self,record):
        with self.app.lock:return record['source_hash']==self._context(record['owner'],record['room_ids'])['input_hash']

    def publish(self,token,report_id):
        app=self.app
        with app.transaction():
            record=app._get(report_id);app._teacher(token,record['owner'])
            if record.get('kind')!='CLASS' or record['status'] not in ['DRAFT','PUBLISHED']:raise DomainError('REPORT_NOT_PUBLISHABLE')
            if not self.current(record):raise DomainError('CLASS_REPORT_STALE',status=409)
            if record.get('supersedes'):
                old=app._get(record['supersedes'])
                if old['status']=='SUPERSEDED' and record['status']!='PUBLISHED':raise DomainError('REVISION_SOURCE_CHANGED')
                old['status']='SUPERSEDED';app._put(old,'class-report')
            record.update(status='PUBLISHED',reviewed_at=app.clock());app._put(record,'class-report');return record
