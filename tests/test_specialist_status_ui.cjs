// Pure presentation regressions; no browser, live DB, or generation calls.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../apps/dashboard/app.js'), 'utf8');

function context() {
  const c = vm.createContext({
    state: { automation: { run: { id: 'run-1', status: 'running', cycle_number: 1,
      start_at: new Date(Date.now() - 360000).toISOString() }, worker_status: 'waiting',
      specialists: { cycle: { id: 'cycle-1', run_id: 'run-1' }, stage_jobs: [], assignments: [] }, stages: [] } },
    productionConnection: { error: '', lastUpdated: new Date().toISOString() },
    autoArtifacts: null, page: 'create', createTab: 'automation',
    badge: (status, text = status) => `${status}:${text}`,
    esc: String, icon: () => '', date: String, renderAutoProgress: () => '',
    autoStageLabels: { sources: '자료 탐색', planning: '기획' }, autoStageDescriptions: {},
    latestStageTrace: () => null, isActiveRun: (run) => run?.status === 'running',
    document: { activeElement: { tagName: 'INPUT', value: 'unsaved guide text', dataset: {} } },
    dirty: false, productionGuides: { busy: false },
    renderNav: () => {}, renderProductionStatus: () => {},
    setTimeout, clearTimeout, AbortController,
  });
  c.currentRun = () => c.state.automation.run;
  vm.runInContext(source.slice(source.indexOf('const specialistRoleDefaults ='), source.indexOf('function automaticVideoOptions(')), c);
  return c;
}

test('handoff retains completed assignment without artifact files; next cycle resets it', () => {
  const c = context(), s = c.state.automation.specialists;
  const assignment = { assignment_id: 'a1', run_id: 'run-1', cycle_id: 'cycle-1', stage: 'sources', agent_id: '/root/fixture', status: 'completed' };
  s.assignments = [assignment];
  s.stage_jobs = [{ cycle_id: 'cycle-1', stage: 'sources', status: 'completed' }];
  assert.equal(c.specialistAssignmentForStage('sources'), assignment);
  assert.equal(c.specialistStageBadge('sources', c.specialistStageTrace('sources'), assignment), 'completed:완료');
  s.cycle.id = 'cycle-2';
  s.stage_jobs = [{ cycle_id: 'cycle-2', stage: 'sources', status: 'running' }];
  assert.equal(c.specialistAssignmentForStage('sources'), null);
  assert.equal(c.specialistStageBadge('sources', c.specialistStageTrace('sources'), null), 'pending:전문가 배정 대기');
});

test('repair does not present an earlier completed assignment as current', () => {
  const c = context(), s = c.state.automation.specialists;
  s.assignments = [{ run_id: 'run-1', cycle_id: 'cycle-1', stage: 'sources', agent_id: '/root/fixture', status: 'completed' }];
  s.stage_jobs = [{ cycle_id: 'cycle-1', stage: 'sources', status: 'pending' }];
  assert.equal(c.specialistAssignmentForStage('sources'), null);
});

test('waiting, live, paused and disconnected states are distinguished', () => {
  const c = context(), a = c.state.automation;
  a.run.cycle_number = 0;
  assert.match(c.specialistWorkerView().heading, /지연/);
  assert.equal(c.specialistStageBadge('sources', null, null), 'pending:작업자 대기');
  a.worker_status = 'active';
  const assigned = { assignment_id: 'a1', run_id: 'run-1', agent_id: '/root/fixture', status: 'assigned', role_name: '리서처' };
  a.specialists.current = assigned;
  assert.match(c.specialistWorkerView().heading, /작업 중/);
  assert.equal(c.specialistAssignmentBadge(assigned, { live: true }), 'running:작업 중');
  a.run.status = 'paused';
  assert.equal(c.specialistAssignmentBadge(assigned, { live: true }), 'paused:일시정지');
  c.productionConnection.error = 'offline';
  assert.equal(c.specialistAssignmentBadge(assigned, { live: true }), 'uncertain:연결 확인');
  assert.equal(c.specialistWorkerView().tone, 'stale');
});

