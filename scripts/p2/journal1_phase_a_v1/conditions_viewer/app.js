// journal1 A2 — multi-condition comparison viewer (scene + per-building modes).
// Full-AOI voxel scenes or per-building crops per arm (E1/E2/E7/E8 primary,
// E3/E4_V2/E5_V2 secondary) against the existing LoD2 RoofSurface overlay.
// Inspection tooling only; no metric is computed here. Orbit/PLY machinery
// follows the Phase-B viewer.
import * as THREE from './three.module.min.js';

const LS_PREFS = 'jbgs-journal1-a2-conditions-viewprefs-v2';
const LS_SEL_OVERRIDES = 'jbgs-journal1-a2-selection-overrides-v1';
const MAX_POINTS = 4_000_000;
const ARM_RGB = {
  E1: [40 / 255, 150 / 255, 1], E2: [1, 145 / 255, 35 / 255],
  E7: [52 / 255, 211 / 255, 153 / 255], E8: [232 / 255, 121 / 255, 249 / 255],
  E3: [148 / 255, 163 / 255, 184 / 255], E4_V2: [244 / 255, 63 / 255, 94 / 255],
  E5_V2: [20 / 255, 184 / 255, 166 / 255],
  E8_dx100: [162 / 255, 28 / 255, 175 / 255], E7_dx100: [21 / 255, 128 / 255, 61 / 255],
  GS55_0: [251 / 255, 191 / 255, 36 / 255], GS55_dx050: [146 / 255, 64 / 255, 14 / 255],
};
const ARM_HEX = { E1: '#2896ff', E2: '#ff9123', E7: '#34d399', E8: '#e879f9',
  E3: '#94a3b8', E4_V2: '#f43f5e', E5_V2: '#14b8a6',
  E8_dx100: '#a21caf', E7_dx100: '#15803d',
  GS55_0: '#fbbf24', GS55_dx050: '#92400e' };
const CLS_RGB = { 6: [0.23, 0.51, 0.96], 2: [0.55, 0.56, 0.6] };
const CLS_OTHER_RGB = [0.49, 0.36, 0.68];
const LOD2_COLOR = 0xeab308;

const $ = (id) => document.getElementById(id);
const manifest = await (await fetch('./conditions_manifest.json')).json();
const ARMS = manifest.arms.map((a) => a.id);
const allBuildings = manifest.buildings;

function loadJson(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}
const prefs = Object.assign({
  viewMode: 'scene',
  show: { E1: true, E2: false, E7: false, E8: false, E3: false, E4_V2: false, E5_V2: false },
  showLod2: true, showNonBldg: true, colorMode: 'arm', ptSize: 2, lodOpacity: 0.35,
  sortMode: 'index', tierFilter: 'ALL', selFilter: 'ALL', stratumView: 'OFF', showBoundary: true,
}, loadJson(LS_PREFS, {}));
prefs.show = Object.assign({ E1: true }, prefs.show);
const savePrefs = () => localStorage.setItem(LS_PREFS, JSON.stringify(prefs));
let selOverrides = loadJson(LS_SEL_OVERRIDES, {});   // {sid: true|false}
const saveOverrides = () => localStorage.setItem(LS_SEL_OVERRIDES, JSON.stringify(selOverrides));
const hasSelection = !!manifest.selection;
const effSel = (b) => b.sel ? (selOverrides[b.stable_id] ?? b.sel.selected) : null;

const state = {
  index: 0, view: [], loadGen: 0, aborter: null,
  clouds: {},                 // building mode: arm -> {raw, points}
  lod2Group: null,            // building mode LoD2
  sceneClouds: {},            // scene mode: arm -> {raw, points} (persistent cache)
  sceneLod2: null,            // merged all-199 LoD2 (selected/excluded split)
  boundary: null,             // scene mode: E1 coverage boundary rings
  highlight: null,            // scene mode: selected building edge highlight
};

