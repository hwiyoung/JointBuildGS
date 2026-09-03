import * as THREE from 'three';
import * as GaussianSplats3D from './lib/gaussian-splats-3d.module.min.js';

const $ = id => document.getElementById(id);
const status = $('status');
const viewport = $('viewport');
const number = value => Number(value).toLocaleString('ko-KR');
const finite = value => (Number.isFinite(value) ? Number(value).toFixed(3) : 'NA');

function setStatus(text, error = false) {
  status.textContent = text;
  status.style.color = error ? '#fca5a5' : '#93c5fd';
}
window.addEventListener('error', event => setStatus(`오류 · ${event.message}`, true));
window.addEventListener('unhandledrejection', event => setStatus(`오류 · ${event.reason?.message || event.reason}`, true));

async function sha256(buffer) {
  if (!crypto?.subtle) return null;
  const value = await crypto.subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(value)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
async function fetchAsset(record) {
  const response = await fetch(record.path, {cache: 'no-store'});
  if (!response.ok) throw new Error(`${record.path}: HTTP ${response.status}`);
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength !== record.bytes) throw new Error(`${record.path}: byte mismatch`);
  const actual = await sha256(buffer);
  if (actual && actual !== record.sha256) throw new Error(`${record.path}: SHA-256 mismatch`);
  return buffer;
}
function hexRgb(value) { const c = new THREE.Color(value); return [c.r, c.g, c.b]; }
function lerpRgb(fromHex, toHex, t) { const a = new THREE.Color(fromHex); a.lerp(new THREE.Color(toHex), Math.min(1, Math.max(0, t))); return [a.r, a.g, a.b]; }
function rampRgb(t) { if (!Number.isFinite(t)) return hexRgb('#475569'); return t < 0.5 ? lerpRgb('#3b82f6', '#facc15', t * 2) : lerpRgb('#facc15', '#ef4444', (t - 0.5) * 2); }
const GREY = hexRgb('#3b4657');
const ramp01 = (value, from, to) => (Number.isFinite(value) ? lerpRgb(from, to, value) : GREY);
const diverging = (value, span) => {
  if (!Number.isFinite(value)) return GREY;
  const t = Math.max(-1, Math.min(1, value / span));
  return t < 0 ? lerpRgb('#facc15', '#3b82f6', -t) : lerpRgb('#facc15', '#ef4444', t);
};

const manifestResponse = await fetch('viewer_manifest.json', {cache: 'no-store'});
if (!manifestResponse.ok) throw new Error(`viewer_manifest.json: HTTP ${manifestResponse.status}`);
const manifest = await manifestResponse.json();
if (manifest.scientific_verdict !== null) throw new Error('scientific_verdict must remain null');
if (manifest.comparison_contract.m3c2_recomputed !== false) throw new Error('M3C2 recomputation contract drift');

// ---------------------------------------------------------------- renderer
const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'high-performance'});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
viewport.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 5000);
camera.up.set(0, 0, 1);
const controls = new GaussianSplats3D.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.08; controls.screenSpacePanning = true; controls.minDistance = 0.5; controls.maxDistance = 3000;
const center = new THREE.Vector3(...manifest.bounds.scene_local.center);
const extent = new THREE.Vector3(...manifest.bounds.scene_local.extent);
const sceneRadius = Math.max(extent.x, extent.y, extent.z * 2, 40) * 0.62;
const grid = new THREE.GridHelper(Math.ceil(sceneRadius * 2.4 / 25) * 25, Math.ceil(sceneRadius * 2.4 / 25), 0x35506b, 0x1b2a3a);
grid.rotation.x = Math.PI / 2; grid.position.set(center.x, center.y, manifest.bounds.scene_local.min[2] - 1);
grid.material.opacity = 0.45; grid.material.transparent = true; scene.add(grid);
const axes = new THREE.AxesHelper(Math.min(35, sceneRadius * 0.15)); axes.position.copy(grid.position); scene.add(axes);

function createPoints(positions, color, size, opacity = 1, vertexColors = null) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  if (vertexColors) geometry.setAttribute('color', new THREE.BufferAttribute(vertexColors, 3));
  geometry.computeBoundingSphere();
  const material = new THREE.PointsMaterial({color: vertexColors ? 0xffffff : color, vertexColors: Boolean(vertexColors), size, sizeAttenuation: false, transparent: opacity < 1, opacity, depthWrite: false});
  const points = new THREE.Points(geometry, material);
  scene.add(points);
  return points;
}
function setView(kind, target = center, radius = sceneRadius) {
  controls.target.copy(target);
  if (kind === 'top') camera.position.set(target.x, target.y, target.z + radius * 2.2);
  else camera.position.set(target.x + radius * 0.9, target.y - radius * 1.25, target.z + radius * 0.8);
  camera.near = Math.max(0.05, radius / 2000); camera.far = Math.max(3000, radius * 12);
  camera.updateProjectionMatrix(); controls.update();
}

