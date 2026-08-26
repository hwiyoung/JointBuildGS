// S3 검증 페이지 1 — 평면 가설(S1) 정적 뷰어. NOT OFFICIAL · scientific_verdict: null.
// 데이터 계약: phd_s3_verify_s1_bundle_v1 — ../runs/<name>/{manifest.json,
// s1_points.ply, s1_planes.json, s1_orphans.json, s1_view.json} 지연 fetch.
// three.js r160 vendored (CDN 금지). 궤도/팬/줌·PLY 파서는 ARRGS 뷰어 관행을 개조.
import * as THREE from './three.module.min.js';

const $ = (s) => document.querySelector(s);
const esc = (x) => String(x).replace(/&/g, '&amp;').replace(/</g, '&lt;');
window.onerror = (msg, src, line) => {
  const el = $('#panel') || document.body;
  el.insertAdjacentHTML('afterbegin', `<div class="err">JS 오류: ${esc(msg)} (${line})</div>`);
};

// 출처색 — 계약 enum: prior|mvs|footprint|gapfill|synthetic_gt|synthetic_distractor
const SRC_COLORS = { prior: 0x4a9eff, mvs: 0xffa040, footprint: 0x9aa4b0,
                     gapfill: 0xb07fe8, synthetic_gt: 0x50d890, synthetic_distractor: 0xff5f6e };
const SRC_LABEL = { prior: 'prior(ALS)', mvs: 'MVS', footprint: 'footprint',
                    gapfill: 'gapfill', synthetic_gt: '합성 GT형', synthetic_distractor: '합성 교란' };
// ALS 점은 데이터 rgb(회색 127)가 mvs(회색 180)와 육안 구분 불가 → 뷰어에서 앰버 틴트
// (prior 출처색 계열)로 대체. mvs 점만 데이터 rgb 유지.
const GT_COLOR = 0x30d060, ALS_COLOR = 0xd08a2e;
const DIM = 0.16;                 // 감광 배율
const GLOW = [1.0, 0.88, 0.40];   // inlier 발광색
const ORPHAN_RGB = [0.94, 0.30, 0.27];

const state = {
  runs: [], runName: null, run: null, cache: {},
  sel: null,           // 선택 평면 plane_id
  orphanMode: false, showMvs: true, showAls: false, showGt: false, showPlanes: true,
  outlineOnly: false,  // 미선택 평면 = 윤곽선만 (중첩 혼잡 완화)
  srcOn: {},           // 출처별 평면 표시 (footprint는 기본 OFF)
  picked: null,        // 점 클릭 카드
  reading: {},         // 런별 판독 기록 {verdict, memo, sign}
  lastFit: null,
};

