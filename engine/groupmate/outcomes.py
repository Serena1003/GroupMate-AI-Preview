"""Published discussion synthesis and factual participation counts; never ratings."""
import copy
from .feedback import FeedbackService
from .domain import DomainError


def group_outcome(app,room):
    contributions=[{'participant_id':m['id'],'name':m['name'],
                    'message_count':sum(e.get('author_type')=='STUDENT' and e.get('author_id')==m['id'] and e['type']=='MESSAGE' for e in room['events'])}
                   for m in room['members']]
    result={'room_id':room['id'],'group_name':room['name'],'status':'AWAITING_REVIEW',
            'contributions':contributions,'student_count':len(room['members']),
            'message_count':sum(x['message_count'] for x in contributions)}
    feedback=FeedbackService(app)
    reports=[]
    for r in app._all('report'):
        if r['room_id']!=room['id'] or r['kind']!='GROUP' or r['status']!='PUBLISHED':continue
        try:feedback._report_source_current(r,room)
        except DomainError:continue
        reports.append(r)
    if reports:
        r=reports[-1];result.update(status='PUBLISHED',report_id=r['id'],published_at=r.get('reviewed_at'),body=copy.deepcopy(r['body']))
    return result