// ---------------------------------------------------------------- scene layer: sources, relation cores, H_M zones
setStatus('장면 자산 검증 중…');
const hz = manifest.hm_zones;
const qz = manifest.quality_zones;
const sceneBuffers = await Promise.all([
  fetchAsset(manifest.sources.mvs), fetchAsset(manifest.sources.als), fetchAsset(manifest.relations.xyz), fetchAsset(manifest.relations.attributes),
  fetchAsset(manifest.relations.metrics), fetchAsset(manifest.relations.support_counts), fetchAsset(hz.assets.flag), fetchAsset(hz.assets.cluster),
  fetchAsset(qz.assets.flag), fetchAsset(qz.assets.cluster),
]);
const sourceObjects = {
  mvs: createPoints(new Float32Array(sceneBuffers[0]), manifest.sources.mvs.color, 1.0, Number($('source-opacity').value)),
  als: createPoints(new Float32Array(sceneBuffers[1]), manifest.sources.als.color, 1.0, Number($('source-opacity').value)),
};
const corePositions = new Float32Array(sceneBuffers[2]);
const coreAttr = new Uint8Array(sceneBuffers[3]);
const coreMetrics = new Float32Array(sceneBuffers[4]);
const coreSupport = new Uint32Array(sceneBuffers[5]);
const hmFlag = new Uint8Array(sceneBuffers[6]);
const hmCluster = new Uint16Array(sceneBuffers[7]);
const qFlag = new Uint8Array(sceneBuffers[8]);
const qCluster = new Uint16Array(sceneBuffers[9]);
const coreCount = manifest.relations.count;
let sceneMode = 'hm';
function coreColor(index, mode) {
  const cls = coreAttr[index * 4];
  if (mode === 'class') return hexRgb(manifest.classes[String(cls)].color);
  if (mode === 'quality') {
    if (qFlag[index]) return hexRgb('#ff9f1c');
    return cls === 1 || cls === 2 ? hexRgb('#3a4a3a') : hexRgb('#2b3442');
  }
  if (hmFlag[index]) return hexRgb('#ff2fd6');
  return cls === 4 ? hexRgb('#4c3d6e') : hexRgb('#2b3442');
}
const coreColors = new Float32Array(coreCount * 3);
for (let i = 0; i < coreCount; i++) coreColors.set(coreColor(i, sceneMode), i * 3);
const coreObject = createPoints(corePositions, 0xffffff, Number($('core-size').value), 1, coreColors);
coreObject.renderOrder = 10;
function updateCoreColors() {
  const colors = coreObject.geometry.getAttribute('color');
  for (let i = 0; i < coreCount; i++) { const rgb = coreColor(i, sceneMode); colors.setXYZ(i, rgb[0], rgb[1], rgb[2]); }
  colors.needsUpdate = true;
}
const hmBoxes = [];
for (const cluster of hz.clusters) {
  const [x0, y0, x1, y1] = cluster.bbox;
  const zb = cluster.z_median - cluster.height_median_m; const zt = cluster.z_median + 2;
  const helper = new THREE.Box3Helper(new THREE.Box3(new THREE.Vector3(x0, y0, zb), new THREE.Vector3(x1, y1, zt)), 0xff2fd6);
  helper.renderOrder = 15; helper.userData = {cluster}; scene.add(helper); hmBoxes.push(helper);
}
const qBoxes = [];
for (const cluster of qz.clusters) {
  const [x0, y0, x1, y1] = cluster.bbox;
  const helper = new THREE.Box3Helper(new THREE.Box3(new THREE.Vector3(x0, y0, cluster.z_median - cluster.height_median_m), new THREE.Vector3(x1, y1, cluster.z_median + 2)), 0xff9f1c);
  helper.renderOrder = 15; helper.userData = {cluster}; scene.add(helper); qBoxes.push(helper);
}
function updateHmBoxes() {
  const showBoundary = $('hm-boundary').checked;
  for (const box of hmBoxes) box.visible = sceneMode === 'hm' && (showBoundary || !box.userData.cluster.touches_scene_boundary);
  for (const box of qBoxes) box.visible = sceneMode === 'quality' && (showBoundary || !box.userData.cluster.touches_scene_boundary);
  $('hm-list').hidden = sceneMode !== 'hm';
  $('quality-list').hidden = sceneMode !== 'quality';
}
function renderQualityList() {
  const showBoundary = $('hm-boundary').checked;
  const rows = qz.clusters.filter(c => showBoundary || !c.touches_scene_boundary);
  $('quality-list').innerHTML = rows.map(c => `<div><dt>#${c.id}${c.touches_scene_boundary ? ' (경계)' : ''} · ${number(Math.round(c.area_m2))} m² · h ${c.height_median_m.toFixed(1)} m · σ ${c.sigma_mvs_median_m.toFixed(2)} / ${c.sigma_als_median_m.toFixed(2)}</dt><dd><button type="button" data-qz="${c.id}">이동</button></dd></div>`).join('')
    || '<div><dt>군집 없음</dt><dd></dd></div>';
  $('quality-list').querySelectorAll('[data-qz]').forEach(button => button.addEventListener('click', () => {
    const c = qz.clusters.find(item => item.id === Number(button.dataset.qz));
    const [x0, y0, x1, y1] = c.bbox;
    setView('oblique', new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, c.z_median), Math.max(x1 - x0, y1 - y0, 20) * 0.9);
  }));
}
function renderHmList() {
  const showBoundary = $('hm-boundary').checked;
  const rows = hz.clusters.filter(c => showBoundary || !c.touches_scene_boundary);
  const kind = c => (c.mvs_column_fraction === null || c.mvs_column_fraction === undefined ? '' : (c.mvs_column_fraction < 0.3 ? ' · MVS 없음' : ' · MVS 다른 높이'));
  $('hm-list').innerHTML = rows.map(c => `<div><dt>#${c.id}${c.touches_scene_boundary ? ' (경계)' : ''} · ${number(Math.round(c.area_m2))} m² · h ${c.height_median_m.toFixed(1)} m${kind(c)}</dt><dd><button type="button" data-hm="${c.id}">이동</button></dd></div>`).join('')
    || '<div><dt>군집 없음</dt><dd></dd></div>';
  $('hm-list').querySelectorAll('[data-hm]').forEach(button => button.addEventListener('click', () => {
    const c = hz.clusters.find(item => item.id === Number(button.dataset.hm));
    const [x0, y0, x1, y1] = c.bbox;
    setView('oblique', new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, c.z_median), Math.max(x1 - x0, y1 - y0, 20) * 0.9);
  }));
}
function renderSceneLegend() {
  const legend = $('scene-legend'); legend.innerHTML = '';
  const add = (color, text) => { const e = document.createElement('span'); e.innerHTML = `<i class="swatch" style="background:${color}"></i><em>${text}</em>`; legend.appendChild(e); };
  const classKo = {'1': '양립 (둘 다 있고 |d| ≤ LoD)', '2': '유의한 불일치 (둘 다 있고 |d| > LoD)', '3': 'MVS만 지지 (ALS 없음)', '4': 'ALS만 지지 (MVS 없음)', '5': '비교 불가 (법선·점 수 부족)'};
  if (sceneMode === 'class') for (const [key, item] of Object.entries(manifest.classes)) add(item.color, `${key} ${classKo[key]} · ${number(manifest.patches.raw_class_counts[key])}`);
  else if (sceneMode === 'quality') {
    add('#ff9f1c', `같은 표면인데 σ_MVS ≥ ${qz.rule.min_sigma_ratio} σ_ALS (σ_MVS ≥ ${qz.rule.min_sigma_mvs_m} m, 지면 +${qz.rule.min_height_above_ground_m} m 이상) · ${number(qz.flagged_core_count)} cores · 군집 ${qz.clusters.length}`);
    add('#3a4a3a', '둘 다 지지하지만 잡음 비가 낮은 core');
    add('#2b3442', '그 밖의 core');
  } else {
    add('#ff2fd6', `ALS만 지지 ∧ 국소 지면 +${hz.rule.min_height_above_ground_m} m 이상 · ${number(hz.elevated_core_count)} cores · 군집 ${hz.clusters.length}`);
    add('#ff2fd6', `목록 표시: "MVS 없음" = 그 XY 기둥에 MVS 점이 거의 없음(H_M 후보), "MVS 다른 높이" = MVS 표면이 다른 높이에 있음(변화 후보, P2가 그 예) · MVS 없음 ${hz.clusters.filter(c => c.mvs_column_fraction !== null && c.mvs_column_fraction < 0.3 && !c.touches_scene_boundary).length}`);
    add('#4c3d6e', 'ALS만 지지, 지면 높이 (수목·경계·틈)');
    add('#2b3442', '그 밖의 core');
  }
  $('scene-note').textContent = sceneMode === 'quality'
    ? '주황 = 두 소스가 같은 표면을 지지하지만 MVS 국소 잡음(σ_MVS)이 ALS의 3배 이상인 core. MVS가 없는 것이 아니라 "prior가 더 정밀한" 자리의 후보(H_C 안의 정밀도 비대칭 → 가중치 w = 정밀도 × 책임이 prior 쪽으로 기움). 표시용이며 판정이 아니다.'
    : sceneMode === 'hm'
    ? '자홍 = ALS 표면이 지면 위에 있는데 그 자리에 MVS 지지가 없는 core. 사진만으로는 "MVS 틀림(H_M)"과 "표면이 바뀜(H_chg)"을 못 가른다(P2가 그 예: 건물은 있으나 지붕이 4 m 낮아짐). 목록의 "MVS 없음/다른 높이"는 기둥 안 MVS 유무로 나눈 1차 분류이고, 판정은 T1·T2 채널이 한다. 상자 = 군집 bbox.'
    : '동결 M3C2/support 관계 core의 5-class 라벨(1 양립 · 2 유의 불일치 · 3 MVS만 · 4 ALS만 · 5 비교 불가). 2 m 간격 표본이며 판정이 아니다.';
  $('scene-counts').textContent = `${number(coreCount)} cores`;
}

