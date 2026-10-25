"""Build final staged entry from native Workflow/Condition/VariableMerge export."""
import copy,json
from pathlib import Path
root=Path(__file__).resolve().parents[3]
out=root/'outputs/groupmate-native-20261024'
base=json.loads((Path(__file__).parent/'release-template.json').read_text())
manifest=json.loads((out/'platform-manifest.json').read_text())
children=[('SOURCE','WF01','01 · 资料与案例'),('DESIGN','WF02','02 · 教学活动设计'),('ROLE','WF03','03 · 单角色互动'),('EVIDENCE','WF04A','04 · 原文证据'),('ASSESSMENT','WF04B','05 · 独立Observer'),('FEEDBACK','WF04C','06 · 个人或小组反馈'),('CLASS','WF05','07 · 教师班级报告')]
help_text={'product':'GroupMate AI · IBSS课堂最终演示版 v1.0','mode':'MANUAL_STAGED_WORKFLOWS','instructions':['先打开本机教学工作室 http://127.0.0.1:8765/，由教师选择实际步骤并准备输入。','把工作室导出的完整JSON粘贴到本工作流input，不额外添加提示词，点击运行。','复制最终运行结果中output对应的完整JSON内容，粘贴回原任务的结果框；模型结果仍由教师确认/审核。','备课：资料/案例→活动设计→九项确认→发布活动并建组。','讨论：学生先保存目标/策略并发言，教师准备单角色输入→运行→导回；每次保留学生回应机会。','课后：冻结→一次证据提取→逐人Observer→逐人个人反馈；小组报告每组一次；教师班级报告按选定范围运行。','学生自评或明确跳过后查看本人已发布反馈，再保存下一步计划。'],'limits':['本入口不保存共享课堂、原始发言或私人学习记录，需配合工作室。','API仍待审批，不因本工作流发布而自动开放。','输入help:true可重新查看本说明；不作正式成绩或排名。']}
router='''function handler(params) {
 const p=JSON.parse(params.input), b=p.workflow_binding||{};let stage='HELP';
 if(b.stage==='SOURCE'||b.stage==='DESIGN')stage=b.stage;
 else if(p.assigned_role&&p.public_facts)stage='ROLE';
 else if(b.kind==='CLASS')stage='CLASS';
 else if(p.mode==='PERSONAL'||p.mode==='GROUP')stage='FEEDBACK';
 else if(p.participant_id&&p.verified_evidence&&p.input_hash)stage='ASSESSMENT';
 else if(Array.isArray(p.participants)&&Array.isArray(p.messages))stage='EVIDENCE';
 return {stage,payload:JSON.stringify(p)};
}'''
def ref(name,node,path):return {'Name':name,'RefType':'node_field','NodeCode':node,'Path':path}
def node(code,name,kind,config,x,y,depends=None):
 n={'Code':code,'ID':code,'Name':name,'Type':kind,'Configs':{kind:config},'Layout':{'X':x,'Y':y},'ErrorConfig':{'ErrorConfigType':'None'}}
 if depends:n['Depends']=depends
 return n
base['ID']=base['UniqueName']='groupmate_ibss_final_manual_v1'
base['Nodes']=[];base['Depends']['WorkflowMap']={}
base['DisplayName']='GroupMate AI · IBSS课堂最终演示版 v1.0'
base['Desc']='统一人工运行入口：自动识别工作室输入，按阶段调用7个已发布子工作流。配合课堂工作室完成教师确认、真人讨论、SRL和报告审核。input填{"help":true}查看说明。API未自动开通。'
schema=[{'Name':'input','Type':0,'Required':True,'Desc':'粘贴本机教学工作室准备的完整JSON；或填 {"help":true} 查看人工使用说明。'}]
ns=base['Nodes'];ns.append(node('start','Start','Start',{'InputSchema':schema,'OutputSchema':schema},0,500))
ns.append(node('route','识别当前教学步骤','Code',{'Code':router,'Language':0,'InputVariables':[ref('input','start','input')],'OutputSchema':[{'Name':'stage','Type':0},{'Name':'payload','Type':0}],'Retries':0,'TimeoutSeconds':120},450,500,[{'NodeCode':'start'}]))
branches=[]
for i,(stage,prefix,label) in enumerate(children):
 branches.append({'ID':'if'+str(i+1),'ConditionLogic':'AND','Conditions':[{'Left':ref('Left','route','stage'),'Operator':'EQ','Right':{'Name':'Right','RefType':'value','JsonValue':json.dumps(stage)}}]})
ns.append(node('choose','只运行当前阶段','Condition',{'IfBranches':branches,'ElseBranch':{'ID':'else'}},900,500,[{'NodeCode':'route'}]))
merge=[]
for i,(stage,prefix,label) in enumerate(children):
 m=next(v for v in manifest['items'] if v['name'].startswith(prefix+' '));wid=m['workflow_id'];dep={'ID':wid,'Name':m['name'],'Desc':'GroupMate已发布课堂子模块','LogoPath':'','ResourceWorkspaceID':'personal-Yongqian.Sun23'};base['Depends']['WorkflowMap'][wid]=dep
 cfg={'WorkflowID':wid,'Name':m['name'],'Description':dep['Desc'],'Icon':'','InputSchema':[{'Name':'input','Type':0,'Required':True}],'InputVariables':[ref('input','route','payload')],'OutputSchema':[{'Name':'output','Type':0}]}
 code='step_'+stage.lower();ns.append(node(code,label,'Workflow',cfg,1400,i*220,[{'NodeCode':'choose','PortID':'if'+str(i+1)}]));merge.append(ref('output['+str(i)+']',code,'output'))
ns.append(node('help','人工操作说明','Code',{'Code':'function handler(params){return {output:'+json.dumps(json.dumps(help_text,ensure_ascii=False),ensure_ascii=False)+'};}','Language':0,'InputVariables':[],'OutputSchema':[{'Name':'output','Type':0}],'Retries':0,'TimeoutSeconds':120},1400,1540,[{'NodeCode':'choose','PortID':'else'}]));merge.append(ref('output[7]','help','output'))
ns.append(node('merge','统一结果出口','VariableMerge',{'Groups':[{'Name':'output','Type':0,'Variables':merge}]},1950,650,[{'NodeCode':r['NodeCode']} for r in merge]))
ns.append(node('end','End','End',{'InputVariables':[ref('output','merge','output')],'OutputType':'Variable'},2400,650,[{'NodeCode':'merge'}]))
(out/'GroupMate-final-v1-import.yaml').write_text(json.dumps(base,ensure_ascii=False,indent=2))
(out/'GroupMate-final-help.json').write_text(json.dumps(help_text,ensure_ascii=False,indent=2))
print('Built final entry with',len(ns),'nodes and',len(children),'published children')
