"""Teacher-facing read models. Facts and permissions remain in the engine."""
import copy
from .domain import DomainError, identifier, digest
from .feedback import FeedbackService
from .review import ReviewWorkspace
from .class_reports import ClassReports
from .assessment_reviews import adopted


class TeacherDashboard:
    def __init__(self,app):
        self.app=app;self.feedback=FeedbackService(app);self.review=ReviewWorkspace(app);self.classes=ClassReports(app)

    def sessions(self,token):
        with self.app.lock:
            actor=self.app._teacher(token)
            return [s for s in self.app._all('teaching-session') if s['owner']==actor['actor_id']]

    def create_session(self,token,title,room_ids,data_mode):
        app=self.app
        with app.transaction():
            actor=app._teacher(token)
            if not isinstance(title,str) or not title.strip() or not isinstance(room_ids,list) or not room_ids:raise DomainError('SESSION_SCOPE_REQUIRED')
            rooms=[app._get(i) for i in sorted(set(room_ids))]
            if any(r.get('owner')!=actor['actor_id'] for r in rooms):raise DomainError('FORBIDDEN',status=403)
            if len({r['snapshot_id'] for r in rooms})!=1:raise DomainError('SESSION_SINGLE_SNAPSHOT_REQUIRED')
            if data_mode not in ['SYNTHETIC','CLASSROOM']:raise DomainError('DATA_MODE_REQUIRED')
            s={'id':identifier('teaching-session'),'owner':actor['actor_id'],'title':title.strip(),'snapshot_id':rooms[0]['snapshot_id'],
               'room_ids':[r['id'] for r in rooms],'data_mode':data_mode,'created_at':app.clock()}
            app._put(s,'teaching-session');return s

    def _active(self,room):
        result={}
        if room['state']!='ENDED':return result
        for m in room['members']:
            context=self.feedback._context(room,m['id'])
            hits=[a for a in self.app._all('assessment') if a['room_id']==room['id'] and a['participant_id']==m['id'] and a['status']=='VALIDATED' and a['input_hash']==context['input_hash']]
            if hits:result[m['id']]=adopted(self.app,hits[-1])
        return result

    def group(self,token,room_id):
        app=self.app
        with app.lock:
            room=app._get(room_id);app._teacher(token,room['owner'])
            packet=app._get(room['snapshot_id'])['packet'];active=self._active(room)
            return {'room_id':room_id,'name':room['name'],'state':room['state'],'snapshot_id':room['snapshot_id'],
                    'members':copy.deepcopy(room['members']),'original_submission':copy.deepcopy(room.get('frozen_submission') if room['state']=='ENDED' else room.get('submission')),
                    'assessments':list(active.values()),'ai_baselines':[a for a in app._all('assessment') if a['room_id']==room_id],
                    'evidence':[e for e in app._all('evidence') if e['room_id']==room_id],
                    'messages':[e for e in room['events'] if e['type'] in ['MESSAGE','CASE_EVENT']],
                    'reports':self.review.dashboard(token,room_id)['reports'],
                    'selected_dimensions':packet['assessment']['selected'],'rubric':packet['assessment'].get('rubric'),
                    'rubric_version':packet['assessment']['rubric_version']}

    def report(self,token,report_id):
        app=self.app
        with app.lock:
            record=app._get(report_id);app._teacher(token,record.get('owner'))
            if record.get('kind') not in ['CLASS','GROUP','PERSONAL']:raise DomainError('NOT_FOUND',status=404)
            result=copy.deepcopy(record);current=True
            if record['kind']=='CLASS':current=self.classes.current(record)
            else:
                try:self.feedback._report_source_current(record,app._get(record['room_id']))
                except DomainError:current=False
            result['source_current']=current
            if not current:result['status']='STALE'
            return result

    def evidence_context(self,token,evidence_id):
        app=self.app
        with app.lock:
            e=app._get(evidence_id);room=app._get(e['room_id']);app._teacher(token,room['owner'])
            if 'quote' not in e:raise DomainError('NOT_FOUND',status=404)
            messages=[v for v in room['events'] if v['type'] in ['MESSAGE','CASE_EVENT']]
            index=next((i for i,m in enumerate(messages) if m['id']==e['message_id']),None)
            return {'evidence':e,'messages':messages[max(0,index-2):index+3] if index is not None else [],'room_id':room['id']}

    def dashboard(self,token,session_id):
        app=self.app
        with app.lock:
            s=app._get(session_id);app._teacher(token,s.get('owner'))
            if 'room_ids' not in s or 'data_mode' not in s:raise DomainError('NOT_FOUND',status=404)
            rooms=[app._get(i) for i in s['room_ids']];packet=app._get(s['snapshot_id'])['packet']
            groups=[];reports={};active={};evidence=[]
            for room in rooms:
                values=self._active(room);active.update(values)
                groups.append({'room_id':room['id'],'name':room['name'],'state':room['state'],'member_count':len(room['members']),
                    'student_message_count':sum(e.get('author_type')=='STUDENT' for e in room['events']),
                    'submission_status':'SUBMITTED' if room.get('frozen_submission') else 'NOT_SUBMITTED',
                    'assessments_ready':len(values),'snapshot_id':room['snapshot_id']})
                evidence.extend({**e,'group_name':room['name'],'pseudonym':next(m['name'] for m in room['members'] if m['id']==e['participant_id'])} for e in app._all('evidence') if e['room_id']==room['id'])
                for r in self.review.dashboard(token,room['id'])['reports']:
                    if r['kind']!='CLASS' or sorted(app._get(r['id'])['room_ids'])==sorted(s['room_ids']):reports[r['id']]=r
            for e in evidence:
                a=active.get(e['participant_id'])
                e['dimensions']=[d['dimension'] for d in a['dimensions'] if e['id'] in d['evidence_ids']+d['counter_evidence_ids']] if a else []
            ended=[r['id'] for r in rooms if r['state']=='ENDED']
            cx=self.classes.context(token,ended) if ended else {'statistics':[],'strata':[],'limitations':[]}
            dims=[];member_count=sum(len(r['members']) for r in rooms)
            for dim in packet['assessment']['selected']:
                details=[next(d for d in a['dimensions'] if d['dimension']==dim) for a in active.values()]
                dims.append({'dimension':dim,'eligible':member_count,'observed':sum(d['status']=='OBSERVED' for d in details),
                    'levels':{str(n):sum(d['status']=='OBSERVED' and d['level']==n for d in details) for n in range(1,5)},
                    'not_observed_by_reason':{k:sum(d['status']==k for d in details) for k in ['INSUFFICIENT_EVIDENCE','INSUFFICIENT_OPPORTUNITY']},
                    'data_incomplete':sum(d['status']=='DATA_INCOMPLETE' for d in details),'pending':member_count-len(details)})
            knowledge=[]
            for tag in packet['assessment'].get('knowledge',[]):
                rows=[v for v in cx['statistics'] if v['metric']=='knowledge_supported_groups' and v['tag']==tag]
                knowledge.append({'concept_id':'concept-'+digest(tag)[:20],'label':tag,
                    'metric_definition':'至少一名成员有支持性证据的小组数；可与覆盖缺失重叠，不代表全组掌握。',
                    'numerator':sum(v['numerator'] for v in rows),'denominator':len(ended),
                    'coverage_missing_groups':sum(v['missing_count'] for v in rows),
                    'coverage_partial_groups':sum(v['partial_count'] for v in rows)})
            published=[r for r in reports.values() if r['kind']=='CLASS' and r['status']=='PUBLISHED']
            highlight=None
            if published:
                cr=published[-1]
                for section in cr['body']['sections']:
                    if section['claims']:
                        claim=section['claims'][0];highlight={'text':claim['text'],'report_id':cr['id'],'evidence_ids':claim['evidence_ids'],'stat_ids':claim['stat_ids'],'counterexample_ids':claim['counterexample_ids'],'referenced_statistics':[v for v in cx['statistics'] if v['stat_id'] in claim['stat_ids']]};break
            return {'schema_version':1,'session':s,'data_mode':s['data_mode'],'execution_mode':'MANUAL_OR_AUTHORIZED_API',
                'activity':{'title':packet['title'],'configured_seconds':packet['runtime']['seconds'],'selected_dimensions':packet['assessment']['selected'],'rubric_version':packet['assessment']['rubric_version']},
                'scope':{'created_groups':len(rooms),'submitted_groups':sum(g['submission_status']=='SUBMITTED' for g in groups),
                    'ended_groups':len(ended),'joined_students':member_count,'registered_students':None,'assessments_ready':len(active),
                    'groups_with_discussion':sum(g['student_message_count']>0 for g in groups)},
                'groups':groups,'dimensions':dims,'knowledge':knowledge,'strata':cx['strata'],'statistics':cx['statistics'],
                'reports':list(reports.values()),'evidence':evidence,'highlight':highlight,
                'limitations':cx['limitations']+['维度总计仅说明当前场次覆盖；跨组表现比较请查看条件分层，不计算均值或排名。']}
