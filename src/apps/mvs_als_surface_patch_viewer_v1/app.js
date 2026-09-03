import * as THREE from 'three';
import * as GaussianSplats3D from './lib/gaussian-splats-3d.module.min.js';

const $ = id => document.getElementById(id);
const status = $('status');
const viewport = $('viewport');
const number = value => Number(value).toLocaleString('ko-KR');
const finite = value => Number.isFinite(value) ? Number(value).toFixed(3) : 'NA';
const decoder = new TextDecoder('ascii');

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

function hexRgb(value) {
  const color = new THREE.Color(value);
  return [color.r, color.g, color.b];
}

function uidRgb(uid) {
  let hash = 2166136261;
  for (let index = 0; index < uid.length; index++) {
    hash ^= uid.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  const color = new THREE.Color();
  color.setHSL(((hash >>> 0) % 360) / 360, 0.72, 0.57);
  return [color.r, color.g, color.b];
}

function lerpRgb(fromHex, toHex, t) {
  const a = new THREE.Color(fromHex);
  const b = new THREE.Color(toHex);
  a.lerp(b, Math.min(1, Math.max(0, t)));
  return [a.r, a.g, a.b];
}

function rampRgb(t) {
  // 0 -> blue, 0.5 -> yellow, 1 -> red
  if (!Number.isFinite(t)) return hexRgb('#475569');
  return t < 0.5 ? lerpRgb('#3b82f6', '#facc15', t * 2) : lerpRgb('#facc15', '#ef4444', (t - 0.5) * 2);
}

const manifestResponse = await fetch('viewer_manifest.json', {cache: 'no-store'});
if (!manifestResponse.ok) throw new Error(`viewer_manifest.json: HTTP ${manifestResponse.status}`);
const manifest = await manifestResponse.json();
if (manifest.scientific_verdict !== null) throw new Error('scientific_verdict must remain null');
if (manifest.comparison_contract.m3c2_recomputed !== false) throw new Error('M3C2 recomputation contract drift');

const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'high-performance'});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
viewport.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 5000);
camera.up.set(0, 0, 1);
const controls = new GaussianSplats3D.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.screenSpacePanning = true;
controls.minDistance = 0.5;
controls.maxDistance = 3000;

const center = new THREE.Vector3(...manifest.bounds.scene_local.center);
const extent = new THREE.Vector3(...manifest.bounds.scene_local.extent);
const sceneRadius = Math.max(extent.x, extent.y, extent.z * 2, 40) * 0.62;
const grid = new THREE.GridHelper(Math.ceil(sceneRadius * 2.4 / 25) * 25, Math.ceil(sceneRadius * 2.4 / 25), 0x35506b, 0x1b2a3a);
grid.rotation.x = Math.PI / 2;
grid.position.set(center.x, center.y, manifest.bounds.scene_local.min[2] - 1);
grid.material.opacity = 0.45;
grid.material.transparent = true;
scene.add(grid);
const axes = new THREE.AxesHelper(Math.min(35, sceneRadius * 0.15));
axes.position.copy(grid.position);
scene.add(axes);

const sourceObjects = {};
const rawObjects = new Map();
const patchObjects = new Map();
let activeObjects = rawObjects;
let centroidObject = null;
let selectionMarker = null;
let patchHighlight = null;
let currentMode = 'raw';
let relationPositions;
let relationLabels;
let relationMetrics;
let relationSupport;
let patchIds;
let patchAttributes;
let patchCoreCounts;
let patchMetrics;
let summaryIds;
let summaryAttributes;
let summaryPose;
let summaryMetrics;
let summaryUidBytes;
const summaryRowByPatch = new Map();
const uidByPatch = new Map();
const uidColorByPatch = new Map();

// ---- T0 region units (display-only) ----
const ru = manifest.region_units || null;
const t0Objects = {};
let t0Xyz; let t0Attr; let t0Unit; let t0Metrics;
let t0UnitIds; let t0UnitAttr; let t0UnitPose; let t0UnitMetrics; let t0UnitUidBytes; let t0Adjacency;
const PAIR_RULE_COLORS = {0: '#c4b5fd', 1: '#22c55e', 2: '#86efac', 3: '#facc15', 4: '#f97316', 5: '#ef4444', 6: '#38bdf8'};
const t0UidByUnit = new Map();
const t0UidColorByUnit = new Map();
const t0Neighbors = new Map();
let t0Mode = 'uid';
let t0Highlight = null;
let t0BoxHelper = null;
let prismHelper = null;
let dimmed = false;

function createPoints(positions, color, size, opacity = 1, vertexColors = null) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  if (vertexColors) geometry.setAttribute('color', new THREE.BufferAttribute(vertexColors, 3));
  geometry.computeBoundingSphere();
  const material = new THREE.PointsMaterial({
    color: vertexColors ? 0xffffff : color,
    vertexColors: Boolean(vertexColors),
    size,
    sizeAttenuation: false,
    transparent: opacity < 1,
    opacity,
    depthWrite: false,
  });
  const points = new THREE.Points(geometry, material);
  scene.add(points);
  return points;
}

function relationClass(index, basis) {
  return basis === 'patch' ? patchAttributes[index * 4] : relationLabels[index * 4];
}

function colorForCore(index, mode) {
  if (mode === 'raw') return hexRgb(manifest.classes[String(relationLabels[index * 4])].color);
  if (mode === 'patch') return hexRgb(manifest.classes[String(patchAttributes[index * 4])].color);
  if (mode === 'source') return hexRgb(manifest.source_family_colors[String(patchAttributes[index * 4 + 1])]);
  if (mode === 'status') return hexRgb(manifest.patch_statuses[String(patchAttributes[index * 4 + 2])].color);
  const patchId = patchIds[index];
  return patchId === 0 ? hexRgb('#475569') : uidColorByPatch.get(patchId);
}

