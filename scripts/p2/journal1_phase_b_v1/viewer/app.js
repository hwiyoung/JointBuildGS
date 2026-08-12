// journal1 Phase B — change-label review viewer (A+B mismatch candidates).
// E1 point cloud vs existing LoD2 RoofSurface overlay; labels in localStorage,
// exported as JSON. Non-confirmatory review tooling; no metric is computed here.
import * as THREE from './three.module.min.js';

const LS_LABELS = 'jbgs-journal1-phase-b-change-labels-v1';
const LS_PREFS = 'jbgs-journal1-phase-b-viewprefs-v1';
const MAX_POINTS = 2_500_000; // per arm; larger clouds are stride-subsampled
const LABELS = ['CHANGE', 'NO_CHANGE', 'ABSTRACTION_MISMATCH', 'UNDECIDABLE'];
const LABEL_KO = { CHANGE: '변화', NO_CHANGE: '비변화', ABSTRACTION_MISMATCH: '추상화 불일치', UNDECIDABLE: '판정불능' };
const emptyCounts = () => Object.fromEntries(LABELS.map((l) => [l, 0]));
const COND_RGB = { E1: [40 / 255, 150 / 255, 1], E2: [1, 145 / 255, 35 / 255] };
const CLS_RGB = { 6: [0.23, 0.51, 0.96], 2: [0.55, 0.56, 0.6] };
const CLS_OTHER_RGB = [0.49, 0.36, 0.68];
const LOD2_COLOR = 0xeab308;

const $ = (id) => document.getElementById(id);
const manifest = await (await fetch('./review_manifest.json')).json();
const buildings = manifest.buildings;

// ---------- persistent state ----------
function loadJson(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}
let labels = loadJson(LS_LABELS, {});           // {sid: {label, note, updated_utc}}
const prefs = Object.assign({
  showE1: true, showLod2: true, showE2: false, showNonBldg: true,
  colorMode: 'rgb', ptSize: 2.5, lodOpacity: 0.45,
}, loadJson(LS_PREFS, {}));
const saveLabels = () => localStorage.setItem(LS_LABELS, JSON.stringify(labels));
const savePrefs = () => localStorage.setItem(LS_PREFS, JSON.stringify(prefs));

const state = {
  index: 0,
  filterTier: 'ALL', filterLab: 'ALL',
  clouds: {},          // arm -> {raw, points}
  lod2Group: null,
  loadGen: 0,
};

// ---------- three.js scene ----------
const canvas = $('canvas');
if (THREE.ColorManagement) THREE.ColorManagement.enabled = false; // raw sRGB pass-through
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
if (THREE.LinearSRGBColorSpace) renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);
const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 5000);
camera.up.set(0, 0, 1);

let needsRender = true;
const invalidate = () => { needsRender = true; };

