// Pure deterministic checks, shared fixtures with groupmate/observer.py.
const DIMS=['C1','C2','C3','C4','C5','C6'];
const META=['snapshot_id','frozen_log_id','participant_id','input_hash','rubric_version'];
const DETAIL=['dimension','status','level','evidence_ids','counter_evidence_ids','explanation','limitations'];
const SAFE=META.concat(['room_id','public_case','events','messages','selected_dimensions','rubric','knowledge','verified_evidence','data_complete','opportunity','limitations','help_exposures']);
const statuses=['NOT_SELECTED','DATA_INCOMPLETE','INSUFFICIENT_OPPORTUNITY','INSUFFICIENT_EVIDENCE','OBSERVED'];
function obj(v){return v!==null&&typeof v==='object'&&!Array.isArray(v);}
function clone(v){return JSON.parse(JSON.stringify(v));}
function strings(v){return Array.isArray(v)&&v.every(s=>typeof s==='string'&&s.trim());}
function fields(v,keys){return obj(v)&&Object.keys(v).sort().join('|')===keys.slice().sort().join('|');}
function anchorsFor(c,d){
  const hits=obj(c.rubric)&&Array.isArray(c.rubric.dimensions)?c.rubric.dimensions.filter(r=>obj(r)&&r.dimension===d):[];
  return hits.length===1&&fields(hits[0].levels,['1','2','3','4'])&&Object.values(hits[0].levels).every(t=>typeof t==='string'&&t.trim())?hits[0].levels:null;
}
function ownedEvidence(c){
  const result={};
  for(const e of c.verified_evidence||[]){
    if(!obj(e))continue;
    const id=e.evidence_id||e.id,quote=e.quote||e.exact_quote;
    if(id&&e.participant_id===c.participant_id&&(e.validation==='VALID'||e.validation_status==='VALID')&&typeof quote==='string'&&quote)result[id]=e;
  }
  return result;
}
function prepare(c){
  const safe={};for(const k of SAFE)if(k in c)safe[k]=clone(c[k]);
  const evidence=ownedEvidence(safe),constraints=[],dimensions=[];
  for(const dimension of DIMS){
    let status=null,code='MODEL_JUDGMENT',explanation='需对照原文锚点与本人的已核证据判断；当前模板不代表模型评价。';
    if(!(safe.selected_dimensions||[]).includes(dimension)){
      status='NOT_SELECTED';code='NOT_SELECTED';explanation='教师本次未选择此维度。';
    }else if(!anchorsFor(safe,dimension)){
      status='DATA_INCOMPLETE';code='MISSING_RUBRIC';explanation='此维度四档量表原文缺失或不完整，不能定级。';
    }else if(safe.data_complete===false){
      status='DATA_INCOMPLETE';code='INCOMPLETE_RECORD';explanation='讨论记录不完整，不能可靠定级。';
    }else if((safe.opportunity||{})[dimension]==='NONE'){
      status='INSUFFICIENT_OPPORTUNITY';code='CONFIRMED_NO_OPPORTUNITY';explanation='教师记录确认本次没有适当展示机会，不能视为低能力。';
    }else if(!Object.keys(evidence).length){
      status='INSUFFICIENT_EVIDENCE';code='NO_VERIFIED_EVIDENCE';explanation='没有本人已核证据；未表达不等于低能力，也不自动等于缺少机会。';
    }
    constraints.push({dimension,required_status:status,reason_code:code});
    dimensions.push({dimension,status:status||'INSUFFICIENT_EVIDENCE',level:null,evidence_ids:[],counter_evidence_ids:[],explanation,limitations:['NOT_SELECTED','MODEL_JUDGMENT'].includes(code)?[]:[code]});
  }
  const template={};for(const k of META)template[k]=safe[k]??null;
  Object.assign(template,{dimensions,knowledge_observations:[],limitations:clone(safe.limitations||[])});
  return {context:safe,dimension_constraints:constraints,template};
}
function validateCandidate(c,value){
  let errors=[];
  if(!fields(value,META.concat(['dimensions','knowledge_observations','limitations'])))return{ok:false,errors:['TOP_LEVEL_FIELDS'],assessment:null};
  if(META.some(k=>typeof c[k]!=='string'||!c[k]||value[k]!==c[k]))errors.push('METADATA');
  const dimensions=value.dimensions,constraints=prepare(c).dimension_constraints,registry=ownedEvidence(c),seen=new Set();
  if(!Array.isArray(dimensions)||dimensions.length!==6)errors.push('SIX_DIMENSIONS_REQUIRED');
  for(const item of Array.isArray(dimensions)?dimensions:[]){
    if(!fields(item,DETAIL)){errors.push('DIMENSION_FIELDS');continue;}
    const d=item.dimension;
    if(!DIMS.includes(d)||seen.has(d)){errors.push('DIMENSION_ID');continue;}
    seen.add(d);const required=constraints.find(x=>x.dimension===d).required_status;
    if(!statuses.includes(item.status)||(required&&item.status!==required)||(!required&&item.status==='NOT_SELECTED')||(item.status==='INSUFFICIENT_OPPORTUNITY'&&(c.opportunity||{})[d]==='PRESENT'))errors.push('STATUS_'+d);
    if(typeof item.explanation!=='string'||!item.explanation.trim()||!strings(item.limitations))errors.push('EXPLANATION_'+d);
    for(const k of ['evidence_ids','counter_evidence_ids'])if(!strings(item[k])||item[k].some(id=>!Object.hasOwn(registry,id))||new Set(item[k]).size!==item[k].length)errors.push('EVIDENCE_'+d);
    if(item.status==='OBSERVED'){
      if(!Number.isInteger(item.level)||item.level<1||item.level>4||!item.evidence_ids.length||!anchorsFor(c,d))errors.push('LEVEL_'+d);
    }else if(item.level!==null)errors.push('LEVEL_'+d);
  }
  if(!Array.isArray(value.knowledge_observations))errors.push('KNOWLEDGE');
  else for(const item of value.knowledge_observations){
    if(!fields(item,['tag','status','evidence_ids','explanation'])){errors.push('KNOWLEDGE');continue;}
    if(!(c.knowledge||[]).includes(item.tag)||!['SUPPORTED','MISUSE','NOT_OBSERVED','UNCERTAIN'].includes(item.status)||!strings(item.evidence_ids)||item.evidence_ids.some(id=>!Object.hasOwn(registry,id))||typeof item.explanation!=='string'||!item.explanation.trim()||(['SUPPORTED','MISUSE'].includes(item.status)&&!item.evidence_ids.length))errors.push('KNOWLEDGE');
  }
  if(!strings(value.limitations))errors.push('LIMITATIONS');
  errors=Array.from(new Set(errors)).sort();
  return {ok:!errors.length,errors,assessment:errors.length?null:clone(value)};
}
