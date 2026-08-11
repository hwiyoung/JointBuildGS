const CONDITIONS = ['E1', 'E2', 'E3', 'E4', 'E5', 'E6'];
const CONDITION_NAMES = {
  E1: 'E1 UAS',
  E2: 'E2 MVS',
  E3: 'E3 GS',
  E4: 'E4 ALS',
  E5: 'E5 conflict',
  E6: 'E6 LoD diag',
};
const PANEL_STATS = {
  E1: 'lidarStats',
  E2: 'mvsStats',
  E3: 'c3Stats',
  E4: 'e4Stats',
  E5: 'e5Stats',
  E6: 'e6Stats',
};
const REASON_LABELS = {
  G0_OUTPUT_MISSING: 'LoD2 출력 없음',
  G1_CITYJSON_CONTRACT_FAILED: 'CityJSON/semantic 계약 실패',
  G2_VAL3DITY_FAILED: '3D geometry validity 실패',
  G3_REFERENCE_MISSING: '구조 reference 없음',
  G3_COMPLETENESS_LOW: '지붕면 completeness 부족',
  G3_CORRECTNESS_LOW: '지붕면 correctness 부족',
  G3_QUALITY_LOW: '지붕면 quality 부족',
  G3_PLANE_RECALL_LOW: 'reference 주요 지붕면 재현 부족',
  G3_PLANE_PRECISION_LOW: '불필요한 주요 지붕면 생성',
  G3_MAJOR_PLANE_MISMATCH: '주요 지붕면 개수 불일치',
  G4_REFERENCE_MISSING: '기하 reference 없음',
  G4_COVERAGE_LOW: '지붕 coverage 부족',
  G4_RMSZ_HIGH: 'RMSZ 초과',
  G4_P95_HIGH: 'P95 높이오차 초과',
  G4_BIAS_HIGH: '높이 bias 초과',
};

let thresholdKey = new URLSearchParams(window.location.search).get('threshold') || 'O50';
if (!['O50', 'O60', 'O70', 'O80'].includes(thresholdKey)) thresholdKey = 'O50';

const manifest = await fetch('./viewer_manifest.json', { cache: 'no-store' }).then((response) => {
  if (!response.ok) throw new Error(`viewer_manifest.json: ${response.status}`);
  return response.json();
});

function conditionSpec(building, condition) {
  if (condition === 'E1') return building.lidar;
  if (condition === 'E2') return building.mvs;
  return building.conditions[condition];
}

function currentBuilding() {
  const select = document.getElementById('buildingSelect');
  return manifest.buildings[Number(select.value) || 0];
}

function formatNumber(value, digits = 2) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '-';
}

function verdictClass(verdict) {
  return verdict === 'O' ? 'is-o' : verdict === 'X' ? 'is-x' : 'is-na';
}

function gateText(result) {
  return ['G0', 'G1', 'G2', 'G3', 'G4']
    .map((gate) => `${gate} ${result.gates?.[gate] ?? '-'}`)
    .join(' · ');
}

function reasonText(result) {
  if (result.verdict === 'O') return '전체 gate 통과';
  if (result.verdict === 'NA') return '평가 reference 없음';
  const reason = (result.failure_reasons || [])[0];
  return REASON_LABELS[reason] || reason || 'gate 실패';
}

function metricText(result) {
  const g3 = result.g3 || {};
  const g4 = result.g4 || {};
  return `support C/P/Q ${formatNumber(g3.area_completeness)}/${formatNumber(g3.area_correctness)}/${formatNumber(g3.area_quality)} · plane R/P ${formatNumber(g3.plane_area_recall)}/${formatNumber(g3.plane_area_precision)} · RMSZ ${formatNumber(g4.rmse_z_m)}m`;
}

function ensureUi() {
  if (document.getElementById('autoOxBar')) return;
  const bar = document.createElement('section');
  bar.id = 'autoOxBar';
  bar.setAttribute('aria-label', 'Reference-based Roofer automatic O/X');
  bar.innerHTML = `
    <div class="auto-ox-controls">
      <strong>Roofer LoD2 자동 O/X</strong>
      ${['O50', 'O60', 'O70', 'O80'].map((key) => `<button type="button" class="auto-ox-threshold" data-auto-threshold="${key}" aria-pressed="false">${key}</button>`).join('')}
      <span class="status" id="autoOxCriterion">불러오는 중</span>
    </div>
    <div id="autoOxConditions"></div>`;
  const lineage = document.querySelector('.lineage-warning');
  lineage.insertAdjacentElement('afterend', bar);
  lineage.innerHTML = '<strong>Reference 기반 자동 이분 판정:</strong> 출력 없음은 X, 평가 reference 자체가 없을 때만 NA입니다. O50이 primary development criterion이고 O60/O70/O80은 sensitivity입니다. E6는 similarity diagnostic이며 독립 성능 주장에 사용하지 않습니다. official_PASS_usable과 scientific_verdict는 null입니다.';
  bar.querySelectorAll('[data-auto-threshold]').forEach((button) => {
    button.addEventListener('click', () => {
      thresholdKey = button.dataset.autoThreshold;
      const url = new URL(window.location.href);
      url.searchParams.set('threshold', thresholdKey);
      history.replaceState(null, '', url);
      render();
    });
  });
}

function renderPanel(condition, result) {
  const stats = document.getElementById(PANEL_STATS[condition]);
  if (!stats) return;
  stats.classList.remove('auto-o', 'auto-x', 'auto-review', 'auto-reference-o', 'auto-reference-x', 'auto-reference-na');
  stats.classList.add(result.verdict === 'O' ? 'auto-reference-o' : result.verdict === 'X' ? 'auto-reference-x' : 'auto-reference-na');
  stats.textContent = `${gateText(result)} · ${reasonText(result)} · ${metricText(result)}`;
}

function render() {
  ensureUi();
  const building = currentBuilding();
  document.querySelectorAll('[data-auto-threshold]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.autoThreshold === thresholdKey));
  });
  const criterion = manifest.reference_auto_ox_contract;
  document.getElementById('autoOxCriterion').textContent = `${building.stable_id} · ${thresholdKey} · major-plane overlap ${thresholdKey.slice(1)}% · normal ≤ ${criterion.normal_tolerance_deg}° · G4 UAS→LoD2 fallback`;
  const container = document.getElementById('autoOxConditions');
  container.replaceChildren();
  for (const condition of CONDITIONS) {
    const spec = conditionSpec(building, condition);
    const result = spec.reference_auto_ox?.sensitivity?.[thresholdKey] || { verdict: 'NA', gates: {} };
    const item = document.createElement('article');
    item.className = `auto-ox-condition ${verdictClass(result.verdict)}`;
    item.innerHTML = `
      <div class="auto-ox-head"><strong>${CONDITION_NAMES[condition]}</strong><span class="auto-ox-verdict">${result.verdict}</span></div>
      <div class="auto-ox-gates">${gateText(result)}</div>
      <div class="auto-ox-reason">${reasonText(result)}</div>
      <div class="auto-ox-metrics">${metricText(result)}</div>`;
    container.appendChild(item);
    renderPanel(condition, result);
  }
}

ensureUi();
document.getElementById('buildingSelect').addEventListener('change', () => queueMicrotask(render));
const message = document.getElementById('message');
new MutationObserver(() => queueMicrotask(render)).observe(message, { childList: true, characterData: true, subtree: true });
render();
