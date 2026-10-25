"""Append-only teacher adoption; the independent model baseline stays intact."""
import copy
from .domain import DomainError, identifier
from .observer import META, validate_candidate


def adopted(app, baseline):
    reviews=[r for r in app._all('assessment-review') if r['ai_baseline_id']==baseline['id']]
    if not reviews:return copy.deepcopy(baseline)
    review=reviews[-1]
    return {**copy.deepcopy(baseline),'id':review['id'],'ai_baseline_id':baseline['id'],
            'dimensions':copy.deepcopy(review['dimensions']),'assessment_source':'TEACHER_ADOPTED',
            'teacher_note':review['note'],'reviewed_at':review['created_at']}


class AssessmentReviews:
    def __init__(self,app):self.app=app

    def save(self,token,assessment_id,expected_adopted_id,dimensions,note):
        from .feedback import FeedbackService
        app=self.app
        with app.transaction():
            baseline=app._get(assessment_id);app._teacher(token,baseline.get('owner'))
            if baseline.get('status')!='VALIDATED' or 'dimensions' not in baseline:raise DomainError('ASSESSMENT_NOT_CURRENT',status=409)
            room=app._get(baseline['room_id']);context=FeedbackService(app)._context(room,baseline['participant_id'])
            if baseline['input_hash']!=context['input_hash'] or adopted(app,baseline)['id']!=expected_adopted_id:raise DomainError('ASSESSMENT_REVIEW_STALE',status=409)
            payload={k:baseline[k] for k in META+['knowledge_observations','limitations']};payload['dimensions']=dimensions
            checked=validate_candidate(context,payload)
            if not checked['ok']:raise DomainError('REVIEW_RULES_REJECTED:'+','.join(checked['errors']))
            if not isinstance(note,str) or not note.strip() or len(note)>2000:raise DomainError('REVIEW_NOTE_REQUIRED')
            prior=[r for r in app._all('assessment-review') if r['ai_baseline_id']==assessment_id]
            record={'id':identifier('assessment-review'),'owner':room['owner'],'room_id':room['id'],
                    'participant_id':baseline['participant_id'],'ai_baseline_id':assessment_id,
                    'previous_adopted_id':expected_adopted_id,'version':len(prior)+1,'input_hash':context['input_hash'],
                    'dimensions':copy.deepcopy(dimensions),'note':note.strip(),'created_at':app.clock(),'status':'ADOPTED'}
            app._put(record,'assessment-review');return record