// ---------------------------------------------------------------- prisms
const prisms = manifest.prisms.map(block => ({block, loaded: false, arrays: null, object: null, box: null}));
for (const pr of prisms) {
  const d = pr.block.domain;
  pr.box = new THREE.Box3Helper(new THREE.Box3(new THREE.Vector3(d.x[0], d.y[0], d.z[0]), new THREE.Vector3(d.x[1], d.y[1], d.z[1])), 0x38bdf8);
  pr.box.renderOrder = 15; scene.add(pr.box);
}
let active = 0;
let stage = 'scene';
const modes = {s1: 'state', t1: 'fpen', t2: 'delta'};
let evHeight = 'both';
const showCells = {m: true, p: true};
const stateFilter = {1: true, 2: true, 3: true, 4: true, 5: true};
let onlySelectedPair = false;
let selectedPair = null;
let cellHighlight = null;
let selectionMarker = null;

async function loadPrism(pr) {
  if (pr.loaded) return;
  setStatus(`${pr.block.label} 자산 검증 중…`);
  const a = pr.block.assets;
  const buffers = await Promise.all([fetchAsset(a.cells_xyz), fetchAsset(a.cells_z), fetchAsset(a.cells_attributes), fetchAsset(a.cells_patches), fetchAsset(a.cells_t1_metrics), fetchAsset(a.cells_t2_metrics)]);
  pr.arrays = {xyz: new Float32Array(buffers[0]), z: new Float32Array(buffers[1]), attr: new Uint8Array(buffers[2]), patch: new Int32Array(buffers[3]), t1: new Float32Array(buffers[4]), t2: new Float32Array(buffers[5])};
  pr.t1Index = new Map(pr.block.t1_metric_names.map((name, index) => [name, index]));
  pr.t2Index = new Map(pr.block.t2_metric_names.map((name, index) => [name, index]));
  pr.T1 = pr.block.t1_metric_names.length; pr.T2 = pr.block.t2_metric_names.length;
  const n = pr.block.cell_count;
  const positions = new Float32Array(n * 3); const colors = new Float32Array(n * 3);
  pr.object = createPoints(positions, 0xffffff, Number($('cell-size').value), 1, colors);
  pr.object.renderOrder = 16; pr.object.visible = false;
  pr.objectP = createPoints(new Float32Array(n * 3), 0xffffff, Math.max(1, Number($('cell-size').value) * 0.7), 0.45, new Float32Array(n * 3));
  pr.objectP.renderOrder = 15; pr.objectP.visible = false;
  pr.loaded = true;
  rebuildPrism(pr);
}
const t1v = (pr, i, name) => pr.arrays.t1[i * pr.T1 + pr.t1Index.get(name)];
const t2v = (pr, i, name) => pr.arrays.t2[i * pr.T2 + pr.t2Index.get(name)];
function cellPosition(pr, i, height = evHeight) {
  const zm = pr.arrays.z[i * 2]; const zp = pr.arrays.z[i * 2 + 1];
  let z = Number.isFinite(zm) ? zm : zp;
  if (height === 'm' || height === 'both') z = zm; if (height === 'p') z = zp;
  return [pr.arrays.xyz[i * 3], pr.arrays.xyz[i * 3 + 1], z];
}
function cellColor(pr, i, st, mode) {
  const A = pr.arrays.attr; const state = A[i * 8]; const rough = A[i * 8 + 1];
  if (st === 's1') {
    if (mode === 'state') return hexRgb(pr.block.state_colors[String(state)]);
    if (mode === 'rough') return hexRgb(rough ? '#f97316' : '#22c55e');
    return diverging(pr.arrays.z[i * 2 + 1] - pr.arrays.z[i * 2], 4);
  }
  if (st === 't1') {
    if (mode === 'd3a') return diverging(t1v(pr, i, 'core_d_median_m'), 4);
    if (mode === 'fpen') return ramp01(t1v(pr, i, 'f_penetrate'), '#1f2937', '#ef4444');
    if (mode === 'fagree') return ramp01(t1v(pr, i, 'f_agree'), '#1f2937', '#22c55e');
    if (mode === 'fblock') return ramp01(t1v(pr, i, 'f_block'), '#1f2937', '#f97316');
    if (mode === 'texture') return ramp01(Math.min(1, t1v(pr, i, 'texture_median') / 30), '#1e3a8a', '#facc15');
    if (mode === 'r1') return ['#1f2937', '#7c2d12', '#f59e0b', '#fef08a'].map(hexRgb)[A[i * 8 + 6]] || GREY;
  }
  if (st === 't2') {
    const powerM = A[i * 8 + 4]; const powerP = A[i * 8 + 5];
    if (mode === 'delta') return diverging(t2v(pr, i, 'delta_median'), 0.8);
    if (mode === 'fmp') return ramp01(t2v(pr, i, 'f_m_over_p'), '#1f2937', '#ef4444');
    if (mode === 'fpm') return ramp01(t2v(pr, i, 'f_p_over_m'), '#1f2937', '#3b82f6');
    if (mode === 'sm' || mode === 'sp') { const v = t2v(pr, i, mode === 'sm' ? 'ncc_median_m' : 'ncc_median_p'); return Number.isFinite(v) ? rampRgb(1 - (v + 0.2) / 1.2) : GREY; }
    if (mode === 'power') return hexRgb(powerM && powerP ? '#22c55e' : powerM ? '#67e8f9' : powerP ? '#c4b5fd' : '#3b4657');
    if (mode === 'npm' || mode === 'npp') { const c = t2v(pr, i, mode === 'npm' ? 'n_pairs_m' : 'n_pairs_p'); return c > 0 ? lerpRgb('#7c2d12', '#22c55e', Math.min(1, Math.log10(c + 1) / 3)) : GREY; }
    if (mode === 'nvdiff') return diverging(t2v(pr, i, 'n_views_p') - t2v(pr, i, 'n_views_m'), 20);
    if (mode === 'ctrl') { const sm = t2v(pr, i, 'ncc_median_m'); const sc = t2v(pr, i, 'ncc_median_ctrl_1'); return Number.isFinite(sm) && Number.isFinite(sc) ? lerpRgb('#1f2937', '#f472b6', Math.max(0, Math.min(1, (sm - sc) / 0.8))) : GREY; }
    if (mode === 'edge') return diverging(t2v(pr, i, 'edge_dist_median_px_p') - t2v(pr, i, 'edge_dist_median_px_m'), 10);
    if (mode === 'r2') return ['#1f2937', '#7c2d12', '#f59e0b', '#fef08a'].map(hexRgb)[A[i * 8 + 7]] || GREY;
  }
  return hexRgb(pr.block.state_colors[String(state)]);
}
function rebuildPrism(pr) {
  if (!pr.loaded) return;
  const st = stage === 'scene' ? 's1' : stage; const mode = modes[st];
  const positions = pr.object.geometry.getAttribute('position'); const colors = pr.object.geometry.getAttribute('color');
  const shown = i => {
    const state = pr.arrays.attr[i * 8];
    if (!stateFilter[state]) return false;
    if (onlySelectedPair && selectedPair && (pr.arrays.patch[i * 2] !== selectedPair[0] || pr.arrays.patch[i * 2 + 1] !== selectedPair[1])) return false;
    return true;
  };
  for (let i = 0; i < pr.block.cell_count; i++) {
    const [x, y, z] = cellPosition(pr, i, 'm');
    positions.setXYZ(i, x, y, Number.isFinite(z) && shown(i) ? z : -1e6);
    const rgb = cellColor(pr, i, st, mode); colors.setXYZ(i, rgb[0], rgb[1], rgb[2]);
  }
  positions.needsUpdate = true; colors.needsUpdate = true; pr.object.geometry.computeBoundingSphere();
  const positionsP = pr.objectP.geometry.getAttribute('position'); const colorsP = pr.objectP.geometry.getAttribute('color');
  for (let i = 0; i < pr.block.cell_count; i++) {
    const [x, y, z] = cellPosition(pr, i, 'p');
    positionsP.setXYZ(i, x, y, Number.isFinite(z) && shown(i) ? z : -1e6);
    const rgb = cellColor(pr, i, st, mode); colorsP.setXYZ(i, rgb[0], rgb[1], rgb[2]);
  }
  positionsP.needsUpdate = true; colorsP.needsUpdate = true; pr.objectP.geometry.computeBoundingSphere();
  applyCellVisibility(pr);
}
function applyCellVisibility(pr) {
  const inPrismStage = stage !== 'scene' && pr === prisms[active];
  pr.object.visible = inPrismStage && showCells.m;
  pr.objectP.visible = inPrismStage && showCells.p;
}

