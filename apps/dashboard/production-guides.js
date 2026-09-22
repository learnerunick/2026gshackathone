/* Shared project video direction, managed beside AI automatic production. */
const productionGuides = {
  selected: null, busy: false, reading: 0, error: '', opened: new Set(),
  render() {
    const guides = autoVideoState?.guides || [], active = guides.filter(g => g.enabled);
    const chosen = this.selected;
    return `<section class="panel production-guides-panel" id="production-video-guides" aria-labelledby="production-guides-title">
      <div class="section-top"><div><h2 id="production-guides-title">영상 제작 참고 MD</h2><p class="field-help">관여도 낮음 · 이번 이야기를 먼저 정하고 MD는 분위기만 가볍게 참고합니다.</p></div><span class="tag">참고 ${active.length}개</span></div>
      <p class="production-guide-description">여러 MD를 합쳐 촬영·소리·생활감 요소를 최대 1~2개만 선택적으로 참고합니다. 예시 장면, 도입부, 컷 순서는 반복하지 않고 매번 이야기와 연출을 새로 구성합니다. 인물의 외형·성격·말투는 유지합니다. 이미지 중심 제작에는 적용하지 않습니다.</p>
      <form id="production-guide-form" class="production-guide-upload">
        <label for="production-guide-file">MD 파일 선택<input id="production-guide-file" type="file" accept=".md,text/markdown" ${this.busy ? 'disabled' : ''}></label>
        <button type="submit" class="button primary" ${!chosen || this.busy ? 'disabled' : ''}>${this.busy ? '저장 중…' : 'MD 등록'}</button>
        <p class="field-help">UTF-8 .md · 파일당 64KB 이하 · 적용 내용 합계 12,000자 · 최대 10개. 같은 이름으로 다시 등록하면 교체합니다.</p>
        <p class="field-help" role="status">${esc(this.error || (chosen ? chosen.filename + ' · ' + Array.from(chosen.content).length.toLocaleString() + '자 · ' + (chosen.base_version ? 'v' + chosen.base_version + ' 교체 예정' : '등록 후 자동 적용') : '촬영 분위기, 생활 소음, 편집 아이디어 등을 적은 파일을 등록하세요.'))}</p>
        ${chosen ? `<details data-guide-details="preview" ${this.opened.has('preview') ? 'open' : ''}><summary>등록할 내용 미리보기</summary><pre class="production-guide-text">${esc(chosen.content)}</pre></details>` : ''}
      </form>
      <div class="production-guide-list">${guides.length ? guides.map(g => `<article class="production-guide-card"><div class="section-top"><h3>${esc(g.filename)}</h3><span class="tag">${g.enabled ? '가볍게 참고 중' : '적용 꺼짐'}</span></div><p class="field-help">v${g.version} · ${Array.from(g.content).length.toLocaleString()}자 · ${esc(date(g.updated_at))}</p><details data-guide-details="${esc(g.id)}" ${this.opened.has(g.id) ? 'open' : ''}><summary>내용 보기</summary><pre class="production-guide-text">${esc(g.content)}</pre></details><div class="production-guide-actions"><button type="button" class="button" data-guide-action="toggle" data-guide-id="${esc(g.id)}" data-guide-version="${g.version}" data-guide-enabled="${!g.enabled}" ${this.busy ? 'disabled' : ''}>${g.enabled ? '자동 적용 끄기' : '자동 적용 켜기'}</button><button type="button" class="button" data-guide-action="delete" data-guide-id="${esc(g.id)}" data-guide-version="${g.version}" ${this.busy ? 'disabled' : ''}>삭제</button></div></article>`).join('') : '<p class="field-help">등록된 MD가 없습니다. 파일 없이도 기존 설정으로 제작할 수 있습니다.</p>'}</div>
      <p class="field-help">수정한 지침은 다음 콘텐츠부터 적용됩니다. 등록만으로 AI 자동 제작이 시작되지는 않습니다. 직접 영상 제작에도 같은 파일을 참고합니다.</p>
    </section>`;
  },
  patch() {
    const host = document.getElementById('production-video-guides');
    if (host) host.outerHTML = this.render();
  },
  async select(file) {
    const sequence = ++this.reading;
    this.selected = null; this.error = '';
    if (!file) { this.patch(); return; }
    this.busy = true; this.patch();
    try {
      if (!/\.md$/i.test(file.name) || file.size > 64 * 1024) throw Error('64KB 이하의 UTF-8 .md 파일을 선택해 주세요.');
      let content;
      try { content = new TextDecoder('utf-8', {fatal:true}).decode(await file.arrayBuffer()); }
      catch { throw Error('UTF-8로 저장한 MD 파일을 선택해 주세요.'); }
      if (sequence !== this.reading) return;
      if (!content.trim() || Array.from(content).length > 12000 || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(content)) throw Error('MD는 비어 있지 않은 텍스트여야 하며 12,000자 이하여야 합니다.');
      const old = (autoVideoState?.guides || []).find(g => g.filename === file.name);
      this.selected = {filename:file.name, content, base_version:old?.version || 0};
    } catch (error) { this.error = error.message; }
    finally { if (sequence === this.reading) { this.busy = false; this.patch(); } }
  },
  async change(path, body, upload = false) {
    if (this.busy) return;
    this.busy = true; this.error = ''; this.patch();
    try {
      await api(path, body);
      if (upload) this.selected = null;
      await loadAutoEvidence();
      render(true);
      toast(upload ? 'MD를 등록했습니다. 다음 콘텐츠부터 AI 자동 제작에 참고합니다.' : '다음 콘텐츠부터 적용할 MD 설정을 저장했습니다.');
    } catch (error) {
      this.error = error.message;
      if (error.message.includes('변경')) this.selected = null;
      await loadAutoEvidence();
      toast(error.message);
    } finally { this.busy = false; this.patch(); }
  }
};
document.addEventListener('change', event => {
  if (event.target.id === 'production-guide-file') productionGuides.select(event.target.files[0]);
});
document.addEventListener('submit', event => {
  if (event.target.id !== 'production-guide-form') return;
  event.preventDefault();
  if (productionGuides.selected) productionGuides.change('/api/video/guides', productionGuides.selected, true);
});
document.addEventListener('click', event => {
  const target = event.target.closest('[data-guide-action]');
  if (!target || target.disabled) return;
  const action = target.dataset.guideAction;
  if (action === 'show') { document.getElementById('production-video-guides')?.scrollIntoView({behavior:'smooth',block:'start'}); return; }
  productionGuides.change('/api/video/guides/' + target.dataset.guideId + (action === 'delete' ? '/delete' : ''), {base_version:Number(target.dataset.guideVersion), enabled:target.dataset.guideEnabled === 'true'});
});
document.addEventListener('toggle', event => {
  const key = event.target.dataset?.guideDetails;
  if (key) event.target.open ? productionGuides.opened.add(key) : productionGuides.opened.delete(key);
}, true);
