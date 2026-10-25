"""Deterministic readiness and fail-closed checks; never assigns observed levels."""
import copy

DIMENSIONS = ['C1','C2','C3','C4','C5','C6']
META = ['snapshot_id','frozen_log_id','participant_id','input_hash','rubric_version']
DETAIL = {'dimension','status','level','evidence_ids','counter_evidence_ids','explanation','limitations'}
STATUSES = {'NOT_SELECTED','DATA_INCOMPLETE','INSUFFICIENT_OPPORTUNITY','INSUFFICIENT_EVIDENCE','OBSERVED'}
SAFE_INPUT = META + ['room_id','public_case','events','messages','selected_dimensions','rubric','knowledge','verified_evidence','data_complete','opportunity','limitations','help_exposures']


def strings(value):
    return isinstance(value,list) and all(isinstance(v,str) and v.strip() for v in value)


def anchors_for(context,dimension):
    rubric=context.get('rubric')
    if not isinstance(rubric,dict): return None
    hits=[r.get('levels') for r in rubric.get('dimensions',[]) if isinstance(r,dict) and r.get('dimension')==dimension]
    if len(hits)!=1: return None
    a=hits[0]
    return a if isinstance(a,dict) and set(a)=={'1','2','3','4'} and all(isinstance(t,str) and t.strip() for t in a.values()) else None


def owned_evidence(context):
    return {e.get('evidence_id',e.get('id')):e for e in context.get('verified_evidence',[]) if isinstance(e,dict) and e.get('participant_id')==context.get('participant_id') and (e.get('validation')=='VALID' or e.get('validation_status')=='VALID') and isinstance(e.get('quote',e.get('exact_quote')),str) and e.get('quote',e.get('exact_quote')) and e.get('evidence_id',e.get('id'))}


def prepare(context):
    safe={k:copy.deepcopy(context[k]) for k in SAFE_INPUT if k in context}
    evidence=owned_evidence(safe)
    constraints=[]; dimensions=[]
    for dim in DIMENSIONS:
        status=None; code='MODEL_JUDGMENT'; explanation='需对照原文锚点与本人的已核证据判断；当前模板不代表模型评价。'
        if dim not in safe.get('selected_dimensions',[]):
            status='NOT_SELECTED'; code='NOT_SELECTED'; explanation='教师本次未选择此维度。'
        elif not anchors_for(safe,dim):
            status='DATA_INCOMPLETE'; code='MISSING_RUBRIC'; explanation='此维度四档量表原文缺失或不完整，不能定级。'
        elif safe.get('data_complete') is False:
            status='DATA_INCOMPLETE'; code='INCOMPLETE_RECORD'; explanation='讨论记录不完整，不能可靠定级。'
        elif safe.get('opportunity',{}).get(dim)=='NONE':
            status='INSUFFICIENT_OPPORTUNITY'; code='CONFIRMED_NO_OPPORTUNITY'; explanation='教师记录确认本次没有适当展示机会，不能视为低能力。'
        elif not evidence:
            status='INSUFFICIENT_EVIDENCE'; code='NO_VERIFIED_EVIDENCE'; explanation='没有本人已核证据；未表达不等于低能力，也不自动等于缺少机会。'
        constraints.append({'dimension':dim,'required_status':status,'reason_code':code})
        dimensions.append({'dimension':dim,'status':status or 'INSUFFICIENT_EVIDENCE','level':None,'evidence_ids':[],'counter_evidence_ids':[],'explanation':explanation,'limitations':[] if code in ['NOT_SELECTED','MODEL_JUDGMENT'] else [code]})
    return {'context':safe,'dimension_constraints':constraints,'template':{**{k:safe.get(k) for k in META},'dimensions':dimensions,'knowledge_observations':[],'limitations':copy.deepcopy(safe.get('limitations',[]))}}


def validate_candidate(context,value):
    errors=[]; expected=set(META)|{'dimensions','knowledge_observations','limitations'}
    if not isinstance(value,dict) or set(value)!=expected:
        return {'ok':False,'errors':['TOP_LEVEL_FIELDS'],'assessment':None}
    if any(not isinstance(context.get(k),str) or not context[k] or value.get(k)!=context[k] for k in META): errors.append('METADATA')
    dimensions=value.get('dimensions'); constraints={d['dimension']:d for d in prepare(context)['dimension_constraints']}; registry=owned_evidence(context)
    if not isinstance(dimensions,list) or len(dimensions)!=6: errors.append('SIX_DIMENSIONS_REQUIRED')
    seen=set()
    for item in dimensions if isinstance(dimensions,list) else []:
        if not isinstance(item,dict) or set(item)!=DETAIL: errors.append('DIMENSION_FIELDS'); continue
        dim=item['dimension']
        if not isinstance(dim,str) or dim not in DIMENSIONS or dim in seen: errors.append('DIMENSION_ID'); continue
        seen.add(dim); status=item['status']; required=constraints[dim]['required_status']
        if not isinstance(status,str) or status not in STATUSES or (required and status!=required) or (not required and status=='NOT_SELECTED') or (status=='INSUFFICIENT_OPPORTUNITY' and context.get('opportunity',{}).get(dim)=='PRESENT'): errors.append('STATUS_'+dim)
        if not isinstance(item['explanation'],str) or not item['explanation'].strip() or not strings(item['limitations']): errors.append('EXPLANATION_'+dim)
        for key in ['evidence_ids','counter_evidence_ids']:
            ids=item[key]
            if not strings(ids) or any(eid not in registry for eid in ids) or len(ids)!=len(set(ids)): errors.append('EVIDENCE_'+dim)
        if status=='OBSERVED':
            if type(item['level']) is not int or not 1<=item['level']<=4 or not item['evidence_ids'] or not anchors_for(context,dim): errors.append('LEVEL_'+dim)
        elif item['level'] is not None: errors.append('LEVEL_'+dim)
    knowledge=value['knowledge_observations']
    if not isinstance(knowledge,list): errors.append('KNOWLEDGE')
    else:
        for item in knowledge:
            if not isinstance(item,dict) or set(item)!={'tag','status','evidence_ids','explanation'}: errors.append('KNOWLEDGE'); continue
            if not isinstance(item['tag'],str) or item['tag'] not in context.get('knowledge',[]) or item['status'] not in ['SUPPORTED','MISUSE','NOT_OBSERVED','UNCERTAIN'] or not strings(item['evidence_ids']) or any(eid not in registry for eid in item['evidence_ids']) or not isinstance(item['explanation'],str) or not item['explanation'].strip() or (item['status'] in ['SUPPORTED','MISUSE'] and not item['evidence_ids']): errors.append('KNOWLEDGE')
    if not strings(value['limitations']): errors.append('LIMITATIONS')
    return {'ok':not errors,'errors':sorted(set(errors)),'assessment':copy.deepcopy(value) if not errors else None}