// ---------- three.js scene ----------
const canvas = $('canvas');
if (THREE.ColorManagement) THREE.ColorManagement.enabled = false;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
if (THREE.LinearSRGBColorSpace) renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);
const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 8000);
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
      this.r = Math.min(6000, Math.max(1.5, this.r * Math.exp(e.deltaY * 0.0011)));
      this.update();
    }, { passive: false });
  }
  pinch(e) {
    const [a, b] = [...this.ptrs.values()];
    const cur = Math.hypot(a.x - b.x, a.y - b.y);
    const p = this.ptrs.get(e.pointerId); p.x = e.clientX; p.y = e.clientY;
    const nxt = Math.hypot(a.x - b.x, a.y - b.y);
    if (cur > 0 && nxt > 0) { this.r = Math.min(6000, Math.max(1.5, this.r * cur / nxt)); this.update(); }
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
  fit(box, factor = 0.85) {
    if (box.isEmpty()) return;
    box.getCenter(this.target);
    const s = box.getSize(new THREE.Vector3()).length();
    this.r = Math.max(8, s * factor);
    this.update();
  }
  flyTo(center, r) { this.target.copy(center); this.r = r; this.update(); }
}
const orbit = new Orbit(camera, canvas);

// ---------- scene-mode picking (click = select, shift+click = toggle include) ----------
const raycaster = new THREE.Raycaster();
const pickIndex = allBuildings.map((b) => {
  const rings2d = b.lod2_rings.map((ring) => ring.map((p) => [p[0], p[1]]));
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const ring of rings2d) for (const [x, y] of ring) {
    if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
  }
  return { b, rings2d, bbox: [x0, y0, x1, y1] };
});

function inRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}

function buildingAtXY(x, y) {
  let best = null, bestD = 30 * 30;
  for (const { b, rings2d, bbox } of pickIndex) {
    if (!rings2d.length) continue;
    if (x >= bbox[0] - 3 && x <= bbox[2] + 3 && y >= bbox[1] - 3 && y <= bbox[3] + 3) {
      for (const ring of rings2d) if (inRing(x, y, ring)) return b;
    }
    if (b.center) {
      const d = (b.center[0] - x) ** 2 + (b.center[1] - y) ** 2;
      if (d < bestD) { bestD = d; best = b; }
    }
  }
  return best;
}

function groundZGuess() {
  const c = Object.values(state.sceneClouds).find((v) => v.raw?.n);
  if (c) {
    const zs = [];
    const step = Math.max(1, Math.floor(c.raw.n / 3000));
    for (let i = 0; i < c.raw.n; i += step) zs.push(c.raw.pos[i * 3 + 2]);
    zs.sort((a, b) => a - b);
    return zs[Math.floor(zs.length * 0.05)];
  }
  const cz = allBuildings.map((b) => b.center?.[2]).filter((v) => v != null).sort((a, b) => a - b);
  return cz.length ? cz[Math.floor(cz.length / 2)] - 10 : 20;
}

function pickAt(e, { toggle = false } = {}) {
  const rect = canvas.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  let p = null;
  if (state.sceneLod2?.visible) {
    const hits = raycaster.intersectObject(state.sceneLod2, true);
    if (hits.length) p = hits[0].point;
  }
  if (!p) {
    const z = groundZGuess();
    const t = (z - raycaster.ray.origin.z) / raycaster.ray.direction.z;
    if (t > 0) p = raycaster.ray.origin.clone().addScaledVector(raycaster.ray.direction, t);
  }
  if (!p) return;
  const b = buildingAtXY(p.x, p.y);
  if (!b) return;
  let idx = state.view.findIndex((v) => v.stable_id === b.stable_id);
  if (idx < 0) {
    prefs.tierFilter = 'ALL'; prefs.selFilter = 'ALL'; savePrefs();
    $('tierFilter').value = 'ALL';
    if (hasSelection) $('selFilter').value = 'ALL';
    applyViewOrder();
    idx = state.view.findIndex((v) => v.stable_id === b.stable_id);
    if (idx < 0) return;
  }
  select(idx, { keepCamera: true });
  if (toggle) toggleSelection(b);
}

function toggleSelection(b) {
  if (!b?.sel) return;
  const now = effSel(b);
  if (b.sel.selected === !now) delete selOverrides[b.stable_id];
  else selOverrides[b.stable_id] = !now;
  saveOverrides(); rebuildSceneLod2(); renderDetail(); renderList(); renderHud();
}

