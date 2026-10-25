/* Same-origin engine only. Tokens never go to XIPU or a remote frontend. */
window.EngineAdapter=class {
  constructor(){this.token=sessionStorage.getItem('gm-token')||'';}
  async request(path,data){
    const r=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(this.token?{Authorization:'Bearer '+this.token}:{})},body:data===undefined?undefined:JSON.stringify(data)});
    const value=await r.json();if(!r.ok){const e=new Error(({"XIPU_API_NOT_CONFIGURED": "XIPU automatic generation is not connected yet. A valid API key for the unified workflow entry must be configured by the operator. Teacher review and existing reports remain available.", "API_TRANSPORT_FAILED": "Cannot reach the XIPU API. Check campus network / VPN. No generated result was saved.", "API_WORKFLOW_NOT_SUCCESSFUL": "XIPU did not return a successful run. The operator must check channel approval, key validity and the workflow.", "EXECUTION_PENDING_REVIEW": "This run is pending or uncertain. Ask the operator to check it before another request."})[value.error]||value.error||'Request failed');e.status=r.status;throw e;}return value;
  }
  async login(secret){const v=await this.request('/api/login',{secret});this.token=v.token;sessionStorage.setItem('gm-token',v.token);sessionStorage.setItem('gm-role','TEACHER');return v;}
  logout(){this.token='';sessionStorage.removeItem('gm-token');sessionStorage.removeItem('gm-role');}
  sessions(){return this.request('/api/v1/teacher/sessions');}
  rooms(){return this.request('/api/rooms');}
  createSession(data){return this.request('/api/v1/teacher/sessions',data);}
  dashboard(id){return this.request('/api/v1/teacher/sessions/'+encodeURIComponent(id)+'/dashboard');}
  group(id){return this.request('/api/v1/teacher/groups/'+encodeURIComponent(id));}
  context(id){return this.request('/api/v1/teacher/evidence/'+encodeURIComponent(id)+'/context');}
  report(id){return this.request('/api/v1/teacher/reports/'+encodeURIComponent(id));}
  review(data){return this.request('/api/v1/teacher/assessment-reviews',data);}
  revise(id,body){return this.request('/api/review/revise',{report_id:id,body});}
  publish(id){return this.request('/api/review/publish',{report_id:id});}
  task(data){return this.request('/api/review/task',data);}
  runTask(task_id){return this.request('/api/automation/run',{task_id});}
  importTask(task_id,output){return this.request('/api/review/import',{task_id,output});}
};
