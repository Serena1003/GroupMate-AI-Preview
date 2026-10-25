"""Transactional classroom state. Models never own permissions, clocks or facts."""
import copy
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager


class DomainError(Exception):
    def __init__(self, code, message=None, status=400):
        super().__init__(message or code)
        self.code, self.status = code, status


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def identifier(prefix):
    return prefix + '-' + secrets.token_hex(10)


class Classroom:
    def __init__(self, database, clock=time.time):
        self.clock = clock
        self.runtime_id = identifier('runtime')
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL)')
        self.db.commit()

    def close(self):
        with self.lock:
            self.db.close()

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def _get(self, key):
        row = self.db.execute('SELECT body FROM objects WHERE id=?', (key,)).fetchone()
        if not row:
            raise DomainError('NOT_FOUND', status=404)
        return json.loads(row[0])

    def _put(self, obj, kind):
        self.db.execute('INSERT OR REPLACE INTO objects(id,kind,body) VALUES(?,?,?)', (obj['id'], kind, json.dumps(obj, ensure_ascii=False)))

    def _all(self, kind):
        return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM objects WHERE kind=?', (kind,))]

    def bootstrap_teacher(self, owner_secret):
        if not isinstance(owner_secret,str) or not owner_secret:
            raise DomainError('OWNER_SECRET_REQUIRED')
        token = digest('groupmate-owner:' + owner_secret)
        with self.transaction():
            actor = {'id': 'auth-' + digest(token), 'actor_id': 'teacher-' + digest(token)[:20], 'role': 'TEACHER'}
            self._put(actor,'actor')
        return token

    def _actor(self, token):
        if not isinstance(token,str) or not token:
            raise DomainError('UNAUTHORIZED', status=401)
        try:
            return self._get('auth-' + digest(token))
        except DomainError:
            raise DomainError('UNAUTHORIZED', status=401)

    def _teacher(self, token, owner=None):
        a = self._actor(token)
        if a['role'] != 'TEACHER' or (owner and a['actor_id'] != owner):
            raise DomainError('FORBIDDEN', status=403)
        return a

    def _member(self, token, room):
        a = self._actor(token)
        if a['role']=='TEACHER':
            if a['actor_id'] != room['owner']:
                raise DomainError('FORBIDDEN', status=403)
        elif a.get('room_id') != room['id']:
            raise DomainError('FORBIDDEN', status=403)
        return a

    def create_draft(self, token, packet):
        with self.transaction():
            a=self._teacher(token)
            d={'id':identifier('draft'),'owner':a['actor_id'],'revision':1,'packet':copy.deepcopy(packet),'confirmations':{},'published_ids':[]}
            self._put(d,'draft')
            return d

    def get_draft(self,token,draft_id):
        with self.transaction():
            d=self._get(draft_id); self._teacher(token,d['owner']); return d

    def update_draft(self,token,draft_id,revision,patch):
        with self.transaction():
            d=self._get(draft_id); self._teacher(token,d['owner'])
            if revision!=d['revision']: raise DomainError('REVISION_CONFLICT',status=409)
            if not isinstance(patch,dict) or any(k not in set(d['packet'])|{'data_policy'} for k in patch): raise DomainError('INVALID_DRAFT_PATCH')
            d['packet'].update(copy.deepcopy(patch)); d['revision']+=1; d['confirmations']={}
            self._put(d,'draft'); return d

    def confirm(self,token,draft_id,node,revision):
        with self.transaction():
            d=self._get(draft_id); self._teacher(token,d['owner'])
            if revision!=d['revision']: raise DomainError('REVISION_CONFLICT',status=409)
            if node not in range(1,10): raise DomainError('INVALID_NODE')
            d['confirmations'][str(node)]={'at':self.clock(),'revision':revision}
            self._put(d,'draft'); return d

    def publish(self,token,draft_id,revision):
        with self.transaction():
            d=self._get(draft_id); self._teacher(token,d['owner'])
            if revision!=d['revision']: raise DomainError('REVISION_CONFLICT',status=409)
            if set(d['confirmations'])!={str(i) for i in range(1,10)}: raise DomainError('CONFIRMATION_REQUIRED')
            p=d['packet']
            for key in ['title','goals','case','roles','questions','task','assessment','runtime','feedback','source']:
                if not p.get(key): raise DomainError('MISSING_'+key.upper())
            if not isinstance(p['case'],dict) or not isinstance(p['runtime'],dict) or not isinstance(p['assessment'],dict) or not isinstance(p['feedback'],dict) or not isinstance(p['source'],dict): raise DomainError('INVALID_PACKET_STRUCTURE')
            if not isinstance(p['case'].get('public'),str) or not p['case']['public'].strip(): raise DomainError('CASE_REQUIRED')
            if not isinstance(p['case'].get('unknowns'),list) or not all(isinstance(x,str) for x in p['case']['unknowns']): raise DomainError('UNKNOWNS_LIST_REQUIRED')
            for key in ['goals','questions','task']:
                if not isinstance(p[key],list) or not p[key] or not all(isinstance(x,str) and x.strip() for x in p[key]): raise DomainError('INVALID_'+key.upper())
            if not isinstance(p['roles'],list) or not p['roles']: raise DomainError('ROLE_REQUIRED')
            role_ids=[]
            for card in p['roles']:
                if not isinstance(card,dict) or not all(isinstance(card.get(k),str) and card[k].strip() for k in ['id','name','background','authority','conditions']): raise DomainError('INVALID_ROLE_CARD')
                role_ids.append(card['id'])
            if len(set(role_ids))!=len(role_ids): raise DomainError('DUPLICATE_ROLE_ID')
            if type(p['runtime'].get('seconds')) is not int: raise DomainError('INVALID_DURATION')
            if type(p['runtime'].get('event_enabled')) is not bool: raise DomainError('EVENT_ENABLED_REQUIRED')
            if p['runtime']['event_enabled'] and (type(p['runtime'].get('event_at')) is not int or not isinstance(p['runtime'].get('event_text'),str) or not p['runtime']['event_text'].strip()): raise DomainError('INVALID_EVENT')
            if not isinstance(p['assessment'].get('selected'),list) or not all(isinstance(x,str) for x in p['assessment']['selected']): raise DomainError('INVALID_DIMENSION')
            if p['source'].get('route') not in ['TEXTBOOK_EXISTING','TEACHER_CASE','TEXTBOOK_NEW','WEB_CASE']: raise DomainError('INVALID_SOURCE_ROUTE')
            if p['feedback'].get('mode') not in ['review','auto']: raise DomainError('INVALID_FEEDBACK_MODE')
            if not 60<=p['runtime'].get('seconds',0)<=3600: raise DomainError('INVALID_DURATION')
            if p['runtime'].get('event_enabled') and not 0<p['runtime']['event_at']<p['runtime']['seconds']: raise DomainError('INVALID_EVENT_TIME')
            if not set(p['assessment']['selected']).issubset({'C1','C2','C3','C4','C5','C6'}): raise DomainError('INVALID_DIMENSION')
            if not p['assessment']['selected']: raise DomainError('DIMENSION_REQUIRED')
            if p['feedback']['mode'] not in ['review','auto']: raise DomainError('INVALID_FEEDBACK_MODE')
            s={'id':identifier('snapshot'),'owner':d['owner'],'draft_id':d['id'],'draft_revision':revision,'packet':copy.deepcopy(p),'at':self.clock()}
            s['hash']=digest(json.dumps(s,ensure_ascii=False,sort_keys=True,separators=(',',':')))
            self._put(s,'snapshot'); d['published_ids'].append(s['id']); self._put(d,'draft'); return s

    def get_snapshot(self,token,snapshot_id):
        with self.transaction():
            s=self._get(snapshot_id); self._teacher(token,s['owner']); return s

    def create_room(self,token,snapshot_id,name):
        with self.transaction():
            s=self._get(snapshot_id); self._teacher(token,s['owner'])
            r={'id':identifier('room'),'snapshot_id':s['id'],'owner':s['owner'],'name':name,'join_code':secrets.token_hex(4).upper(),'state':'READY','epoch':0,'elapsed_base':0.0,'resumed_at':None,'events':[],'members':[],'event_published':False,'fact_version':1,'submission':None,'frozen_submission':None,'end_seq':None,'learning':{},'ai_status':'NOT_CONNECTED'}
            self._put(r,'room'); return r

    def join(self,join_code,name,notice_accepted=False):
        if not isinstance(name,str) or not name.strip() or len(name)>40: raise DomainError('INVALID_PSEUDONYM')
        with self.transaction():
            rooms=[r for r in self._all('room') if r['join_code']==str(join_code).strip().upper()]
            if not rooms: raise DomainError('INVALID_JOIN_CODE',status=404)
            r=rooms[0]
            if r.get('archived'):raise DomainError('ROOM_ARCHIVED')
            if r['state']!='READY': raise DomainError('ROOM_NOT_JOINABLE')
            policy=self._get(r['snapshot_id'])['packet'].get('data_policy',{})
            if policy.get('notice_required') and notice_accepted is not True:raise DomainError('READ_ACTIVITY_NOTICE_FIRST')
            token=secrets.token_urlsafe(32); pid=identifier('participant')
            a={'id':'auth-'+digest(token),'actor_id':pid,'role':'STUDENT','room_id':r['id'],'name':name.strip()}
            self._put(a,'actor'); r['members'].append({'id':pid,'name':name.strip()}); r['learning'][pid]={'goal':'','reflection':None}
            self._put(r,'room'); return {'token':token,'participant_id':pid,'room_id':r['id'],'name':name.strip()}

    def _elapsed(self,r):
        return r['elapsed_base']+(max(0,self.clock()-r['resumed_at']) if r['state']=='RUNNING' else 0)

    def _event(self,r,typ,text,**fields):
        e={'id':identifier('message'),'seq':len(r['events'])+1,'type':typ,'text':text,'at':self.clock(),'fact_version':r['fact_version'],**fields}
        r['events'].append(e); return e

    def _end(self,r):
        if r['state']=='ENDED': return
        r['elapsed_base']=self._elapsed(r); r['resumed_at']=None; r['state']='ENDED'; r['epoch']+=1
        self._event(r,'CONTROL','讨论已结束，原始记录与提交已冻结。',author_type='SYSTEM')
        r['end_seq']=len(r['events']); r['ended_at']=self.clock(); r['frozen_submission']=copy.deepcopy(r['submission'])

    def _tick(self,r):
        if r['state']!='RUNNING': return
        cfg=self._get(r['snapshot_id'])['packet']['runtime']; elapsed=self._elapsed(r)
        if elapsed>=cfg['seconds']:
            self._end(r); return
        if cfg.get('event_enabled') and not r['event_published'] and elapsed>=cfg['event_at']:
            r['event_published']=True; r['fact_version']+=1
            self._event(r,'CASE_EVENT',cfg['event_text'],author_type='SYSTEM')

    def _advance_clock(self, r):
        """Commit clock transitions before a command which may be rejected.

        Called only after authorization and before command mutations, while the
        transaction lock is held. A rejected late command cannot undo expiry.
        """
        before = (r['epoch'], r['fact_version'])
        self._tick(r)
        if before != (r['epoch'], r['fact_version']):
            self._put(r, 'room')
            self.db.commit()
            self.db.execute('BEGIN IMMEDIATE')

    def control(self,token,room_id,action):
        with self.transaction():
            r=self._get(room_id); self._teacher(token,r['owner'])
            if action=='end' and r['state'] in ['RUNNING','PAUSED']:
                self._end(r)
            elif action=='start' and r['state']=='READY':
                r['state']='RUNNING'; r['resumed_at']=self.clock(); r['epoch']+=1
                self._event(r,'CONTROL','讨论开始。',author_type='SYSTEM')
            elif action=='pause' and r['state']=='RUNNING':
                self._tick(r)
                if r['state']=='RUNNING':
                    r['elapsed_base']=self._elapsed(r); r['resumed_at']=None; r['state']='PAUSED'; r['epoch']+=1
                    self._event(r,'CONTROL','教师暂停讨论。',author_type='SYSTEM')
            elif action=='resume' and r['state']=='PAUSED':
                r['state']='RUNNING'; r['resumed_at']=self.clock(); r['epoch']+=1
                self._event(r,'CONTROL','教师恢复讨论。',author_type='SYSTEM')
            else: raise DomainError('INVALID_ROOM_TRANSITION')
            self._put(r,'room'); return r

    def room_view(self,token,room_id):
        with self.transaction():
            r=self._get(room_id); a=self._member(token,r); self._advance_clock(r); self._put(r,'room')
            p=self._get(r['snapshot_id'])['packet']
            public={'title':p['title'],'goals':p['goals'],'case':p['case']['public'],'unknowns':p['case']['unknowns'],'roles':[{k:role.get(k) for k in ['id','name','background','authority']} for role in p['roles']],'questions':p['questions'],'task':p['task'],'difficulty':p['runtime'].get('difficulty','标准'),'help_policy':p['runtime'].get('help_policy','角色内澄清与追问'),'data_policy':p.get('data_policy',{}),'feedback':{'allow_skip':p['feedback'].get('allow_skip',False),'share_group':p['feedback'].get('share_group',False)}}
            v={'id':r['id'],'name':r['name'],'state':r['state'],'elapsed':int(self._elapsed(r)),'remaining':max(0,int(p['runtime']['seconds']-self._elapsed(r))),'epoch':r['epoch'],'fact_version':r['fact_version'],'events':r['events'],'members':r['members'],'activity':public,'submission':r['frozen_submission'] if r['state']=='ENDED' else r['submission'],'ai_status':r['ai_status'],'actor':{'id':a['actor_id'],'role':a['role'],'name':a.get('name','教师')}}
            if a['role']=='TEACHER': v['join_code']=r['join_code']; v['learning']=r['learning']; v['observation_conditions']=r.get('observation_conditions',{})
            else: v['my_learning']=r['learning'][a['actor_id']]
            return v

    def message(self,token,room_id,client_id,text,reply_to=None):
        if not isinstance(text,str) or not text.strip() or len(text)>5000: raise DomainError('INVALID_MESSAGE')
        if not isinstance(client_id,str) or not client_id or len(client_id)>120: raise DomainError('CLIENT_ID_REQUIRED')
        with self.transaction():
            r=self._get(room_id); a=self._member(token,r)
            for e in r['events']:
                if e.get('author_id')==a['actor_id'] and e.get('client_id')==client_id: return e
            if r.get('withdrawals',{}).get(a['actor_id'])=='WITHDRAWN':raise DomainError('PARTICIPATION_WITHDRAWN')
            self._advance_clock(r)
            if r['state']!='RUNNING':
                raise DomainError('ROOM_'+r['state'])
            if reply_to and not any(e['id']==reply_to for e in r['events']): raise DomainError('INVALID_REPLY_TARGET')
            e=self._event(r,'MESSAGE',text,author_type=a['role'],author_id=a['actor_id'],display_name=a.get('name','教师'),client_id=client_id,reply_to=reply_to)
            self._put(r,'room'); return e

    def submit(self,token,room_id,raw,expected_version):
        if not isinstance(raw,str) or not raw.strip() or len(raw)>20000: raise DomainError('INVALID_SUBMISSION')
        with self.transaction():
            r=self._get(room_id); a=self._member(token,r)
            if a['role']!='STUDENT':raise DomainError('STUDENT_REQUIRED',status=403)
            if r.get('withdrawals',{}).get(a['actor_id'])=='WITHDRAWN':raise DomainError('PARTICIPATION_WITHDRAWN')
            self._advance_clock(r)
            if r['state']!='RUNNING': raise DomainError('DEADLINE_CLOSED')
            old=r['submission']; version=old['version'] if old else 0
            if expected_version!=version: raise DomainError('SUBMISSION_CONFLICT',status=409)
            s={'version':version+1,'raw':raw,'submitted_by':a['actor_id'],'at':self.clock(),'acks':{}}
            r['submission']=s; self._event(r,'SUBMISSION','小组已提交建议版本'+str(s['version']),author_type='SYSTEM')
            self._put(r,'room'); return s

    def acknowledge(self,token,room_id,version,decision):
        if decision not in ['agree','reserve']: raise DomainError('INVALID_ACK')
        with self.transaction():
            r=self._get(room_id); a=self._member(token,r)
            if a['role']!='STUDENT':raise DomainError('STUDENT_REQUIRED',status=403)
            if r.get('withdrawals',{}).get(a['actor_id'])=='WITHDRAWN':raise DomainError('PARTICIPATION_WITHDRAWN')
            self._advance_clock(r)
            if r['state']!='RUNNING': raise DomainError('DEADLINE_CLOSED')
            if not r['submission'] or r['submission']['version']!=version: raise DomainError('STALE_SUBMISSION',status=409)
            r['submission']['acks'][a['actor_id']]={'decision':decision,'at':self.clock()}
            self._put(r,'room'); return r['submission']

    def set_goal(self,token,room_id,text):
        if not isinstance(text,str) or len(text)>2000: raise DomainError('INVALID_GOAL')
        with self.transaction():
            r=self._get(room_id); a=self._member(token,r)
            if a['role']!='STUDENT': raise DomainError('STUDENT_REQUIRED')
            learning=r['learning'][a['actor_id']]
            if learning['goal']==text:return {'saved':True,'version':learning.get('goal_version',0)}
            learning['goal']=text;learning['goal_version']=learning.get('goal_version',0)+1
            self._put({'id':identifier('goal-version'),'room_id':room_id,'participant_id':a['actor_id'],'version':learning['goal_version'],'text':text,'at':self.clock()},'goal-version')
            self._put(r,'room'); return {'saved':True,'version':learning['goal_version']}

    def reflect(self,token,room_id,text,skip=False):
        with self.transaction():
            r=self._get(room_id); a=self._member(token,r)
            if a['role']!='STUDENT' or r['state']!='ENDED': raise DomainError('REFLECTION_NOT_OPEN')
            p=self._get(r['snapshot_id'])['packet']
            if skip and not p['feedback'].get('allow_skip'): raise DomainError('SKIP_NOT_ALLOWED')
            if not skip and (not isinstance(text,str) or not text.strip()): raise DomainError('EMPTY_REFLECTION')
            old=r['learning'][a['actor_id']]['reflection']
            ref={'status':'SKIPPED_EXPLICIT' if skip else 'SUBMITTED','text':'' if skip else text,'at':self.clock(),'version':(old['version']+1 if old else 1)}
            r['learning'][a['actor_id']]['reflection']=ref; self._put(r,'room'); return ref

    def role_context(self,token,room_id,role_id):
        with self.transaction():
            r=self._get(room_id); self._teacher(token,r['owner']); self._advance_clock(r)
            if r['state']!='RUNNING': raise DomainError('DISCUSSION_NOT_RUNNING')
            p=self._get(r['snapshot_id'])['packet']
            cards=[card for card in p['roles'] if card['id']==role_id]
            if len(cards)!=1: raise DomainError('INVALID_ROLE')
            context={'id':identifier('role-job'),'room_id':r['id'],'snapshot_id':r['snapshot_id'],'epoch':r['epoch'],'fact_version':r['fact_version'],'context_seq':len(r['events']),'public_case':p['case']['public'],'unknowns':p['case']['unknowns'],'assigned_role':copy.deepcopy(cards[0]),'public_events':[e for e in r['events'] if e['type']=='CASE_EVENT'],'messages':[e for e in r['events'] if e['type']=='MESSAGE'],'remaining':max(0,int(p['runtime']['seconds']-self._elapsed(r)))}
            self._put({'id':context['id'],'context':context,'delivered':None},'role_job')
            return context

    def deliver_role(self,token,room_id,context,text):
        if not isinstance(text,str) or not text.strip() or len(text)>1000: raise DomainError('INVALID_ROLE_TEXT')
        with self.transaction():
            r=self._get(room_id); self._teacher(token,r['owner']); self._advance_clock(r)
            job=self._get(context['id'])
            if job.get('context')!=context or context['room_id']!=room_id: raise DomainError('INVALID_ROLE_JOB')
            if job['delivered']: return job['delivered']
            if r['state']!='RUNNING' or context['epoch']!=r['epoch'] or context['fact_version']!=r['fact_version'] or context['context_seq']!=len(r['events']): raise DomainError('STALE_MODEL_RESULT',status=409)
            card=context['assigned_role']
            event=self._event(r,'MESSAGE',text,author_type='AI',author_id=card['id'],display_name=card['name'],model_job_id=job['id'])
            job['delivered']=event; self._put(job,'role_job'); self._put(r,'room'); return event

    def model_context(self,token,room_id,kind):
        with self.transaction():
            r=self._get(room_id); self._teacher(token,r['owner']); self._advance_clock(r)
            p=self._get(r['snapshot_id'])['packet']
            if kind not in ['assessment','group_report']: raise DomainError('INVALID_MODEL_TASK')
            if kind!='role' and r['state']!='ENDED': raise DomainError('DISCUSSION_NOT_ENDED')
            return {'room_id':r['id'],'snapshot_id':r['snapshot_id'],'epoch':r['epoch'],'fact_version':r['fact_version'],'kind':kind,'public_case':p['case']['public'],'public_events':[e for e in r['events'] if e['type']=='CASE_EVENT'],'roles':p['roles'] if kind=='role' else [],'messages':[e for e in r['events'] if e['type']=='MESSAGE'],'submission':r['frozen_submission'] if kind!='role' else None,'assessment':p['assessment'] if kind!='role' else None}

    def validate_evidence(self,token,room_id,participant_id,message_id,quote):
        with self.transaction():
            r=self._get(room_id); self._teacher(token,r['owner'])
            if r['state']!='ENDED': raise DomainError('DISCUSSION_NOT_ENDED')
            hits=[e for e in r['events'] if e['id']==message_id and e['seq']<=r['end_seq']]
            if not hits or hits[0].get('author_type')!='STUDENT' or hits[0].get('author_id')!=participant_id: raise DomainError('EVIDENCE_AUTHOR_INVALID')
            m=hits[0]
            if not isinstance(quote,str) or not quote or quote not in m['text']: raise DomainError('EVIDENCE_QUOTE_INVALID')
            start=m['text'].index(quote)
            return {'message_id':message_id,'participant_id':participant_id,'quote':quote,'start':start,'end':start+len(quote),'seq':m['seq'],'validation':'VALID'}