let pressPos = null;
canvas.addEventListener('pointerdown', (e) => { if (e.button === 0) pressPos = { x: e.clientX, y: e.clientY, shift: e.shiftKey }; });
canvas.addEventListener('pointerup', (e) => {
  if (!pressPos || e.button !== 0) { pressPos = null; return; }
  const moved = Math.hypot(e.clientX - pressPos.x, e.clientY - pressPos.y);
  const shift = pressPos.shift || e.shiftKey;
  pressPos = null;
  if (moved < 6 && inScene()) pickAt(e, { toggle: shift });
});

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

// ---------- binary PLY ----------
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
    if (t[0] === 'format' && t[1] !== 'binary_little_endian') throw new Error(`PLY: unsupported ${t[1]}`);
    if (t[0] === 'element') { inVertex = t[1] === 'vertex'; if (inVertex) count = +t[2]; }
    else if (t[0] === 'property' && inVertex) {
      const sz = PROP_SIZE[t[1]];
      if (!sz) throw new Error(`PLY: unsupported property ${t[1]}`);
      fields[t[2]] = { off: offset };
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

async function fetchBuf(url, note, signal) {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  if (!res.body) return res.arrayBuffer();
  const total = +res.headers.get('content-length') || 0;
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

// ---------- point/LoD2 objects ----------
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
  const mode = (prefs.colorMode === 'rgb' && !raw.hasRgb) ? 'arm' : prefs.colorMode;
  const [zlo, zhi] = mode === 'height' ? zRange(raw) : [0, 1];
  for (let j = 0; j < keep.length; j++) {
    const i = keep[j];
    pos[j * 3] = raw.pos[i * 3]; pos[j * 3 + 1] = raw.pos[i * 3 + 1]; pos[j * 3 + 2] = raw.pos[i * 3 + 2];
    let c;
    if (mode === 'rgb') c = [raw.col[i * 3], raw.col[i * 3 + 1], raw.col[i * 3 + 2]];
    else if (mode === 'height') c = heightRamp((raw.pos[i * 3 + 2] - zlo) / (zhi - zlo));
    else if (mode === 'cls') c = CLS_RGB[raw.cls[i]] ?? CLS_OTHER_RGB;
    else c = ARM_RGB[arm] ?? [0.8, 0.8, 0.8];
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

function mergedLod2(buildingsSubset, faceColor, edgeColor, faceOpacity) {
  const positions = [];
  const indices = [];
  const linePositions = [];
  let vertexBase = 0;
  for (const b of buildingsSubset) {
    for (const ring of b.lod2_rings) {
      const r = ringGeometry(ring);
      if (!r) continue;
      const pa = r.geo.getAttribute('position').array;
      const ia = r.geo.getIndex().array;
      positions.push(...pa);
      for (const ii of ia) indices.push(ii + vertexBase);
      vertexBase += pa.length / 3;
      const pts = r.pts;
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i], c = pts[(i + 1) % pts.length];
        linePositions.push(a.x, a.y, a.z, c.x, c.y, c.z);
      }
    }
  }
  const group = new THREE.Group();
  const meshGeo = new THREE.BufferGeometry();
  meshGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
  meshGeo.setIndex(new THREE.BufferAttribute(new Uint32Array(indices), 1));
  group.add(new THREE.Mesh(meshGeo, new THREE.MeshBasicMaterial({
    color: faceColor, transparent: true, opacity: faceOpacity,
    side: THREE.DoubleSide, depthWrite: false,
  })));
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(linePositions), 3));
  group.add(new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({ color: edgeColor })));
  return group;
}

function buildSceneLod2() {
  const group = new THREE.Group();
  // 층(채움-의존 45 / N12) 강조가 켜져 있으면 장면 LoD2를 그 기준으로 색칠:
  // 대상 = 주황(N12는 빨강), 나머지 = 흐림. 선정 색칠보다 우선.
  if (strata && prefs.stratumView !== 'OFF') {
    const inSet = (b) => prefs.stratumView === 'N12'
      ? strata.n12.has(b.stable_id) : strata.fill.has(b.stable_id);
    const hot = allBuildings.filter((b) => inSet(b));
    const hotN = hot.filter((b) => strata.n12.has(b.stable_id));
    const hotRest = hot.filter((b) => !strata.n12.has(b.stable_id));
    const cold = allBuildings.filter((b) => !inSet(b));
    group.add(mergedLod2(hotRest, 0xf97316, 0xfb923c, Math.max(0.35, prefs.lodOpacity)));
    group.add(mergedLod2(hotN, 0xef4444, 0xf87171, Math.max(0.4, prefs.lodOpacity)));
    group.add(mergedLod2(cold, 0x475569, 0x64748b, Math.min(0.10, prefs.lodOpacity)));
    return group;
  }
  if (hasSelection) {
    const chosen = allBuildings.filter((b) => effSel(b));
    const dropped = allBuildings.filter((b) => !effSel(b));
    group.add(mergedLod2(chosen, LOD2_COLOR, 0xfacc15, prefs.lodOpacity));
    group.add(mergedLod2(dropped, 0x6b7280, 0xf85149, Math.min(0.18, prefs.lodOpacity)));
  } else {
    group.add(mergedLod2(allBuildings, LOD2_COLOR, 0xfacc15, prefs.lodOpacity));
  }
  return group;
}

