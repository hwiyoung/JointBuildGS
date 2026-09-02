import * as THREE from 'three';
import * as GaussianSplats3D from './lib/gaussian-splats-3d.module.min.js';

const $ = id => document.getElementById(id);
const status = $('status');
const viewport = $('viewport');
const number = value => Number(value).toLocaleString('ko-KR');
const finite = value => Number.isFinite(value) ? Number(value).toFixed(3) : 'NA';

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

const manifest = await fetch('viewer_manifest.json', {cache: 'no-store'}).then(response => {
  if (!response.ok) throw new Error(`viewer_manifest.json: HTTP ${response.status}`);
  return response.json();
});
if (manifest.scientific_verdict !== null) throw new Error('scientific_verdict must remain null');

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
const relationObjects = new Map();
let robustObject = null;
let robustOnly = false;
let relationPositions;
let relationLabels;
let relationMetrics;
let relationCounts;
let selectionMarker;

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

function classColor(classId) {
  return manifest.classes[String(classId)].color;
}

function metricColor(mode, index, classId) {
  if (mode === 'class') return hexRgb(classColor(classId));
  const offset = index * manifest.relations.metrics_stride;
  if (mode === 'distance') {
    const value = relationMetrics[offset];
    if (!Number.isFinite(value)) return hexRgb(classColor(classId));
    const t = Math.max(-1, Math.min(1, value / 3));
    return t < 0 ? [1 + t, 1 + t, 1] : [1, 1 - t, 1 - t];
  }
  const ratio = relationMetrics[offset + 3];
  if (!Number.isFinite(ratio)) return hexRgb(classColor(classId));
  const t = Math.max(0, Math.min(1, ratio / 5));
  return [1, 0.92 * (1 - t), 0.18 * (1 - t)];
}

function updateRelationColors() {
  const mode = $('color-mode').value;
  for (const [classId, points] of relationObjects) {
    const ids = points.userData.originalIndices;
    const colors = points.geometry.getAttribute('color');
    for (let row = 0; row < ids.length; row++) {
      const rgb = metricColor(mode, ids[row], classId);
      colors.setXYZ(row, rgb[0], rgb[1], rgb[2]);
    }
    colors.needsUpdate = true;
  }
  $('color-note').textContent = mode === 'class'
    ? '고정된 5개 관계 색상'
    : mode === 'distance'
      ? 'signed M3C2: blue −3 m · white 0 · red +3 m; support-only는 class 색상'
      : 'significance ratio: pale 0 · red ≥5; support-only는 class 색상';
}

function createRelationClass(classId) {
  const ids = [];
  for (let index = 0; index < relationLabels.length / 4; index++) {
    if (relationLabels[index * 4] === classId) ids.push(index);
  }
  const positions = new Float32Array(ids.length * 3);
  const colors = new Float32Array(ids.length * 3);
  const base = hexRgb(classColor(classId));
  ids.forEach((index, row) => {
    positions.set(relationPositions.subarray(index * 3, index * 3 + 3), row * 3);
    colors.set(base, row * 3);
  });
  const points = createPoints(positions, 0xffffff, Number($('relation-size').value), 1, colors);
  points.renderOrder = 10;
  points.userData = {kind: 'relation', classId, originalIndices: Uint32Array.from(ids)};
  relationObjects.set(classId, points);
}

function createRobustObject() {
  const ids = [];
  for (let index = 0; index < relationLabels.length / 4; index++) {
    if (relationLabels[index * 4 + 3] === 1) ids.push(index);
  }
  const positions = new Float32Array(ids.length * 3);
  ids.forEach((index, row) => positions.set(relationPositions.subarray(index * 3, index * 3 + 3), row * 3));
  robustObject = createPoints(positions, '#ff1744', Number($('relation-size').value) * 1.35, 1);
  robustObject.renderOrder = 11;
  robustObject.visible = false;
  robustObject.userData = {kind: 'relation', classId: 2, originalIndices: Uint32Array.from(ids)};
}

function relationVisibility() {
  for (const [classId, points] of relationObjects) {
    const checked = document.querySelector(`[data-class="${classId}"]`).checked;
    points.visible = !robustOnly && checked;
  }
  robustObject.visible = robustOnly;
  $('preset-robust').classList.toggle('active', robustOnly);
  const visible = robustOnly
    ? manifest.relations.robust_significant_count
    : [...relationObjects].reduce((sum, [id, points]) => sum + (points.visible ? points.userData.originalIndices.length : 0), 0);
  $('view-summary').textContent = `${number(manifest.sources.mvs.count)} MVS · ${number(manifest.sources.als.count)} ALS · ${number(visible)} visible relation cores`;
}

