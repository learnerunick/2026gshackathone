document.getElementById('remote-login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button');
  const error = document.getElementById('login-error');
  button.disabled = true; error.textContent = '';
  try {
    const response = await fetch('/api/remote/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: new FormData(form).get('password') }) });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || '로그인하지 못했습니다.');
    const next = new URLSearchParams(location.search).get('next') || '/';
    const url = new URL(next, location.origin);
    location.replace(url.origin === location.origin && ['/', '/video', '/video.html'].includes(url.pathname) ? url.href : '/');
  } catch (reason) { error.textContent = reason.message; }
  finally { button.disabled = false; }
});