class Orbit {
  constructor(cam, dom) {
    this.cam = cam; this.dom = dom;
    this.target = new THREE.Vector3();
    this.r = 60; this.theta = -Math.PI / 4; this.phi = Math.PI / 3.2;
    this.ptrs = new Map();
    dom.addEventListener('contextmenu', (e) => e.preventDefault());
    dom.addEventListener('pointerdown', (e) => {
      dom.setPointerCapture(e.pointerId);
      this.ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY, b: e.button, shift: e.shiftKey });
    });
    dom.addEventListener('pointermove', (e) => {
      const p = this.ptrs.get(e.pointerId);
      if (!p) return;
      const dx = e.clientX - p.x, dy = e.clientY - p.y;
      p.x = e.clientX; p.y = e.clientY;
      if (this.ptrs.size === 2) { this.pinch(e); return; }
      if (p.b === 2 || p.b === 1 || p.shift) this.pan(dx, dy);
      else { this.theta -= dx * 0.006; this.phi = Math.min(Math.PI - 0.03, Math.max(0.03, this.phi - dy * 0.006)); }
      this.update();
    });
    const drop = (e) => this.ptrs.delete(e.pointerId);
    dom.addEventListener('pointerup', drop);
    dom.addEventListener('pointercancel', drop);
    dom.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.r = Math.min(3000, Math.max(1.5, this.r * Math.exp(e.deltaY * 0.0011)));
      this.update();
    }, { passive: false });
  }
  pinch(e) {
    const [a, b] = [...this.ptrs.values()];
    const cur = Math.hypot(a.x - b.x, a.y - b.y);
    const p = this.ptrs.get(e.pointerId); p.x = e.clientX; p.y = e.clientY;
    const nxt = Math.hypot(a.x - b.x, a.y - b.y);
    if (cur > 0 && nxt > 0) { this.r = Math.min(3000, Math.max(1.5, this.r * cur / nxt)); this.update(); }
  }
  pan(dx, dy) {
    const k = this.r * 0.0016;
    const fwd = this.target.clone().sub(this.cam.position).normalize();
    const right = fwd.clone().cross(this.cam.up).normalize();
    const up = right.clone().cross(fwd).normalize();
    this.target.addScaledVector(right, -dx * k).addScaledVector(up, dy * k);
    this.update();
  }
  update() {
    const sp = Math.sin(this.phi);
    this.cam.position.set(
      this.target.x + this.r * sp * Math.cos(this.theta),
      this.target.y + this.r * sp * Math.sin(this.theta),
      this.target.z + this.r * Math.cos(this.phi));
    this.cam.lookAt(this.target);
    invalidate();
  }
  fit(box) {
    if (box.isEmpty()) return;
    box.getCenter(this.target);
    const s = box.getSize(new THREE.Vector3()).length();
    this.r = Math.max(8, s * 0.85);
    this.update();
  }
}
const orbit = new Orbit(camera, canvas);

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  invalidate();
}
new ResizeObserver(resize).observe($('viewPane'));

(function loop() {
  requestAnimationFrame(loop);
  if (needsRender) { needsRender = false; renderer.render(scene, camera); }
})();

// ---------- binary PLY parsing (little-endian, generic scalar props) ----------
const PROP_SIZE = { float: 4, float32: 4, double: 8, uchar: 1, uint8: 1, char: 1, int8: 1,
  ushort: 2, uint16: 2, short: 2, int16: 2, uint: 4, uint32: 4, int: 4, int32: 4 };

function parsePly(buf) {
  const head = new TextDecoder().decode(new Uint8Array(buf, 0, Math.min(buf.byteLength, 8192)));
  const end = head.indexOf('end_header');
  if (end < 0) throw new Error('PLY: end_header not found');
  const dataStart = head.indexOf('\n', end) + 1;
  let count = 0, inVertex = false, offset = 0;
  const fields = {};
  for (const line of head.slice(0, end).split('\n')) {
    const t = line.trim().split(/\s+/);
    if (t[0] === 'format' && t[1] !== 'binary_little_endian') throw new Error(`PLY: unsupported format ${t[1]}`);
    if (t[0] === 'element') { inVertex = t[1] === 'vertex'; if (inVertex) count = +t[2]; }
    else if (t[0] === 'property' && inVertex) {
      const sz = PROP_SIZE[t[1]];
      if (!sz) throw new Error(`PLY: unsupported property type ${t[1]}`);
      fields[t[2]] = { type: t[1], off: offset };
      offset += sz;
    }
  }
  const stride = offset;
  const step = Math.max(1, Math.ceil(count / MAX_POINTS));
  const n = count ? Math.floor((count - 1) / step) + 1 : 0;
  const pos = new Float32Array(n * 3);
  const col = new Float32Array(n * 3);
  const cls = new Uint8Array(n);
  const dv = new DataView(buf, dataStart);
  const f = (name) => fields[name]?.off;
  const [ox, oy, oz] = [f('x'), f('y'), f('z')];
  const [or_, og, ob] = [f('red'), f('green'), f('blue')];
  const oc = f('classification');
  const hasRgb = or_ !== undefined && og !== undefined && ob !== undefined;
  let maxRgb = 0;
  for (let i = 0; i < n; i++) {
    const base = i * step * stride;
    pos[i * 3] = dv.getFloat32(base + ox, true);
    pos[i * 3 + 1] = dv.getFloat32(base + oy, true);
    pos[i * 3 + 2] = dv.getFloat32(base + oz, true);
    if (hasRgb) {
      const r = dv.getUint8(base + or_), g = dv.getUint8(base + og), b = dv.getUint8(base + ob);
      if (r > maxRgb) maxRgb = r; if (g > maxRgb) maxRgb = g; if (b > maxRgb) maxRgb = b;
      col[i * 3] = r / 255; col[i * 3 + 1] = g / 255; col[i * 3 + 2] = b / 255;
    }
    cls[i] = oc !== undefined ? dv.getUint8(base + oc) : 0;
  }
  return { n, total: count, step, pos, col, cls, hasRgb: hasRgb && maxRgb > 0 };
}

