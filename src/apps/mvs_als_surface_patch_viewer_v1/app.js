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
  if (patchHighlight) {
    scene.remove(patchHighlight);
    patchHighlight.geometry.dispose();
    patchHighlight.material.dispose();
  }
  const ids = [];
  if (patchId === 0) ids.push(index);
  else for (let row = 0; row < patchIds.length; row++) if (patchIds[row] === patchId) ids.push(row);
  const positions = new Float32Array(ids.length * 3);
  ids.forEach((row, output) => positions.set(relationPositions.subarray(row * 3, row * 3 + 3), output * 3));
  patchHighlight = createPoints(positions, '#ffff00', 8, 1);
  patchHighlight.material.depthTest = false;
  patchHighlight.renderOrder = 19;
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
      points.material.opacity = Number(event.target.value);
      points.material.transparent = Number(event.target.value) < 1;
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
setStatus(`ready · ${number(manifest.relations.count)} cores / ${number(manifest.patches.patch_count)} patches`);

function frame() {
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
frame();