// ---------- three.js scaffold (ARRGS 뷰어 개조) ----------
const view = $('#view3d');
let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  view.appendChild(renderer.domElement);
} catch (e) {  // WebGL 불가 환경 — 패널·체크리스트·판독 기록은 그대로 동작
  view.innerHTML += `<div class="err" style="margin:10px">WebGL 사용 불가: ${esc(e.message)}</div>`;
}
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x14161a);
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 5000);
scene.add(new THREE.AmbientLight(0xffffff, 0.75));
const dl = new THREE.DirectionalLight(0xffffff, 0.9); dl.position.set(1, 2, 3);
scene.add(dl);
const orbit = { target: new THREE.Vector3(), r: 50, th: 0.9, ph: 0.9 };
function applyOrbit() {
  camera.position.set(
    orbit.target.x + orbit.r * Math.sin(orbit.ph) * Math.cos(orbit.th),
    orbit.target.y + orbit.r * Math.sin(orbit.ph) * Math.sin(orbit.th),
    orbit.target.z + orbit.r * Math.cos(orbit.ph));
  camera.up.set(0, 0, 1);
  camera.lookAt(orbit.target);
}
let drag = null;
view.addEventListener('mousedown', (e) => {
  drag = { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, btn: e.button };
});
view.addEventListener('mouseup', (e) => {
  if (drag && drag.btn === 0 &&
      Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 5) pickAt(e);
  drag = null;
});
window.addEventListener('mouseup', () => { drag = null; });
window.addEventListener('mousemove', (e) => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  drag.x = e.clientX; drag.y = e.clientY;
  if (drag.btn === 0) {
    orbit.th -= dx * 0.005;
    orbit.ph = Math.min(Math.PI - 0.03, Math.max(0.03, orbit.ph - dy * 0.005));
  } else {
    const s = orbit.r * 0.0011;
    const fwd = new THREE.Vector3().subVectors(orbit.target, camera.position).normalize();
    const right = new THREE.Vector3().crossVectors(fwd, camera.up).normalize();
    const up = new THREE.Vector3().crossVectors(right, fwd).normalize();
    orbit.target.addScaledVector(right, -dx * s);
    orbit.target.addScaledVector(up, dy * s);
  }
  applyOrbit();
});
view.addEventListener('wheel', (e) => {
  orbit.r = Math.max(1, orbit.r * (1 + Math.sign(e.deltaY) * 0.07));
  applyOrbit(); e.preventDefault();
}, { passive: false });
view.addEventListener('contextmenu', (e) => e.preventDefault());
window.addEventListener('keydown', (e) => {  // ESC = 평면 선택/점 카드 해제
  if (e.key !== 'Escape' || !state.run) return;
  const t = e.target;
  if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.tagName === 'SELECT')) return;
  const hadPick = state.picked !== null;
  state.picked = null;
  if (state.sel !== null) selectPlane(state.sel);   // 토글 해제 (색·패널 갱신 포함)
  else if (hadPick) renderPanel();
});
function resize() {
  if (!renderer) return;
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
let hiliteMats = [];
if (renderer) (function loop() {
  requestAnimationFrame(loop);
  if (hiliteMats.length) {
    const o = 0.5 + 0.45 * Math.sin(performance.now() / 200);
    hiliteMats.forEach(m => m.opacity = o);
  }
  renderer.render(scene, camera);
})();

let ptsGroup = new THREE.Group(), planeGroup = new THREE.Group(),
    gtGroup = new THREE.Group(), ctxGroup = new THREE.Group();
scene.add(ptsGroup, planeGroup, gtGroup, ctxGroup);
function clear3d() {
  for (const g of [ptsGroup, planeGroup, gtGroup, ctxGroup]) scene.remove(g);
  ptsGroup = new THREE.Group(); planeGroup = new THREE.Group();
  gtGroup = new THREE.Group(); ctxGroup = new THREE.Group();
  scene.add(ptsGroup, planeGroup, gtGroup, ctxGroup);
  hiliteMats = [];
}

// ---------- binary PLY 파서 (ARRGS 개조 — 씨닝 없음: 행 순서 = 인덱스 공간) ----------
function parsePly(buf) {
  const headBytes = new Uint8Array(buf, 0, Math.min(4096, buf.byteLength));
  const head = new TextDecoder().decode(headBytes);
  const end = head.indexOf('end_header\n');
  if (end < 0) throw new Error('PLY 헤더 없음');
  const offset = end + 'end_header\n'.length;
  let count = 0; const props = [];
  head.slice(0, end).split('\n').forEach(ln => {
    const t = ln.trim().split(/\s+/);
    if (t[0] === 'element' && t[1] === 'vertex') count = +t[2];
    else if (t[0] === 'property') props.push([t[1], t[2]]);
  });
  const SZ = { float: 4, double: 8, uchar: 1, char: 1, ushort: 2, short: 2, uint: 4, int: 4 };
  const size = props.reduce((s, p) => s + (SZ[p[0]] || 4), 0);
  const dv = new DataView(buf, offset);
  const pos = new Float32Array(count * 3);
  const rgb = new Uint8Array(count * 3);
  const src = new Uint8Array(count);
  for (let i = 0; i < count; i++) {
    let po = i * size;
    for (const [typ, name] of props) {
      let v;
      if (typ === 'float') { v = dv.getFloat32(po, true); po += 4; }
      else if (typ === 'double') { v = dv.getFloat64(po, true); po += 8; }
      else if (typ === 'uchar' || typ === 'char') { v = dv.getUint8(po); po += 1; }
      else if (typ === 'ushort' || typ === 'short') { v = dv.getUint16(po, true); po += 2; }
      else { v = dv.getUint32(po, true); po += 4; }
      if (name === 'x') pos[i * 3] = v;
      else if (name === 'y') pos[i * 3 + 1] = v;
      else if (name === 'z') pos[i * 3 + 2] = v;
      else if (name === 'red') rgb[i * 3] = v;
      else if (name === 'green') rgb[i * 3 + 1] = v;
      else if (name === 'blue') rgb[i * 3 + 2] = v;
      else if (name === 'source') src[i] = v;
    }
  }
  return { count, pos, rgb, src };
}

// ---------- 런 로드 ----------
async function fetchRun(name) {
  const base = `../runs/${name}`;
  const [manifest, planes, orphans, viewJ, plyBuf] = await Promise.all([
    fetch(`${base}/manifest.json`).then(r => { if (!r.ok) throw new Error(`manifest ${r.status}`); return r.json(); }),
    fetch(`${base}/s1_planes.json`).then(r => { if (!r.ok) throw new Error(`s1_planes ${r.status}`); return r.json(); }),
    fetch(`${base}/s1_orphans.json`).then(r => { if (!r.ok) throw new Error(`s1_orphans ${r.status}`); return r.json(); }),
    fetch(`${base}/s1_view.json`).then(r => { if (!r.ok) throw new Error(`s1_view ${r.status}`); return r.json(); }),
    fetch(`${base}/s1_points.ply`).then(r => { if (!r.ok) throw new Error(`s1_points ${r.status}`); return r.arrayBuffer(); }),
  ]);
  const pts = parsePly(plyBuf);
  const N = pts.count;
  // mvs/als 분리 + full↔mvs 로컬 인덱스 매핑 (inlier/orphan 인덱스 = full 공간)
  let nMvs = 0;
  for (let i = 0; i < N; i++) if (pts.src[i] === 0) nMvs++;
  const mvsLocals = new Uint32Array(nMvs);          // local -> full
  const fullToMvs = new Int32Array(N).fill(-1);     // full -> local
  const alsLocals = new Uint32Array(N - nMvs);
  let mi = 0, ai = 0;
  for (let i = 0; i < N; i++) {
    if (pts.src[i] === 0) { fullToMvs[i] = mi; mvsLocals[mi++] = i; }
    else alsLocals[ai++] = i;
  }
  // 점→소속 평면 Uint32 역인덱스 (CSR, 로드 시 1회 — 계약 성능 조항)
  const pl = planes.planes || [];
  const csrOff = new Uint32Array(N + 1);
  for (const p of pl) for (const idx of (p.inlier_idx || [])) csrOff[idx + 1]++;
  for (let i = 0; i < N; i++) csrOff[i + 1] += csrOff[i];
  const csrItems = new Uint32Array(csrOff[N]);
  const cur = csrOff.slice(0, N);
  pl.forEach((p, pi) => { for (const idx of (p.inlier_idx || [])) csrItems[cur[idx]++] = pi; });
  const orphanFlag = new Uint8Array(N);
  for (const idx of (orphans.orphan_idx || [])) orphanFlag[idx] = 1;
  const selFlag = new Uint8Array(N);
  const byId = {}; pl.forEach((p, pi) => { byId[p.plane_id] = pi; });
  // bbox (카메라 맞춤)
  const bb = { mn: [1e18, 1e18, 1e18], mx: [-1e18, -1e18, -1e18] };
  for (let i = 0; i < N; i++) for (let k = 0; k < 3; k++) {
    const v = pts.pos[i * 3 + k];
    if (v < bb.mn[k]) bb.mn[k] = v;
    if (v > bb.mx[k]) bb.mx[k] = v;
  }
  return { name, manifest, planes, orphans, view: viewJ, N,
           pos: pts.pos, rgb: pts.rgb, src: pts.src,
           nMvs, mvsLocals, fullToMvs, alsLocals, csrOff, csrItems,
           orphanFlag, selFlag, byId, bb };
}

// ---------- 색 적용 — 기존 BufferAttribute 부분 갱신 (지오메트리 재생성 금지) ----------
function colorOf(d, local, out) {
  const full = d.mvsLocals[local];
  if (state.orphanMode && d.orphanFlag[full]) {
    out[0] = ORPHAN_RGB[0]; out[1] = ORPHAN_RGB[1]; out[2] = ORPHAN_RGB[2]; return;
  }
  if (state.sel !== null && d.selFlag[full]) {
    out[0] = GLOW[0]; out[1] = GLOW[1]; out[2] = GLOW[2]; return;
  }
  const f = (state.sel !== null || state.orphanMode) ? DIM : 1.0;
  out[0] = d.rgb[full * 3] / 255 * f;
  out[1] = d.rgb[full * 3 + 1] / 255 * f;
  out[2] = d.rgb[full * 3 + 2] / 255 * f;
}
const _c = [0, 0, 0];
function applyColors(subset) {
  const d = state.run;
  if (!d || !d.mvsPoints) return;
  const attr = d.mvsPoints.geometry.getAttribute('color');
  const a = attr.array;
  if (subset && subset.length) {
    let mn = Infinity, mx = -1;
    for (const li of subset) {
      colorOf(d, li, _c);
      a[li * 3] = _c[0]; a[li * 3 + 1] = _c[1]; a[li * 3 + 2] = _c[2];
      if (li < mn) mn = li;
      if (li > mx) mx = li;
    }
    if (attr.clearUpdateRanges) {  // three r160: 변경 구간만 GPU 업로드
      attr.clearUpdateRanges();
      attr.addUpdateRange(mn * 3, (mx - mn + 1) * 3);
    }
  } else {
    for (let li = 0; li < d.nMvs; li++) {
      colorOf(d, li, _c);
      a[li * 3] = _c[0]; a[li * 3 + 1] = _c[1]; a[li * 3 + 2] = _c[2];
    }
    if (attr.clearUpdateRanges) attr.clearUpdateRanges();
  }
  attr.needsUpdate = true;
}

// ---------- 씬 구축 ----------
function polyGeometry(poly) {  // support_local 3D 폴리곤 → 부채꼴 삼각화
  const g = new THREE.BufferGeometry();
  const verts = [];
  for (let k = 1; k + 1 < poly.length; k++) verts.push(...poly[0], ...poly[k], ...poly[k + 1]);
  g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  g.computeVertexNormals();
  return g;
}
function polyOutline(poly, closeLoop) {
  const g = new THREE.BufferGeometry();
  const pts = [];
  poly.forEach(p => pts.push(p[0], p[1], p.length > 2 ? p[2] : 0));
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  return g;
}
function buildScene(d) {
  clear3d();
  if (!d.mvsPoints) {
    // mvs 점군 (색 = PLY rgb, 선택/고아 시 부분 갱신)
    const mg = new THREE.BufferGeometry();
    const mpos = new Float32Array(d.nMvs * 3);
    const mcol = new Float32Array(d.nMvs * 3);
    for (let li = 0; li < d.nMvs; li++) {
      const full = d.mvsLocals[li];
      mpos[li * 3] = d.pos[full * 3]; mpos[li * 3 + 1] = d.pos[full * 3 + 1];
      mpos[li * 3 + 2] = d.pos[full * 3 + 2];
    }
    mg.setAttribute('position', new THREE.BufferAttribute(mpos, 3));
    mg.setAttribute('color', new THREE.BufferAttribute(mcol, 3));
    d.mvsPoints = new THREE.Points(mg, new THREE.PointsMaterial({
      size: 0.12, vertexColors: true, sizeAttenuation: true }));
    d.mvsPoints.userData.kind = 'mvs';
    // ALS 오버레이 (o_init 전용 입력 — inlier 판정 비대상, 오버레이 전용).
    // 색 = 뷰어 앰버 틴트(ALS_COLOR) 고정 — 데이터 rgb 회색 127은 mvs와 구분 불가.
    const ag = new THREE.BufferGeometry();
    const apos = new Float32Array(d.alsLocals.length * 3);
    d.alsLocals.forEach((full, li) => {
      apos[li * 3] = d.pos[full * 3]; apos[li * 3 + 1] = d.pos[full * 3 + 1];
      apos[li * 3 + 2] = d.pos[full * 3 + 2];
    });
    ag.setAttribute('position', new THREE.BufferAttribute(apos, 3));
    d.alsPoints = new THREE.Points(ag, new THREE.PointsMaterial({
      color: ALS_COLOR, size: 0.18, transparent: true, opacity: 0.85 }));
    d.alsPoints.userData.kind = 'als';
    // 후보 평면 폴리곤 + 윤곽 + 선택 강조용 EdgesGeometry (레이캐스트 대상 = mesh)
    d.planeMeshes = {};
    (d.planes.planes || []).forEach(p => {
      if (!p.support_local || p.support_local.length < 3) return;
      const col = SRC_COLORS[p.source] ?? 0x888888;
      const mesh = new THREE.Mesh(polyGeometry(p.support_local),
        new THREE.MeshLambertMaterial({ color: col, transparent: true, opacity: 0.28,
                                        side: THREE.DoubleSide, depthWrite: false }));
      mesh.userData.pid = p.plane_id;
      const line = new THREE.LineLoop(polyOutline(p.support_local),
        new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.8 }));
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry),
        new THREE.LineBasicMaterial({ color: 0xffe066, transparent: true, opacity: 1.0 }));
      edges.visible = false;
      d.planeMeshes[p.plane_id] = { mesh, line, edges, source: p.source, baseColor: col };
    });
    // GT 면 (평가 전용 — 별도 토글)
    d.gtMeshes = [];
    (d.planes.gt_planes || []).forEach(g => {
      if (!g.support_local || g.support_local.length < 3) return;
      const mesh = new THREE.Mesh(polyGeometry(g.support_local),
        new THREE.MeshLambertMaterial({ color: GT_COLOR, transparent: true, opacity: 0.18,
                                        side: THREE.DoubleSide, depthWrite: false }));
      const line = new THREE.LineLoop(polyOutline(g.support_local),
        new THREE.LineBasicMaterial({ color: GT_COLOR, transparent: true, opacity: 0.9 }));
      d.gtMeshes.push(mesh, line);
    });
    // 맥락: footprint 윤곽 (ground_z / top_z)
    d.ctx = [];
    const fp = (d.view || {}).footprint_local;
    if (fp && fp.length >= 3) {
      for (const z of [d.view.ground_z, d.view.top_z]) {
        if (z === undefined || z === null) continue;
        const g = new THREE.BufferGeometry();
        const pts = [];
        fp.forEach(p => pts.push(p[0], p[1], z));
        g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
        d.ctx.push(new THREE.LineLoop(g, new THREE.LineBasicMaterial({
          color: 0x556070, transparent: true, opacity: 0.55 })));
      }
    }
  }
  ptsGroup.add(d.mvsPoints, d.alsPoints);
  Object.values(d.planeMeshes).forEach(({ mesh, line, edges }) => planeGroup.add(mesh, line, edges));
  d.gtMeshes.forEach(o => gtGroup.add(o));
  d.ctx.forEach(o => ctxGroup.add(o));
  applyStyles();
  applyColors(null);
  if (state.lastFit !== d.name) {
    state.lastFit = d.name;
    orbit.target.set((d.bb.mn[0] + d.bb.mx[0]) / 2, (d.bb.mn[1] + d.bb.mx[1]) / 2,
                     (d.bb.mn[2] + d.bb.mx[2]) / 2);
    orbit.r = Math.hypot(d.bb.mx[0] - d.bb.mn[0], d.bb.mx[1] - d.bb.mn[1],
                         d.bb.mx[2] - d.bb.mn[2]) * 1.15 + 5;
    applyOrbit();
  }
}
const _WHITE = new THREE.Color(1, 1, 1);
function applyStyles() {
  const d = state.run;
  if (!d) return;
  hiliteMats = [];
  d.mvsPoints.visible = state.showMvs;
  d.alsPoints.visible = state.showAls;
  gtGroup.visible = state.showGt;
  const anySel = state.sel !== null;
  for (const [pid, pm] of Object.entries(d.planeMeshes)) {
    const on = state.showPlanes && (state.srcOn[pm.source] !== false);
    const isSel = anySel && pid === state.sel;
    // mesh는 윤곽선만 모드에서도 visible 유지 (opacity 0) — 레이캐스트 픽킹 대상
    pm.mesh.visible = on;
    pm.line.visible = on && !isSel;
    pm.edges.visible = on && isSel;
    if (!on) continue;
    if (isSel) {
      // 선택 = 밝은 불투명 채움 + EdgesGeometry 윤곽 강조(맥동)
      pm.mesh.material.color.setHex(pm.baseColor).lerp(_WHITE, 0.35);
      pm.mesh.material.opacity = 0.75;
      hiliteMats.push(pm.edges.material);
    } else {
      pm.mesh.material.color.setHex(pm.baseColor);
      pm.line.material.color.setHex(pm.baseColor);
      if (state.outlineOnly) {          // 미선택 평면 채움 없음 — 중첩 혼잡 완화
        pm.mesh.material.opacity = 0.0;
        pm.line.material.opacity = anySel ? 0.15 : 0.75;
      } else {                          // 미선택 = 반투명 고스트 (선택 시 더 감광)
        pm.mesh.material.opacity = anySel ? 0.06 : 0.28;
        pm.line.material.opacity = anySel ? 0.15 : 0.8;
      }
    }
  }
  renderSelBadge();
}
function renderSelBadge() {
  const el = $('#selbadge');
  if (!el) return;
  const d = state.run;
  const p = (d && state.sel !== null) ? planeAt(d, state.sel) : null;
  if (!p) { el.style.display = 'none'; return; }
  el.style.display = 'block';
  el.innerHTML = `<b style="color:#ffe066">${esc(p.plane_id)}</b> ·
    <span style="color:#${(SRC_COLORS[p.source] ?? 0x888888).toString(16).padStart(6, '0')}">${esc(SRC_LABEL[p.source] || p.source)}</span> ·
    inlier ${p.inlier_count ?? (p.inlier_idx || []).length}
    <span class="note">재클릭·빈 공간·ESC=해제</span>`;
}

