import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createHash, createHmac, randomUUID } from 'node:crypto';
import { createGateway, configuration, allowed, resolveTarget } from '../../deploy/gateway.mjs';

const secret = 'test-bridge-secret-' + 'x'.repeat(32);
let fixture, bridge, core, root, server, base, cookie, csrf;
let errors = '';
before(async () => {
  fixture = spawn('python3', ['tests/remote/fixture_server.py'], { env: { ...process.env, BOCA_TEST_BRIDGE_SECRET: secret }, stdio: ['ignore', 'pipe', 'pipe'] });
  fixture.stderr.on('data', data => { errors += data; });
  const ready = await new Promise((resolve, reject) => {
    let buffer = '';
    const timeout = setTimeout(() => reject(Error('Fixture timeout: ' + errors)), 20000);
    fixture.stdout.on('data', data => { buffer += data; if (buffer.includes('\n')) { clearTimeout(timeout); resolve(JSON.parse(buffer.split('\n')[0])); } });
    fixture.once('exit', code => { clearTimeout(timeout); reject(Error('Fixture exit ' + code + ': ' + errors)); });
  });
  bridge = `http://127.0.0.1:${ready.bridge_port}`; core = `http://127.0.0.1:${ready.local_port}`; root = ready.root;
  const env = { BOCA_ALLOW_LOCAL_DEVELOPMENT: '1', BOCA_PUBLIC_ORIGIN: 'http://127.0.0.1:1', BOCA_BRIDGE_ORIGIN: bridge,
    BOCA_BRIDGE_SECRET: secret, BOCA_SESSION_SECRET: 'session-secret-' + 's'.repeat(32), BOCA_DASHBOARD_PASSWORD: 'password-' + 'p'.repeat(32) };
  server = http.createServer(createGateway({ env })); server.listen(0, '127.0.0.1'); await once(server, 'listening');
  base = `http://127.0.0.1:${server.address().port}`; env.BOCA_PUBLIC_ORIGIN = base;
  const login = await fetch(base + '/api/remote/login', { method: 'POST', headers: { Origin: base, 'Content-Type': 'application/json' }, body: JSON.stringify({ password: env.BOCA_DASHBOARD_PASSWORD }) });
  assert.equal(login.status, 200); cookie = login.headers.get('set-cookie').split(';')[0];
  const session = await (await fetch(base + '/api/remote/session', { headers: { Cookie: cookie } })).json(); csrf = session.token;
});
after(async () => { server?.closeAllConnections(); if (server) await new Promise(resolve => server.close(resolve)); fixture?.kill('SIGINT'); });

function api(path, method = 'GET', body, id = randomUUID(), extra = {}) {
  return fetch(base + path, { method, headers: { Cookie: cookie, Origin: base, 'X-BOCA-Token': csrf,
    'X-BOCA-Request-ID': id, 'Content-Type': 'application/json', ...extra }, body: method === 'POST' ? JSON.stringify(body) : undefined });
}

test('unauthenticated requests and worker/publication/import paths are rejected', async () => {
  assert.equal((await fetch(base + '/api/state')).status, 401);
  for (const path of ['/api/worker/next', '/api/contents/import', '/api/publishing/claim', '/api/personas/abc/references']) {
    assert.equal((await api(path, 'POST', {})).status, 403);
  }
  assert.equal((await fetch(bridge + '/api/state')).status, 401);
  assert.equal(allowed('GET', '/media/../.runtime/access-token'), false);
  assert.throws(() => resolveTarget('/api/gateway?_boca_path=/api/state&_boca_path=/api/worker/next'));
});

test('cloud cannot opt into insecure local settings; origin and CSRF are required', async () => {
  assert.throws(() => configuration({ VERCEL: '1', BOCA_ALLOW_LOCAL_DEVELOPMENT: '1', BOCA_PUBLIC_ORIGIN: base, BOCA_BRIDGE_ORIGIN: bridge }));
  assert.throws(() => configuration({ BOCA_PUBLIC_ORIGIN: 'https://dashboard.example.com', BOCA_BRIDGE_ORIGIN: 'https://worker.example.com',
    BOCA_BRIDGE_SECRET: 'replace-with-at-least-32-random-characters', BOCA_SESSION_SECRET: secret, BOCA_DASHBOARD_PASSWORD: secret }));
  assert.equal((await api('/api/personas', 'POST', {}, randomUUID(), { Origin: 'https://other.example' })).status, 403);
  assert.equal((await api('/api/personas', 'POST', {}, randomUUID(), { 'X-BOCA-Token': 'bad' })).status, 403);
  assert.equal((await fetch(base + '/api/state', { headers: { Cookie: cookie + 'tampered' } })).status, 401);
});

