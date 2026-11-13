/* One click, saved stages, explicit teacher publication. */
window.GroupMateFeedbackBatch={
 async generate(request,roomId,progress=()=>{}){
  let group=await request('/api/v1/teacher/groups/'+encodeURIComponent(roomId));
  if(group.state!=='ENDED')throw Error('End the discussion before generating feedback.');
  if(!group.members.length)throw Error('This group has no students to assess.');
  const stage=async(kind,participant_id=null)=>{
   const task=await request('/api/review/task',{room_id:roomId,kind,participant_id,require_teacher_review:true});
   return request('/api/automation/run',{task_id:task.id});
  };
  const review=await request('/api/review?room_id='+encodeURIComponent(roomId));
  if(!review.tasks.some(t=>t.kind==='EVIDENCE'&&t.status==='IMPORTED')){
   progress('Step 1/3 · Extracting discussion evidence…');await stage('EVIDENCE');
  }
  group=await request('/api/v1/teacher/groups/'+encodeURIComponent(roomId));
  for(let i=0;i<group.members.length;i++){
   const member=group.members[i];progress('Step 2/3 · All selected dimensions · '+member.name+' ('+(i+1)+'/'+group.members.length+')…');
   if(!group.assessments.some(a=>a.participant_id===member.id))await stage('ASSESSMENT',member.id);
  }
  group=await request('/api/v1/teacher/groups/'+encodeURIComponent(roomId));
  progress('Step 3/3 · Generating the group summary…');
  if(!group.reports.some(r=>r.kind==='GROUP'&&['DRAFT','PUBLISHED'].includes(r.status)))await stage('GROUP');
  return request('/api/v1/teacher/groups/'+encodeURIComponent(roomId));
 }
};