function createCoreGroups(basis, objects) {
  for (let classId = 1; classId <= 5; classId++) {
    const ids = [];
    for (let index = 0; index < manifest.relations.count; index++) {
      if (relationClass(index, basis) === classId) ids.push(index);
    }
    const positions = new Float32Array(ids.length * 3);
    const colors = new Float32Array(ids.length * 3);
    ids.forEach((index, row) => {
      positions.set(relationPositions.subarray(index * 3, index * 3 + 3), row * 3);
      colors.set(colorForCore(index, basis === 'patch' ? 'patch' : 'raw'), row * 3);
    });
    const points = createPoints(positions, 0xffffff, Number($('relation-size').value), 1, colors);
    points.renderOrder = 10;
    points.userData = {kind: 'relation', basis, classId, originalIndices: Uint32Array.from(ids)};
    objects.set(classId, points);
  }
}

function updateObjectColors(objects, mode) {
  for (const points of objects.values()) {
    const ids = points.userData.originalIndices;
    const colors = points.geometry.getAttribute('color');
    for (let row = 0; row < ids.length; row++) {
      const rgb = colorForCore(ids[row], mode);
      colors.setXYZ(row, rgb[0], rgb[1], rgb[2]);
    }
    colors.needsUpdate = true;
  }
}

function summaryUid(row) {
  return decoder.decode(summaryUidBytes.subarray(row * 20, row * 20 + 20)).replaceAll('\0', '');
}

function colorForSummary(row, mode) {
  if (mode === 'raw') return hexRgb(manifest.classes[String(summaryAttributes[row * 4 + 3])].color);
  if (mode === 'patch') return hexRgb(manifest.classes[String(summaryAttributes[row * 4 + 1])].color);
  if (mode === 'source') return hexRgb(manifest.source_family_colors[String(summaryAttributes[row * 4])]);
  if (mode === 'status') return hexRgb(manifest.patch_statuses[String(summaryAttributes[row * 4 + 2])].color);
  return uidColorByPatch.get(summaryIds[row * 7]);
}

function createCentroids() {
  const positions = new Float32Array(manifest.patches.patch_count * 3);
  const colors = new Float32Array(manifest.patches.patch_count * 3);
  for (let row = 0; row < manifest.patches.patch_count; row++) {
    positions.set(summaryPose.subarray(row * 6, row * 6 + 3), row * 3);
    colors.set(colorForSummary(row, currentMode), row * 3);
  }
  centroidObject = createPoints(positions, 0xffffff, 5.5, 0.9, colors);
  centroidObject.renderOrder = 12;
  centroidObject.visible = false;
  centroidObject.userData.kind = 'centroids';
}

function updateCentroidColors() {
  const colors = centroidObject.geometry.getAttribute('color');
  for (let row = 0; row < manifest.patches.patch_count; row++) {
    const rgb = colorForSummary(row, currentMode);
    colors.setXYZ(row, rgb[0], rgb[1], rgb[2]);
  }
  colors.needsUpdate = true;
}

function classBasis() {
  return currentMode === 'patch' ? 'patch' : 'raw';
}

function classCounts() {
  return classBasis() === 'patch' ? manifest.patches.patch_class_counts : manifest.patches.raw_class_counts;
}

function updateClassControls() {
  const counts = classCounts();
  $('class-basis').textContent = `${classBasis()} relation filter`;
  document.querySelectorAll('[data-class]').forEach(input => {
    input.closest('.class-row').querySelector('.class-count').textContent = number(counts[input.dataset.class]);
  });
}

function updateVisibility() {
  const active = classBasis() === 'patch' ? patchObjects : rawObjects;
  activeObjects = active;
  for (const objects of [rawObjects, patchObjects]) {
    for (const [classId, points] of objects) {
      const checked = document.querySelector(`[data-class="${classId}"]`).checked;
      points.visible = objects === active && checked;
    }
  }
  const visible = [...active].reduce((sum, [classId, points]) => sum + (points.visible ? Number(classCounts()[String(classId)]) : 0), 0);
  $('view-summary').textContent = `${number(manifest.sources.mvs.count)} MVS · ${number(manifest.sources.als.count)} ALS · ${number(visible)} visible cores · ${number(manifest.patches.patch_count)} patches`;
}

function applyMode(mode) {
  currentMode = mode;
  $('color-mode').value = mode;
  document.querySelectorAll('[data-mode]').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
  const active = mode === 'patch' ? patchObjects : rawObjects;
  updateObjectColors(active, mode);
  updateCentroidColors();
  const titles = {
    raw: 'before · raw five-class cores',
    patch: 'after · connected patch five-class',
    uid: 'after · stable patch UID colors',
    source: 'patch source family',
    status: 'patch aggregation status',
  };
  const notes = {
    raw: '동결된 M3C2/support core 라벨. 아직 연결 patch가 아니다.',
    patch: 'source별 기하 연결 뒤 patch 단위로 집계한 라벨. 작은·혼합 patch는 5로 기각된다.',
    uid: '같은 색은 같은 stable patch UID다. 회색은 연결 bridge에서 제외된 core다.',
    source: 'cyan=MVS core surface · violet=Existing ALS core surface. 서로 한 patch로 합치지 않는다.',
    status: 'stable, small island, mixed ambiguity, non-comparable 및 unassigned 상태를 표시한다.',
  };
  $('mode-title').textContent = titles[mode];
  $('mode-note').textContent = notes[mode];
  updateClassControls();
  updateVisibility();
}