// ---------- 선택/픽 ----------
function planeAt(d, pid) { const pi = d.byId[pid]; return pi === undefined ? null : d.planes.planes[pi]; }
function selectPlane(pid) {
  const d = state.run;
  if (!d) return;
  const prev = state.sel;
  const next = (prev === pid) ? null : pid;
  if (prev) { const p = planeAt(d, prev); if (p) for (const i of (p.inlier_idx || [])) d.selFlag[i] = 0; }
  if (next) { const p = planeAt(d, next); if (p) for (const i of (p.inlier_idx || [])) d.selFlag[i] = 1; }
  state.sel = next;
  if (prev && next && !state.orphanMode) {
    // 평면→평면 전환: 두 inlier 집합 합집합만 색 갱신 (부분 갱신 경로)
    const touch = [];
    for (const id of [prev, next]) {
      const p = planeAt(d, id);
      if (p) for (const i of (p.inlier_idx || [])) { const l = d.fullToMvs[i]; if (l >= 0) touch.push(l); }
    }
    applyColors(touch);
  } else applyColors(null);
  applyStyles();
  renderPanel();
  if (state.sel !== null) {  // 목록 동기화 — active 행을 시야로
    const key = (window.CSS && CSS.escape) ? CSS.escape(state.sel) : state.sel;
    const row = document.querySelector(`#panel tr[data-pid="${key}"]`);
    if (row) row.scrollIntoView({ block: 'nearest' });
  }
}
const raycaster = new THREE.Raycaster();
function pickAt(e) {
  const d = state.run;
  if (!d || !d.mvsPoints || !renderer) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1,
                                -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  // 1) 평면 메시 우선 — 표시 중인 평면만 (윤곽선만 모드에서도 mesh.visible 유지 → 픽킹 가능)
  if (d.planeMeshes) {
    const meshes = [];
    for (const pm of Object.values(d.planeMeshes)) if (pm.mesh.visible) meshes.push(pm.mesh);
    if (meshes.length) {
      const phits = raycaster.intersectObjects(meshes, false);
      if (phits.length) {
        state.picked = null;
        selectPlane(phits[0].object.userData.pid);  // 같은 평면 재클릭 = 토글 해제
        return;
      }
    }
  }
  // 2) 평면 히트 없음 → 기존 점 픽킹 (후보 평면 토글 OFF 시 순수 점 픽킹)
  raycaster.params.Points.threshold = Math.max(0.04, orbit.r * 0.004);
  const objs = [];   // 표시 중인 점 출처만 픽킹 대상
  if (d.mvsPoints.visible) objs.push(d.mvsPoints);
  if (d.alsPoints.visible) objs.push(d.alsPoints);
  const hits = objs.length ? raycaster.intersectObjects(objs, false) : [];
  if (!hits.length) {  // 빈 공간 클릭 = 선택·점 카드 해제
    state.picked = null;
    if (state.sel !== null) selectPlane(state.sel);
    else renderPanel();
    return;
  }
  const h = hits[0];
  const kind = h.object.userData.kind;
  const full = kind === 'mvs' ? d.mvsLocals[h.index] : d.alsLocals[h.index];
  const planes = [];
  for (let k = d.csrOff[full]; k < d.csrOff[full + 1]; k++) planes.push(d.csrItems[k]);
  state.picked = {
    full, kind,
    xyz: [d.pos[full * 3], d.pos[full * 3 + 1], d.pos[full * 3 + 2]],
    planes, orphan: !!d.orphanFlag[full],
  };
  renderPanel();
}