function rebuildSceneLod2() {
  if (!state.sceneLod2) return;
  const visible = state.sceneLod2.visible;
  disposeObj(state.sceneLod2);
  state.sceneLod2 = buildSceneLod2();
  state.sceneLod2.visible = visible;
  scene.add(state.sceneLod2);
  invalidate();
}

function buildBoundary() {
  const sel = manifest.selection;
  if (!sel) return null;
  const group = new THREE.Group();
  const covMat = new THREE.LineBasicMaterial({ color: 0x22d3ee });
  const intMat = new THREE.LineBasicMaterial({ color: 0x155e75 });
  for (const [rings, mat] of [[sel.coverage_rings, covMat], [sel.interior_rings, intMat]]) {
    for (const ring of rings) {
      const pts = ring.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
      group.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), mat));
    }
  }
  return group;
}

function buildHighlight(b) {
  const group = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({ color: 0xffffff });
  for (const ring of b.lod2_rings) {
    const pts = ring.map((p) => new THREE.Vector3(p[0], p[1], p[2] + 0.15));
    group.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), mat));
  }
  return group;
}

// ---------- lifecycle ----------
const current = () => state.view[state.index];
const inScene = () => prefs.viewMode === 'scene';

async function loadArm(arm, b, gen) {
  const rel = b.assets[arm];
  if (!rel || state.clouds[arm]) return;
  try {
    const buf = await fetchBuf('./' + rel, `${arm} 로딩`, state.aborter?.signal);
    if (gen !== state.loadGen || inScene()) return;
    const raw = parsePly(buf);
    const points = buildPoints(arm, raw);
    state.clouds[arm] = { raw, points };
    points.visible = !!prefs.show[arm];
    scene.add(points);
    showLoad('');
    renderArmToggles();
    invalidate();
  } catch (err) {
    if (err.name === 'AbortError') return;
    if (gen === state.loadGen) showLoad(`${arm} 로드 실패: ${err.message}`);
  }
}

async function loadSceneArm(arm) {
  if (state.sceneClouds[arm]) return;
  const spec = manifest.scene?.assets?.[arm];
  let url = spec ? './' + spec.path : null;
  let note = `${arm} 전체 로딩`;
  if (!url) {
    // Crop-only arm (e.g. corridor GS smoke): fall back to the building crop —
    // it is in the same viewer-local frame, so it renders in place in the scene.
    const rel = current()?.assets?.[arm]
      ?? allBuildings.find((b) => b.assets[arm])?.assets[arm];
    if (!rel) return;
    url = './' + rel;
    note = `${arm} (건물 크롭) 로딩`;
  }
  state.sceneClouds[arm] = { pending: true };
  try {
    const buf = await fetchBuf(url, note, null);
    const raw = parsePly(buf);
    const points = buildPoints(arm, raw);
    state.sceneClouds[arm] = { raw, points };
    points.visible = inScene() && !!prefs.show[arm];
    scene.add(points);
    showLoad('');
    renderArmToggles();
    invalidate();
  } catch (err) {
    delete state.sceneClouds[arm];
    showLoad(`${arm} 전체 로드 실패: ${err.message}`);
  }
}