function buildClassControls() {
  const root = $('class-controls');
  for (const [key, item] of Object.entries(manifest.classes)) {
    const row = document.createElement('label');
    row.className = 'class-row';
    row.innerHTML = `<input type="checkbox" data-class="${key}" checked><i class="swatch" style="background:${item.color}"></i><span class="class-name">${key} ${item.name}</span><span class="class-count"></span>`;
    row.querySelector('input').addEventListener('change', updateVisibility);
    root.appendChild(row);
  }
  const legend = $('status-legend');
  for (const [key, item] of Object.entries(manifest.patch_statuses)) {
    const entry = document.createElement('span');
    entry.innerHTML = `<i class="swatch" style="background:${item.color}"></i><em>${key} ${item.name}</em>`;
    legend.appendChild(entry);
  }
}

function setView(kind, target = center, radius = sceneRadius) {
  controls.target.copy(target);
  if (kind === 'top') camera.position.set(target.x, target.y, target.z + radius * 2.2);
  else camera.position.set(target.x + radius * 0.9, target.y - radius * 1.25, target.z + radius * 0.8);
  camera.near = Math.max(0.05, radius / 2000);
  camera.far = Math.max(3000, radius * 12);
  camera.updateProjectionMatrix();
  controls.update();
}

function selectCore(index) {
  const raw = relationLabels[index * 4];
  const source = patchAttributes[index * 4 + 1] === 0 ? 'MVS core surface' : 'ALS core surface';
  const reason = manifest.reasons[String(relationLabels[index * 4 + 2])] || `reason ${relationLabels[index * 4 + 2]}`;
  const robust = relationLabels[index * 4 + 3] === 1;
  const patchId = patchIds[index];
  const patchClass = patchAttributes[index * 4];
  const patchStatus = patchAttributes[index * 4 + 2];
  const unassigned = patchAttributes[index * 4 + 3];
  const local = relationPositions.subarray(index * 3, index * 3 + 3);
  const world = [...local].map((value, axis) => value + manifest.frame.world_shift_xyz_m[axis]);
  const metric = index * manifest.relations.metrics_stride;
  const support = index * 2;
  const fields = [
    ['raw label', `${raw} ${manifest.classes[String(raw)].name}`],
    ['patch label', `${patchClass} ${manifest.classes[String(patchClass)].name}`],
    ['core source', source],
    ['raw reason', reason],
    ['raw robust', robust ? 'YES' : 'NO'],
    ['local XYZ', [...local].map(value => value.toFixed(2)).join(', ')],
    ['world XYZ', world.map(value => value.toFixed(2)).join(', ')],
    ['M3C2 signed m', finite(relationMetrics[metric])],
    ['|d| / LoD95', finite(relationMetrics[metric + 3])],
    ['support MVS / ALS', `${number(relationSupport[support])} / ${number(relationSupport[support + 1])}`],
    ['patch ID', patchId || '0 · unassigned'],
    ['patch status', `${patchStatus} ${manifest.patch_statuses[String(patchStatus)].name}`],
    ['unassigned reason', `${unassigned} ${manifest.unassigned_reasons[String(unassigned)]}`],
    ['member count', number(patchCoreCounts[index])],
    ['purity / radius m', `${finite(patchMetrics[index * 2])} / ${finite(patchMetrics[index * 2 + 1])}`],
  ];
  if (patchId > 0) {
    const row = summaryRowByPatch.get(patchId);
    const id = row * 7;
    const attr = row * 4;
    const pose = row * 6;
    const metrics = row * 11;
    fields.push(
      ['patch UID', uidByPatch.get(patchId)],
      ['dominant raw', `${summaryAttributes[attr + 3]} ${manifest.classes[String(summaryAttributes[attr + 3])].name}`],
      ['centroid', [...summaryPose.subarray(pose, pose + 3)].map(value => finite(value)).join(', ')],
      ['normal', [...summaryPose.subarray(pose + 3, pose + 6)].map(value => finite(value)).join(', ')],
      ['bbox diag / area', `${finite(summaryMetrics[metrics + 1])} m / ${finite(summaryMetrics[metrics + 7])} m²`],
      ['plane RMSE / p95 / max', `${finite(summaryMetrics[metrics + 2])} / ${finite(summaryMetrics[metrics + 3])} / ${finite(summaryMetrics[metrics + 4])} m`],
      ['normal p95 / max', `${finite(summaryMetrics[metrics + 5])} / ${finite(summaryMetrics[metrics + 6])}°`],
      ['purity / robust / variation', `${finite(summaryMetrics[metrics + 8])} / ${finite(summaryMetrics[metrics + 9])} / ${finite(summaryMetrics[metrics + 10])}`],
      ['raw 1·2·3·4·5', [...summaryIds.subarray(id + 2, id + 7)].map(number).join(' · ')],
    );
  }
  $('selection-details').innerHTML = fields.map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join('');
  if (selectionMarker) scene.remove(selectionMarker);
  selectionMarker = new THREE.Mesh(
    new THREE.SphereGeometry(1.25, 16, 12),
    new THREE.MeshBasicMaterial({color: 0xffff00, wireframe: true, depthTest: false}),
  );
  selectionMarker.position.fromArray(local);
  selectionMarker.renderOrder = 20;
  scene.add(selectionMarker);
  clearPatchHighlight();
  if (ru) clearT0Selection();
  const ids = [];
  if (patchId === 0) ids.push(index);
  else for (let row = 0; row < patchIds.length; row++) if (patchIds[row] === patchId) ids.push(row);
  const positions = new Float32Array(ids.length * 3);
  ids.forEach((row, output) => positions.set(relationPositions.subarray(row * 3, row * 3 + 3), output * 3));
  patchHighlight = createPoints(positions, '#ffff00', 8, 1);
  patchHighlight.material.depthTest = false;
  patchHighlight.renderOrder = 19;
}

function t0UnitUid(row) {
  return decoder.decode(t0UnitUidBytes.subarray(row * 16, row * 16 + 16)).replaceAll('\0', '');
}