// ---------- 집계 ----------
function gtStats(d) {
  const gts = (d.planes.gt_planes || []);
  const matched = gts.filter(g => (g.matched_plane_ids || []).length > 0).length;
  return { total: gts.length, matched };
}
function prereg(d) { return (d.manifest || {}).prereg || {}; }
function orphanPass(d) {
  const mx = prereg(d).orphan_ratio_max;
  const r = (d.orphans || {}).orphan_ratio;
  if (mx === undefined || r === undefined) return null;
  return r <= mx;
}

// ---------- 체크리스트 (상단 — 합격 사전치는 화면을 보기 전에 명기된 값) ----------
function renderChecklist() {
  const d = state.run;
  if (!d) { $('#checkstrip').innerHTML = '<span class="note">런 없음</span>'; return; }
  const pr = prereg(d);
  const gm = pr.gt_match || {};
  const gs = gtStats(d);
  const op = orphanPass(d);
  const ratio = (d.orphans.orphan_ratio ?? NaN);
  const b1 = gs.total === 0
    ? '<span class="badge na">GT 면 없음</span>'
    : `<span class="badge ${gs.matched === gs.total ? 'good' : 'bad'}">대응 ${gs.matched}/${gs.total}</span>`;
  const b3 = op === null ? '<span class="badge na">사전치 없음</span>'
    : `<span class="badge ${op ? 'good' : 'bad'}">${(ratio * 100).toFixed(1)}% ${op ? '≤' : '>'} ${(pr.orphan_ratio_max * 100).toFixed(0)}%</span>`;
  $('#checkstrip').innerHTML = `
    <div class="chkrow">
      <span class="chkitem"><b>①</b> GT 지붕면마다 대응 후보 존재(재현율 우선) ${b1}</span>
      <span class="chkitem"><b>②</b> 대형 오적합(B036형 49° 회전) 육안 0 <span class="badge na">육안</span></span>
      <span class="chkitem"><b>③</b> 고아 점 비율 ≤ 사전치 ${b3}</span>
      <span class="chkitem"><b>④</b> 출처 표기 정확 <span class="badge na">육안</span></span>
    </div>
    <div class="chkrow meta">
      <span>합격 사전치 <span class="badge prop">${pr.proposal ? '제안' : '등록'}</span>:
        고아 비율 ≤ ${pr.orphan_ratio_max ?? '—'} ·
        GT 매칭 각 ≤ ${gm.max_angle_deg ?? '—'}° · 오프셋 ≤ ${gm.max_offset_m ?? '—'} m</span>
      <span>판독 순서 규율: ① 전수 집계 → ② 무작위 표본 → ③ 지목 사례 — 보고 컷은 무작위 표본에서만.</span>
    </div>`;
}

