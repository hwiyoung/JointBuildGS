"use strict";

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[ch]));
const finite = value => typeof value === "number" && Number.isFinite(value);
const fmt = (value, places = 4) => finite(value) ? value.toFixed(places) : "미정의";
const names = {prior:"Prior · 기존 ALS", da3:"DA3 · 영상 depth", mvs:"MVS · 영상 depth"};
const strata = {low_disagreement:"두 depth가 가까운 위치", high_disagreement:"두 depth 차이가 큰 위치", prior_hole:"Prior 결손 위치", mvs_hole:"MVS 결손 위치"};
const readings = {INSUFFICIENT_SUPPORT:"요건을 충족한 사진이 부족함", PHOTO_COST_PREFERS_PRIOR:"관측 비용이 Prior 쪽으로 일관됨", PHOTO_COST_PREFERS_IMAGE:"관측 비용이 영상 source 쪽으로 일관됨", PHOTO_COST_CLOSE:"두 source의 관측 비용이 가까움", VIEW_DEPENDENT_OR_CLOSE:"사진별 방향이 다르거나 비용이 가까움", PATCH_SIZE_DEPENDENT:"패치 크기에 따라 관측 해석이 달라짐"};
let manifest, current, currentIndex = 0, neighborIndex = 0, loadToken = 0;
let referenceEvaluation = null, referenceLoadError = null;
const caseCache = new Map();
const caseErrors = new Map();