function t0ColorForCell(index, mode) {
  const unitId = t0Unit[index];
  const row = unitId - 1;
  const source = t0Attr[index * 5];
  const role = t0Attr[index * 5 + 1];
  const kind = t0Attr[index * 5 + 2];
  const primary = t0Attr[index * 5 + 3];
  const pairRule = t0Attr[index * 5 + 4];
  const pairDistance = t0Metrics[index * 2 + 1];
  const colors = ru.colors;
  if (mode === 'uid') return t0UidColorByUnit.get(unitId);
  if (mode === 'kind') return hexRgb(colors.kind[String(kind)]);
  if (mode === 'primary') return hexRgb(colors.primary[String(primary)]);
  if (mode === 'role') return hexRgb(colors.role[String(role)]);
  if (mode === 'pairing') {
    if (source === 0) return hexRgb(colors.pairing.mvs);
    if (pairRule === 6) return hexRgb('#38bdf8');
    return hexRgb(pairRule > 0 ? colors.pairing.als_paired : colors.pairing.als_prior_only);
  }
  if (mode === 'pairrule') {
    if (source === 0) return hexRgb('#334155');
    return hexRgb(PAIR_RULE_COLORS[pairRule] || '#ffffff');
  }
  if (mode === 'layer') {
    const spread = t0UnitMetrics[row * 16 + 14];
    const reason = t0UnitAttr[row * 6 + 4];
    const mixed = t0UnitAttr[row * 6 + 5];
    if (primary === 1) return hexRgb('#334155');
    if (reason === 2) return hexRgb('#f472b6');
    if (mixed === 1) return hexRgb('#f59e0b');
    return Number.isFinite(spread) ? lerpRgb('#22c55e', '#facc15', spread / ru.profile.prior_layer_split_offset_m) : hexRgb('#475569');
  }
  if (mode === 'cores') {
    const cores = t0UnitIds[row * 14 + 8];
    return cores === 0 ? hexRgb('#ef4444') : lerpRgb('#facc15', '#22c55e', Math.min(1, cores / 8));
  }
  if (mode === 'support') {
    if (source === 1) return hexRgb('#334155');
    const support = t0UnitMetrics[row * 16 + 6];
    if (!Number.isFinite(support)) return hexRgb('#475569');
    return support < 0.5 ? lerpRgb('#ef4444', '#f59e0b', support * 2) : lerpRgb('#f59e0b', '#22c55e', (support - 0.5) * 2);
  }
  if (mode === 'pairdist') {
    if (source === 0) return hexRgb('#334155');
    if (!Number.isFinite(pairDistance)) return hexRgb(colors.pairing.als_prior_only);
    return rampRgb(pairDistance / ru.profile.pair_normal_half_length_m);
  }
  if (mode === 'tilt') {
    const tilt = t0UnitMetrics[row * 16 + 5];
    return Number.isFinite(tilt) ? rampRgb(tilt / 90) : hexRgb('#475569');
  }
  return hexRgb('#ffffff');
}

function createT0Layer() {
  for (const [source, key] of [[0, 'mvs'], [1, 'als']]) {
    const ids = [];
    for (let index = 0; index < ru.cell_count; index++) if (t0Attr[index * 5] === source) ids.push(index);
    const positions = new Float32Array(ids.length * 3);
    const colors = new Float32Array(ids.length * 3);
    ids.forEach((index, row) => {
      positions.set(t0Xyz.subarray(index * 3, index * 3 + 3), row * 3);
      colors.set(t0ColorForCell(index, t0Mode), row * 3);
    });
    const points = createPoints(positions, 0xffffff, Number($('t0-size').value), 1, colors);
    points.renderOrder = 14;
    points.userData = {kind: 't0', source, originalIndices: Uint32Array.from(ids)};
    t0Objects[key] = points;
  }
  const d = ru.domain;
  const box = new THREE.Box3(new THREE.Vector3(d.x[0], d.y[0], d.z[0]), new THREE.Vector3(d.x[1], d.y[1], d.z[1]));
  prismHelper = new THREE.Box3Helper(box, 0xf472b6);
  prismHelper.renderOrder = 15;
  scene.add(prismHelper);
}

function updateT0Colors() {
  for (const points of Object.values(t0Objects)) {
    const ids = points.userData.originalIndices;
    const colors = points.geometry.getAttribute('color');
    for (let row = 0; row < ids.length; row++) {
      const rgb = t0ColorForCell(ids[row], t0Mode);
      colors.setXYZ(row, rgb[0], rgb[1], rgb[2]);
    }
    colors.needsUpdate = true;
  }
}