async function fetchWithProgress(url, note, signal) {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const total = +res.headers.get('content-length') || 0;
  if (!res.body) return res.arrayBuffer();
  const reader = res.body.getReader();
  const chunks = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value); got += value.length;
    showLoad(`${note} ${(got / 1048576).toFixed(1)}${total ? ' / ' + (total / 1048576).toFixed(1) : ''} MB`);
  }
  const out = new Uint8Array(got);
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out.buffer;
}

const showLoad = (msg) => { const el = $('loadMsg'); el.style.display = msg ? 'block' : 'none'; el.textContent = msg || ''; };

// ---------- point cloud + LoD2 objects ----------
function heightRamp(t) {
  const stops = [[0.12, 0.25, 0.68], [0.06, 0.72, 0.51], [0.99, 0.87, 0.28], [0.97, 0.31, 0.27]];
  const x = Math.min(0.99999, Math.max(0, t)) * (stops.length - 1);
  const i = Math.floor(x), u = x - i;
  return [0, 1, 2].map((k) => stops[i][k] * (1 - u) + stops[i + 1][k] * u);
}

function zRange(raw) {
  if (!raw.n) return [0, 1];
  const zs = [];
  const step = Math.max(1, Math.floor(raw.n / 5000));
  for (let i = 0; i < raw.n; i += step) zs.push(raw.pos[i * 3 + 2]);
  zs.sort((a, b) => a - b);
  const lo = zs[Math.floor(zs.length * 0.02)], hi = zs[Math.floor(zs.length * 0.98)];
  return hi > lo ? [lo, hi] : [lo, lo + 1];
}

function buildPoints(arm, raw) {
  const keep = [];
  for (let i = 0; i < raw.n; i++) {
    if (!prefs.showNonBldg && raw.cls[i] !== 6) continue;
    keep.push(i);
  }
  const pos = new Float32Array(keep.length * 3);
  const col = new Float32Array(keep.length * 3);
  const mode = (prefs.colorMode === 'rgb' && !raw.hasRgb) ? 'height' : prefs.colorMode;
  const [zlo, zhi] = mode === 'height' ? zRange(raw) : [0, 1];
  for (let j = 0; j < keep.length; j++) {
    const i = keep[j];
    pos[j * 3] = raw.pos[i * 3]; pos[j * 3 + 1] = raw.pos[i * 3 + 1]; pos[j * 3 + 2] = raw.pos[i * 3 + 2];
    let c;
    if (mode === 'rgb') c = [raw.col[i * 3], raw.col[i * 3 + 1], raw.col[i * 3 + 2]];
    else if (mode === 'height') c = heightRamp((raw.pos[i * 3 + 2] - zlo) / (zhi - zlo));
    else if (mode === 'cls') c = CLS_RGB[raw.cls[i]] ?? CLS_OTHER_RGB;
    else c = COND_RGB[arm];
    col[j * 3] = c[0]; col[j * 3 + 1] = c[1]; col[j * 3 + 2] = c[2];
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.computeBoundingSphere();
  const mat = new THREE.PointsMaterial({ size: prefs.ptSize, sizeAttenuation: false, vertexColors: true });
  return new THREE.Points(geo, mat);
}

function disposeObj(obj) {
  if (!obj) return;
  scene.remove(obj);
  obj.traverse?.((o) => { o.geometry?.dispose(); o.material?.dispose(); });
  obj.geometry?.dispose(); obj.material?.dispose();
}

function ringGeometry(ring) {
  let pts = ring.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
  if (pts.length > 1 && pts[0].distanceTo(pts[pts.length - 1]) < 1e-6) pts = pts.slice(0, -1);
  if (pts.length < 3) return null;
  // Newell normal, then an in-plane (u,v) basis for triangulation.
  const nrm = new THREE.Vector3();
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    nrm.x += (a.y - b.y) * (a.z + b.z);
    nrm.y += (a.z - b.z) * (a.x + b.x);
    nrm.z += (a.x - b.x) * (a.y + b.y);
  }
  if (nrm.lengthSq() < 1e-12) return null;
  nrm.normalize();
  const e = pts[1].clone().sub(pts[0]);
  const u = e.sub(nrm.clone().multiplyScalar(e.dot(nrm)));
  if (u.lengthSq() < 1e-12) return null;
  u.normalize();
  const w = nrm.clone().cross(u);
  const uv = pts.map((p) => {
    const d = p.clone().sub(pts[0]);
    return new THREE.Vector2(d.dot(u), d.dot(w));
  });
  let tris;
  try { tris = THREE.ShapeUtils.triangulateShape(uv, []); }
  catch { return null; }
  if (!tris.length) return null;
  const posArr = new Float32Array(pts.length * 3);
  pts.forEach((p, i) => { posArr[i * 3] = p.x; posArr[i * 3 + 1] = p.y; posArr[i * 3 + 2] = p.z; });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(posArr, 3));
  geo.setIndex(tris.flat());
  geo.computeVertexNormals();
  return { geo, pts };
}