function asset(value) {
  if (!value) return null;
  const path = String(value).replace(/^\.\//, "");
  if (/^(?:[a-z]+:|\/|\\)/i.test(path) || path.split("/").includes("..")) return null;
  return path.startsWith("assets/diagnostic/") ? path : "assets/diagnostic/" + path;
}
const pairKey = () => $("#pair-select").value;
const imageKey = () => pairKey() === "prior_mvs" ? "mvs" : "da3";
const patchKey = () => $("#patch-select").value;
const totalPixels = () => Number(patchKey()) ** 2;
const caseLabel = item => {
  const id = item.case_id || "";
  return (item.region || id.split("_")[0]) + " · " + (strata[id.replace(/^[^_]+_/, "")] || item.label || id);
};
const patchFor = row => row?.patches?.[patchKey()] || {};
const comparisonFor = row => patchFor(row).comparisons?.[pairKey()] || {};
const scoreFor = (comparison, method, source) => comparison?.[method]?.[source] || {};
const summaryFor = (item, size = patchKey()) => item?.summary?.[pairKey()]?.[size] || {};
const countText = value => Number.isInteger(value) ? String(value) : "미기록";

function figure(url, title, kind = "context") {
  const path = asset(url);
  if (!path) return '<figure class="' + kind + '"><div class="empty">자료 없음 · 결손 또는 미지원<br>수치 0을 뜻하지 않습니다.</div><figcaption>' + esc(title) + '</figcaption></figure>';
  return '<figure class="' + kind + '"><button type="button" class="image-button" data-image="' + esc(path) + '" data-caption="' + esc(title) + '" aria-label="' + esc(title) + ' 확대"><img src="' + esc(path) + '" alt="' + esc(title) + '"></button><figcaption>' + esc(title) + '</figcaption></figure>';
}
function metric(value, label) {
  return '<div class="metric"><span class="value">' + esc(value) + '</span><span class="label">' + esc(label) + '</span></div>';
}
function deltaCell(value) {
  const sign = !finite(value) || value === 0 ? "tie" : value > 0 ? "prior" : "image";
  return '<span class="delta-' + sign + '">' + (finite(value) && value > 0 ? "+" : "") + fmt(value) + '</span>';
}
function scoreStatus(score) {
  if (finite(score.cost)) return "계산됨";
  const code = String(score.status || "");
  if (/FLAT|TEXTURE|VARIANCE/i.test(code)) return "밝기 변화 부족";
  if (/INSUFFICIENT|COMMON|SUPPORT/i.test(code)) return "공통 표본 부족";
  if (/MISSING|INVALID|UNAVAILABLE|NO_DEPTH/i.test(code)) return "입력 또는 투영 미지원";
  return code || "비용 미정의";
}
function eligibilityText(comparison) {
  const eligible = comparison.eligibility || {};
  const reasons = Array.isArray(eligible.reasons) ? eligible.reasons : [];
  const translated = reasons.map(reason => {
    const key = String(reason);
    if (/count|pixel|support|fraction|coverage/i.test(key)) return "공통 표본 요건 미충족 (" + key + ")";
    if (/texture|std|flat|variance/i.test(key)) return "밝기 변화 요건 미충족 (" + key + ")";
    if (/normal|plane/i.test(key)) return "normal 또는 평면 계산 미지원 (" + key + ")";
    return key;
  });
  if (eligible.usable === true) return {label:"수치 요건 충족", note:"공통 표본과 밝기 변화의 진단 요건을 충족했습니다. 실제 가시성이나 정답을 확인한 상태는 아닙니다.", cls:""};
  return {label:eligible.usable === false ? "수치 요건 미충족" : "요건 판정 미기록", note:translated.join(" / ") || "유효 표본과 각 패치의 밝기 변화를 함께 확인하세요.", cls:" unsupported"};
}
function descriptiveReading(summary) {
  if (!summary) return "집계 자료가 없습니다.";
  const p = summary.prior_lower_views, i = summary.image_lower_views, n = summary.eligible_views;
  const margin = manifest.config?.diagnostic_gates?.cost_margin ?? 0.02;
  if (n === 0) return "수치 요건을 충족한 사진이 없어 상대 비용을 집계하지 않습니다.";
  if (Number.isInteger(p) && Number.isInteger(i) && Number.isInteger(n)) {
    return "요건 충족 사진에서 " + margin + " 초과 비용 차이: Prior가 작음 " + p + "장 / " + imageKey().toUpperCase() + "가 작음 " + i + "장 / 차이 " + margin + " 이내 " + Math.max(0, n - p - i) + "장.";
  }
  return typeof summary.reading === "string" ? summary.reading : "표본과 사진별 비용을 확인하세요.";
}
function methodCard(summary = {}, method) {
  const title = method === "raw" ? "원 depth 투영" : "Depth·normal 평면 투영";
  return '<div class="method-card ' + method + '"><h3>' + title + '</h3><div class="metrics">' +
    metric(fmt(summary.median_prior_cost), "Prior 비용 중앙값") +
    metric(fmt(summary.median_image_cost), imageKey().toUpperCase() + " 비용 중앙값") +
    '</div><p>대응 비용차 중앙값 (영상 − Prior): <strong>' + deltaCell(summary.median_delta_image_minus_prior) + '</strong></p>' +
    '<p>비용 쌍 계산 <strong>' + countText(summary.paired_views) + '</strong>장 · 수치 요건 충족 <strong>' + countText(summary.eligible_views) + '</strong>장 / 선정 이웃 ' + (current.neighbors?.length || 0) + '장</p><p><strong>' + esc(readings[summary.reading] || summary.reading || "요약 미기록") + '</strong></p><p>' + esc(descriptiveReading(summary)) + '</p></div>';
}
function gateGuide() {
  const gates = manifest.config?.diagnostic_gates || {};
  return '<details class="inner"><summary>이번 진단에서 사용한 수치 요건</summary><p>공통 표본이 패치의 ' + esc(100 * (gates.minimum_fraction ?? 0.8)) + '% 이상이고, 네 비용이 정의되며, 기준·투영 패치 grayscale 표준편차가 각각 ' + esc(gates.texture_std ?? 0.02) + ' 이상인 사진을 집계합니다.</p><p>집계 가능한 사진 ' + esc(gates.minimum_views ?? 2) + '장 이상 중 ' + esc(100 * (gates.consistent_fraction ?? 0.75)) + '% 이상이 ' + esc(gates.cost_margin ?? 0.02) + ' 초과 비용 차이로 같은 쪽을 지지하면 “관측 비용이 일관됨”으로 표시합니다. 이는 미리 정한 진단용 요건이며 가중치 결정 문턱이나 정확성 인증 기준이 아닙니다.</p></details>';
}
function normalTable() {
  let html = '<div class="table-wrap"><table id="normal-table"><thead><tr><th>Source</th><th>중심 depth (m)</th><th>Camera 좌표 normal (x, y, z)</th><th>추정 표본 / 81</th><th>원 해상도 조회 위치 수</th><th>평면 fit RMS (m)</th><th>중심 고정 RMS (m)</th><th>평면성 비율</th></tr></thead><tbody>';
  for (const key of ["prior", "da3", "mvs"]) {
    const n = current.normal_sources?.[key] || {};
    const vector = Array.isArray(n.normal_camera) ? n.normal_camera.map(v => fmt(v, 4)).join(", ") : "미정의";
    html += '<tr><td>' + esc(names[key]) + '<span class="normal-status">' + esc(n.status || "미기록") + '</span></td><td class="num">' + fmt(n.center_depth_m, 3) + '</td><td class="normal-vector">' + esc(vector) + '</td><td class="num">' + countText(n.fit_count) + '</td><td class="num">' + countText(n.unique_native_queries) + '</td><td class="num">' + fmt(n.fit_rms_m, 5) + '</td><td class="num">' + fmt(n.anchored_rms_m, 5) + '</td><td class="num">' + fmt(n.planarity_ratio, 6) + '</td></tr>';
  }
  return html + '</tbody></table></div><p class="hint">Normal은 해당 source의 depth에서 계산한 표면 방향입니다. fit RMS는 주변 depth가 추정 평면에서 벗어난 정도이고, 중심 고정 RMS는 원 중심 depth를 지나는 평면에서 벗어난 정도입니다. 둘 다 GT 오차가 아닙니다. 평면성 비율은 작은 특이값 / 중간 특이값으로, 작을수록 추정점이 평면에 모여 있다는 뜻입니다. 낮은 원 해상도 source를 여러 번 조회했다면 81개 표본이 81개의 독립 측정을 뜻하지 않습니다.</p>' + figure(current.normal_geometry_url, "Source별 원 depth·중심 고정 평면·중심 행 단면 · GT 미사용");
}
function scoreCaption(comparison, method, source) {
  const score = scoreFor(comparison, method, source);
  return '<div class="score-caption"><strong>비용 ' + fmt(score.cost) + '</strong> · ZNCC ' + fmt(score.zncc) + '<br>' + esc(scoreStatus(score)) + '</div>';
}
function patchComparison(row) {
  const patch = patchFor(row), comparison = comparisonFor(row), image = imageKey();
  const e = eligibilityText(comparison);
  let html = '<section class="panel" id="patch-panel"><h2>2. 같은 이웃 사진에서 가져온 패치를 비교합니다</h2><p class="lead">열은 투영 방법, 행은 depth source입니다. 두 열에서 동일한 중심 depth를 사용합니다. 사진을 누르면 원 표본을 확대해 볼 수 있습니다.</p>';
  html += '<div class="reference-strip">' + figure(patch.reference_url, "기준 사진의 " + patchKey() + "×" + patchKey() + " 패치", "pixel") + '<div><strong>이 패턴을 두 source가 얼마나 잘 다시 찾는가?</strong><p>현재 이웃: ' + esc(row.camera_id || "미지원") + '<br>비용 계산 공통 표본: <strong>' + countText(comparison.common_count) + ' / ' + totalPixels() + '</strong></p><p><span class="swatch gray"></span> 패치의 회색은 결손·투영 미지원입니다.</p></div></div>';
  html += '<div class="compare-grid"><div></div><div class="column-label">원 depth 투영</div><div class="column-label plane">Depth·normal 평면 투영</div>';
  for (const source of ["prior", image]) {
    const s = patch.sources?.[source] || {};
    html += '<div class="row-label">' + (source === "prior" ? "Prior" : source.toUpperCase()) + '</div>';
    for (const method of ["raw", "plane"]) html += '<div>' + scoreCaption(comparison, method, source) + figure(s[method + "_url"], names[source] + " · " + (method === "raw" ? "원 depth" : "depth·normal 평면") + " · " + patchKey() + "×" + patchKey(), "pixel") + '</div>';
  }
  html += '</div><div class="explain"><span class="status' + e.cls + '">' + esc(e.label) + '</span><p>' + esc(e.note) + '</p><p>작은 비용은 밝고 어두운 무늬의 배치가 기준 패치와 더 비슷하다는 뜻입니다. 엉뚱한 반복무늬를 보고 있는지, 평면이 서로 다른 표면을 이어 붙였는지도 확인해야 합니다.</p></div>';
  html += '<details class="inner" id="projection-details"><summary>이웃 원사진의 투영 위치와 source 단독 지원 보기</summary><p>비교 상대가 결손이어도 유효한 source의 투영은 표시합니다. 테두리가 사진 밖에 있거나 원 depth가 결손이면 표시가 없거나 끊길 수 있습니다.</p><div class="compare-grid"><div></div><div class="column-label">원 depth 위치</div><div class="column-label plane">Depth·normal 평면 위치</div>';
  for (const source of ["prior", image]) {
    const s = patch.sources?.[source] || {};
    html += '<div class="row-label">' + source.toUpperCase() + '</div>';
    for (const method of ["raw", "plane"]) html += figure(s[method + "_full_overlay_url"], names[source] + " · " + (method === "raw" ? "원 depth" : "평면") + " · 이웃 사진 투영");
  }
  html += '</div><h3>각 source 자체의 계산 가능한 표본</h3><p class="hint">아래 비용은 각 source·방법의 자체 mask에서 계산한 진단값입니다. 서로 다른 표본을 쓸 수 있으므로 이 표의 비용끼리 우열을 비교하거나 위의 공통 비용과 동일시하지 마세요.</p><div class="table-wrap"><table id="own-support-table"><thead><tr><th>Source</th><th>방법</th><th>자체 계산 가능 표본</th><th>자체 표본 비용</th><th>상태</th></tr></thead><tbody>';
  for (const source of ["prior", image]) for (const method of ["raw", "plane"]) {
    const own = patch.sources?.[source]?.[method + "_own_support_score"] || {};
    html += '<tr><td>' + source.toUpperCase() + '</td><td>' + (method === "raw" ? "원 depth" : "평면") + '</td><td class="num">' + countText(own.common_count) + ' / ' + totalPixels() + '</td><td class="num">' + fmt(own.cost) + '</td><td>' + esc(scoreStatus(own)) + '</td></tr>';
  }
  html += '</tbody></table></div></details>';
  html += '<details class="inner" id="mask-details"><summary>어느 표본으로 비용을 계산했는지 보기</summary><p><span class="swatch white"></span> 흰색 = 계산 가능 · <span class="swatch black"></span> 검은색 = 결손·투영 미지원. 흰색이 정답을 뜻하지 않습니다.</p><div class="reference-strip">' + figure(comparison.mask_url, "네 결과의 공통 mask · 네 비용에 같은 표본 사용", "pixel") + '<div><strong>' + countText(comparison.common_count) + ' / ' + totalPixels() + ' 공통 표본</strong><p>아래 네 mask의 교집합입니다. 원 depth 결손은 평면 방식에서도 유지합니다. 교집합 밖의 패치 색은 보이더라도 비용 계산에는 들어가지 않습니다.</p></div></div><div class="compare-grid"><div></div><div class="column-label">원 depth 유효 mask</div><div class="column-label plane">평면 유효 mask</div>';
  for (const source of ["prior", image]) {
    const s = patch.sources?.[source] || {};
    html += '<div class="row-label">' + (source === "prior" ? "Prior" : source.toUpperCase()) + '</div>' + figure(s.raw_mask_url, names[source] + " · 원 depth 유효 mask", "pixel") + figure(s.plane_mask_url, names[source] + " · 평면 유효 mask", "pixel");
  }
  html += '</div>' + textureTable(comparison) + '</details></section>';
  return html;
}
function textureTable(comparison) {
  let html = '<h3>정규화 전 밝기 변화</h3><div class="table-wrap"><table><thead><tr><th>방법</th><th>Source</th><th>기준 표준편차</th><th>가져온 패치 표준편차</th><th>상태</th></tr></thead><tbody>';
  for (const method of ["raw", "plane"]) for (const source of ["prior", imageKey()]) {
    const score = scoreFor(comparison, method, source);
    html += '<tr><td>' + (method === "raw" ? "원 depth" : "평면") + '</td><td>' + esc(source.toUpperCase()) + '</td><td class="num">' + fmt(score.std_reference, 6) + '</td><td class="num">' + fmt(score.std_warp, 6) + '</td><td>' + esc(scoreStatus(score)) + '</td></tr>';
  }
  return html + '</tbody></table></div><p class="hint">Grayscale [0,1]의 표준편차입니다. 밝기 변화가 아주 작으면 ZNCC가 정의되더라도 작은 영상 변화에 비용이 민감할 수 있습니다.</p>';
}
function viewsTable() {
  const image = imageKey();
  let html = '<section class="panel"><h2>3. 모든 이웃 사진에서 비용 방향이 유지되는지 봅니다</h2><p class="lead">비용 = (1 − ZNCC) / 2. 네 비용은 같은 공통 표본에서 계산합니다. 화면 밖·결손 사진도 표에 남깁니다.</p><div class="table-wrap"><table id="score-table"><thead><tr><th rowspan="2">이웃 사진</th><th rowspan="2">공통 표본</th><th colspan="3">원 depth 투영</th><th colspan="3">Depth·normal 평면 투영</th><th rowspan="2">수치 요건</th><th rowspan="2">패치</th></tr><tr><th>Prior 비용</th><th>' + image.toUpperCase() + ' 비용</th><th>영상 − Prior</th><th>Prior 비용</th><th>' + image.toUpperCase() + ' 비용</th><th>영상 − Prior</th></tr></thead><tbody>';
  (current.neighbors || []).forEach((row, index) => {
    const c = comparisonFor(row), e = eligibilityText(c);
    html += '<tr class="' + (index === neighborIndex ? "selected" : "") + '"><td class="camera">' + (index + 1) + '. ' + esc(row.camera_id) + '</td><td class="num">' + countText(c.common_count) + ' / ' + totalPixels() + '</td>';
    for (const method of ["raw", "plane"]) {
      const p = scoreFor(c, method, "prior"), i = scoreFor(c, method, image);
      html += '<td class="num">' + fmt(p.cost) + '</td><td class="num">' + fmt(i.cost) + '</td><td class="num">' + deltaCell(finite(p.cost) && finite(i.cost) ? i.cost - p.cost : null) + '</td>';
    }
    html += '<td><span class="status' + e.cls + '" title="' + esc(e.note) + '">' + esc(e.label) + '</span></td><td><button class="table-button" data-neighbor="' + index + '">보기</button></td></tr>';
  });
  html += '</tbody></table></div><p class="hint"><span class="delta-prior">양수: Prior 비용이 더 작음.</span> <span class="delta-image">음수: 영상 source 비용이 더 작음.</span> 색은 정답·오답 표시가 아닙니다. 미정의 비용과 미지원 사진은 0점이나 반대표로 합치지 않습니다.</p></section>';
  return html;
}
function stabilityTable() {
  let html = '<section class="panel"><h2>4. 패치 크기를 바꿔도 해석이 유지되는지 봅니다</h2><p class="lead">중심 위치와 normal 추정 범위를 고정한 채, 점수 계산 영역만 9×9 → 17×17 → 33×33으로 바꿉니다.</p><div class="table-wrap"><table id="stability-table"><thead><tr><th>점수 패치</th><th>원 depth · 비용차 중앙값</th><th>원 depth · 비용 쌍 / 수치 요건 충족 사진</th><th>평면 · 비용차 중앙값</th><th>평면 · 비용 쌍 / 수치 요건 충족 사진</th><th></th></tr></thead><tbody>';
  for (const size of ["9", "17", "33"]) {
    const s = summaryFor(current, size);
    html += '<tr class="' + (size === patchKey() ? "selected" : "") + '"><td>' + size + ' × ' + size + '</td><td class="num">' + deltaCell(s.raw?.median_delta_image_minus_prior) + '</td><td class="num">' + countText(s.raw?.paired_views) + ' / ' + countText(s.raw?.eligible_views) + '</td><td class="num">' + deltaCell(s.plane?.median_delta_image_minus_prior) + '</td><td class="num">' + countText(s.plane?.paired_views) + ' / ' + countText(s.plane?.eligible_views) + '</td><td><button class="table-button" data-size="' + size + '">이 크기 보기</button></td></tr>';
  }
  html += '</tbody></table></div><div class="explain">부호가 바뀌면 비용 순위가 패치 크기 또는 투영 방식에 민감하다는 뜻입니다. 작은 차이가 유지되는 것만으로 source 정확성이 검증되지는 않습니다. 크기별 공통 표본과 지원 사진이 달라지는지도 함께 보세요.</div>';
  const reading = current.stability?.[pairKey()]?.reading;
  if (typeof reading === "string" && reading) html += '<p class="hint">평면 방식의 크기별 요약: ' + esc(readings[reading] || reading) + '</p>';
  return html + '</section>';
}
function referenceCard() {
  let html = '<section class="panel" id="reference-panel"><h2>5. 관측 비용과 참조 오차를 분리해서 확인합니다</h2><p class="lead">관측 비용과 진단 조건을 고정한 뒤에만 UAS 참조로 평가했습니다. 참조는 normal·비용·문턱 계산에 사용하지 않았습니다.</p>';
  if (!referenceEvaluation) return html + '<p>' + (referenceLoadError ? '참조 평가 자료를 읽지 못했습니다: ' + esc(referenceLoadError) : '별도 참조 평가 자료를 읽고 있습니다.') + '</p></section>';
  const item = referenceEvaluation.cases?.find(row => row.case_id === current.case_id);
  if (!item) return html + '<div class="explain">이 위치의 참조 평가가 없습니다. 관측 비용의 방향이 정확도와 맞는지 판단할 수 없습니다.</div></section>';
  const coverage = item.coverage?.find(row => Number(row.patch_size) === Number(patchKey())) || {};
  html += '<div class="metrics">' + metric(countText(coverage.all_reference_count), "현재 패치에 투영된 UAS 점") + metric(countText(coverage.inherited_strict_count), "기존 엄격 지원 조건을 통과한 UAS 점") + '</div>';
  const comparisons = (item.comparisons || []).filter(row => row.pair === pairKey() && Number(row.patch_size) === Number(patchKey()));
  if (!comparisons.some(row => row.common_reference_count > 0)) html += '<div class="explain"><strong>현재 패치·비교쌍을 함께 평가할 참조점이 없습니다.</strong><p>이 경우 사진 비용을 계산할 수 있어도 어느 source가 GT에 더 가까운지는 이 자료로 검증할 수 없습니다. 오차 0이나 두 source의 동등성을 뜻하지 않습니다.</p></div>';
  html += '<div class="table-wrap"><table id="reference-table"><thead><tr><th>방법</th><th>같은 UAS ID 수</th><th>Prior 절대 camera-Z 오차 중앙값</th><th>' + imageKey().toUpperCase() + ' 절대 camera-Z 오차 중앙값</th><th>동결된 사진 비용 해석</th><th>오차 방향과의 관계</th></tr></thead><tbody>';
  const matches = {DESCRIPTIVE_AGREEMENT:"관측 방향과 참조 오차 방향이 같음", DESCRIPTIVE_DISAGREEMENT:"관측 방향과 참조 오차 방향이 다름", UNAVAILABLE_NO_COMMON_REFERENCE:"공통 참조 없음", UNRESOLVED_TIE_OR_UNCERTAIN:"사진 해석 또는 오차 차이 미확정", UNAVAILABLE_NO_FROZEN_PHOTO_PREFERENCE:"사진 해석 미기록"};
  for (const row of comparisons) html += '<tr><td>' + (row.mode === "raw" ? "원 depth" : "평면") + '</td><td class="num">' + countText(row.common_reference_count) + (row.low_count_descriptive_only ? ' · 적은 표본' : '') + '</td><td class="num">' + fmt(row.prior?.median_abs_error_m, 3) + ' m</td><td class="num">' + fmt(row.image?.median_abs_error_m, 3) + ' m</td><td>' + esc(readings[row.photo_preference?.reading] || "방향 미확정") + '</td><td>' + esc(matches[row.photo_reference_comparison] || row.photo_reference_comparison) + '</td></tr>';
  html += '</tbody></table></div><p class="hint">두 source와 원 depth·평면 네 조건을 정확히 같은 참조점 ID에서 비교합니다. 이 값은 camera-Z 오차이며 높이(Z) 오차와 같지 않습니다. 표본이 10개 미만이면 적은 표본으로 표시합니다. 실제 가시성과 기존 좌표계·정합 불확실성이 남아 있어 보정된 절대 정확도나 다른 영역의 성능으로 확대하지 않습니다.</p><p class="hint"><a href="assets/evaluation/receipt.json" target="_blank" rel="noopener">별도 참조 평가 JSON</a> · 가중치와 기하 학습 결과는 이 평가 대상이 아닙니다.</p></section>';
  return html;
}
function render() {
  if (!current) return;
  const ref = typeof current.ref_camera === "string" ? current.ref_camera : current.ref_camera?.camera_id || "미기록";
  $("#case-info").textContent = caseLabel(current) + " · 기준 사진 " + ref + " · 중심 픽셀 (" + (current.center_uv || []).join(", ") + ")";
  $("#neighbor-select").replaceChildren(...(current.neighbors || []).map((row, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = (index + 1) + ". " + row.camera_id + " · 공통 " + countText(comparisonFor(row).common_count) + "/" + totalPixels();
    return option;
  }));
  $("#neighbor-select").value = String(neighborIndex);
  const depths = current.depths || {}, summary = summaryFor(current);
  let html = '<section class="panel"><h2>1. 위치와 비교할 표면을 확인합니다</h2><p class="lead">기존 진단에서 고정한 위치입니다. “두 depth”에 따른 위치 이름은 Prior와 DA3의 차이로 정한 것이며, GT나 사진 비용으로 고른 표본은 아닙니다.</p><div class="grid two">' + figure(current.ref_full_overlay_url, "기준 원사진 · 고정 중심 위치") + figure(current.ref_context_url, "기준 사진의 주변 문맥 · 현재 점수 패치와 구분") + '</div><div class="metrics">';
  for (const key of ["prior", "da3", "mvs"]) html += metric(fmt(depths[key] ?? current.normal_sources?.[key]?.center_depth_m, 3) + " m", key.toUpperCase() + " 중심 camera-Z depth");
  html += '</div><p class="hint">Depth는 기준 카메라 축 방향 거리입니다. Normal 방식에서도 이 중심값을 옮기지 않습니다. 문맥 그림은 위치 이해용이며 선택한 점수 패치 전체와 같다고 가정하지 마세요.</p><details class="inner"><summary>Source별 normal 추정 수치 확인</summary>' + normalTable() + '</details></section>';
  html += '<section class="panel"><h2>현재 조건의 관측 비용 요약</h2><p class="lead">' + esc(caseLabel(current)) + ' · Prior ↔ ' + imageKey().toUpperCase() + ' · ' + patchKey() + '×' + patchKey() + '</p><div class="grid two">' + methodCard(summary.raw, "raw") + methodCard(summary.plane, "plane") + '</div><p class="hint">중앙값과 방향 집계는 수치 요건을 충족한 사진만 사용합니다. 비용이 계산된 사진 수는 따로 표시합니다. 비용 중앙값의 차이와 대응 비용차 중앙값은 일반적으로 다릅니다. 두 source 쌍은 공통 mask가 달라 직접 순위화하지 않습니다.</p>' + gateGuide() + '</section>';
  html += patchComparison(current.neighbors?.[neighborIndex] || {}) + viewsTable() + stabilityTable() + referenceCard();
  $("#case-body").innerHTML = html;
  bindContent();
  renderOverview();
  window.__normalWalkthrough = {caseId:current.case_id, neighbor:neighborIndex, pair:pairKey(), patchSize:Number(patchKey()), caseCount:manifest.cases.length, neighborCount:current.neighbors?.length || 0, scientific_verdict:null};
}
function renderOverview() {
  if (!manifest) return;
  let html = '<div class="table-wrap"><table id="overview-table"><thead><tr><th>고정 위치</th><th>원 depth 비용차 중앙값</th><th>계산 / 수치 요건 충족 사진</th><th>평면 비용차 중앙값</th><th>계산 / 수치 요건 충족 사진</th><th></th></tr></thead><tbody>';
  manifest.cases.forEach((entry, index) => {
    const item = caseCache.get(index), s = item && !(item instanceof Promise) ? summaryFor(item) : {};
    html += '<tr class="' + (index === currentIndex ? "selected" : "") + '"><td>' + esc(caseLabel(entry)) + (caseErrors.has(index) ? '<span class="normal-status">읽기 실패</span>' : '') + '</td><td class="num">' + deltaCell(s.raw?.median_delta_image_minus_prior) + '</td><td class="num">' + countText(s.raw?.paired_views) + ' / ' + countText(s.raw?.eligible_views) + '</td><td class="num">' + deltaCell(s.plane?.median_delta_image_minus_prior) + '</td><td class="num">' + countText(s.plane?.paired_views) + ' / ' + countText(s.plane?.eligible_views) + '</td><td><button class="table-button" data-case="' + index + '">위치 보기</button></td></tr>';
  });
  $("#overview-body").innerHTML = html + '</tbody></table></div><p class="hint">비용차 = 영상 − Prior. 양수는 Prior 비용이 더 작고, 음수는 영상 source 비용이 더 작습니다. 이 표는 정확도 순위나 감독 가중치 지도가 아닙니다.</p>';
  $("#overview-body").querySelectorAll("[data-case]").forEach(button => button.addEventListener("click", () => {
    $("#case-select").value = button.dataset.case;
    loadCase(Number(button.dataset.case)).then(() => $("#case-body").scrollIntoView({behavior:"smooth", block:"start"})).catch(fail);
  }));
}
function bindContent() {
  $("#case-body").querySelectorAll("[data-image]").forEach(button => button.addEventListener("click", () => {
    $("#zoom-image").src = button.dataset.image;
    $("#zoom-image").alt = button.dataset.caption;
    $("#zoom-caption").textContent = button.dataset.caption;
    $("#zoom").showModal();
  }));
  $("#case-body").querySelectorAll("[data-neighbor]").forEach(button => button.addEventListener("click", () => {
    neighborIndex = Number(button.dataset.neighbor);
    render();
    $("#patch-panel").scrollIntoView({behavior:"smooth", block:"start"});
  }));
  $("#case-body").querySelectorAll("[data-size]").forEach(button => button.addEventListener("click", () => {
    $("#patch-select").value = button.dataset.size;
    chooseSupportedNeighbor();
    render();
    $("#patch-panel").scrollIntoView({behavior:"smooth", block:"start"});
  }));
}
function chooseSupportedNeighbor() {
  const first = (current?.neighbors || []).findIndex(row => Number(comparisonFor(row).common_count) > 0);
  const single = (current?.neighbors || []).findIndex(row => ["prior", imageKey()].some(source => Number(patchFor(row).sources?.[source]?.raw_own_support_score?.common_count) > 0));
  neighborIndex = first >= 0 ? first : Math.max(0, single);
}
async function fetchCase(index) {
  if (caseCache.has(index)) return caseCache.get(index);
  const entry = manifest.cases[index];
  const promise = (async () => {
    const path = asset(entry.path);
    if (!path) throw Error("위치 자료 경로가 올바르지 않습니다: " + entry.case_id);
    const response = await fetch(path);
    if (!response.ok) throw Error("위치 자료 HTTP " + response.status + ": " + entry.case_id);
    const item = await response.json();
    caseCache.set(index, item);
    return item;
  })();
  caseCache.set(index, promise);
  try { return await promise; }
  catch (error) { caseCache.delete(index); caseErrors.set(index, String(error)); throw error; }
}
async function loadCase(index) {
  const token = ++loadToken;
  const item = await fetchCase(index);
  if (token !== loadToken) return;
  current = item;
  currentIndex = index;
  chooseSupportedNeighbor();
  $("#case-link").href = asset(manifest.cases[index].path);
  render();
}
function fail(error) {
  $("#case-body").innerHTML = '<div class="error">자료를 표시하지 못했습니다: ' + esc(error.message) + '</div>';
  window.__normalWalkthroughError = String(error);
}
$("#case-select").addEventListener("change", event => loadCase(Number(event.target.value)).catch(fail));
$("#pair-select").addEventListener("change", () => { chooseSupportedNeighbor(); render(); });
$("#patch-select").addEventListener("change", () => { chooseSupportedNeighbor(); render(); });
$("#neighbor-select").addEventListener("change", event => { neighborIndex = Number(event.target.value); render(); });
$("#close-zoom").addEventListener("click", () => $("#zoom").close());
$("#zoom").addEventListener("click", event => { if (event.target === $("#zoom")) $("#zoom").close(); });

(async () => {
  const response = await fetch("data.json");
  if (!response.ok) throw Error("자료 목록 HTTP " + response.status);
  manifest = await response.json();
  if (!Array.isArray(manifest.cases) || !manifest.cases.length) throw Error("위치 목록이 비어 있습니다.");
  $("#case-select").replaceChildren(...manifest.cases.map((entry, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = caseLabel(entry);
    return option;
  }));
  const first = Math.max(0, manifest.cases.findIndex(entry => entry.case_id === "P2_low_disagreement"));
  $("#case-select").value = String(first);
  await loadCase(first);
  const referencePromise = (async () => {
    const response = await fetch("assets/evaluation/receipt.json");
    if (!response.ok) throw Error("참조 평가 HTTP " + response.status);
    referenceEvaluation = await response.json();
  })();
  const results = await Promise.allSettled([...manifest.cases.map((_, index) => fetchCase(index)), referencePromise]);
  const referenceResult = results.pop();
  if (referenceResult.status === "rejected") referenceLoadError = String(referenceResult.reason);
  window.__normalOverviewErrors = results.flatMap((result, index) => result.status === "rejected" ? [{case_id:manifest.cases[index].case_id, error:String(result.reason)}] : []);
  renderOverview();
  if (current) {
    $("#reference-panel").outerHTML = referenceCard();
  }
})().catch(fail);