// ---------------------------------------------------------------- legends, notes, accounting
function addLegend(legend, color, text) { const e = document.createElement('span'); e.innerHTML = `<i class="swatch" style="background:${color}"></i><em>${text}</em>`; legend.appendChild(e); }
function barLegend(legend, from, via, to, low, high) { const e = document.createElement('span'); e.className = 'bar'; e.innerHTML = `<em>${low}</em><i style="background:linear-gradient(90deg,${from},${via},${to})"></i><em>${high}</em>`; legend.appendChild(e); }
function renderStageLegend() {
  const pr = prisms[active]; const b = pr.block;
  if (stage === 's1') {
    const legend = $('s1-legend'); legend.innerHTML = ''; const mode = modes.s1; const t1 = b.t1_per_state_summary;
    if (mode === 'state') for (const [key, name] of Object.entries(b.state_names)) addLegend(legend, b.state_colors[key], `${key} ${name} · ${t1[name] ? number(t1[name].cells) : 0} cells`);
    if (mode === 'dz') barLegend(legend, '#3b82f6', '#facc15', '#ef4444', '−4 m (지금 것이 위)', '+4 m (옛 것이 위)');
    if (mode === 'rough') { addLegend(legend, '#22c55e', '평면 짝'); addLegend(legend, '#f97316', '거친(산재 군집) 짝 — 수목 등'); }
    $('s1-note').textContent = {state: 'COMPATIBLE |dz| ≤ 0.3 m · PRIOR_ABOVE 옛 것이 위 · CURRENT_ABOVE 지금 것이 위 · PRIOR_ONLY 옛 것만 · CURRENT_ONLY 지금 것만.', dz: '위층 표면의 높이차. 큰 양수 = 2022 표면이 지금보다 높다(소실 또는 MVS 낮음), 큰 음수 = 지금 것이 더 높다(출현·수목).', rough: '거친 짝은 표면이 아니라 군집이라 뒤 단계에서 검정력이 낮다.'}[mode];
    $('s1-counts').textContent = `${number(b.cell_count)} cells`;
  }
  if (stage === 't1') {
    const legend = $('t1-legend'); legend.innerHTML = ''; const mode = modes.t1;
    if (mode === 'd3a') barLegend(legend, '#3b82f6', '#facc15', '#ef4444', '−4 m', '+4 m (ALS 위)');
    if (mode === 'fpen') barLegend(legend, '#1f2937', '#7f1d1d', '#ef4444', '0', '1');
    if (mode === 'fagree') barLegend(legend, '#1f2937', '#14532d', '#22c55e', '0', '1');
    if (mode === 'fblock') barLegend(legend, '#1f2937', '#7c2d12', '#f97316', '0', '1');
    if (mode === 'texture') barLegend(legend, '#1e3a8a', '#7c9a2c', '#facc15', '0', '30 grey std');
    if (mode === 'r1') { addLegend(legend, '#1f2937', 'r 0'); addLegend(legend, '#7c2d12', 'r 1'); addLegend(legend, '#f59e0b', 'r 2'); addLegend(legend, '#fef08a', 'r 3'); }
    $('t1-note').textContent = {d3a: '동결 M3C2 core의 부호거리 중앙값(셀에 core가 있을 때만; 2 m 간격이라 셀의 약 15 %).', fpen: '현재 카메라 광선이 prior 표면을 지나 뒤의 MVS 표면에 착지한 비율. 옛 표면이 사라졌을 때도, MVS가 낮게 잡혔을 때도 높다.', fagree: '두 표면에 같은 깊이(±0.5 m)로 착지한 비율.', fblock: 'MVS 표면이 prior 앞에 있는 비율(출현 서명).', texture: '비가림 MVS 픽셀의 7×7 국소 표준편차 중앙값.', r1: 'P_3Da + P_3Db + P_2Da(대용) — 검정력 있는 채널 수.'}[mode];
    $('t1-counts').textContent = `${number(b.t1_view_count)} views`;
  }
  if (stage === 't2') {
    const legend = $('t2-legend'); legend.innerHTML = ''; const mode = modes.t2;
    if (mode === 'delta') barLegend(legend, '#3b82f6', '#facc15', '#ef4444', '−0.8 (사진이 P 설명)', '+0.8 (사진이 M 설명)');
    if (mode === 'fmp') barLegend(legend, '#1f2937', '#7f1d1d', '#ef4444', '0', '1');
    if (mode === 'fpm') barLegend(legend, '#1f2937', '#1e3a8a', '#3b82f6', '0', '1');
    if (mode === 'sm' || mode === 'sp') barLegend(legend, '#ef4444', '#facc15', '#3b82f6', 'NCC −0.2', '1.0');
    if (mode === 'power') { addLegend(legend, '#22c55e', 'M·P 둘 다'); addLegend(legend, '#67e8f9', 'M만'); addLegend(legend, '#c4b5fd', 'P만'); addLegend(legend, '#3b4657', '없음'); }
    if (mode === 'npm' || mode === 'npp') barLegend(legend, '#7c2d12', '#8a8a2a', '#22c55e', '1쌍', '1000+');
    if (mode === 'nvdiff') barLegend(legend, '#3b82f6', '#facc15', '#ef4444', '−20 (M이 더 보임)', '+20 (P가 더 보임)');
    if (mode === 'ctrl') barLegend(legend, '#1f2937', '#8a3f6b', '#f472b6', '0 (못 느낌)', '0.8 (1 m 이동이 NCC를 무너뜨림)');
    if (mode === 'edge') barLegend(legend, '#3b82f6', '#facc15', '#ef4444', '−10 px (M 에지 설명 안 됨)', '+10 px (P 에지 설명 안 됨)');
    if (mode === 'r2') { addLegend(legend, '#1f2937', 'r 0'); addLegend(legend, '#7c2d12', 'r 1'); addLegend(legend, '#f59e0b', 'r 2'); addLegend(legend, '#fef08a', 'r 3'); }
    const band = b.t2_algorithm.ncc.summary_angle_max_deg;
    $('t2-note').textContent = {
      delta: `둘 다 보이는 공통 쌍(교차각 ≤ ${band}°)에서 ρ_M − ρ_P의 중앙값. 빨강 = 현재 MVS 표면이 사진들을 설명, 파랑 = 2022 ALS 표면이 설명.`,
      fmp: '공통 쌍 중 ρ_M − ρ_P > 0.1 인 비율.', fpm: '공통 쌍 중 ρ_P − ρ_M > 0.1 인 비율.',
      sm: 'M 높이장으로 옮긴 가중 ZNCC의 쌍 중앙값(M이 보이는 쌍만).', sp: 'P 높이장으로 옮긴 값(P가 보이는 쌍만).',
      power: 'n_pairs ≥ 3 인 후보. 2D-a 는 가시성이 정하는 채널이다.', npm: 'M 후보가 두 뷰에서 모두 보이고 교차각 대역 안인 쌍의 수.', npp: 'P 후보의 유효 쌍 수.',
      nvdiff: '후보별 유효 뷰 수의 차.', ctrl: 'M을 1 m 올린 가짜 후보의 S가 S_M보다 얼마나 낮은가(같은 셀).', edge: '후보 높이장 렌더의 깊이 에지에서 영상 Canny 에지까지의 거리 중앙값 차.',
      r2: 'P_3Da + P_3Db + [n_pairs(M) ≥ 3 ∨ n_pairs(P) ≥ 3].',
    }[mode];
    $('t2-counts').textContent = `${number(b.t2_view_count)} views · ${number(b.t2_pair_count)} pairs · ${number(b.chips.count)} chips`;
  }
  const option = stage === 'scene' ? $('scene-mode').selectedOptions[0] : $(`${stage}-mode`).selectedOptions[0];
  const titles = {scene: '장면', s1: '1 영역', t1: '2 증거 T1', t2: '2 증거 T2'};
  $('mode-title').textContent = `${titles[stage]} · ${option ? option.textContent : ''}`;
}
function renderAccounting() {
  const b = prisms[active].block;
  const t1rows = [];
  for (const [state, name] of Object.entries(b.state_names)) {
    const s = b.t1_per_state_summary[name]; if (!s) continue;
    t1rows.push([`${name} · cells / d med`, `${number(s.cells)} / ${s.core_d_median_m === null ? '—' : s.core_d_median_m.toFixed(2)} m`]);
    t1rows.push([`${name} · agree / pen / block`, `${s.f_agree_mean.toFixed(2)} / ${s.f_penetrate_mean.toFixed(2)} / ${s.f_block_mean.toFixed(2)}`]);
  }
  const t1met = Object.values(b.t1_expectation_checks).reduce((sum, item) => sum + (item.met || 0), 0);
  const t1tot = Object.values(b.t1_expectation_checks).reduce((sum, item) => sum + (item.total || 0), 0);
  t1rows.push(['T1 expectations met', `${t1met} / ${t1tot}`]);
  $('t1-accounting').innerHTML = t1rows.map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join('');
  const t2 = b.t2_per_state_summary; const rows = [['views / pairs', `${number(b.t2_view_count)} / ${number(b.t2_pair_count)}`]];
  for (const [state, name] of Object.entries(b.state_names)) {
    const s = t2[name] && (t2[name].planar || t2[name].all); if (!s) continue;
    rows.push([`${name} · pairs M/P med`, `${finite(s.n_pairs_m_median)} / ${finite(s.n_pairs_p_median)}`]);
    rows.push([`${name} · S_M / S_P / Δ`, `${finite(s.ncc_median_m)} / ${finite(s.ncc_median_p)} / ${finite(s.delta_median)}`]);
  }
  const ctrl = b.t2_controls || {};
  for (const name of ['M+z0.5', 'M+z1', 'M+z2', 'M+x1']) if (ctrl[name]) rows.push([`paired f(M > ${name})`, `${finite(ctrl[name].paired_f_m_over_ctrl)} (${number(ctrl[name].paired_pairs)} pairs)`]);
  for (const [state, item] of Object.entries(b.t2_expectation_checks || {})) rows.push([`T2 expectation ${state}`, `${item.met} / ${item.total} met`]);
  $('t2-accounting').innerHTML = rows.map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join('');
}

