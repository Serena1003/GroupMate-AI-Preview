"""Local classroom HTTP boundary; optional authorized role API, no public hosting."""
import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .domain import Classroom, DomainError
from .orchestrator import RoleOrchestrator
from .xipu import XipuWorkflowClient, XipuError
from .review import ReviewWorkspace
from .sources import Sources
from .preparation import Preparation
from .learning import Learning
from .manual_roles import ManualRoles
from .operations import Operations
from .dashboard import TeacherDashboard
from .assessment_reviews import AssessmentReviews

STATIC=Path(__file__).resolve().parent.parent/'static'


def make_server(app,owner_secret,host='127.0.0.1',port=8765,role_client=None,workflow_client=None):
    teacher=app.bootstrap_teacher(owner_secret)
    roles=RoleOrchestrator(app,teacher,role_client or workflow_client)
    review=ReviewWorkspace(app)
    sources=Sources(app);preparation=Preparation(app);learning=Learning(app);manual_roles=ManualRoles(app);operations=Operations(app)
    dashboard=TeacherDashboard(app);assessment_reviews=AssessmentReviews(app)
    class Handler(BaseHTTPRequestHandler):
        server_version='GroupMate/0.2'
        def log_message(self,*args): pass  # Never log session tokens or student text.
        def send_json(self,status,value):
            data=json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers(); self.wfile.write(data)
        def do_GET(self): self.handle_request(False)
        def do_POST(self): self.handle_request(True)
        def handle_request(self,post):
            try:
                parsed=urlparse(self.path); path=parsed.path
                if not path.startswith('/api/'):
                    if post: raise DomainError('METHOD_NOT_ALLOWED',status=405)
                    if path not in ['/','/app.js','/studio.js','/style.css','/manual.html','/teacher','/dashboard.css','/dashboard.js','/engine-adapter.js','/classroom-theme.css','/demo-guide','/demo-flow.png','/demo-guide.css']: raise DomainError('NOT_FOUND',status=404)
                    f=STATIC/('demo-guide.html' if path=='/demo-guide' else 'index.html' if path=='/' else 'dashboard.html' if path=='/teacher' else path[1:])
                    content=f.read_bytes()
                    self.send_response(200); self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','png':'image/png'}[f.suffix[1:]])
                    self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
                    self.end_headers(); self.wfile.write(content); return
                origin=self.headers.get('Origin')
                d={}
                if post:
                    if not self.headers.get('Content-Type','').startswith('application/json'): raise DomainError('JSON_REQUIRED',status=415)
                    size=int(self.headers.get('Content-Length','0'))
                    if size<1 or size>(29000000 if path in ['/api/sources/upload','/api/archives/restore'] else 200000): raise DomainError('BODY_SIZE_INVALID',status=413)
                    d=json.loads(self.rfile.read(size))
                    if not isinstance(d,dict): raise DomainError('OBJECT_REQUIRED')
                if origin and urlparse(origin).netloc!=self.headers.get('Host'):
                    self.close_connection=True
                    raise DomainError('ORIGIN_REJECTED',status=403)
                token=self.headers.get('Authorization','').removeprefix('Bearer ')
                if path=='/api/login' and post:
                    if not hmac.compare_digest(str(d.get('secret','')),owner_secret): raise DomainError('UNAUTHORIZED',status=401)
                    value={'token':teacher,'role':'TEACHER'}
                elif path=='/api/join-info' and not post:
                    with app.lock:
                        code=parse_qs(parsed.query).get('code',[''])[0].strip().upper()
                        found=[r for r in app._all('room') if r['join_code']==code]
                        if not found:raise DomainError('INVALID_JOIN_CODE',status=404)
                        room=found[0];packet=app._get(room['snapshot_id'])['packet'];value={'name':room['name'],'state':room['state'],'policy':packet.get('data_policy',{})}
                elif path=='/api/join' and post: value=app.join(d['code'],d['name'],d.get('notice_accepted',False))
                else:
                    if not token: raise DomainError('UNAUTHORIZED',status=401)
                    if path=='/api/v1/teacher/sessions':
                        value=dashboard.create_session(token,d['title'],d['room_ids'],d['data_mode']) if post else dashboard.sessions(token)
                    elif path.startswith('/api/v1/teacher/sessions/') and path.endswith('/dashboard') and not post:value=dashboard.dashboard(token,path.split('/')[-2])
                    elif path.startswith('/api/v1/teacher/groups/') and not post:value=dashboard.group(token,path.split('/')[-1])
                    elif path.startswith('/api/v1/teacher/evidence/') and path.endswith('/context') and not post:value=dashboard.evidence_context(token,path.split('/')[-2])
                    elif path.startswith('/api/v1/teacher/reports/') and not post:value=dashboard.report(token,path.split('/')[-1])
                    elif path=='/api/v1/teacher/assessment-reviews' and post:value=assessment_reviews.save(token,d['assessment_id'],d['expected_adopted_id'],d['dimensions'],d['note'])
                    elif path=='/api/sample' and not post:
                        with app.transaction(): app._teacher(token)
                        value=json.loads((Path(__file__).parent/'sample.json').read_text())
                    elif path=='/api/studio' and not post: value=preparation.library(token)
                    elif path=='/api/sources' and not post: value=sources.list(token)
                    elif path=='/api/source' and not post: value=sources.get(token,parse_qs(parsed.query)['source_id'][0])
                    elif path=='/api/sources/upload' and post: value=sources.upload(token,d['filename'],d['content'],d.get('first',1),d.get('last',1))
                    elif path=='/api/sources/search' and post: value=sources.search(token,d['query'])
                    elif path=='/api/preparation/task' and post: value=preparation.task(token,d['draft_id'],d['stage'],d['fields'],d.get('source_ids',[]),d.get('requirements',{}))
                    elif path=='/api/automation/status' and not post:
                        with app.lock: app._teacher(token)
                        value={'workflow_configured':bool(workflow_client),'role_configured':bool(role_client or workflow_client)}
                    elif path=='/api/automation/run' and post:
                        with app.lock:
                            task=app._get(d['task_id']);app._teacher(token,task['owner'])
                            if task['id'].startswith('prep-task-'): category='preparation'
                            elif task['id'].startswith('review-task-'): category='review'
                            elif task['id'].startswith('manual-role-'): category='role'
                            else: raise DomainError('INVALID_AUTOMATION_TASK')
                        client=(workflow_client or role_client) if category=='role' else workflow_client
                        if not client: raise DomainError('XIPU_API_NOT_CONFIGURED',status=503)
                        with app.transaction():
                            task=app._get(task['id'])
                            if task.get('execution',{}).get('status')=='COMPLETED':
                                self.send_json(200,task['execution']['result']);return
                            if task.get('execution',{}).get('status') in ['RUNNING','UNCERTAIN']: raise DomainError('EXECUTION_PENDING_REVIEW',status=409)
                            task['execution']={'status':'RUNNING'};app._put(task,category=='preparation' and 'prep-task' or category=='review' and 'review-task' or 'manual-role')
                        try:
                            response=client.run(task['input'],'gm-web')
                            result=(preparation if category=='preparation' else review if category=='review' else manual_roles).import_result(token,task['id'],response['value'])
                        except Exception:
                            with app.transaction():
                                task=app._get(task['id']);task['execution']={'status':'UNCERTAIN'};app._put(task,category=='preparation' and 'prep-task' or category=='review' and 'review-task' or 'manual-role')
                            raise
                        with app.transaction():
                            task=app._get(task['id']);result['provenance']='XIPU_OFFICIAL_API_VALIDATED_OUTPUT'
                            if category=='role':result['transport']='XIPU_OFFICIAL_API'
                            if category=='preparation':app._put(result,'proposal')
                            task['execution']={'status':'COMPLETED','result':result,'run_id':response.get('run_id'),'transport':'XIPU_OFFICIAL_API'};app._put(task,category=='preparation' and 'prep-task' or category=='review' and 'review-task' or 'manual-role')
                        value=result
                    elif path=='/api/preparation/import' and post: value=preparation.import_result(token,d['task_id'],d['output'])
                    elif path=='/api/preparation/decide' and post: value=preparation.decide(token,d['proposal_id'],d['decision'])
                    elif path=='/api/studio/reuse' and post: value=preparation.reuse(token,d['snapshot_id'])
                    elif path=='/api/manual-role/prepare' and post: value=manual_roles.prepare(token,d['room_id'],d['role_id'])
                    elif path=='/api/manual-role/import' and post: value=manual_roles.import_result(token,d['task_id'],d['output'])
                    elif path=='/api/learning' and post: value=learning.save(token,d['room_id'],d['field'],d['text'])
                    elif path=='/api/learning' and not post: value=learning.view(token,parse_qs(parsed.query)['room_id'][0])
                    elif path=='/api/help' and post: value=learning.help(token,d['room_id'],d['text'],d['kind'])
                    elif path=='/api/room/archive' and post: value=operations.archive_room(token,d['room_id'],d.get('archived',True))
                    elif path=='/api/archives/export' and post: value=operations.export_room(token,d['room_id'])
                    elif path=='/api/archives/restore' and post: value=operations.restore(token,d['bundle'])
                    elif path=='/api/archives' and not post: value=operations.library(token)
                    elif path=='/api/archive' and not post: value=operations.get(token,parse_qs(parsed.query)['archive_id'][0])
                    elif path=='/api/coverage' and not post:
                        with app.lock:app._teacher(token)
                        value=json.loads((Path(__file__).resolve().parents[1]/'docs/product-coverage.json').read_text())
                    elif path=='/api/drafts' and post: value=app.create_draft(token,d['packet'])
                    elif path=='/api/draft' and not post: value=app.get_draft(token,parse_qs(parsed.query)['draft_id'][0])
                    elif path=='/api/update' and post: value=app.update_draft(token,d['draft_id'],d['revision'],d['patch'])
                    elif path=='/api/confirm' and post: value=app.confirm(token,d['draft_id'],d['node'],d['revision'])
                    elif path=='/api/publish' and post: value=app.publish(token,d['draft_id'],d['revision'])
                    elif path=='/api/rooms' and post: value=app.create_room(token,d['snapshot_id'],d['name'])
                    elif path=='/api/rooms' and not post: value=review.rooms(token)
                    elif path=='/api/review' and not post: value=review.dashboard(token,parse_qs(parsed.query)['room_id'][0])
                    elif path=='/api/review/task' and post: value=review.create_task(token,d['room_id'],d['kind'],d.get('participant_id'),d.get('room_ids'))
                    elif path=='/api/review/task' and not post: value=review.get_task(token,parse_qs(parsed.query)['task_id'][0])
                    elif path=='/api/review/import' and post: value=review.import_result(token,d['task_id'],d['output'])
                    elif path=='/api/review/publish' and post: value=review.publish_report(token,d['report_id'])
                    elif path=='/api/review/revise' and post: value=review.revise_report(token,d['report_id'],d['body'])
                    elif path=='/api/review/conditions' and post: value=review.record_conditions(token,d['room_id'],d['participant_id'],d['conditions'])
                    elif path=='/api/room' and not post:
                        value=app.room_view(token,parse_qs(parsed.query)['room_id'][0])
                        value['ai_status']='API_CONFIGURED' if role_client or workflow_client else 'NOT_CONNECTED'
                    elif path=='/api/control' and post: value=app.control(token,d['room_id'],d['action'])
                    elif path=='/api/invite-role' and post: value=roles.invite(token,d['room_id'],d['role_id'],d['request_id'])
                    elif path=='/api/message' and post: value=app.message(token,d['room_id'],d['client_id'],d['text'],d.get('reply_to'))
                    elif path=='/api/submit' and post: value=app.submit(token,d['room_id'],d['raw'],d['expected_version'])
                    elif path=='/api/ack' and post: value=app.acknowledge(token,d['room_id'],d['version'],d['decision'])
                    elif path=='/api/goal' and post: value=app.set_goal(token,d['room_id'],d['text'])
                    elif path=='/api/reflection' and post: value=app.reflect(token,d['room_id'],d.get('text',''),d.get('skip',False))
                    elif path=='/api/model-context' and post: value=app.model_context(token,d['room_id'],d['kind'])
                    else: raise DomainError('NOT_FOUND',status=404)
                self.send_json(200,value)
            except XipuError as e: self.send_json(502,{'error':str(e)})
            except DomainError as e: self.send_json(e.status,{'error':e.code})
            except (KeyError,ValueError,TypeError): self.send_json(400,{'error':'INVALID_REQUEST'})
            except Exception: self.send_json(500,{'error':'INTERNAL_ERROR'})
    return ThreadingHTTPServer((host,port),Handler)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--port',type=int,default=8765); p.add_argument('--host',default='127.0.0.1'); args=p.parse_args()
    secret=os.environ.get('GROUPMATE_OWNER_SECRET')
    if not secret: raise SystemExit('请先设置 GROUPMATE_OWNER_SECRET（教师登录口令），不写入文件。')
    Path('data').mkdir(exist_ok=True); app=Classroom('data/classroom.sqlite')
    # Local secrets stay server-side; existing environment takes precedence.
    env_file=Path('.env')
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            name,sep,value=line.partition('=')
            if sep and name.strip() in ['GROUPMATE_XIPU_ROLE_KEY','GROUPMATE_XIPU_WORKFLOW_KEY']:
                os.environ.setdefault(name.strip(),value.strip().strip(chr(34)).strip(chr(39)))
    key=os.environ.get('GROUPMATE_XIPU_ROLE_KEY')
    server=make_server(app,secret,args.host,args.port,role_client=XipuWorkflowClient(key) if key else None,workflow_client=XipuWorkflowClient(os.environ['GROUPMATE_XIPU_WORKFLOW_KEY']) if os.environ.get('GROUPMATE_XIPU_WORKFLOW_KEY') else None)
    print('GroupMate local classroom: http://'+args.host+':'+str(args.port),flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); app.close()

if __name__=='__main__': main()