test('team refresh continues while a form input prevents a full page render', () => {
  const c = context();
  let painted = '';
  const panel = { contains: () => false, get outerHTML() { return painted; }, set outerHTML(value) { painted = value; } };
  c.$ = (id) => id === 'specialist-team' ? panel : id === 'workspace' ? { contains: () => true, querySelectorAll: () => [] } : null;
  vm.runInContext(source.slice(source.indexOf('function render(force'), source.indexOf('const videoLibraryStorageKey')), c);
  c.render();
  assert.match(painted, /5초마다 상태 확인/);
  assert.equal(c.document.activeElement.value, 'unsaved guide text');
});

test('latest team state paints before slow artifact requests resolve', async () => {
  const c = context();
  let painted = false, releaseArtifacts;
  c.refreshBusy = false;
  c.allLogs = new Map();
  c.$ = () => ({ textContent: '' });
  c.fetch = async () => ({ ok: true, json: async () => c.state });
  c.patchSpecialistTeam = () => { painted = true; };
  c.render = () => {};
  c.loadAutoEvidence = () => new Promise((resolve) => { releaseArtifacts = resolve; });
  vm.runInContext(source.slice(source.indexOf('async function refresh('), source.indexOf('function renderProductionStatus(')), c);
  const pending = c.refresh();
  await new Promise(setImmediate);
  assert.equal(painted, true);
  releaseArtifacts();
  await pending;
});

test('preparation distinguishes connection, input reading, delay and another run', () => {
  const c = context(), a = c.state.automation;
  a.run.cycle_number = 0;
  a.run.start_at = new Date(Date.now() - 15000).toISOString();
  a.worker_runtime = { online: true, run_id: 'run-1', status: 'starting' };
  assert.match(c.specialistWorkerView().heading, /연결/);
  assert.match(c.specialistWorkerView().copy, /실행 요청 후 15초/);
  a.worker_runtime.status = 'running';
  assert.match(c.specialistWorkerView().heading, /제작 입력/);
  a.run.start_at = new Date(Date.now() - 180000).toISOString();
  assert.match(c.specialistWorkerView().heading, /지연/);
  assert.equal(c.specialistWorkerView().tone, 'stale');
  a.worker_runtime.run_id = 'old-run';
  assert.equal(c.runtimePreparationView(), null);
});

test('every stage detail distinguishes its live assignee from historical assignments', () => {
  const c = context(), a = c.state.automation;
  a.worker_status = 'active';
  for (const stage of ['sources', 'planning', 'storyboard', 'copy', 'images', 'quality', 'register']) {
    const assignment = { assignment_id: stage, run_id: 'run-1', stage,
      agent_id: '/root/fixture', status: 'assigned' };
    a.specialists.current = assignment;
    assert.match(c.renderStageSpecialist({ specialist_assignment: assignment }, stage), /running:작업 중/);
    assert.match(c.renderStageSpecialist({ specialist_assignment: { ...assignment, run_id: 'old-run' } }, stage), /pending:배정됨/);
    assignment.status = 'completed';
    assert.match(c.renderStageSpecialist({ specialist_assignment: assignment }, stage), /completed:완료/);
  }
});

test('stage activity shows actual progress separately from coordinator heartbeat', () => {
  const c = context();
  vm.runInContext(source.slice(source.indexOf('function stageActivityView('), source.indexOf('function stageResultBody(')), c);
  c.state.automation.specialists.current = { cycle_id: 'cycle-1', stage: 'sources' };
  c.state.automation.worker_last_seen_at = '2026-09-21T10:45:59Z';
  const data = { run_id: 'run-1', cycle_id: 'cycle-1', stage: 'sources', events: [
    { event: 'sources.search.started', message: '공식 자료 검색을 시작했습니다.', created_at: '2026-09-21T10:39:00Z' },
    { event: 'worker.heartbeat', message: 'heartbeat-only', created_at: '2026-09-21T10:45:59Z' },
    { event: 'stage.completed', message: '자료 확인 완료', created_at: '2026-09-21T10:45:00Z' },
  ] };
  const view = c.stageActivityView(data);
  assert.match(view, /공식 자료 검색/);
  assert.match(view, /자료 확인 완료/);
  assert.doesNotMatch(view, /heartbeat-only/);
  assert.match(view, /연결 신호와 작업 완료 기록은 별도/);
  assert.ok(view.indexOf('자료 확인 완료') < view.indexOf('공식 자료 검색'));
  assert.doesNotMatch(c.stageActivityView({ ...data, run_id: 'old-run' }), /제작 총괄 연결 확인/);
});