// ---------------------------------------------------------------- guided review cases (per prism; H_M sites expect P)
function evCases(pr) {
  const n = pr.block.cell_count; const A = pr.arrays.attr;
  const st = i => A[i * 8]; const rough = i => A[i * 8 + 1]; const v = (i, name) => t2v(pr, i, name);
  const sign = Number(pr.block.t2_expectations_before_run?.PRIOR_ABOVE?.delta_sign ?? 1) < 0 ? -1 : 1;
  const pick = (filter, score) => { let best = -1; let bestScore = -Infinity; for (let i = 0; i < n; i++) { if (!filter(i)) continue; const s = score(i); if (Number.isFinite(s) && s > bestScore) { bestScore = s; best = i; } } return best; };
  const who = sign > 0 ? 'M(현재 표면)' : 'P(2022 표면)';
  const other = sign > 0 ? 'P' : 'M';
  const expectA = sign > 0
    ? '기대: pairing = 옛 것이 위, 3D-b 관통, 3D-a d ≈ +2 m → 2022 지붕이 사라졌다. 채널: Δ > 0(빨강). 확인: chip에서 M 두 타일이 같은 무늬로 겹치고 P 두 타일은 어긋나면 숫자가 사진과 같은 말을 한다. 결론은 "이 셀의 2D-a는 믿을 만하다"까지이며 판정이 아니다.'
    : '기대: pairing = 옛 것이 위(ALS 능선이 MVS 지붕보다 높음), 3D-b 관통 — 3D만 보면 파일럿의 사라진 지붕과 같은 서명이다. 그러나 사진에는 지붕이 있으므로 채널은 Δ < 0(파랑)이어야 한다. 확인: chip에서 P 두 타일이 겹치고 M 두 타일이 어긋나면 "MVS가 틀렸다(H_M)"를 사진이 말하는 것.';
  const expectB = sign > 0
    ? '기대: 지붕이 사라졌으니 Δ > 0이어야 한다. 채널: Δ ≤ 0. 확인: chip과 레코드에서 이유를 찾는다 — 쌍 수, 교차각, 창 안의 수목·그림자·차량. 이런 셀이 T3가 잡음으로 모델링할 사례다.'
    : '기대: 사진이 P를 설명해야 하므로 Δ < 0이어야 한다. 채널: Δ ≥ 0. 확인: chip과 레코드에서 이유를 찾는다 — MVS가 실제로 맞는 부분(톱니의 골)인가, 쌍 수가 적은가, 유리·반사인가.';
  const cases = [
    {key: 'A', title: `A · 옛 것이 위 — 채널이 ${who}를 가장 뚜렷하게 지지`, index: pick(i => st(i) === 2 && rough(i) === 0 && v(i, 'n_pairs_common') >= 3, i => sign * v(i, 'delta_median')), note: expectA},
    {key: 'B', title: `B · 옛 것이 위인데 채널이 ${other}를 지지 (기대와 다름)`, index: pick(i => st(i) === 2 && rough(i) === 0 && v(i, 'n_pairs_common') >= 3 && sign * v(i, 'delta_median') <= 0, i => -sign * v(i, 'delta_median')), note: expectB},
    {key: 'C', title: 'C · 양립 — 두 후보가 같은 자리, Δ ≈ 0', index: pick(i => st(i) === 1 && rough(i) === 0 && v(i, 'n_pairs_common') >= 3, i => -Math.abs(v(i, 'delta_median'))),
     note: '기대: 높이가 같으니(|dz| ≤ 0.3 m) 두 후보 모두 사진을 설명한다. 채널: Δ ≈ 0, S_M ≈ S_P. 확인: chip 네 타일이 모두 비슷해야 한다. 여기서 Δ가 크면 오탐이다.'},
    {key: 'D', title: 'D · 양립인데 유효 쌍이 없음 — 가시성 제한', index: pick(i => st(i) === 1 && rough(i) === 0 && v(i, 'n_pairs_m') === 0, i => t1v(pr, i, 'texture_median')),
     note: '기대: 텍스처는 있으나 이 셀을 함께 보는 사진 쌍(교차각 대역 안, 둘 다 가림 없음)이 없다. 채널: 값 없음 → r_t2에서 2D-a가 빠진다. 확인: 레코드의 유효 뷰 수·쌍 수.'},
    {key: 'E', title: 'E · 수목(거친 짝) — 표면이 아닌 자리', index: pick(i => st(i) === 3 && rough(i) === 1 && v(i, 'n_pairs_m') >= 1, i => v(i, 'n_pairs_m')),
     note: '기대: 수관은 표면이 아니라 어느 후보로 옮겨도 사진이 안 맞는다. 채널: S_M·S_P 모두 낮고 Δ 부호 불안정. 확인: chip 네 타일이 모두 흐트러지면 채널이 "판단 못 함"을 바르게 말하는 것.'},
    {key: 'F', title: 'F · 옛 것만 — 유보가 나와야 하는 자리', index: pick(i => st(i) === 4, i => v(i, 'n_views_p')),
     note: '기대: MVS가 없고 ALS만 있다. 채널: M 쌍 0. P의 쌍이 있으면 그 값이 유일한 사진 증거이고, 없으면 r_t2 0~1 = 구조적 유보(R5).'},
  ];
  return cases;
}
function populateCases(pr) {
  const select = $('t2-case'); select.innerHTML = '<option value="">— 고르면 셀로 이동 —</option>';
  pr.cases = evCases(pr);
  for (const item of pr.cases) { const o = document.createElement('option'); o.value = item.key; o.textContent = item.index >= 0 ? item.title : `${item.title} — 해당 셀 없음`; o.disabled = item.index < 0; select.appendChild(o); }
  $('t2-case-note').hidden = true;
}