test('Instagram recheck reaches the local verifier through authenticated routing', async () => {
  assert.equal(allowed('POST', '/api/instagram/verify'), true);
  assert.equal(allowed('GET', '/api/instagram/verify'), false);
  assert.equal((await fetch(base + '/api/instagram/verify', { method: 'POST',
    headers: { Origin: base, 'Content-Type': 'application/json' }, body: '{}' })).status, 401);
  // The isolated fixture has no Instagram credentials; this error comes from the core API.
  const response = await api('/api/instagram/verify', 'POST', {});
  assert.equal(response.status, 409);
  assert.match((await response.json()).error, /게시 대상 계정|인증 토큰/);
});

test('actual local state survives proxying, and local mutation token is replaced', async () => {
  const original = await (await fetch(core + '/api/state')).json();
  const response = await api('/api/gateway?_boca_path=/api/state');
  const state = await response.json();
  assert.equal(response.status, 200); assert.equal(state.contents.length, original.contents.length);
  assert.equal(state.token, csrf); assert.notEqual(state.token, original.token);
  assert.equal(JSON.stringify(state).includes(original.token), false);
  assert.equal(state.remote.mode, 'local-worker');
  assert.equal(response.headers.get('content-encoding'), 'gzip');
  assert.equal(state.jobs.find(job => job.id === 'large-history-job').status, 'completed');
  assert.equal(state.jobs.find(job => job.id === 'large-history-job').input, undefined);
  assert.equal(original.jobs.find(job => job.id === 'large-history-job').input.previous_results.length, 6_000_000);
  assert.ok(JSON.stringify(state).length < JSON.stringify(original).length / 10);
});

test('uncompressed clients and gzip refusal receive readable state without encoding mismatches', async () => {
  for (const encoding of ['identity', 'gzip;q=0, br']) {
    const response = await api('/api/state', 'GET', undefined, randomUUID(), { 'Accept-Encoding': encoding });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-encoding'), null);
    assert.equal((await response.json()).contents.length, 2);
  }
});

test('edit, approval, re-edit and rejection use original version safeguards', async () => {
  let response = await api('/api/contents/remote-image/edit', 'POST', { base_version: 1, title: '원격 수정 완료' });
  assert.equal(response.status, 200);
  assert.equal((await api('/api/contents/remote-image/approve', 'POST', { version: 2 })).status, 200);
  assert.equal((await api('/api/contents/remote-image/edit', 'POST', { base_version: 2, title: '다시 검수할 문안' })).status, 200);
  let state = await (await api('/api/state')).json();
  assert.equal(state.contents.find(c => c.id === 'remote-image').status, 'ready');
  assert.equal((await api('/api/contents/remote-image/approve', 'POST', { version: 2 })).status, 409);
  assert.equal((await api('/api/contents/remote-image/reject', 'POST', { version: 3 })).status, 200);
});

test('lost-response replay does not apply a mutation twice, and ID reuse with new body fails', async () => {
  const id = randomUUID(); const body = { base_version: 3, title: '재전송 검증' };
  const first = await api('/api/contents/remote-image/edit', 'POST', body, id); assert.equal(first.status, 200);
  const firstJSON = await first.json();
  const second = await api('/api/contents/remote-image/edit', 'POST', body, id);
  assert.deepEqual(await second.json(), firstJSON);
  assert.equal((await api('/api/contents/remote-image/edit', 'POST', { ...body, title: '다른 내용' }, id)).status, 409);
  const state = await (await api('/api/state')).json(); assert.equal(state.contents.find(c => c.id === 'remote-image').current_version, 4);
});

test('run start, pause, resume and stop forward to the same isolated run without AI execution', async () => {
  const response = await api('/api/runs/start', 'POST', { start_at: new Date().toISOString().replace('Z', '+00:00'), stop_after_posts: 3, media_mode: 'images' });
  const result = await response.json(); assert.equal(response.status, 200, JSON.stringify(result));
  const state = await (await api('/api/state')).json(); const id = state.automation.run.id;
  for (const action of ['pause', 'resume', 'stop']) assert.equal((await api(`/api/runs/${id}/${action}`, 'POST', {})).status, 200);
  const final = await (await api('/api/state')).json(); assert.equal(final.automation.run.status, 'stopped');
  assert.equal(final.automation.run.completed_count, 0);
});

