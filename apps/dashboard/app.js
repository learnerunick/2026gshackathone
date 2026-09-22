const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const iconPaths = {
  overview:
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  persona:
    '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  create:
    '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4m8-4v4M3 10h18m-9 3v5m-2.5-2.5h5"/>',
  production:
    '<rect x="3" y="4" width="18" height="15" rx="2"/><path d="M7 13V9m5 6V8m5 5v-3M9 22h6m-3-3v3"/>',
  videos:
    '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m10 8 6 4-6 4V8Z"/>',
  review:
    '<path d="M8 4H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-3"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="m8 13 3 3 5-6"/>',
  feed: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18m6-18v18"/>',
  sources:
    '<path d="M3 7h6l2-3h9a1 1 0 0 1 1 1v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="M3 9h18"/>',
  logs: '<path d="M4 7h16M4 12h16M4 17h10"/><circle cx="18" cy="17" r="2"/>',
  settings:
    '<path d="m9.5 3-.6 2.1-2 .9-2-.6L2.8 9l1.5 1.5v3L2.8 15l2.1 3.6 2-.6 2 .9.6 2.1h5l.6-2.1 2-.9 2 .6 2.1-3.6-1.5-1.5v-3L21.2 9l-2.1-3.6-2 .6-2-.9-.6-2.1Z"/><circle cx="12" cy="12" r="3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="m9 5 7 7-7 7"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  refresh:
    '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  image:
    '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
  stack:
    '<rect x="6" y="3" width="15" height="15" rx="2"/><path d="M3 7v12a2 2 0 0 0 2 2h12"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  spark:
    '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  play: '<path d="m7 4 14 8-14 8V4Z"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
  edit: '<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14v6Z"/>',
  link: '<path d="m10 13 4-4M8 15l-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m4 2 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(1 0) scale(.92)"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v2"/>',
  instagram:
    '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><path d="M17 7h.01"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  leaf: '<path d="M20 3C7 2 1 10 6 16c6 6 15-2 14-13Z"/><path d="M3 22 15 10"/>',
};
const icon = (name, cls = "") =>
  `<svg class="${esc(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.info}</svg>`;
const pages = [
  ["overview", "개요"],
  ["persona", "페르소나"],
  ["create", "콘텐츠 제작"],
  ["production", "제작 현황"],
  ["videos", "영상 라이브러리"],
  ["review", "검수 & 승인"],
  ["feed", "피드 미리보기"],
  ["sources", "GS 소재 관리"],
  ["logs", "활동 로그"],
  ["settings", "설정"],
];
const labels = {
  ready: "검수 대기",
  approved: "승인 완료",
  rejected: "반려",
  posting: "게시 처리 중",
  published: "게시 완료",
  uncertain: "확인 필요",
  pending: "대기",
  running: "제작 중",
  completed: "완료",
  producing: "제작 중",
  failed: "실패",
  superseded: "새 버전",
  skipped: "검수 보류",
  draft: "기획 초안",
  queued: "제작 대기",
  scheduled: "시작 예약",
  paused: "일시정지",
  stopped: "중지",
  blocked: "확인 필요",
  active: "활용 가능",
  expired: "기간 만료",
};
const affiliateNames = ["GS리테일", "GS SHOP", "GS건설", "GS칼텍스", "파르나스 호텔"];
const affiliateLabel = (name) =>
  ({ "GS리테일": "GS리테일(편의점,수퍼)", "GS SHOP": "GSSHOP" })[name] || name;
const disclosure = "AI로 만든 가상 인물의 창작 일상입니다.";
let state = null,
  page = pages.some((p) => p[0] === location.hash.slice(1))
    ? location.hash.slice(1)
    : "overview";
let createTab = "automation",
  briefFilter = "all",
  reviewFilter = "ready",
  sourceFilter = "all",
  feedFilter = "all",
  logFilter = "all",
  logStage = "all";
let selectedId = null,
  selectedCard = 0,
  editingVersion = null,
  dirty = false,
  refreshBusy = false,
  mutating = false,
  pageSignature = "",
  searchQuery = "",
  sourceQuery = "",
  logQuery = "",
  allLogs = new Map();
let autoEvidenceTab = "stages",
  autoArtifacts = null,
  autoArtifactsError = "",
  autoVideoState = null,
  autoEvidenceBusy = false,
  autoStageLimit = 14;
const resultCards = new Map();
const productionConnection = { error: "", lastUpdated: null };
const autoDraft = {
  persona_id: null,
  media_mode: "mixed",
  video_duration: null,
  video_resolution: null,
  quantity_mode: "unlimited",
  stop_after_posts: "10",
  start_at: "",
  end_at: "",
  schedule_open: false,
};
const date = (value, full = false) =>
  value && !Number.isNaN(new Date(value).getTime())
    ? new Date(value).toLocaleString("ko-KR", {
        ...(full ? { year: "numeric" } : {}),
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Asia/Seoul",
      })
    : "—";
const shortDate = (value) =>
  value && !Number.isNaN(new Date(value).getTime())
    ? new Date(value).toLocaleDateString("ko-KR", {
        month: "numeric",
        day: "numeric",
        timeZone: "Asia/Seoul",
      })
    : "—";
const inputDate = (value) =>
  value && !Number.isNaN(new Date(value).getTime())
    ? new Date(value)
        .toLocaleString("sv-SE", {
          timeZone: "Asia/Seoul",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        })
        .replace(" ", "T")
    : "";
const koreanISO = (value) => (value ? value + ":00+09:00" : null);
const array = (value) =>
  Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value
          .split(/[,\n]/)
          .map((s) => s.trim())
          .filter(Boolean)
      : [];
const activePersona = () => {
  const studio = state?.studio || {};
  return (
    (studio.personas || []).find((p) => p.id === studio.active_persona_id) ||
    (studio.personas || [])[0] || {
      id: state?.persona?.id,
      version: state?.persona?.version || 1,
      profile: state?.persona || {},
    }
  );
};
const profile = (persona) => persona?.profile || persona || {};
const personaName = (persona) =>
  persona?.display_name || profile(persona).display_name || "여의도 워킹맘";
const personaBio = (persona) => persona?.bio || profile(persona).bio || "";
const contentPersona = (content) =>
  content.payload?.persona_id || state?.persona?.id;
const personaContents = (id) =>
  (state?.contents || []).filter((c) => !id || contentPersona(c) === id);
const sourceRows = () => state?.automation?.sources || [];
const currentRun = () => state?.automation?.run;
const isActiveRun = (run) =>
  run && ["scheduled", "running", "paused", "blocked"].includes(run.status);
const badge = (status, text) =>
  `<span class="badge ${esc(status)}"><i class="status-dot"></i>${esc(text || labels[status] || status)}</span>`;
const button = (text, action, type = "primary", iconName = "", extra = "") =>
  `<button class="button ${type}" type="button" data-action="${action}" ${extra}>${iconName ? icon(iconName) : ""}${esc(text)}</button>`;
const options = (items, value) =>
  items
    .map((item) => {
      const [v, label] = Array.isArray(item) ? item : [item, item];
      return `<option value="${esc(v)}" ${v === value ? "selected" : ""}>${esc(label)}</option>`;
    })
    .join("");
function safeURL(value) {
  try {
    const u = new URL(value, location.origin);
    if (["https:", "http:"].includes(u.protocol)) return esc(u.href);
  } catch {}
  return "#";
}
function avatar(persona, size = "") {
  const p = profile(persona);
  const ref =
    persona?.portrait_url || p.visual_reference_url || p.visual_reference;
  if (
    typeof ref === "string" &&
    (ref.startsWith("/media/") || ref.startsWith("/api/personas/"))
  )
    return `<div class="persona-avatar ${size}"><img src="${esc(ref)}" alt="${esc(personaName(persona))} 외형 참고"></div>`;
  return `<div class="persona-avatar ${size}" aria-label="외형 이미지 미등록">${p.display_name ? esc(p.display_name.slice(0, 1)) : icon("persona")}</div>`;
}
function media(card, { interactive = false } = {}) {
  if (!card?.media) return `<div class="media-empty">${icon("image")}</div>`;
  const path = "/media/" + encodeURIComponent(card.media);
  const alt = esc(card.alt || "콘텐츠 미디어");
  if (/\.(mp4|webm|mov)$/i.test(card.media))
    return `<video src="${path}" preload="metadata" playsinline ${interactive ? "controls" : 'muted tabindex="-1"'} aria-label="${alt}"></video>${interactive ? "" : `<span class="media-video-indicator" aria-hidden="true">${icon("play")}</span>`}`;
  const img = `<img src="${path}" alt="${alt}" loading="lazy">`;
  return interactive
    ? `<a class="media-original-link" href="${path}" target="_blank" rel="noopener noreferrer" aria-label="${alt} · 원본 이미지 새 창으로 보기">${img}<span class="media-original-hint">원본 보기 ${icon("arrow")}</span></a>`
    : img;
}
function renderFeedCell(content) {
  const card = content.payload.cards?.[0];
  return `<button class="instagram-cell" data-action="open-content" data-id="${esc(content.id)}" aria-label="${esc(content.payload.title)}">${media(card)}<span class="cell-status">${esc(labels[content.status] || content.status)}</span></button>`;
}
function renderProductionResults() {
  const rows = [...(state.contents || [])].sort((a, b) =>
    (b.updated_at || "").localeCompare(a.updated_at || ""),
  );
  return `<section class="production-results"><div class="production-results-heading"><div><h2>제작 결과 <span>${rows.length}</span></h2><p>전체 페르소나의 저장된 이미지·영상과 문안입니다. 자동 제작과 직접 제작 결과를 함께 보여줍니다.</p></div><a class="button" href="#videos" data-nav="videos">${icon("videos")}영상 라이브러리</a></div>${
    rows.length
      ? `<div class="production-results-list">${rows
          .map((content) => {
            const payload = content.payload || {},
              cards = payload.cards || [],
              index = Math.min(
                resultCards.get(content.id) || 0,
                Math.max(cards.length - 1, 0),
              );
            const persona = (state.studio?.personas || []).find(
              (p) => p.id === contentPersona(content),
            );
            return `<article class="production-result" data-result-id="${esc(content.id)}"><div class="result-visual"><div class="result-media">${media(cards[index], { interactive: true })}</div>${cards.length > 1 ? `<div class="result-filmstrip" aria-label="첨부 미디어 선택">${cards.map((card, i) => `<button type="button" class="${i === index ? "selected" : ""}" data-action="result-card" data-id="${esc(content.id)}" data-index="${i}" aria-label="${i + 1}번째 ${/\.(mp4|webm|mov)$/i.test(card.media || "") ? "영상" : "이미지"} 보기" aria-pressed="${i === index}">${media(card)}<span>${i + 1}</span></button>`).join("")}</div>` : ""}<p class="result-media-caption">${index + 1} / ${cards.length} · ${esc(cards[index]?.alt || "첨부 미디어")}</p></div><div class="result-copy"><div class="result-meta">${badge(content.status)}<span>${esc(persona ? personaName(persona) : contentPersona(content) || "페르소나")} · v${content.current_version}</span></div><h3>${esc(payload.title)}</h3><p class="result-caption">${esc(payload.caption || "저장된 게시 문안이 없습니다.")}</p>${renderHashtags(payload.hashtags)}${payload.storyboard ? `<details class="result-storyboard"><summary>제작에 사용한 스토리보드</summary>${readableValue(payload.storyboard)}</details>` : ""}${array(payload.review_notes).length ? `<details class="result-storyboard"><summary>검토 메모 ${array(payload.review_notes).length}건</summary>${readableValue(payload.review_notes)}</details>` : ""}<div class="result-actions">${button("검수 화면에서 열기", "open-content", "subtle", "review", `data-id="${esc(content.id)}"`)}<a class="button" href="/api/contents/${encodeURIComponent(content.id)}/export" download>${icon("download")}콘텐츠 받기</a></div></div></article>`;
          })
          .join("")}</div>`
      : empty(
          "아직 완성된 콘텐츠가 없어요",
          "완성되어 대시보드에 등록된 이미지와 영상은 이곳에서 재생하고 문안과 함께 확인할 수 있습니다.",
          "go-auto",
          "AI 자동 제작 보기",
        )
  }</section>`;
}