// ---------------------------------------------------------------- selection
function clearSelection() {
  selectedPair = null;
  if (onlySelectedPair) { onlySelectedPair = false; $('only-selected-pair').checked = false; if (prisms[active].loaded) rebuildPrism(prisms[active]); }
  if (cellHighlight) { scene.remove(cellHighlight); cellHighlight.geometry.dispose(); cellHighlight.material.dispose(); cellHighlight = null; }
  if (selectionMarker) { scene.remove(selectionMarker); selectionMarker = null; }
  $('chip-panel').hidden = true;
  $('selection-details').innerHTML = '<div><dt>상태</dt><dd>셀 또는 core를 클릭하세요.</dd></div>';
}
function marker(local, radius) {
  if (selectionMarker) scene.remove(selectionMarker);
  selectionMarker = new THREE.Mesh(new THREE.SphereGeometry(radius, 16, 12), new THREE.MeshBasicMaterial({color: 0xffff00, wireframe: true, depthTest: false}));
  selectionMarker.position.fromArray(local); selectionMarker.renderOrder = 20; scene.add(selectionMarker);
}
function selectCell(pr, index) {
  const A = pr.arrays.attr; const state = A[index * 8]; const local = cellPosition(pr, index);
  const world = local.map((value, axis) => value + manifest.frame.world_shift_xyz_m[axis]);
  const t1 = name => finite(t1v(pr, index, name)); const t2 = name => finite(t2v(pr, index, name)); const t2i = name => number(t2v(pr, index, name));
  const viewName = id => (id >= 0 ? `${id} ${pr.block.t2_views[String(id)] || ''}` : 'none');
  const chipA = t2v(pr, index, 'chip_view_a'); const chipB = t2v(pr, index, 'chip_view_b');
  const b = pr.block; const dom = b.domain; const cm = b.cell_size_m;
  const fields = [
    ['prism / cell ix,iy', `${b.label} · ${Math.round((local[0] - dom.x[0]) / cm - 0.5)}, ${Math.round((local[1] - dom.y[0]) / cm - 0.5)}`],
    ['— 1 영역 (pairing) —', ''],
    ['상태', `${state} ${b.state_names[String(state)]}${A[index * 8 + 1] ? ' · ROUGH' : ''}`],
    ['patch MVS / ALS', `${pr.arrays.patch[index * 2]} / ${pr.arrays.patch[index * 2 + 1]}`],
    ['z MVS / ALS (dz)', `${finite(pr.arrays.z[index * 2])} / ${finite(pr.arrays.z[index * 2 + 1])} (${finite(pr.arrays.z[index * 2 + 1] - pr.arrays.z[index * 2])})`],
    ['— T1 3D-a —', ''],
    ['cores / d / LoD', `${number(t1v(pr, index, 'n_cores'))} / ${t1('core_d_median_m')} / ${t1('core_lod_median_m')}`],
    ['— T1 3D-b (rays) —', ''],
    ['agree / pen / block', `${number(t1v(pr, index, 'n_agree'))} / ${number(t1v(pr, index, 'n_penetrate'))} / ${number(t1v(pr, index, 'n_block'))}`],
    ['f_agree / f_pen / f_block', `${t1('f_agree')} / ${t1('f_penetrate')} / ${t1('f_block')}`],
    ['mvs_only / no_landing / occl', `${number(t1v(pr, index, 'n_mvs_only'))} / ${number(t1v(pr, index, 'n_no_landing'))} / ${number(t1v(pr, index, 'n_occluded'))}`],
    ['— T1 2D-c —', ''],
    ['texture / views / incidence', `${t1('texture_median')} / ${number(t1v(pr, index, 'n_views_unoccluded'))} / ${t1('incidence_best_deg')}°`],
    ['power 3D-a / 3D-b / r_t1', `${A[index * 8 + 2]} / ${A[index * 8 + 3]} / ${A[index * 8 + 6]}`],
    [`— T2 2D-a (θ ≤ ${b.t2_algorithm.ncc.summary_angle_max_deg}°) —`, ''],
    ['views valid M / P', `${t2i('n_views_m')} / ${t2i('n_views_p')}`],
    ['pairs M / P / common', `${t2i('n_pairs_m')} / ${t2i('n_pairs_p')} / ${t2i('n_pairs_common')}`],
    ['S_M med / fisher / f_good', `${t2('ncc_median_m')} / ${t2('ncc_fisher_m')} / ${t2('f_good_m')}`],
    ['S_P med / fisher / f_good', `${t2('ncc_median_p')} / ${t2('ncc_fisher_p')} / ${t2('f_good_p')}`],
    ['angle med M / P', `${t2('angle_median_m')}° / ${t2('angle_median_p')}°`],
    ['Δ med / f(M>P) / f(P>M)', `${t2('delta_median')} / ${t2('f_m_over_p')} / ${t2('f_p_over_m')}`],
    ['wide 3–60°: pairs M/P/common', `${t2i('n_pairs_wide_m')} / ${t2i('n_pairs_wide_p')} / ${t2i('n_pairs_common_wide')}`],
    ['wide: S_M / S_P / Δ', `${t2('ncc_median_wide_m')} / ${t2('ncc_median_wide_p')} / ${t2('delta_median_wide')}`],
    ['ctrl S M+z0.5 / +z1 / +z2 / +x1', `${t2('ncc_median_ctrl_0')} / ${t2('ncc_median_ctrl_1')} / ${t2('ncc_median_ctrl_2')} / ${t2('ncc_median_ctrl_3')}`],
    ['power 2D-a M / P / r_t2', `${A[index * 8 + 4]} / ${A[index * 8 + 5]} / ${A[index * 8 + 7]}`],
    ['— T2 2D-b —', ''],
    ['edge M: n / d_px / d_m', `${t2i('n_edge_px_m')} / ${t2('edge_dist_median_px_m')} / ${t2('edge_dist_median_m_m')}`],
    ['edge P: n / d_px / d_m', `${t2i('n_edge_px_p')} / ${t2('edge_dist_median_px_p')} / ${t2('edge_dist_median_m_p')}`],
    ['chip pair a / b', `${viewName(chipA)} / ${viewName(chipB)}`],
    ['chip angle / ρ_M / ρ_P', `${t2('chip_angle_deg')}° / ${t2('chip_ncc_m')} / ${t2('chip_ncc_p')}`],
    ['local XYZ', local.map(finite).join(', ')], ['world XYZ', world.map(finite).join(', ')],
  ];
  $('selection-details').innerHTML = fields.map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join('');
  if (cellHighlight) { scene.remove(cellHighlight); cellHighlight.geometry.dispose(); cellHighlight.material.dispose(); cellHighlight = null; }
  marker(local, 0.45);
  const members = [];
  for (let other = 0; other < b.cell_count; other++) if (pr.arrays.patch[other * 2] === pr.arrays.patch[index * 2] && pr.arrays.patch[other * 2 + 1] === pr.arrays.patch[index * 2 + 1]) members.push(other);
  const positions = new Float32Array(members.length * 3);
  members.forEach((other, output) => positions.set(cellPosition(pr, other), output * 3));
  cellHighlight = createPoints(positions, '#ffff00', 4, 0.8); cellHighlight.material.depthTest = false; cellHighlight.renderOrder = 19;
  selectedPair = [pr.arrays.patch[index * 2], pr.arrays.patch[index * 2 + 1]];
  if (onlySelectedPair) rebuildPrism(pr);
  const chip = b.chips.files[String(index)];
  if (chip) {
    $('chip-img').src = chip;
    $('chip-caption').textContent = `warp chip · cell ${index} · ${viewName(chipA)} ↔ ${viewName(chipB)} · θ ${t2('chip_angle_deg')}° · ρ_M ${t2('chip_ncc_m')} · ρ_P ${t2('chip_ncc_p')}`;
    $('chip-panel').hidden = false;
  } else $('chip-panel').hidden = true;
}
function selectCore(index) {
  const cls = coreAttr[index * 4]; const reason = manifest.reasons[String(coreAttr[index * 4 + 2])] || `reason ${coreAttr[index * 4 + 2]}`;
  const local = corePositions.subarray(index * 3, index * 3 + 3); const world = [...local].map((value, axis) => value + manifest.frame.world_shift_xyz_m[axis]);
  const metric = index * manifest.relations.metrics_stride;
  const cluster = hmCluster[index];
  const fields = [
    ['relation class', `${cls} ${manifest.classes[String(cls)].name}`], ['core source', coreAttr[index * 4 + 1] === 0 ? 'MVS core surface' : 'ALS core surface'],
    ['reason / robust', `${reason} / ${coreAttr[index * 4 + 3] === 1 ? 'YES' : 'NO'}`],
    ['M3C2 signed m / |d|/LoD95', `${finite(coreMetrics[metric])} / ${finite(coreMetrics[metric + 3])}`],
    ['support MVS / ALS', `${number(coreSupport[index * 2])} / ${number(coreSupport[index * 2 + 1])}`],
    ['H_M zone', hmFlag[index] ? `elevated class-4 core · cluster ${cluster || '(< min area)'}` : 'no'],
    ['prior-quality zone', qFlag[index] ? `σ_MVS ${finite(coreMetrics[metric + 4])} ≥ 3 σ_ALS ${finite(coreMetrics[metric + 5])} · cluster ${qCluster[index] || '(< min area)'}` : `no (σ_MVS ${finite(coreMetrics[metric + 4])} / σ_ALS ${finite(coreMetrics[metric + 5])})`],
    ['local XYZ', [...local].map(finite).join(', ')], ['world XYZ', world.map(finite).join(', ')],
  ];
  $('selection-details').innerHTML = fields.map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join('');
  if (cellHighlight) { scene.remove(cellHighlight); cellHighlight = null; }
  $('chip-panel').hidden = true;
  marker([...local], 1.25);
}