function renderT0Legend() {
  const legend = $('t0-legend');
  legend.innerHTML = '';
  const add = (color, text) => {
    const entry = document.createElement('span');
    entry.innerHTML = `<i class="swatch" style="background:${color}"></i><em>${text}</em>`;
    legend.appendChild(entry);
  };
  const bar = (from, via, to, low, high) => {
    const entry = document.createElement('span');
    entry.className = 'bar';
    entry.innerHTML = `<em>${low}</em><i style="background:linear-gradient(90deg,${from},${via},${to})"></i><em>${high}</em>`;
    legend.appendChild(entry);
  };
  const colors = ru.colors;
  const acc = ru.accounting;
  if (t0Mode === 'uid') add('#888', '같은 색 = 같은 unit UID (ALS 셀은 짝지어진 MVS 단위 색)');
  if (t0Mode === 'kind') { add(colors.kind['0'], '0 PLANAR'); add(colors.kind['1'], '1 ROUGH'); }
  if (t0Mode === 'primary') { add(colors.primary['0'], 'MVS-primary unit'); add(colors.primary['1'], 'prior-only unit'); }
  if (t0Mode === 'role') { add(colors.role['0'], 'PLANAR_CORE'); add(colors.role['1'], 'ROUGH_MEMBER'); add(colors.role['2'], 'ABSORBED_SMALL'); }
  if (t0Mode === 'pairing') {
    add(colors.pairing.als_paired, `ALS paired · ${number(acc.criterion_4_pairing.als_cells_paired)}`);
    add(colors.pairing.als_prior_only, `ALS prior-only zone · ${number(acc.criterion_4_pairing.als_cells_prior_only_zone)}`);
    add('#38bdf8', `ALS small component absorbed into MVS unit · ${number(acc.criterion_4_pairing.pair_rule_counts.ABSORBED_SMALL_PRIOR_COMPONENT_INTO_MVS_UNIT || 0)}`);
    add(colors.pairing.mvs, 'MVS cell');
  }
  if (t0Mode === 'pairrule') for (const [key, name] of Object.entries(ru.pair_rule_names)) add(PAIR_RULE_COLORS[Number(key)], `${key} ${name} · ${number(acc.criterion_4_pairing.pair_rule_counts[name])}`);
  if (t0Mode === 'layer') { add('#f472b6', 'split by prior layer (all pieces of a carved parent)'); add('#f59e0b', 'mixed_prior (planar: layer footprint < A_min; rough: spread only, never carved)'); add('#475569', 'MVS unit without prior side'); add('#334155', 'prior-only unit'); bar('#22c55e', '#facc15', '#facc15', 'spread 0', `${ru.profile.prior_layer_split_offset_m} m`); }
  if (t0Mode === 'cores') { add('#ef4444', '0 relation cores in unit'); bar('#facc15', '#22c55e', '#22c55e', '1', '8+'); }
  if (t0Mode === 'support') bar('#ef4444', '#f59e0b', '#22c55e', 'f_P 0', '1');
  if (t0Mode === 'pairdist') bar('#3b82f6', '#facc15', '#ef4444', '0 m', `${ru.profile.pair_normal_half_length_m} m`);
  if (t0Mode === 'tilt') bar('#3b82f6', '#facc15', '#ef4444', '0° (수평)', '90° (벽)');
  const notes = {
    uid: '단위 = 책임 하나가 붙는 자리. 소스별 작업 셀(0.25 m) 위의 결정론적 평면 region growing + 규모 상한 + 거친 영역 + M3C2 창 pairing.',
    kind: 'PLANAR = 평면 세그먼트(면적 ≥ A_min), ROUGH = 잔여 연결 성분. 판정이 아니라 기하 종류다.',
    primary: 'MVS가 있는 곳은 MVS 세그먼트가 단위, prior-only 지대는 ALS 세그먼트가 단위.',
    pairing: 'ALS 셀이 MVS 단위의 발자국 안·법선 거리 ≤ 3 m(M3C2 투영창)에 들면 그 단위의 prior 측이 된다. 소스 판정이 아니다.',
    support: 'f_P = 1 m 지지 격자에서 prior 표본이 있는 발자국 비율. MVS-only 지대의 연속 표현.',
    pairdist: 'paired ALS 셀의 법선 거리. 3D-a 증거의 자리이지 판정값이 아니다.',
    tilt: '동결 Gate-S0 중력(up)에 대한 단위 법선 각. 서술용.',
    role: 'ABSORBED_SMALL = A_min 미만 잔여 성분이 r_attach 안의 단위에 흡수된 셀.',
    pairrule: 'D-1e′: ALS 셀 자기 법선(또는 ALS 세그먼트 법선) 방향 창. 법선 없는 거친 셀만 유클리드 대체.',
    layer: 'D-1k: prior 측에 오프셋 다른 ALS 층이 있으면 발자국으로 잘라 단위 하나 = 층 하나. 판정이 아니다.',
    cores: 'D-1j: 동결 관계 core(3D-a 표본)의 단위 사상. core 0인 단위는 3D-a 검정력 없음(T1이 r로 반영).',
  };
  $('t0-note').textContent = notes[t0Mode];
}

function renderT0Accounting() {
  const acc = ru.accounting;
  const c4 = acc.criterion_4_pairing;
  const rows = [
    ['units total', number(ru.unit_count)],
    ['MVS planar / rough', `${number(c4.mvs_primary_kind_counts.PLANAR)} / ${number(c4.mvs_primary_kind_counts.ROUGH)}`],
    ['prior-only planar / rough', `${number(c4.prior_only_kind_counts.PLANAR)} / ${number(c4.prior_only_kind_counts.ROUGH)}`],
    ['cells assigned / unassigned', `${number(acc.criterion_2_coverage.cells_assigned)} / ${number(acc.criterion_2_coverage.cells_unassigned)}`],
    ['ALS paired / prior-only', `${number(c4.als_cells_paired)} / ${number(c4.als_cells_prior_only_zone)}`],
    ['MVS units without prior', number(c4.mvs_units_without_prior_side)],
    ['layer split / mixed', `${number(acc.criterion_3b_prior_layer.mvs_units_split_by_prior_layer)} / ${number(acc.criterion_3b_prior_layer.mvs_units_flagged_mixed_prior)}`],
    ['cores in domain / unresolved', `${number(acc.criterion_6_lineage.relation_cores_in_domain)} / ${number(acc.criterion_6_lineage.relation_cores_unresolved)}`],
    ['units with 0 cores', number(acc.criterion_6_lineage.units_with_zero_cores)],
    ['small / split children', `${number(acc.criterion_3_scale.small_units)} / ${number(acc.criterion_3_scale.split_children)}`],
    ['over extent cap', number(acc.criterion_3_scale.units_over_extent_cap)],
    ['connected units', `${number(acc.criterion_1_connected_area.units_with_one_component)} / ${number(acc.criterion_1_connected_area.units_total)}`],
    ['area p50 / p90 m²', `${finite(acc.criterion_1_connected_area.area_m2_quantiles.p50)} / ${finite(acc.criterion_1_connected_area.area_m2_quantiles.p90)}`],
    ['f_P p50', finite(c4.prior_support_fraction_quantiles.p50)],
    ['adjacency edges', number(acc.criterion_6_lineage.adjacency_edges)],
    ['profile', ru.selected_profile],
  ];
  $('t0-accounting').innerHTML = rows.map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join('');
  $('t0-counts').textContent = `${number(ru.unit_count)} units / ${number(ru.cell_count)} cells`;
}