function buildLod2(b) {
  const group = new THREE.Group();
  const faceMat = new THREE.MeshBasicMaterial({
    color: LOD2_COLOR, transparent: true, opacity: prefs.lodOpacity,
    side: THREE.DoubleSide, depthWrite: false,
  });
  const edgeMat = new THREE.LineBasicMaterial({ color: 0xfacc15 });
  for (const ring of b.lod2_rings) {
    const r = ringGeometry(ring);
    if (!r) continue;
    group.add(new THREE.Mesh(r.geo, faceMat));
    const lineGeo = new THREE.BufferGeometry().setFromPoints(r.pts);
    group.add(new THREE.LineLoop(lineGeo, edgeMat));
  }
  return group;
}

// ---------- building lifecycle ----------
function currentBuilding() { return buildings[state.index]; }

async function loadArm(arm, b, gen) {
  const rel = b.assets[arm];
  if (!rel) return;
  try {
    const buf = await fetchWithProgress('./' + rel, `${arm} 로딩`, state.aborter?.signal);
    if (gen !== state.loadGen) return;
    const raw = parsePly(buf);
    const points = buildPoints(arm, raw);
    state.clouds[arm] = { raw, points };
    points.visible = arm === 'E1' ? prefs.showE1 : prefs.showE2;
    scene.add(points);
    if (arm === 'E1') fitView();
    showLoad('');
    if (raw.step > 1) showTransient(`${arm}: ${raw.total.toLocaleString()}점 → 1/${raw.step} 서브샘플 표시`);
    invalidate();
  } catch (err) {
    if (err.name === 'AbortError') return;
    if (gen === state.loadGen) showLoad(`${arm} 로드 실패: ${err.message}`);
  }
}

let transientTimer = 0;
function showTransient(msg) {
  showLoad(msg);
  clearTimeout(transientTimer);
  transientTimer = setTimeout(() => showLoad(''), 3500);
}

function fitView() {
  const box = new THREE.Box3();
  const c = state.clouds.E1;
  if (c?.raw.n) {
    const step = Math.max(1, Math.floor(c.raw.n / 4000));
    for (let i = 0; i < c.raw.n; i += step) {
      box.expandByPoint(new THREE.Vector3(c.raw.pos[i * 3], c.raw.pos[i * 3 + 1], c.raw.pos[i * 3 + 2]));
    }
  }
  for (const ring of currentBuilding().lod2_rings) {
    for (const p of ring) box.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
  }
  orbit.fit(box);
}

function select(idx, { keepCamera = false } = {}) {
  state.index = Math.min(buildings.length - 1, Math.max(0, idx));
  state.loadGen += 1;
  state.aborter?.abort();
  state.aborter = new AbortController();
  for (const arm of Object.keys(state.clouds)) { disposeObj(state.clouds[arm].points); delete state.clouds[arm]; }
  disposeObj(state.lod2Group); state.lod2Group = null;
  const b = currentBuilding();
  state.lod2Group = buildLod2(b);
  state.lod2Group.visible = prefs.showLod2;
  scene.add(state.lod2Group);
  if (!keepCamera) fitView();
  loadArm('E1', b, state.loadGen);
  if (prefs.showE2) loadArm('E2', b, state.loadGen);
  history.replaceState(null, '', '#' + b.bkey);
  renderSidebar();
  renderList();
  invalidate();
}

