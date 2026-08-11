const REVIEWER_ID = new URLSearchParams(window.location.search).get('reviewer') || 'R1';
const STORAGE_KEY = `jointbuildgs-e1-e6-roofer-ox-v4-${REVIEWER_ID}`;
const BLIND_SEED = 'JBGS_E2_BASELINE_BLIND_V1';
const PRIMARY_METHODS = ['mvs', 'c3', 'e4', 'e5'];
const LABELS = { mvs: 'E2 product baseline', c3: 'E3 GS-only', e4: 'E4 ALS unweighted', e5: 'E5 conflict-aware' };
const METHOD_VIEWPORTS = { mvs: 'mvsViewport', c3: 'c3Viewport', e4: 'e4Viewport', e5: 'e5Viewport' };
let viewerMode = 'BLIND';

const manifest = await fetch('./viewer_manifest.json', { cache: 'no-store' }).then((response) => {
  if (!response.ok) throw new Error(`viewer_manifest.json: ${response.status}`);
  return response.json();
});

function readReviews() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
  catch { return {}; }
}
function currentBuilding() {
  const select = document.getElementById('buildingSelect');
  return manifest.buildings[Number(select.value) || 0];
}
function reviewFor(building) { return readReviews()[building.stable_id] || {}; }
function conditionSpec(building, method) {
  if (method === 'mvs') return building.mvs;
  if (method === 'c3') return building.conditions.E3;
  return building.conditions[method.toUpperCase()];
}
function automaticState(building, method) {
  const spec = conditionSpec(building, method);
  const dev = spec.development_g3_g4 || {};
  if (dev.assessment_status === 'NOT_ASSESSED_AOI') return 'NA';
  if (dev.overall_candidate === 'O_CANDIDATE') return 'O*';
  if (dev.overall_candidate === 'X_CANDIDATE') return 'X*';
  if (dev.overall_candidate === 'REVIEW') return 'REVIEW';
  if (dev.overall_candidate === 'NOT_ASSESSED') return 'NA';
  return '?';
}
function deriveTransition(base, method) {
  if (!base || !method) return { label: '판정 대기', className: 'pending' };
  if (base === 'X' && method === 'O') return { label: 'RESCUE', className: 'rescue' };
  if (base === 'X' && method === 'X') return { label: 'rescue 실패', className: 'failed' };
  if (base === 'O' && method === 'O') return { label: '성공 유지', className: 'maintained' };
  if (base === 'O' && method === 'X') return { label: 'REGRESSION', className: 'regression' };
  return { label: '판정 대기', className: 'pending' };
}
function priorIncrement(baseE3, method) {
  if (!baseE3 || !method) return 'E3 비교 대기';
  if (baseE3 === 'X' && method === 'O') return 'prior incremental rescue';
  if (baseE3 === 'O' && method === 'O') return 'GS 성공 유지';
  if (baseE3 === 'O' && method === 'X') return 'prior 추가 후 악화';
  return 'prior incremental 없음';
}

function blindPermutation(stableId) {
  let value = 2166136261;
  for (const char of `${BLIND_SEED}:${stableId}`) {
    value ^= char.charCodeAt(0);
    value = Math.imul(value, 16777619) >>> 0;
  }
  const methods = [...PRIMARY_METHODS];
  for (let index = methods.length - 1; index > 0; index -= 1) {
    value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
    const selected = value % (index + 1);
    [methods[index], methods[selected]] = [methods[selected], methods[index]];
  }
  return methods;
}

