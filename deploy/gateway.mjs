import { createHash, createHmac, randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { createGzip } from 'node:zlib';

const routes = JSON.parse(readFileSync(new URL('./routes.json', import.meta.url), 'utf8'));
const cookieName = 'boca_remote_session';
const bodyLimit = 2_000_000;
const signature = (key, value) => createHmac('sha256', key).update(value).digest('hex');
const equal = (a, b) => timingSafeEqual(createHash('sha256').update(String(a)).digest(), createHash('sha256').update(String(b)).digest());

function acceptsGzip(req) {
  return String(req.headers['accept-encoding'] || '').toLowerCase().split(',').some(value => {
    const [name, ...parameters] = value.trim().split(';').map(part => part.trim());
    return name === 'gzip' && parameters.filter(part => part.startsWith('q=')).every(part => Number(part.slice(2)) > 0);
  });
}

async function streamJSON(req, res, source) {
  res.setHeader('Vary', 'Accept-Encoding');
  const compressed = acceptsGzip(req);
  if (compressed) res.setHeader('Content-Encoding', 'gzip');
  res.flushHeaders();
  if (compressed) await pipeline(source, createGzip(), res);
  else await pipeline(source, res);
}

export function configuration(env = process.env) {
  const local = env.BOCA_ALLOW_LOCAL_DEVELOPMENT === '1' && !env.VERCEL;
  const origin = new URL(env.BOCA_PUBLIC_ORIGIN || 'https://configuration-required.invalid');
  const bridge = new URL(env.BOCA_BRIDGE_ORIGIN || 'https://configuration-required.invalid');
  for (const url of [origin, bridge]) {
    if (url.username || url.password || url.pathname !== '/' || url.search || url.hash ||
        (url.protocol !== 'https:' && !(local && url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) ||
        url.hostname === 'configuration-required.invalid') throw Error('Remote origin configuration is required');
  }
  for (const key of ['BOCA_BRIDGE_SECRET', 'BOCA_SESSION_SECRET', 'BOCA_DASHBOARD_PASSWORD']) {
    if (!env[key] || env[key].length < 32 || env[key].startsWith('replace-with-')) throw Error('Remote secrets must be generated, with at least 32 characters');
  }
  return { origin: origin.origin, bridge: bridge.origin, local, bridgeSecret: env.BOCA_BRIDGE_SECRET,
    sessionSecret: env.BOCA_SESSION_SECRET, password: env.BOCA_DASHBOARD_PASSWORD };
}

export function allowed(method, path) {
  return !(path.includes('..') || /[%\\\x00-\x20]/.test(path)) &&
    (routes[method] || []).some(pattern => new RegExp('^(?:' + pattern + ')$').test(path));
}

export function resolveTarget(rawURL) {
  const url = new URL(rawURL, 'http://gateway.local');
  const paths = url.searchParams.getAll('_boca_path');
  if (paths.length > 1) throw Error('Ambiguous route');
  const path = paths[0] || url.pathname;
  if (!path.startsWith('/') || /[?#]/.test(path)) throw Error('Invalid route');
  url.searchParams.delete('_boca_path');
  const query = url.searchParams.toString();
  return { path, target: path + (query ? '?' + query : '') };
}

export function sessionFor(req, config, now = Date.now()) {
  const cookie = String(req.headers.cookie || '').split(';').map(v => v.trim()).find(v => v.startsWith(cookieName + '='));
  if (!cookie) return null;
  const token = cookie.slice(cookieName.length + 1);
  const [data, mac, extra] = token.split('.');
  if (extra || !data || !mac || !equal(mac, signature(config.sessionSecret, data))) return null;
  try {
    const session = JSON.parse(Buffer.from(data, 'base64url').toString());
    if (!Number.isInteger(session.exp) || session.exp <= now || session.exp > now + 8 * 3600_000 ||
        typeof session.nonce !== 'string') return null;
    return { csrf: signature(config.sessionSecret, 'csrf:' + token) };
  } catch { return null; }
}

function json(res, status, value) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(value));
}

async function body(req) {
  // Vercel parses application/json; local Node HTTP leaves an async stream.
  if (req.body !== undefined) {
    const value = Buffer.isBuffer(req.body) ? req.body : Buffer.from(typeof req.body === 'string' ? req.body : JSON.stringify(req.body));
    if (value.length > bodyLimit) throw Error('Body too large');
    return value;
  }
  const parts = []; let size = 0;
  for await (const part of req) {
    size += part.length;
    if (size > bodyLimit) throw Error('Body too large');
    parts.push(part);
  }
  return Buffer.concat(parts);
}

export function createGateway({ env = process.env, fetcher = fetch } = {}) {
  return async function gateway(req, res) {
    res.setHeader('Cache-Control', 'private, no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    let config;
    try { config = configuration(env); }
    catch { return json(res, 503, { error: '원격 연결 환경변수를 먼저 설정해 주세요.', code: 'REMOTE_NOT_CONFIGURED' }); }
    let route;
    try { route = resolveTarget(req.url); }
    catch { return json(res, 400, { error: '요청 경로가 올바르지 않습니다.' }); }
    const { path, target } = route;
    const method = req.method;
    if (!['GET', 'POST'].includes(method)) return json(res, 405, { error: '지원하지 않는 요청입니다.' });
    if (method === 'POST' && req.headers.origin !== config.origin) return json(res, 403, { error: '같은 대시보드에서 요청해 주세요.' });
    let input = Buffer.alloc(0);
    if (method === 'POST') {
      if (!String(req.headers['content-type'] || '').startsWith('application/json')) return json(res, 415, { error: 'JSON 요청이 필요합니다.' });
      try {
        input = await body(req);
        const value = JSON.parse(input.toString());
        if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('JSON object required');
      }
      catch { return json(res, 400, { error: '요청 형식 또는 크기를 확인해 주세요.' }); }
    }
    if (path === '/api/remote/login' && method === 'POST') {
      if (!equal(JSON.parse(input).password, config.password)) return json(res, 401, { error: '접속 암호를 확인해 주세요.' });
      const data = Buffer.from(JSON.stringify({ exp: Date.now() + 8 * 3600_000, nonce: randomBytes(24).toString('hex') })).toString('base64url');
      res.setHeader('Set-Cookie', `${cookieName}=${data}.${signature(config.sessionSecret, data)}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800${config.local ? '' : '; Secure'}`);
      return json(res, 200, { authenticated: true });
    }
    const session = sessionFor(req, config);
    if (!session) return json(res, 401, { error: '대시보드 로그인이 필요합니다.', code: 'LOGIN_REQUIRED' });
    if (method === 'POST' && !equal(req.headers['x-boca-token'] || '', session.csrf)) return json(res, 403, { error: '인증 정보를 새로고침해 주세요.' });
    if (path === '/api/remote/session' && method === 'GET') return json(res, 200, { authenticated: true, token: session.csrf });
    if (path === '/api/remote/logout' && method === 'POST') {
      res.setHeader('Set-Cookie', `${cookieName}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0${config.local ? '' : '; Secure'}`);
      return json(res, 200, { authenticated: false });
    }
    if (!allowed(method, path)) return json(res, 403, { error: '이 경로는 원격 대시보드에서 사용할 수 없습니다.' });
    const suppliedId = req.headers['x-boca-request-id'];
    if (suppliedId && !/^[a-zA-Z0-9-]{16,80}$/.test(suppliedId)) return json(res, 400, { error: '요청 ID 형식이 잘못됐습니다.' });
    const requestId = suppliedId || randomUUID();
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const hash = createHash('sha256').update(input).digest('hex');
    const mac = signature(config.bridgeSecret, [method, target, timestamp, requestId, hash].join('\n'));
    const headers = { 'X-BOCA-Bridge-Time': timestamp, 'X-BOCA-Request-ID': requestId, 'X-BOCA-Bridge-Signature': mac };
    if (method === 'POST') headers['Content-Type'] = 'application/json';
    if (req.headers.range) headers.Range = req.headers.range;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 270_000);
    res.on('close', () => { if (!res.writableEnded) controller.abort(); });
    try {
      const upstream = await fetcher(config.bridge + target, { method, headers, body: method === 'POST' ? input : undefined,
        redirect: 'manual', signal: controller.signal });
      if ([301, 302, 303, 307, 308].includes(upstream.status)) throw Error('Unexpected bridge redirect');
      if (path === '/api/state' && upstream.ok) {
        const data = await upstream.json();
        data.token = session.csrf;
        data.remote = { mode: 'local-worker', connected: true };
        // Chunked JSON and binary responses do not buffer media in a Function.
        res.statusCode = upstream.status;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        await streamJSON(req, res, Readable.from([JSON.stringify(data)]));
        return;
      }
      res.statusCode = upstream.status;
      for (const name of ['content-type', 'content-disposition', 'content-range', 'accept-ranges', 'x-boca-outcome']) {
        const value = upstream.headers.get(name);
        if (value) res.setHeader(name, value);
      }
      // Deliberately omit Content-Length: Vercel streams the response, including ZIP/MP4 >4.5 MB.
      if (upstream.body && upstream.headers.get('content-type')?.includes('application/json')) {
        await streamJSON(req, res, Readable.fromWeb(upstream.body));
        return;
      }
      res.flushHeaders();
      if (upstream.body) await pipeline(Readable.fromWeb(upstream.body), res);
      else res.end();
    } catch {
      if (!res.headersSent) json(res, 503, { error: method === 'POST'
        ? 'Mac의 응답을 확인하지 못했습니다. 제작 현황을 확인한 뒤 다시 요청해 주세요. 자동 재전송하지 않았습니다.'
        : 'Mac 작업자에 연결할 수 없습니다. Mac의 서버와 터널 실행 상태를 확인해 주세요.',
        code: 'WORKER_UNAVAILABLE', request_id: requestId });
      else res.destroy();
    } finally { clearTimeout(timer); }
  };
}