// ---------- 우측 패널 ----------
function reading() {
  return state.reading[state.runName] ||
    (state.reading[state.runName] = { verdict: null, memo: '', sign: '' });
}
function fmtGtMatch(p, pr) {
  const g = p.gt_match;
  if (!g) return '<td class="l">—</td>';
  const gm = (pr || {}).gt_match || {};
  const ok = (gm.max_angle_deg === undefined || g.angle_deg <= gm.max_angle_deg) &&
             (gm.max_offset_m === undefined || g.offset_m <= gm.max_offset_m);
  return `<td class="l ${ok ? 'good' : 'warn'}">${esc(g.gt_plane_id)} · ${(+g.angle_deg).toFixed(1)}° · ${(+g.offset_m).toFixed(2)}m</td>`;
}
function planeCardHtml(d, pid) {
  const p = planeAt(d, pid);
  if (!p) return '';
  const g = p.gt_match;
  return `<div class="card"><b style="color:#ffe066">${esc(pid)}</b>
    <span style="color:#${(SRC_COLORS[p.source] ?? 0x888888).toString(16).padStart(6, '0')}">${esc(SRC_LABEL[p.source] || p.source)}</span>
    <table style="margin-top:4px">
      <tr><td class="l">inlier 수</td><td>${p.inlier_count ?? (p.inlier_idx || []).length}</td></tr>
      <tr><td class="l">inlier RMS</td><td>${p.inlier_rms_m !== undefined ? (+p.inlier_rms_m).toFixed(3) + ' m' : '—'}</td></tr>
      <tr><td class="l">중력각</td><td>${p.gravity_angle_deg !== undefined ? (+p.gravity_angle_deg).toFixed(1) + '°' : '—'}</td></tr>
      <tr><td class="l">GT 매칭</td>${fmtGtMatch(p, prereg(d))}</tr>
      <tr><td class="l">n · d</td><td>[${(p.n || []).map(v => (+v).toFixed(3)).join(', ')}] · ${p.d !== undefined ? (+p.d).toFixed(3) : '—'}</td></tr>
    </table></div>`;
}
function pickedCardHtml(d) {
  const pk = state.picked;
  if (!pk) return '';
  let body;
  if (pk.kind === 'als') {
    body = '<span class="note">ALS prior 점(앰버 틴트 — 데이터 rgb 아님) — prior 진술·o_init 전용 입력, inlier 판정 비대상</span>';
  } else if (!pk.planes.length) {
    body = `<span class="bad">고아 점 — 어느 후보 평면의 inlier도 아님</span>`;
  } else {
    body = '소속 평면: ' + pk.planes.map(pi => {
      const p = d.planes.planes[pi];
      return `<a href="#" data-pid="${esc(p.plane_id)}" style="color:#8ecbff">${esc(p.plane_id)}</a>`;
    }).join(' · ');
  }
  return `<div class="card"><b>점 #${pk.full}</b>
    <span class="note">(${pk.kind === 'mvs' ? 'mvs_current' : 'als_prior'} ·
    ${pk.xyz.map(v => v.toFixed(2)).join(', ')})</span><br>${body}</div>`;
}
function renderPanel() {
  const d = state.run;
  if (!d) { $('#panel').innerHTML = '<p class="note">런을 선택하세요.</p>'; return; }
  const pr = prereg(d);
  const gs = gtStats(d);
  const op = orphanPass(d);
  const ratio = d.orphans.orphan_ratio;
  const rd = reading();
  const srcSet = [...new Set((d.planes.planes || []).map(p => p.source))];
  let h = `<div class="note caption">페이지 1 = 원시 후보 가설(중첩·과잉 = 재현율 우선, §1.1).
      프리즘 절단·정리된 면은 페이지 2(S2)에서 판독.</div>
    <h2>표시</h2>
    <div class="legend">
      <label><input type="checkbox" id="planesTgl" ${state.showPlanes ? 'checked' : ''}> 후보 평면</label>
      <label><input type="checkbox" id="outlineTgl" ${state.outlineOnly ? 'checked' : ''}>
        미선택 평면 윤곽선만</label>
      <label><input type="checkbox" id="gtTgl" ${state.showGt ? 'checked' : ''}>
        <span style="color:#30d060">GT 면</span> <span class="badge eval">평가 전용</span></label>
      <label><input type="checkbox" id="orphanTgl" ${state.orphanMode ? 'checked' : ''}>
        <span style="color:#ff7b72">고아 점 강조</span></label>
    </div>
    <div class="legend">점 출처:
      <label><input type="checkbox" id="mvsTgl" ${state.showMvs ? 'checked' : ''}>
        <span style="color:#b4b4b4">MVS 점</span></label>
      <label><input type="checkbox" id="alsTgl" ${state.showAls ? 'checked' : ''}>
        <span style="color:#d08a2e">ALS prior 점</span></label>
      <div class="note">MVS 점(회색)=현재 관측·판정 대상 / ALS 점(앰버)=prior 진술·o_init 전용·판정 비대상</div>
    </div>
    <div class="legend">평면 출처: ${srcSet.map(s =>
      `<label><input type="checkbox" class="srcTgl" data-src="${esc(s)}" ${state.srcOn[s] !== false ? 'checked' : ''}>
       <span style="color:#${(SRC_COLORS[s] ?? 0x888888).toString(16).padStart(6, '0')}">${esc(SRC_LABEL[s] || s)}</span></label>`).join('')}
      ${srcSet.includes('footprint')
        ? '<span class="note">footprint(벽 대형 사각형)는 기본 OFF — 체크리스트 ④ 출처 표기 판독 때 켠다.</span>' : ''}
    </div>`;
  // 고아 패널
  h += `<h2>고아 점 <span class="note">(mvs 점 중 어느 평면 inlier도 아님)</span></h2>
    <div class="card">비율 <b class="${op === null ? '' : op ? 'good' : 'bad'}">${ratio !== undefined ? (ratio * 100).toFixed(2) + '%' : '—'}</b>
    (${(d.orphans.orphan_idx || []).length} / ${(d.manifest.counts || {}).points_mvs ?? d.nMvs})
    — 사전치 ≤ ${pr.orphan_ratio_max !== undefined ? (pr.orphan_ratio_max * 100).toFixed(0) + '%' : '—'}
    ${op === null ? '' : op ? '<span class="badge good">합</span>' : '<span class="badge bad">불</span>'}
    <span class="badge prop">${pr.proposal ? '제안' : '등록'}</span>
    <div class="note" style="margin-top:3px">inlier 정의(등록): ${esc((d.manifest.inlier_def || {}).definition || '—')}
    — τ=${(d.manifest.inlier_def || {}).tau_m ?? '?'} m · support 버퍼=${(d.manifest.inlier_def || {}).support_buffer_m ?? '?'} m ·
    대상=${esc((d.manifest.inlier_def || {}).target || 'mvs_current')}</div></div>`;
  // 선택 카드
  if (state.sel) h += `<h2>선택 평면</h2>${planeCardHtml(d, state.sel)}`;
  if (state.picked) h += `<h2>점 카드</h2>${pickedCardHtml(d)}`;
  // GT 커버리지
  const gts = d.planes.gt_planes || [];
  h += `<h2>GT 커버리지 <span class="badge eval">평가 전용</span></h2>`;
  if (!gts.length) h += '<div class="note">이 런에는 GT 면이 없다.</div>';
  else {
    h += `<div class="note">대응 ${gs.matched}/${gs.total} — 체크리스트 ①</div>
      <table><tr><th class="l">GT 면</th><th class="l">대응 후보</th><th class="l">상태</th></tr>` +
      gts.map(g => {
        const m = g.matched_plane_ids || [];
        return `<tr><td class="l">${esc(g.gt_plane_id)}</td>
          <td class="l">${m.length ? m.map(id => `<a href="#" data-pid="${esc(id)}" style="color:#8ecbff">${esc(id)}</a>`).join(' ') : '—'}</td>
          <td class="l ${m.length ? 'good' : 'bad'}">${m.length ? '대응' : '누락'}</td></tr>`;
      }).join('') + '</table>';
  }
  // 평면 목록
  const planesList = d.planes.planes || [];
  h += `<h2>후보 평면 (${planesList.length})
      <button class="small" id="rndbtn" title="판독 순서 규율 ② 무작위 표본">무작위 표본</button></h2>
    <table><tr><th class="l">평면(클릭=발광)</th><th class="l">출처</th><th>inlier</th><th>RMS m</th><th>중력각°</th><th class="l">GT 매칭</th></tr>` +
    planesList.map(p => `<tr data-pid="${esc(p.plane_id)}" class="${state.sel === p.plane_id ? 'sel' : ''}">
      <td class="l">${esc(p.plane_id)}</td>
      <td class="l" style="color:#${(SRC_COLORS[p.source] ?? 0x888888).toString(16).padStart(6, '0')}">${esc(SRC_LABEL[p.source] || p.source)}</td>
      <td>${p.inlier_count ?? (p.inlier_idx || []).length}</td>
      <td>${p.inlier_rms_m !== undefined ? (+p.inlier_rms_m).toFixed(3) : '—'}</td>
      <td>${p.gravity_angle_deg !== undefined ? (+p.gravity_angle_deg).toFixed(1) : '—'}</td>
      ${fmtGtMatch(p, pr)}</tr>`).join('') + '</table>';
  // 판독 기록 — 파일 다운로드만, 서버 전송 없음
  h += `<h2>판독 기록 (리뷰어: 김휘영)</h2>
    <div class="card">
      <div class="legend">
        <label><input type="radio" name="verdict" value="합격" ${rd.verdict === '합격' ? 'checked' : ''}> 합격</label>
        <label><input type="radio" name="verdict" value="불합격" ${rd.verdict === '불합격' ? 'checked' : ''}> 불합격</label>
        <label><input type="radio" name="verdict" value="보류" ${rd.verdict === '보류' ? 'checked' : ''}> 보류</label>
      </div>
      <textarea id="memo" rows="4" placeholder="판독 메모 — 전수 집계/무작위 표본/지목 사례 순서로">${esc(rd.memo)}</textarea>
      <div style="margin-top:5px">서명란 <input type="text" id="sign" placeholder="리뷰어 김휘영 서명" value="${esc(rd.sign)}" style="width:180px">
        <button class="small" id="dlbtn">판독 기록 JSON 다운로드</button></div>
      <div class="note" style="margin-top:4px">파일로만 저장 — 서버 전송 없음. scientific_verdict: null 유지(사람 판정은 별도 승인 문서).</div>
    </div>`;
  $('#panel').innerHTML = h;
  bindPanel();
}
function bindPanel() {
  const on = (id, ev, fn) => { const el = $(id); if (el) el[ev] = fn; };
  on('#planesTgl', 'onchange', () => { state.showPlanes = $('#planesTgl').checked; applyStyles(); });
  on('#outlineTgl', 'onchange', () => { state.outlineOnly = $('#outlineTgl').checked; applyStyles(); });
  on('#mvsTgl', 'onchange', () => { state.showMvs = $('#mvsTgl').checked; applyStyles(); });
  on('#alsTgl', 'onchange', () => { state.showAls = $('#alsTgl').checked; applyStyles(); });
  on('#gtTgl', 'onchange', () => { state.showGt = $('#gtTgl').checked; applyStyles(); });
  on('#orphanTgl', 'onchange', () => {
    state.orphanMode = $('#orphanTgl').checked; applyColors(null); renderPanel();
  });
  document.querySelectorAll('.srcTgl').forEach(cb => {
    cb.onchange = () => { state.srcOn[cb.dataset.src] = cb.checked; applyStyles(); };
  });
  document.querySelectorAll('[data-pid]').forEach(el => {
    el.onclick = (e) => { e.preventDefault(); selectPlane(el.dataset.pid); };
  });
  on('#rndbtn', 'onclick', () => {
    const d = state.run;
    const vis = (d.planes.planes || []).filter(p => state.srcOn[p.source] !== false);
    if (vis.length) selectPlane(vis[Math.floor(Math.random() * vis.length)].plane_id);
  });
  document.querySelectorAll('input[name="verdict"]').forEach(r => {
    r.onchange = () => { reading().verdict = r.value; };
  });
  on('#memo', 'oninput', () => { reading().memo = $('#memo').value; });
  on('#sign', 'oninput', () => { reading().sign = $('#sign').value; });
  on('#dlbtn', 'onclick', downloadReading);
}
function downloadReading() {
  const d = state.run;
  const rd = reading();
  const pr = prereg(d);
  const gs = gtStats(d);
  const now = new Date().toISOString();
  const obj = {
    schema: 'phd_s3_verify_p1_reading_v1',
    page: 'p1_plane_hypothesis',
    run: state.runName,
    bundle: {
      schema: d.manifest.schema, bundle_name: d.manifest.bundle_name,
      s1_mode: d.manifest.s1_mode, dataset: d.manifest.dataset,
      counts: d.manifest.counts, inlier_def: d.manifest.inlier_def,
      prereg: d.manifest.prereg ?? null,
    },
    checklist: [
      '① GT 지붕면마다 대응 후보 존재(재현율 우선)',
      '② 대형 오적합(B036형 49° 회전) 육안 0',
      '③ 고아 점 비율 ≤ 사전 등록치',
      '④ 출처 표기 정확',
    ],
    auto: {
      orphan_ratio: d.orphans.orphan_ratio ?? null,
      orphan_ratio_max: pr.orphan_ratio_max ?? null,
      orphan_pass: orphanPass(d),
      gt_matched: gs.matched, gt_total: gs.total,
      prereg_proposal: !!pr.proposal,
    },
    reading_order_rule: '전수 집계 → 무작위 표본 → 지목 사례 (보고 컷은 무작위 표본에서만)',
    verdict: rd.verdict, memo: rd.memo,
    reviewer: '김휘영', signature: rd.sign,
    saved_at: now, transport: 'file-download-only',
    not_official: true, scientific_verdict: null,
  };
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)],
                                        { type: 'application/json' }));
  a.download = `p1_reading_${state.runName}_${now.replace(/[:.]/g, '-')}.json`;
  a.click();
}