function identifyReviewFields() {
  const ids = { lidarReview: 'lidar', mvsReview: 'mvs', c3Review: 'c3', e4Review: 'e4', e5Review: 'e5', e6Review: 'e6', reviewNote: 'note' };
  document.querySelectorAll('#reviewbar .review-field').forEach((field) => {
    const match = Object.entries(ids).find(([id]) => field.querySelector(`#${id}`));
    if (!match) return;
    const method = match[1];
    field.dataset.judgeMethod = method;
    field.dataset.originalLabel = field.querySelector('label')?.textContent || '';
    field.classList.add(PRIMARY_METHODS.includes(method) ? 'judge-primary' : 'judge-secondary');
    if (!PRIMARY_METHODS.includes(method)) return;
    field.tabIndex = 0;
    const hint = document.createElement('span');
    hint.className = 'judge-shortcut';
    hint.textContent = `${LABELS[method]} · O/X 키 · C 지우기`;
    field.appendChild(hint);
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'judge-clear';
    clear.dataset.clearMethod = method;
    clear.textContent = '보류/지우기';
    field.querySelector('.review-buttons')?.appendChild(clear);
  });
}
function classifyPanels() {
  const definitions = [
    ['lidarViewport', 'judge-reference', 1], ['priorLod2Viewport', 'judge-reference', 2],
    ['mvsViewport', 'judge-method', 3], ['c3Viewport', 'judge-method', 4],
    ['e4Viewport', 'judge-method', 5], ['e5Viewport', 'judge-method', 6],
    ['e6Viewport', 'judge-secondary-panel', 7], ['priorAlsViewport', 'judge-secondary-panel', 8],
  ];
  for (const [id, className, order] of definitions) {
    const shell = document.getElementById(id)?.closest('.viewport-shell');
    if (!shell) continue;
    shell.classList.add(className);
    shell.style.order = String(order);
    const label = shell.querySelector('.panel-label');
    if (label) label.dataset.originalLabel = label.textContent;
  }
}
function workflowNode() {
  const node = document.createElement('section');
  node.id = 'adjudicationWorkflow';
  node.innerHTML = `
    <div class="judge-mode">
      <div class="judge-mode-buttons">
        <button id="judgeBlindMode" type="button" aria-pressed="true">Blind 임계값 판정</button>
        <button id="judgeTransitionMode" type="button" aria-pressed="false">전이 확인</button>
      </div>
      <label>Reviewer
        <select id="judgeReviewer"><option value="R1">R1</option><option value="R2">R2</option></select>
      </label>
    </div>
    <div class="judge-baseline">
      <strong>E2 기존 image-based LoD2</strong><span id="judgeBaselineState" class="is-empty">미평가</span>
      <small id="judgeBaselineAuto">자동 후보 확인 중</small><small id="judgeBuildingId">-</small>
    </div>
    <div class="judge-transitions">
      <div id="judgeE3Transition" class="judge-transition pending"><span>E2 → E3</span><strong>판정 대기</strong><small>GS-only 효과</small></div>
      <div id="judgeE4Transition" class="judge-transition pending"><span>E2 → E4</span><strong>판정 대기</strong><small>E3 비교 대기</small></div>
      <div id="judgeE5Transition" class="judge-transition pending"><span>E2 → E5 · PRIMARY</span><strong>판정 대기</strong><small>E3 비교 대기</small></div>
    </div>
    <div class="judge-queue">
      <label for="judgeQueueFilter">다음 건물 기준</label>
      <select id="judgeQueueFilter">
        <option value="UNREVIEWED">E2–E5 미완료</option>
        <option value="E2_AUTO_X">E2 자동 X*/NA 우선</option>
        <option value="E2_AUTO_O">E2 자동 O* 우선</option>
        <option value="AUTO_REVIEW">E2 자동 REVIEW/NA</option>
        <option value="ALL">전체 순서</option>
      </select>
      <button id="judgeNext" type="button">다음 해당 건물</button>
      <span id="judgeProgress" class="judge-progress">진행률 계산 중</span>
    </div>`;
  return node;
}
function updateTransition(id, transition, note) {
  const node = document.getElementById(id);
  node.className = `judge-transition ${transition.className}`;
  node.querySelector('strong').textContent = transition.label;
  if (note) node.querySelector('small').textContent = note;
}
function updateWorkflow() {
  const building = currentBuilding();
  if (!building) return;
  const review = reviewFor(building);
  const baseline = document.getElementById('judgeBaselineState');
  baseline.textContent = review.mvs || '미평가';
  baseline.className = review.mvs === 'O' ? 'is-o' : review.mvs === 'X' ? 'is-x' : 'is-empty';
  document.getElementById('judgeBaselineAuto').textContent = `자동 ${automaticState(building, 'mvs')} · Roofer primary`;
  document.getElementById('judgeBuildingId').textContent = `${building.population_index}/199 · ${building.stable_id}`;
  updateTransition('judgeE3Transition', deriveTransition(review.mvs, review.c3), 'GS-only 효과');
  updateTransition('judgeE4Transition', deriveTransition(review.mvs, review.e4), priorIncrement(review.c3, review.e4));
  updateTransition('judgeE5Transition', deriveTransition(review.mvs, review.e5), priorIncrement(review.c3, review.e5));
  const reviews = readReviews();
  const completed = manifest.buildings.filter((item) => {
    const row = reviews[item.stable_id] || {};
    return PRIMARY_METHODS.every((method) => ['O', 'X'].includes(row[method]));
  }).length;
  document.getElementById('judgeProgress').textContent = `E2–E5 완료 ${completed}/${manifest.buildings.length}`;
  applyMode();
}

