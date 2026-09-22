import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const legacyLogin = readFileSync(new URL('../../deploy/vercel/login.js', import.meta.url), 'utf8');

test('old login links open their dashboard or video destination without user input', () => {
  for (const next of ['/', '/#review', '/video', '/video.html?draft=1']) {
    let result;
    runInNewContext(legacyLogin, { URL, URLSearchParams, location: {
      origin: 'https://boca.example', search: '?next=' + encodeURIComponent(next),
      replace: value => { result = value; },
    } });
    assert.equal(result, 'https://boca.example' + next);
  }
});

test('old login links cannot redirect to another site or unsupported path', () => {
  for (const next of ['https://other.example/', '//other.example/', '/api/state', 'javascript:alert(1)', 'http://[']) {
    let result;
    runInNewContext(legacyLogin, { URL, URLSearchParams, location: {
      origin: 'https://boca.example', search: '?next=' + encodeURIComponent(next),
      replace: value => { result = value; },
    } });
    assert.equal(result, '/');
  }
});

test('a bridge authentication error stays on the dashboard without a login or logout UI', async () => {
  let mounted, onReady;
  const nodes = [];
  const node = tag => {
    const element = { tag, children: [], setAttribute() {},
      append(...children) { this.children.push(...children); },
      querySelector() { return this.children[0]; } };
    nodes.push(element); return element;
  };
  const window = { fetch: async () => ({ status: 401, ok: false }) };
  const document = { addEventListener: (_, fn) => { onReady = fn; }, createElement: node,
    body: { append: element => { mounted = element; } } };
  runInNewContext(readFileSync(new URL('../../deploy/vercel/remote.js', import.meta.url), 'utf8'), {
    window, document, URL, location: { origin: 'https://boca.example', replace() { assert.fail('Unexpected login redirect'); } },
  });
  onReady();
  assert.equal((await window.fetch('/api/state')).status, 401);
  assert.match(mounted.children[0].textContent, /Mac 연결 끊김/);
  assert.equal(nodes.some(element => ['button', 'a', 'input'].includes(element.tag)), false);
});