function fitBuilding() {
  const box = new THREE.Box3();
  const first = ARMS.find((a) => state.clouds[a]?.raw?.n);
  if (first) {
    const c = state.clouds[first];
    const step = Math.max(1, Math.floor(c.raw.n / 4000));
    for (let i = 0; i < c.raw.n; i += step) {
      box.expandByPoint(new THREE.Vector3(c.raw.pos[i * 3], c.raw.pos[i * 3 + 1], c.raw.pos[i * 3 + 2]));
    }
  }
  for (const ring of current().lod2_rings) {
    for (const p of ring) box.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
  }
  orbit.fit(box);
}

function fitScene() {
  const box = new THREE.Box3();
  for (const b of allBuildings) {
    for (const ring of b.lod2_rings) {
      for (const p of ring) box.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
    }
  }
  orbit.fit(box, 0.6);
}

function applyMode({ fit = true } = {}) {
  const sceneMode = inScene();
  for (const arm of Object.keys(state.clouds)) {
    if (sceneMode) { disposeObj(state.clouds[arm].points); delete state.clouds[arm]; }
  }
  for (const [arm, c] of Object.entries(state.sceneClouds)) {
    if (c.points) c.points.visible = sceneMode && !!prefs.show[arm];
  }
  if (state.lod2Group) state.lod2Group.visible = !sceneMode && prefs.showLod2;
  if (sceneMode && !state.sceneLod2) { state.sceneLod2 = buildSceneLod2(); scene.add(state.sceneLod2); }
  if (state.sceneLod2) state.sceneLod2.visible = sceneMode && prefs.showLod2;
  if (sceneMode && !state.boundary) { state.boundary = buildBoundary(); if (state.boundary) scene.add(state.boundary); }
  if (state.boundary) state.boundary.visible = sceneMode && prefs.showBoundary;
  if (state.highlight) state.highlight.visible = sceneMode;
  $('modeHint').textContent = sceneMode
    ? '목록 클릭=해당 건물로 이동' : '목록 클릭=크롭 로드';
  if (sceneMode) {
    for (const arm of ARMS) if (prefs.show[arm]) loadSceneArm(arm);
    if (fit) fitScene();
  }
  renderArmToggles();
}

function select(idx, { keepCamera = false } = {}) {
  state.index = Math.min(state.view.length - 1, Math.max(0, idx));
  const b = current();
  if (!b) return;
  if (inScene()) {
    disposeObj(state.highlight);
    state.highlight = buildHighlight(b);
    scene.add(state.highlight);
    if (!keepCamera && b.center) {
      orbit.flyTo(new THREE.Vector3(b.center[0], b.center[1], b.center[2]), 55);
    }
  } else {
    state.loadGen += 1;
    state.aborter?.abort();
    state.aborter = new AbortController();
    for (const arm of Object.keys(state.clouds)) { disposeObj(state.clouds[arm].points); delete state.clouds[arm]; }
    disposeObj(state.lod2Group);
    state.lod2Group = buildLod2(b);
    state.lod2Group.visible = prefs.showLod2;
    scene.add(state.lod2Group);
    const gen = state.loadGen;
    const wanted = ARMS.filter((a) => prefs.show[a]);
    (async () => {
      for (const arm of wanted) await loadArm(arm, b, gen);
      if (gen === state.loadGen && !keepCamera) fitBuilding();
    })();
    if (!keepCamera && !wanted.length) fitBuilding();
  }
  renderDetail();
  renderList();
  renderHud();
  invalidate();
}

function rebuildAll() {
  const sets = [state.clouds, state.sceneClouds];
  for (const set of sets) {
    for (const arm of Object.keys(set)) {
      const c = set[arm];
      if (!c.raw) continue;
      const visible = c.points.visible;
      disposeObj(c.points);
      const points = buildPoints(arm, c.raw);
      points.visible = visible;
      set[arm] = { raw: c.raw, points };
      scene.add(points);
    }
  }
  invalidate();
}

// ---------- UI ----------
function shortId(sid) { const m = sid.match(/(\d+)$/); return m ? m[1] : sid; }
const tierClass = (t) => t?.[0] === 'A' ? 'A' : t?.[0] === 'B' ? 'B' : t?.[0] === 'C' ? 'C' : 'N';