// ---------- 헤더 ----------
function renderHeader() {
  const d = state.run;
  if (!d) { $('#countsline').textContent = '런 없음 — writer(s1 번들)를 먼저 실행'; return; }
  const c = d.manifest.counts || {};
  const t = d.manifest.thinning || {};
  const off = d.manifest.local_offset || [];
  $('#countsline').textContent =
    `${d.manifest.bundle_name || state.runName} · ${d.manifest.s1_mode || ''}` +
    ` · 점 ${c.points_total ?? d.N}(mvs ${c.points_mvs ?? d.nMvs} / als ${c.points_als ?? (d.N - d.nMvs)})` +
    ` · 평면 ${c.planes ?? (d.planes.planes || []).length} · 고아 ${c.orphans ?? (d.orphans.orphan_idx || []).length}` +
    (t.original_count ? ` · 씨닝 ${t.original_count}→${c.points_total ?? d.N}` : '') +
    ` · CRS ${d.manifest.crs || '?'} (offset −[${off.map(v => (+v).toFixed(1)).join(', ')}])`;
  $('#hud').textContent = `${state.runName} — 좌드래그 회전 · 우드래그 이동 · 휠 줌 · ` +
    `클릭=평면 선택(평면 밖은 점→소속 평면) · 재클릭·빈 공간·ESC=해제 · 순수 점 픽킹은 후보 평면 OFF · ` +
    `점 출처: MVS 회색(판정 대상) / ALS 앰버(prior — 기본 OFF)`;
}

