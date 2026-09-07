import * as THREE from './three.module.min.js';

const $ = id => document.getElementById(id);
const count = n => Number(n).toLocaleString('ko-KR');
const keys = ['als', 'image', 'update', 'reference'];
const cache = new Map(), panels = new Map();
const qa = window.__WV_REGIONS_QA = {ready: false, errors: [], frames: 0};
let data, region, arm, loaded = {}, token = 0, mode = 'height', section = 'x';
let azimuth = -.8, elevation = .65, zoom = 1, contextOpen = false;

async function binary(url, Type) {
  const key = Type.name + ':' + url;
  if (!cache.has(key)) cache.set(key, fetch(url).then(r => {
    if (!r.ok) throw Error(url + ' HTTP ' + r.status);
    return r.arrayBuffer();
  }).then(buffer => new Type(buffer)));
  return cache.get(key);
}
async function cloud(meta) {
  const result = {meta, xyz: await binary(meta.xyz, Float32Array), sections: {}};
  if (meta.source) result.source = await binary(meta.source, Uint8Array);
  for (const axis of ['x', 'y']) result.sections[axis] = {
    xyz: await binary(meta.sections[axis].xyz, Float32Array),
    source: meta.sections[axis].source ? await binary(meta.sections[axis].source, Uint8Array) : null,
  };
  return result;
}
function fail(error) {
  qa.errors.push(String(error)); qa.ready = false;
  $('error').hidden = false; $('error').textContent = '표시 실패: ' + error;
  console.error(error);
}
function currentUpdate() { return loaded[mode === 'removed_old' ? 'removed_old' : mode === 'added_new' ? 'added_new' : 'update']; }
function heightRGB(z) {
  const colors = [[39, 73, 150], [24, 182, 193], [232, 211, 83], [225, 89, 57]];
  const low = region.bounds.min[2], high = region.bounds.max[2];
  const t = Math.max(0, Math.min(1, (z - low) / Math.max(high - low, 1e-6))) * 3;
  const k = Math.min(2, Math.floor(t)), a = t - k;
  return colors[k].map((v, i) => (v * (1 - a) + colors[k + 1][i] * a) / 255);
}
function pointRGB(key, points, i) {
  if (key === 'update' && mode === 'source') return points.source[i] === 0 ? [184 / 255, 135 / 255, 66 / 255] : [38 / 255, 141 / 255, 192 / 255];
  if (key === 'update' && mode === 'removed_old') return [.82, .2, .26];
  if (key === 'update' && mode === 'added_new') return [38 / 255, 141 / 255, 192 / 255];
  return heightRGB(points.xyz[3 * i + 2]);
}
// Three.js vertex attributes use linear RGB. The shared HTML/canvas legend uses
// sRGB; convert exactly once before the renderer's linear-to-sRGB output step.
function srgbToLinear(channel) { return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4; }
function rebuild(key) {
  const panel = panels.get(key), points = key === 'update' ? currentUpdate() : loaded[key];
  if (!panel || !points) return;
  if (panel.points) { panel.scene.remove(panel.points); panel.points.geometry.dispose(); panel.points.material.dispose(); }
  const colors = new Float32Array(points.xyz.length);
  for (let i = 0; i < points.xyz.length / 3; i++) colors.set(pointRGB(key, points, i).map(srgbToLinear), i * 3);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(points.xyz, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  panel.points = new THREE.Points(geometry, new THREE.PointsMaterial({size: 1.6, sizeAttenuation: false, vertexColors: true}));
  panel.scene.add(panel.points);
  const host = document.querySelector(`[data-method="${key}"] .counts`);
  if (host) host.textContent = `전체 ${count(points.meta.native_count)}점 · 표시 ${count(points.meta.display_count)}점`;
  if (key === 'mvs') $('context-count').textContent = `원 MVS ${count(points.meta.native_count)}점 · 표시 ${count(points.meta.display_count)}점`;
}
function cameraAll() {
  if (!region) return;
  const b = region.bounds, center = b.min.map((v, i) => (v + b.max[i]) / 2);
  const span = Math.max(...b.max.map((v, i) => v - b.min[i]));
  qa.cameras = {}; qa.heightRange = [b.min[2], b.max[2]];
  for (const [key, p] of panels) {
    if (key === 'mvs' && !contextOpen) continue;
    const w = p.host.clientWidth, h = p.host.clientHeight;
    if (!w || !h) continue;
    const scale = span * .70 / zoom * Math.max(1, h / w);
    p.camera.left = -scale * w / h; p.camera.right = scale * w / h;
    p.camera.top = scale; p.camera.bottom = -scale;
    p.camera.near = .01; p.camera.far = span * 100;
    p.camera.position.set(center[0] + 3 * span * Math.cos(azimuth) * Math.cos(elevation), center[1] + 3 * span * Math.sin(azimuth) * Math.cos(elevation), center[2] + 3 * span * Math.sin(elevation));
    p.camera.up.set(0, 0, 1); p.camera.lookAt(...center); p.camera.updateProjectionMatrix();
    p.renderer.setSize(w, h, false); p.renderer.render(p.scene, p.camera); qa.frames++;
    qa.cameras[key] = {position: p.camera.position.toArray(), target: center, left: p.camera.left, right: p.camera.right, top: scale, heightRange: qa.heightRange};
  }
}
function initPanel(key) {
  const host = $('view-' + key), scene = new THREE.Scene();
  scene.background = new THREE.Color('#eaf0f4');
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, .01, 10000);
  const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); host.append(renderer.domElement);
  panels.set(key, {host, scene, camera, renderer});
  let drag = null;
  renderer.domElement.onpointerdown = event => { drag = [event.clientX, event.clientY]; renderer.domElement.setPointerCapture(event.pointerId); };
  renderer.domElement.onpointerup = () => drag = null;
  renderer.domElement.onpointermove = event => {
    if (!drag) return;
    azimuth -= (event.clientX - drag[0]) * .007;
    elevation = Math.max(-1.54, Math.min(1.54, elevation + (event.clientY - drag[1]) * .007));
    drag = [event.clientX, event.clientY]; cameraAll();
  };
  renderer.domElement.addEventListener('wheel', event => {
    event.preventDefault(); zoom = Math.max(.4, Math.min(12, zoom * Math.exp(-event.deltaY * .001))); cameraAll();
  }, {passive: false});
}
function sectionPlot(key) {
  const points = key === 'update' ? currentUpdate() : loaded[key], native = points.sections[section];
  const canvas = $('section-' + key), w = canvas.clientWidth, h = canvas.clientHeight, ratio = Math.min(devicePixelRatio, 2);
  canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio);
  const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio); ctx.fillStyle = '#fbfcfd'; ctx.fillRect(0, 0, w, h);
  const axis = section === 'x' ? 1 : 0, b = region.bounds, xb = [b.min[axis], b.max[axis]], zb = [b.min[2], b.max[2]];
  const pad = {l: 48, r: 15, t: 15, b: 35}, fx = x => pad.l + (x - xb[0]) / (xb[1] - xb[0]) * (w - pad.l - pad.r), fy = z => h - pad.b - (z - zb[0]) / (zb[1] - zb[0]) * (h - pad.t - pad.b);
  ctx.font = '10px system-ui'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const x = xb[0] + (xb[1] - xb[0]) * i / 4, z = zb[0] + (zb[1] - zb[0]) * i / 4;
    ctx.strokeStyle = '#e0e8ed'; ctx.beginPath(); ctx.moveTo(fx(x), pad.t); ctx.lineTo(fx(x), h - pad.b); ctx.moveTo(pad.l, fy(z)); ctx.lineTo(w - pad.r, fy(z)); ctx.stroke();
    ctx.fillStyle = '#536e7e'; ctx.textAlign = 'center'; ctx.fillText(x.toFixed(1), fx(x), h - 17); ctx.textAlign = 'right'; ctx.fillText(z.toFixed(1), pad.l - 6, fy(z) + 3);
  }
  ctx.textAlign = 'center'; ctx.fillText((axis === 0 ? 'X' : 'Y') + ' (m)', w / 2, h - 3);
  for (let i = 0; i < native.xyz.length / 3; i++) {
    const rgb = pointRGB(key, native, i); ctx.fillStyle = `rgb(${rgb.map(v => Math.round(v * 255)).join(',')})`;
    ctx.fillRect(fx(native.xyz[i * 3 + axis]) - .7, fy(native.xyz[i * 3 + 2]) - .7, 1.4, 1.4);
  }
  qa.sections[key] = {nativeCount: native.xyz.length / 3, axis: section, location: region.sections[section], width: region.sections.width};
}
function allSections() {
  if (!loaded.als || !loaded.update) return;
  qa.sections = {}; keys.forEach(sectionPlot);
  $('section-note').textContent = `${section.toUpperCase()} = ${region.sections[section].toFixed(2)} m, 전체 폭 ${region.sections.width} m. 각 원점 전체에서 동일한 공간 구간을 선택했습니다. 3D 표시용 샘플을 단면에 재사용하지 않습니다.`;
}
function metrics() {
  const threshold = Number($('metric-threshold').value), methods = region.evaluation.methods;
  const titles = ['조건', '원점 수', '점군 → 참조 p90', '참조 → 점군 p90', `참조 근처 점 비율 P (${threshold} m)`, `점군 근처 참조 비율 R (${threshold} m)`, 'F1', '참조 셀 중 누락'];
  $('metrics-head').replaceChildren(); const header = document.createElement('tr');
  for (const title of titles) { const cell = document.createElement('th'); cell.textContent = title; header.append(cell); } $('metrics-head').append(header);
  $('metrics-body').replaceChildren(); qa.metrics = [];
  for (const [name, value] of Object.entries(methods)) {
    const k = value.coverage.thresholds_m.findIndex(t => Math.abs(t - threshold) < 1e-8);
    const fmt = n => n === null || n === undefined ? '—' : Number(n).toFixed(3) + ' m';
    const pct = n => n === null || n === undefined ? '—' : (100 * n).toFixed(2) + '%';
    const values = [region.metric_labels?.[name] ?? name, count(value.point_count), fmt(value.to_reference.p90_m), fmt(value.reference_to.p90_m), pct(value.coverage.precision[k]), pct(value.coverage.recall[k]), pct(value.coverage.fscore[k]), `${count(value.xy_cells.missed_reference_cells)} / ${count(value.xy_cells.reference_cells)}`];
    const row = document.createElement('tr'); row.dataset.method = name; row.classList.toggle('after', name === arm.evaluation_key);
    for (const v of values) { const cell = document.createElement('td'); cell.textContent = v; row.append(cell); } $('metrics-body').append(row);
    qa.metrics.push({name, values, threshold});
  }
}
function updateCounts() {
  $('change-counts').replaceChildren();
  for (const [title, value] of [['유지한 ALS', arm.counts.retained_old], ['삭제한 ALS', arm.counts.removed_old], ['추가한 영상점', arm.counts.admitted_new], ['갱신 전체', arm.counts.updated]]) {
    const box = document.createElement('div'); box.className = 'stat'; const name = document.createElement('span'), number = document.createElement('b'); name.textContent = title; number.textContent = count(value); box.append(name, number); $('change-counts').append(box);
  }
  $('update-title').textContent = mode === 'removed_old' ? '③ 갱신에서 삭제한 ALS' : mode === 'added_new' ? '③ 갱신에 추가한 영상점' : '③ Wu–Vallet 기반 · 갱신 후';
  $('source-legend').hidden = mode === 'height';
  $('source-legend').replaceChildren();
  const legendItems = mode === 'source' ? [['#b88742', '유지 ALS'], ['#268dc0', '추가 영상점']] : mode === 'removed_old' ? [['#d13342', '삭제한 ALS · 갱신 패널']] : [['#268dc0', '추가한 영상점 · 갱신 패널']];
  for (const [color, label] of legendItems) { const swatch = document.createElement('span'); swatch.className = 'swatch'; swatch.style.background = color; $('source-legend').append(swatch, document.createTextNode(label)); }
  qa.region = region.id; qa.arm = arm.name; qa.mode = mode;
  qa.counts = arm.counts; qa.visibleCounts = {};
  for (const key of keys) qa.visibleCounts[key] = (key === 'update' ? currentUpdate() : loaded[key]).xyz.length / 3;
}
async function switchArm(name) {
  const request = ++token; qa.ready = false;
  arm = region.arms.find(a => a.name === name); if (!arm) throw Error('Unknown arm ' + name);
  $('arm-select').value = name;
  const [update, removed, added] = await Promise.all([cloud(arm.cloud), cloud(arm.removed_old), cloud(arm.added_new)]);
  if (request !== token) return;
  Object.assign(loaded, {update, removed_old: removed, added_new: added});
  rebuild('update'); updateCounts(); cameraAll(); allSections(); metrics(); renderDownloads(); qa.ready = true; $('loading').hidden = true;
}
function renderDownloads() {
  $('downloads').replaceChildren();
  for (const item of [...region.downloads, ...arm.downloads]) { const a = document.createElement('a'); a.href = item.path; a.textContent = item.label; $('downloads').append(a); }
}
function renderFigure() {
  const figure = region.figures.find(x => x.id === $('figure-select').value);
  if (!figure) return; $('evaluation-figure').src = figure.path; $('figure-note').textContent = figure.caption ?? figure.label;
}
async function switchRegion(id) {
  const request = ++token;
  qa.ready = false; $('loading').hidden = false; region = data.regions.find(r => r.id === id);
  $('region-select').value = id; loaded = {}; contextOpen = false; qa.contextOpen = false; $('context-content').hidden = true; $('context-toggle').textContent = '점군 펼치기';
  azimuth = -.8; elevation = .65; zoom = 1;
  $('arm-select').replaceChildren(); for (const a of region.arms) { const option = document.createElement('option'); option.value = a.name; option.textContent = a.label; $('arm-select').append(option); }
  const native = await Promise.all(['als', 'image', 'reference'].map(key => cloud(region.methods[key])));
  if (request !== token) return;
  ['als', 'image', 'reference'].forEach((key, i) => loaded[key] = native[i]);
  ['als', 'image', 'reference'].forEach(rebuild);
  $('region-note').textContent = `${region.label} · 공통 ROI와 좌표 원점을 고정했습니다. 표시 소스당 최대 ${count(data.display_cap)}점의 결정적 원점 부분집합이며, 정량 수치와 단면은 전체 원점에서 계산했습니다.`;
  if (region.note) $('region-note').textContent += ' ' + region.note;
  $('height-range').textContent = `${region.bounds.min[2].toFixed(2)} ~ ${region.bounds.max[2].toFixed(2)} m · scene local Z`;
  $('evaluation-note').textContent = region.evaluation_note;
  $('scope-note').textContent = region.scope_note;
  $('provenance').textContent = JSON.stringify({frame: region.frame, domain: region.domain, input_paths: region.input_paths, source_hashes: region.source_hashes, membership_validation: region.membership_validation, scientific_verdict: null}, null, 2);
  $('evaluation-link').href = region.evaluation_path;
  $('metric-threshold').replaceChildren(); const thresholds = Object.values(region.evaluation.methods)[0].coverage.thresholds_m;
  for (const t of thresholds) { const option = document.createElement('option'); option.value = t; option.textContent = t + ' m'; $('metric-threshold').append(option); } $('metric-threshold').value = thresholds.includes(.5) ? '.5' : String(thresholds[0]);
  // HTML option values serialize 0.5, so do not rely on a leading-dot alias.
  $('metric-threshold').value = String(thresholds.includes(.5) ? .5 : thresholds[0]);
  $('context-card').hidden = !region.methods.mvs;
  $('photo-card').hidden = !region.photo;
  if (region.photo) { $('master-photo').src = region.photo.path; $('photo-link').href = region.photo.path; $('photo-note').textContent = `현재 영상 ${region.photo.image_id}의 실제 보정 사진입니다. 점군 표시나 GS 렌더가 아닙니다.`; $('photo-detail-link').hidden = !region.photo.detail_url; if (region.photo.detail_url) $('photo-detail-link').href = region.photo.detail_url; }
  $('figure-card').hidden = !region.figures.length; $('figure-select').replaceChildren();
  for (const fig of region.figures) { const option = document.createElement('option'); option.value = fig.id; option.textContent = fig.label; $('figure-select').append(option); } renderFigure();
  await switchArm(region.default_arm);
}
async function toggleContext() {
  if (!region.methods.mvs) return;
  contextOpen = !contextOpen; $('context-content').hidden = !contextOpen; $('context-toggle').textContent = contextOpen ? '점군 접기' : '점군 펼치기';
  if (contextOpen) { loaded.mvs = await cloud(region.methods.mvs); if (!panels.has('mvs')) initPanel('mvs'); rebuild('mvs'); cameraAll(); }
  qa.contextOpen = contextOpen;
}
try {
  const response = await fetch('data.json'); if (!response.ok) throw Error('data.json HTTP ' + response.status); data = await response.json();
  if (data.scientific_verdict !== null || !data.regions.length) throw Error('Invalid comparison manifest');
  keys.forEach(initPanel);
  for (const r of data.regions) { const option = document.createElement('option'); option.value = r.id; option.textContent = r.label; $('region-select').append(option); }
  $('region-select').onchange = () => switchRegion($('region-select').value).catch(fail);
  $('arm-select').onchange = () => switchArm($('arm-select').value).catch(fail);
  $('update-mode').onchange = () => { mode = $('update-mode').value; rebuild('update'); updateCounts(); cameraAll(); allSections(); };
  $('section-select').onchange = () => { section = $('section-select').value; allSections(); };
  $('metric-threshold').onchange = metrics;
  $('figure-select').onchange = renderFigure;
  $('context-toggle').onclick = () => toggleContext().catch(fail);
  $('reset-view').onclick = () => { azimuth = -.8; elevation = .65; zoom = 1; cameraAll(); };
  $('top-view').onclick = () => { azimuth = -Math.PI / 2; elevation = 1.54; cameraAll(); };
  $('front-view').onclick = () => { azimuth = -Math.PI / 2; elevation = .03; cameraAll(); };
  let resizePending = false;
  window.addEventListener('resize', () => { if (resizePending) return; resizePending = true; requestAnimationFrame(() => { resizePending = false; cameraAll(); allSections(); }); });
  await switchRegion(data.default_region);
} catch (error) { fail(error); }
