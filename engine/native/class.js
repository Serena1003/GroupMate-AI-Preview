// Exact alias mapping: never repair unknown model references by similarity.
const CLASS_KEYS=['activity_evidence_scope','knowledge_application','dimension_commonalities','key_issues','representative_fragments','follow_up_teaching_suggestions'];
function classClone(v){return JSON.parse(JSON.stringify(v));}
function classMaps(c){return {stats:Object.fromEntries((c.statistics||[]).map((s,i)=>['S'+(i+1),s.stat_id])),evidence:Object.fromEntries((c.authorized_fragments||[]).map((e,i)=>['E'+(i+1),e.evidence_id]))};}
function classEqual(a,b){if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;const ka=Object.keys(a).sort(),kb=Object.keys(b).sort();return ka.join('|')===kb.join('|')&&ka.every(k=>classEqual(a[k],b[k]));}
function prepareClass(c){const m=classMaps(c),reverse={};for(const v of Object.values(m))for(const [alias,id] of Object.entries(v))reverse[id]=alias;function walk(v){if(typeof v==='string')return reverse[v]||v;if(Array.isArray(v))return v.map(walk);if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,walk(x)]));return v;}return walk(c);}
function validateClass(c,candidate){
  const errors=[],m=classMaps(c);let v;
  try{
    v=classClone(candidate);
    if(!classEqual(v.workflow_binding,c.workflow_binding)||Object.keys(v).sort().join('|')!=='body|workflow_binding')errors.push('BINDING');
    const b=v.body;
    if(!b||Object.keys(b).sort().join('|')!=='limitations|sections'||!Array.isArray(b.limitations)||b.limitations.some(s=>typeof s!=='string'||!s.trim())||!Array.isArray(b.sections)||b.sections.length!==6)errors.push('SIX_SECTIONS');
    for(const [i,s] of (b?.sections||[]).entries()){
      if(s.key!==CLASS_KEYS[i]||Object.keys(s).sort().join('|')!=='claims|key|text'||typeof s.text!=='string'||!Array.isArray(s.claims)){errors.push('SECTION');continue;}
      for(const claim of s.claims){
        if(Object.keys(claim).sort().join('|')!=='counterexample_ids|evidence_ids|limitations|stat_ids|text'||typeof claim.text!=='string'||!claim.text.trim()||!Array.isArray(claim.limitations)||claim.limitations.some(s=>typeof s!=='string'||!s.trim()))errors.push('CLAIM');
        for(const k of ['stat_ids','evidence_ids','counterexample_ids']){
          const registry=k==='stat_ids'?m.stats:m.evidence;
          if(!Array.isArray(claim[k])||claim[k].some(id=>!Object.prototype.hasOwnProperty.call(registry,id))){errors.push('REFERENCE');continue;}
          claim[k]=claim[k].map(id=>registry[id]);
        }
      }
    }
  }catch(e){errors.push('JSON_SHAPE');}
  return {ok:!errors.length,errors:Array.from(new Set(errors)),workflow_binding:c.workflow_binding,body:errors.length?null:v.body};
}