function empty(title, copy, action = "", actionText = "", extra = "") {
  return `<div class="empty-state ${extra}"><div class="empty-illustration" aria-hidden="true"><span>${icon("image")}</span><span>${icon("spark")}</span><span>${icon("image")}</span></div><h3>${esc(title)}</h3><p>${esc(copy)}</p>${action ? button(actionText, action, "subtle", "plus") : ""}</div>`;
}
function heading(title, copy, actions = "") {
  return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(copy)}</p></div><div class="heading-actions">${actions}</div></div>`;
}
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("toast").hidden = true), 5500);
}
async function api(path, body, timeoutMs = 0) {
  const controller = new AbortController();
  const timer = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-BOCA-Token": state?.token || "",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok)
      throw Error(
        result.error || "저장하지 못했습니다. 입력 내용을 확인해 주세요.",
      );
    return result;
  } catch (error) {
    if (error.name === "AbortError")
      throw Error("제어 요청의 응답을 확인하지 못했습니다. 현재 상태를 새로 확인해 주세요. 요청은 자동으로 재전송하지 않았습니다.");
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
}
let runControlQueue = Promise.resolve();
const pendingRunControls = new Map();
function controlRun(runId, action, message) {
  const key = runId + ":" + action;
  if (pendingRunControls.has(key)) return pendingRunControls.get(key);
  const task = async () => {
    try {
      await api("/api/runs/" + encodeURIComponent(runId) + "/" + action, {}, 15000);
      await refresh(true);
      toast(message);
    } catch (error) {
      toast(error.message);
      await refresh(true).catch(() => {});
    }
  };
  const result = runControlQueue.then(task, task).finally(() => pendingRunControls.delete(key));
  pendingRunControls.set(key, result);
  runControlQueue = result;
  return result;
}
async function mutate(task, message) {
  if (mutating) return;
  mutating = true;
  const buttons = [...document.querySelectorAll("button[type=submit]")];
  buttons.forEach((b) => (b.disabled = true));
  try {
    const value = await task();
    await refresh(true);
    if (message) toast(message);
    return value;
  } catch (error) {
    toast(error.message);
    return null;
  } finally {
    mutating = false;
    buttons.forEach((b) => {
      if (b.isConnected) b.disabled = false;
    });
  }
}
function navigate(next) {
  if (!pages.some((p) => p[0] === next)) return;
  if (
    dirty &&
    !confirm("저장하지 않은 수정이 있습니다. 다른 화면으로 이동할까요?")
  )
    return;
  dirty = false;
  page = next;
  history.replaceState(null, "", "#" + page);
  const usedMobileMenu =
    sidebarMedia.matches && $("sidebar").classList.contains("open");
  setSidebar(false, { restoreFocus: false });
  pageSignature = "";
  render(true);
  window.scrollTo({ top: 0, behavior: "instant" });
  if (usedMobileMenu) $("workspace").focus({ preventScroll: true });
  if (page === "production" || (page === "create" && createTab === "automation"))
    loadAutoEvidence().then(() => render());
  if (page === "videos") loadVideoLibrary();
}
function renderNav() {
  document.querySelector(".workspace-label strong").textContent =
    state?.studio?.settings?.workspace_name || "라이프스타일 스튜디오";
  const ready = (state?.contents || []).filter(
    (c) => c.status === "ready",
  ).length;
  const navigation = $("navigation");
  const signature = JSON.stringify([page, ready]);
  if (navigation.dataset.signature !== signature) {
    const focusedNav = navigation.contains(document.activeElement)
      ? document.activeElement.closest("[data-nav]")?.dataset.nav
      : null;
    navigation.innerHTML = pages
      .map(
        ([id, label], index) =>
          `${id === "logs" ? '<div class="nav-spacer"></div>' : ""}<a href="#${id}" class="nav-link ${page === id ? "active" : ""}" data-nav="${id}" ${page === id ? 'aria-current="page"' : ""}>${icon(id)}<span>${label}</span>${id === "review" && ready ? `<span class="nav-count">${ready}</span>` : ""}</a>`,
      )
      .join("");
    navigation.dataset.signature = signature;
    if (focusedNav && !$("sidebar").inert) {
      navigation
        .querySelector(`[data-nav="${focusedNav}"]`)
        ?.focus({ preventScroll: true });
    }
  }
  $("breadcrumb-current").textContent = pages.find((p) => p[0] === page)[1];
  const personas = state?.studio?.personas || [];
  const selector = $("persona-switch");
  const personaSignature = JSON.stringify([
    personas.map((p) => [p.id, personaName(p)]),
    state.studio?.active_persona_id,
  ]);
  if (
    document.activeElement !== selector &&
    selector.dataset.signature !== personaSignature
  ) {
    selector.innerHTML = personas.length
      ? options(
          personas.map((p) => [p.id, personaName(p)]),
          state.studio.active_persona_id,
        )
      : `<option>${esc(personaName(activePersona()))}</option>`;
    selector.dataset.signature = personaSignature;
  }
}
async function refresh(force = false) {
  if (refreshBusy) return;
  refreshBusy = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), globalThis.BOCA_REMOTE ? 30000 : 8000);
  try {
    const response = await fetch("/api/state", { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw Error("서버 연결을 확인해 주세요.");
    state = await response.json();
    clearTimeout(timeout);
    productionConnection.error = "";
    productionConnection.lastUpdated = new Date().toISOString();
    for (const log of state.automation?.logs || []) allLogs.set(log.id, log);
    $("server-status").textContent = "워크스페이스 연결됨";
    renderProductionStatus();
    patchSpecialistTeam();
    if (page === "production" || (page === "create" && createTab === "automation"))
      await loadAutoEvidence();
    render(force);
  } catch (error) {
    productionConnection.error = "최신 실행 상태를 불러오지 못했습니다. 서버 연결을 확인해 주세요.";
    renderProductionStatus();
    patchSpecialistTeam();
    if (state && page === "production") render();
    throw error;
  } finally {
    clearTimeout(timeout);
    refreshBusy = false;
  }
}
function renderProductionStatus() {
  const button = $("production-status-button");
  if (!button || !state) return;
  const status = productionMonitorState(), run = status.run;
  const visible = isActiveRun(run);
  if (!visible && !button.hidden && button.contains(document.activeElement))
    $("workspace").focus({ preventScroll: true });
  button.hidden = !visible;
  document.querySelector(".topbar").classList.toggle("has-production-status", visible);
  if (!visible) return;
  const count = run.completed_count || 0;
  const limit = run.settings?.stop_after_posts;
  const countLabel = Number.isInteger(limit) && limit > 0 ? `${count}/${limit}건` : `${count}건 완료`;
  const title = status.compactTitle || status.title;
  $("production-status-label").textContent = title;
  $("production-status-stage").textContent = status.stageLabel || "";
  $("production-status-count").textContent = countLabel;
  button.dataset.tone = { running: "active", uncertain: "warning", blocked: "warning" }[status.tone] || status.tone;
  button.setAttribute("aria-label", `${title}, ${status.stageLabel || "단계 시작 전"}, ${countLabel}. 제작 현황 상세 보기`);
  button.title = status.description || "자동 제작 상세 보기";
  if (page === "production") button.setAttribute("aria-current", "page");
  else button.removeAttribute("aria-current");
}
function render(force = false) {
  if (!state) return;
  renderNav();
  renderProductionStatus();
  patchSpecialistTeam();
  if (page === "videos") {
    renderVideoLibrary();
    return;
  }
  const focused = document.activeElement;
  const writing =
    focused &&
    $("workspace").contains(focused) &&
    ["INPUT", "TEXTAREA", "SELECT"].includes(focused.tagName);
  const playing = [...$("workspace").querySelectorAll("video")].some(
    (video) => !video.paused && !video.ended,
  );
  if (!force && (dirty || writing || playing || productionGuides.busy)) return;
  const signature = JSON.stringify([
    page,
    createTab,
    briefFilter,
    reviewFilter,
    sourceFilter,
    feedFilter,
    logFilter,
    logStage,
    selectedId,
    selectedCard,
    state.studio,
    state.contents,
    state.automation,
    state.automation?.worker_status === "waiting" ? runtimePreparationView()?.copy : null,
    state.config,
    productionConnection.error,
    autoEvidenceTab,
    autoArtifacts,
    autoArtifactsError,
    autoVideoState?.connection,
    autoVideoState?.config,
    autoVideoState?.guides,
  ]);
  if (!force && signature === pageSignature) return;
  pageSignature = signature;
  const scroll = window.scrollY;
  const oldLog = $("log-table-scroll")?.scrollTop || 0;
  const oldList = $("review-list")?.scrollTop || 0;
  const sameView = $("workspace").dataset.renderPage === page;
  const monitorFocus = sameView && page === "production" && $("workspace").contains(focused)
    ? [...(focused.closest("button, a")?.attributes || [])].filter((attribute) => attribute.name.startsWith("data-")).map(({name, value}) => [name, value])
    : [];
  const openSourceDetails = new Set(
    sameView
      ? [
          ...$("workspace").querySelectorAll(
            "details[data-source-detail][open]",
          ),
        ].map((node) => node.dataset.sourceDetail)
      : [],
  );
  const focusedSourceDetail =
    sameView && document.activeElement?.matches("summary")
      ? document.activeElement.parentElement?.dataset.sourceDetail
      : null;
  const renderers = {
    overview: renderOverview,
    persona: renderPersonas,
    create: renderCreate,
    production: renderProductionMonitor,
    review: renderReview,
    feed: renderFeed,
    sources: renderSources,
    logs: renderLogs,
    settings: renderSettings,
  };
  $("workspace").innerHTML = renderers[page]();
  updateAutoVideoEstimate();
  $("workspace").dataset.renderPage = page;
  if (monitorFocus.length)
    [...$("workspace").querySelectorAll("button, a")].find((node) => monitorFocus.every(([name, value]) => node.getAttribute(name) === value))?.focus({ preventScroll: true });
  $("workspace")
    .querySelectorAll("details[data-source-detail]")
    .forEach((node) => {
      if (openSourceDetails.has(node.dataset.sourceDetail)) node.open = true;
      if (node.dataset.sourceDetail === focusedSourceDetail)
        node.querySelector("summary")?.focus({ preventScroll: true });
    });
  if ($("log-table-scroll")) $("log-table-scroll").scrollTop = oldLog;
  if ($("review-list")) $("review-list").scrollTop = oldList;
  window.scrollTo({ top: scroll, behavior: "instant" });
}
const videoLibraryStorageKey = "boca.video-library.selected-id";
const videoLibrary = {
  items: [],
  selectedId: null,
  filter: "all",
  query: "",
  busy: false,
  loaded: false,
  error: "",
  lastChecked: null,
  selectionMissing: false,
};
try {
  videoLibrary.selectedId = localStorage.getItem(videoLibraryStorageKey);
} catch {}
const videoStatusLabels = {
  queued: "제작 대기",
  preparing: "제작 준비",
  submitting: "생성 요청 중",
  running: "영상 생성 중",
  downloading: "영상 저장 중",
  completed: "제작 완료",
  failed: "생성 실패",
  attention: "확인 필요",
  uncertain: "결과 확인 필요",
  cancelled: "취소",
  stopped: "중지",
  paused: "일시정지",
};
function videoLibraryGroup(item) {
  if (item.sync_pending && item.sync_error) return "attention";
  if (item.status === "completed" && item.media_available) return "completed";
  if (
    ["queued", "preparing", "submitting", "running", "downloading"].includes(
      item.status,
    )
  )
    return "working";
  return "attention";
}
function videoLibraryURL(item) {
  if (!item?.media_available || !item.media_url) return null;
  try {
    const url = new URL(item.media_url, location.origin);
    return url.origin === location.origin &&
      ["http:", "https:"].includes(url.protocol) &&
      (url.pathname.startsWith("/api/video/jobs/") ||
        url.pathname.startsWith("/api/video-library/imported/"))
      ? url.href
      : null;
  } catch {
    return null;
  }
}
function videoLibraryPersona(item) {
  return (
    item.persona_name ||
    personaName(
      (state?.studio?.personas || []).find((p) => p.id === item.persona_id) || {
        profile: { display_name: item.persona_id || "페르소나 미지정" },
      },
    )
  );
}
function rememberVideoSelection(id) {
  videoLibrary.selectedId = id || null;
  try {
    if (id) localStorage.setItem(videoLibraryStorageKey, id);
    else localStorage.removeItem(videoLibraryStorageKey);
  } catch {}
}
function videoLibraryShell() {
  return `${heading("영상 라이브러리", "만든 영상을 다시 보고, 진행 중인 제작 상태를 확인하세요. 모든 페르소나의 기록을 보관합니다.", `<a class="button" href="/video">${icon("plus")}영상 직접 제작</a>${button("새로고침", "video-library-refresh", "subtle", "refresh")}`)}<div class="video-library-syncbar"><div id="video-library-sync"></div><p>3초마다 상태 자동 확인 · 재생은 유지됩니다.</p></div><div id="video-library-announcement" class="sr-only" aria-live="polite"></div><div class="video-library-layout"><section class="video-library-viewer" aria-label="선택한 영상"><div id="video-library-player" class="video-library-player"></div><div id="video-library-selection-note" class="video-library-selection-note" hidden></div><div id="video-library-detail" class="video-library-detail"></div></section><aside class="video-library-history" aria-label="전체 영상 이력"><div class="video-library-history-heading"><h2>전체 영상 <span id="video-library-total">0</span></h2><span>최신순</span></div><div class="video-library-filters" role="group" aria-label="영상 상태 필터">${[
    ["all", "전체"],
    ["completed", "완료"],
    ["working", "진행 중"],
    ["attention", "확인 필요"],
  ]
    .map(
      ([key, label]) =>
        `<button type="button" data-action="video-library-filter" data-value="${key}" aria-pressed="${videoLibrary.filter === key}" class="${videoLibrary.filter === key ? "active" : ""}">${label}<span data-video-count="${key}">0</span></button>`,
    )
    .join(
      "",
    )}</div><label class="search-field video-library-search">${icon("search")}<input id="video-library-search" type="search" value="${esc(videoLibrary.query)}" placeholder="영상 제목, 페르소나 검색" aria-label="영상 제목과 페르소나 검색"></label><p id="video-library-list-summary" class="video-library-list-summary"></p><div id="video-library-list" class="video-library-list"></div><div id="video-library-list-empty" class="video-library-list-empty" hidden></div></aside></div>`;
}
function videoLibraryVersionLabel(item) {
  if (!item.content_version) return "";
  const relation = item.current_content_version
    ? item.content_version === item.current_content_version
      ? " · 현재 버전"
      : item.content_version < item.current_content_version
        ? " · 이전 버전"
        : " · 별도 버전"
    : "";
  return `콘텐츠 v${item.content_version}${relation}`;
}
function videoLibraryCard(item) {
  const group = videoLibraryGroup(item),
    source =
      { automatic: "자동 제작", manual: "직접 제작", imported: "등록 영상" }[
        item.source
      ] || "저장 영상";
  return `<span class="video-library-card-icon ${group}">${icon(group === "completed" ? "play" : group === "working" ? "clock" : "info")}</span><span class="video-library-card-copy"><strong>${esc(item.title || "제목 없는 영상")}</strong><span>${esc(videoLibraryPersona(item))} · ${source}</span>${item.content_version ? `<span>${esc(videoLibraryVersionLabel(item))}</span>` : ""}<small>${date(item.created_at)}</small></span><span class="video-library-card-status">${badge(group === "completed" ? "completed" : group === "working" ? "running" : "warning", item.status === "completed" && !item.media_available ? "파일 확인 필요" : item.sync_pending && item.sync_error ? "단계 반영 확인" : videoStatusLabels[item.status] || item.status)}${item.duration_requested ? `<small>${esc(item.duration_requested)}초 요청</small>` : ""}</span>`;
}
function patchVideoLibraryHTML(id, markup) {
  const element = $(id);
  if (element && element._libraryHTML !== markup) {
    const opened = [...element.querySelectorAll("details[open]")]
      .map((node) => node.dataset.libraryDetail)
      .filter(Boolean);
    element.innerHTML = markup;
    element._libraryHTML = markup;
    element.querySelectorAll("details[data-library-detail]").forEach((node) => {
      if (opened.includes(node.dataset.libraryDetail)) node.open = true;
    });
  }
}
function videoLibrarySelectedDetail(item) {
  const source =
    {
      automatic: "AI 자동 제작",
      manual: "직접 제작",
      imported: "등록된 콘텐츠",
    }[item.source] || "저장된 영상";
  const metadata = [
    ["제작 방식", source],
    ["생성 요청", date(item.created_at, true)],
    ["최근 변경", date(item.updated_at, true)],
    [
      "요청 길이",
      item.duration_requested ? `${item.duration_requested}초` : null,
    ],
    ["해상도", item.resolution],
    [
      "현재 콘텐츠 상태",
      item.content_status
        ? `${item.current_content_version ? `v${item.current_content_version} · ` : ""}${labels[item.content_status] || item.content_status}`
        : item.status === "completed"
          ? "콘텐츠 등록 전"
          : "제작 완료 후 등록",
    ],
    [
      "이 기록의 콘텐츠 버전",
      item.content_version ? `v${item.content_version}` : null,
    ],
    ["생성 작업 ID", item.job_id],
    ["외부 작업 ID", item.external_id],
  ].filter(([, value]) => value);
  return `<div class="video-library-detail-top">${badge(videoLibraryGroup(item) === "completed" ? "completed" : videoLibraryGroup(item) === "working" ? "running" : "warning", item.sync_pending && item.sync_error ? "단계 반영 확인" : videoStatusLabels[item.status] || item.status)}<span>${esc(videoLibraryPersona(item))}</span>${item.content_version ? `<span>${esc(videoLibraryVersionLabel(item))}</span>` : ""}</div><h2>${esc(item.title || "제목 없는 영상")}</h2>${item.error || item.sync_error ? `<div class="video-library-error">${icon("info")}<p>${esc(item.sync_error ? (item.status === "completed" ? "영상 저장 완료 · " : "") + "제작 단계 반영 확인 필요: " + item.sync_error : item.error)}</p></div>` : ""}${item.next_retry_at && (item.error || item.sync_error) ? `<p class="field-help">자동 복구 ${Number(item.sync_errors || item.poll_errors) || 0}회 · 다음 확인 ${date(item.next_retry_at, true)}</p>` : ""}${["attention", "uncertain"].includes(item.status) || item.sync_pending ? '<p class="field-help"><a href="/video">영상 작업 복구 화면</a>에서 기존 결과 조회·반영을 재개할 수 있습니다. 복구 완료 후 자동 제작이 확인 대기라면 제작 현황에서 재개해 주세요.</p>' : ""}<section class="video-library-caption"><h3>게시 문안</h3><p>${esc(item.caption || "아직 게시 문안이 저장되지 않았습니다.")}</p></section>${item.storyboard ? `<details data-library-detail="storyboard" class="video-library-more"><summary>스토리보드 보기</summary>${readableValue(item.storyboard)}</details>` : ""}<details data-library-detail="metadata" class="video-library-more"><summary>제작 정보</summary><dl>${metadata.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl></details><div class="video-library-detail-actions">${item.content_id ? button("콘텐츠 검수하기", "open-content", "subtle", "review", `data-id="${esc(item.content_id)}"`) : ""}${videoLibraryURL(item) ? `<a class="button" href="${esc(videoLibraryURL(item))}" download>${icon("download")}영상 다운로드</a>` : ""}</div>`;
}
function patchVideoLibraryPlayer(item) {
  const host = $("video-library-player");
  if (!host) return;
  const url = videoLibraryURL(item);
  const key = url
    ? `${item.id}|${item.media_sha256 || url}`
    : `${item?.id || "empty"}|${item?.status || (videoLibrary.loaded ? "empty" : "loading")}|${videoLibrary.error ? "error" : ""}`;
  if (host.dataset.playerKey === key) {
    const player = host.querySelector("video");
    if (player && item)
      player.setAttribute("aria-label", item.title || "선택한 영상");
    return;
  }
  host.querySelector("video")?.pause();
  host.dataset.playerKey = key;
  if (url) {
    const player = document.createElement("video");
    player.id = "video-library-current-player";
    player.controls = true;
    player.playsInline = true;
    player.preload = "metadata";
    player.setAttribute("aria-label", item.title || "선택한 영상");
    player.src = url;
    player.addEventListener("error", () => {
      if (
        !player.isConnected ||
        host.querySelector(".video-library-playback-error")
      )
        return;
      const note = document.createElement("p");
      note.className = "video-library-playback-error";
      note.textContent =
        "영상 파일을 불러오지 못했습니다. 네트워크 연결을 확인한 뒤 다시 열어 주세요.";
      host.append(note);
    });
    host.replaceChildren(player);
    return;
  }
  const working = item && videoLibraryGroup(item) === "working";
  const title = item
    ? working
      ? videoStatusLabels[item.status] || "영상 제작 중"
      : "재생할 파일을 확인해 주세요"
    : videoLibrary.error && !videoLibrary.loaded
      ? "라이브러리에 연결하지 못했어요"
      : videoLibrary.loaded
        ? "아직 저장된 영상이 없어요"
        : "영상 기록을 불러오고 있어요";
  const copy = item
    ? working
      ? "완성된 영상이 저장되면 이 화면에 자동으로 나타납니다."
      : "제작 정보와 오류 내용을 아래에서 확인할 수 있습니다."
    : videoLibrary.loaded
      ? "영상이 만들어지면 제작 이력과 함께 이곳에 보관됩니다."
      : videoLibrary.error || "잠시 후 저장된 영상을 표시합니다.";
  host.innerHTML = `<div class="video-library-player-empty">${icon(working ? "clock" : "play")}<h2>${esc(title)}</h2><p>${esc(copy)}</p></div>`;
}
function patchVideoLibrary() {
  if (page !== "videos" || !$("video-library-list")) return;
  const items = videoLibrary.items;
  let selected = items.find((item) => item.id === videoLibrary.selectedId);
  if (!selected && items.length) {
    const previous = videoLibrary.selectedId;
    selected = items.find((item) => videoLibraryURL(item)) || items[0];
    rememberVideoSelection(selected.id);
    videoLibrary.selectionMissing = Boolean(previous);
  }
  if (!items.length && videoLibrary.loaded && !videoLibrary.error)
    rememberVideoSelection(null);
  patchVideoLibraryPlayer(selected);
  patchVideoLibraryHTML(
    "video-library-detail",
    selected
      ? videoLibrarySelectedDetail(selected)
      : `<div class="video-library-no-selection"><h2>제작 기록을 기다리고 있어요.</h2><p>새 제작을 시작하지 않아도 이전에 만든 영상을 계속 확인할 수 있습니다.</p><a class="button" href="/video">${icon("plus")}영상 직접 제작</a></div>`,
  );
  const query = videoLibrary.query.trim().toLocaleLowerCase();
  const visible = items.filter(
    (item) =>
      (videoLibrary.filter === "all" ||
        videoLibraryGroup(item) === videoLibrary.filter) &&
      (!query ||
        `${item.title || ""} ${videoLibraryPersona(item)} ${item.caption || ""}`
          .toLocaleLowerCase()
          .includes(query)),
  );
  const visibleIDs = new Set(visible.map((item) => item.id));
  const selectedOutsideFilter = selected && !visibleIDs.has(selected.id);
  const selectionNote = $("video-library-selection-note");
  selectionNote.hidden =
    !selectedOutsideFilter && !videoLibrary.selectionMissing;
  selectionNote.textContent = selectedOutsideFilter
    ? "선택한 영상은 현재 검색 조건에 포함되지 않습니다. 재생은 계속 유지됩니다."
    : videoLibrary.selectionMissing
      ? "이전에 선택한 기록을 찾을 수 없어 다른 저장 영상을 열었습니다."
      : "";
  const list = $("video-library-list");
  const nodes = new Map(
    [...list.children].map((node) => [node.dataset.videoId, node]),
  );
  const ids = new Set(items.map((item) => item.id));
  for (const [id, node] of nodes) if (!ids.has(id)) node.remove();
  items.forEach((item, index) => {
    let node = nodes.get(item.id);
    if (!node) {
      node = document.createElement("button");
      node.type = "button";
      node.className = "video-library-card";
      node.dataset.action = "video-library-select";
      node.dataset.id = item.id;
      node.dataset.videoId = item.id;
    }
    const markup = videoLibraryCard(item);
    if (node._libraryHTML !== markup) {
      node.innerHTML = markup;
      node._libraryHTML = markup;
    }
    node.hidden = !visibleIDs.has(item.id);
    node.classList.toggle("selected", item.id === selected?.id);
    node.setAttribute("aria-pressed", String(item.id === selected?.id));
    node.setAttribute(
      "aria-label",
      `${item.title || "제목 없는 영상"}${item.content_version ? ` · ${videoLibraryVersionLabel(item)}` : ""} · ${item.sync_pending && item.sync_error ? "단계 반영 확인" : videoStatusLabels[item.status] || item.status}`,
    );
    if (list.children[index] !== node)
      list.insertBefore(node, list.children[index] || null);
  });
  $("video-library-total").textContent = String(items.length);
  $("video-library-list-summary").textContent =
    `${visible.length}개 표시 · 전체 ${items.length}개`;
  document.querySelectorAll("[data-video-count]").forEach((node) => {
    node.textContent = String(
      node.dataset.videoCount === "all"
        ? items.length
        : items.filter(
            (item) => videoLibraryGroup(item) === node.dataset.videoCount,
          ).length,
    );
  });
  document
    .querySelectorAll("[data-action=video-library-filter]")
    .forEach((node) => {
      const active = node.dataset.value === videoLibrary.filter;
      node.classList.toggle("active", active);
      node.setAttribute("aria-pressed", String(active));
    });
  const emptyNode = $("video-library-list-empty");
  emptyNode.hidden = visible.length > 0;
  emptyNode.textContent = !videoLibrary.loaded
    ? videoLibrary.error
      ? "기록을 불러오지 못했습니다. 다시 연결해 주세요."
      : "저장된 기록을 확인하고 있습니다."
    : items.length
      ? "검색 조건에 맞는 영상이 없습니다."
      : "아직 영상 제작 기록이 없습니다.";
  const checked = videoLibrary.lastChecked
    ? new Date(videoLibrary.lastChecked).toLocaleTimeString("ko-KR", {
        hour12: false,
        timeZone: "Asia/Seoul",
      })
    : null;
  patchVideoLibraryHTML(
    "video-library-sync",
    `${videoLibrary.error ? `<span class="video-library-connection offline">${icon("info")}연결 확인 필요</span><span>${esc(videoLibrary.error)}</span><button class="text-button" type="button" data-action="video-library-refresh">다시 연결</button>` : `<span class="video-library-connection"><i></i>${videoLibrary.loaded ? "자동 갱신 중" : "연결 중"}</span>`}${checked ? `<time>최근 확인 ${checked}</time>` : ""}`,
  );
  const announcement = $("video-library-announcement"),
    summary = `전체 영상 ${items.length}개, 재생 가능 ${items.filter((item) => videoLibraryGroup(item) === "completed").length}개, 진행 중 ${items.filter((item) => videoLibraryGroup(item) === "working").length}개`;
  if (videoLibrary.loaded && announcement.textContent !== summary)
    announcement.textContent = summary;
}
async function loadVideoLibrary() {
  if (videoLibrary.busy) return;
  videoLibrary.busy = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), globalThis.BOCA_REMOTE ? 30000 : 10000);
  try {
    const response = await fetch("/api/video-library", {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok)
      throw Error(
        "저장된 목록을 불러오지 못했습니다. 자동으로 다시 확인합니다.",
      );
    const data = await response.json();
    if (!Array.isArray(data.items))
      throw Error("영상 기록의 응답을 확인할 수 없습니다.");
    videoLibrary.items = [...data.items].sort(
      (a, b) =>
        (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0),
    );
    videoLibrary.loaded = true;
    videoLibrary.error = "";
    videoLibrary.lastChecked = Date.now();
  } catch (error) {
    videoLibrary.error =
      error.name === "AbortError"
        ? "상태 확인이 지연되고 있습니다. 자동으로 다시 확인합니다."
        : "영상 상태를 확인하지 못했습니다. 연결되면 자동으로 갱신합니다.";
  } finally {
    clearTimeout(timeout);
    videoLibrary.busy = false;
    patchVideoLibrary();
  }
}
function renderVideoLibrary() {
  if (!$("video-library-list")) {
    $("workspace").innerHTML = videoLibraryShell();
    $("workspace").dataset.renderPage = "videos";
    loadVideoLibrary();
  }
  patchVideoLibrary();
}

function contentTile(content) {
  return `<button class="content-tile" data-action="open-content" data-id="${esc(content.id)}"><div class="content-image">${media(content.payload.cards?.[0])}${badge(content.status)}<span class="card-count">${icon("stack")} ${content.payload.cards?.length || 0}</span></div><h3>${esc(content.payload.title)}</h3><p>${esc(shortDate(content.updated_at))} 저장 · v${content.current_version}</p></button>`;
}
function renderOverview() {
  const persona = activePersona(),
    p = profile(persona),
    contents = state.contents || [],
    ready = contents.filter((c) => c.status === "ready").length,
    approved = contents.filter((c) => c.status === "approved").length;
  const run = currentRun(),
    sources = sourceRows(),
    logs = [...allLogs.values()].sort((a, b) => b.id - a.id).slice(0, 4);
  return `${heading("스튜디오 개요", "오늘 만들 이야기와 검토할 콘텐츠를 한곳에서 확인하세요.", `<span class="date-pill">${new Date().toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "long", timeZone: "Asia/Seoul" })}</span>${button("AI 자동 제작", "go-auto", "primary", "spark")}`)}<div class="overview-main"><section class="persona-feature"><div class="feature-heading"><span>현재 작업 중인 페르소나</span>${badge("draft", "가상 인플루언서")}</div><div class="persona-feature-content"><div class="persona-feature-avatar-wrap">${avatar(persona, "large")}<p class="avatar-note">${persona.portrait_url ? "외형 참고 등록됨" : "외형 이미지 미등록"}</p></div><div><div class="persona-feature-title"><h2>${esc(personaName(persona))}</h2></div><p class="persona-subtitle">${esc([p.age_description, p.work?.location, p.work?.role].filter(Boolean).join(" · "))}</p><div class="persona-tags">${array(
    p.interests,
  )
    .slice(0, 4)
    .map((t) => `<span class="tag">${esc(t)}</span>`)
    .join(
      "",
    )}</div><p class="persona-bio">${esc(personaBio(persona) || [p.home?.neighborhood ? "집은 " + p.home.neighborhood + "." : "", array(p.personality)[0] || "일상을 나누는 가상 인플루언서.", p.family?.daughter ? p.family.daughter.age + "살 딸과 함께하는 작은 순간들." : ""].filter(Boolean).join(" "))}</p></div></div><div class="feature-footer"><span>${icon("lock")}프로필 v${persona.version || p.version || 1} · 사람의 검토 후 게시</span><button class="text-button" data-nav="persona">페르소나 관리 ${icon("arrow")}</button></div></section><section class="panel today-panel"><div class="today-header"><h2>다음 할 일</h2><span>나의 작업 가이드</span></div><button class="todo-item" data-nav="review"><span class="todo-icon">${icon("review")}</span><span><strong>${ready ? `콘텐츠 ${ready}건 검수하기` : "첫 콘텐츠를 검수할 준비"}</strong><small>${ready ? "이미지와 문안을 확인하고 게시할 버전을 승인하세요." : "제작이 끝나면 이곳에 검수할 콘텐츠가 모여요."}</small></span>${icon("arrow", "chevron")}</button><button class="todo-item" data-nav="sources"><span class="todo-icon green">${icon("sources")}</span><span><strong>${sources.length ? "GS 소재 수집 기록 확인" : "GS 소재는 AI가 찾아요"}</strong><small>${sources.length ? `활용 가능한 소재 ${sources.filter((s) => s.status === "active").length}건과 수집 출처를 확인하세요.` : "AI 자동 제작에서 공식 자료 탐색·등록을 함께 진행해요."}</small></span>${icon("arrow", "chevron")}</button><button class="todo-item" data-nav="settings"><span class="todo-icon pink">${icon("instagram")}</span><span><strong>Instagram 게시 계정 확인</strong><small>${state.config.instagram?.connection === "verified" ? "계정 연결과 승인된 콘텐츠를 확인하세요." : "대상 계정을 지정하고 연결 상태를 확인하세요."}</small></span>${icon("arrow", "chevron")}</button></section></div><div class="stat-strip">${[
    ["전체 콘텐츠", contents.length, "저장된 이야기", "stack"],
    ["검수 대기", ready, "사람의 확인이 필요해요", "review"],
    ["승인 완료", approved, "게시를 기다리고 있어요", "check"],
    [
      "제작 상태",
      run ? labels[run.status] || run.status : "실행 전",
      run?.completed_count
        ? `${run.completed_count}건 제작 완료`
        : "콘텐츠 제작에서 시작해요",
      "create",
    ],
  ]
    .map(
      ([label, value, desc, i]) =>
        `<div class="stat-item"><span class="stat-label">${icon(i)}${label}</span><strong class="stat-value ${typeof value === "string" ? "word-value" : ""}">${value}</strong><span class="stat-description">${desc}</span></div>`,
    )
    .join(
      "",
    )}</div><div class="overview-bottom"><section class="panel"><div class="panel-header"><h2>최근 콘텐츠 <span class="section-count">${contents.length}</span></h2><button class="text-button" data-nav="feed">전체 보기 ${icon("arrow")}</button></div>${contents.length ? `<div class="recent-grid">${contents.slice(0, 3).map(contentTile).join("")}</div>` : empty("첫 번째 이야기를 기다리고 있어요", "페르소나를 선택하면 AI가 일상 주제를 정하고, 어울리는 소재로 콘텐츠를 만듭니다.", "go-auto", "AI 자동 제작 시작하기")}</section><section class="panel"><div class="panel-header"><h2>최근 활동</h2><button class="text-button" data-nav="logs">전체 보기 ${icon("arrow")}</button></div>${logs.length ? `<ol class="activity-mini">${logs.map((l) => `<li><i></i><div><p>${esc(l.message || l.event)}</p><time>${date(l.created_at)}</time></div></li>`).join("")}</ol>` : empty("아직 활동 기록이 없어요", "페르소나 설정과 콘텐츠 제작 과정이 여기에 기록됩니다.", "", "", "empty-compact")}</section></div>`;
}
function renderPersonas() {
  const personas = state.studio?.personas || [activePersona()];
  return `${heading("페르소나", "한 사람의 외형부터 취향, 말투까지. 콘텐츠의 기준을 만들어 주세요.", button("페르소나 만들기", "new-persona", "primary", "plus"))}<div class="page-toolbar"><span class="small muted">전체 페르소나 <strong class="accent-text">${personas.length}</strong></span><span class="small muted">프로필은 버전별로 보관됩니다.</span></div><div class="persona-grid">${personas
    .map((persona) => {
      const p = profile(persona),
        active = persona.id === state.studio?.active_persona_id,
        posts = personaContents(persona.id);
      return `<article class="persona-card ${active ? "is-active" : ""}"><div class="persona-card-top">${avatar(persona)}${active ? badge("draft", "현재 작업 중") : badge("ready", "설정됨")}</div><h2>${esc(personaName(persona))}</h2><p class="persona-subtitle">${esc([p.age_description, p.work?.location, p.work?.role].filter(Boolean).join(" · ")) || "기본 프로필을 설정해 주세요."}</p><p class="persona-bio">${esc(personaBio(persona) || array(p.personality).join(", "))}</p><div class="persona-tags">${array(
        p.interests,
      )
        .slice(0, 3)
        .map((t) => `<span class="tag">${esc(t)}</span>`)
        .join(
          "",
        )}</div><div class="persona-card-stats"><div><span>전체 콘텐츠</span><strong>${posts.length}</strong></div><div><span>검수 대기</span><strong>${posts.filter((c) => c.status === "ready").length}</strong></div><div><span>프로필 버전</span><strong>v${persona.version || 1}</strong></div></div><div class="persona-card-actions">${button("프로필 편집", "edit-persona", "", "edit", `data-id="${esc(persona.id)}"`)}${active ? button("피드 미리보기", "go-feed", "subtle", "feed") : button("작업 페르소나로 선택", "select-persona", "subtle", "", `data-id="${esc(persona.id)}"`)}</div></article>`;
    })
    .join(
      "",
    )}<button class="new-persona-card" data-action="new-persona"><span>${icon("plus")}</span><h3>새로운 일상의 주인공</h3><p>새 페르소나를 만들고<br>각자의 이야기를 구분해서 관리하세요.</p></button></div><div class="helper-banner">${icon("info")}<div><strong>페르소나와 실제 Instagram 계정은 따로 관리해요.</strong>이곳에서 가상 인물의 설정과 프로필 초안을 만들 수 있어요. 실제 계정 개설과 연결 상태는 설정에서 확인하세요.</div></div>`;
}
function renderCreate() {
  const p = activePersona(),
    briefs = (state.studio?.briefs || []).filter((b) => b.persona_id === p.id),
    run = currentRun();
  return `${heading("콘텐츠 제작", "AI가 일상을 기획하고 제작합니다. 완성된 콘텐츠는 사람이 검토하고 승인해요.", createTab === "briefs" ? button("직접 기획 추가", "new-brief", "", "plus") : button("검수 대기 확인", "go-review", "", "review"))}<div class="page-toolbar"><div class="tabs"><button class="tab ${createTab === "automation" ? "active" : ""}" data-action="create-tab" data-tab="automation">AI 자동 제작${isActiveRun(run) ? '<span class="tab-count">' + esc(labels[run.status]) + "</span>" : ""}</button><button class="tab ${createTab === "results" ? "active" : ""}" data-action="create-tab" data-tab="results">제작 결과<span class="tab-count">${state.contents?.length || 0}</span></button><button class="tab ${createTab === "briefs" ? "active" : ""}" data-action="create-tab" data-tab="briefs">직접 기획 <span class="optional-tab-label">선택</span><span class="tab-count">${briefs.length}</span></button></div></div>${
    createTab === "automation"
      ? renderAutomation()
      : createTab === "results"
        ? renderProductionResults()
        : `<div class="page-toolbar"><div class="source-status-tabs">${[
            ["all", "전체"],
            ["draft", "기획 초안"],
            ["queued", "제작 대기"],
            ["completed", "완료"],
          ]
            .map(
              ([v, t]) =>
                `<button class="${briefFilter === v ? "active" : ""}" data-action="brief-filter" data-value="${v}">${t}</button>`,
            )
            .join(
              "",
            )}</div><span class="small muted">${esc(personaName(p))}의 이야기</span></div><div class="brief-layout"><div class="brief-grid">${renderBriefCards(briefs)}</div><aside class="guide-panel">${icon("leaf")}<h2>상품보다 먼저,<br>오늘의 이야기를.</h2><p>페르소나가 보낼 법한 하루에서 출발하세요. 그 장면에 어울리는 GS 소재를 나중에 연결하면 자연스러운 콘텐츠가 됩니다.</p><ul class="idea-list">${[
            [
              "퇴근 후, 15분만 집을 정리한다면",
              "목동 집으로 돌아온 워킹맘의 저녁. 딸이 잠들기 전, 작은 공간을 정리하며 하루를 마무리하는 이야기를 기획합니다.",
            ],
            [
              "주말 아침을 느리게 시작하는 법",
              "일찍 일어난 딸과 주말 아침을 준비하는 가상의 일상. 간단한 식사와 집에서 발견하는 취향을 중심으로 기획합니다.",
            ],
            [
              "여의도 점심시간의 작은 취향",
              "직장인의 점심시간 산책에서 발견한 취향. 과장된 경험담 없이 도시의 계절과 생활의 선택을 이야기합니다.",
            ],
          ]
            .map(
              ([title, brief]) =>
                `<li><button data-action="idea-brief" data-title="${esc(title)}" data-brief="${esc(brief)}">${icon("plus")}${esc(title)}</button></li>`,
            )
            .join(
              "",
            )}</ul><p class="suggested-guidance">아이디어 예시입니다. 선택 후 자유롭게 고쳐보세요.</p></aside></div>`
  }`;
}
function renderBriefCards(briefs) {
  const filtered = briefs.filter(
    (b) => briefFilter === "all" || b.status === briefFilter,
  );
  if (!filtered.length)
    return `<section class="panel brief-full-empty">${empty(briefs.length ? "선택한 상태의 기획이 없어요" : "어떤 하루를 이야기할까요?", briefs.length ? "다른 상태를 선택하거나 새로운 이야기를 기획해 보세요." : "주제와 전달하고 싶은 장면을 적어주세요. 이미지와 문안으로 만들기 전에 이야기의 흐름을 먼저 잡아요.", "new-brief", "콘텐츠 기획하기", "full-empty")}</section>`;
  return filtered
    .map((b) => {
      const persona = (state.studio?.personas || []).find(
        (p) => p.id === b.persona_id,
      );
      return `<article class="brief-card"><div class="brief-card-head">${badge(b.status)}<span class="small muted">${shortDate(b.updated_at || b.created_at)}</span></div><h3>${esc(b.title)}</h3><p>${esc(b.brief)}</p><div class="brief-meta"><span class="tag">${esc(persona ? personaName(persona) : "페르소나")}</span><span class="tag">${b.format === "video" ? "짧은 영상" : b.format === "image" ? "단일 이미지" : "카드형 피드"}</span><span class="tag">${esc(affiliateLabel(b.affiliate) || "이야기에 맞게 선택")}</span></div><div class="brief-card-actions">${button("기획 편집", "edit-brief", "", "edit", `data-id="${esc(b.id)}"`)}${b.content_id && state.contents.some((c) => c.id === b.content_id) ? button("결과 보기", "open-content", "subtle", "", `data-id="${esc(b.content_id)}"`) : b.status === "draft" ? button("제작 요청", "produce-brief", "primary", "play", `data-id="${esc(b.id)}"`) : `<span class="small muted push-right">${b.status === "queued" ? "작업자 대기 중" : b.status === "failed" ? "수정 후 다시 요청해 주세요" : "제작 결과를 기다리고 있어요"}</span>`}</div></article>`;
    })
    .join("");
}
const specialistRoleDefaults = {
  sources: { id: "source_researcher", name: "GS 소재 리서처" },
  planning: { id: "lifestyle_planner", name: "라이프스타일 기획자" },
  storyboard: { id: "storyboard_director", name: "스토리보드 디렉터" },
  copy: { id: "persona_copywriter", name: "페르소나 카피라이터" },
  images: { id: "visual_producer", name: "비주얼 프로듀서" },
  quality: { id: "quality_reviewer", name: "콘텐츠 품질 검수자" },
  register: { id: "feed_editor", name: "피드 패키징 에디터" },
};
function specialistRoleForStage(stage) {
  const fallback = specialistRoleDefaults[stage] || {
    id: stage,
    name: "담당 전문가",
  };
  const specialists = state.automation?.specialists || {};
  const roles =
    isActiveRun(currentRun()) && specialists.roles?.length
      ? specialists.roles
      : specialists.configured_roles?.length
        ? specialists.configured_roles
        : specialists.roles || [];
  const role = roles.find(
    (item) => item.id === fallback.id || item.stages?.includes(stage),
  );
  const reference = state.automation?.stages?.find(
    (item) => item.key === stage,
  )?.specialist;
  return (
    role || {
      ...fallback,
      ...(reference
        ? {
            id: reference.role_id || fallback.id,
            name: reference.name || fallback.name,
          }
        : {}),
    }
  );
}
function specialistAssignmentForStage(stage) {
  const specialists = state.automation?.specialists || {},
    run = currentRun();
  if (!run) return null;
  const assignments = (specialists.assignments || []).filter(
    (item) => item.run_id === run.id && item.agent_id,
  );
  const current =
    specialists.current?.run_id === run.id && specialists.current?.agent_id
      ? specialists.current
      : null;
  const cycle =
    (specialists.cycle?.run_id === run.id ? specialists.cycle.id : null) ||
    current?.cycle_id ||
    (autoArtifacts?.run_id === run.id
      ? autoArtifacts.stages?.find(
          (item) => item.cycle_number === run.cycle_number,
        )?.cycle_id
      : null);
  if (current?.stage === stage) return current;
  if (!cycle) return null;
  const trace = specialistStageTrace(stage);
  // A repaired stage has a historical assignee, but no current handoff yet.
  if (trace?.cycle_id === cycle && ["pending", "running"].includes(trace.status))
    return null;
  return (
    assignments
      .filter((item) => item.stage === stage && item.cycle_id === cycle)
      .sort(
        (a, b) =>
          (b.attempt || 0) - (a.attempt || 0) ||
          (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0),
      )[0] || null
  );
}
function specialistAssignmentBadge(assignment, { live = false } = {}) {
  if (!assignment?.agent_id) return badge("pending", "대기");
  const states = {
    completed: ["completed", "완료"],
    failed: ["failed", "실패"],
    uncertain: ["uncertain", "확인 필요"],
    interrupted: ["stopped", "중단됨"],
    skipped: ["paused", "검수 보류"],
  };
  if (assignment.status === "assigned") {
    if (live && (productionConnection.error || state.automation?.worker_status === "stale"))
      return badge("uncertain", "연결 확인");
    if (live && currentRun()?.status === "paused") return badge("paused", "일시정지");
    const current = state.automation?.specialists?.current;
    const working =
      live &&
      current?.assignment_id === assignment.assignment_id &&
      currentRun()?.status === "running" &&
      state.automation?.worker_status === "active";
    return badge(
      working ? "running" : "pending",
      working ? "작업 중" : "배정됨",
    );
  }
  const status = states[assignment.status] || [
    "pending",
    assignment.status || "기록됨",
  ];
  return badge(...status);
}
function renderSpecialistCoordinator() {
  const specialists = state.automation?.specialists || {},
    current = specialists.current,
    run = currentRun();
  const actualCurrent =
    current?.agent_id && run?.id && current.run_id === run.id ? current : null;
  const coordinator = isActiveRun(run)
    ? specialists.coordinator || specialists.configured_coordinator
    : specialists.configured_coordinator || specialists.coordinator;
  return `${specialists.configuration_error ? `<div class="inline-warning">${icon("info")}${esc(specialists.configuration_error)}</div>` : ""}<div class="specialist-coordinator"><span class="specialist-coordinator-icon">${icon("persona")}</span><div><span class="specialist-role-label">흐름을 연결하는 역할</span><h3>${esc(coordinator?.name || "제작 총괄")}</h3><p>이전 결과를 정리해 다음 전문가에게 전달하고, 진행 상태와 중단 복구를 관리합니다.</p></div><span class="specialist-config-tag">조율</span></div><div class="specialist-team-caption"><p>전문가가 한 단계씩 맡아 순서대로 이어갑니다. 게시 전에는 사람이 최종 검수합니다.</p><span>${actualCurrent ? `${actualCurrent.status === "assigned" ? "현재" : "최근"} 배정: ${esc(actualCurrent.role_name || specialistRoleForStage(actualCurrent.stage).name)}` : specialists.configured_enabled === false ? "전문가 위임이 현재 설정에서 꺼져 있습니다." : "전문 역할 구성 · 실제 에이전트 배정 대기"}</span></div>`;
}
function renderSpecialistStage(stage, index) {
  const run = currentRun(),
    trace = specialistStageTrace(stage.key),
    role = specialistRoleForStage(stage.key),
    assignment = specialistAssignmentForStage(stage.key);
  const working =
    assignment?.status === "assigned" &&
    assignment.assignment_id ===
      state.automation?.specialists?.current?.assignment_id &&
    run?.status === "running" &&
    state.automation?.worker_status === "active" && !productionConnection.error;
  return `<li class="specialist-stage ${working ? "current" : ""}" data-specialist-stage="${esc(stage.key)}"><span class="stage-number">${index + 1}</span><div class="specialist-stage-copy"><span class="specialist-stage-role">${esc(assignment?.role_name || role.name)}${stage.key === "quality" ? "<small>독립 검수</small>" : ""}</span><strong>${esc(autoStageLabels[stage.key] || stage.label)}</strong><p>${esc(autoStageDescriptions[stage.key] || "저장된 입력을 받아 결과를 다음 단계에 전달합니다.")}</p></div><div class="specialist-stage-state">${specialistStageBadge(stage.key, trace, assignment)}${trace ? `<button type="button" class="text-button auto-stage-open" data-action="open-stage" data-cycle="${esc(trace.cycle_id)}" data-stage="${esc(trace.stage)}">${assignment && assignment.cycle_id === trace.cycle_id ? "단계 결과" : "저장된 결과"}${icon("arrow")}</button>` : ""}</div></li>`;
}
function renderStageSpecialist(data, stage) {
  const storedRole = data.specialist || data.input?.specialist;
  const role = storedRole || specialistRoleForStage(stage);
  const assignment =
    data.specialist_assignment || data.result?.specialist_assignment || null;
  const assignments = Array.isArray(data.specialist_assignments)
    ? data.specialist_assignments
    : [];
  const actual = assignment?.agent_id ? assignment : null;
  const live = !!actual && actual.run_id === currentRun()?.id &&
    actual.assignment_id === state.automation?.specialists?.current?.assignment_id;
  const label =
    actual?.role_name || role.name || specialistRoleForStage(stage).name;
  return `<section class="stage-specialist"><div class="stage-specialist-heading"><div><span class="specialist-role-label">${actual ? "실제 배정 기록" : storedRole ? "저장된 전문 역할" : "현재 전문 역할 안내"}</span><h3>${esc(label)}</h3></div>${specialistAssignmentBadge(actual, { live })}</div>${actual ? `<dl class="stage-specialist-facts"><div><dt>담당 에이전트</dt><dd>${esc(actual.agent_id)}</dd></div><div><dt>배정 시각</dt><dd>${date(actual.created_at)}</dd></div><div><dt>배정 상태 변경</dt><dd>${date(actual.updated_at)}</dd></div></dl>${actual.result_summary ? `<div class="specialist-handoff"><h4>다음 단계에 전달한 요약</h4>${readableValue(actual.result_summary)}</div>` : '<p class="specialist-assignment-note">인계 요약은 이 단계의 결과가 저장되면 표시됩니다. 진행 기록은 아래에서 확인할 수 있습니다.</p>'}${assignments.length > 1 ? `<details class="specialist-assignment-history"><summary>이 단계의 배정 이력 ${assignments.length}건</summary><ol>${assignments.map((item) => `<li><div><strong>${esc(item.role_name || label)}</strong>${specialistAssignmentBadge(item)}</div><p>${esc(item.agent_id || "에이전트 ID 미기록")}</p>${item.result_summary ? readableValue(item.result_summary) : ""}<time>${date(item.updated_at || item.created_at)}</time></li>`).join("")}</ol></details>` : ""}<p class="specialist-assignment-note">제작 총괄이 남긴 실행·인계 기록입니다. 서버가 에이전트 실행 환경을 별도로 확인한 것은 아닙니다.</p>` : '<p class="specialist-assignment-note">이 역할의 실제 에이전트 배정 기록이 없습니다. 역할 설정만으로 실행 중이라고 표시하지 않습니다.</p>'}</section>`;
}

function specialistStageTrace(stage) {
  const specialists = state.automation?.specialists || {}, run = currentRun();
  if (specialists.cycle?.run_id === run?.id) {
    return (specialists.stage_jobs || []).find((job) => job.stage === stage && job.cycle_id === specialists.cycle.id) || null;
  }
  // Compatibility with a server that has not yet reloaded the live status API.
  const trace = latestStageTrace(stage);
  return trace?.cycle_number === run?.cycle_number ? trace : null;
}

function specialistStageBadge(stage, trace, assignment) {
  if (assignment) return specialistAssignmentBadge(assignment, { live: true });
  const run = currentRun();
  if (trace?.status === "completed") return badge("completed", "단계 완료");
  if (["failed", "uncertain"].includes(trace?.status)) return badge(trace.status);
  if (["stopped", "completed"].includes(run?.status)) return badge("pending", "배정 기록 없음");
  if (run?.status === "paused") return badge("paused", "일시정지");
  if (run?.status === "blocked") return badge("uncertain", "확인 필요");
  if (trace?.status === "running") return badge("pending", "전문가 배정 대기");
  if (run?.status === "running" && !run.cycle_number && stage === "sources") return badge("pending", "작업자 대기");
  return badge("pending", "순서 대기");
}

function runtimePreparationView() {
  const a = state?.automation || {}, run = currentRun(), runtime = a.worker_runtime;
  if (run?.status !== "running" || !runtime?.online || runtime.run_id !== run.id ||
      !["starting", "running"].includes(runtime.status)) return null;
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(run.start_at)) / 1000)) || 0;
  const elapsed = seconds < 60 ? `${seconds}초` : `${Math.floor(seconds / 60)}분 ${seconds % 60}초`;
  const delayed = !run.cycle_number && seconds >= 120;
  return {
    heading: delayed ? "첫 단계 시작이 지연되고 있어요" : runtime.status === "starting" ? "AI 작업자에 연결하고 있어요" : "AI가 제작 입력을 확인하고 있어요",
    copy: `실행 요청 후 ${elapsed} · ${runtime.status === "starting" ? "로컬 AI 실행 환경에 연결 중입니다." : "AI 연결이 완료되어 단계 입력과 전문가 배정을 준비 중입니다."}${delayed ? " 아직 첫 단계 시작 기록은 없습니다. 중지 후 다시 시작하기보다 실행 로그를 먼저 확인해 주세요." : " 실제 단계가 시작되면 담당자와 결과가 표시됩니다."}`,
    tone: delayed ? "stale" : "waiting",
  };
}

function specialistWorkerView() {
  const a = state.automation || {}, run = currentRun();
  if (productionConnection.error) return { heading: "상태 연결 확인 필요", copy: productionConnection.error, tone: "stale" };
  if (run?.status === "scheduled") return { heading: "예약한 시작 시각 대기", copy: "예약 시각 이후 작업자가 연결되면 전문가에게 첫 단계를 배정합니다.", tone: "waiting" };
  if (run?.status === "paused") return { heading: "자동 제작 일시정지", copy: "새 작업을 시작하지 않고 저장된 결과를 보관하고 있습니다.", tone: "idle" };
  if (run?.status === "blocked") return { heading: "확인 후 재개가 필요합니다", copy: run.pause_reason || "단계 기록에서 오류와 복구 상태를 확인해 주세요.", tone: "stale" };
  if (run?.status !== "running") return { heading: "실행 중인 AI 작업 없음", copy: "저장된 전문가 배정과 단계 결과를 표시합니다.", tone: "idle" };
  const retryAfter = a.specialists?.cycle?.retry_after || a.worker_runtime?.retry_after;
  if (retryAfter && Date.parse(retryAfter) > Date.now()) return {
    heading: "자동 복구 후 재시도를 기다리고 있어요",
    copy: `${Math.max(1, Math.ceil((Date.parse(retryAfter) - Date.now()) / 1000))}초 후 중단된 단계부터 이어갑니다. 완료된 단계와 기존 미디어는 보존됩니다.`, tone: "waiting",
  };
  if (a.worker_status === "stale") return { heading: "AI 작업자 응답 확인 필요", copy: "작업 소유권이 만료되었습니다. 저장된 결과와 외부 작업 상태를 확인해야 합니다.", tone: "stale" };
  if (a.worker_status === "active") {
    const assignment = a.specialists?.current;
    const stage = autoStageLabels[run.current_stage] || "현재 단계";
    return { heading: assignment?.status === "assigned" ? `${assignment.role_name} 작업 중` : "제작 총괄이 전문가 배정을 준비하고 있습니다",
      copy: `${stage}의 실제 배정·완료 기록을 자동으로 반영합니다.`, tone: "active" };
  }
  const preparation = runtimePreparationView();
  if (preparation) return preparation;
  const waitStart = a.worker_last_seen_at || run.start_at;
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(waitStart)) / 60000)) || 0;
  const delay = minutes >= 5;
  return { heading: delay ? "AI 작업자 연결이 지연되고 있습니다" : "AI 작업자 연결 대기",
    copy: `${run.cycle_number ? "다음 단계 작업자 연결을 기다리고 있습니다." : "실행 요청은 접수됐지만 아직 첫 단계가 시작되지 않았습니다."} ${minutes}분 경과. ${delay ? "제작 작업자의 실행 상태를 확인해 주세요. 자동 시작 버튼을 다시 누를 필요는 없습니다." : "작업자가 연결되면 실제 전문가 배정 상태가 표시됩니다."}`,
    tone: delay ? "stale" : "waiting" };
}

function renderSpecialistSync() {
  const updated = productionConnection.lastUpdated;
  const time = updated ? new Date(updated).toLocaleTimeString("ko-KR", { hour12: false, timeZone: "Asia/Seoul" }) : "—";
  return `<p class="field-help specialist-sync" role="status">${productionConnection.error ? "연결 확인 필요 · 마지막 확인" : "5초마다 상태 확인 · 최근 확인"} ${esc(time)}</p>`;
}

function patchSpecialistTeam() {
  if (page !== "create" || createTab !== "automation" || !state) return;
  const panel = $("specialist-team");
  if (!panel) return;
  const focused = panel.contains(document.activeElement) ? document.activeElement.dataset : null;
  const html = renderSpecialistTeam();
  if (panel.outerHTML === html) return;
  panel.outerHTML = html;
  if (focused?.action === "open-stage") {
    const replacement = [...$("specialist-team").querySelectorAll("[data-action=open-stage]")]
      .find((button) => button.dataset.cycle === focused.cycle && button.dataset.stage === focused.stage);
    replacement?.focus({ preventScroll: true });
  }
}

function renderSpecialistTeam() {
  const a = state.automation || {}, run = currentRun();
  const workerView = specialistWorkerView();
  const reviewDeferred = (isActiveRun(run) ? run?.settings : state.config)?.ai_quality_review_enabled === false;
  return `<section id="specialist-team" class="panel auto-process-panel" aria-label="전문가 팀"><div class="section-top"><div><h2>전문가 팀</h2><p class="field-help">전문 역할과 실제 배정 상태를 함께 확인하세요.</p>${renderSpecialistSync()}</div><span class="auto-loop-tag">${icon("refresh")}연속 제작</span></div><div class="auto-worker-status" data-worker="${esc(workerView.tone)}"><span class="auto-worker-dot"></span><div><strong>${esc(workerView.heading)}</strong><p>${esc(workerView.copy)}</p>${a.worker_last_seen_at ? `<small>마지막 연결 ${date(a.worker_last_seen_at)}</small>` : ""}</div></div>${renderAutoProgress(run)}${renderSpecialistCoordinator()}${reviewDeferred ? `<p class="field-help">AI 품질 검수는 보류 중입니다. 미디어 완성 후 피드를 등록하고, 미확인 사항은 사람의 검수 메모로 넘깁니다.</p>` : ""}<ol class="auto-loop-stages specialist-team-stages">${(
    (a.stages || []).filter((stage) => stage.key !== "quality" || !reviewDeferred)
  )
    .map(renderSpecialistStage)
    .join(
      "",
    )}</ol><div class="auto-loop-return">${icon("refresh")}각 단계가 끝나면 결과를 바로 저장하고 다음 단계로 이어집니다. 피드 등록 후에는 설정된 개수만큼 다음 이야기를 만듭니다.</div><div class="auto-process-footer"><div><strong>${run?.completed_count || 0}</strong><span>완성 콘텐츠</span></div><div><strong>${run?.cycle_number || 0}</strong><span>현재 순환</span></div><div><strong>${run?.failed_count || 0}</strong><span>실패 기록</span></div></div></section>`;
}

function automaticVideoOptions(active = isActiveRun(currentRun())) {
  const saved = state.studio?.settings?.generation?.auto_video || state.config.video || {};
  const video = active ? currentRun().settings?.video || {} : saved;
  return {
    duration: active ? video.duration ?? autoVideoState?.config?.duration ?? 30 : autoDraft.video_duration ?? video.duration ?? 20,
    resolution: active ? video.resolution ?? autoVideoState?.config?.resolution ?? "720p" : autoDraft.video_resolution ?? video.resolution ?? "480p",
  };
}

function renderAutoVideoOptions(active, mode) {
  const video = automaticVideoOptions(active);
  return `<fieldset id="auto-video-options" class="auto-video-options" ${mode === "images" ? "hidden disabled" : ""}><legend>자동 영상 설정</legend><div class="run-form-grid"><label>해상도<select name="video_resolution" id="run-video-resolution" ${active ? "disabled" : ""}>${options([["480p", "480p · 비용 절약"], ["720p", "720p · 선명하게"]], video.resolution)}</select></label><label>영상 길이 (초)<input name="video_duration" id="run-video-duration" type="number" min="20" max="30" step="1" required value="${esc(video.duration)}" ${active ? "disabled" : ""}></label></div><p class="field-help">${active ? "이번 실행에 고정된 값입니다. 변경하려면 중지 후 새로 시작해 주세요." : "20~30초 사이로 선택하세요. 선택한 값으로 이번 실행을 제작합니다. 한국어 보이스와 큰 자막을 넣습니다. 목소리·자막 일치는 게시 전 사람이 확인합니다."}</p><div class="auto-video-settings-footer"><span id="auto-video-estimate" class="field-help"></span>${active ? "" : '<button type="button" class="text-button" data-action="save-auto-video">영상 기본값 저장</button>'}</div></fieldset>`;
}

function updateAutoVideoEstimate() {
  const note = $("auto-video-estimate");
  if (!note) return;
  const duration = Number($("run-video-duration").value);
  const resolution = $("run-video-resolution").value;
  note.textContent = Number.isInteger(duration) && duration >= 20 && duration <= 30
    ? `영상 1편 약 $${(duration * (resolution === "480p" ? 0.1065 : 0.2389)).toFixed(2)} · 실제 청구액은 달라질 수 있어요.`
    : "영상 길이를 20~30초 사이로 입력해 주세요.";
}

function automaticQuantity(active = isActiveRun(currentRun())) {
  const limit = active ? currentRun().settings?.stop_after_posts : null;
  return {
    mode: active ? (limit == null ? "unlimited" : "limited") : autoDraft.quantity_mode,
    count: active ? limit ?? "10" : autoDraft.stop_after_posts,
  };
}

function quantityCaption(mode, count) {
  return mode === "limited"
    ? `완성 콘텐츠 ${count || "—"}건 목표 · 사람의 게시 승인은 별도`
    : "개수 제한 없이 계속 제작 · 중지 또는 설정된 제한에 도달하면 종료";
}

function renderAutoQuantityOptions(active) {
  const { mode, count } = automaticQuantity(active);
  return `<fieldset class="auto-quantity-options"><legend>콘텐츠 개수</legend><div class="auto-quantity-modes">${[["unlimited", "제한 없이"], ["limited", "개수 지정"]].map(([value, label]) => `<label class="auto-quantity-choice ${mode === value ? "selected" : ""}"><input type="radio" name="quantity_mode" value="${value}" ${mode === value ? "checked" : ""} ${active ? "disabled" : ""}><span>${label}</span></label>`).join("")}</div><label id="auto-quantity-field" class="auto-quantity-field" ${mode === "limited" ? "" : "hidden"}>목표 콘텐츠 수<div class="auto-quantity-input"><input id="run-count" name="stop_after_posts" type="number" min="1" max="1000" step="1" inputmode="numeric" value="${esc(count)}" required aria-describedby="auto-quantity-help" ${active || mode !== "limited" ? "disabled" : ""}><span>건</span></div></label><p id="auto-quantity-help" class="field-help">피드 등록이 끝난 콘텐츠 1개가 1건입니다. 카드 장수·영상 파일 수·실패와 재시도는 세지 않습니다. 목표 개수에 도달하면 멈춥니다. 종료 시각은 선택 사항입니다.</p>${active ? '<p class="field-help">이번 실행의 개수 설정은 고정됩니다. 변경하려면 중지 후 새로 시작해 주세요.</p>' : '<p class="field-help">1~1,000건을 지정할 수 있습니다. 생성 도구와 영상의 사용 한도는 그대로 적용됩니다.</p>'}</fieldset>`;
}

function updateAutoQuantityOptions() {
  const { mode, count } = automaticQuantity();
  if ($("auto-quantity-field")) $("auto-quantity-field").hidden = mode !== "limited";
  if ($("run-count")) $("run-count").disabled = isActiveRun(currentRun()) || mode !== "limited";
  document.querySelectorAll(".auto-quantity-choice").forEach((choice) => {
    choice.classList.toggle("selected", choice.querySelector("input").checked);
  });
  if ($("auto-start-caption")) $("auto-start-caption").textContent = quantityCaption(mode, count);
}

function renderAutoProgress(run) {
  if (!run) return "";
  const count = run.completed_count || 0,
    limit = run.settings?.stop_after_posts,
    limited = Number.isInteger(limit) && limit > 0,
    reached = limited && count >= limit;
  return `<section class="auto-count-progress ${reached ? "reached" : ""}" aria-label="콘텐츠 제작 진행"><div><span>${isActiveRun(run) ? "이번 실행" : "최근 실행"} · 피드 등록 완료</span><strong>${count}<small>${limited ? ` / ${limit}건` : "건 · 개수 제한 없음"}</small></strong></div>${limited ? `<progress max="${limit}" value="${Math.min(count, limit)}" aria-label="목표 ${limit}건 중 ${count}건 완료"></progress>` : ""}<p>${reached ? "목표 개수 달성 · 등록된 콘텐츠를 검수하고 승인해 주세요." : limited ? `목표까지 ${Math.max(0, limit - count)}건 남았습니다. ${isActiveRun(run) ? run.end_at ? "설정한 종료 시각에 먼저 도달하면 제작을 마칩니다." : "종료 시각 제한 없이 완료되는 대로 반영합니다." : "이 실행은 종료되었습니다."}` : "카드 장수와 관계없이 등록된 콘텐츠 수를 표시합니다."}</p></section>`;
}

function autoMediaNote(mode, budget = autoVideoState?.config?.daily_estimated_budget_usd) {
  if (mode === "images") return "이미지는 연결된 내장 생성 도구로 제작합니다.";
  const limit = budget != null ? `하루 예상 사용량 $${budget} 한도를 유지합니다.` : "현재 설정된 비용 한도 안에서 제작합니다.";
  return `영상은 Segmind 크레딧을 사용합니다. ${limit} ${mode === "video_only" ? "영상 제작이 어려우면 사유를 표시하고 대기합니다. 조건을 해결한 뒤 재개해 주세요." : "영상 한도에 도달하면 이미지 제작을 이어갑니다."}`;
}

function renderAutomation() {
  const a = state.automation || {},
    run = a.run,
    active = isActiveRun(run);
  const convert =
    active &&
    run.settings?.production_mode === "queued" &&
    run.persona_id === activePersona().id;
  const personas = state.studio?.personas || [activePersona()];
  const executingPersona = personas.find((p) => p.id === run?.persona_id);
  const selectedPersona = active
    ? run.persona_id
    : autoDraft.persona_id || activePersona().id;
  const mode = active
    ? run.settings?.media_mode || "images"
    : autoDraft.media_mode;
  const videoOnly = mode === "video";
  const end = active ? run.end_at : autoDraft.end_at;
  const budget = autoVideoState?.config?.daily_estimated_budget_usd;
  return `${state.contents?.length ? `<div class="production-result-notice"><span>${icon("image")}저장된 제작 결과 <strong>${state.contents.length}건</strong> · 이미지와 영상을 확인하세요.</span>${button("제작 결과 보기", "show-results", "subtle", "arrow")}</div>` : ""}<div class="auto-studio-layout"><section class="panel auto-launch-panel"><div class="section-top"><h2>AI 자동 제작</h2>${badge(run?.status || "draft", run ? labels[run.status] : "시작 전")}</div><h3 class="auto-launch-title">페르소나를 고르면,<br>AI가 다음 일상을 만듭니다.</h3><p class="auto-launch-description">제작 총괄이 단계별 전문가에게 결과를 넘기며 GS 소재 탐색부터 기획·제작·피드 등록까지 이어갑니다. 소재를 미리 수동 등록할 필요가 없어요.</p><div class="auto-source-research-note">${icon("search")}<p>GS리테일(편의점,수퍼)·GSSHOP·GS건설·GS칼텍스·파르나스 호텔의 공식 자료를 찾고, 확인한 정보만 소재로 저장합니다.</p></div><form id="run-form" class="auto-start-form"><label>콘텐츠를 만들 페르소나<select id="run-persona" name="persona_id" required ${active ? "disabled" : ""}>${options(
    personas.map((p) => [p.id, personaName(p)]),
    selectedPersona,
  )}</select></label><fieldset class="auto-media-options"><legend>AI가 제작할 미디어</legend>${videoOnly ? `<div class="auto-existing-video">${icon("play")}현재 실행: 짧은 영상 중심</div>` : ""}<label class="auto-media-choice ${mode === "mixed" ? "selected" : ""}"><input type="radio" name="media_mode" value="mixed" ${mode === "mixed" ? "checked" : ""} ${active ? "disabled" : ""}><span><strong>이미지 + 짧은 영상</strong><small>이야기에 맞는 형식을 AI가 선택합니다.</small></span>${icon("spark")}</label><label class="auto-media-choice ${mode === "images" ? "selected" : ""}"><input type="radio" name="media_mode" value="images" ${mode === "images" ? "checked" : ""} ${active ? "disabled" : ""}><span><strong>이미지 중심</strong><small>이야기에 맞춰 장수를 유동적으로 구성합니다.</small></span>${icon("image")}</label><label class="auto-media-choice ${mode === "video_only" ? "selected" : ""}"><input type="radio" name="media_mode" value="video_only" ${mode === "video_only" ? "checked" : ""} ${active ? "disabled" : ""}><span><strong>영상만</strong><small>등록된 인물 사진을 기준으로 짧은 영상만 만듭니다.</small></span>${icon("play")}</label></fieldset>${renderAutoQuantityOptions(active)}${renderAutoVideoOptions(active, mode)}<p class="auto-video-note" id="auto-video-note">${esc(autoMediaNote(mode, budget))}</p><div class="auto-guide-summary"><span>영상 참고 MD <strong>${(autoVideoState?.guides || []).filter((g) => g.enabled).length}개</strong> · <span id="auto-guide-mode">${mode === "images" ? "이미지 중심 실행에는 적용 안 함" : "낮은 관여도로 참고"}</span></span><button type="button" class="text-button" data-guide-action="show">등록·관리</button></div><details class="auto-schedule" ${autoDraft.schedule_open && !active ? "open" : ""}><summary>${icon("clock")}실행 일정 <span>선택</span>${icon("arrow")}</summary><div class="run-form-grid"><label>시작 시각<input id="run-start" name="start_at" type="datetime-local" value="${active ? inputDate(run.start_at) : esc(autoDraft.start_at)}" ${active ? "disabled" : ""}><p class="field-help">비워두면 지금 시작합니다.</p></label><label>종료 시각 (선택)<input id="run-end" name="end_at" type="datetime-local" value="${active ? inputDate(end) : esc(end)}" ${active ? "disabled" : ""}><p class="field-help">비워두면 시간 제한 없이 제작합니다. 각 단계 결과는 완료 즉시 저장됩니다.</p></label></div></details><button id="run-start-button" type="submit" class="button primary auto-start-button" ${active && !convert ? "disabled" : ""}>${icon("play")}${convert ? "AI 연속 제작으로 전환" : active ? "자동 제작 " + esc(labels[run.status]) : "콘텐츠 자동 생성 시작"}</button><div class="auto-control-actions">${run && ["scheduled", "running"].includes(run.status) ? button("일시정지", "run-pause", "", "pause") : ""}${run && ["paused", "blocked"].includes(run.status) ? button("재개", "run-resume", "subtle", "play") : ""}${active ? button("중지", "run-stop", "", "stop") : ""}</div></form><p id="auto-start-caption" class="auto-start-caption">${quantityCaption(automaticQuantity(active).mode, automaticQuantity(active).count)}</p><p class="auto-source-worker-note">시작하면 로컬 AI 작업자가 바로 실행되어 공식 자료 탐색부터 진행합니다.</p>${active ? `<div class="auto-run-context"><span>${esc(executingPersona ? personaName(executingPersona) : run.persona_id)}</span><span>${date(run.start_at)} 시작 · ${run.end_at ? date(run.end_at) + " 종료" : "종료 시각 제한 없음"}</span></div>` : ""}${run?.pause_reason ? `<p class="warning-note">${esc(run.pause_reason)}</p>` : ""}</section>${renderSpecialistTeam()}</div>${productionGuides.render()}<section class="panel auto-evidence-panel"><div class="auto-evidence-header"><div><h2>제작 과정과 기록</h2><p>단계별 담당 전문가, 인계 요약과 실제 제작 결과를 확인하세요.</p></div>${button("기록 새로고침", "refresh-artifacts", "", "refresh")}</div><div class="auto-evidence-tabs tabs"><button type="button" class="tab ${autoEvidenceTab === "stages" ? "active" : ""}" data-action="auto-evidence-tab" data-tab="stages">단계별 결과</button><button type="button" class="tab ${autoEvidenceTab === "files" ? "active" : ""}" data-action="auto-evidence-tab" data-tab="files">실행 로그 · 파일</button></div>${autoEvidenceTab === "files" ? renderArtifactFiles() : renderStageEvidence()}</section><div class="auto-human-gate">${icon("review")}<div><strong>제작 결과는 사람이 검수하고 최종 승인합니다.</strong><p>수정하거나 반려할 수 있으며, 검수 대기 중에도 다음 콘텐츠 제작은 계속됩니다.</p></div><button class="text-button" data-nav="review">검수 & 승인 ${icon("arrow")}</button></div>`;
}
const autoStageLabels = {
  sources: "GS 소재 웹 탐색·등록",
  planning: "새로운 일상 주제 선정",
  storyboard: "스토리보드 구성",
  copy: "문안·해시태그 작성",
  images: "이미지·선택 영상 제작",
  quality: "AI 품질 검수",
  register: "피드 등록",
};
const autoStageDescriptions = {
  sources:
    `GS ${affiliateNames.length}개 수집 대상의 공식 자료를 찾아 출처·확인일·유효기간과 함께 저장합니다.`,
  planning: "페르소나의 취향과 최근 피드를 바탕으로 고릅니다.",
  storyboard: "이야기에 필요한 장면과 카드 수를 정합니다.",
  copy: "페르소나의 말투로 일상을 표현합니다.",
  images: "외형의 일관성을 유지하며 장면을 제작합니다.",
  quality: "정보·외형·표현을 확인하고 필요한 수정을 진행합니다.",
  register: "완성된 콘텐츠를 사람의 검수 대기에 저장합니다.",
};
function latestStageTrace(stage) {
  const run = currentRun();
  const traces =
    autoArtifacts && run && autoArtifacts.run_id === run.id
      ? autoArtifacts.stages || []
      : [];
  const latestCycle = traces.reduce(
    (last, t) => Math.max(last, t.cycle_number || 0),
    0,
  );
  return traces.find(
    (t) => t.stage === stage && t.cycle_number === latestCycle,
  );
}
function traceURL(runId, cycleId, stage) {
  return `/api/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(cycleId)}/${encodeURIComponent(stage)}`;
}
function renderStageEvidence() {
  const run = currentRun(),
    traces =
      autoArtifacts && run && autoArtifacts.run_id === run.id
        ? autoArtifacts.stages || []
        : [];
  if (!traces.length)
    return `<div class="auto-evidence-empty">${icon("logs")}<h3>${autoArtifactsError ? "제작 기록을 불러오지 못했습니다" : "현재 실행에 저장된 단계 결과가 없어요"}</h3><p>${esc(autoArtifactsError || "AI 작업자가 단계를 수행하면 실제 결과가 이곳에 쌓입니다. 이미 등록된 콘텐츠는 ‘제작 결과’에서 볼 수 있어요.")}</p>${state.contents?.length ? button("제작 결과 보기", "show-results", "subtle", "image") : ""}</div>`;
  const staleNotice = autoArtifactsError
    ? `<p class="auto-artifact-error" role="status">${esc(autoArtifactsError)} 현재 표시된 단계 기록은 마지막으로 불러온 정보입니다.</p>`
    : "";
  const order = Object.keys(autoStageLabels),
    sorted = [...traces].sort(
      (a, b) =>
        (b.cycle_number || 0) - (a.cycle_number || 0) ||
        order.indexOf(a.stage) - order.indexOf(b.stage),
    );
  const groups = new Map();
  sorted.slice(0, autoStageLimit).forEach((trace) => {
    if (!groups.has(trace.cycle_id)) groups.set(trace.cycle_id, []);
    groups.get(trace.cycle_id).push(trace);
  });
  return `${staleNotice}<div class="stage-records">${[...groups.entries()].map(([cycle, items]) => `<section class="stage-cycle-group"><div class="stage-cycle-heading"><h3>제작 순환 ${items[0].cycle_number || ""}</h3><span>${items.length}개 단계 기록</span></div>${items.map((t) => `<button type="button" class="stage-record" data-action="open-stage" data-cycle="${esc(cycle)}" data-stage="${esc(t.stage)}"><span class="stage-record-icon">${String(order.indexOf(t.stage) + 1).padStart(2, "0")}</span><div><strong>${esc(autoStageLabels[t.stage] || t.stage)}</strong><span>${date(t.updated_at)}</span>${t.summary ? `<p>${esc(t.summary)}</p>` : ""}</div>${badge(t.status || "pending")}<span class="stage-record-size">결과 보기</span>${icon("arrow")}</button>`).join("")}</section>`).join("")}</div>${traces.length > autoStageLimit ? `<div class="auto-more-records">${button(`이전 단계 ${Math.min(14, traces.length - autoStageLimit)}건 더 보기`, "more-stage-records", "", "logs")}</div>` : ""}`;
}

function formatBytes(bytes) {
  if (bytes == null) return "—";
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}
function renderArtifactFiles() {
  const run = currentRun();
  if (!run)
    return `<div class="auto-evidence-empty">${icon("sources")}<h3>실행하면 기록 파일이 만들어져요</h3><p>실행 로그와 단계별 JSON 결과를 확인하고 내려받을 수 있습니다.</p></div>`;
  const artifacts = autoArtifacts?.run_id === run.id ? autoArtifacts : null;
  const logs = [...allLogs.values()]
    .filter((l) => l.run_id === run.id)
    .sort((a, b) => b.id - a.id)
    .slice(0, 12);
  return `<div class="auto-file-tools"><div><strong>실행 로그 파일</strong><p>${esc(artifacts?.root || "실행별 기록 파일을 확인하고 있습니다.")}</p></div><div class="auto-downloads">${["log", "jsonl"].map((format) => `<a class="button small" href="/api/runs/${encodeURIComponent(run.id)}/logs?format=${format}" download>${icon("download")}${format.toUpperCase()} 받기</a>`).join("")}</div></div>${autoArtifactsError ? `<p class="auto-artifact-error">${esc(autoArtifactsError)}</p>` : ""}${artifacts?.events?.length ? `<div class="auto-event-files">${artifacts.events.map((f) => `<a href="${safeURL(f.url || `/api/runs/${encodeURIComponent(run.id)}/logs?format=${f.format}`)}" download><span>${icon("logs")}${esc(f.path)}</span><small>${formatBytes(f.bytes)} ${icon("download")}</small></a>`).join("")}</div>` : ""}${logs.length ? logTable(logs) : '<p class="auto-no-logs">현재 실행에 저장된 로그가 없습니다.</p>'}`;
}
async function loadAutoEvidence() {
  const run = currentRun();
  if (autoEvidenceBusy) return;
  autoEvidenceBusy = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), globalThis.BOCA_REMOTE ? 30000 : 8000);
  try {
    const requests = [fetch("/api/video", { cache: "no-store", signal: controller.signal })];
    if (run)
      requests.push(
        fetch(`/api/runs/${encodeURIComponent(run.id)}/artifacts`, {
          cache: "no-store",
          signal: controller.signal,
        }),
      );
    const results = await Promise.allSettled(requests);
    const video = results[0];
    if (video.status === "fulfilled" && video.value.ok)
      autoVideoState = await video.value.json();
    if (run) {
      const item = results[1];
      if (item.status === "fulfilled" && item.value.ok) {
        autoArtifacts = await item.value.json();
        autoArtifactsError = "";
      } else
        autoArtifactsError =
          "저장된 기록 파일을 확인할 수 없습니다. 잠시 후 다시 불러와 주세요.";
    } else {
      autoArtifacts = null;
      autoArtifactsError = "";
    }
  } catch (error) {
    autoArtifactsError = error.message;
  } finally {
    clearTimeout(timeout);
    autoEvidenceBusy = false;
  }
}
const resultFieldNames = {
  poll_errors: "연속 통신 오류 횟수",
  next_retry_at: "다음 자동 복구 시각",
  sync_errors: "단계 반영 오류 횟수",
  video_guides: "영상 제작 참고 MD",
  video_guide_policy: "MD 참고 방식",
  label: "확인 항목",
  title: "이야기 제목",
  topic_key: "주제 구분",
  topic: "선정한 주제",
  theme: "이야기 주제",
  angle: "이야기 방향",
  hook: "도입",
  rationale: "선정 이유",
  reason: "이유",
  reason_summary: "판단 요약",
  decision_summary: "판단 요약",
  summary: "요약",
  notes: "검토 메모",
  note: "메모",
  review_notes: "검토 메모",
  source_ids: "연결한 소재 ID",
  sources: "참고 자료",
  source_id: "소재 ID",
  claims: "사용할 정보",
  name: "이름",
  affiliate: "계열사",
  url: "출처",
  checked_at: "확인 시각",
  verified_at: "확인 시각",
  expires_at: "유효기간",
  visibility: "공개 범위",
  status: "상태",
  cards: "장면 구성",
  scene: "장면",
  description: "내용",
  visual: "화면 구성",
  image_prompt: "이미지 제작 지시",
  video_prompt: "영상 제작 지시",
  prompt: "제작 지시",
  narration: "내레이션",
  text: "표시 문안",
  overlay_text: "화면 문안",
  caption: "게시 문안",
  hashtags: "해시태그",
  alt: "미디어 설명",
  duration: "길이",
  duration_seconds: "길이(초)",
  shot: "촬영 구도",
  camera: "카메라",
  mood: "분위기",
  media: "저장된 미디어",
  media_mode: "미디어 형식",
  format: "콘텐츠 형식",
  content_id: "콘텐츠 ID",
  version: "등록 버전",
  passed: "검수 통과",
  checks: "확인 항목",
  label: "항목",
  issues: "발견한 문제",
  warnings: "확인 필요",
  fixes: "수정 내용",
  persona_consistency: "페르소나 일관성",
  source_accuracy: "정보 정확성",
  disclosure: "가상 인물 표시",
  no_fabricated_experience: "실제 경험을 지어내지 않음",
  approved: "확인 완료",
  result: "결과",
  output: "결과",
  external_job_id: "외부 생성 작업 ID",
  external_job_ids: "외부 생성 작업 ID",
  provider: "생성 도구",
  model: "모델",
  fallback: "대체 제작 방식",
  skipped: "건너뜀",
  registered_at: "등록 시각",
  attempt: "시도",
  attempts: "시도 횟수",
  brief: "기획 메모",
  persona_id: "페르소나 ID",
  persona_version: "페르소나 버전",
  cycle_id: "제작 순환 ID",
  run_id: "실행 ID",
  previous_results: "이전 단계에서 전달한 결과",
  objective: "목적",
  target: "대상",
  setting: "배경",
  order: "순서",
  index: "순서",
  card_number: "장면 번호",
  daughter_appears: "딸 등장",
  product_connection: "소재 연결",
  brand_connection: "브랜드 연결",
  source_snapshot: "제작 당시 소재",
  selected_sources: "선택한 소재",
  added_count: "신규 등록",
  skipped_count: "건너뜀",
  skipped: "건너뛴 자료",
  research_id: "탐색 기록 ID",
  web_verified: "AI 작업자가 웹에서 확인",
  verified_by: "확인한 주체",
  material_type: "자료 유형",
  validity_note: "유효기간 판단 근거",
  source_version: "소재 버전",
  specialist: "전문 역할 설정",
  specialist_assignment: "실제 전문가 배정 기록",
  role_id: "역할 ID",
  role_name: "담당 역할",
  agent_id: "에이전트 ID",
  assignment_id: "배정 기록 ID",
  result_summary: "인계 요약",
  result_artifact: "저장된 결과",
  expertise: "담당 전문 영역",
  instructions: "작업 지침",
  output_contract: "저장할 결과",
  recorded_by: "기록 주체",
  runtime_verified: "서버의 실행 환경 확인",
  queries: "검색 질의",
  query: "검색 질의",
  registered_count: "새로 등록한 소재",
  reused_count: "재사용한 소재",
  rejected_count: "제외한 후보",
  failed_count: "탐색 실패",
  registered_source_ids: "신규 등록 소재 ID",
  reused_source_ids: "재사용 소재 ID",
  rejected: "제외한 후보",
  failures: "탐색 실패",
  evidence: "확인 근거",
  evidence_excerpt: "출처에서 확인한 내용",
  provenance: "수집 이력",
  origin: "등록 방식",
  collected_at: "수집 시각",
  collection_run_id: "수집 실행 ID",
  searched_at: "탐색 시각",
  search_queries: "검색 질의",
  official_domain: "공식 도메인",
  research_receipt: "소재 수집 기록",
  source_research: "공식 자료 탐색 기록",
  duplicate_check: "최근 주제 중복 확인",
};
function readableValue(value, depth = 0) {
  if (value == null || value === "")
    return '<span class="muted">저장된 내용 없음</span>';
  if (typeof value === "boolean")
    return `<span class="result-boolean ${value ? "yes" : "no"}">${value ? "예" : "아니요"}</span>`;
  if (Array.isArray(value))
    return value.length
      ? `<ul class="stage-readable-list">${value.map((item) => `<li>${readableValue(item, depth + 1)}</li>`).join("")}</ul>`
      : '<span class="muted">없음</span>';
  if (typeof value === "object")
    return `<dl class="stage-readable-fields">${Object.entries(value)
      .map(
        ([key, entry]) =>
          `<div><dt>${esc(resultFieldNames[key] || key.replaceAll("_", " "))}</dt><dd>${key === "url" && typeof entry === "string" ? `<a href="${safeURL(entry)}" target="_blank" rel="noopener noreferrer">${esc(entry)}</a>` : readableValue(entry, depth + 1)}</dd></div>`,
      )
      .join("")}</dl>`;
  return `<p class="stage-readable-text">${esc(typeof value === "string" ? labels[value] || value : String(value))}</p>`;
}
function renderHashtags(value) {
  const tags = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.split(/\s+/).filter(Boolean)
      : [];
  return tags.length
    ? `<div class="result-hashtags">${tags.map((tag) => `<span>${esc(tag)}</span>`).join("")}</div>`
    : "";
}
function remainingResultFields(result, keys) {
  if (!result || typeof result !== "object" || Array.isArray(result)) return "";
  const remaining = Object.fromEntries(
    Object.entries(result).filter(([key]) => !keys.includes(key)),
  );
  return Object.keys(remaining).length ? readableValue(remaining) : "";
}
function stageMediaPreviews(previews) {
  if (!Array.isArray(previews) || !previews.length) return "";
  return `<div class="stage-media-previews">${previews
    .map((item, index) => {
      let url = null;
      try {
        const candidate = new URL(item.url, location.origin);
        if (
          item.url &&
          candidate.origin === location.origin &&
          candidate.pathname.startsWith("/api/runs/")
        )
          url = candidate.href;
      } catch {}
      const available = item.available && url;
      const alt = item.alt || item.name || `${index + 1}번째 미디어`;
      return `<figure class="stage-media-preview"><div class="stage-media-frame">${!available ? `<div class="stage-media-unavailable">${icon(item.kind === "video" ? "play" : "image")}<strong>미디어 파일을 사용할 수 없어요</strong><p>저장 경로는 기록되어 있지만 현재 파일을 불러올 수 없습니다.</p></div>` : item.kind === "video" ? `<video controls playsinline preload="metadata" src="${esc(url)}" aria-label="${esc(alt)}"></video>` : `<a class="media-original-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(alt)} · 원본 이미지 새 창으로 보기"><img src="${esc(url)}" alt="${esc(alt)}" loading="lazy"><span class="media-original-hint">원본 보기 ${icon("arrow")}</span></a>`}</div><figcaption><strong>${index + 1}. ${esc(alt)}</strong><span>${esc(item.name || "")}${item.origin === "checkpoint" ? " · 중간 저장 결과" : item.origin === "registered" ? " · 등록 당시 버전" : ""}</span>${available ? `<a href="${esc(url)}" download="${esc(item.name || "media")}" class="text-button">${icon("download")}파일 받기</a>` : ""}</figcaption></figure>`;
    })
    .join("")}</div>`;
}
function stageOutputView(stage, output, data) {
  if (output == null)
    return '<p class="stage-data-empty">아직 최종 결과가 저장되지 않았습니다. 중간 저장 파일이 있다면 아래에서 확인할 수 있어요.</p>';
  if (typeof output !== "object" || Array.isArray(output))
    return readableValue(output);
  output = Object.fromEntries(
    Object.entries(output).filter(
      ([key]) => !["decision_summary", "specialist_assignment", "specialist_assignment_id"].includes(key),
    ),
  );
  if (stage === "storyboard") {
    const cards = Array.isArray(output.cards) ? output.cards : [];
    return `${cards.length ? `<div class="storyboard-scenes">${cards.map((card, i) => `<article class="storyboard-scene"><div class="storyboard-scene-heading"><span>${String(i + 1).padStart(2, "0")}</span><h4>${esc(card && typeof card === "object" ? card.title || card.scene || `장면 ${i + 1}` : `장면 ${i + 1}`)}</h4></div>${card && typeof card === "object" ? remainingResultFields(card, [card.title ? "title" : "scene"]) : readableValue(card)}</article>`).join("")}</div>` : ""}${remainingResultFields(output, ["cards"])}`;
  }
  if (stage === "copy")
    return `${output.caption ? `<div class="stage-caption-paper">${esc(output.caption)}</div>` : ""}${renderHashtags(output.hashtags)}${remainingResultFields(output, ["caption", "hashtags"])}`;
  if (stage === "quality")
    return `${typeof output.passed === "boolean" ? `<div class="stage-quality-verdict ${output.passed ? "passed" : "needs-review"}">${icon(output.passed ? "check" : "info")}<div><strong>${output.passed ? "AI 품질 검수 통과" : "수정이 필요한 결과입니다"}</strong><p>사람의 최종 승인과 별도로 저장된 AI 검수 결과입니다.</p></div></div>` : ""}${remainingResultFields(output, ["passed"])}`;
  if (stage === "register") {
    const registered = data.registered_content?.payload;
    const copy = registered || data.input?.previous_results?.copy;
    const content = state.contents.find((c) => c.id === output.content_id);
    return `${readableValue(output)}${copy?.caption ? `<h4 class="stage-subheading">${registered ? "등록 당시 게시 문안" : "문안 단계에서 작성한 내용"}</h4><div class="stage-caption-paper">${esc(copy.caption)}</div>${renderHashtags(copy.hashtags)}` : ""}${content ? `<div class="stage-register-action">${button("현재 버전 검수하기", "stage-open-content", "subtle", "review", `data-id="${esc(content.id)}"`)}<p>현재 v${content.current_version} · 이 기록은 등록 당시 v${esc(output.version || "—")}입니다.</p></div>` : ""}`;
  }
  if (stage === "sources")
    return `${renderSourceResearchReceipt(output.source_research, { stage: true })}${data.source_snapshot && !output.source_research?.materials?.length ? `<h4 class="stage-subheading">제작 당시 확인한 소재</h4>${renderSourceEvidenceCards(data.source_snapshot)}` : ""}${remainingResultFields(output, ["source_research"])}`;
  return readableValue(output);
}
function stageInputView(input) {
  if (!input || typeof input !== "object") return readableValue(input);
  const previous = input.previous_results || {},
    brief = input.brief;
  const metadata = Object.fromEntries(
    Object.entries(input).filter(
      ([key]) => !["previous_results", "brief"].includes(key),
    ),
  );
  return `${brief ? `<h4 class="stage-subheading">입력된 기획</h4>${readableValue(brief)}` : ""}${readableValue(metadata)}${
    Object.keys(previous).length
      ? `<h4 class="stage-subheading">이전 단계에서 전달한 결과</h4>${Object.entries(
          previous,
        )
          .map(
            ([name, result]) =>
              `<details class="stage-input-result"><summary>${esc(autoStageLabels[name] || name)}</summary>${readableValue(result)}</details>`,
          )
          .join("")}`
      : ""
  }`;
}

function stageActivityView(data) {
  const events = (data.events || []).filter((event) =>
    event.message && !/heartbeat/.test(event.event || ""),
  ).slice().sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 6);
  const current = state.automation?.specialists?.current;
  const live = data.run_id === currentRun()?.id && data.cycle_id === current?.cycle_id && data.stage === current?.stage;
  const heartbeat = live ? state.automation?.worker_last_seen_at : null;
  const clockTime = (value) => value ? new Date(value).toLocaleTimeString("ko-KR", { hour12: false }) : "—";
  return `<section class="stage-activity"><div class="stage-activity-heading"><h3>최근 작업 기록</h3><span>5초마다 자동 확인</span></div>${events.length ? `<ol>${events.map((event) => `<li><time datetime="${esc(event.created_at)}">${clockTime(event.created_at)}</time><div><p>${esc(event.message)}</p><small>${esc(event.event)}</small></div></li>`).join("")}</ol>` : '<p class="field-help">아직 저장된 작업 로그가 없습니다. 첫 기록을 기다리고 있습니다.</p>'}${heartbeat ? `<p class="field-help">제작 총괄 연결 확인 ${clockTime(heartbeat)} · 연결 신호와 작업 완료 기록은 별도입니다.</p>` : ""}</section>`;
}
function stageResultBody(data, stage) {
  const input = data.input ?? data.job?.input ?? data.input_json;
  const output = data.output ?? data.result ?? data.job?.result ?? data.result_json;
  const summary = data.decision_summary ?? data.summary ?? data.reason_summary ??
    output?.decision_summary ?? output?.summary ?? output?.review_notes;
  return `<section class="stage-result-section"><h3>${{ sources: "웹 탐색·등록 결과", planning: "선정한 일상 이야기", storyboard: "장면별 스토리보드", copy: "작성한 문안과 해시태그", images: "제작한 이미지·영상", quality: "품질 검수 결과", register: "피드 등록 결과" }[stage] || "단계 결과"}</h3>${stage === "images" ? stageMediaPreviews(data.previews) : ""}${stageOutputView(stage, output, data)}${stage !== "images" ? stageMediaPreviews(data.previews) : ""}</section>${summary ? `<section class="stage-decision-summary"><h3>판단 요약</h3>${readableValue(summary)}</section>` : ""}<details class="stage-input-details"><summary>이 단계에 전달된 입력 보기</summary>${stageInputView(input)}</details>${data.external_job_id || data.job?.external_job_id ? `<p class="field-help stage-external-id">외부 작업 ID: ${esc(data.external_job_id || data.job.external_job_id)}</p>` : ""}`;
}
function patchStageDialogSection(node, html) {
  if (node._stageHTML === html) return;
  const expanded = [...node.querySelectorAll("details")].map((detail) => detail.open);
  node.innerHTML = html;
  node.querySelectorAll("details").forEach((detail, index) => {
    if (expanded[index] !== undefined) detail.open = expanded[index];
  });
  node._stageHTML = html;
}
function stopStageDialog() {
  if (!stageDialogSession) return;
  clearTimeout(stageDialogSession.timer);
  stageDialogSession.controller?.abort();
  stageDialogSession = null;
}
async function refreshStageDialog(session) {
  if (stageDialogSession !== session || !$("studio-dialog").open || session.busy) return;
  clearTimeout(session.timer);
  session.busy = true;
  const controller = new AbortController();
  session.controller = controller;
  const timeout = setTimeout(() => controller.abort(), globalThis.BOCA_REMOTE ? 30000 : 8000);
  try {
    const response = await fetch(session.url, { cache: "no-store", signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || "단계 결과를 불러오지 못했습니다.");
    if (stageDialogSession !== session || !$("studio-dialog").open) return;
    const dialog = $("studio-dialog");
    const scrollArea = dialog.querySelector(".dialog-body") || dialog;
    const scrollTop = scrollArea.scrollTop;
    $("dialog-content").querySelector(".dialog-header p").textContent =
      `${labels[data.status] || data.status || "저장됨"} · 결과 갱신 ${date(data.updated_at)}`;
    patchStageDialogSection($("stage-dialog-live"), `<div class="stage-result-status">${badge(data.status || "pending")}<span>시도 ${data.attempts || 0} / ${data.max_attempts || "—"}</span></div>${data.error ? `<div class="inline-warning">${icon("info")}${esc(data.error)}</div>` : ""}${renderStageSpecialist(data, session.stage)}${stageActivityView(data)}`);
    // Keep a playing media element intact while status and logs continue updating.
    const result = $("stage-dialog-result");
    const playing = [...result.querySelectorAll("video")].some((video) => !video.paused && !video.ended);
    if (!playing) patchStageDialogSection(result, stageResultBody(data, session.stage));
    const json = $("stage-dialog-json");
    const raw = JSON.stringify(data, null, 2);
    if (json.textContent !== raw) json.textContent = raw;
    session.loaded = true;
    $("stage-dialog-sync").textContent = `자동 갱신 중 · 마지막 확인 ${new Date().toLocaleTimeString("ko-KR", { hour12: false })}${playing ? " · 영상 재생 유지 중" : ""}`;
    $("stage-dialog-sync").classList.remove("stage-sync-error");
    scrollArea.scrollTop = scrollTop;
  } catch (error) {
    if (stageDialogSession !== session || !$("studio-dialog").open) return;
    $("stage-dialog-sync").textContent = `${error.name === "AbortError" ? "응답 시간이 초과됐습니다." : error.message} ${session.loaded ? "마지막으로 확인한 결과를 표시합니다." : "단계 기록을 아직 불러오지 못했습니다."} 5초 후 다시 확인합니다.`;
    $("stage-dialog-sync").classList.add("stage-sync-error");
  } finally {
    clearTimeout(timeout);
    session.busy = false;
    if (stageDialogSession === session && $("studio-dialog").open)
      session.timer = setTimeout(() => refreshStageDialog(session), 5000);
  }
}
async function stageDialog(cycle, stage) {
  const run = currentRun();
  if (!run) return;
  const url = traceURL(run.id, cycle, stage);
  if (stageDialogSession?.url === url && $("studio-dialog").open)
    return refreshStageDialog(stageDialogSession);
  openDialog(
    autoStageLabels[stage] || stage,
    "실제 저장된 단계 결과를 확인합니다.",
    `<div class="dialog-body stage-inspector"><p id="stage-dialog-sync" class="stage-dialog-sync" role="status">단계 결과를 불러오고 있습니다.</p><div id="stage-dialog-live"></div><div id="stage-dialog-result"></div><details class="stage-raw-json"><summary>저장된 JSON 전체 보기</summary><pre id="stage-dialog-json"></pre></details></div>`,
    `<div class="dialog-footer stage-result-footer"><p>모든 단계의 결과와 로그를 5초마다 확인합니다.</p><div class="button-group">${button("지금 확인", "open-stage", "", "refresh", `data-cycle="${esc(cycle)}" data-stage="${esc(stage)}"`)}<a class="button" href="${url}" download>${icon("download")}JSON 받기</a><button class="button primary" type="button" data-action="close-dialog">닫기</button></div></div>`,
  );
  const session = { url, stage, timer: null, controller: null, busy: false, loaded: false };
  stageDialogSession = session;
  return refreshStageDialog(session);
}

function renderReview() {
  const contents = state.contents || [],
    rows = contents.filter(
      (c) => reviewFilter === "all" || c.status === reviewFilter,
    );
  if (!selectedId && rows.length) selectedId = rows[0].id;
  const current = rows.find((c) => c.id === selectedId);
  return `${heading("검수 & 승인", "전체 페르소나의 콘텐츠를 확인하고, 게시할 정확한 버전을 승인하세요.")}<div class="page-toolbar"><div class="tabs">${[
    ["ready", "검수 대기"],
    ["approved", "승인 완료"],
    ["rejected", "반려"],
    ["all", "전체"],
  ]
    .map(
      ([v, t]) =>
        `<button class="tab ${reviewFilter === v ? "active" : ""}" data-action="review-filter" data-value="${v}">${t}<span class="tab-count">${contents.filter((c) => v === "all" || c.status === v).length}</span></button>`,
    )
    .join(
      "",
    )}</div><span class="version-lock">${icon("lock")}수정 후에는 다시 승인해야 합니다.</span></div>${!contents.length ? `<section class="panel">${empty("아직 검수할 콘텐츠가 없어요", "제작이 끝난 콘텐츠가 이곳에 모입니다. 완성된 이미지와 문안을 확인한 뒤 게시할 버전을 승인하세요.", "go-create", "콘텐츠 제작하기", "full-empty")}</section>` : `<div class="review-layout"><div class="review-list" id="review-list">${rows.length ? rows.map((c) => `<button class="review-item ${c.id === selectedId ? "active" : ""}" data-action="select-content" data-id="${esc(c.id)}"><div class="review-item-image">${media(c.payload.cards?.[0])}</div><div><h3>${esc(c.payload.title)}</h3>${badge(c.status)}<small>${esc(personaName((state.studio?.personas || []).find((p) => p.id === contentPersona(c)) || activePersona()))} · v${c.current_version} · ${c.payload.cards?.length || 0}장</small></div></button>`).join("") : '<p class="review-empty-list">이 상태에 해당하는<br>콘텐츠가 없습니다.</p>'}</div>${current ? renderEditor(current) : `<section class="panel">${empty("콘텐츠를 선택해 주세요", "왼쪽 목록에서 검토할 이야기를 선택하면 이미지와 문안을 함께 볼 수 있어요.", "", "", "full-empty")}</section>`}</div>`}`;
}
function renderEditor(current) {
  const p = current.payload,
    frozen = ["posting", "published", "uncertain"].includes(current.status);
  editingVersion = current.current_version;
  selectedCard = Math.min(
    Math.max(0, selectedCard),
    Math.max(0, (p.cards?.length || 1) - 1),
  );
  return `<form id="editor" class="review-editor"><div class="editor-top"><span id="version">버전 ${editingVersion} <span class="muted">/ ${p.cards?.length || 0}장</span></span><div class="editor-top-actions">${badge(current.status)}<a class="text-button" href="/api/contents/${encodeURIComponent(current.id)}/export">${icon("download")}콘텐츠 다운로드</a></div></div><div class="editor-body"><div class="review-media"><div class="review-hero" id="hero">${media(p.cards?.[selectedCard], { interactive: true })}</div><div id="filmstrip" class="filmstrip">${(p.cards || []).map((c, i) => `<button type="button" class="${i === selectedCard ? "selected" : ""}" data-action="select-card" data-index="${i}" aria-label="${i + 1}번째 카드 보기">${media(c)}</button>`).join("")}</div><p class="scene-caption" id="scene">${selectedCard + 1} / ${p.cards?.length || 0} · ${esc(p.cards?.[selectedCard]?.alt || "이미지 설명 없음")}</p></div><div class="editor-fields"><label>이야기 제목<input id="title" name="title" maxlength="200" required value="${esc(p.title)}" ${frozen ? "disabled" : ""}></label><label>게시 문안<textarea id="caption" name="caption" rows="9" required ${frozen ? "disabled" : ""}>${esc(p.caption)}</textarea></label><label>해시태그<input id="hashtags" name="hashtags" value="${esc((p.hashtags || []).join(" "))}" placeholder="#일상 #집꾸미기" ${frozen ? "disabled" : ""}></label><details class="source-details"><summary>소재 출처와 검토 메모</summary>${(p.sources || []).map((s) => `<p><a href="${safeURL(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name || s.url)}</a><br>확인 ${date(s.checked_at)}</p>`).join("") || "<p>연결된 상품 출처가 없습니다. 상품 관련 주장이 있다면 승인 전에 확인해 주세요.</p>"}${(p.review_notes || []).map((n) => `<p>${esc(n)}</p>`).join("")}</details></div></div><div class="editor-bottom"><p id="revision-note">${current.proposals ? `늦게 도착한 AI 제안 ${current.proposals}건을 별도 보관했습니다. 현재 수정본은 유지됩니다.` : "수정한 내용을 저장하면 새 버전이 됩니다. 검토한 버전의 이미지와 문안만 승인됩니다."}</p><div class="editor-buttons"><button type="submit" id="save" class="button" ${frozen ? "disabled" : ""}>수정 저장</button><button type="button" id="reject" class="button" data-action="reject" ${frozen ? "disabled" : ""}>반려</button><button type="button" id="approve" class="button primary" data-action="approve" ${frozen || current.status === "approved" ? "disabled" : ""}>버전 ${editingVersion} 승인</button></div></div><p id="publish-note" class="publish-note">${current.publication?.status === "blocked" ? `게시 전 확인 필요: ${esc(current.publication.detail || "출처와 미디어를 다시 확인해 주세요.")}` : current.publication?.permalink ? `<a href="${safeURL(current.publication.permalink)}" target="_blank" rel="noopener noreferrer">Instagram 게시물 보기</a>` : state.config.instagram?.connection === "verified" && state.config.instagram?.publisher_ready !== false ? "승인한 버전만 게시 작업에 전달합니다." : "승인하면 게시 대기로 보관합니다. 실제 게시는 Instagram 계정 연결 후 진행됩니다."}</p></form>`;
}
function renderFeed() {
  const persona = activePersona(),
    p = profile(persona),
    all = personaContents(persona.id),
    rows = all.filter((c) => feedFilter === "all" || c.status === feedFilter),
    handle =
      p.instagram_handle ||
      state.studio?.settings?.instagram?.account ||
      state.config.instagram?.account;
  return `${heading("피드 미리보기", "계정의 분위기, 표지와 주제의 균형을 한눈에 확인하세요.", button("프로필 편집", "edit-persona", "", "edit", `data-id="${esc(persona.id)}"`))}<div class="feed-layout"><section class="instagram-preview"><div class="instagram-top"><span>${esc(handle || "프로필 미리보기")}</span>${icon("more")}</div><div class="instagram-profile"><div class="instagram-profile-head">${avatar(persona)}<div class="instagram-stats"><div><strong>${rows.length}</strong><span>콘텐츠</span></div><div><strong>52만</strong><span>팔로워</span></div><div><strong>25</strong><span>팔로잉</span></div></div></div><p class="instagram-bio"><strong>${esc(personaName(persona))}</strong>${esc(personaBio(persona) || array(p.interests).join(" · "))}<br>${esc(p.content?.disclosure || disclosure)}</p><div class="instagram-buttons"><span>프로필 초안</span><span>게시 전 미리보기</span></div></div><div class="instagram-tab">${icon("feed")}</div><div class="instagram-grid">${rows.length ? rows.map(renderFeedCell).join("") : Array.from({ length: 9 }, (_, i) => `<div class="instagram-cell ghost" aria-hidden="true">${i === 4 ? icon("plus") : icon("image")}</div>`).join("")}</div><p class="instagram-caption">${rows.length ? "실제 Instagram 화면과 일부 차이가 있을 수 있습니다. 콘텐츠를 선택하면 검수 화면으로 이동합니다." : "아직 피드가 없습니다. 이야기가 완성되면 이 공간에 실제 표지가 채워집니다."}</p></section><aside class="feed-sidebar"><section class="panel feed-note"><h2>이 계정의 콘텐츠</h2><div class="balance-item"><span>전체 콘텐츠</span><strong>${all.length}건</strong></div><div class="balance-item"><span>검수 대기</span><strong>${all.filter((c) => c.status === "ready").length}건</strong></div><div class="balance-item"><span>승인 완료</span><strong>${all.filter((c) => c.status === "approved").length}건</strong></div><div class="balance-item"><span>게시 완료</span><strong>${all.filter((c) => c.status === "published").length}건</strong></div><label class="feed-filter">미리보기 범위<select id="feed-filter">${options(
    [
      ["all", "모든 콘텐츠"],
      ["ready", "검수 대기만"],
      ["approved", "승인 완료만"],
      ["published", "게시 완료만"],
    ],
    feedFilter,
  )}</select></label></section><section class="panel feed-note"><h2>계정의 일관성 확인하기</h2><p>표지의 색감이 한 계정처럼 이어지는지, 최근 이야기와 주제가 반복되지 않는지 살펴보세요.</p><div class="persona-tags">${array(
    p.interests,
  )
    .map((i) => `<span class="tag">${esc(i)}</span>`)
    .join(
      "",
    )}</div><hr class="section-divider"><p>팔로워 52만 명·팔로잉 25명은 미리보기용 예시입니다. 이 화면은 저장된 페르소나의 프로필 초안이며, 실제 계정은 아직 연결되지 않았습니다.</p><button class="text-button space-top" data-nav="settings">계정 연결 상태 확인 ${icon("arrow")}</button></section></aside></div>`;
}
function sourceOrigin(source) {
  return source.origin === "web_research" ? "automatic" : "manual";
}
function renderSourceOrigin(source) {
  const automatic = sourceOrigin(source) === "automatic";
  return `<span class="source-origin ${automatic ? "automatic" : ""}">${automatic ? "AI 웹 탐색" : "수동·기존 등록"}</span>`;
}
function renderSourceEvidenceCards(sources, { researched = false } = {}) {
  if (!Array.isArray(sources)) return readableValue(sources);
  if (!sources.length)
    return '<p class="stage-data-empty">이번 기록에 연결된 소재가 없습니다.</p>';
  return `<div class="source-evidence-cards">${sources
    .map((source) => {
      if (!source || typeof source !== "object")
        return `<article class="source-evidence-card">${readableValue(source)}</article>`;
      return `<article class="source-evidence-card">${researched ? '<span class="source-origin automatic">AI 웹 탐색</span>' : renderSourceOrigin(source)}<h4>${esc(source.title || source.name || source.id || "확인한 소재")}</h4>${source.url ? `<a href="${safeURL(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.url)}</a>` : ""}<p class="source-evidence-meta">${esc(affiliateLabel(source.affiliate) || "")}${source.verified_at ? ` · ${date(source.verified_at)} 확인` : ""}${source.expires_at ? ` · ${date(source.expires_at)}까지 유효` : ""}${source.action ? ` · ${{ added: "새로 등록", reused: "기존 소재 재사용" }[source.action] || esc(source.action)}` : ""}</p>${source.claims ? readableValue(source.claims) : ""}${source.evidence || source.provenance?.evidence ? `<h4 class="stage-subheading">출처에서 확인한 근거</h4>${readableValue(source.evidence || source.provenance.evidence)}` : ""}${source.validity_note || source.provenance?.validity_note ? `<p class="source-evidence-meta">유효기간 판단: ${esc(source.validity_note || source.provenance.validity_note)}</p>` : ""}</article>`;
    })
    .join("")}</div>`;
}
function renderSourceResearchReceipt(receipt, { stage = false } = {}) {
  if (!receipt || typeof receipt !== "object") return "";
  const counts = [
    ["added_count", "신규 등록"],
    ["reused_count", "재사용"],
    ["skipped_count", "건너뜀"],
    ["rejected_count", "등록 제외"],
  ].filter(([key]) => typeof receipt[key] === "number");
  const detailKey =
    receipt.research_id || receipt.cycle_id || receipt.created_at || "receipt";
  const queries = Array.isArray(receipt.queries) ? receipt.queries : [];
  const rejected = Array.isArray(receipt.rejected) ? receipt.rejected : [],
    skipped = Array.isArray(receipt.skipped) ? receipt.skipped : [];
  return `<div class="${stage ? "source-stage-receipt" : "source-research-receipt"}"><div class="source-research-receipt-heading"><h3>${stage ? "실제 탐색 기록" : "마지막 수집 기록"}</h3>${receipt.created_at ? `<time>${date(receipt.created_at, true)}</time>` : ""}</div>${counts.length ? `<div class="source-research-metrics">${counts.map(([key, label]) => `<div><span>${label}</span><strong>${receipt[key]}</strong></div>`).join("")}</div>` : ""}${receipt.outcome === "empty" ? `<p class="source-collection-issues">이번 탐색에서는 사용할 소재를 등록하지 않았습니다.${receipt.empty_reason ? ` ${esc(receipt.empty_reason)}` : ""}</p>` : ""}${receipt.decision_summary ? `<p class="source-research-decision">${esc(receipt.decision_summary)}</p>` : ""}${queries.length ? `<details class="source-research-detail" data-source-detail="${esc(detailKey)}:queries" ${stage ? "open" : ""}><summary>실제 검색 질의 ${queries.length}건</summary><ul class="source-research-queries">${queries.map((query) => `<li>${icon("search")}<span>${query?.affiliate ? `<strong>${esc(affiliateLabel(query.affiliate))}</strong> · ` : ""}${esc(typeof query === "string" ? query : query?.query || "검색어 기록 없음")}</span></li>`).join("")}</ul></details>` : ""}${receipt.materials?.length ? `<details class="source-research-detail" data-source-detail="${esc(detailKey)}:materials" ${stage ? "open" : ""}><summary>확인한 소재 ${receipt.materials.length}건</summary>${renderSourceEvidenceCards(receipt.materials, { researched: true })}</details>` : ""}${rejected.length ? `<details class="source-research-detail" data-source-detail="${esc(detailKey)}:rejected"><summary>등록 제외 ${rejected.length}건 · 사유 확인</summary>${readableValue(rejected)}</details>` : ""}${skipped.length ? `<details class="source-research-detail" data-source-detail="${esc(detailKey)}:skipped"><summary>건너뛴 자료 ${skipped.length}건 · 사유 확인</summary>${readableValue(skipped)}</details>` : ""}${receipt.run_id || receipt.cycle_id ? `<p class="source-research-meta">${receipt.run_id ? `수집 실행 ${esc(receipt.run_id)}` : ""}${receipt.cycle_id ? `<br>제작 순환 ${esc(receipt.cycle_id)}` : ""}</p>` : ""}<p class="source-research-meta">AI 작업자가 웹에서 확인하고 저장한 기록입니다. 서버가 별도로 원문 내용을 검증한 것은 아닙니다.</p></div>`;
}
function renderSourceProvenance(source) {
  const provenance = source.provenance;
  if (
    (!provenance || !Object.keys(provenance).length) &&
    sourceOrigin(source) !== "automatic"
  )
    return "";
  return `<section class="source-provenance"><h3>이 소재의 수집 이력${source.source_version ? ` · v${source.source_version}` : ""}</h3>${renderSourceOrigin(source)}${provenance && Object.keys(provenance).length ? readableValue(provenance) : "<p>자동 탐색으로 등록된 소재입니다. 세부 검색 기록은 제작 단계 결과에서 확인하세요.</p>"}<p class="source-research-meta">AI 작업자가 확인한 출처와 근거입니다. 최종 사용 전 내용과 유효기간을 검토하세요.</p></section>`;
}
function renderSourceResearchPanel() {
  const research = state.automation?.source_research || {},
    receipt = research.latest;
  const run = currentRun(),
    active = isActiveRun(run);
  const researching = Boolean(
    research.enabled &&
    run?.status === "running" &&
    run.current_stage === "sources" &&
    state.automation?.worker_status === "active",
  );
  const needsReview = Boolean(
    run?.current_stage === "sources" &&
    ["blocked", "failed"].includes(run.status),
  );
  const paused = active && run.status === "paused";
  const title = researching
    ? "소재 탐색·등록 단계를 진행하고 있어요"
    : needsReview
      ? "소재 탐색 단계에 확인이 필요해요"
      : paused
        ? "자동 제작이 일시정지되어 있어요"
        : active
          ? research.enabled
            ? "자동 제작 실행에 소재 탐색이 포함되어 있어요"
            : "현재 실행의 소재 설정을 확인하세요"
          : receipt
            ? "최근 수집 결과를 보관하고 있어요"
            : "아직 자동 수집 기록이 없습니다";
  const copy = researching
    ? "연결된 작업자가 소재 단계를 수행하고 있습니다. 검색어와 수집 근거는 결과가 저장되면 표시합니다."
    : needsReview
      ? run.pause_reason || "활동 로그에서 실패 사유를 확인한 뒤 재개해 주세요."
      : paused
        ? "이전 수집 기록은 보관됩니다. 자동 제작을 재개하면 중단된 단계부터 이어갑니다."
        : active
          ? research.enabled
            ? "실제 검색 기록이 저장되기 전까지 탐색 완료로 표시하지 않습니다. 작업자 연결 상태는 AI 자동 제작에서 확인하세요."
            : "이 실행에는 자동 웹 탐색 설정이 없습니다. 새 AI 자동 제작 실행에서 공식 자료 탐색을 사용할 수 있습니다."
          : "AI 자동 제작에서 시작하면 로컬 작업자가 바로 공식 자료를 찾아 등록합니다.";
  return `<section class="source-research-panel"><div class="source-research-intro"><div><h2>이야기에 쓸 GS 소재를 AI가 찾아요.</h2><p>AI 자동 제작의 첫 단계에서 계열사 공식 웹사이트를 탐색합니다. 확인한 정보만 출처·확인일·유효기간과 함께 등록하므로 소재를 미리 수동으로 입력하지 않아도 됩니다.</p><div class="source-research-affiliates">${affiliateNames.map((name) => `<span>${esc(affiliateLabel(name))}</span>`).join("")}</div></div>${button("AI 자동 제작으로 이동", "go-auto", "primary", "spark")}</div><div class="source-research-status">${icon(researching ? "search" : "sources")}<div><strong>${esc(title)}</strong><p>${esc(copy)}</p></div>${badge(researching ? "running" : needsReview ? "warning" : paused ? "paused" : receipt ? "completed" : "pending", researching ? "단계 진행 중" : needsReview ? "확인 필요" : paused ? "일시정지" : receipt ? "기록 있음" : active ? labels[run.status] || "실행 중" : "수집 전")}</div>${renderSourceResearchReceipt(receipt)}${research.history?.length > 1 ? `<div class="source-research-history-note">최근 수집 기록 ${research.history.length}건 · 이전 기록은 제작 단계 결과와 활동 로그에서 확인할 수 있습니다.</div>` : ""}</section>`;
}

function renderSources() {
  const sources = sourceRows(),
    rows = sources.filter(
      (s) =>
        (sourceFilter === "all" || s.affiliate === sourceFilter) &&
        (!sourceQuery ||
          (s.title + " " + s.affiliate + " " + affiliateLabel(s.affiliate) + " " + s.claims?.join(" "))
            .toLowerCase()
            .includes(sourceQuery.toLowerCase())),
    );
  return `${heading("GS 소재 관리", "AI가 탐색한 공식 자료와 수집 근거를 확인하고, 필요한 소재를 보완하세요.", button("수동 소재 추가", "new-source", "", "plus"))}${renderSourceResearchPanel()}<div class="source-summary"><span>전체 소재<strong>${sources.length}</strong></span><span>활용 가능<strong>${sources.filter((s) => s.status === "active").length}</strong></span><span>기간 만료<strong>${sources.filter((s) => s.status === "expired").length}</strong></span></div><div class="page-toolbar"><div class="source-status-tabs">${[["all", "전체"], ...affiliateNames.map((a) => [a, affiliateLabel(a)])].map(([v, t]) => `<button class="${sourceFilter === v ? "active" : ""}" data-action="source-filter" data-value="${v}">${t}</button>`).join("")}</div><label class="search-field">${icon("search")}<input type="search" id="source-search" value="${esc(sourceQuery)}" placeholder="소재 이름, 사용할 정보 검색" aria-label="소재 검색"></label></div><section class="panel table-scroll" tabindex="0" role="region" aria-label="GS 소재 목록">${rows.length ? `<table class="source-table"><thead><tr><th>소재 이름 / 출처</th><th>계열사</th><th>활용할 정보</th><th>확인 / 유효기간</th><th>공개 범위</th><th>상태</th></tr></thead><tbody>${rows.map((s) => `<tr><td>${renderSourceOrigin(s)}<span class="source-name">${esc(s.title)}</span><a class="source-url" href="${safeURL(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url)}</a><button class="source-detail-button" data-action="source-detail" data-id="${esc(s.id)}">상세 보기 / 수정</button></td><td><span class="tag">${esc(affiliateLabel(s.affiliate))}</span></td><td><p class="claim-preview">${esc((s.claims || []).slice(0, 2).join(" / "))}</p></td><td>${shortDate(s.verified_at)} 확인<br><span class="muted">${s.expires_at ? shortDate(s.expires_at) + "까지" : "기간 미지정"}</span></td><td><span class="small">${{ internal: "내부 참고", subtle: "자연스러운 등장", explicit: "이름 명시 가능" }[s.visibility] || esc(s.visibility)}</span></td><td>${badge(s.status)}</td></tr>`).join("")}</tbody></table>` : empty(sources.length ? "검색 조건에 맞는 소재가 없어요" : "자동으로 찾은 소재가 여기에 모여요", sources.length ? "다른 계열사나 검색어를 선택해 주세요." : "AI 자동 제작에서 GS 공식 자료를 탐색하고 등록합니다. 직접 확인한 자료는 위의 수동 소재 추가로 보완할 수 있어요.", sources.length ? "" : "go-auto", "AI 자동 제작으로 이동", "full-empty")}</section><div class="helper-banner">${icon("info")}<div><strong>자료의 출처와 공개 노출 범위를 구분해요.</strong>GS SHOP 판매처 이름과 로고는 공개 콘텐츠에 표시하지 않습니다. 브랜드나 상품 정보를 사용하더라도 실제 구매·사용 경험을 만들지 않아요.</div></div>`;
}
function logTable(rows) {
  const stages = state.automation?.stages || [];
  return `<div class="table-scroll" id="log-table-scroll" tabindex="0" role="region" aria-label="활동 기록 목록"><table class="log-table"><thead><tr><th>시각</th><th>단계</th><th>기록</th></tr></thead><tbody>${rows.map((l) => `<tr><td>${date(l.created_at)}</td><td><span class="tag">${esc(stages.find((s) => s.key === l.stage)?.label || l.stage || "워크스페이스")}</span></td><td class="log-message"><span class="log-level-dot ${esc(l.level)}"></span>${esc(l.message || l.event)}${l.detail && Object.keys(l.detail).length ? `<details><summary>상세 정보</summary><pre>${esc(typeof l.detail === "string" ? l.detail : JSON.stringify(l.detail, null, 2))}</pre></details>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
}
function renderLogs() {
  const logs = [...allLogs.values()].sort((a, b) => b.id - a.id),
    rows = logs.filter(
      (l) =>
        (logFilter === "all" ||
          ["error", "warning", "warn", "critical"].includes(l.level) ||
          /fail|error|blocked/.test(l.event)) &&
        (logStage === "all" || l.stage === logStage) &&
        (!logQuery ||
          (l.message + " " + l.event + " " + JSON.stringify(l.detail))
            .toLowerCase()
            .includes(logQuery.toLowerCase())),
    );
  return `${heading("활동 로그", "실행 단계, 저장된 결과, 실패와 재시도 이력을 확인하세요.", button("전체 기록 불러오기", "load-logs", "", "refresh"))}<div class="page-toolbar"><div class="filter-row"><select id="log-filter" aria-label="로그 수준">${options(
    [
      ["all", "모든 기록"],
      ["errors", "실패 · 주의"],
    ],
    logFilter,
  )}</select><select id="log-stage" aria-label="제작 단계">${options([["all", "모든 단계"], ...(state.automation?.stages || []).map((s) => [s.key, s.label])], logStage)}</select><label class="search-field">${icon("search")}<input id="log-search" type="search" placeholder="기록 내용 검색" value="${esc(logQuery)}" aria-label="로그 검색"></label></div></div><p class="logs-stat">불러온 기록 ${logs.length}건 · 검색 결과 ${rows.length}건</p><section class="panel">${rows.length ? logTable(rows) : empty("조건에 맞는 활동 기록이 없어요", "제작을 시작하거나 소재를 등록하면 실제 작업 기록이 이곳에 쌓입니다.", "", "", "full-empty")}</section>`;
}
function renderSettings() {
  const settings = state.studio?.settings || {},
    instagram = settings.instagram || state.config.instagram || {},
    generation = settings.generation || {},
    connected = instagram.connection === "verified";
  return `${heading("설정", "게시 계정과 제작 기본값, 워크스페이스의 연결 상태를 관리하세요.")}<div class="settings-layout"><section class="settings-section"><div><h2>Instagram 계정</h2><p>페르소나의 실제 게시 대상과 연결 상태를 확인하세요.</p></div><div><div class="account-connection"><span class="instagram-icon">${icon("instagram")}</span><div><h3>${instagram.account ? "@" + esc(instagram.account) : "게시할 계정 미지정"}</h3><p>${connected ? "Instagram에서 계정과 게시 권한을 확인했습니다." : "대상 계정 지정 후 실제 인증 연결이 필요합니다."}</p></div>${badge(connected ? "active" : "warning", connected ? "연결됨" : "미연결")}</div><form id="account-form" class="field-stack"><label>게시 대상 계정<input name="account" id="account-handle" value="${esc(instagram.account || "")}" placeholder="@demo_account" autocomplete="off"><p class="field-help">비밀번호 없이 계정 아이디만 저장합니다. 저장만으로 계정 인증이나 연결이 완료되지는 않습니다.</p></label><div class="form-footer"><button type="submit" class="button">대상 계정 저장</button><button type="button" class="button" data-action="verify-instagram">연결 다시 확인</button></div>${instagram.verified_at ? `<p class="field-help">최근 인증 확인 ${date(instagram.verified_at)} · ${instagram.account_type === "MEDIA_CREATOR" ? "크리에이터" : "비즈니스"} 계정</p>` : ""}<p class="field-help">${connected && instagram.publisher_ready === false ? "계정 인증과 게시 권한을 연결했습니다. 실제 자동 게시 작업자와 미디어 전달 연결은 아직 준비되지 않았습니다." : instagram.connection === "recheck-required" ? "마지막 인증 확인 후 24시간이 지났습니다. 연결 다시 확인을 눌러주세요." : ""}</p></form></div></section><section class="settings-section"><div><h2>제작 기본값</h2><p>새 기획과 생성 작업의 기본 설정입니다. 자동 제작의 목표 개수와 별개로 재시도·대기 한도를 관리해요.</p></div><form id="generation-settings-form" class="field-stack"><div class="field-row"><label>기본 콘텐츠 형식<select name="default_format">${options(
    [
      ["carousel", "카드형 피드"],
      ["image", "단일 이미지"],
      ["video", "짧은 영상"],
    ],
    generation.default_format || "carousel",
  )}</select></label><label>단계별 최대 시도<select name="max_attempts_per_job">${options(
    [
      ["1", "1회"],
      ["2", "2회"],
      ["3", "3회"],
    ],
    String(
      generation.max_attempts_per_job || state.config.max_attempts_per_job || 2,
    ),
  )}</select></label></div><label>수동 제작 대기 한도<input type="number" name="max_pending_requests" value="${generation.max_pending_requests || state.config.max_pending_requests || 20}" min="1" max="100" required><p class="field-help">동시에 대기시킬 수 있는 수동 기획의 수입니다. 연속 생성의 총 건수를 제한하지 않아요.</p></label><label class="check-field"><input type="checkbox" name="video_enabled" ${generation.video_enabled ? "checked" : ""}>직접 기획에서 영상 형식을 기본 옵션에 포함</label><p class="field-help">AI 자동 제작의 미디어 형식은 시작할 때 별도로 선택합니다. 실제 영상 생성은 연결된 도구 지원 여부에 따라 달라집니다.</p><div class="form-footer"><button type="submit" class="button">제작 기본값 저장</button></div></form></section><section class="settings-section"><div><h2>워크스페이스</h2><p>현재 개발 환경과 콘텐츠 운영 기준을 확인하세요.</p></div><div><form id="workspace-settings-form" class="inline-input"><label>워크스페이스 이름<input name="workspace_name" value="${esc(settings.workspace_name || "Boca studio")}" maxlength="80" required></label><button type="submit" class="button">저장</button></form><dl class="settings-details"><div class="setting-readonly"><dt>실행 환경</dt><dd>이 Mac의 로컬 서버</dd></div><div class="setting-readonly"><dt>콘텐츠 생성</dt><dd>Codex 작업자 · 내장 생성 도구</dd></div><div class="setting-readonly"><dt>이미지 생성</dt><dd>내장 생성 도구</dd></div><div class="setting-readonly"><dt>영상 생성</dt><dd>Segmind · 설정된 비용 한도 유지</dd></div><div class="setting-readonly"><dt>가상 인물 표시</dt><dd>${esc(disclosure)}</dd></div><div class="setting-readonly"><dt>게시 원칙</dt><dd>사람이 승인한 정확한 버전만 게시</dd></div><div class="setting-readonly"><dt>공개 노출</dt><dd>GS SHOP 판매처 이름·로고 제외</dd></div></dl></div></section></div>`;
}
let stageDialogSession = null;
let dialogRevision = 0,
  dialogDirty = false,
  dialogStep = 0,
  dialogPersona = null,
  dialogBrief = null,
  dialogSource = null;
function openDialog(title, copy, body, footer = "") {
  stopStageDialog();
  $("studio-dialog")
    .querySelectorAll("video")
    .forEach((video) => video.pause());
  dialogRevision += 1;
  dialogDirty = false;
  $("dialog-content").innerHTML =
    `<div class="dialog-header"><div><h2 id="dialog-title">${esc(title)}</h2><p>${esc(copy)}</p></div><button class="icon-button" data-action="close-dialog" aria-label="닫기">${icon("close")}</button></div>${body}${footer}`;
  if (!$("studio-dialog").open) $("studio-dialog").showModal();
  $("studio-dialog").scrollTop = 0;
  document.body.classList.add("dialog-open-body");
}
function closeDialog(force = false) {
  if (
    !force &&
    dialogDirty &&
    !confirm("저장하지 않은 내용이 있습니다. 창을 닫을까요?")
  )
    return;
  stopStageDialog();
  dialogDirty = false;
  $("studio-dialog")
    .querySelectorAll("video")
    .forEach((video) => video.pause());
  $("studio-dialog").close();
  document.body.classList.remove("dialog-open-body");
}
function renderAppearanceFields(appearance) {
  if (!appearance || typeof appearance !== "object" || Array.isArray(appearance))
    return `<label>외형 설정<textarea name="appearance" rows="3" placeholder="예: 자연스러운 검정 중단발, 단정한 일상복, 따뜻한 인상">${esc(typeof appearance === "string" ? appearance : "")}</textarea></label>`;
  const labels = {
    direction: "전체 인상", face: "얼굴 특징", hair: "머리",
    makeup: "화장", makeup_avoid: "피할 화장", styling: "의상과 스타일",
    identity_reference_policy: "기준 이미지 사용 원칙",
  };
  return Object.entries(appearance).map(([key, value]) => {
    if (typeof value !== "string" && !(Array.isArray(value) && value.every((item) => typeof item === "string")))
      return "";
    return `<label>${esc(labels[key] || "추가 외형 설정")}<textarea name="appearance:${esc(key)}" rows="3">${esc(Array.isArray(value) ? value.join("\n") : value)}</textarea></label>`;
  }).join("");
}
function appearanceFromForm(previous, values) {
  if (!previous || typeof previous !== "object" || Array.isArray(previous))
    return (typeof values.appearance === "string" ? values.appearance : typeof previous === "string" ? previous : "").trim();
  const updated = { ...previous };
  for (const [key, value] of Object.entries(previous)) {
    const field = values["appearance:" + key];
    if (typeof field !== "string") continue;
    if (typeof value === "string") updated[key] = field.trim();
    else if (Array.isArray(value) && value.every((item) => typeof item === "string"))
      updated[key] = field.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  }
  return updated;
}
function personaDialog(id) {
  dialogPersona =
    (state.studio?.personas || []).find((p) => p.id === id) || null;
  const p = profile(dialogPersona) || {},
    family =
      p.family?.description ||
      (p.family?.daughter
        ? `${p.family.daughter.age}세 외동딸. 엄마와 닮은 외형으로 가끔 등장.`
        : "");
  dialogStep = 0;
  openDialog(
    dialogPersona ? "페르소나 편집" : "페르소나 만들기",
    "일관된 일상을 만들기 위한 기본 설정을 저장하세요.",
    `<form id="persona-form" novalidate><div class="dialog-body"><div class="wizard-tabs" role="tablist" aria-label="프로필 설정 단계"><button class="active" type="button" data-action="persona-step" data-step="0" role="tab" aria-selected="true"><span>1</span>기본 정보</button><button type="button" data-action="persona-step" data-step="1" role="tab" aria-selected="false"><span>2</span>성격과 취향</button><button type="button" data-action="persona-step" data-step="2" role="tab" aria-selected="false"><span>3</span>프로필 완성</button></div><section class="wizard-step field-stack" data-step="0"><div class="field-row"><label>페르소나 이름<input name="display_name" value="${esc(p.display_name || "")}" maxlength="40" required placeholder="예: 서윤"></label><label>나이 설정<input name="age_description" value="${esc(p.age_description || "")}" placeholder="예: 30대 후반" required></label></div><div class="field-row"><label>국적<input name="nationality" value="${esc(p.nationality || "한국인")}" placeholder="한국인"></label><label>성별<select name="gender">${options(["여성", "남성", "기타"], p.gender || "여성")}</select></label></div><div class="field-row"><label>일하는 곳<input name="work_location" value="${esc(p.work?.location || "")}" placeholder="예: 서울 여의도"></label><label>일상 역할<input name="work_role" value="${esc(p.work?.role || "")}" placeholder="예: 직장인, 워킹맘"></label></div><label>사는 동네<input name="home_neighborhood" value="${esc(p.home?.neighborhood || "")}" placeholder="예: 서울 목동"><p class="field-help">이야기의 배경이 될 지역만 정하세요. 실제 주소는 필요하지 않습니다.</p></label><label>가족 설정 <span class="optional">선택</span><textarea name="family_description" rows="2" placeholder="예: 엄마를 닮은 5살 외동딸이 가끔 등장">${esc(family)}</textarea></label></section><section class="wizard-step field-stack" data-step="1" hidden><label>성격<textarea name="personality" rows="3" placeholder="예: 계획적이고 실용적, 일상에서는 다정함">${esc(array(p.personality).join(", "))}</textarea><p class="field-help">쉼표나 줄바꿈으로 구분해 주세요.</p></label><label>말투<input name="tone" value="${esc(p.tone || "")}" placeholder="예: 간결하지만 차갑지 않은 존댓말"></label><label>관심사<input name="interests" value="${esc(array(p.interests).join(", "))}" placeholder="예: 집 가꾸기, 일상 공유, 취향 발견"><p class="field-help">반복해서 다룰 주제를 쉼표로 구분해 주세요.</p></label>${renderAppearanceFields(p.appearance)}<div class="reference-placeholder">${icon("image")}<div><h4>${dialogPersona?.portrait_url ? "외형 참고 이미지가 등록되어 있어요" : "외형은 먼저 글로 설정해요"}</h4><p>이미지 생성은 콘텐츠 제작 단계에서 진행합니다. 설정을 저장하는 것만으로 이미지를 생성하거나 유료 API를 호출하지 않습니다.</p></div></div></section><section class="wizard-step field-stack" data-step="2" hidden><label>Instagram 아이디 초안 <span class="optional">선택</span><input name="instagram_handle" value="${esc(p.instagram_handle || "")}" placeholder="예: seoyun.daily" maxlength="30"><p class="field-help">프로필 미리보기용입니다. 실제 계정은 별도로 준비해야 합니다.</p></label><label>프로필 소개<textarea name="bio" id="persona-bio" rows="5" placeholder="이 사람이 어떤 일상을 나누는지 소개해 주세요.">${esc(p.bio || "")}</textarea></label><div><button class="button subtle small" type="button" data-action="draft-profile">${icon("spark")}설정으로 소개 초안 만들기</button><p class="field-help">입력한 설정을 조합한 초안입니다. 저장 전에 직접 다듬을 수 있어요.</p></div><div class="persona-draft-preview"><strong>콘텐츠에 함께 표시되는 안내</strong><p>${esc(p.content?.disclosure || disclosure)}</p></div></section></div><div class="dialog-footer"><p>설정을 저장하면 새 프로필 버전이 됩니다.</p><div class="button-group"><button type="button" class="button" id="persona-back" data-action="persona-prev" hidden>이전</button><button type="button" class="button primary" id="persona-next" data-action="persona-next">다음</button><button type="submit" class="button primary" id="persona-submit" hidden>${dialogPersona ? "변경사항 저장" : "페르소나 생성"}</button></div></div></form>`,
  );
}
function setPersonaStep(next) {
  dialogStep = Math.max(0, Math.min(2, next));
  document
    .querySelectorAll(".wizard-step")
    .forEach((el) => (el.hidden = Number(el.dataset.step) !== dialogStep));
  document.querySelectorAll(".wizard-tabs button").forEach((el) => {
    el.classList.toggle("active", Number(el.dataset.step) === dialogStep);
    el.setAttribute(
      "aria-selected",
      Number(el.dataset.step) === dialogStep ? "true" : "false",
    );
  });
  $("persona-back").hidden = dialogStep === 0;
  $("persona-next").hidden = dialogStep === 2;
  $("persona-submit").hidden = dialogStep !== 2;
  $("studio-dialog").scrollTop = 0;
  $("studio-dialog").querySelector(".dialog-body").scrollTop = 0;
}
function briefDialog(id, idea) {
  dialogBrief = (state.studio?.briefs || []).find((b) => b.id === id) || null;
  const b = dialogBrief || idea || {},
    frozen = dialogBrief && !["draft", "failed"].includes(dialogBrief.status);
  openDialog(
    dialogBrief ? "콘텐츠 기획 편집" : "새 콘텐츠 기획",
    "상품을 고르기 전에, 페르소나가 나눌 일상 이야기를 적어주세요.",
    `<form id="brief-form"><div class="dialog-body field-stack">${b.status === "failed" ? '<div class="inline-warning">' + icon("info") + "기존 작업 기록을 확인한 뒤 기획을 수정해서 다시 요청해 주세요.</div>" : ""}${frozen ? '<div class="inline-warning">' + icon("lock") + "제작 요청한 기획은 수정할 수 없어요. 아래에서 새 초안으로 복사할 수 있습니다.</div>" : ""}<label>페르소나<select name="persona_id" ${frozen ? "disabled" : ""}>${options(
      (state.studio?.personas || [activePersona()]).map((p) => [
        p.id,
        personaName(p),
      ]),
      b.persona_id || activePersona().id,
    )}</select></label><label>이야기 제목<input name="title" value="${esc(b.title || "")}" required maxlength="200" placeholder="예: 퇴근 후, 15분만 집을 정리한다면" ${frozen ? "disabled" : ""}></label><label>기획 메모<textarea name="brief" rows="6" maxlength="12000" placeholder="어떤 하루인가요? 등장하는 인물, 주요 장면, 전하고 싶은 감정을 적어주세요." ${frozen ? "disabled" : ""}>${esc(b.brief || "")}</textarea></label><div class="field-row"><label>콘텐츠 형식<select name="format" ${frozen ? "disabled" : ""}>${options(
      [
        ["carousel", "카드형 피드 · 장수 유동"],
        ["image", "단일 이미지"],
        ["video", "짧은 영상 · 도구 지원 필요"],
      ],
      b.format ||
        state.studio?.settings?.generation?.default_format ||
        "carousel",
    )}</select></label><label>연결할 소재<select name="affiliate" ${frozen ? "disabled" : ""}>${options([["", "이야기에 맞게 선택"], ["일상", "순수 일상 이야기"], ...affiliateNames.map((a) => [a, affiliateLabel(a)])], b.affiliate || "")}</select></label></div><p class="field-help">저장한 기획은 초안으로 보관됩니다. ‘제작 요청’을 누르면 작업자 대기열에 추가됩니다.</p></div><div class="dialog-footer"><p>카드 장수는 이야기에 맞게 구성합니다.</p><div class="button-group"><button type="button" class="button" data-action="close-dialog">취소</button>${frozen ? button("새 초안으로 복사", "copy-brief", "primary", "plus") : '<button type="submit" class="button primary">기획 저장</button>'}</div></div></form>`,
  );
}
function sourceDialog(id) {
  dialogSource = sourceRows().find((s) => s.id === id) || null;
  const s = dialogSource || {};
  openDialog(
    dialogSource ? "GS 소재 확인·수정" : "GS 소재 수동 등록",
    "공개 출처에서 확인한 정보와 사용할 범위를 함께 저장하세요.",
    `<form id="source-form"><div class="dialog-body field-stack">${dialogSource ? renderSourceProvenance(s) : `<p class="field-help">자동 탐색 외에 직접 확인한 공개 자료를 추가하는 보조 기능입니다.</p>`}<div class="field-row"><label>계열사<select name="affiliate">${options(affiliateNames.map((a) => [a, affiliateLabel(a)]), s.affiliate || affiliateNames[0])}</select></label><label>공개 노출 범위<select name="visibility">${options(
      [
        ["subtle", "일상 속 자연스러운 등장"],
        ["internal", "내부 참고만"],
        ["explicit", "브랜드·상품명 명시 가능"],
      ],
      s.visibility || "subtle",
    )}</select></label></div><label>소재 이름<input name="title" value="${esc(s.title || "")}" required maxlength="200" placeholder="예: 집을 정리할 때 함께 쓰는 생활 소품"></label><label>공개 출처 URL<input type="url" name="url" value="${esc(s.url || "")}" required placeholder="https://"><p class="field-help">계열사 또는 브랜드의 공식 공개 자료를 등록해 주세요.</p></label><div class="field-row"><label>정보 확인 시각<input type="datetime-local" name="verified_at" value="${inputDate(s.verified_at || new Date())}" required></label><label>유효기간 종료 <span class="optional">선택</span><input type="datetime-local" name="expires_at" value="${inputDate(s.expires_at)}"></label></div><label>활용할 정보<textarea name="claims" rows="4" required placeholder="출처에서 확인한 정보를 한 줄에 하나씩 적어주세요.">${esc((s.claims || []).join("\n"))}</textarea><p class="field-help">추측한 성능이나 실제 사용한 것처럼 보이는 후기는 넣지 마세요.</p></label></div><div class="dialog-footer"><p>GS SHOP 판매처 이름·로고는 노출하지 않습니다.</p><div class="button-group"><button type="button" class="button" data-action="close-dialog">취소</button><button type="submit" class="button primary">소재 저장</button></div></div></form>`,
  );
}
function formValues(form) {
  return Object.fromEntries(new FormData(form).entries());
}
async function handleSubmit(event) {
  const form = event.target;
  if (!form.matches("form")) return;
  event.preventDefault();
  const values = formValues(form);
  if (form.id === "persona-form") {
    const invalid = [...form.querySelectorAll("[required]")].find(
      (el) => !el.value.trim(),
    );
    if (invalid) {
      setPersonaStep(Number(invalid.closest(".wizard-step").dataset.step));
      invalid.focus();
      invalid.reportValidity();
      return;
    }
    const previous = profile(dialogPersona) || {};
    const updated = {
      ...previous,
      display_name: values.display_name.trim(),
      age_description: values.age_description.trim(),
      nationality: values.nationality.trim(),
      gender: values.gender,
      work: {
        ...(previous.work || {}),
        location: values.work_location.trim(),
        role: values.work_role.trim(),
      },
      home: {
        ...(previous.home || {}),
        neighborhood: values.home_neighborhood.trim(),
      },
      family: {
        ...(previous.family || {}),
        description: values.family_description.trim(),
      },
      personality: array(values.personality),
      tone: values.tone.trim(),
      interests: array(values.interests),
      appearance: appearanceFromForm(previous.appearance, values),
      instagram_handle: values.instagram_handle.replace(/^@/, "").trim(),
      bio: values.bio.trim(),
      content: {
        ...(previous.content || {}),
        disclosure: previous.content?.disclosure || disclosure,
      },
    };
    const id = dialogPersona?.id;
    await mutate(
      async () => {
        await api(
          id ? "/api/personas/" + encodeURIComponent(id) : "/api/personas",
          {
            ...(id ? { base_version: dialogPersona.version } : {}),
            profile: updated,
          },
        );
        closeDialog(true);
        if (page !== "persona") {
          page = "persona";
          history.replaceState(null, "", "#persona");
        }
        pageSignature = "";
      },
      id
        ? "페르소나의 새 버전을 저장했습니다."
        : "페르소나를 생성했습니다. 작업할 페르소나를 선택해 주세요.",
    );
  } else if (form.id === "brief-form") {
    const id = dialogBrief?.id;
    await mutate(async () => {
      await api(id ? "/api/briefs/" + encodeURIComponent(id) : "/api/briefs", {
        ...(id ? { base_version: dialogBrief.version } : {}),
        ...values,
      });
      closeDialog(true);
      createTab = "briefs";
      page = "create";
      history.replaceState(null, "", "#create");
      pageSignature = "";
    }, "콘텐츠 기획을 초안으로 저장했습니다.");
  } else if (form.id === "source-form") {
    await mutate(async () => {
      await api("/api/sources", {
        ...(dialogSource ? { id: dialogSource.id } : {}),
        affiliate: values.affiliate,
        title: values.title.trim(),
        url: values.url.trim(),
        verified_at: koreanISO(values.verified_at),
        expires_at: koreanISO(values.expires_at),
        claims: values.claims
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        visibility: values.visibility,
      });
      closeDialog(true);
    }, "소재와 출처를 저장했습니다.");
  } else if (form.id === "run-form") {
    const run = currentRun(),
      active = isActiveRun(run);
    const start = active
      ? run.start_at
      : koreanISO(values.start_at) ||
        new Date().toISOString().replace("Z", "+00:00");
    const end = active ? run.end_at : koreanISO(values.end_at);
    if (
      !active &&
      values.end_at &&
      new Date(koreanISO(values.end_at)) <= new Date()
    ) {
      toast("종료 시각을 현재 시각 이후로 지정해 주세요.");
      return;
    }
    if (end && new Date(end) <= new Date(start)) {
      toast("종료 시각을 시작 시각 이후로 지정해 주세요.");
      return;
    }
    const persona_id = active ? run.persona_id : values.persona_id;
    if (!persona_id) {
      toast("콘텐츠를 만들 페르소나를 선택해 주세요.");
      return;
    }
    const media_mode = active
      ? run.settings?.media_mode || "images"
      : values.media_mode || "mixed";
    const stop_after_posts = active
      ? run.settings?.stop_after_posts ?? null
      : values.quantity_mode === "limited" ? Number(values.stop_after_posts) : null;
    if (stop_after_posts !== null && (!Number.isInteger(stop_after_posts) || stop_after_posts < 1 || stop_after_posts > 1000)) {
      toast("목표 콘텐츠 수를 1~1,000 사이의 정수로 입력해 주세요.");
      return;
    }
    await mutate(
      () =>
        api("/api/runs/start", {
          start_at: start,
          end_at: end,
          persona_id,
          media_mode,
          stop_after_posts,
          ...(!active && media_mode !== "images" ? { video: { duration: Number(values.video_duration), resolution: values.video_resolution } } : {}),
        }),
      "AI 자동 제작 요청을 저장했습니다. 작업자가 연결되면 GS 공식 자료 탐색·등록부터 순환합니다.",
    );
  } else if (form.id === "editor") {
    await mutate(async () => {
      await api("/api/contents/" + encodeURIComponent(selectedId) + "/edit", {
        base_version: editingVersion,
        title: values.title,
        caption: values.caption,
        hashtags: values.hashtags.split(/\s+/).filter(Boolean),
      });
      dirty = false;
    }, "수정본을 새 버전으로 저장했습니다. 다시 검토한 뒤 승인해 주세요.");
  } else if (form.id === "account-form") {
    await mutate(
      () => api("/api/settings", { instagram: { account: values.account } }),
      "게시 대상 계정을 저장했습니다. 실제 인증 연결은 별도로 필요합니다.",
    );
  } else if (form.id === "generation-settings-form") {
    await mutate(
      () =>
        api("/api/settings", {
          generation: {
            default_format: values.default_format,
            max_attempts_per_job: Number(values.max_attempts_per_job),
            max_pending_requests: Number(values.max_pending_requests),
            video_enabled: values.video_enabled === "on",
          },
        }),
      "제작 기본값을 저장했습니다.",
    );
  } else if (form.id === "workspace-settings-form") {
    await mutate(
      () => api("/api/settings", { workspace_name: values.workspace_name }),
      "워크스페이스 이름을 저장했습니다.",
    );
  }
}
async function handleAction(target) {
  const action = target.dataset.action,
    id = target.dataset.id;
  if (action === "retry-connection") {
    await refresh(true);
  } else if (action === "verify-instagram") {
    await mutate(() => api("/api/instagram/verify", {}), "Instagram 계정과 게시 권한을 확인했습니다.");
  } else if (action === "new-persona") personaDialog();
  else if (action === "edit-persona") personaDialog(id || activePersona().id);
  else if (action === "select-persona") {
    await mutate(
      () => api("/api/personas/" + encodeURIComponent(id) + "/select", {}),
      "작업 페르소나를 변경했습니다.",
    );
  } else if (action === "new-brief") briefDialog();
  else if (action === "edit-brief") briefDialog(id);
  else if (action === "idea-brief")
    briefDialog(null, {
      title: target.dataset.title,
      brief: target.dataset.brief,
    });
  else if (action === "copy-brief") {
    const b = dialogBrief;
    dialogDirty = false;
    briefDialog(null, {
      title: b.title + " (새 초안)",
      brief: b.brief,
      persona_id: b.persona_id,
      format: b.format,
      affiliate: b.affiliate,
    });
  } else if (action === "produce-brief") {
    await mutate(
      () => api("/api/briefs/" + encodeURIComponent(id) + "/produce", {}),
      "제작 대기열에 추가했습니다. 예약된 실행이 있으면 해당 시작 시각에 진행합니다.",
    );
  } else if (action === "new-source") sourceDialog();
  else if (action === "source-detail") sourceDialog(id);
  else if (action === "close-dialog") closeDialog();
  else if (action === "persona-step")
    setPersonaStep(Number(target.dataset.step));
  else if (action === "persona-prev") setPersonaStep(dialogStep - 1);
  else if (action === "persona-next") {
    const step = document.querySelector(".wizard-step:not([hidden])"),
      invalid = [...step.querySelectorAll("[required]")].find(
        (el) => !el.value.trim(),
      );
    if (invalid) {
      invalid.focus();
      invalid.reportValidity();
      return;
    }
    setPersonaStep(dialogStep + 1);
  } else if (action === "draft-profile") {
    const values = formValues($("persona-form")),
      intro = [
        values.home_neighborhood
          ? values.home_neighborhood +
            "에서 살아가는 " +
            (values.work_role || "사람") +
            "."
          : values.work_role
            ? values.work_role + "의 일상."
            : "나만의 속도로 기록하는 일상.",
        array(values.interests).length
          ? array(values.interests).join(" · ")
          : "",
        disclosure,
      ]
        .filter(Boolean)
        .join("\n");
    $("persona-bio").value = intro;
    dialogDirty = true;
    toast("입력한 설정으로 소개 초안을 만들었습니다. 자유롭게 다듬어 주세요.");
  } else if (action === "create-tab") {
    createTab = target.dataset.tab;
    render(true);
    if (createTab === "automation") {
      await loadAutoEvidence();
      render();
    }
  } else if (action === "save-auto-video") {
    const duration = $("run-video-duration");
    if (!duration.reportValidity()) return;
    await mutate(async () => {
      await api("/api/settings", { generation: { auto_video: {
        duration: Number(duration.value), resolution: $("run-video-resolution").value,
      } } });
      autoDraft.video_duration = null;
      autoDraft.video_resolution = null;
    }, "자동 영상 기본값을 저장했습니다. 다음 실행부터 사용합니다.");
  } else if (action === "video-library-refresh") {
    await loadVideoLibrary();
  } else if (action === "video-library-select") {
    rememberVideoSelection(id);
    videoLibrary.selectionMissing = false;
    patchVideoLibrary();
    if (window.matchMedia("(max-width: 940px)").matches)
      $("video-library-player")?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
  } else if (action === "video-library-filter") {
    videoLibrary.filter = target.dataset.value;
    patchVideoLibrary();
  } else if (action === "show-results") {
    createTab = "results";
    if (page !== "create") navigate("create");
    else render(true);
    window.scrollTo({ top: 0, behavior: "instant" });
  } else if (action === "result-card") {
    const content = state.contents.find((c) => c.id === id),
      index = Number(target.dataset.index);
    const card = content?.payload?.cards?.[index],
      article = target.closest(".production-result");
    if (!card || !article) return;
    resultCards.set(id, index);
    article.querySelector(".result-media").innerHTML = media(card, {
      interactive: true,
    });
    article.querySelector(".result-media-caption").textContent =
      `${index + 1} / ${content.payload.cards.length} · ${card.alt || "첨부 미디어"}`;
    article
      .querySelectorAll(".result-filmstrip button")
      .forEach((button, i) => {
        button.classList.toggle("selected", i === index);
        button.setAttribute("aria-pressed", String(i === index));
      });
  } else if (action === "brief-filter") {
    briefFilter = target.dataset.value;
    render(true);
  } else if (action === "source-filter") {
    sourceFilter = target.dataset.value;
    render(true);
  } else if (action === "review-filter") {
    if (dirty && !confirm("저장하지 않은 수정이 있습니다. 필터를 변경할까요?"))
      return;
    dirty = false;
    reviewFilter = target.dataset.value;
    selectedId =
      (state.contents || []).find(
        (c) => reviewFilter === "all" || c.status === reviewFilter,
      )?.id || null;
    selectedCard = 0;
    render(true);
  } else if (action === "go-create" || action === "go-auto") {
    createTab = "automation";
    navigate("create");
  } else if (action === "go-review") navigate("review");
  else if (action === "production-show-logs") {
    autoEvidenceTab = "files";
    render(true);
    document.querySelector(".production-monitor-evidence")?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
      block: "start",
    });
  } else if (action === "auto-evidence-tab") {
    autoEvidenceTab = target.dataset.tab;
    render(true);
  } else if (action === "refresh-artifacts") {
    await loadAutoEvidence();
    render(true);
    if (!autoArtifactsError) toast("저장된 제작 기록을 불러왔습니다.");
  } else if (action === "open-stage") {
    await stageDialog(target.dataset.cycle, target.dataset.stage);
  } else if (action === "stage-open-content") {
    closeDialog();
    selectedId = id;
    selectedCard = 0;
    reviewFilter = "all";
    navigate("review");
  } else if (action === "more-stage-records") {
    autoStageLimit += 14;
    render(true);
  } else if (action === "go-feed") navigate("feed");
  else if (action === "open-content" || action === "select-content") {
    if (
      dirty &&
      !confirm("저장하지 않은 수정이 있습니다. 다른 콘텐츠를 열까요?")
    )
      return;
    dirty = false;
    selectedId = id;
    selectedCard = 0;
    if (action === "open-content") {
      reviewFilter = "all";
      navigate("review");
    } else render(true);
  } else if (action === "select-card") {
    selectedCard = Number(target.dataset.index);
    const p = state.contents.find((c) => c.id === selectedId)?.payload;
    if (!p) return;
    $("hero").innerHTML = media(p.cards[selectedCard], { interactive: true });
    $("scene").textContent =
      selectedCard +
      1 +
      " / " +
      p.cards.length +
      " · " +
      (p.cards[selectedCard].alt || "이미지 설명 없음");
    document
      .querySelectorAll("#filmstrip button")
      .forEach((b, i) => b.classList.toggle("selected", i === selectedCard));
  } else if (action === "approve" || action === "reject") {
    if (dirty) {
      toast("수정한 내용을 먼저 저장해 주세요.");
      return;
    }
    await mutate(
      () =>
        api("/api/contents/" + encodeURIComponent(selectedId) + "/" + action, {
          version: editingVersion,
        }),
      action === "approve"
        ? "검토한 버전을 승인했습니다. 게시 대기로 보관합니다."
        : "이 콘텐츠를 반려했습니다.",
    );
  } else if (["run-pause", "run-resume", "run-stop"].includes(action)) {
    const run = currentRun();
    if (!run) return;
    await controlRun(
      run.id, action.replace("run-", ""),
      {
        "run-pause": "일시정지를 요청했습니다. 저장된 결과는 유지됩니다.",
        "run-resume": "재개를 요청했습니다.",
        "run-stop": "중지했습니다. 완성된 콘텐츠와 기록은 보관됩니다.",
      }[action],
    );
  } else if (action === "load-logs") {
    target.disabled = true;
    try {
      let after = 0;
      for (let n = 0; n < 100; n++) {
        const response = await fetch(
            "/api/logs?after_id=" + after + "&limit=500",
            { cache: "no-store" },
          ),
          result = await response.json();
        if (!response.ok)
          throw Error(result.error || "로그를 불러오지 못했습니다.");
        const logs = result.logs || [];
        if (!logs.length) break;
        logs.forEach((l) => allLogs.set(l.id, l));
        const next = Math.max(...logs.map((l) => Number(l.id)));
        if (next <= after) break;
        after = next;
        if (logs.length < 500 || result.has_more === false) break;
      }
      render(true);
      toast("저장된 전체 활동 기록을 불러왔습니다.");
    } catch (e) {
      toast(e.message);
    } finally {
      target.disabled = false;
    }
  }
}
document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-nav]");
  if (nav) {
    event.preventDefault();
    navigate(nav.dataset.nav);
    return;
  }
  const action = event.target.closest("[data-action]");
  if (action && !action.disabled) {
    event.preventDefault();
    handleAction(action).catch((e) => toast(e.message));
  }
});
document.addEventListener("submit", (event) => {
  handleSubmit(event).catch((e) => toast(e.message));
});
document.addEventListener(
  "toggle",
  (event) => {
    if (event.target.matches?.(".auto-schedule") && !isActiveRun(currentRun()))
      autoDraft.schedule_open = event.target.open;
  },
  true,
);
document.addEventListener("input", (event) => {
  if (event.target.id === "run-count") {
    autoDraft.stop_after_posts = event.target.value;
    updateAutoQuantityOptions();
  }
  if (event.target.id === "run-video-duration") {
    autoDraft.video_duration = event.target.value;
    updateAutoVideoEstimate();
  }
  if (
    event.target.closest("#run-form") &&
    ["start_at", "end_at"].includes(event.target.name)
  )
    autoDraft[event.target.name] = event.target.value;
  if (event.target.closest("#studio-dialog")) dialogDirty = true;
  if (
    event.target.closest("#editor") &&
    ["title", "caption", "hashtags"].includes(event.target.id)
  ) {
    dirty = true;
    if ($("approve")) $("approve").disabled = true;
    $("revision-note").textContent =
      "저장하지 않은 수정이 있습니다. 수정본을 저장한 뒤 새 버전을 승인하세요.";
  }
  if (event.target.id === "source-search") {
    sourceQuery = event.target.value;
    debounceSearch("sources", "source-search");
  }
  if (event.target.id === "log-search") {
    logQuery = event.target.value;
    debounceSearch("logs", "log-search");
  }
});
function debounceSearch(expected, id) {
  clearTimeout(debounceSearch.timer);
  debounceSearch.timer = setTimeout(() => {
    if (page !== expected) return;
    const input = $(id),
      position = input.selectionStart;
    render(true);
    $(id)?.focus();
    if ($(id)?.setSelectionRange)
      try {
        $(id).setSelectionRange(position, position);
      } catch {}
  }, 220);
}
document.addEventListener("change", (event) => {
  if (event.target.closest("#studio-dialog")) dialogDirty = true;
  if (event.target.closest("#run-form")) {
    const name = event.target.name;
    if (["persona_id", "media_mode", "start_at", "end_at", "video_duration", "video_resolution", "quantity_mode", "stop_after_posts"].includes(name))
      autoDraft[name] = event.target.value;
    if (["quantity_mode", "stop_after_posts"].includes(name)) updateAutoQuantityOptions();
    if (["video_duration", "video_resolution"].includes(name)) updateAutoVideoEstimate();
    if (name === "media_mode") {
      if ($("auto-video-options")) {
        $("auto-video-options").hidden = event.target.value === "images";
        $("auto-video-options").disabled = event.target.value === "images";
      }
      document
        .querySelectorAll(".auto-media-choice")
        .forEach((choice) =>
          choice.classList.toggle(
            "selected",
            choice.querySelector("input").checked,
          ),
        );
      if ($("auto-guide-mode"))
        $("auto-guide-mode").textContent =
          event.target.value === "images"
            ? "이미지 중심 실행에는 적용 안 함"
            : "낮은 관여도로 참고";
      $("auto-video-note").textContent = autoMediaNote(event.target.value);
    }
  }
  if (event.target.id === "feed-filter") {
    feedFilter = event.target.value;
    render(true);
  }
  if (event.target.id === "log-filter") {
    logFilter = event.target.value;
    render(true);
  }
  if (event.target.id === "log-stage") {
    logStage = event.target.value;
    render(true);
  }
});
$("studio-dialog").addEventListener("focusin", (event) => {
  const field = event.target;
  if (!field.closest(".dialog-body")) return;
  requestAnimationFrame(() => {
    if (document.activeElement === field)
      field.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
});
$("studio-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeDialog();
});
$("studio-dialog").addEventListener("click", (event) => {
  if (event.target === $("studio-dialog")) {
    const rect = $("studio-dialog").getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    )
      closeDialog();
  }
});
const sidebarMedia = window.matchMedia("(max-width: 720px)");
function setSidebar(open, { restoreFocus = true } = {}) {
  const sidebar = $("sidebar");
  const mobile = sidebarMedia.matches;
  const wasOpen = sidebar.classList.contains("open");
  const shouldOpen = mobile && open;
  const shell = document.querySelector(".app-shell");
  shell.inert = shouldOpen;
  if (
    !shouldOpen &&
    restoreFocus &&
    mobile &&
    (wasOpen || sidebar.contains(document.activeElement))
  ) {
    $("menu-button").focus({ preventScroll: true });
  }
  sidebar.classList.toggle("open", shouldOpen);
  sidebar.inert = mobile && !shouldOpen;
  if (sidebar.inert) sidebar.setAttribute("aria-hidden", "true");
  else sidebar.removeAttribute("aria-hidden");
  $("sidebar-backdrop").hidden = !shouldOpen;
  $("menu-button").setAttribute("aria-expanded", String(shouldOpen));
  document.body.classList.toggle("sidebar-open", shouldOpen);
  if (shouldOpen && !wasOpen) {
    $("sidebar-close").focus({ preventScroll: true });
  }
}
$("menu-button").innerHTML = icon("menu");
$("sidebar-close").innerHTML = icon("close");
$("menu-button").onclick = () =>
  setSidebar(!$("sidebar").classList.contains("open"));
$("sidebar-close").onclick = () => setSidebar(false);
$("sidebar-backdrop").onclick = () => setSidebar(false);
sidebarMedia.addEventListener("change", () => setSidebar(false));
document.addEventListener("keydown", (event) => {
  if (!sidebarMedia.matches || !$("sidebar").classList.contains("open")) return;
  if (event.key === "Escape") {
    event.preventDefault();
    setSidebar(false);
  } else if (event.key === "Tab") {
    const focusable = [
      ...$("sidebar").querySelectorAll(
        'a[href], button:not([disabled]), [tabindex="0"]',
      ),
    ].filter((el) => el.getClientRects().length);
    const first = focusable[0],
      last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }
});
setSidebar(false, { restoreFocus: false });
$("refresh-button").innerHTML = icon("refresh");
$("refresh-button").onclick = () =>
  Promise.all([
    refresh(!dirty),
    ...(page === "videos" ? [loadVideoLibrary()] : []),
  ])
    .then(() => toast("최신 상태를 불러왔습니다."))
    .catch((e) => toast(e.message));
$("persona-switch").onchange = async (event) => {
  if (
    dirty &&
    !confirm(
      "저장하지 않은 콘텐츠 수정이 있습니다. 작업 페르소나를 변경할까요?",
    )
  ) {
    event.target.value = state.studio.active_persona_id;
    renderNav();
    return;
  }
  dirty = false;
  await mutate(
    () =>
      api(
        "/api/personas/" + encodeURIComponent(event.target.value) + "/select",
        {},
      ),
    "작업 페르소나를 변경했습니다.",
  );
};
window.addEventListener("beforeunload", (event) => {
  if (dirty || dialogDirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});
window.addEventListener("hashchange", () => {
  const next = location.hash.slice(1);
  if (pages.some((p) => p[0] === next)) navigate(next);
});
refresh().catch((error) => {
  $("workspace").innerHTML =
    `<div class="initial-load-error"><h2>스튜디오에 연결하지 못했어요.</h2><p>${esc(error.message)}</p><button class="button" type="button" data-action="retry-connection">다시 연결하기</button></div>`;
  $("server-status").textContent = "연결 확인 필요";
});
setInterval(
  () =>
    refresh().catch(() => {
      $("server-status").textContent = "서버 연결 확인 필요";
    }),
  5000,
);

document.addEventListener("input", (event) => {
  if (event.target.id !== "video-library-search") return;
  videoLibrary.query = event.target.value;
  patchVideoLibrary();
});
window.addEventListener("focus", () => {
  if (page === "videos") loadVideoLibrary();
  if (page === "production") refresh().catch(() => {});
});
document.addEventListener("visibilitychange", () => {
  if (page === "videos" && !document.hidden) loadVideoLibrary();
  if (page === "production" && !document.hidden) refresh().catch(() => {});
});
setInterval(() => {
  if (page === "videos" && !document.hidden) loadVideoLibrary();
}, 3000);

/* Execution monitoring reads the saved run; opening this screen never starts work. */
function productionMonitorState() {
  const run = currentRun(), a = state?.automation || {};
  const active = Boolean(isActiveRun(run));
  const assignment = a.specialists?.current;
  const currentAssignment = assignment?.run_id === run?.id && assignment?.agent_id
    ? assignment : null;
  const stageLabel = run?.current_stage
    ? autoStageLabels[run.current_stage] || run.current_stage
    : run?.cycle_number ? "다음 콘텐츠 준비" : "첫 단계 대기";
  const workerLabel = { active: "작업자 연결됨", waiting: "작업자 연결 대기", stale: "작업자 응답 확인 필요", idle: "작업 종료" }[a.worker_status] || "연결 정보 확인 중";
  let tone = "pending", title = "아직 자동 제작을 시작하지 않았어요";
  let description = "페르소나와 콘텐츠 개수를 설정해 시작하면, 이 화면에서 전체 제작 과정과 결과를 확인할 수 있습니다.";
  if (run?.status === "running") {
    if (a.worker_status === "active") {
      tone = "running";
      title = "AI가 콘텐츠를 제작하고 있어요";
      description = "저장된 결과를 다음 전문가에게 전달하며 제작을 이어갑니다. 아래에서 현재 단계와 실제 산출물을 확인하세요.";
    } else if (a.worker_status === "stale") {
      tone = "uncertain";
      title = "작업자 응답을 확인하고 있어요";
      description = "마지막 연결 이후 새 응답을 받지 못했습니다. 저장된 결과와 외부 작업 상태를 확인한 뒤 이어집니다.";
    } else {
      const runtime = a.worker_runtime;
      const preparation = runtimePreparationView();
      title = preparation?.heading || "AI 작업자 연결을 확인해 주세요";
      description = preparation?.copy || runtime?.message || "로컬 서버의 제작 작업자 연결을 확인해 주세요.";
      if (preparation?.tone === "stale") tone = "uncertain";
    }
  } else if (run?.status === "scheduled") {
    title = "예약한 시작 시각을 기다리고 있어요";
    description = "예약 시각 이후 작업자가 연결되면 GS 소재 탐색부터 순서대로 제작합니다.";
  } else if (run?.status === "paused") {
    tone = "paused";
    title = "자동 제작을 잠시 멈췄어요";
    description = "새 작업을 시작하지 않습니다. 저장된 단계와 결과는 그대로 보관되며 재개하면 이어집니다.";
  } else if (run?.status === "blocked") {
    tone = "blocked";
    title = "확인이 필요한 작업이 있어요";
    description = "아래 사유와 단계 기록을 확인해 주세요. 불확실한 외부 작업은 결과를 확인한 뒤 재개할 수 있습니다.";
  } else if (run?.status === "stopped") {
    tone = "stopped";
    title = "자동 제작이 중지되었어요";
    description = "이 실행의 기록과 완성 콘텐츠가 보관되어 있습니다. 새로운 제작은 제작 설정에서 시작할 수 있습니다.";
  } else if (run?.status === "completed") {
    tone = "completed";
    title = "이번 자동 제작을 마쳤어요";
    description = "등록된 콘텐츠의 이미지·영상과 문안을 확인하고 최종 승인해 주세요.";
  } else if (run) {
    tone = run.status || "pending";
    title = "저장된 제작 상태를 확인해 주세요";
    description = "실행 기록과 단계별 결과를 아래에서 확인할 수 있습니다.";
  }
  const connection = typeof productionConnection === "undefined" ? {} : productionConnection;
  let compactTitle = run?.status === "running"
    ? a.worker_status === "active" ? "AI 제작 중" : a.worker_status === "stale" ? "AI 제작 확인 필요" : "AI 제작 대기"
    : { scheduled: "AI 제작 예약", paused: "AI 제작 일시정지", blocked: "AI 제작 확인 필요", stopped: "AI 제작 중지", completed: "AI 제작 완료" }[run?.status] || "제작 현황";
  if (connection.error) {
    tone = "uncertain";
    title = "상태 연결 확인 필요";
    compactTitle = "상태 연결 확인 필요";
    description = `서버에서 최신 상태를 받지 못했습니다. ${connection.lastUpdated ? `마지막 확인 ${date(connection.lastUpdated)}의 정보입니다. ` : ""}연결이 복구되면 최신 상태를 표시합니다.`;
  }
  return { run, active, tone, title, description, compactTitle, currentAssignment, stageLabel, workerLabel, offline: Boolean(connection.error) };
}

function productionMonitorTraces(run) {
  return autoArtifacts?.run_id === run?.id ? autoArtifacts.stages || [] : [];
}

function productionMonitorControls(run) {
  if (!isActiveRun(run)) return "";
  if (typeof productionConnection !== "undefined" && productionConnection.error) return '<span class="production-monitor-offline-control">연결 복구 후 실행을 제어할 수 있습니다.</span>';
  const uncertain = productionMonitorTraces(run).some((trace) => trace.status === "uncertain") || /불확실|중단된 작업 결과 확인/.test(run.pause_reason || "");
  const expired = Number.isFinite(Date.parse(run.end_at)) && Date.parse(run.end_at) <= Date.now();
  return `<div class="production-monitor-controls" aria-label="자동 제작 제어">${["scheduled", "running"].includes(run.status) ? button("일시정지", "run-pause", "", "pause") : ""}${["paused", "blocked"].includes(run.status) ? button("재개", "run-resume", "primary", "play", uncertain || expired ? `disabled title="${uncertain ? "결과가 불확실한 작업을 먼저 확인해 주세요." : "종료 시각이 지났습니다."}"` : "") : ""}${button("중지", "run-stop", "", "stop")}</div>`;
}

function productionMonitorWorkflow(run) {
  const a = state.automation || {}, traces = productionMonitorTraces(run);
  const cycleTraces = traces.filter((trace) => trace.cycle_number === run.cycle_number);
  const cycleId = cycleTraces[0]?.cycle_id;
  const frozenRoles = run.settings?.specialist_roles || run.settings?.specialist_pack?.roles || [];
  const assignments = (a.specialists?.assignments || []).filter((item) => item.run_id === run.id);
  const enabled = run.settings?.specialist_agents_enabled === true;
  const current = a.specialists?.current?.run_id === run.id ? a.specialists.current : null;
  const stages = a.stages?.length ? a.stages : Object.keys(autoStageLabels).map((key) => ({ key }));
  const online = typeof productionConnection === "undefined" || !productionConnection.error;
  const flowing = online && run.status === "running" && a.worker_status === "active";
  const currentIndex = stages.findIndex((stage) => stage.key === run.current_stage);
  const reachedIndex = run.status === "completed" ? stages.length - 1 : currentIndex;
  return `<ol class="production-workflow">${stages.map((stage, index) => {
    const trace = cycleTraces.find((item) => item.stage === stage.key);
    const role = frozenRoles.find((item) => item.stages?.includes(stage.key));
    const assignee = current?.stage === stage.key && current?.agent_id ? current : assignments
      .filter((item) => item.stage === stage.key && item.cycle_id === cycleId && item.agent_id)
      .sort((x, y) => (y.attempt || 0) - (x.attempt || 0) || (Date.parse(y.created_at) || 0) - (Date.parse(x.created_at) || 0))[0];
    const repaired = trace && ["pending", "running"].includes(trace.status) && assignee?.assignment_id !== current?.assignment_id;
    const actual = repaired ? null : assignee;
    const working = flowing && run.current_stage === stage.key;
    const reached = index < reachedIndex;
    const completed = trace?.status === "completed";
    const status = completed ? "completed" : ["failed", "uncertain"].includes(trace?.status) ? trace.status : working ? "running" : "pending";
    const statusText = completed ? "완료" : status === "failed" ? "실패" : status === "uncertain" ? "확인 필요" : working ? actual?.status === "assigned" ? "작업 중" : "단계 진행" : actual?.status === "assigned" && isActiveRun(run) ? "배정됨" : trace?.status === "running" ? "저장됨" : "대기";
    return `<li class="production-workflow-step ${working ? "is-current" : ""} ${completed ? "is-complete" : ""} ${reached ? "is-reached" : ""} ${reached && flowing ? "is-flowing" : ""}"><span class="production-workflow-number">${completed ? icon("check") : index + 1}</span><div class="production-workflow-copy"><div class="production-workflow-heading"><h3>${esc(autoStageLabels[stage.key] || stage.label || stage.key)}</h3>${badge(status, statusText)}</div><p>${esc(enabled ? actual?.role_name || role?.name || stage.specialist?.name || "전문가 배정 대기" : "AI 작업자")}${stage.key === "quality" && enabled ? '<span class="production-independent">독립 검수</span>' : ""}</p>${actual?.agent_id ? `<small class="production-assignee" title="${esc(actual.agent_id)}">${esc(actual.agent_id)}</small>` : ""}${trace ? `<button class="text-button" type="button" data-action="open-stage" data-cycle="${esc(trace.cycle_id)}" data-stage="${esc(stage.key)}">${completed ? "결과 확인" : "진행 기록"}${icon("arrow")}</button>` : ""}</div></li>`;
  }).join("")}</ol>`;
}

function productionMonitorEvidence(run) {
  const traces = productionMonitorTraces(run);
  const emptyRecords = `<div class="auto-evidence-empty">${icon("logs")}<h3>${autoArtifactsError ? "제작 기록을 불러오지 못했습니다" : "이 실행의 단계 결과를 기다리고 있어요"}</h3><p>${esc(autoArtifactsError || "각 단계가 진행되면 입력·판단 요약·문안·이미지·영상이 여기에 기록됩니다.")}</p></div>`;
  return `<section class="panel auto-evidence-panel production-monitor-evidence"><div class="auto-evidence-header"><div><h2>단계별 결과와 상세 기록</h2><p>이번 실행에 저장된 결과를 확인하고 원본 로그를 내려받으세요.</p></div>${button("기록 새로고침", "refresh-artifacts", "", "refresh")}</div><div class="auto-evidence-tabs tabs"><button type="button" class="tab ${autoEvidenceTab === "stages" ? "active" : ""}" data-action="auto-evidence-tab" data-tab="stages" aria-pressed="${autoEvidenceTab === "stages"}">단계별 결과</button><button type="button" class="tab ${autoEvidenceTab === "files" ? "active" : ""}" data-action="auto-evidence-tab" data-tab="files" aria-pressed="${autoEvidenceTab === "files"}">실행 로그 · 파일</button></div>${autoEvidenceTab === "files" ? renderArtifactFiles() : traces.length ? renderStageEvidence() : emptyRecords}</section>`;
}

function renderProductionMonitor() {
  const view = productionMonitorState(), { run } = view;
  if (!run) return `<div class="production-monitor"><div class="production-monitor-page-heading"><div><h1>제작 현황</h1><p>AI 자동 제작의 진행 상황을 한곳에서 확인하세요.</p></div>${button("제작 설정", "go-auto", "", "settings")}</div><section class="panel production-monitor-empty">${icon("spark")}<h2>${esc(view.title)}</h2><p>${esc(view.description)}</p>${button("제작 설정으로 이동", "go-auto", "primary", "create")}</section></div>`;
  const a = state.automation || {}, p = run.persona || {}, settings = run.settings || {};
  const knownName = personaName(p);
  const latest = [...allLogs.values()].filter((log) => log.run_id === run.id).sort((x, y) => y.id - x.id)[0];
  const traces = productionMonitorTraces(run), cycleTraces = traces.filter((trace) => trace.cycle_number === run.cycle_number);
  const activeStageKeys = new Set((a.stages || []).map((stage) => stage.key));
  const completedStages = cycleTraces.filter((trace) => trace.status === "completed" && activeStageKeys.has(trace.stage)).length;
  const mode = { images: "이미지 중심", video: "짧은 영상 중심", video_only: "영상만", mixed: "이미지 + 짧은 영상" }[settings.media_mode] || "저장된 미디어 설정";
  const specialist = view.currentAssignment;
  const liveSpecialist = !view.offline && run.status === "running" && a.worker_status === "active" && specialist?.status === "assigned" && specialist.stage === run.current_stage;
  const currentLabel = run.current_stage ? view.stageLabel : run.status === "running" ? view.stageLabel : "진행 중인 단계 없음";
  const personaReference = p.references?.mother?.url;
  const safeReference = typeof personaReference === "string" && personaReference.startsWith("/media/") && !personaReference.includes("..") ? personaReference : null;
  const quantity = Number.isInteger(settings.stop_after_posts) && settings.stop_after_posts > 0 ? `${settings.stop_after_posts}건` : "제한 없이";
  const coordinator = settings.specialist_pack?.coordinator?.name || "제작 총괄";
  const uncertainty = cycleTraces.some((trace) => trace.status === "uncertain");
  return `<div class="production-monitor"><div class="production-monitor-page-heading"><div><h1>제작 현황</h1><p>현재 실행의 작업 상태부터 완성 결과까지.</p></div>${button("제작 설정", "go-auto", "", "settings")}</div><section class="panel production-monitor-summary" data-status="${esc(view.tone)}"><div class="production-monitor-summary-top"><div class="production-monitor-status-heading">${badge(view.tone, view.offline ? "연결 확인" : run.status === "running" && a.worker_status !== "active" ? a.worker_status === "stale" ? "연결 확인" : "작업자 대기" : labels[run.status])}<h2>${esc(view.title)}</h2><p>${esc(view.description)}</p></div>${productionMonitorControls(run)}</div><div class="production-monitor-persona">${safeReference ? `<img src="${esc(safeReference)}" alt="이번 실행의 페르소나 기준 이미지">` : `<span class="production-monitor-persona-fallback">${icon("persona")}</span>`}<div><strong>${esc(knownName)}</strong><span>페르소나 v${esc(run.persona_version || p.version || "—")} · ${esc(mode)}</span></div><span class="production-monitor-mode">${settings.production_mode === "queued" ? "기획 요청 제작" : "AI 연속 제작"}</span></div>${run.pause_reason ? `<div class="production-monitor-reason">${icon("info")}<div><strong>${run.status === "completed" || run.status === "stopped" ? "종료 사유" : "확인할 내용"}</strong><p>${esc(run.pause_reason)}</p>${uncertainty ? '<small>불확실한 생성 결과를 확인해야 재개할 수 있습니다.</small>' : ""}</div></div>` : ""}<div class="production-monitor-context"><div><span>${view.active ? "현재 단계" : "마지막 단계"}</span><strong>${esc(currentLabel)}</strong><small>${liveSpecialist ? `${esc(specialist.role_name)} 작업 중` : view.offline ? "마지막 확인 상태" : view.active ? esc(view.workerLabel) : "실행 기록 보관 중"}</small></div><div><span>콘텐츠 등록 완료</span><strong>${Number(run.completed_count) || 0}<small>${quantity === "제한 없이" ? "건" : ` / ${esc(quantity)}`}</small></strong><small>${quantity === "제한 없이" ? "개수 제한 없음" : "목표 개수까지 자동 제작"}</small></div><div><span>${run.end_at ? "종료 시각 · 한국 시간" : "종료 조건"}</span><strong>${run.end_at ? date(run.end_at) : "시간 제한 없음"}</strong><small>${run.end_at ? "목표 개수 또는 종료 시각까지" : quantity !== "제한 없이" ? "목표 " + esc(quantity) + " 완료 시 종료" : "사용자 중지 또는 사용 한도까지"}</small></div></div></section><div class="production-monitor-grid"><section class="panel production-monitor-workflow"><div class="section-top"><div><h2>제작 흐름</h2><p>${run.cycle_number ? `${run.cycle_number}번째 콘텐츠 · ${completedStages} / ${(a.stages || []).length || 6}단계 완료` : view.active ? "첫 콘텐츠의 제작 준비 중" : "이 실행에 저장된 제작 단계가 없습니다"}</p></div><span class="production-monitor-coordinator">${icon("persona")}${esc(coordinator)}</span></div>${productionMonitorWorkflow(run)}<p class="production-monitor-loop">${icon("refresh")}${view.active ? "피드 등록이 끝나면 설정된 목표까지 다음 콘텐츠를 만듭니다." : "단계 기록은 실행이 끝난 뒤에도 확인할 수 있습니다."}</p></section><aside class="production-monitor-sidebar"><section class="panel production-monitor-facts"><h2>이번 실행 정보</h2><dl><div><dt>시작 시각</dt><dd>${date(run.start_at)}</dd></div><div><dt>목표 콘텐츠</dt><dd>${esc(quantity)}</dd></div><div><dt>제작 방식</dt><dd>${esc(mode)}</dd></div><div><dt>전문가 위임</dt><dd>${settings.specialist_agents_enabled === true ? "역할별 전문 에이전트" : "이 실행에서 사용 안 함"}</dd></div><div><dt>실패 기록</dt><dd class="${run.failed_count ? "production-failure-count" : ""}">${Number(run.failed_count) || 0}건</dd></div><div><dt>마지막 작업자 연결</dt><dd>${date(a.worker_last_seen_at || run.last_heartbeat_at)}</dd></div><div><dt>상태 저장 시각</dt><dd>${date(run.updated_at)}</dd></div></dl><p class="production-monitor-run-id">실행 ID<span>${esc(run.id)}</span></p></section><section class="panel production-monitor-latest"><h2>최근 기록</h2>${latest ? `<time datetime="${esc(latest.created_at)}">${date(latest.created_at)}</time><p>${esc(latest.message || latest.event || "실행 기록이 저장되었습니다.")}</p>${latest.stage ? `<span class="tag">${esc(autoStageLabels[latest.stage] || latest.stage)}</span>` : ""}` : '<p>작업자가 기록을 남기면 이곳에 표시됩니다.</p>'}<button class="text-button" type="button" data-action="production-show-logs">상세 로그 보기${icon("arrow")}</button></section><div class="production-monitor-approval">${icon("review")}<div><strong>게시 전에는 사람의 승인이 필요해요.</strong><p>제작 완료 후 검수 대기에 등록됩니다. 승인 대기 중에도 다음 제작은 계속됩니다.</p><button type="button" class="text-button" data-nav="review">검수 & 승인${icon("arrow")}</button></div></div></aside></div>${productionMonitorEvidence(run)}</div>`;
}