function applyViewOrder() {
  let v = allBuildings.filter((b) => prefs.tierFilter === 'ALL' || tierClass(b.tier) === prefs.tierFilter);
  if (hasSelection && prefs.selFilter !== 'ALL') {
    v = v.filter((b) => prefs.selFilter === 'SEL' ? effSel(b) : !effSel(b));
  }
  if (strata && prefs.stratumView !== 'OFF') {
    v = v.filter((b) => prefs.stratumView === 'N12'
      ? strata.n12.has(b.stable_id) : strata.fill.has(b.stable_id));
  }
  if (prefs.sortMode !== 'index') {
    const key = prefs.sortMode;
    v = [...v].sort((a, b) => (b.deltas[key] ?? -9) - (a.deltas[key] ?? -9));
  }
  state.view = v;
}

function renderHud() {
  const b = current();
  if (!b) return;
  let selInfo = '';
  if (hasSelection) {
    const n = allBuildings.filter((x) => effSel(x)).length;
    const overrides = Object.keys(selOverrides).length;
    selInfo = ` · 선정 ${n}/199${overrides ? ` (수동 ${overrides})` : ''}`;
  }
  $('hud').innerHTML = `${inScene() ? '전체 장면 · ' : ''}<b>${b.bkey}</b> ${b.stable_id} · tier ${b.tier}${selInfo}`;
}

function armCloud(arm) { return inScene() ? state.sceneClouds[arm] : state.clouds[arm]; }

function renderArmToggles() {
  const b = current();
  const host = $('armToggles');
  host.innerHTML = '';
  ARMS.forEach((arm, i) => {
    const meta = manifest.arms[i];
    const m = b?.metrics?.[arm] ?? {};
    const cloud = armCloud(arm);
    const count = cloud?.raw ? cloud.raw.total.toLocaleString() + '점'
      : cloud?.pending ? '로딩…'
      : inScene() ? '' : (b?.assets?.[arm] ? '' : '자산 없음');
    const row = document.createElement('div');
    row.className = 'armRow';
    row.innerHTML = `
      <input type="checkbox" id="tglArm_${arm}" ${prefs.show[arm] ? 'checked' : ''}>
      <span class="chip" style="background:${ARM_HEX[arm]}"></span>
      <label for="tglArm_${arm}" title="${meta.lineage}">${arm}${meta.primary ? '' : ' ·'}</label>
      <span class="ox ${m.ox ?? ''}">${m.ox ?? ''}</span>
      <span class="cnt">${count}</span>`;
    host.appendChild(row);
    row.querySelector('input').addEventListener('change', (e) => {
      prefs.show[arm] = e.target.checked; savePrefs();
      const c = armCloud(arm);
      if (c?.points) { c.points.visible = prefs.show[arm]; invalidate(); }
      else if (prefs.show[arm]) inScene() ? loadSceneArm(arm) : loadArm(arm, current(), state.loadGen);
    });
  });
}

function renderDetail() {
  const b = current();
  if (!b) return;
  const rows = ARMS.map((arm) => {
    const m = b.metrics[arm] ?? {};
    const fmt = (v) => v == null ? '—' : v.toFixed(3);
    return `<tr><td><span class="chip" style="background:${ARM_HEX[arm]};display:inline-block;vertical-align:-1px"></span> ${arm}</td>
      <td>${fmt(m.f1_lod2)}</td><td>${fmt(m.f1_e1)}</td>
      <td class="ox ${m.ox ?? ''}">${m.ox ?? '—'}</td></tr>`;
  }).join('');
  let selHtml = '';
  if (b.sel) {
    const on = effSel(b);
    const zoneKo = { interior: '내부', boundary: '경계', outside: '외부' }[b.sel.zone] ?? b.sel.zone;
    const overridden = selOverrides[b.stable_id] !== undefined;
    selHtml = `<div class="selRow">
      <span class="selBadge ${on ? 'in' : 'out'}">${on ? '✓ 선정' : '✕ 제외'}</span>
      <span>${zoneKo}${b.sel.cover != null ? ` · E1 커버 ${(b.sel.cover * 100).toFixed(0)}%` : ''}${overridden ? ' · 수동' : ''}</span>
      <button id="btnSelToggle">${on ? '제외로' : '포함으로'}</button>
      ${overridden ? '<button id="btnSelReset">규칙값</button>' : ''}
    </div>`;
  }
  $('detail').innerHTML = `${selHtml}
    <table>
      <tr><th>arm</th><th>f1@0.5 lod2</th><th>f1@0.5 e1</th><th>O50</th></tr>
      ${rows}
    </table>`;
  $('btnSelToggle')?.addEventListener('click', () => toggleSelection(b));
  $('btnSelReset')?.addEventListener('click', () => {
    delete selOverrides[b.stable_id];
    saveOverrides(); rebuildSceneLod2(); renderDetail(); renderList(); renderHud();
  });
  renderArmToggles();
}