// ---------- UI: list / filters / progress ----------
function shortId(sid) { const m = sid.match(/(\d+)$/); return m ? m[1] : sid; }
function tierShort(t) { return t.startsWith('A') ? 'A' : 'B'; }

function visibleInList(b) {
  if (state.filterTier !== 'ALL' && tierShort(b.tier) !== state.filterTier) return false;
  const lab = labels[b.stable_id]?.label;
  if (state.filterLab === 'TODO' && lab) return false;
  if (state.filterLab === 'DONE' && !lab) return false;
  return true;
}

function renderList() {
  const host = $('buildingList');
  host.textContent = '';
  buildings.forEach((b, i) => {
    if (!visibleInList(b)) return;
    const row = document.createElement('div');
    row.className = 'bitem' + (i === state.index ? ' sel' : '');
    const lab = labels[b.stable_id]?.label;
    const gateFail = b.coverage && b.coverage.gate_any_070 === false;
    row.innerHTML = `
      <span class="dot ${lab ?? ''}"></span>
      <span class="tier ${tierShort(b.tier)}">${tierShort(b.tier)}</span>
      <span class="bid">${b.bkey} · ${shortId(b.stable_id)}</span>
      ${gateFail ? '<span class="gate" title="E1·E2 모두 LoD2 지붕 자리 커버리지 70% 미만">⊘</span>' : ''}
      <span class="acc">${b.metrics.e1_lod2_acc_median_m.toFixed(2)}m</span>`;
    row.addEventListener('click', () => select(i));
    host.appendChild(row);
    if (i === state.index) queueMicrotask(() => row.scrollIntoView({ block: 'nearest' }));
  });
  renderProgress();
}

function renderProgress() {
  const counts = emptyCounts();
  let done = 0;
  for (const b of buildings) {
    const l = labels[b.stable_id]?.label;
    if (l) { done += 1; counts[l] = (counts[l] ?? 0) + 1; }
  }
  $('progress').innerHTML =
    `라벨 <b>${done}</b>/${buildings.length} · ` +
    `<span style="color:var(--change)">변화 ${counts.CHANGE}</span> · ` +
    `<span style="color:var(--nochange)">비변화 ${counts.NO_CHANGE}</span> · ` +
    `<span style="color:var(--abst)">추상화 ${counts.ABSTRACTION_MISMATCH}</span> · ` +
    `<span style="color:var(--undec)">불능 ${counts.UNDECIDABLE}</span>`;
}

function renderSidebar() {
  const b = currentBuilding();
  $('bTitle').textContent = `${b.bkey} — ${b.stable_id}`;
  $('bSub').textContent = `${b.tier} · ${state.index + 1}/${buildings.length}` +
    (b.assets.E2 ? '' : ' · E2 자산 없음');
  const m = b.metrics;
  $('metricsTable').innerHTML = `
    <tr><td>completeness@0.5</td><td>${m.e1_lod2_completeness_0p5.toFixed(3)}</td></tr>
    <tr><td>acc_median (E1 지붕점→LoD2 면)</td><td>${m.e1_lod2_acc_median_m.toFixed(2)} m</td></tr>
    <tr><td>f1@0.5</td><td>${m.e1_lod2_f1_0p5.toFixed(3)}</td></tr>
    <tr><td>E1 지붕점 수</td><td>${m.n_e1_roof_pts.toLocaleString()}</td></tr>
    ${m.flag ? `<tr><td>플래그</td><td>${m.flag}</td></tr>` : ''}
    <tr><td>LoD2 지붕면 링</td><td>${b.lod2_rings.length}</td></tr>`;
  renderCoverage(b);
  const rec = labels[b.stable_id] ?? {};
  for (const l of LABELS) $('btn' + l).classList.toggle('on', rec.label === l);
  const note = $('noteBox');
  if (note.value !== (rec.note ?? '')) note.value = rec.note ?? '';
}