function clearT0Selection() {
  if (t0Highlight) { scene.remove(t0Highlight); t0Highlight.geometry.dispose(); t0Highlight.material.dispose(); t0Highlight = null; }
  if (t0BoxHelper) { scene.remove(t0BoxHelper); t0BoxHelper = null; }
}

function clearPatchHighlight() {
  if (patchHighlight) { scene.remove(patchHighlight); patchHighlight.geometry.dispose(); patchHighlight.material.dispose(); patchHighlight = null; }
}

function selectUnit(cellIndex) {
  const unitId = t0Unit[cellIndex];
  const row = unitId - 1;
  const ids = row * 14;
  const attr = row * 6;
  const pose = row * 7;
  const metrics = row * 16;
  const local = t0Xyz.subarray(cellIndex * 3, cellIndex * 3 + 3);
  const world = [...local].map((value, axis) => value + manifest.frame.world_shift_xyz_m[axis]);
  const isMvsCell = t0Attr[cellIndex * 5] === 0;
  const source = isMvsCell ? 'MVS' : 'Existing ALS';
  const role = ru.role_names[String(t0Attr[cellIndex * 5 + 1])];
  const pairRule = isMvsCell ? 'n/a (MVS cell)' : ru.pair_rule_names[String(t0Attr[cellIndex * 5 + 4])];
  const primary = t0UnitAttr[attr] === 0 ? 'MVS-primary' : 'prior-only';
  const kind = ru.kind_names[String(t0UnitAttr[attr + 1])];
  const neighbors = t0Neighbors.get(unitId) || [];
  const fields = [
    ['unit ID / UID', `${unitId} · ${t0UidByUnit.get(unitId)}`],
    ['primary / kind', `${primary} · ${kind}`],
    ['small / split child', `${t0UnitAttr[attr + 2] ? 'YES' : 'no'} / ${t0UnitAttr[attr + 3] ? ru.split_reason_names[String(t0UnitAttr[attr + 4])] : 'no'}`],
    ['mixed prior', t0UnitAttr[attr + 5] ? 'YES (layer < A_min)' : 'no'],
    ['cells MVS / ALS', `${number(t0UnitIds[ids + 1])} / ${number(t0UnitIds[ids + 3])}`],
    ['points MVS / ALS', `${number(t0UnitIds[ids + 2])} / ${number(t0UnitIds[ids + 4])}`],
    ['absorbed / components', `${number(t0UnitIds[ids + 5])} / ${number(t0UnitIds[ids + 7])}`],
    ['area m²', finite(t0UnitMetrics[metrics])],
    ['extent e1 / e2 m', `${finite(t0UnitMetrics[metrics + 3])} / ${finite(t0UnitMetrics[metrics + 4])}`],
    ['centroid', [...t0UnitPose.subarray(pose, pose + 3)].map(finite).join(', ')],
    ['normal', [...t0UnitPose.subarray(pose + 3, pose + 6)].map(finite).join(', ')],
    ['tilt from up °', finite(t0UnitMetrics[metrics + 5])],
    ['plane RMSE / p95 m', `${finite(t0UnitMetrics[metrics + 1])} / ${finite(t0UnitMetrics[metrics + 2])}`],
    ['prior support f_P', finite(t0UnitMetrics[metrics + 6])],
    ['prior offset med / spread m', `${finite(t0UnitMetrics[metrics + 13])} / ${finite(t0UnitMetrics[metrics + 14])}`],
    ['prior plane RMSE m', finite(t0UnitMetrics[metrics + 15])],
    ['paired ALS segments', number(t0UnitIds[ids + 6])],
    ['relation cores 1·2·3·4·5', [...t0UnitIds.subarray(ids + 9, ids + 14)].map(number).join(' · ')],
    ['adjacent units', neighbors.length ? neighbors.map(n => `${n.id}${n.same ? '' : '*'}(${n.contact}/${n.mm}mm)`).join(' ') : 'none'],
    ['— selected cell —', ''],
    ['cell source / role', `${source} · ${role}`],
    ['cell pair rule', pairRule],
    ['cell σ / pair dist m', `${finite(t0Metrics[cellIndex * 2])} / ${isMvsCell ? 'n/a' : finite(t0Metrics[cellIndex * 2 + 1])}`],
    ['local XYZ', [...local].map(value => value.toFixed(2)).join(', ')],
    ['world XYZ', world.map(value => value.toFixed(2)).join(', ')],
  ];
  $('selection-details').innerHTML = fields.map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join('');
  if (selectionMarker) scene.remove(selectionMarker);
  selectionMarker = new THREE.Mesh(
    new THREE.SphereGeometry(0.6, 16, 12),
    new THREE.MeshBasicMaterial({color: 0xffff00, wireframe: true, depthTest: false}),
  );
  selectionMarker.position.fromArray(local);
  selectionMarker.renderOrder = 20;
  scene.add(selectionMarker);
  clearT0Selection();
  clearPatchHighlight();
  const members = [];
  for (let index = 0; index < ru.cell_count; index++) if (t0Unit[index] === unitId) members.push(index);
  const positions = new Float32Array(members.length * 3);
  members.forEach((index, output) => positions.set(t0Xyz.subarray(index * 3, index * 3 + 3), output * 3));
  t0Highlight = createPoints(positions, '#ffff00', 7, 1);
  t0Highlight.material.depthTest = false;
  t0Highlight.renderOrder = 19;
  const box = new THREE.Box3(
    new THREE.Vector3(t0UnitMetrics[metrics + 7], t0UnitMetrics[metrics + 8], t0UnitMetrics[metrics + 9]),
    new THREE.Vector3(t0UnitMetrics[metrics + 10], t0UnitMetrics[metrics + 11], t0UnitMetrics[metrics + 12]),
  );
  t0BoxHelper = new THREE.Box3Helper(box, 0xffff00);
  t0BoxHelper.renderOrder = 18;
  scene.add(t0BoxHelper);
}

