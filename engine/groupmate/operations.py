"""Credential-free portable classroom records and non-destructive archive restoration."""
import copy
from .domain import DomainError,identifier
from .review import hashed

class Operations:
    def __init__(self,app):self.app=app
    def export_room(self,token,room_id):
        with self.app.lock:
            room=self.app._get(room_id);self.app._teacher(token,room['owner'])
            if room['state']!='ENDED':raise DomainError('FREEZE_BEFORE_EXPORT')
            data={'format':'GROUPMATE_CLASSROOM_ARCHIVE_V1','room':{k:copy.deepcopy(room.get(k)) for k in ['id','name','state','members','events','submission','frozen_submission','end_seq','learning','observation_conditions']},'packet':self.app._get(room['snapshot_id'])['packet'],'reports':[r for r in self.app._all('report') if r['room_id']==room_id],'assessments':[r for r in self.app._all('assessment') if r['room_id']==room_id],'assessment_reviews':[r for r in self.app._all('assessment-review') if r['room_id']==room_id],'evidence':[r for r in self.app._all('evidence') if r['room_id']==room_id],'help':[r for r in self.app._all('help-exposure') if r['room_id']==room_id],'srl':[r for r in self.app._all('learning-state') if r['room_id']==room_id],'class_reports':[r for r in self.app._all('class-report') if room_id in r['room_ids'] and r['owner']==room['owner']],'notice':'内部课堂记录含假名、原话和学习反思；不是匿名公开材料。保管者负责本机文件。','exported_at':self.app.clock()}
            data['checksum']=hashed(data);return data
    def restore(self,token,bundle):
        with self.app.transaction():
            actor=self.app._teacher(token)
            if not isinstance(bundle,dict) or bundle.get('format')!='GROUPMATE_CLASSROOM_ARCHIVE_V1' or not isinstance(bundle.get('room'),dict) or not isinstance(bundle.get('packet'),dict) or len(str(bundle))>6*1024*1024:raise DomainError('ARCHIVE_INVALID')
            value=copy.deepcopy(bundle);checksum=value.pop('checksum',None)
            if not checksum or hashed(value)!=checksum:raise DomainError('ARCHIVE_CHECKSUM_INVALID')
            forbidden={'token','apikey','api_key','join_code','owner_secret'}
            def check(v):
                if isinstance(v,dict):
                    if set(v)&forbidden:raise DomainError('ARCHIVE_CONTAINS_CREDENTIALS')
                    for item in v.values():check(item)
                elif isinstance(v,list):
                    for item in v:check(item)
            check(bundle)
            record={'id':identifier('restored-archive'),'owner':actor['actor_id'],'status':'READ_ONLY_RESTORED_COPY','name':bundle['room'].get('name','恢复的课堂记录'),'data':copy.deepcopy(bundle),'at':self.app.clock()}
            self.app._put(record,'restored-archive');return record
    def library(self,token):
        with self.app.lock:
            actor=self.app._teacher(token);return [{k:r[k] for k in ['id','name','status','at']} for r in self.app._all('restored-archive') if r['owner']==actor['actor_id']]
    def get(self,token,archive_id):
        with self.app.lock:
            r=self.app._get(archive_id);self.app._teacher(token,r['owner'])
            if r.get('status')!='READ_ONLY_RESTORED_COPY':raise DomainError('ARCHIVE_REQUIRED')
            return r
    def archive_room(self,token,room_id,archived=True):
        with self.app.transaction():
            room=self.app._get(room_id);self.app._teacher(token,room['owner'])
            if room['state'] not in ['READY','ENDED']:raise DomainError('END_OR_PAUSE_BEFORE_ARCHIVING')
            room['archived']=bool(archived);self.app._put(room,'room');return {'room_id':room_id,'archived':room['archived']}
