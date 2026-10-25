import copy
import json
import tempfile
import unittest
from pathlib import Path

try:
    from groupmate.domain import Classroom, DomainError
except ImportError:
    Classroom = None
    class DomainError(Exception):
        pass


def packet():
    return {
        'title': 'IOM420 Like-for-Like',
        'goals': ['识别相关者及参与差距'],
        'case': {'public': '统一更新打印机硬件和驱动。', 'teacher_only': '原书延期两年。', 'unknowns': ['完整预算']},
        'roles': [{'id': 'maya', 'name': 'Maya', 'background': '业务代表', 'authority': '仅代表本部门', 'conditions': '明确影响后可条件支持'}],
        'questions': ['如何更新参与安排？'],
        'task': ['一句判断', '三类相关者', '两项行动', '一项未决问题'],
        'assessment': {'selected': ['C2', 'C3', 'C4'], 'rubric_version': 'md-v1.1', 'knowledge': ['授权', '参与差距']},
        'runtime': {'seconds': 900, 'event_at': 360, 'event_enabled': True, 'event_text': '提案改用按使用量计费，尚未批准。'},
        'feedback': {'mode': 'review', 'allow_skip': True, 'share_group': True},
        'source': {'route': 'TEACHER_CASE', 'references': ['Worsley Case 3.3 pp49–50 PDF62–63'], 'simulation': ['人物与事件时点']},
    }


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Classroom, '尚未实现Classroom权威状态服务')
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'classroom.sqlite')
        self.now = 1000.0
        self.app = Classroom(self.db, clock=lambda: self.now)
        self.teacher = self.app.bootstrap_teacher('test-owner')

    def tearDown(self):
        if hasattr(self, 'app'):
            self.app.close()
        if hasattr(self, 'tmp'):
            self.tmp.cleanup()

    def publish(self):
        d = self.app.create_draft(self.teacher, packet())
        for n in range(1, 10):
            d = self.app.confirm(self.teacher, d['id'], n, d['revision'])
        return self.app.publish(self.teacher, d['id'], d['revision'])

    def room(self):
        s = self.publish()
        r = self.app.create_room(self.teacher, s['id'], 'A组')
        a = self.app.join(r['join_code'], '蓝舟')
        b = self.app.join(r['join_code'], '蓝舟')
        self.app.control(self.teacher, r['id'], 'start')
        return r, a, b

    def test_invalid_nested_packet_cannot_publish(self):
        for key in ['unknowns','event_text','role_id']:
            with self.subTest(key=key):
                p=packet()
                if key=='unknowns': del p['case']['unknowns']
                elif key=='event_text': del p['runtime']['event_text']
                else: del p['roles'][0]['id']
                d=self.app.create_draft(self.teacher,p)
                for n in range(1,10): self.app.confirm(self.teacher,d['id'],n,1)
                with self.assertRaises(DomainError): self.app.publish(self.teacher,d['id'],1)

    def test_role_context_contains_only_assigned_card(self):
        p=packet(); p['roles'].append({'id':'ethan','name':'Ethan','background':'IT implementation','authority':'IT','conditions':'OTHER_ROLE_SECRET'})
        d=self.app.create_draft(self.teacher,p)
        for n in range(1,10): self.app.confirm(self.teacher,d['id'],n,1)
        snap=self.app.publish(self.teacher,d['id'],1)
        r=self.app.create_room(self.teacher,snap['id'],'A')
        self.app.control(self.teacher,r['id'],'start')
        context=self.app.role_context(self.teacher,r['id'],'maya')
        raw=json.dumps(context,ensure_ascii=False)
        self.assertEqual(context['assigned_role']['id'],'maya')
        self.assertNotIn('OTHER_ROLE_SECRET',raw)
        self.assertNotIn('teacher_only',raw)
        with self.assertRaises(DomainError): self.app.role_context(self.teacher,r['id'],'missing')

    def test_stale_role_output_not_delivered_after_pause(self):
        r,a,b=self.room()
        self.app.message(a['token'],r['id'],'m','我的建议')
        job=self.app.role_context(self.teacher,r['id'],'maya')
        self.app.control(self.teacher,r['id'],'pause')
        with self.assertRaises(DomainError): self.app.deliver_role(self.teacher,r['id'],job,'请说明本部门的业务影响。')
        self.assertFalse([e for e in self.app.room_view(a['token'],r['id'])['events'] if e.get('author_type')=='AI'])

    def test_role_result_idempotency_and_student_cannot_impersonate(self):
        r,a,b=self.room()
        self.app.message(a['token'],r['id'],'m','我的建议')
        job=self.app.role_context(self.teacher,r['id'],'maya')
        with self.assertRaises(DomainError): self.app.deliver_role(a['token'],r['id'],job,'冒充')
        first=self.app.deliver_role(self.teacher,r['id'],job,'请说明本部门的业务影响。')
        second=self.app.deliver_role(self.teacher,r['id'],job,'请说明本部门的业务影响。')
        self.assertEqual(first,second)

    def test_expired_rejected_writes_still_persist_deadline(self):
        for operation in ['submit', 'acknowledge']:
            with self.subTest(operation=operation):
                r,a,b=self.room()
                self.app.submit(a['token'],r['id'],'原始建议',0)
                self.now+=901
                with self.assertRaises(DomainError):
                    if operation=='submit':
                        self.app.submit(a['token'],r['id'],'截止后修改',1)
                    else:
                        self.app.acknowledge(b['token'],r['id'],1,'agree')
                stored=json.loads(self.app.db.execute('SELECT body FROM objects WHERE id=?',(r['id'],)).fetchone()[0])
                self.assertEqual(stored['state'],'ENDED')
                self.assertEqual(stored['frozen_submission']['raw'],'原始建议')
                self.assertFalse(stored['frozen_submission']['acks'])

    def test_publish_requires_current_confirmations(self):
        d = self.app.create_draft(self.teacher, packet())
        with self.assertRaises(DomainError):
            self.app.publish(self.teacher, d['id'], d['revision'])

    def test_case_change_invalidates_confirmations(self):
        d = self.app.create_draft(self.teacher, packet())
        for n in range(1,10):
            d = self.app.confirm(self.teacher,d['id'],n,d['revision'])
        d = self.app.update_draft(self.teacher,d['id'],d['revision'],{'case':{'public':'新的业务情境','teacher_only':'私有结局','unknowns':[]}})
        self.assertFalse(d['confirmations'])
        with self.assertRaises(DomainError): self.app.publish(self.teacher,d['id'],d['revision'])

    def test_revision_conflict_preserves_teacher_edit(self):
        d = self.app.create_draft(self.teacher,packet())
        self.app.update_draft(self.teacher,d['id'],d['revision'],{'title':'教师手改'})
        with self.assertRaises(DomainError): self.app.update_draft(self.teacher,d['id'],d['revision'],{'title':'陈旧覆盖'})
        self.assertEqual(self.app.get_draft(self.teacher,d['id'])['packet']['title'],'教师手改')

    def test_snapshot_immutable_when_draft_changes(self):
        s = self.publish()
        d = self.app.get_draft(self.teacher,s['draft_id'])
        self.app.update_draft(self.teacher,d['id'],d['revision'],{'title':'下个版本'})
        self.assertEqual(self.app.get_snapshot(self.teacher,s['id'])['packet']['title'],'IOM420 Like-for-Like')

    def test_same_pseudonym_keeps_stable_authors(self):
        r,a,b = self.room()
        self.assertNotEqual(a['participant_id'],b['participant_id'])
        ma=self.app.message(a['token'],r['id'],'m-a','甲的建议')
        mb=self.app.message(b['token'],r['id'],'m-b','乙的建议')
        self.assertNotEqual(ma['author_id'],mb['author_id'])

    def test_student_view_excludes_teacher_and_future_event(self):
        r,a,b=self.room()
        view=self.app.room_view(a['token'],r['id'])
        raw=json.dumps(view,ensure_ascii=False)
        self.assertNotIn('延期两年',raw)
        self.assertNotIn('按使用量计费',raw)
        self.assertNotIn('conditions',raw)
        self.assertIn('task',view['activity'])

    def test_cross_group_access_rejected(self):
        r,a,b=self.room()
        r2=self.app.create_room(self.teacher,r['snapshot_id'],'B组')
        with self.assertRaises(DomainError): self.app.room_view(a['token'],r2['id'])
        with self.assertRaises(DomainError): self.app.control(a['token'],r['id'],'end')

    def test_message_retry_is_idempotent_and_persistent(self):
        r,a,b=self.room()
        m=self.app.message(a['token'],r['id'],'retry-1','保留原话')
        m2=self.app.message(a['token'],r['id'],'retry-1','重复请求不新增')
        self.assertEqual(m['id'],m2['id'])
        self.app.close()
        self.app=Classroom(self.db,clock=lambda:self.now)
        messages=self.app.room_view(a['token'],r['id'])['events']
        self.assertEqual(len([e for e in messages if e.get('client_id')=='retry-1']),1)

    def test_pause_excludes_time_and_event_publishes_once(self):
        r,a,b=self.room()
        self.now+=300
        self.app.control(self.teacher,r['id'],'pause')
        self.now+=200
        v=self.app.room_view(a['token'],r['id'])
        self.assertEqual(v['elapsed'],300)
        self.assertFalse(any(e['type']=='CASE_EVENT' for e in v['events']))
        self.app.control(self.teacher,r['id'],'resume')
        self.now+=61
        for _ in range(3): v=self.app.room_view(a['token'],r['id'])
        self.assertEqual(len([e for e in v['events'] if e['type']=='CASE_EVENT']),1)

    def test_end_freezes_submission_and_confirmation(self):
        r,a,b=self.room()
        sub=self.app.submit(a['token'],r['id'],'原始建议',0)
        self.app.acknowledge(b['token'],r['id'],sub['version'],'agree')
        ended=self.app.control(self.teacher,r['id'],'end')
        self.assertEqual(ended['frozen_submission']['raw'],'原始建议')
        self.assertIn(b['participant_id'],ended['frozen_submission']['acks'])
        with self.assertRaises(DomainError): self.app.message(a['token'],r['id'],'late','截止后发言')
        self.now+=500
        self.assertFalse(any(e['type']=='CASE_EVENT' for e in self.app.room_view(a['token'],r['id'])['events']))

    def test_submission_edit_resets_ack_and_conflicts(self):
        r,a,b=self.room()
        s=self.app.submit(a['token'],r['id'],'V1',0)
        self.app.acknowledge(b['token'],r['id'],s['version'],'agree')
        s=self.app.submit(a['token'],r['id'],'V2',s['version'])
        self.assertEqual(s['acks'],{})
        with self.assertRaises(DomainError): self.app.acknowledge(b['token'],r['id'],1,'agree')

    def test_personal_goal_never_enters_observer_input(self):
        r,a,b=self.room()
        self.app.set_goal(a['token'],r['id'],'我的私人学习目标')
        self.app.message(a['token'],r['id'],'x','讨论原话')
        self.app.control(self.teacher,r['id'],'end')
        self.app.reflect(a['token'],r['id'],'我觉得自己满分',skip=False)
        ctx=self.app.model_context(self.teacher,r['id'],'assessment')
        raw=json.dumps(ctx,ensure_ascii=False)
        self.assertNotIn('私人学习目标',raw)
        self.assertNotIn('自己满分',raw)
        self.assertIn('讨论原话',raw)

    def test_invalid_quote_and_ai_attribution_rejected(self):
        r,a,b=self.room()
        m=self.app.message(a['token'],r['id'],'x','需要确认授权条件。')
        self.app.control(self.teacher,r['id'],'end')
        with self.assertRaises(DomainError): self.app.validate_evidence(self.teacher,r['id'],a['participant_id'],m['id'],'编造句子')
        with self.assertRaises(DomainError): self.app.validate_evidence(self.teacher,r['id'],b['participant_id'],m['id'],'需要确认授权条件。')
        ev=self.app.validate_evidence(self.teacher,r['id'],a['participant_id'],m['id'],'授权条件')
        self.assertEqual(ev['quote'],'授权条件')

    def test_teacher_reports_do_not_wait_for_reflection(self):
        r,a,b=self.room()
        self.app.message(a['token'],r['id'],'x','我建议先分析业务影响。')
        self.app.control(self.teacher,r['id'],'end')
        ctx=self.app.model_context(self.teacher,r['id'],'group_report')
        self.assertEqual(ctx['room_id'],r['id'])

    def test_no_model_result_is_not_a_fake_ai_reply(self):
        r,a,b=self.room()
        self.app.message(a['token'],r['id'],'x','请AI回答')
        v=self.app.room_view(a['token'],r['id'])
        self.assertEqual(len([x for x in v['events'] if x.get('author_type')=='AI']),0)
        self.assertEqual(v['ai_status'],'NOT_CONNECTED')


    def test_teacher_cannot_submit_or_acknowledge_as_a_student(self):
        r,a,b=self.room()
        with self.assertRaises(DomainError):self.app.submit(self.teacher,r['id'],'teacher text',0)
        self.app.submit(a['token'],r['id'],'student submission',0)
        with self.assertRaises(DomainError):self.app.acknowledge(self.teacher,r['id'],1,'agree')


if __name__=='__main__': unittest.main()