function covTags(b) {
  const c = b.coverage;
  const e1 = c.E1, e2 = c.E2;
  const tags = [];
  const maxAny = Math.max(e1?.any_xy ?? 0, e2?.any_xy ?? 0);
  if (c.gate_any_070 === false) {
    const npts = Math.max(e1?.n_pts ?? 0, e2?.n_pts ?? 0);
    if (npts < 5000) tags.push(['bad', '공백 — E1·E2 모두 데이터 부족 (판정불능 후보)']);
    else tags.push(['warn', '변위/형상 — 데이터는 있으나 LoD2 자리 밖 (변화 후보)']);
  } else tags.push(['ok', `커버리지 확보 max ${Math.round(maxAny * 100)}%`]);
  if ((e1?.groundonly_xy ?? 0) >= 0.3) tags.push(['bad', `지면화 ${Math.round(e1.groundonly_xy * 100)}% — 철거 의심`]);
  if ((e1?.above_ridge_share ?? 0) >= 0.25 || (e1?.veg_cell_share ?? 0) >= 0.3) {
    tags.push(['warn', '수목 오분류 의심 — 건물 분류(c6)에 수관 혼입']);
  }
  const dz = e1?.dz_med_m;
  if (dz != null && Math.abs(dz) >= 1 && (e1?.any_xy ?? 0) >= 0.5) {
    tags.push(['warn', `Δz ${dz > 0 ? '+' : ''}${dz}m — 증고/추상화 의심`]);
  }
  return tags;
}

function renderCoverage(b) {
  const el = $('covBadge');
  if (!b.coverage) { el.textContent = '진단 데이터 없음'; return; }
  const pct = (v) => (v == null ? '—' : Math.round(v * 100) + '%');
  const armRow = (name, a) => {
    if (!a) return '';
    const extra =
      (a.dz_med_m != null ? ` · Δz ${a.dz_med_m > 0 ? '+' : ''}${a.dz_med_m}m` : '') +
      (a.above_ridge_share != null ? ` · 릿지위 ${pct(a.above_ridge_share)}` : '') +
      (a.veg_cell_share != null ? ` · 수관성 ${pct(a.veg_cell_share)}` : '');
    return `<tr><td>${name}</td><td>존재 ${pct(a.any_xy)} · 건물 ${pct(a.cls6_xy)} · 지면만 ${pct(a.groundonly_xy)}${extra}</td></tr>`;
  };
  el.innerHTML = covTags(b).map(([k, t]) => `<span class="tag ${k}">${t}</span>`).join('') +
    `<table>${armRow('E1', b.coverage.E1)}${armRow('E2', b.coverage.E2)}</table>`;
}

// ---------- labeling ----------
function setLabel(label) {
  const sid = currentBuilding().stable_id;
  const rec = labels[sid] ?? {};
  rec.label = rec.label === label ? null : label;   // same key toggles off
  rec.updated_utc = new Date().toISOString();
  labels[sid] = rec;
  saveLabels();
  flashSaved(rec.label ? `${LABEL_KO[rec.label]} 저장됨` : '라벨 해제됨');
  renderSidebar(); renderList();
}

function clearLabel() {
  const sid = currentBuilding().stable_id;
  if (!labels[sid]) return;
  labels[sid].label = null;
  labels[sid].updated_utc = new Date().toISOString();
  saveLabels();
  flashSaved('라벨 해제됨');
  renderSidebar(); renderList();
}

let flashTimer = 0;
function flashSaved(msg) {
  $('savedFlash').textContent = msg;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => { $('savedFlash').textContent = ''; }, 1800);
}

let noteTimer = 0;
$('noteBox').addEventListener('input', () => {
  clearTimeout(noteTimer);
  noteTimer = setTimeout(() => {
    const sid = currentBuilding().stable_id;
    const rec = labels[sid] ?? (labels[sid] = {});
    rec.note = $('noteBox').value;
    rec.updated_utc = new Date().toISOString();
    saveLabels();
    flashSaved('메모 저장됨');
    renderList();
  }, 400);
});