function buildClassControls() {
  const root = $('class-controls');
  for (const [key, item] of Object.entries(manifest.classes)) {
    const row = document.createElement('label');
    row.className = 'class-row';
    row.innerHTML = `<input type="checkbox" data-class="${key}" checked><i class="swatch" style="background:${item.color}"></i><span class="class-name">${key} ${item.name}</span><span class="class-count">${number(item.count)}</span>`;
    row.querySelector('input').addEventListener('change', () => { robustOnly = false; relationVisibility(); });
    root.appendChild(row);
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
  const attr = index * 4;
  const metric = index * manifest.relations.metrics_stride;
  const count = index * 2;
  const cls = relationLabels[attr];
  const source = relationLabels[attr + 1] === 0 ? 'MVS core' : 'ALS reciprocal core';
  const reason = manifest.reasons[String(relationLabels[attr + 2])];
  const robust = relationLabels[attr + 3] === 1;
  const local = relationPositions.subarray(index * 3, index * 3 + 3);
  const world = local.map((value, axis) => value + manifest.frame.world_shift_xyz_m[axis]);
  const fields = [
    ['label', `${cls} ${manifest.classes[String(cls)].name}`],
    ['core source', source], ['reason', reason], ['robust', robust ? 'YES' : 'NO'],
    ['local XYZ', [...local].map(value => value.toFixed(2)).join(', ')],
    ['world XYZ', [...world].map(value => value.toFixed(2)).join(', ')],
    ['M3C2 signed m', finite(relationMetrics[metric])],
    ['LoD95 local m', finite(relationMetrics[metric + 1])],
    ['LoD95 reg-upper m', finite(relationMetrics[metric + 2])],
    ['|d| / LoD95', finite(relationMetrics[metric + 3])],
    ['sigma MVS / ALS', `${finite(relationMetrics[metric + 4])} / ${finite(relationMetrics[metric + 5])}`],
    ['support MVS / ALS', `${number(relationCounts[count])} / ${number(relationCounts[count + 1])}`],
  ];
  $('selection-details').innerHTML = fields.map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join('');
  if (selectionMarker) scene.remove(selectionMarker);
  selectionMarker = new THREE.Mesh(new THREE.SphereGeometry(1.25, 16, 12), new THREE.MeshBasicMaterial({color: 0xffff00, wireframe: true, depthTest: false}));
  selectionMarker.position.fromArray(local);
  selectionMarker.renderOrder = 20;
  scene.add(selectionMarker);
}

buildClassControls();
setStatus('browser assets 검증 중…');
const [mvsBuffer, alsBuffer, relationXyzBuffer, labelBuffer, metricBuffer, countBuffer] = await Promise.all([
  fetchAsset(manifest.sources.mvs), fetchAsset(manifest.sources.als),
  fetchAsset(manifest.relations.xyz), fetchAsset(manifest.relations.attributes),
  fetchAsset(manifest.relations.metrics), fetchAsset(manifest.relations.support_counts),
]);

sourceObjects.mvs = createPoints(new Float32Array(mvsBuffer), manifest.sources.mvs.color, Number($('source-size').value), Number($('source-opacity').value));
sourceObjects.als = createPoints(new Float32Array(alsBuffer), manifest.sources.als.color, Number($('source-size').value), Number($('source-opacity').value));
sourceObjects.mvs.userData.kind = 'source';
sourceObjects.als.userData.kind = 'source';
relationPositions = new Float32Array(relationXyzBuffer);
relationLabels = new Uint8Array(labelBuffer);
relationMetrics = new Float32Array(metricBuffer);
relationCounts = new Uint32Array(countBuffer);
for (let classId = 1; classId <= 5; classId++) createRelationClass(classId);
createRobustObject();

$('source-counts').textContent = `${number(manifest.sources.mvs.count)} + ${number(manifest.sources.als.count)}`;
$('relation-total').textContent = number(manifest.relations.count);
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
    if (id === 'source-opacity') for (const points of Object.values(sourceObjects)) { points.material.opacity = Number(event.target.value); points.material.transparent = Number(event.target.value) < 1; }
    if (id === 'source-size') for (const points of Object.values(sourceObjects)) points.material.size = Number(event.target.value);
    if (id === 'relation-size') { for (const points of relationObjects.values()) points.material.size = Number(event.target.value); robustObject.material.size = Number(event.target.value) * 1.35; }
  });
}
$('xray-labels').addEventListener('change', event => { for (const points of [...relationObjects.values(), robustObject]) { points.material.depthTest = !event.target.checked; points.material.needsUpdate = true; } });
$('color-mode').addEventListener('change', updateRelationColors);
$('preset-all').addEventListener('click', () => { robustOnly = false; document.querySelectorAll('[data-class]').forEach(input => input.checked = true); relationVisibility(); });
$('preset-queue').addEventListener('click', () => { robustOnly = false; document.querySelectorAll('[data-class]').forEach(input => input.checked = [2, 3, 4].includes(Number(input.dataset.class))); relationVisibility(); });
$('preset-robust').addEventListener('click', () => { robustOnly = true; relationVisibility(); });
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
  const candidates = robustOnly ? [robustObject] : [...relationObjects.values()].filter(points => points.visible);
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
updateRelationColors();
relationVisibility();
setStatus(`ready · ${number(manifest.relations.count)} relation cores`);

function frame() {
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
frame();