// ---------- 런 전환 ----------
async function loadRun(name) {
  state.runName = name; state.sel = null; state.orphanMode = false; state.picked = null;
  $('#panel').innerHTML = `<p class="note">${esc(name)} 로딩 중…</p>`;
  try {
    if (!state.cache[name]) state.cache[name] = await fetchRun(name);
  } catch (e) {
    $('#panel').innerHTML =
      `<div class="err">런 ${esc(name)} 로드 실패: ${esc(e.message)}<br>
       writer가 s1 번들을 아직 생성하지 않았을 수 있다.</div>`;
    $('#checkstrip').innerHTML = '<span class="note">—</span>';
    return;
  }
  const d = state.cache[name];
  d.selFlag.fill(0);
  state.run = d;
  const srcSet = new Set((d.planes.planes || []).map(p => p.source));
  // footprint(벽 대형 사각형)는 시야 지배 → 기본 OFF. ④ 출처 표기 판독 때 수동 ON.
  for (const s of srcSet) if (state.srcOn[s] === undefined) state.srcOn[s] = (s !== 'footprint');
  buildScene(d);
  renderHeader();
  renderChecklist();
  renderPanel();
  resize();
}

// ---------- 부트 ----------
fetch('./manifest.json').then(r => {
  if (!r.ok) throw new Error(`viewer manifest ${r.status}`);
  return r.json();
}).then(man => {
  state.runs = man.runs || [];
  const sel = $('#runsel');
  state.runs.forEach(r => {
    const o = document.createElement('option');
    o.value = r.name;
    const ds = r.dataset || {};
    o.textContent = r.name + (ds.kind === 'synthetic' ? ` (합성 ${ds.synth_kind || ''})`
                              : ds.stable_id ? ` (${ds.stable_id})` : '');
    sel.appendChild(o);
  });
  sel.onchange = () => loadRun(sel.value);
  if (state.runs.length) loadRun(state.runs[0].name);
  else {
    $('#countsline').textContent = '런 0개 — writer(s1 번들) 실행 후 build_verify_pages.py 재실행';
    $('#panel').innerHTML = '<p class="note">runs/ 아래에 s1 번들이 없다.</p>';
    $('#checkstrip').innerHTML = '<span class="note">—</span>';
  }
  resize();
}).catch(e => {
  $('#panel').innerHTML = `<div class="err">viewer manifest 로드 실패: ${esc(e.message)} —
    build_verify_pages.py로 뷰어를 번들 루트에 배포한 뒤 8885로 서빙해야 한다.</div>`;
});
resize();
applyOrbit();