// ---------- export / import / reset ----------
function exportJson() {
  const counts = emptyCounts();
  const out = {};
  for (const b of buildings) {
    const rec = labels[b.stable_id];
    if (!rec || (!rec.label && !rec.note)) continue;
    out[b.stable_id] = {
      tier: b.tier, label: rec.label ?? null, note: rec.note ?? '',
      updated_utc: rec.updated_utc,
      gate_any_070: b.coverage?.gate_any_070 ?? null,
    };
    if (rec.label) counts[rec.label] += 1;
  }
  const payload = {
    schema: 'journal1_phase_b_change_labels_v1',
    task_id: manifest.task_id,
    status: manifest.status,
    scientific_verdict: null,
    source_csv: manifest.source_csv,
    source_csv_sha256: manifest.source_csv_sha256,
    frame: manifest.frame,
    label_values: LABELS,
    exported_utc: new Date().toISOString(),
    n_candidates: buildings.length,
    n_labeled: Object.values(out).filter((r) => r.label).length,
    counts,
    labels: out,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `journal1_phase_b_labels_${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function importJson(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (data.schema !== 'journal1_phase_b_change_labels_v1' || typeof data.labels !== 'object') {
        alert('스키마가 다른 파일입니다 (journal1_phase_b_change_labels_v1 아님).');
        return;
      }
      const n = Object.keys(data.labels).length;
      if (!confirm(`${n}건을 가져와 병합할까요? (가져온 항목이 우선합니다)`)) return;
      for (const [sid, rec] of Object.entries(data.labels)) {
        labels[sid] = { label: rec.label ?? null, note: rec.note ?? '', updated_utc: rec.updated_utc ?? new Date().toISOString() };
      }
      saveLabels();
      renderSidebar(); renderList();
      flashSaved(`${n}건 가져옴`);
    } catch (e) { alert('가져오기 실패: ' + e.message); }
  };
  reader.readAsText(file);
}

// ---------- toggle / control wiring ----------
function applyPrefControls() {
  $('tglE1').checked = prefs.showE1;
  $('tglLod2').checked = prefs.showLod2;
  $('tglE2').checked = prefs.showE2;
  $('tglNonBldg').checked = prefs.showNonBldg;
  $('colorMode').value = prefs.colorMode;
  $('ptSize').value = prefs.ptSize; $('ptSizeVal').textContent = prefs.ptSize;
  $('lodOpacity').value = prefs.lodOpacity; $('lodOpacityVal').textContent = prefs.lodOpacity;
  $('legendE2').style.display = prefs.showE2 ? '' : 'none';
}

function rebuildClouds() {
  for (const [arm, c] of Object.entries(state.clouds)) {
    disposeObj(c.points);
    c.points = buildPoints(arm, c.raw);
    c.points.visible = arm === 'E1' ? prefs.showE1 : prefs.showE2;
    scene.add(c.points);
  }
  invalidate();
}

$('tglE1').addEventListener('change', (e) => {
  prefs.showE1 = e.target.checked; savePrefs();
  if (state.clouds.E1) state.clouds.E1.points.visible = prefs.showE1;
  invalidate();
});
$('tglLod2').addEventListener('change', (e) => {
  prefs.showLod2 = e.target.checked; savePrefs();
  if (state.lod2Group) state.lod2Group.visible = prefs.showLod2;
  invalidate();
});
$('tglE2').addEventListener('change', (e) => {
  prefs.showE2 = e.target.checked; savePrefs();
  $('legendE2').style.display = prefs.showE2 ? '' : 'none';
  if (state.clouds.E2) { state.clouds.E2.points.visible = prefs.showE2; invalidate(); }
  else if (prefs.showE2) loadArm('E2', currentBuilding(), state.loadGen);
});
$('tglNonBldg').addEventListener('change', (e) => { prefs.showNonBldg = e.target.checked; savePrefs(); rebuildClouds(); });
$('colorMode').addEventListener('change', (e) => { prefs.colorMode = e.target.value; savePrefs(); rebuildClouds(); });
$('ptSize').addEventListener('input', (e) => {
  prefs.ptSize = +e.target.value; $('ptSizeVal').textContent = prefs.ptSize; savePrefs();
  for (const c of Object.values(state.clouds)) c.points.material.size = prefs.ptSize;
  invalidate();
});
$('lodOpacity').addEventListener('input', (e) => {
  prefs.lodOpacity = +e.target.value; $('lodOpacityVal').textContent = prefs.lodOpacity; savePrefs();
  state.lod2Group?.traverse((o) => { if (o.isMesh) o.material.opacity = prefs.lodOpacity; });
  invalidate();
});

document.querySelectorAll('.filters button').forEach((btn) => {
  btn.addEventListener('click', () => {
    const [kind, val] = btn.dataset.f.split(':');
    if (kind === 'tier') state.filterTier = val;
    else state.filterLab = val;
    document.querySelectorAll(`.filters button[data-f^="${kind}:"]`)
      .forEach((b) => b.classList.toggle('on', b === btn));
    renderList();
  });
});

// prev/next move within the current list filter (wrap-around)
function stepFiltered(dir) {
  const vis = buildings.map((b, i) => (visibleInList(b) ? i : -1)).filter((i) => i >= 0);
  if (!vis.length) return;
  if (dir > 0) select(vis.find((i) => i > state.index) ?? vis[0]);
  else {
    const before = vis.filter((i) => i < state.index);
    select(before.length ? before[before.length - 1] : vis[vis.length - 1]);
  }
}
$('prevBtn').addEventListener('click', () => stepFiltered(-1));
$('nextBtn').addEventListener('click', () => stepFiltered(1));
$('fitBtn').addEventListener('click', fitView);
for (const l of LABELS) $('btn' + l).addEventListener('click', () => setLabel(l));
$('btnClear').addEventListener('click', clearLabel);
$('exportBtn').addEventListener('click', exportJson);
$('exportBtn2').addEventListener('click', exportJson);
$('importBtn').addEventListener('click', () => $('importFile').click());
$('importFile').addEventListener('change', (e) => { if (e.target.files[0]) importJson(e.target.files[0]); e.target.value = ''; });
$('bulkApply').addEventListener('click', () => {
  const label = $('bulkLabel').value;
  const vis = buildings.filter(visibleInList);
  const todo = vis.filter((b) => !labels[b.stable_id]?.label);
  if (!todo.length) { alert('현재 필터에 미라벨 건물이 없습니다.'); return; }
  if (!confirm(`현재 필터 ${vis.length}동 중 미라벨 ${todo.length}동에 '${LABEL_KO[label]}' 라벨을 일괄 적용할까요?\n(이미 라벨된 건물은 건드리지 않습니다)`)) return;
  const now = new Date().toISOString();
  for (const b of todo) {
    const rec = labels[b.stable_id] ?? (labels[b.stable_id] = {});
    rec.label = label;
    rec.updated_utc = now;
  }
  saveLabels();
  renderSidebar(); renderList();
  flashSaved(`${todo.length}동 일괄 적용됨`);
});
$('resetBtn').addEventListener('click', () => {
  if (!confirm('이 브라우저에 저장된 라벨·메모를 전부 삭제할까요? (내보낸 JSON은 영향 없음)')) return;
  labels = {};
  saveLabels();
  renderSidebar(); renderList();
});

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowLeft') stepFiltered(-1);
  else if (e.key === 'ArrowRight') stepFiltered(1);
  else if (e.key === '1') setLabel('CHANGE');
  else if (e.key === '2') setLabel('NO_CHANGE');
  else if (e.key === '3') setLabel('ABSTRACTION_MISMATCH');
  else if (e.key === '4') setLabel('UNDECIDABLE');
  else if (e.key === '0') clearLabel();
  else if (e.key === 'f' || e.key === 'F') fitView();
  else if (e.key === 'e' || e.key === 'E') { $('tglE2').checked = !prefs.showE2; $('tglE2').dispatchEvent(new Event('change')); }
  else if (e.key === 'l' || e.key === 'L') { $('tglLod2').checked = !prefs.showLod2; $('tglLod2').dispatchEvent(new Event('change')); }
  else if (e.key === 'g' || e.key === 'G') { $('tglNonBldg').checked = !prefs.showNonBldg; $('tglNonBldg').dispatchEvent(new Event('change')); }
});

// ---------- boot ----------
applyPrefControls();
resize();
{
  const want = location.hash.slice(1);
  const idx = want ? buildings.findIndex((b) => b.bkey === want) : -1;
  select(idx >= 0 ? idx : 0);
}
