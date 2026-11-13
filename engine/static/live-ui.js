'use strict';
// Reuse the established API and validated workflow, with the new twelve-page UI.
const liveMenus={TEACHER:['Overview','Case Setup','Activities','Group Monitor','Assessment','Reports'],STUDENT:['My Classroom','Case Materials','Preparation','Discussion','Reflection','My Feedback']};
let livePage=role==='TEACHER'?'Overview':'My Classroom';
let reportFilter='GROUP';
const liveBlocks=[];
document.querySelectorAll('header [onclick]').forEach(e=>e.removeAttribute('onclick'));
document.querySelectorAll('header .topnav button').forEach((b,i)=>b.onclick=()=>{if(i===3){notice('Start with Case Setup and Activities. Open a group to monitor discussion, then end it to review and publish feedback. Students prepare, discuss, reflect and view released feedback.');return;}livePage=token?(role==='TEACHER'?(i===0?'Overview':'Activities'):'My Classroom'):'Join classroom';paintLive();});
function place(el,pages){if(!el)return;el.classList.add('live-block');liveBlocks.push({el,pages});}
function liveButton(text,fn){const b=document.createElement('button');b.textContent=text;b.addEventListener('click',guard(fn));return b;}
// Existing nodes retain their listeners and field IDs when regrouped.
for(const el of [...$('teacher').children]){
 const id=el.id;
 const pages=id==='studio-summary'||id==='activity-library'||el.classList.contains('start-actions')?['Overview']:['course-context','source-studio','source-note','preparation-workflow'].includes(id)?['Case Setup']:id==='nodes'||id==='activity-preview'||id==='create-room'||el.classList.contains('actions')||el.classList.contains('teacher-help')?['Case Setup','Activities']:el.contains($('recent-rooms'))?['Group Monitor','Assessment','Reports']:['Case Setup'];
 place(el,pages);
}
// Discover AI preparation section by its actual controls, not a guessed ID.
for(const block of liveBlocks)if(block.el.contains($('run-prep')))block.pages=['Case Setup','Activities'];
place($('room').querySelector('.title'),['My Classroom','Group Monitor','Discussion','Assessment','Reports']);
place($('teacher-controls'),['Group Monitor']);
place($('brief').parentElement,['Case Materials','Group Monitor']);
$('brief').parentElement.open=true;
place($('goal-section'),['Preparation']);
place($('student-participation'),['My Classroom']);
const discussion=$('room').querySelector('.discussion');
for(const id of ['legacy-submission','reflection-section','feedback'])$('room').append($(id));
place(discussion,['Discussion','Group Monitor']);
place($('legacy-submission'),['Discussion']);
place($('reflection-section'),['Reflection']);
place($('feedback'),['My Feedback']);
const home=document.createElement('div');home.id='student-home';$('room').prepend(home);place(home,['My Classroom']);
const empty=document.createElement('p');empty.className='empty-state';$('workspace-main').append(empty);
const helper=document.createElement('div');helper.className='actions';$('review-workspace').prepend(helper);
helper.append(liveButton('Individual & group feedback',()=>{ $('review-kind').value='PERSONAL';$('review-kind').dispatchEvent(new Event('change'));$('manual-workflow').open=true;}),liveButton('Generate class summary',()=>{$('review-kind').value='CLASS';$('review-kind').dispatchEvent(new Event('change'));$('manual-workflow').open=true;}));
const exportButton=liveButton('Export displayed reports',()=>{
 if(!reviewData?.reports?.length)throw Error('No reports available for this group yet.');
 const data={activity:view.activity.title,group:view.name,reports:reviewData.reports.filter(r=>r.kind===reportFilter)};
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='groupmate-reports.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});helper.append(exportButton);
const filters=document.createElement('div');filters.className='report-filter';$('review-reports').before(filters);
for(const [kind,label] of [['PERSONAL','Individual feedback'],['GROUP','Group reports'],['CLASS','Class summary']])filters.append(liveButton(label,()=>{reportFilter=kind;paintLive();}));
const originalEvidenceLinks=evidenceLinks;evidenceLinks=function(ids,parent){originalEvidenceLinks(ids,parent);for(const b of parent.querySelectorAll('.evidence-link')){const action=b.onclick;b.onclick=async e=>{livePage=role==='TEACHER'?'Group Monitor':'Discussion';paintLive();await action(e);};}};
function liveNav(){
 const nav=$('workspace-navigation');nav.replaceChildren();
 const pages=token?(liveMenus[role]||[]):['Join classroom','Teacher sign in'];
 for(const p of pages){const b=liveButton(p,async()=>{livePage=p;paintLive();});b.className=livePage===p?'active':'secondary';b.setAttribute('aria-current',livePage===p?'page':'false');nav.append(b);}
 $('sideheading').textContent=token?(role==='TEACHER'?'TEACHER WORKSPACE':'STUDENT CLASSROOM'):'WELCOME';
 $('identity').textContent=token?(role==='TEACHER'?'Teacher':'Student'):'';$('live-signout').hidden=!token;
}
function paintLive(){
 liveNav();$('title').textContent=token?livePage:'Welcome to GroupMate AI';
 $('subtitle').textContent=token?'Prepare · Discuss · Reflect · Improve':'Join your classroom or sign in to prepare an activity.';
 $('entry').hidden=!!token;
 if(!token){$('student-entry').hidden=livePage==='Teacher sign in';$('teacher-entry').hidden=livePage!=='Teacher sign in';}
 const teacher=role==='TEACHER';
 $('teacher').hidden=!token||!teacher;
 $('room').hidden=!token||!roomId;
 for(const {el,pages} of liveBlocks)el.classList.toggle('page-off',!pages.includes(livePage));
 // Split the same activity editor across two simple pages; confirmations remain server-side.
 [...$('nodes').children].forEach((el,i)=>el.classList.toggle('page-off',livePage==='Case Setup'?i>2:livePage==='Activities'?i<3:true));
 $('review-workspace').classList.toggle('page-off',!teacher||!['Assessment','Reports'].includes(livePage));
 for(const card of $('review-reports').children)card.classList.toggle('page-off',card.dataset.reportKind!==reportFilter);
 filters.hidden=livePage!=='Reports';
 if(livePage==='Assessment')for(const card of $('review-reports').children)card.classList.remove('page-off');
 if(view&&roomId){
  $('goal-section').hidden=teacher;$('legacy-submission').hidden=teacher;
  $('student-participation').hidden=teacher;
  $('next-action-section').hidden=teacher||view.state!=='ENDED'||!view.my_learning?.reflection;
  home.replaceChildren();line(view.name,home,'h2');line('Activity: '+view.activity.title,home);line('Members: '+view.members.length+' · '+view.state,home);
  home.append(liveButton('Read case materials',()=>{livePage='Case Materials';paintLive();}),liveButton('Continue discussion',()=>{livePage='Discussion';paintLive();}));
 }
 const requiresRoom=teacher?['Assessment','Reports']:liveMenus.STUDENT;
 empty.hidden=!token||(!requiresRoom.includes(livePage))||!!roomId;
 empty.textContent=teacher?'Open a classroom group below to review its records. Reports become available after discussion ends.':'Join a classroom group to continue.';
 if(teacher&&roomId&&['Assessment','Reports'].includes(livePage)&&view?.state!=='ENDED'){empty.hidden=false;empty.textContent='Discussion is still open. End the group discussion in Group Monitor before generating or reviewing reports.';}
 if(!teacher&&roomId&&['Reflection','My Feedback'].includes(livePage)&&view?.state!=='ENDED'){empty.hidden=false;empty.textContent='This step opens after your teacher ends the discussion.';}
}
workspaceNavigation=function(){paintLive();};
const liveOriginalRender=renderDraft;renderDraft=function(){liveOriginalRender();for(const s of document.querySelectorAll('.design-step>summary'))s.textContent=s.textContent.replace(/^\d+\. /,'').replace(/ · Confirmation needed/,'').replace(/ · Confirmed/,' · Reviewed');paintLive();};
const liveOriginalRefresh=refresh;refresh=async function(){await liveOriginalRefresh();if(role==='STUDENT'&&reviewData&&!reviewData.reflection_required){$('student-reports').replaceChildren();for(const r of reviewData.reports.filter(r=>r.kind==='PERSONAL'&&r.status==='PUBLISHED'&&r.body)){const card=document.createElement('article');line('Your published feedback',card,'h3');renderReportBody(r.body,card);$('student-reports').append(card);}}paintLive();};
const liveOriginalShow=show;show=function(id){liveOriginalShow(id);if(id==='room')livePage=role==='TEACHER'?'Group Monitor':'Discussion';paintLive();};
for(const id of ['sample','new-blank']){const prior=$(id).onclick;$(id).onclick=async e=>{await prior(e);if(draft){livePage='Case Setup';paintLive();}};}
openSection=function(id){livePage=['nodes','activity-preview','create-room'].includes(id)?'Activities':id==='recent-rooms'?'Group Monitor':'Case Setup';paintLive();const el=$(id);if(el?.tagName==='DETAILS')el.open=true;el?.scrollIntoView({block:'start'});};
$('live-signout').onclick=()=>{for(const k of ['gm-token','gm-role','gm-room','gm-draft'])sessionStorage.removeItem(k);location.assign('/');};
// All teaching actions now use actual server state. Never render prototype sample records.
paintLive();