function applyDim() {
  const active = Boolean(ru) && $('show-t0').checked && $('t0-dim').checked;
  if (active === dimmed) return;
  dimmed = active;
  const factor = active ? 0.22 : 1;
  for (const points of Object.values(sourceObjects)) {
    points.material.opacity = Number($('source-opacity').value) * factor;
    points.material.transparent = points.material.opacity < 1;
  }
  for (const objects of [rawObjects, patchObjects]) for (const points of objects.values()) {
    points.material.opacity = factor;
    points.material.transparent = factor < 1;
  }
}

function updateT0Visibility() {
  if (!ru) return;
  const show = $('show-t0').checked;
  t0Objects.mvs.visible = show && $('t0-show-mvs').checked;
  t0Objects.als.visible = show && $('t0-show-als').checked;
  prismHelper.visible = show;
  if (!show) clearT0Selection();
  applyDim();
}

buildClassControls();
setStatus('browser assets 검증 중…');
const pa = manifest.patches.assets;
const buffers = await Promise.all([
  fetchAsset(manifest.sources.mvs), fetchAsset(manifest.sources.als),
  fetchAsset(manifest.relations.xyz), fetchAsset(manifest.relations.attributes),
  fetchAsset(manifest.relations.metrics), fetchAsset(manifest.relations.support_counts),
  fetchAsset(pa.ids), fetchAsset(pa.attributes), fetchAsset(pa.core_counts), fetchAsset(pa.metrics),
  fetchAsset(pa.summary_ids), fetchAsset(pa.summary_attributes), fetchAsset(pa.summary_pose),
  fetchAsset(pa.summary_metrics), fetchAsset(pa.summary_uids),
]);

sourceObjects.mvs = createPoints(new Float32Array(buffers[0]), manifest.sources.mvs.color, Number($('source-size').value), Number($('source-opacity').value));
sourceObjects.als = createPoints(new Float32Array(buffers[1]), manifest.sources.als.color, Number($('source-size').value), Number($('source-opacity').value));
relationPositions = new Float32Array(buffers[2]);
relationLabels = new Uint8Array(buffers[3]);
relationMetrics = new Float32Array(buffers[4]);
relationSupport = new Uint32Array(buffers[5]);
patchIds = new Uint32Array(buffers[6]);
patchAttributes = new Uint8Array(buffers[7]);
patchCoreCounts = new Uint32Array(buffers[8]);
patchMetrics = new Float32Array(buffers[9]);
summaryIds = new Uint32Array(buffers[10]);
summaryAttributes = new Uint8Array(buffers[11]);
summaryPose = new Float32Array(buffers[12]);
summaryMetrics = new Float32Array(buffers[13]);
summaryUidBytes = new Uint8Array(buffers[14]);

for (let row = 0; row < manifest.patches.patch_count; row++) {
  const patchId = summaryIds[row * 7];
  const uid = summaryUid(row);
  summaryRowByPatch.set(patchId, row);
  uidByPatch.set(patchId, uid);
  uidColorByPatch.set(patchId, uidRgb(uid));
}
createCoreGroups('raw', rawObjects);
createCoreGroups('patch', patchObjects);
createCentroids();

if (ru) {
  setStatus('T0 region unit assets 검증 중…');
  const ra = ru.assets;
  const t0Buffers = await Promise.all([
    fetchAsset(ra.cells_xyz), fetchAsset(ra.cells_attributes), fetchAsset(ra.cells_unit), fetchAsset(ra.cells_metrics),
    fetchAsset(ra.units_ids), fetchAsset(ra.units_attributes), fetchAsset(ra.units_pose), fetchAsset(ra.units_metrics),
    fetchAsset(ra.units_uids), fetchAsset(ra.adjacency),
  ]);
  t0Xyz = new Float32Array(t0Buffers[0]);
  t0Attr = new Uint8Array(t0Buffers[1]);
  t0Unit = new Uint32Array(t0Buffers[2]);
  t0Metrics = new Float32Array(t0Buffers[3]);
  t0UnitIds = new Uint32Array(t0Buffers[4]);
  t0UnitAttr = new Uint8Array(t0Buffers[5]);
  t0UnitPose = new Float32Array(t0Buffers[6]);
  t0UnitMetrics = new Float32Array(t0Buffers[7]);
  t0UnitUidBytes = new Uint8Array(t0Buffers[8]);
  t0Adjacency = new Uint32Array(t0Buffers[9]);
  for (let row = 0; row < ru.unit_count; row++) {
    const uid = t0UnitUid(row);
    t0UidByUnit.set(row + 1, uid);
    t0UidColorByUnit.set(row + 1, uidRgb(uid));
  }
  for (let edge = 0; edge < ru.adjacency_count; edge++) {
    const a = t0Adjacency[edge * 7];
    const b = t0Adjacency[edge * 7 + 1];
    const contact = t0Adjacency[edge * 7 + 2];
    const same = t0Adjacency[edge * 7 + 3] === 1;
    const mm = t0Adjacency[edge * 7 + 4];
    if (!t0Neighbors.has(a)) t0Neighbors.set(a, []);
    if (!t0Neighbors.has(b)) t0Neighbors.set(b, []);
    t0Neighbors.get(a).push({id: b, contact, same, mm});
    t0Neighbors.get(b).push({id: a, contact, same, mm});
  }
  createT0Layer();
  renderT0Legend();
  renderT0Accounting();
  $('show-t0').addEventListener('change', updateT0Visibility);
  $('t0-show-mvs').addEventListener('change', updateT0Visibility);
  $('t0-show-als').addEventListener('change', updateT0Visibility);
  $('t0-dim').addEventListener('change', applyDim);
  $('t0-mode').addEventListener('change', event => { t0Mode = event.target.value; updateT0Colors(); renderT0Legend(); });
  $('t0-size').addEventListener('input', event => {
    event.target.nextElementSibling.value = event.target.value;
    for (const points of Object.values(t0Objects)) points.material.size = Number(event.target.value);
  });
  $('t0-xray').addEventListener('change', event => {
    for (const points of Object.values(t0Objects)) { points.material.depthTest = !event.target.checked; points.material.needsUpdate = true; }
  });
  $('t0-clear').addEventListener('click', () => {
    clearT0Selection();
    clearPatchHighlight();
    if (selectionMarker) { scene.remove(selectionMarker); selectionMarker = null; }
    $('selection-details').innerHTML = '<div><dt>상태</dt><dd>core 또는 T0 셀을 클릭하세요.</dd></div>';
  });
  $('view-prism').addEventListener('click', () => {
    const d = ru.domain;
    const target = new THREE.Vector3((d.x[0] + d.x[1]) / 2, (d.y[0] + d.y[1]) / 2, (d.z[0] + d.z[1]) / 2);
    setView('oblique', target, Math.max(d.x[1] - d.x[0], d.y[1] - d.y[0]) * 0.8);
  });
} else {
  $('t0-section').hidden = true;
}