test('large binary/ZIP download and byte-range seeking stream intact through both layers', async () => {
  const state = await (await api('/api/state')).json();
  const media = state.contents.find(c => c.id === 'remote-large').payload.cards[0];
  const range = await api('/media/' + media.media, 'GET', undefined, randomUUID(), { Range: 'bytes=1024-2047' });
  assert.equal(range.status, 206); assert.equal((await range.arrayBuffer()).byteLength, 1024);
  assert.match(range.headers.get('content-range'), /^bytes 1024-2047\//);
  const full = await api('/media/' + media.media);
  assert.equal(full.headers.get('content-length'), null);
  assert.equal(createHash('sha256').update(Buffer.from(await full.arrayBuffer())).digest('hex'), media.sha256);
  const zip = await api('/api/contents/remote-large/export');
  assert.equal(zip.status, 200); assert.equal(zip.headers.get('content-type'), 'application/zip');
  assert.ok((await zip.arrayBuffer()).byteLength > 0);
});

test('bridge rejects expired signatures and body tampering', async () => {
  const path = '/api/contents/remote-image/edit'; const data = Buffer.from('{}');
  const id = randomUUID(); const stamp = Math.floor(Date.now() / 1000 - 120).toString();
  const mac = createHmac('sha256', secret).update(['POST', path, stamp, id, createHash('sha256').update(data).digest('hex')].join('\n')).digest('hex');
  const response = await fetch(bridge + path, { method: 'POST', headers: { 'X-BOCA-Bridge-Time': stamp, 'X-BOCA-Request-ID': id, 'X-BOCA-Bridge-Signature': mac }, body: data });
  assert.equal(response.status, 401);
  const current = Math.floor(Date.now() / 1000).toString();
  const valid = createHmac('sha256', secret).update(['POST', path, current, id, createHash('sha256').update(data).digest('hex')].join('\n')).digest('hex');
  const tampered = await fetch(bridge + path, { method: 'POST', headers: { 'X-BOCA-Bridge-Time': current, 'X-BOCA-Request-ID': id, 'X-BOCA-Bridge-Signature': valid }, body: '{"title":"changed"}' });
  assert.equal(tampered.status, 401);
});

test('malformed login and oversized input return errors without crashing the gateway', async () => {
  for (const body of ['null', '[]', '"string"', 'bad-json']) {
    const result = await fetch(base + '/api/remote/login', { method: 'POST', headers: { Origin: base, 'Content-Type': 'application/json' }, body });
    assert.equal(result.status, 400);
  }
  assert.equal((await api('/api/video/reference', 'POST', { data: 'x'.repeat(2_000_001) })).status, 400);
  assert.equal((await api('/api/state')).status, 200);
});

test('chunk upload verifies completeness/hash and returns the original local media result', async () => {
  const data = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=';
  const id = randomUUID();
  assert.equal((await api(`/api/remote/uploads/${id}/0`, 'POST', { data: data.slice(0, 44) })).status, 200);
  assert.equal((await api(`/api/remote/uploads/${id}/complete`, 'POST', { parts: 2, sha256: 'bad' })).status, 409);
  assert.equal((await api(`/api/remote/uploads/${id}/1`, 'POST', { data: data.slice(44) })).status, 200);
  assert.equal((await api(`/api/remote/uploads/${id}/complete`, 'POST', { parts: 2, sha256: 'bad' })).status, 400);
  const complete = await api(`/api/remote/uploads/${id}/complete`, 'POST', { parts: 2, sha256: createHash('sha256').update(data).digest('hex') });
  assert.equal(complete.status, 200); const result = await complete.json(); assert.match(result.media, /^[a-f0-9]{64}\.png$/);
});

test('a reference above the Function request limit is assembled in small requests without corruption', async () => {
  // Valid tiny PNG plus trailing padding, used only to exercise transport size.
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=', 'base64');
  const raw = Buffer.concat([png, Buffer.alloc(5_000_000)]);
  const encoded = raw.toString('base64'); const id = randomUUID();
  const count = Math.ceil(encoded.length / 1_000_000);
  for (let i = 0; i < count; i++) {
    assert.equal((await api(`/api/remote/uploads/${id}/${i}`, 'POST', { data: encoded.slice(i * 1_000_000, (i + 1) * 1_000_000) })).status, 200);
  }
  const result = await api(`/api/remote/uploads/${id}/complete`, 'POST', { parts: count, sha256: createHash('sha256').update(encoded).digest('hex') });
  assert.equal(result.status, 200);
  const media = await result.json();
  const downloaded = await api(media.url);
  assert.equal(createHash('sha256').update(Buffer.from(await downloaded.arrayBuffer())).digest('hex'), createHash('sha256').update(raw).digest('hex'));
});

test('unreachable Mac produces an explicit error and never retries a mutation', async () => {
  let calls = 0;
  const badEnv = { BOCA_ALLOW_LOCAL_DEVELOPMENT: '1', BOCA_PUBLIC_ORIGIN: base, BOCA_BRIDGE_ORIGIN: bridge,
    BOCA_BRIDGE_SECRET: secret, BOCA_SESSION_SECRET: 'session-secret-' + 's'.repeat(32), BOCA_DASHBOARD_PASSWORD: 'password-' + 'p'.repeat(32) };
  const failing = http.createServer(createGateway({ env: badEnv, fetcher: async () => { calls++; throw Error('offline'); } }));
  failing.listen(0, '127.0.0.1'); await once(failing, 'listening');
  try {
    const response = await fetch(`http://127.0.0.1:${failing.address().port}/api/runs/start`, { method: 'POST', headers: { Cookie: cookie, Origin: base, 'Content-Type': 'application/json', 'X-BOCA-Token': csrf }, body: '{}' });
    assert.equal(response.status, 503); assert.equal((await response.json()).code, 'WORKER_UNAVAILABLE'); assert.equal(calls, 1);
  } finally { failing.closeAllConnections(); await new Promise(resolve => failing.close(resolve)); }
});
