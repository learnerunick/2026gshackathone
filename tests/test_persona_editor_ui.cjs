// Regression: editing a bio must not erase the structured identity instructions.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../apps/dashboard/app.js'), 'utf8');
const context = vm.createContext({ esc: value => String(value).replace(/[<>&"]/g, char => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[char])) });
vm.runInContext(source.slice(source.indexOf('function renderAppearanceFields('), source.indexOf('function personaDialog(')), context);
const plain = value => JSON.parse(JSON.stringify(value));
const appearance = {
  direction: '수수한 30대 중반 워킹맘', face: '부드러운 타원형 얼굴', hair: '어깨 길이 짙은 갈색 머리',
  makeup: '연한 피치 핑크', makeup_avoid: ['진한 아이라인', '강한 컨투어링'],
  styling: '아이보리 블라우스', identity_reference_policy: '등록된 사진의 얼굴을 유지',
  future_detail: { preserve: true },
};

test('existing face, hair, makeup and reference rules are visible in the editor', () => {
  const html = context.renderAppearanceFields(appearance);
  for (const value of Object.values(appearance).filter(value => typeof value === 'string')) assert.ok(html.includes(value));
  assert.ok(html.includes('진한 아이라인\n강한 컨투어링'));
  assert.ok(!html.includes('[object Object]'));
});

test('saving unrelated profile edits preserves structured identity and unknown fields', () => {
  const fields = Object.fromEntries(Object.entries(appearance)
    .filter(([, value]) => typeof value === 'string' || Array.isArray(value))
    .map(([key, value]) => ['appearance:' + key, Array.isArray(value) ? value.join('\n') : value]));
  fields.bio = '새 소개글';
  assert.deepEqual(plain(context.appearanceFromForm(appearance, fields)), appearance);
  assert.deepEqual(plain(context.appearanceFromForm(appearance, {})), appearance);
});

test('changing one visible identity field keeps other fields and list types', () => {
  const result = plain(context.appearanceFromForm(appearance, {'appearance:hair':'  자연스러운 단발  ', 'appearance:makeup_avoid':'진한 아이라인\n\n붉은 립'}));
  assert.deepEqual(result, {...appearance, hair:'자연스러운 단발', makeup_avoid:['진한 아이라인','붉은 립']});
  assert.equal(appearance.hair, '어깨 길이 짙은 갈색 머리');
});

test('new free-text profiles and escaped saved values remain editable', () => {
  assert.equal(context.appearanceFromForm(undefined, {appearance:' 자연스러운 단발 '}), '자연스러운 단발');
  assert.equal(context.appearanceFromForm('이전 외형', {appearance:''}), '');
  assert.ok(context.renderAppearanceFields({face:'</textarea><script>alert(1)</script>'}).includes('&lt;/textarea&gt;'));
});