function applyMode() {
  const building = currentBuilding();
  if (!building) return;
  const blind = viewerMode === 'BLIND';
  document.body.classList.toggle('blind-mode', blind);
  document.getElementById('judgeBlindMode').setAttribute('aria-pressed', String(blind));
  document.getElementById('judgeTransitionMode').setAttribute('aria-pressed', String(!blind));
  document.querySelector('.judge-baseline').hidden = blind;
  document.querySelector('.judge-transitions').hidden = blind;
  const warning = document.querySelector('.lineage-warning');
  if (warning) {
    if (!warning.dataset.originalText) warning.dataset.originalText = warning.textContent;
    warning.textContent = blind
      ? 'Blind threshold-development mode · 결과 A–D의 실제 condition과 자동 G3/G4 후보는 숨김 · 사람 O/X는 threshold 개발용이며 공식 PASS가 아님'
      : warning.dataset.originalText;
  }
  const permutation = blindPermutation(building.stable_id);
  permutation.forEach((method, index) => {
    const code = String.fromCharCode(65 + index);
    const field = document.querySelector(`#reviewbar .review-field[data-judge-method="${method}"]`);
    const shell = document.getElementById(METHOD_VIEWPORTS[method])?.closest('.viewport-shell');
    if (field) {
      field.style.order = blind ? String(index + 1) : String(PRIMARY_METHODS.indexOf(method) + 1);
      const label = field.querySelector('label');
      if (label) label.textContent = blind ? `결과 ${code} · Roofer 사람 O/X` : field.dataset.originalLabel;
      const hint = field.querySelector('.judge-shortcut');
      if (hint) hint.textContent = blind ? `결과 ${code} · O/X 키 · C 지우기` : `${LABELS[method]} · O/X 키 · C 지우기`;
    }
    if (shell) {
      shell.style.order = blind ? String(index + 3) : String(PRIMARY_METHODS.indexOf(method) + 3);
      const label = shell.querySelector('.panel-label');
      if (label) label.textContent = blind ? `결과 ${code} · Roofer output` : label.dataset.originalLabel;
    }
  });
  document.querySelectorAll('#viewports .panel-stats').forEach((stats) => { stats.style.display = blind ? 'none' : 'block'; });
  document.getElementById('judgeQueueFilter').disabled = blind;
}
function queueMatch(building, filter) {
  const review = reviewFor(building);
  const auto = automaticState(building, 'mvs');
  if (filter === 'UNREVIEWED') return PRIMARY_METHODS.some((method) => !['O', 'X'].includes(review[method]));
  if (filter === 'E2_AUTO_X') return auto === 'X*' || auto === 'NA';
  if (filter === 'E2_AUTO_O') return auto === 'O*';
  if (filter === 'AUTO_REVIEW') return auto === 'REVIEW' || auto === 'NA';
  return true;
}
function goToNextQueueBuilding() {
  const select = document.getElementById('buildingSelect');
  const start = Number(select.value) || 0;
  const filter = document.getElementById('judgeQueueFilter').value;
  for (let offset = 1; offset <= manifest.buildings.length; offset += 1) {
    const index = (start + offset) % manifest.buildings.length;
    if (!queueMatch(manifest.buildings[index], filter)) continue;
    select.value = String(index);
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return;
  }
}
function clearReview(method) {
  const selected = ['O', 'X'].find((value) => document.getElementById(`${method}Review${value}`)?.getAttribute('aria-pressed') === 'true');
  if (selected) document.getElementById(`${method}Review${selected}`).click();
}
function activeMethod() {
  return document.activeElement?.closest?.('.review-field')?.dataset.judgeMethod || 'mvs';
}
function installUi() {
  identifyReviewFields();
  classifyPanels();
  document.getElementById('topbar').after(workflowNode());
  document.getElementById('judgeReviewer').value = REVIEWER_ID;
  document.getElementById('judgeReviewer').addEventListener('change', (event) => {
    const url = new URL(window.location.href);
    url.searchParams.set('reviewer', event.target.value);
    window.location.href = url.toString();
  });
  document.getElementById('judgeBlindMode').addEventListener('click', () => { viewerMode = 'BLIND'; applyMode(); });
  document.getElementById('judgeTransitionMode').addEventListener('click', () => { viewerMode = 'TRANSITION'; applyMode(); });
  const more = document.createElement('button');
  more.id = 'judgeMore'; more.type = 'button'; more.textContent = 'E1/E6/메모 펼치기';
  document.getElementById('reviewbar').appendChild(more);
  more.addEventListener('click', () => {
    const grid = document.getElementById('viewports');
    grid.classList.toggle('show-secondary');
    document.querySelectorAll('#reviewbar .judge-secondary').forEach((field) => { field.style.display = grid.classList.contains('show-secondary') ? 'grid' : 'none'; });
    more.textContent = grid.classList.contains('show-secondary') ? '보조 항목 접기' : 'E1/E6/메모 펼치기';
  });
  document.getElementById('judgeNext').addEventListener('click', goToNextQueueBuilding);
  document.querySelectorAll('[data-clear-method]').forEach((button) => button.addEventListener('click', () => clearReview(button.dataset.clearMethod)));
  document.getElementById('buildingSelect').addEventListener('change', () => setTimeout(updateWorkflow, 0));
  new MutationObserver(() => setTimeout(updateWorkflow, 0)).observe(document.getElementById('message'), { childList: true, characterData: true, subtree: true });
  document.getElementById('reviewbar').addEventListener('click', () => setTimeout(updateWorkflow, 0));
  document.getElementById('reviewbar').addEventListener('input', () => setTimeout(updateWorkflow, 0));
  window.addEventListener('keydown', (event) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
    const method = activeMethod();
    if (!PRIMARY_METHODS.includes(method)) return;
    if (event.key.toLowerCase() === 'o') document.getElementById(`${method}ReviewO`).click();
    if (event.key.toLowerCase() === 'x') document.getElementById(`${method}ReviewX`).click();
    if (event.key.toLowerCase() === 'c') clearReview(method);
    if (event.key.toLowerCase() === 'n') goToNextQueueBuilding();
  });
  setTimeout(updateWorkflow, 0);
}
function waitForBaseViewer() {
  const select = document.getElementById('buildingSelect');
  if (select.options.length === manifest.buildings.length) { installUi(); return; }
  const observer = new MutationObserver(() => {
    if (select.options.length !== manifest.buildings.length) return;
    observer.disconnect(); installUi();
  });
  observer.observe(select, { childList: true });
}
waitForBaseViewer();
