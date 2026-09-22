/* Loaded only into the Vercel build. Local dashboard scripts remain unchanged. */
(() => {
  const originalFetch = window.fetch.bind(window);
  let authenticated = false;
  let statusText = 'Mac 작업자 연결 확인 중';
  let toolbar;
  function status(message) {
    statusText = message;
    if (toolbar) toolbar.querySelector('[role=status]').textContent = message;
  }
  function loginURL() { return '/login.html?next=' + encodeURIComponent(location.pathname + location.search + location.hash); }
  async function checked(url, init = {}) {
    const response = await originalFetch(url, init);
    if (response.status === 401) {
      if (!authenticated) location.replace(loginURL());
      else { status('로그인이 만료됐습니다. 새 창에서 다시 로그인해 주세요.'); toolbar?.querySelector('a').removeAttribute('hidden'); }
    } else if (response.status === 503) status('Mac 연결 끊김 · 서버와 터널을 확인해 주세요');
    else if (response.ok && String(url).includes('/api/')) { authenticated = true; status('Mac 연결됨 · AI 제작은 Mac에서 실행'); }
    return response;
  }
  async function uploadInParts(init, data) {
    const upload = crypto.randomUUID();
    const bytes = new TextEncoder().encode(data);
    const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(n => n.toString(16).padStart(2, '0')).join('');
    const count = Math.ceil(data.length / 1_000_000);
    for (let index = 0; index < count; index++) {
      const headers = new Headers(init.headers);
      headers.set('X-BOCA-Request-ID', crypto.randomUUID());
      const response = await checked(`/api/remote/uploads/${upload}/${index}`, { ...init, headers,
        body: JSON.stringify({ data: data.slice(index * 1_000_000, (index + 1) * 1_000_000) }) });
      if (!response.ok) return response;
    }
    const headers = new Headers(init.headers);
    headers.set('X-BOCA-Request-ID', crypto.randomUUID());
    return checked(`/api/remote/uploads/${upload}/complete`, { ...init, headers, body: JSON.stringify({ parts: count, sha256: sha }) });
  }
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return originalFetch(input, init);
    const options = { ...init };
    try {
      if ((options.method || 'GET').toUpperCase() === 'POST') {
        options.headers = new Headers(options.headers);
        if (!options.headers.has('X-BOCA-Request-ID')) options.headers.set('X-BOCA-Request-ID', crypto.randomUUID());
        if (url.pathname === '/api/video/reference' && typeof options.body === 'string') {
          const body = JSON.parse(options.body);
          if (typeof body.data === 'string' && body.data.length > 1_000_000) return await uploadInParts(options, body.data);
        }
      }
      return await checked(input, options);
    } catch (error) { status('Mac 연결 확인 필요 · 요청을 자동 재전송하지 않습니다'); throw error; }
  };
  document.addEventListener('DOMContentLoaded', () => {
    toolbar = document.createElement('aside');
    toolbar.className = 'remote-toolbar';
    toolbar.setAttribute('aria-label', '원격 연결');
    const message = document.createElement('span'); message.setAttribute('role', 'status'); message.textContent = statusText;
    const link = document.createElement('a'); link.textContent = '다시 로그인'; link.href = loginURL(); link.target = '_blank'; link.rel = 'noopener'; link.hidden = true;
    const logout = document.createElement('button'); logout.type = 'button'; logout.textContent = '로그아웃';
    logout.onclick = async () => {
      const session = await originalFetch('/api/remote/session', { cache: 'no-store' });
      if (session.ok) {
        const { token } = await session.json();
        await originalFetch('/api/remote/logout', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-BOCA-Token': token }, body: '{}' });
      }
      sessionStorage.removeItem('boca-video-draft');
      location.href = '/login.html';
    };
    toolbar.append(message, link, logout); document.body.append(toolbar);
  });
})();
