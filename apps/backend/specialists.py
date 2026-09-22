"""Durable coordinator-attested specialist handoffs; no runtime spawning here."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

STAGE_KEYS = ('sources', 'planning', 'storyboard', 'copy', 'images', 'quality', 'register')
AUTHOR_STAGES = ('planning', 'storyboard', 'copy', 'images')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def now():
    return datetime.now(timezone.utc).isoformat()


class SpecialistsStore:
    def init_specialists(self, db):
        db.execute("""CREATE TABLE IF NOT EXISTS specialist_assignments (
            assignment_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,cycle_id TEXT NOT NULL,
            job_id TEXT NOT NULL,stage TEXT NOT NULL,role_id TEXT NOT NULL,role_name TEXT NOT NULL,
            agent_id TEXT NOT NULL,attempt INTEGER NOT NULL,status TEXT NOT NULL,
            lease_hash TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            result_summary TEXT,result_artifact TEXT,UNIQUE(job_id,lease_hash)
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS specialist_run_history ON specialist_assignments(run_id,created_at)")

    def _load_specialist_pack(self):
        try:
            pack = json.loads((self.root / 'config/specialists.json').read_text())
        except (OSError, ValueError):
            raise self.problem('전문가 역할 설정 config/specialists.json을 확인해 주세요.')
        if not isinstance(pack, dict) or not isinstance(pack.get('version'), int) or pack['version'] < 1:
            raise self.problem('전문가 역할 설정의 버전이 올바르지 않습니다.')
        roles = pack.get('roles')
        if not isinstance(roles, list) or not roles or len(roles) > 12:
            raise self.problem('전문가 역할 목록이 필요합니다.')
        ids, stages, clean = set(), set(), []
        for role in roles:
            if (not isinstance(role, dict) or not isinstance(role.get('id'), str) or
                    not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', role['id']) or role['id'] in ids or
                    not isinstance(role.get('name'), str) or not role['name'].strip() or
                    not isinstance(role.get('stages'), list) or not role['stages']):
                raise self.problem('전문가 역할 ID, 이름, 담당 단계를 확인해 주세요.')
            if any(stage not in STAGE_KEYS or stage in stages for stage in role['stages']):
                raise self.problem('모든 제작 단계에는 중복 없이 전문가를 지정해야 합니다.')
            if not isinstance(role.get('instructions'), list) or not role['instructions'] or not isinstance(role.get('output_contract'), dict):
                raise self.problem('전문가에게 전달할 지침과 JSON 출력 계약이 필요합니다.')
            if any(not isinstance(value, str) for value in role['instructions']):
                raise self.problem('전문가 지침은 문자열 목록이어야 합니다.')
            ids.add(role['id'])
            stages.update(role['stages'])
            clean.append(dict(role, version=role.get('version', pack['version'])))
        if stages != set(STAGE_KEYS):
            raise self.problem('7개 제작 단계의 전문가 역할 설정이 모두 필요합니다.')
        return self._safe_log(pack)

    def _freeze_specialists(self, settings):
        settings['specialist_agents_enabled'] = settings.get('specialist_agents_enabled', True) is True
        if settings['specialist_agents_enabled']:
            pack = self._load_specialist_pack()
            settings['specialist_pack'] = pack
            settings['specialist_pack_version'] = pack['version']
            settings['specialist_roles'] = [dict(role, version=role.get('version', pack['version'])) for role in pack['roles']]

    def _specialist_role(self, settings, stage):
        if settings.get('specialist_agents_enabled') is not True:
            return None
        role = next((role for role in settings.get('specialist_roles', []) if stage in role.get('stages', [])), None)
        if role is None:
            raise self.problem('이 실행에 저장한 전문가 역할을 찾을 수 없습니다.', 409)
        if stage == 'register' and settings.get('ai_quality_review_enabled', True) is False:
            # The explicit run policy overrides the older frozen quality gate.
            role = dict(role, instructions=[
                '이번 실행은 AI 품질 검수를 보류했습니다. 이전 역할 지침의 품질 통과 요구는 적용하지 않습니다. '
                'previous_results의 확정 문안과 기존 미디어로 manifest를 작성하세요. quality를 새로 실행하거나 통과했다고 표시하지 마세요. '
                'review_handoff.notes와 미확인 사항을 review_notes로 넘기고 사람의 검수 대기로 등록합니다. '
                '미디어 재생성·자동 승인·게시를 하지 않습니다.'
            ] + [line for line in role['instructions'] if '품질 검수를 통과한' not in line])
        return dict(role, role_id=role['id'], delegation={
            'required': True, 'coordinator_commits_only': True, 'runtime_verified': False,
            'steps': [
                'spawn_agent 또는 followup_task로 실제 전문가에게 현재 단계 입력을 위임합니다.',
                '실제 runtime canonical agent ID로 worker-agent를 등록합니다. 역할 이름으로 ID를 만들지 않습니다.',
                '전문가는 JSON 결과 파일을 반환합니다. 서버 DB 변경과 worker 명령은 조정자만 수행합니다.',
                '조정자는 작업 소유권을 유지하고 대기 중 worker-ping으로 실행 상태를 확인합니다.',
                '결과에 specialist_assignment_id를 연결하여 조정자가 완료 처리합니다.',
            ]})

    def _assignment(self, row):
        if row is None:
            return None
        item = dict(row)
        item.pop('lease_hash', None)
        return dict(item, recorded_by='coordinator', runtime_verified=False)

    def _assignment_current(self, db, cycle):
        token = cycle['lease_token']
        if not token:
            return None
        return db.execute('SELECT * FROM specialist_assignments WHERE job_id=? AND lease_hash=?',
                          (cycle['id'] + ':' + STAGE_KEYS[cycle['stage_index']], hashlib.sha256(token.encode()).hexdigest())).fetchone()

    def _specialist_required_assignment(self, db, cycle, assignment_id=None, require_id=False):
        run = db.execute('SELECT settings_json FROM production_runs WHERE id=?', (cycle['run_id'],)).fetchone()
        if json.loads(run[0]).get('specialist_agents_enabled') is not True:
            return None
        row = self._assignment_current(db, cycle)
        job = db.execute('SELECT attempts FROM jobs WHERE id=?', (cycle['id'] + ':' + STAGE_KEYS[cycle['stage_index']],)).fetchone()
        if (not row or not job or row['attempt'] != job['attempts'] or
                row['status'] not in ('assigned', 'uncertain', 'interrupted') or
                (require_id and assignment_id != row['assignment_id'])):
            raise self.problem('현재 단계와 작업 소유권에 연결된 실제 전문가 위임 기록이 필요합니다. worker-agent를 먼저 등록해 주세요.', 409)
        return row

    def worker_agent(self, cycle_id, lease_token, agent_id, role_id, action='assign'):
        if action != 'assign':
            raise self.problem('전문가 상태는 worker 완료·실패·중단 결과에 따라 기록됩니다. assign만 요청할 수 있습니다.')
        if (not isinstance(agent_id, str) or len(agent_id) > 300 or
                not re.fullmatch(r'(?:/root(?:/[A-Za-z0-9_-]+)+|[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})', agent_id)):
            raise self.problem('위임 도구가 반환한 실제 canonical task ID 또는 UUID agent ID가 필요합니다.')
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            run = db.execute('SELECT * FROM production_runs WHERE id=?', (cycle['run_id'],)).fetchone()
            current = datetime.now(timezone.utc)
            if cycle['status'] != 'running' or run['status'] != 'running' or self._deadline_reached(run, current) or self._time(cycle['lease_expires_at']) <= current:
                raise self.problem('진행 중이며 만료되지 않은 단계에만 새 전문가를 배정할 수 있습니다.', 409)
            stage = STAGE_KEYS[cycle['stage_index']]
            role = self._specialist_role(json.loads(run['settings_json']), stage)
            if not role:
                raise self.problem('이전 실행은 전문가 위임 계약을 사용하지 않습니다.', 409)
            if role_id != role['role_id']:
                raise self.problem('현재 단계에 설정된 전문가 역할과 일치하지 않습니다.', 409)
            prior = self._assignment_current(db, cycle)
            if prior:
                if prior['agent_id'] != agent_id or prior['role_id'] != role_id:
                    raise self.problem('이미 위임된 단계의 전문가를 덮어쓸 수 없습니다. 현재 작업을 먼저 마치거나 실패로 처리해 주세요.', 409)
                return dict(self._assignment(prior), duplicate=True)
            if stage == 'quality' and db.execute(
                    "SELECT 1 FROM specialist_assignments WHERE cycle_id=? AND agent_id=? AND stage IN ('planning','storyboard','copy','images')",
                    (cycle_id, agent_id)).fetchone():
                raise self.problem('품질 검수는 이 콘텐츠를 기획·작성·제작한 전문가와 다른 agent에게 맡겨 주세요.', 409)
            job = db.execute('SELECT * FROM jobs WHERE id=?', (cycle_id + ':' + stage,)).fetchone()
            created = now()
            assignment_id = 'agent-' + uuid.uuid4().hex[:20]
            db.execute('''INSERT INTO specialist_assignments
                (assignment_id,run_id,cycle_id,job_id,stage,role_id,role_name,agent_id,attempt,status,lease_hash,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'assigned',?,?,?)''',
                       (assignment_id, run['id'], cycle_id, job['id'], stage, role_id, role['name'], agent_id,
                        job['attempts'], hashlib.sha256(lease_token.encode()).hexdigest(), created, created))
            assignment = self._assignment(db.execute('SELECT * FROM specialist_assignments WHERE assignment_id=?', (assignment_id,)).fetchone())
            self._event(db, run['id'], cycle_id, stage, 'specialist.assigned', role['name'] + '에게 실제 작업을 위임했습니다.',
                        {'specialist_assignment': assignment})
            return dict(assignment, duplicate=False)

    def _specialist_change(self, db, row, status, summary=None):
        if not row or (row['status'] == status and (summary is None or row['result_summary'] == summary)):
            return self._assignment(row)
        artifact = '/api/runs/' + row['run_id'] + '/stages/' + row['cycle_id'] + '/' + row['stage']
        db.execute('UPDATE specialist_assignments SET status=?,updated_at=?,result_summary=?,result_artifact=? WHERE assignment_id=?',
                   (status, now(), self._safe_log(summary), artifact, row['assignment_id']))
        assignment = self._assignment(db.execute('SELECT * FROM specialist_assignments WHERE assignment_id=?', (row['assignment_id'],)).fetchone())
        self._event(db, row['run_id'], row['cycle_id'], row['stage'], 'specialist.' + status,
                    row['role_name'] + ' 위임 결과: ' + status, {'specialist_assignment': assignment},
                    'warning' if status in ('failed', 'uncertain', 'interrupted') else 'info')
        return assignment

    def _specialist_cycle_status(self, db, cycle_id, status, summary=None):
        for row in db.execute("SELECT * FROM specialist_assignments WHERE cycle_id=? AND status IN ('assigned','uncertain')", (cycle_id,)).fetchall():
            self._specialist_change(db, row, status, summary)

    def _specialist_run_stopped(self, db, run_id):
        for row in db.execute("SELECT * FROM specialist_assignments WHERE run_id=? AND status IN ('assigned','uncertain')", (run_id,)).fetchall():
            self._specialist_change(db, row, 'interrupted', '실행이 종료되어 새 작업을 중지했습니다. 이미 진행 중인 결과는 같은 소유권으로 보존할 수 있습니다.')

    def _specialist_complete(self, db, cycle, stage, result):
        row = self._specialist_required_assignment(db, cycle, result.get('specialist_assignment_id'), require_id=True)
        if row is None:
            return result
        assignment = self._specialist_change(db, row, 'completed', self._result_summary(stage, result))
        return dict(result, specialist_assignment_id=assignment['assignment_id'], specialist_assignment=assignment)

    def worker_sources(self, cycle_id, lease_token, result):
        # The source endpoint also validates the lease and run inside its write
        # transaction. Any intervening ownership change makes that call fail.
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            self._specialist_required_assignment(db, cycle)
        return super().worker_sources(cycle_id, lease_token, result)

    def _specialists_state(self, db, run):
        configured = dict(self.config())
        configuration_error = None
        try:
            self._freeze_specialists(configured)
        except self.problem as error:
            configuration_error = str(error)
        settings = json.loads(run['settings_json']) if run else configured
        enabled = settings.get('specialist_agents_enabled') is True
        assignments = [self._assignment(row) for row in db.execute('SELECT * FROM specialist_assignments ORDER BY created_at DESC,rowid DESC LIMIT 100')]
        cycle = db.execute("SELECT * FROM production_cycles WHERE run_id=? ORDER BY number DESC LIMIT 1", (run['id'],)).fetchone() if run else None
        current = self._assignment(self._assignment_current(db, cycle)) if cycle and cycle['lease_token'] else None
        # Live status must not depend on the separately fetched artifact files.
        cycle_summary = {key: cycle[key] for key in ('id', 'run_id', 'number', 'status', 'stage_index', 'updated_at')} if cycle else None
        stage_jobs = [dict(row) for row in db.execute(
            "SELECT id,cycle_id,run_id,stage,status,attempts,updated_at FROM jobs WHERE cycle_id=? ORDER BY updated_at",
            (cycle['id'],))] if cycle else []
        return {'enabled': enabled, 'roles': settings.get('specialist_roles', []), 'assignments': assignments,
                'coordinator': settings.get('specialist_pack', {}).get('coordinator'),
                'latest': assignments[0] if assignments else None, 'current': current,
                'cycle': cycle_summary, 'stage_jobs': stage_jobs,
                'configured_enabled': configured.get('specialist_agents_enabled') is True,
                'configured_roles': configured.get('specialist_roles', []),
                'configured_coordinator': configured.get('specialist_pack', {}).get('coordinator'),
                'configuration_error': configuration_error}

    def _specialist_stages(self, settings, stages):
        result = []
        for stage in stages:
            role = self._specialist_role(settings, stage['key'])
            result.append(dict(stage, specialist={'role_id': role['role_id'], 'name': role['name']} if role else None))
        return result

    def _stage_document(self, run, cycle, job, events):
        document = super()._stage_document(run, cycle, job, events)
        assignments = {}
        current_assignments = {}
        invalidated_at = max((event['id'] for event in document['events']
                              if event['event'] == 'stage.invalidated'), default=0)
        for event in document['events']:
            assignment = event.get('detail', {}).get('specialist_assignment')
            if assignment:
                assignments[assignment['assignment_id']] = assignment
                if event['id'] > invalidated_at:
                    current_assignments[assignment['assignment_id']] = assignment
        document['specialist'] = document.get('input', {}).get('specialist')
        document['specialist_assignments'] = list(assignments.values())
        document['specialist_assignment'] = list(current_assignments.values())[-1] if current_assignments else None
        return document
