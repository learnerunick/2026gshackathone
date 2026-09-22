// Old login bookmarks keep their destination; the MVP opens without a password.
(() => {
  let target = '/';
  try {
    const next = new URLSearchParams(location.search).get('next') || '/';
    const url = new URL(next, location.origin);
    if (url.origin === location.origin && ['/', '/video', '/video.html'].includes(url.pathname)) target = url.href;
  } catch { /* Invalid old links open the main dashboard. */ }
  location.replace(target);
})();
