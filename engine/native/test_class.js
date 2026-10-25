const assert=require('assert'),fs=require('fs'),vm=require('vm'),scope={};
vm.createContext(scope);vm.runInContext(fs.readFileSync(__dirname+'/class.js','utf8'),scope);
const context={workflow_binding:{task_id:'t',input_hash:'h',kind:'CLASS',room_id:'r',participant_id:null},statistics:[{stat_id:'stat-long-original'}],authorized_fragments:[{evidence_id:'evidence-long-original',text:'actual words'}],group_reports:[{body:{evidence_ids:['evidence-long-original']}}]};
const p=JSON.parse(JSON.stringify(scope.prepareClass(context)));
assert.equal(p.statistics[0].stat_id,'S1');assert.equal(p.authorized_fragments[0].evidence_id,'E1');assert.equal(p.group_reports[0].body.evidence_ids[0],'E1');
const keys=['activity_evidence_scope','knowledge_application','dimension_commonalities','key_issues','representative_fragments','follow_up_teaching_suggestions'];
const value={workflow_binding:context.workflow_binding,body:{sections:keys.map(key=>({key,text:'Synthetic',claims:[{text:'Synthetic claim',stat_ids:['S1'],evidence_ids:['E1'],counterexample_ids:[],limitations:[]}]})),limitations:[]}};
const good=scope.validateClass(context,value);assert.equal(good.ok,true);assert.equal(good.body.sections[0].claims[0].stat_ids[0],'stat-long-original');assert.equal(good.body.sections[0].claims[0].evidence_ids[0],'evidence-long-original');
for(const bad of [()=>{value.workflow_binding={...context.workflow_binding,task_id:'old'}},()=>{value.workflow_binding=context.workflow_binding;value.body.sections[0].claims[0].stat_ids=['S99']},()=>{value.body.sections=[]}]){bad();const result=scope.validateClass(context,value);assert.equal(result.ok,false);assert.equal(result.body,null);}
console.log('6 native class reference/binding contract checks passed');