function exportSelection() {
  const effective = allBuildings.filter((b) => effSel(b)).map((b) => b.stable_id);
  const body = {
    schema: 'journal1_a2_e1_coverage_selection_confirm_v1',
    generated_utc: new Date().toISOString(),
    rule: manifest.selection?.rule ?? null,
    rule_counts: manifest.selection?.counts ?? null,
    overrides: selOverrides,
    effective_selected_count: effective.length,
    effective_selected_ids: effective,
    scientific_verdict: null,
  };
  const blob = new Blob([JSON.stringify(body, null, 1)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `journal1_selection_confirm_${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderList() {
  const host = $('list');
  const key = prefs.sortMode === 'index' ? null : prefs.sortMode;
  host.innerHTML = '';
  state.view.forEach((b, i) => {
    const el = document.createElement('div');
    el.className = 'bitem' + (i === state.index ? ' on' : '');
    const d = key ? b.deltas[key] : null;
    const dCls = d == null ? 'na' : d > 0 ? 'pos' : d < 0 ? 'neg' : 'na';
    const selMark = hasSelection && b.sel
      ? `<span class="selDot ${effSel(b) ? 'in' : 'out'}">${effSel(b) ? '✓' : '✕'}</span>` : '';
    el.innerHTML = `
      <span class="idx">${b.bkey}</span>
      <span class="sid">${shortId(b.stable_id)}</span>
      ${selMark}
      <span class="tier ${tierClass(b.tier)}">${tierClass(b.tier)}</span>
      ${key ? `<span class="d ${dCls}">${d == null ? '—' : (d > 0 ? '+' : '') + d.toFixed(2)}</span>` : ''}`;
    el.addEventListener('click', () => select(i));
    host.appendChild(el);
  });
  host.querySelector('.bitem.on')?.scrollIntoView({ block: 'nearest' });
}

// ---------- wiring ----------
$('viewMode').value = prefs.viewMode;
$('tglLod2').checked = prefs.showLod2;
$('tglNonBldg').checked = prefs.showNonBldg;
$('colorMode').value = prefs.colorMode;
$('ptSize').value = prefs.ptSize;
$('lodOpacity').value = prefs.lodOpacity;
$('sortMode').value = prefs.sortMode;
$('tierFilter').value = prefs.tierFilter;
if (hasSelection) {
  $('selFilter').value = prefs.selFilter;
  $('selFilter').addEventListener('change', (e) => { prefs.selFilter = e.target.value; savePrefs(); reflow(); });
  $('btnExportSel').addEventListener('click', exportSelection);
} else {
  $('selControls').style.display = 'none';
}

$('viewMode').addEventListener('change', (e) => {
  prefs.viewMode = e.target.value; savePrefs();
  applyMode();
  select(state.index, { keepCamera: inScene() ? false : false });
});
$('tglLod2').addEventListener('change', (e) => {
  prefs.showLod2 = e.target.checked; savePrefs();
  if (state.lod2Group) state.lod2Group.visible = !inScene() && prefs.showLod2;
  if (state.sceneLod2) state.sceneLod2.visible = inScene() && prefs.showLod2;
  invalidate();
});
$('tglNonBldg').addEventListener('change', (e) => {
  prefs.showNonBldg = e.target.checked; savePrefs(); rebuildAll();
});
$('colorMode').addEventListener('change', (e) => { prefs.colorMode = e.target.value; savePrefs(); rebuildAll(); });
$('ptSize').addEventListener('input', (e) => {
  prefs.ptSize = +e.target.value; savePrefs();
  for (const set of [state.clouds, state.sceneClouds]) {
    for (const c of Object.values(set)) if (c.points) c.points.material.size = prefs.ptSize;
  }
  invalidate();
});
$('lodOpacity').addEventListener('input', (e) => {
  prefs.lodOpacity = +e.target.value; savePrefs();
  for (const g of [state.lod2Group, state.sceneLod2]) {
    g?.traverse((o) => { if (o.isMesh) o.material.opacity = prefs.lodOpacity; });
  }
  invalidate();
});
const reflow = () => { const sid = current()?.stable_id; applyViewOrder(); const i = state.view.findIndex((b) => b.stable_id === sid); select(i >= 0 ? i : 0, { keepCamera: inScene() }); };
$('sortMode').addEventListener('change', (e) => { prefs.sortMode = e.target.value; savePrefs(); reflow(); });
$('tierFilter').addEventListener('change', (e) => { prefs.tierFilter = e.target.value; savePrefs(); reflow(); });

// 채움-의존 45동 / N12 층 가시화: cause_labeling_manifest가 있으면 층 선택 UI를
// 붙이고, 장면 LoD2 색칠(주황=45, 빨강=N12, 흐림=나머지) + 목록 필터를 건다.
let strata = null;
fetch('./cause_labeling_manifest_v1.json')
  .then((r) => (r.ok ? r.json() : null))
  .then((m) => {
    if (!m?.targets) return;
    strata = {
      fill: new Set(m.targets.map((t) => t.stable_id)),
      n12: new Set(m.targets.filter((t) => t.in_change_and_insufficient_N).map((t) => t.stable_id)),
    };
    $('tierFilter').insertAdjacentHTML('afterend',
      ' 층 <select id="stratumView"><option value="OFF">전체</option>'
      + '<option value="FILL45">채움-의존 45</option>'
      + '<option value="N12">변화∧불충분 12</option></select>');
    const sel = $('stratumView');
    sel.value = prefs.stratumView === 'FILL45' || prefs.stratumView === 'N12'
      ? prefs.stratumView : 'OFF';
    sel.addEventListener('change', (e) => {
      prefs.stratumView = e.target.value; savePrefs();
      rebuildSceneLod2(); reflow();
    });
    if (prefs.stratumView !== 'OFF') { rebuildSceneLod2(); reflow(); }
  })
  .catch(() => {});

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowLeft') select(state.index - 1);
  else if (e.key === 'ArrowRight') select(state.index + 1);
  else if (e.key >= '1' && e.key <= String(ARMS.length)) {
    const arm = ARMS[+e.key - 1];
    const box = $(`tglArm_${arm}`);
    if (box) { box.checked = !prefs.show[arm]; box.dispatchEvent(new Event('change')); }
  } else if (e.key === 'l' || e.key === 'L') { $('tglLod2').checked = !prefs.showLod2; $('tglLod2').dispatchEvent(new Event('change')); }
  else if (e.key === 'g' || e.key === 'G') { $('tglNonBldg').checked = !prefs.showNonBldg; $('tglNonBldg').dispatchEvent(new Event('change')); }
  else if (e.key === 's' || e.key === 'S') {
    $('viewMode').value = inScene() ? 'building' : 'scene';
    $('viewMode').dispatchEvent(new Event('change'));
  } else if (e.key === 'b' || e.key === 'B') {
    prefs.showBoundary = !prefs.showBoundary; savePrefs();
    if (state.boundary) { state.boundary.visible = inScene() && prefs.showBoundary; invalidate(); }
  } else if (e.key === 'x' || e.key === 'X') {
    toggleSelection(current());
  }
});

function selectFromHash() {
  const key = decodeURIComponent(location.hash.slice(1));
  if (!key) return false;
  let i = state.view.findIndex((b) => b.bkey === key || b.stable_id === key || b.stable_id.endsWith(key));
  if (i < 0) {
    // Building filtered out of the current view: reset filters so the link lands.
    prefs.tierFilter = 'ALL'; prefs.selFilter = 'ALL'; savePrefs();
    $('tierFilter').value = 'ALL';
    if (hasSelection) $('selFilter').value = 'ALL';
    applyViewOrder();
    i = state.view.findIndex((b) => b.bkey === key || b.stable_id === key || b.stable_id.endsWith(key));
  }
  if (i < 0) return false;
  select(i, { keepCamera: false });
  return true;
}
window.addEventListener('hashchange', selectFromHash);

applyViewOrder();
resize();
applyMode({ fit: false });
if (inScene()) fitScene();
if (!selectFromHash()) select(0, { keepCamera: inScene() });