// ---------------------------------------------------------------- stage / prism switching
function applyDim() {
  const dim = stage !== 'scene' && $('ev-dim').checked;
  const factor = dim ? 0.22 : 1;
  const raw = {mvs: $('show-raw-m').checked, als: $('show-raw-p').checked};
  for (const [key, points] of Object.entries(sourceObjects)) {
    const lift = stage !== 'scene' && raw[key];
    points.material.opacity = lift ? Math.max(0.6, Number($('source-opacity').value)) : Number($('source-opacity').value) * factor;
    points.material.transparent = points.material.opacity < 1;
    points.visible = $(key === 'mvs' ? 'show-mvs' : 'show-als').checked || lift;
  }
  coreObject.material.opacity = factor; coreObject.material.transparent = factor < 1;
}
async function setStage(name) {
  stage = name;
  document.querySelectorAll('[data-stage]').forEach(button => button.classList.toggle('active', button.dataset.stage === name));
  for (const section of document.querySelectorAll('.stage')) section.hidden = section.id !== `stage-${name}`;
  const pr = prisms[active];
  if (name !== 'scene') { await loadPrism(pr); rebuildPrism(pr); }
  for (const item of prisms) if (item.object) applyCellVisibility(item);
  $('split-panel').hidden = name === 'scene';
  for (const box of hmBoxes) box.visible = name === 'scene' && box.visible;
  if (name === 'scene') updateHmBoxes();
  applyDim(); renderStageLegend();
  if (name === 'scene') renderSceneLegend();
}
async function setActivePrism(index) {
  active = index; const pr = prisms[active];
  $('prism-note').textContent = pr.block.site_note;
  await loadPrism(pr); rebuildPrism(pr); populateCases(pr); renderAccounting(); clearSelection();
  const t1 = pr.block.t1_per_state_summary;
  document.querySelectorAll('[data-state]').forEach(input => { const name = pr.block.state_names[input.dataset.state]; input.closest('.class-row').querySelector('.class-count').textContent = t1[name] ? number(t1[name].cells) : '0'; });
  for (const item of prisms) if (item.object) applyCellVisibility(item);
  renderStageLegend();
}
function focusPrism(pr) { const d = pr.block.domain; setView('oblique', new THREE.Vector3((d.x[0] + d.x[1]) / 2, (d.y[0] + d.y[1]) / 2, (d.z[0] + d.z[1]) / 2), Math.max(d.x[1] - d.x[0], d.y[1] - d.y[0]) * 0.8); }
function showImage(pr, key) {
  const titles = {t2_on_image: `${pr.block.label} · T2 2D-a on the current TOP image (S_M / S_P / Δ; display only)`};
  $('image-title').textContent = titles[key] || key; $('image-view').src = pr.block.images[key].path; $('image-panel').hidden = false;
}

