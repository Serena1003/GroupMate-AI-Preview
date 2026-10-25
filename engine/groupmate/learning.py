"""Private SRL records and explicitly recorded public teaching support."""
from .domain import DomainError,identifier,digest

class Learning:
    def __init__(self,app):self.app=app
    def view(self,token,room_id):
        with self.app.lock:
            room=self.app._get(room_id);actor=self.app._member(token,room)
            if actor['role']!='STUDENT':raise DomainError('STUDENT_REQUIRED')
            records=[r for r in self.app._all('learning-state') if r['room_id']==room_id and r['participant_id']==actor['actor_id']]
            return records[-1] if records else {'strategy':'','next_action':'','experience':'','participation':'ACTIVE'}
    def save(self,token,room_id,field,text):
        if field not in ['strategy','next_action','experience','participation'] or not isinstance(text,str) or len(text)>2000:raise DomainError('LEARNING_INPUT_INVALID')
        with self.app.transaction():
            room=self.app._get(room_id);actor=self.app._member(token,room)
            if actor['role']!='STUDENT':raise DomainError('STUDENT_REQUIRED')
            if field=='strategy' and room['state']=='ENDED':raise DomainError('STRATEGY_STAGE_CLOSED')
            if field in ['next_action','experience'] and (room['state']!='ENDED' or not room['learning'][actor['actor_id']]['reflection']):raise DomainError('REFLECTION_REQUIRED')
            if field=='participation' and text not in ['ACTIVE','WITHDRAWN']:raise DomainError('PARTICIPATION_INVALID')
            current=self.view(token,room_id);current.update(id='learning-'+digest(room_id+actor['actor_id'])[:32],room_id=room_id,participant_id=actor['actor_id'],owner=room['owner'],at=self.app.clock());current[field]=text
            current['version']=current.get('version',0)+1;self.app._put(current,'learning-state')
            self.app._put({'id':identifier('learning-version'),'room_id':room_id,'participant_id':actor['actor_id'],'field':field,'text':text,'at':self.app.clock()},'learning-version')
            if field=='participation':room.setdefault('withdrawals',{})[actor['actor_id']]=text;self.app._put(room,'room')
            return current
    def help(self,token,room_id,text,kind='CLARIFICATION'):
        if kind not in ['QUESTION','CLARIFICATION','CONCEPT','STRATEGY','ANSWER_HINT'] or not isinstance(text,str) or not text.strip() or len(text)>1000:raise DomainError('HELP_INVALID')
        with self.app.transaction():
            room=self.app._get(room_id);self.app._teacher(token,room['owner']);self.app._advance_clock(room)
            if room['state']!='RUNNING':raise DomainError('DISCUSSION_NOT_RUNNING')
            event=self.app._event(room,'MESSAGE',text,author_type='TEACHER',author_id=room['owner'],display_name='教师 · 教学支持',help_kind=kind)
            self.app._put(room,'room');return record_help(self.app,room,event,kind)

def record_help(app,room,event,kind):
    record={'id':'help-'+event['id'],'room_id':room['id'],'message_id':event['id'],'kind':kind,'audience_ids':[m['id'] for m in room['members']],'visibility':'GROUP_PUBLIC_AVAILABLE_NOT_PROOF_OF_ATTENTION','at':app.clock()}
    app._put(record,'help-exposure');return record