$('source-counts').textContent = `${number(manifest.sources.mvs.count)} + ${number(manifest.sources.als.count)}`;
$('relation-total').textContent = `${number(manifest.relations.count)} cores / ${number(manifest.patches.patch_count)} patches`;
for (const tile of manifest.active_tiles) {
  const option = document.createElement('option');
  option.value = tile.tile_id;
  option.textContent = `${tile.tile_id} · ${number(tile.relation_rows)}`;
  $('tile-select').appendChild(option);
}

$('show-mvs').addEventListener('change', event => { sourceObjects.mvs.visible = event.target.checked; });
$('show-als').addEventListener('change', event => { sourceObjects.als.visible = event.target.checked; });
for (const id of ['source-opacity', 'source-size', 'relation-size']) {
  $(id).addEventListener('input', event => {
    event.target.nextElementSibling.value = event.target.value;
    if (id === 'source-opacity') for (const points of Object.values(sourceObjects)) {
      points.material.opacity = Number(event.target.value) * (dimmed ? 0.22 : 1);
      points.material.transparent = points.material.opacity < 1;
    }
    if (id === 'source-size') for (const points of Object.values(sourceObjects)) points.material.size = Number(event.target.value);
    if (id === 'relation-size') for (const objects of [rawObjects, patchObjects]) for (const points of objects.values()) points.material.size = Number(event.target.value);
  });
}
$('xray-labels').addEventListener('change', event => {
  for (const objects of [rawObjects, patchObjects]) for (const points of objects.values()) {
    points.material.depthTest = !event.target.checked;
    points.material.needsUpdate = true;
  }
});
$('show-centroids').addEventListener('change', event => { centroidObject.visible = event.target.checked; });
$('color-mode').addEventListener('change', event => applyMode(event.target.value));
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => applyMode(button.dataset.mode)));
$('preset-all').addEventListener('click', () => {
  document.querySelectorAll('[data-class]').forEach(input => input.checked = true);
  updateVisibility();
});
$('preset-queue').addEventListener('click', () => {
  document.querySelectorAll('[data-class]').forEach(input => input.checked = manifest.render_queue_classes.includes(Number(input.dataset.class)));
  updateVisibility();
});
$('view-fit').addEventListener('click', () => setView('oblique'));
$('view-oblique').addEventListener('click', () => setView('oblique'));
$('view-top').addEventListener('click', () => setView('top'));
$('tile-select').addEventListener('change', event => {
  if (!event.target.value) return setView('oblique');
  const tile = manifest.active_tiles.find(item => item.tile_id === event.target.value);
  setView('oblique', new THREE.Vector3(...tile.scene_local_center), tile.focus_radius_m);
});

const raycaster = new THREE.Raycaster();
raycaster.params.Points.threshold = 2.0;
const pointer = new THREE.Vector2();
renderer.domElement.addEventListener('click', event => {
  const bounds = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
  pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  // T0 cells are 0.25 m apart: pick the cell closest to the ray within a tight tube; fall back to the relation cores
  if (ru) {
    raycaster.params.Points.threshold = 0.35;
    const t0Hits = raycaster.intersectObjects(Object.values(t0Objects).filter(points => points.visible), false);
    if (t0Hits.length) {
      const best = t0Hits.reduce((a, b) => (b.distanceToRay < a.distanceToRay ? b : a));
      selectUnit(best.object.userData.originalIndices[best.index]);
      return;
    }
  }
  raycaster.params.Points.threshold = 2.0;
  const candidates = [...activeObjects.values()].filter(points => points.visible);
  const hit = raycaster.intersectObjects(candidates, false)[0];
  if (hit) selectCore(hit.object.userData.originalIndices[hit.index]);
});

const resize = () => {
  const width = Math.max(1, viewport.clientWidth);
  const height = Math.max(1, viewport.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
};
new ResizeObserver(resize).observe(viewport);
resize();
setView('oblique');
applyMode('raw');
if (ru) { updateT0Visibility(); $('view-prism').click(); }
setStatus(`ready · ${number(manifest.relations.count)} cores / ${number(manifest.patches.patch_count)} patches${ru ? ` / ${number(ru.unit_count)} T0 units` : ''}`);

function frame() {
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
frame();