// ---------------------------------------------------------------- wiring
for (const [index, pr] of prisms.entries()) { const o = document.createElement('option'); o.value = String(index); o.textContent = pr.block.label; $('prism-select').appendChild(o); }
for (const tile of manifest.active_tiles) { const o = document.createElement('option'); o.value = tile.tile_id; o.textContent = `${tile.tile_id} · ${number(tile.relation_rows)}`; $('tile-select').appendChild(o); }
document.querySelectorAll('[data-stage]').forEach(button => button.addEventListener('click', () => setStage(button.dataset.stage)));
$('prism-select').addEventListener('change', async event => { await setActivePrism(Number(event.target.value)); focusPrism(prisms[active]); });
{
  const names = manifest.prisms[0].state_names; const colors = manifest.prisms[0].state_colors; const root = $('state-filter');
  for (const [key, name] of Object.entries(names)) {
    const row = document.createElement('label'); row.className = 'class-row';
    row.innerHTML = `<input type="checkbox" data-state="${key}" checked><i class="swatch" style="background:${colors[key]}"></i><span class="class-name">${key} ${name}</span><span class="class-count"></span>`;
    row.querySelector('input').addEventListener('change', event => { stateFilter[Number(key)] = event.target.checked; rebuildPrism(prisms[active]); });
    root.appendChild(row);
  }
}
$('show-cells-m').addEventListener('change', event => { showCells.m = event.target.checked; applyCellVisibility(prisms[active]); });
$('show-cells-p').addEventListener('change', event => { showCells.p = event.target.checked; applyCellVisibility(prisms[active]); });
$('show-raw-m').addEventListener('change', applyDim);
$('show-raw-p').addEventListener('change', applyDim);
$('only-selected-pair').addEventListener('change', event => { onlySelectedPair = event.target.checked; rebuildPrism(prisms[active]); });
$('view-prism').addEventListener('click', () => focusPrism(prisms[active]));
$('view-scene').addEventListener('click', () => setView('oblique'));
$('clear-selection').addEventListener('click', clearSelection);
$('scene-mode').addEventListener('change', event => { sceneMode = event.target.value; updateCoreColors(); updateHmBoxes(); renderSceneLegend(); renderStageLegend(); });
$('hm-boundary').addEventListener('change', () => { updateHmBoxes(); renderHmList(); renderQualityList(); });
for (const st of ['s1', 't1', 't2']) $(`${st}-mode`).addEventListener('change', event => { modes[st] = event.target.value; rebuildPrism(prisms[active]); renderStageLegend(); });
$('t2-case').addEventListener('change', event => {
  const pr = prisms[active]; const item = (pr.cases || []).find(c => c.key === event.target.value);
  if (!item || item.index < 0) { $('t2-case-note').hidden = true; return; }
  $('t2-case-note').textContent = item.note; $('t2-case-note').hidden = false;
  if (modes.t2 !== 'delta') { modes.t2 = 'delta'; $('t2-mode').value = 'delta'; rebuildPrism(pr); renderStageLegend(); }
  selectCell(pr, item.index);
  const [x, y, z] = cellPosition(pr, item.index); setView('oblique', new THREE.Vector3(x, y, z), 7);
});
$('image-top').addEventListener('click', () => showImage(prisms[active], 't2_on_image'));
$('image-close').addEventListener('click', () => { $('image-panel').hidden = true; });
window.addEventListener('keydown', event => { if (event.key === 'Escape') $('image-panel').hidden = true; });
$('show-mvs').addEventListener('change', event => { sourceObjects.mvs.visible = event.target.checked; });
$('show-als').addEventListener('change', event => { sourceObjects.als.visible = event.target.checked; });
$('show-cores').addEventListener('change', event => { coreObject.visible = event.target.checked; });
$('source-opacity').addEventListener('input', event => { event.target.nextElementSibling.value = event.target.value; applyDim(); });
$('core-size').addEventListener('input', event => { event.target.nextElementSibling.value = event.target.value; coreObject.material.size = Number(event.target.value); });
$('cell-size').addEventListener('input', event => { event.target.nextElementSibling.value = event.target.value; for (const pr of prisms) if (pr.object) { pr.object.material.size = Number(event.target.value); pr.objectP.material.size = Math.max(1, Number(event.target.value) * 0.7); } });
$('ev-dim').addEventListener('change', applyDim);
$('ev-xray').addEventListener('change', event => { for (const pr of prisms) if (pr.object) { pr.object.material.depthTest = !event.target.checked; pr.object.material.needsUpdate = true; pr.objectP.material.depthTest = !event.target.checked; pr.objectP.material.needsUpdate = true; } });
$('tile-select').addEventListener('change', event => {
  if (!event.target.value) return setView('oblique');
  const tile = manifest.active_tiles.find(item => item.tile_id === event.target.value);
  setView('oblique', new THREE.Vector3(...tile.scene_local_center), tile.focus_radius_m);
});

const raycaster = new THREE.Raycaster(); const pointer = new THREE.Vector2();
renderer.domElement.addEventListener('click', event => {
  const bounds = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1; pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const pr = prisms[active];
  if (stage !== 'scene' && pr.object && pr.object.visible) {
    raycaster.params.Points.threshold = 0.4;
    const hits = raycaster.intersectObject(pr.object, false);
    if (hits.length) { const best = hits.reduce((a, b) => (b.distanceToRay < a.distanceToRay ? b : a)); selectCell(pr, best.index); return; }
  }
  if (coreObject.visible) {
    raycaster.params.Points.threshold = 2.0;
    const hit = raycaster.intersectObject(coreObject, false)[0];
    if (hit) selectCore(hit.index);
  }
});
const resize = () => { const width = Math.max(1, viewport.clientWidth); const height = Math.max(1, viewport.clientHeight); renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix(); };
new ResizeObserver(resize).observe(viewport); resize();

renderSceneLegend(); renderHmList(); renderQualityList(); updateHmBoxes();
await setActivePrism(0);
setView('oblique');
$('view-summary').textContent = `${number(manifest.sources.mvs.count)} MVS · ${number(manifest.sources.als.count)} ALS · ${number(coreCount)} cores · ${prisms.length} prism`;
setStatus(`ready · ${number(coreCount)} cores / ${prisms.length} prism / ${number(hz.clusters.length)} H_M clusters`);
function frame() { controls.update(); renderer.render(scene, camera); requestAnimationFrame(frame); }
frame();
