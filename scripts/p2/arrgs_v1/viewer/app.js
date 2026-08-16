import * as THREE from './three.module.min.js';
window.onerror = (msg, src, line) => {
  const el = document.getElementById('runs');
  if (el) el.insertAdjacentHTML('afterbegin',
    `<div style="color:#ff7b72;font-size:11px;border:1px solid #663;padding:4px">JS 오류: ${msg} (${line})</div>`);
};

const $ = (s) => document.querySelector(s);
const state = { manifest: null, run: null, tab: 's5', snap: 0, playing: null, evMode: 'class' };
const TAB_GUIDE = {
  s1: 'S1 평면 가설: 출력 = 후보 평면 목록(반투명 면, 출처별 색). 청록 점(ALS 입력)이 면에 붙어 있어야 정상 — 면 밖 점 덩어리 = 후보 누락.',
  s2: 'S2 = 초기값 검수. 변수별 표현 — 점유: 주황 복셀(o_init; 라디오로 최종/Δ 전환), 가우시안: 시드 점(소스색), 평면: 파란 facet 윤곽(평면 자체는 S1 탭). 와이어 모드에서 셀 구조 확인.',
  s34: 'S3 = 최적화 재생(하단 슬라이더). 변수별 표현 — 점유: 면 진하기(게이트 v; 부피로 보려면 S2 탭 최종/Δ), 가우시안: 렌더↔사진 패널, 평면: 우측 표 dn°/dd(이동량이 미세해 수치로).',
  s5: 'S4 모델: 출력 = 구조화 모델(적갈=지붕, 회=벽, 녹=지면). 파란 점 = E1 GT — 색면이 파란 점을 따라가면 성공. Δ 모드 = 판정이 초기값에 가한 수정.',
};

const SRC_COLORS = { prior_als: 0x4a9eff, mvs: 0xffa040, footprint: 0x9aa4b0,
                     gt: 0x50d890, distractor: 0xff5f6e, domain: 0x556070 };
const CLS_COLORS = { roof: 0xd06048, wall: 0xb8b0a0, ground: 0x5a8f5a };

// ---------- three.js scaffold ----------
const view = $('#view3d');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
view.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x14161a);
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 5000);
scene.add(new THREE.AmbientLight(0xffffff, 0.75));
const dl = new THREE.DirectionalLight(0xffffff, 0.9); dl.position.set(1, 2, 3);
scene.add(dl);
let orbit = { target: new THREE.Vector3(), r: 50, th: 0.9, ph: 0.9 };
function applyOrbit() {
  camera.position.set(
    orbit.target.x + orbit.r * Math.sin(orbit.ph) * Math.cos(orbit.th),
    orbit.target.y + orbit.r * Math.sin(orbit.ph) * Math.sin(orbit.th),
    orbit.target.z + orbit.r * Math.cos(orbit.ph));
  camera.up.set(0, 0, 1);
  camera.lookAt(orbit.target);
}
let drag = null;
view.addEventListener('mousedown', (e) => { drag = { x: e.clientX, y: e.clientY, btn: e.button }; });
window.addEventListener('mouseup', () => drag = null);
window.addEventListener('mousemove', (e) => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  drag.x = e.clientX; drag.y = e.clientY;
  if (drag.btn === 0) {
    orbit.th -= dx * 0.005;
    orbit.ph = Math.min(Math.PI - 0.03, Math.max(0.03, orbit.ph - dy * 0.005));
  } else {
    // pan in the camera plane (screen-right / screen-up), not world axes
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
  orbit.r = Math.max(2, orbit.r * (1 + Math.sign(e.deltaY) * 0.07));
  applyOrbit(); e.preventDefault();
}, { passive: false });
view.addEventListener('contextmenu', (e) => e.preventDefault());
function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
let hiliteMats = [];
(function loop() {
  requestAnimationFrame(loop);
  if (hiliteMats.length) {
    const t = performance.now() / 1000;
    const o = 0.5 + 0.45 * Math.sin(t * 5);
    hiliteMats.forEach(m => m.opacity = o);
  }
  renderer.render(scene, camera);
})();

let group = new THREE.Group(); scene.add(group);
let ringGroup = new THREE.Group(); scene.add(ringGroup);
let overlayGroup = new THREE.Group(); scene.add(overlayGroup);
let faceMeshes = [];   // aligned to s2.faces indices
function clear3d() {
  scene.remove(group); group = new THREE.Group(); scene.add(group); faceMeshes = [];
  scene.remove(ringGroup); ringGroup = new THREE.Group(); scene.add(ringGroup);
  hiliteMats = [];
}
// ---- model visibility / opacity (GT 비교용) ----
state.showModel = state.showModel !== false;
state.modelAlpha = state.modelAlpha ?? 1.0;
function applyModelAlpha() {
  group.visible = state.showModel;
  group.traverse(o => {
    if (o.material && o.material.userData && o.material.userData.baseOp !== undefined) {
      o.material.transparent = true;
      o.material.opacity = o.material.userData.baseOp * state.modelAlpha;
    }
  });
}
function modelControlsHtml() {
  return `<div class="legend" id="mdlctl"><label><input type="checkbox" id="mdltgl" ${state.showModel ? 'checked' : ''}> 모델 표시</label>
    &nbsp;투명도 <input type="range" id="mdlalpha" min="5" max="100" value="${Math.round(state.modelAlpha * 100)}" style="width:90px;vertical-align:middle"></div>`;
}
function bindModelControls() {
  const t = document.getElementById('mdltgl');
  if (t) t.onchange = () => { state.showModel = t.checked; applyModelAlpha(); };
  const a = document.getElementById('mdlalpha');
  if (a) a.oninput = () => { state.modelAlpha = a.value / 100; applyModelAlpha(); };
}
function markHilite(mesh, f, i) {
  const hl = state.hl || {};
  const fi = (f.fi !== undefined) ? f.fi : i;
  const hit = (hl.plane && f.plane_id === hl.plane) || (hl.face !== undefined && hl.face === fi);
  if (hit) {
    mesh.material.color.setHex(0xffe066);
    mesh.material.depthWrite = false;
    hiliteMats.push(mesh.material);
  } else if (hl.plane || hl.face !== undefined) {
    mesh.material.opacity = Math.min(mesh.material.opacity, 0.07); // dim the rest
  }
}

// ---------- GT / comparison point-cloud overlays ----------
const OVERLAY_COLORS = { E7: 0x40cfe0, E1: 0x3070c0, E2: 0xffa040 };
const OVERLAY_LABEL = { E7: 'E7 ALS(=S1 입력)', E1: 'E1 GT', E2: 'E2 MVS' };
state.overlayOn = { E7: false, E1: false, E2: false };
const cloudCache = {};
function parsePly(buf) {
  const head = new TextDecoder().decode(new Uint8Array(buf, 0, Math.min(2048, buf.byteLength)));
  const end = head.indexOf('end_header\n');
  if (end < 0) return null;
  const offset = end + 'end_header\n'.length;
  let count = 0; const props = [];
  head.slice(0, end).split('\n').forEach(ln => {
    const t = ln.trim().split(/\s+/);
    if (t[0] === 'element' && t[1] === 'vertex') count = +t[2];
    else if (t[0] === 'property') props.push([t[1], t[2]]);
  });
  const size = props.reduce((s, p) => s + (p[0] === 'float' ? 4 : p[0] === 'double' ? 8 : p[0] === 'uchar' ? 1 : 4), 0);
  const dv = new DataView(buf, offset);
  const stride = Math.max(1, Math.floor(count / 300000));
  const out = new Float32Array(Math.ceil(count / stride) * 3);
  let oi = 0;
  for (let i = 0; i < count; i += stride) {
    let po = i * size; let x = 0, y = 0, z = 0;
    for (const [typ, name] of props) {
      let v;
      if (typ === 'float') { v = dv.getFloat32(po, true); po += 4; }
      else if (typ === 'double') { v = dv.getFloat64(po, true); po += 8; }
      else if (typ === 'uchar') { v = dv.getUint8(po); po += 1; }
      else { v = dv.getInt32(po, true); po += 4; }
      if (name === 'x') x = v; else if (name === 'y') y = v; else if (name === 'z') z = v;
    }
    out[oi++] = x; out[oi++] = y; out[oi++] = z;
  }
  return out.subarray(0, oi);
}
async function refreshOverlays() {
  scene.remove(overlayGroup); overlayGroup = new THREE.Group(); scene.add(overlayGroup);
  const run = state.run;
  if (!run || !run.overlays) return;
  for (const arm of Object.keys(state.overlayOn)) {
    if (!state.overlayOn[arm] || !run.overlays[arm]) continue;
    const key = run.dir + '|' + arm;
    if (!cloudCache[key]) {
      const buf = await fetch('../' + run.overlays[arm]).then(r => r.arrayBuffer());
      cloudCache[key] = parsePly(buf);
    }
    const pos = cloudCache[key];
    if (!pos) continue;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    overlayGroup.add(new THREE.Points(g, new THREE.PointsMaterial({
      color: OVERLAY_COLORS[arm], size: 0.28, transparent: true, opacity: 0.55 })));
  }
}
function drawLod2Rings(run) {
  if (!run || !run.lod2_rings || state.showLod2 === false) return;
  if (!(state.tab === 's1' || state.tab === 's5')) return;
  run.lod2_rings.forEach(ring => {
    const pts = [];
    ring.forEach(p => pts.push(...p));
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    ringGroup.add(new THREE.LineLoop(geo, new THREE.LineBasicMaterial({
      color: 0x30d060, linewidth: 2 })));
  });
}
function lod2ToggleHtml(run) {
  if (!run || !run.lod2_rings) return '';
  return `<div class="legend"><label><input type="checkbox" id="lod2tgl2" ${state.showLod2 !== false ? 'checked' : ''}> <span style="color:#30d060">LoD2 GT 지붕 링(초록 선)</span></label></div>`;
}
function bindLod2Toggle() {
  const lt = document.getElementById('lod2tgl2');
  if (lt) lt.onchange = () => { state.showLod2 = lt.checked; renderTab(); };
}
function overlayControlsHtml(run) {
  if (!run || !run.overlays) return '';
  return '<div class="legend" id="ovctl">오버레이: ' + Object.keys(OVERLAY_COLORS)
    .filter(a => run.overlays[a])
    .map(a => `<label style="margin-right:8px"><input type="checkbox" data-ov="${a}" ${state.overlayOn[a] ? 'checked' : ''}> <span style="color:#${OVERLAY_COLORS[a].toString(16)}">${OVERLAY_LABEL[a]}</span></label>`)
    .join('') + '</div>';
}
function bindOverlayControls() {
  document.querySelectorAll('#ovctl input').forEach(cb => {
    cb.onchange = () => { state.overlayOn[cb.dataset.ov] = cb.checked; refreshOverlays(); };
  });
}
function faceGeometry(poly) {
  const g = new THREE.BufferGeometry();
  const verts = [];
  for (let k = 1; k + 1 < poly.length; k++) {
    verts.push(...poly[0], ...poly[k], ...poly[k + 1]);
  }
  g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  g.computeVertexNormals();
  return g;
}
function addFaces(faces, colorFn, opacityFn) {
  const hl = state.hl || {};
  faces.forEach((f, i) => {
    const op = opacityFn(f, i);
    const fi0 = (f.fi !== undefined) ? f.fi : i;
    const hlHit = (hl.plane && f.plane_id === hl.plane) ||
                  (hl.face !== undefined && hl.face === fi0);
    if (op <= 0.05 && !hlHit) return;  // dead faces: no mesh, no draw call
    const mat = new THREE.MeshLambertMaterial({
      color: colorFn(f, i), transparent: true, opacity: op,
      side: THREE.DoubleSide, depthWrite: false });
    const m = new THREE.Mesh(faceGeometry(f.poly3d), mat);
    m.userData.faceIdx = i;
    markHilite(m, f, i);
    mat.userData.baseOp = mat.opacity;
    group.add(m); faceMeshes[i] = m;
  });
}
function addCellWires(cells, colorFn) {
  const buckets = {};
  cells.forEach((c) => {
    if (!c.edges || !c.edges.length) return;
    const col = colorFn(c);
    const arr = buckets[col] = buckets[col] || [];
    c.edges.forEach(([a, b]) => arr.push(...a, ...b));
  });
  for (const [col, pts] of Object.entries(buckets)) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    const wm = new THREE.LineBasicMaterial({ color: +col, transparent: true, opacity: 0.45 });
    wm.userData.baseOp = 0.45;
    group.add(new THREE.LineSegments(g, wm));
  }
}
function drawSeedsS2(run) {
  if (state.showSeeds === undefined) state.showSeeds = true;
  if (!state.showSeeds) return;
  if (run._seeds === undefined) {
    run._seeds = null; // in flight
    fetch('../' + run.dir + '/s2_seeds.json').then(r => r.ok ? r.json() : null)
      .then(s => { run._seeds = s; if (state.tab === 's2') renderTab(); })
      .catch(() => { run._seeds = null; });
  } else if (run._seeds) {
    const bySrc = {};
    run._seeds.xyz.forEach((p, i) => {
      const k = run._seeds.src[i];
      (bySrc[k] = bySrc[k] || []).push(p[0], p[1], p[2]);
    });
    for (const [k, arr] of Object.entries(bySrc)) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
      group.add(new THREE.Points(geo, new THREE.PointsMaterial({
        color: SRC_COLORS[k] || 0x999999, size: 0.5 })));
    }
  }
}
function drawFinalGaussians(run) {
  if (!state.showFinalG) return;
  if (run._fg === undefined) {
    run._fg = null; // in flight
    fetch('../' + run.dir + '/s4_gaussians.json').then(r => r.ok ? r.json() : null)
      .then(d => { run._fg = d; if (state.tab === 's2') renderTab(); })
      .catch(() => { run._fg = null; });
  } else if (run._fg && run._fg.n && run._fg.s) {
    drawGaussianDiscs(run._fg, 0.85);  // full form: oriented, scaled, coloured
  } else if (run._fg) {  // legacy export: points only
    const arr = [];
    run._fg.xyz.forEach(p => arr.push(p[0], p[1], p[2]));
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
    group.add(new THREE.Points(geo, new THREE.PointsMaterial({
      color: 0x39b3a6, size: 0.55 })));
  }
}
function drawCellBoxes(cells, color, opacity) {
  if (!cells.length) return;
  const geo = new THREE.BoxGeometry(1, 1, 1);
  const mat = new THREE.MeshLambertMaterial({
    color, transparent: true, opacity });
  mat.userData.baseOp = opacity;
  const inst = new THREE.InstancedMesh(geo, mat, cells.length);
  const m4 = new THREE.Matrix4();
  cells.forEach((c, i) => {
    const mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
    c.edges.forEach(([a, b]) => [a, b].forEach(p =>
      p.forEach((v, k) => { mn[k] = Math.min(mn[k], v); mx[k] = Math.max(mx[k], v); })));
    m4.makeScale(Math.max(0.25, (mx[0] - mn[0]) * 0.94),
                 Math.max(0.25, (mx[1] - mn[1]) * 0.94),
                 Math.max(0.25, (mx[2] - mn[2]) * 0.94));
    m4.setPosition((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2);
    inst.setMatrixAt(i, m4);
  });
  group.add(inst);
}
function drawGaussianDiscs(g, opacity) {
  const N = g.xyz.length;
  if (!N) return;
  const geo = new THREE.CircleGeometry(1, 10);
  const mat = new THREE.MeshBasicMaterial({
    side: THREE.DoubleSide, transparent: true, opacity });
  mat.userData.baseOp = opacity;
  const inst = new THREE.InstancedMesh(geo, mat, N);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
  const z = new THREE.Vector3(0, 0, 1), nv = new THREE.Vector3();
  const pos = new THREE.Vector3(), sc = new THREE.Vector3();
  for (let i = 0; i < N; i++) {
    nv.set(...g.n[i]).normalize();
    q.setFromUnitVectors(z, nv);
    pos.set(...g.xyz[i]);
    const fade = g.a[i] < 0.3 ? 0.3 : 1.0;  // dying discs shrink visually
    sc.set(Math.max(0.06, g.s[i][0] * fade), Math.max(0.06, g.s[i][1] * fade), 1);
    m4.compose(pos, q, sc);
    inst.setMatrixAt(i, m4);
    inst.setColorAt(i, new THREE.Color(...g.rgb[i]));
  }
  if (inst.instanceColor) inst.instanceColor.needsUpdate = true;
  group.add(inst);
}
function drawFacetOutlines(faces, opacity) {
  const pts = [];
  faces.forEach(f => {
    const P = f.poly3d;
    for (let k = 0; k < P.length; k++) pts.push(...P[k], ...P[(k + 1) % P.length]);
  });
  if (!pts.length) return;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  const lm = new THREE.LineBasicMaterial({ color: 0x5a7290, transparent: true, opacity });
  lm.userData.baseOp = opacity;
  group.add(new THREE.LineSegments(g, lm));
}
function fitView(faces) {
  // preserve the camera across toggles/tab switches within the same run
  if (state.lastFit === (state.run && state.run.dir)) return;
  state.lastFit = state.run && state.run.dir;
  const bb = new THREE.Box3();
  faces.forEach(f => f.poly3d.forEach(p => bb.expandByPoint(new THREE.Vector3(...p))));
  if (bb.isEmpty()) return;
  bb.getCenter(orbit.target);
  orbit.r = bb.getSize(new THREE.Vector3()).length() * 1.1 + 5;
  applyOrbit();
}

// ---------- tabs & rendering per tab ----------
function oOf(run, snap, cellIdx) {
  const cells = run.s2.cells;
  const c = cells[cellIdx];
  if (!c || c.fixed === 0) return 0;
  const fi = snap.free_cells.indexOf(cellIdx);
  return fi >= 0 ? snap.o[fi] : 0;
}
function renderTab() {
  const run = state.run;
  $('#quantwrap').style.display = state.tab === 'quant' ? 'block' : 'none';
  $('#view3d').style.display = state.tab === 'quant' ? 'none' : 'block';
  $('#panel').style.display = state.tab === 'quant' ? 'none' : 'block';
  $('#timeline').style.display = state.tab === 's34' ? 'flex' : 'none';
  document.querySelectorAll('#tabs button').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === state.tab));
  if (state.tab === 'quant') { renderQuant(); return; }
  if (!run) { $('#panel').innerHTML = '<p>런을 선택하세요.</p>'; return; }
  // arrangement geometry is lazy-loaded per run (manifest stays small)
  let s2 = run.s2 || run._s2;
  if (!s2 && run.s2_ref) {
    if (!run._s2load) {
      run._s2load = true;
      $('#panel').innerHTML = '<p>배열 로딩 중…</p>';
      fetch('../' + run.s2_ref).then(r => r.json())
        .then(d => { run._s2 = d; renderTab(); })
        .catch(() => { $('#panel').innerHTML = '<p>배열 로드 실패</p>'; });
    }
    return;
  }
  if (!s2) {
    // oracle-style runs: B-rep + overlays only
    if (run.s5_obj) {
      clear3d();
      loadObj('../' + run.s5_obj);
      drawLod2Rings(run);
      $('#panel').innerHTML = '<p>모델 로딩 중…</p>';
      refreshOverlays();
      return;
    }
    $('#panel').innerHTML = '<p>이 런에는 3D 데이터가 없습니다.</p>';
    return;
  }
  clear3d();
  const faces = s2.faces;
  const interior = faces.filter(f => f.cell_b >= 0 && !f.plane_id.startsWith('domain:'));
  if (state.tab === 's1') {
    if (!state.s1src) state.s1src = { prior_als: true, mvs: true, footprint: false };
    const srcOf = {};
    (run.s1.planes || []).forEach(p => srcOf[p.id] = p.source);
    addFaces(faces.filter(f => !f.plane_id.startsWith('domain:')
                               && state.s1src[srcOf[f.plane_id]]),
      (f) => SRC_COLORS[srcOf[f.plane_id]] || 0x888888,
      () => 0.38);
    panelS1(run);
  } else if (state.tab === 's2') {
    if (state.s2Mode === undefined) state.s2Mode = 'voxel';
    if (state.s2Mode === 'voxel') {
      // occupancy as VOLUME, in three states: init (the prior's hypothesis),
      // final (what optimization settled on), delta (the judgment's edits).
      if (state.occState === undefined) state.occState = 'init';
      let oFin = run._oFin;
      if (state.occState !== 'init' && oFin === undefined) {
        run._oFin = null; // in flight
        const metas = run.snapshots || [];
        const last = metas[metas.length - 1];
        const done = d => {
          const m = {}; d.free_cells.forEach((ci, k) => m[ci] = d.o[k]);
          run._oFin = m; if (state.tab === 's2') renderTab();
        };
        if (last) {
          if (last.ref) fetch('../' + last.ref).then(r => r.json()).then(done).catch(() => {});
          else done(last);
        }
        oFin = null;
      }
      const groups = {};  // color -> cells
      s2.cells.forEach(c => {
        if (c.fixed === 0 || !c.edges || !c.edges.length) return;
        const oi = (c.o_init ?? 0.5) > 0.5;
        const of_ = oFin ? (oFin[c.idx] ?? 0) > 0.5 : null;
        let col = null;
        if (state.occState === 'init') col = oi ? 0xf08c28 : null;
        else if (state.occState === 'final') col = of_ ? 0x39b3a6 : null;
        else if (of_ !== null) {  // delta: the optimizer's edits only
          if (oi && !of_) col = 0xe5484d;       // 제거(구멍)
          else if (!oi && of_) col = 0xf08c28;  // 신규(유령 또는 정당 추가)
        }
        if (col !== null) (groups[col] = groups[col] || []).push(c);
      });
      for (const [col, cells] of Object.entries(groups)) {
        drawCellBoxes(cells, +col, 0.4);
      }
      drawFacetOutlines(interior, 0.22);  // candidate facets, light
      if (state.showPlanesS2) {  // candidate planes beside the volume (S1 재료)
        addFaces(interior, (f) => {
          const p = (run.s1 && run.s1.planes || []).find(q => q.id === f.plane_id);
          return SRC_COLORS[p ? p.source : 'domain'] || 0x667788;
        }, () => 0.14);
      }
      drawSeedsS2(run);
      drawFinalGaussians(run);
      panelS2(run, s2);
    } else {
    addCellWires(s2.cells, (c) => c.fixed === 0 ? 0x5a3040
      : (state.showInit !== false && (c.o_init ?? 0.5) > 0.5) ? 0xf08c28 : 0x3f77b0);
    addFaces(interior, () => 0x4a9eff, () => 0.06);
    drawSeedsS2(run);
    drawFinalGaussians(run);
    panelS2(run, s2);
    }
  } else if (state.tab === 's34') {
    const snaps = run.snapshots || [];
    $('#tl-slider').max = Math.max(0, snaps.length - 1);
    if (state.snap >= snaps.length) state.snap = snaps.length - 1;
    const meta = snaps[state.snap];
    run._snapCache = run._snapCache || {};
    let snap = meta && (meta.iter !== undefined && meta.ref
      ? run._snapCache[meta.iter] : meta);
    if (meta && meta.ref && !snap) {
      $('#panel').innerHTML = '<p>스냅샷 로딩 중…</p>';
      fetch('../' + meta.ref).then(r => r.json()).then(d => {
        d.renders = meta.renders; run._snapCache[meta.iter] = d; renderTab();
      });
      return;
    }
    if (snap && meta.renders) snap.renders = meta.renders;
    if (snap) {
      const vMap = {}; snap.renderable_faces.forEach((fi, si) => vMap[fi] = snap.face_v[si]);
      addFaces(faces, (f) => {
        const p = (run.s1.planes || []).find(q => q.id === f.plane_id);
        return SRC_COLORS[p ? p.source : 'domain'] || 0x667788;
      }, (f, i) => { const fi = (f.fi !== undefined) ? f.fi : i; return vMap[fi] !== undefined ? Math.min(0.95, vMap[fi]) : 0; });
      // the optimization as a story: at this iteration, the volume the
      // occupancy claims (teal boxes) + the appearance discs (new runs)
      if (snap.o && snap.free_cells) {
        const oMap = {}; snap.free_cells.forEach((ci, k) => oMap[ci] = snap.o[k]);
        drawCellBoxes(s2.cells.filter(c => c.fixed !== 0 &&
          (oMap[c.idx] ?? 0) > 0.5 && c.edges && c.edges.length), 0x39b3a6, 0.15);
      }
      if (snap.g) drawGaussianDiscs(snap.g, 0.8);
      drawFacetOutlines(interior, 0.1);  // static plane-structure context
      panelS34(run, snap);
    }
  } else if (state.tab === 's5') {
    if (state.evMode === 'brep' && run.s5_obj) {
      loadObj('../' + run.s5_obj);
    } else {
      if (!run.s5_evidence && run.s5_evidence_ref) {
        if (!run._evload) {
          run._evload = true;
          fetch('../' + run.s5_evidence_ref).then(r => r.json())
            .then(d => { run.s5_evidence = d; renderTab(); });
        }
        $('#panel').innerHTML = '<p>증거 카드 로딩 중…</p>';
        return;
      }
      const ev = run.s5_evidence || [];
      const evByFace = {}; ev.forEach(e => evByFace[e.face] = e);
      // init-vs-adjusted comparison: face gate from o_init vs the optimized one
      const oInitOf = (ci) => {
        const c = ci >= 0 ? s2.cells[ci] : null;
        if (!c || c.fixed === 0) return 0;
        return c.o_init ?? 0.5;
      };
      const dState = (f, i) => {
        const e = evByFace[(f.fi !== undefined) ? f.fi : i];
        const v1 = e ? e.v_final : 0;
        const v0 = Math.abs(oInitOf(f.cell_a) - oInitOf(f.cell_b));
        return (v0 > 0.5 ? 2 : 0) + (v1 > 0.5 ? 1 : 0); // 3=유지 1=신규 2=제거
      };
      addFaces(faces, (f, i) => {
        if (state.evMode === 'delta') {
          const d = dState(f, i);
          return d === 3 ? 0x9aa4b0 : d === 1 ? 0xf08c28 : 0xe5484d;
        }
        const e = evByFace[(f.fi !== undefined) ? f.fi : i]; if (!e) return 0x333944;
        if (state.evMode === 'class') return CLS_COLORS[e.class] || 0x888888;
        if (state.evMode === 'support') {
          const t = Math.min(1, e.photo_support_proxy * 1.6);
          return new THREE.Color(1 - t, t, 0.25).getHex();
        }
        return e.has_prior ? 0x4a9eff : 0x50d890; // prior vs current
      }, (f, i) => {
        if (state.evMode === 'delta') {
          const d = dState(f, i);
          return d === 3 ? 0.3 : d === 1 ? 0.9 : d === 2 ? 0.55 : 0;
        }
        const e = evByFace[(f.fi !== undefined) ? f.fi : i]; return e && e.v_final > 0.5 ? 0.92 : 0.03;
      });
      if (state.showFacetEdges !== false) {
        // facet outlines on active faces: the arrangement decomposition itself
        const pts = [];
        faces.forEach((f, i) => {
          const e = evByFace[(f.fi !== undefined) ? f.fi : i];
          if (!e || e.v_final <= 0.5) return;
          const P = f.poly3d;
          for (let k = 0; k < P.length; k++) {
            pts.push(...P[k], ...P[(k + 1) % P.length]);
          }
        });
        if (pts.length) {
          const g = new THREE.BufferGeometry();
          g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
          const lm = new THREE.LineBasicMaterial({ color: 0x141619, transparent: true, opacity: 0.7 });
          lm.userData.baseOp = 0.7;
          group.add(new THREE.LineSegments(g, lm));
        }
      }
      panelS5(run);
    }
  }
  drawLod2Rings(run);
  const g = TAB_GUIDE[state.tab];
  $('#panel').insertAdjacentHTML('afterbegin',
    (g ? `<div class="note" style="border:1px solid #2e3542;border-radius:5px;padding:6px;margin-bottom:6px">${g}</div>` : '')
    + modelControlsHtml() + overlayControlsHtml(run));
  bindOverlayControls(); bindModelControls();
  applyModelAlpha();
  refreshOverlays();
  fitView(interior.length ? interior : faces);
}
function loadObj(path) {
  fetch(path).then(r => r.text()).then(txt => {
    const verts = []; let cls = 'roof'; const tris = { roof: [], wall: [], ground: [] };
    const runDir = state.run && state.run.dir;
    txt.split('\n').forEach(ln => {
      const t = ln.trim().split(/\s+/);
      if (t[0] === 'v') verts.push([+t[1], +t[2], +t[3]]);
      else if (t[0] === 'g') cls = t[1] in tris ? t[1] : 'roof';
      else if (t[0] === 'f') tris[cls].push(t.slice(1).map(s => parseInt(s) - 1));
    });
    for (const [c, list] of Object.entries(tris)) {
      const pos = [];
      list.forEach(tr => tr.forEach(vi => pos.push(...verts[vi])));
      if (!pos.length) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.computeVertexNormals();
      const om = new THREE.MeshLambertMaterial({
        color: CLS_COLORS[c], side: THREE.DoubleSide, transparent: true, opacity: 0.95 });
      om.userData.baseOp = 0.95;
      group.add(new THREE.Mesh(g, om));
    }
    // oracle-style runs skip the arrangement fitView -> fit camera to the OBJ
    if (state.lastFit !== runDir && verts.length) {
      state.lastFit = runDir;
      const bb = new THREE.Box3();
      verts.forEach(v => bb.expandByPoint(new THREE.Vector3(v[0], v[1], v[2])));
      bb.getCenter(orbit.target);
      orbit.r = bb.getSize(new THREE.Vector3()).length() * 1.1 + 5;
      applyOrbit();
    }
    if (state.run && !state.run.s2_ref && !state.run.s2) {
      const stats = {};
      for (const [c, list] of Object.entries(tris)) {
        let area = 0;
        list.forEach(tr => {
          const a = verts[tr[0]], b = verts[tr[1]], cc = verts[tr[2]];
          const ux = b[0]-a[0], uy = b[1]-a[1], uz = b[2]-a[2];
          const vx = cc[0]-a[0], vy = cc[1]-a[1], vz = cc[2]-a[2];
          area += 0.5 * Math.hypot(uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx);
        });
        stats[c] = { tris: list.length, area: Math.round(area) };
      }
      panelOracle(state.run, stats);
    } else {
      panelS5(state.run);
    }
  });
}
function panelOracle(run, stats) {
  let h = `<div class="note" style="border:1px solid #2e3542;border-radius:5px;padding:6px;margin-bottom:6px">${TAB_GUIDE.s5}</div>`
    + modelControlsHtml() + overlayControlsHtml(run) + lod2ToggleHtml(run) + evalTable(run)
    + '<h2>S5 산출 (오라클 — 최적화 0)</h2>'
    + '<table><tr><th class="l">클래스</th><th>삼각형</th><th>면적 m²</th></tr>';
  for (const c of ['roof', 'wall', 'ground']) {
    const st = stats[c] || { tris: 0, area: 0 };
    h += `<tr><td class="l">${c}</td><td>${st.tris}</td><td>${st.area}</td></tr>`;
  }
  h += '</table>';
  const oc = run._oracle;
  if (oc) {
    const v = oc.s1_verdict || {};
    h += `<h2>S1 게이트</h2><table><tr><th class="l">항목</th><th>값</th></tr>
      <tr><td class="l">판정</td><td class="${v.grade === 'PASS' ? 'good' : v.grade === 'PASS_RESIDUE' ? 'warn' : 'bad'}">${v.grade || '—'}</td></tr>
      <tr><td class="l">설명률</td><td>${v.explained !== undefined ? (v.explained * 100).toFixed(1) + '%' : '—'}</td></tr>
      <tr><td class="l">최대 응집 공백</td><td>${v.largest_gap_m2 ?? '—'} m²</td></tr>
      <tr><td class="l">배열 셀</td><td>${oc.cells ?? '—'}</td></tr></table>`;
  } else if (run._oracle === undefined) {
    run._oracle = null;
    fetch('../' + run.dir + '/oracle.json').then(r => r.ok ? r.json() : null)
      .then(d => { run._oracle = d; if (state.run === run) panelOracle(run, stats); })
      .catch(() => {});
  }
  $('#panel').innerHTML = h;
  bindOverlayControls(); bindLod2Toggle(); bindModelControls();
  applyModelAlpha();
}

// ---------- panels ----------
function esc(x) { return String(x).replace(/</g, '&lt;'); }
function planeTable(planes, extra) {
  let h = '<table><tr><th class="l">평면(클릭=강조)</th><th class="l">출처</th>' + (extra ? '<th>Δ각°</th><th>Δd m</th>' : '') + '</tr>';
  planes.forEach(p => {
    const sel = state.hl && state.hl.plane === p.id;
    h += `<tr data-pid="${esc(p.id)}" style="cursor:pointer${sel ? ';background:#4a3d10' : ''}">` +
      `<td class="l">${esc(p.id)}</td><td class="l">${esc(p.source || '')}</td>`;
    if (extra) h += `<td>${(p.dn_deg || 0).toFixed(2)}</td><td>${(p.dd_m || 0).toFixed(3)}</td>`;
    h += '</tr>';
  });
  return h + '</table>';
}
function bindPlaneRows() {
  document.querySelectorAll('tr[data-pid]').forEach(tr => {
    tr.onclick = () => {
      const pid = tr.dataset.pid;
      state.hl = (state.hl && state.hl.plane === pid) ? {} : { plane: pid };
      renderTab();
    };
  });
  document.querySelectorAll('tr[data-face]').forEach(tr => {
    tr.onclick = () => {
      const fi = +tr.dataset.face;
      state.hl = (state.hl && state.hl.face === fi) ? {} : { face: fi };
      renderTab();
    };
  });
}
function panelS1(run) {
  const s = state.s1src || { prior_als: true, mvs: true, footprint: false };
  $('#panel').innerHTML = `<h2>S1 후보 평면 (${run.s1.planes.length})</h2>
    <div class="legend" id="s1src">평면 소스:
      <label><input type="checkbox" data-src="prior_als" ${s.prior_als ? 'checked' : ''}> <span style="color:#4a9eff">prior(ALS)</span></label>
      <label style="margin-left:6px"><input type="checkbox" data-src="mvs" ${s.mvs ? 'checked' : ''}> <span style="color:#ffa040">MVS</span></label>
      <label style="margin-left:6px"><input type="checkbox" data-src="footprint" ${s.footprint ? 'checked' : ''}> <span style="color:#9aa4b0">footprint 벽</span></label>
    </div>
    <div class="legend"><label><input type="checkbox" id="lod2tgl" ${state.showLod2 !== false ? 'checked' : ''}> <span style="color:#30d060">LoD2 GT 지붕 링(초록 선)</span></label>
    ${run.lod2_rings ? '' : ' — 이 런엔 없음'}</div>
    ${planeTable(run.s1.planes.filter(p => p.source !== 'footprint' || s.footprint))}`;
  document.querySelectorAll('#s1src input').forEach(cb => {
    cb.onchange = () => { state.s1src[cb.dataset.src] = cb.checked; renderTab(); };
  });
  bindPlaneRows();
  const lt = $('#lod2tgl');
  if (lt) lt.onchange = () => { state.showLod2 = lt.checked; renderTab(); };
}
function panelS2(run, s2) {
  const cells = (s2 && s2.cells) || [];
  const free = cells.filter(c => c.fixed !== 0);
  $('#panel').innerHTML = `<h2>S2 분할·초기화 (셀·o_init·시드)</h2>
    <p class="legend">표시:
    <label><input type="radio" name="s2mode" value="voxel" ${state.s2Mode !== 'wire' ? 'checked' : ''}> o_init 복셀(가벼움)</label>
    <label><input type="radio" name="s2mode" value="wire" ${state.s2Mode === 'wire' ? 'checked' : ''}> 전체 와이어</label></p>
    <table><tr><th class="l">항목</th><th>값</th></tr>
    <tr><td class="l">셀 (자유/고정빈)</td><td>${free.length} / ${cells.length - free.length}</td></tr>
    <tr><td class="l">면</td><td>${(run.s2_counts||{}).faces ?? (s2? s2.faces.length : '—')}</td></tr>
    <tr><td class="l">렌더 가능 면</td><td>${(run.s2_counts||{}).renderable ?? '—'}</td></tr>
    <tr><td class="l">가우시안 시드</td><td>${run.metrics ? run.metrics.gaussians : '—'}</td></tr></table>
    ${state.s2Mode !== 'wire' ? `<p class="legend">점유 상태:
    <label><input type="radio" name="occst" value="init" ${state.occState !== 'final' && state.occState !== 'delta' ? 'checked' : ''}> 초기</label>
    <label><input type="radio" name="occst" value="final" ${state.occState === 'final' ? 'checked' : ''}> 최종</label>
    <label><input type="radio" name="occst" value="delta" ${state.occState === 'delta' ? 'checked' : ''}> Δ(판정 수정분)</label>
    &nbsp;<label><input type="checkbox" id="planetgl" ${state.showPlanesS2 ? 'checked' : ''}> 후보 평면 면(출처색)</label></p>
    <p class="legend">초기: <span style="color:#f08c28">주황</span>=prior의 부피 가설 —
    E1/E7 점 지붕이 주황 상면에 접해야 정상. 최종: <span style="color:#39b3a6">청록</span>=
    최적화 후 solid. Δ: <span style="color:#f08c28">주황</span>=판정이 새로 채움,
    <span style="color:#e5484d">빨강</span>=판정이 비움(구멍). 재현 런은 Δ가 비어야 정상.
    옅은 파란 선 = 후보 facet 윤곽 (o_init 토글은 와이어 모드 전용)</p>` : `
    <p class="legend"><label><input type="checkbox" id="inittgl" ${state.showInit !== false ? 'checked' : ''}> o_init 표시</label>
    — <span style="color:#f08c28">주황</span>=초기 solid 셀(prior의 부피 가설),
    파랑=초기 empty 자유 셀, 자주=고정 빈 셀. E7/E1 점을 켜고 "점은 있는데 주황이
    없는 부피"를 찾으면 그게 init 결손(타워·지붕 갭)</p>`}
    <p class="legend"><label><input type="checkbox" id="seedtgl" ${state.showSeeds !== false ? 'checked' : ''}> 시드(초기 가우시안)</label>
    — 색 = 소속 평면 소스: <span style="color:#4a9eff">prior</span>
    <span style="color:#ffa040">MVS</span> <span style="color:#9aa4b0">footprint벽</span>
    <span style="color:#667788">domain</span>
    &nbsp;<label><input type="checkbox" id="finalgtgl" ${state.showFinalG ? 'checked' : ''}> <span style="color:#39b3a6">최종 가우시안</span></label>
    (신규 런만 — 살아남은 α>0.3 점) — 초기↔최종을 같은 점 형태로 비교</p>`;
  const st = $('#seedtgl');
  if (st) st.onchange = () => { state.showSeeds = st.checked; renderTab(); };
  const it = $('#inittgl');
  if (it) it.onchange = () => { state.showInit = it.checked; renderTab(); };
  document.querySelectorAll('input[name="s2mode"]').forEach(r => {
    r.onchange = () => { state.s2Mode = r.value; renderTab(); };
  });
  document.querySelectorAll('input[name="occst"]').forEach(r => {
    r.onchange = () => { state.occState = r.value; renderTab(); };
  });
  const fg = $('#finalgtgl');
  if (fg) fg.onchange = () => { state.showFinalG = fg.checked; renderTab(); };
  const pt = $('#planetgl');
  if (pt) pt.onchange = () => { state.showPlanesS2 = pt.checked; renderTab(); };
}
function chart(canvas, series, labels) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width = canvas.clientWidth * 2, H = canvas.height = 240;
  ctx.clearRect(0, 0, W, H);
  const all = series.flatMap(s => s.data).filter(v => isFinite(v));
  if (!all.length) return;
  const max = Math.max(...all), min = Math.min(0, ...all);
  const colors = ['#8ecbff', '#ffd866', '#ff7b72', '#7ee787'];
  series.forEach((s, si) => {
    ctx.strokeStyle = colors[si % 4]; ctx.lineWidth = 2; ctx.beginPath();
    s.data.forEach((v, i) => {
      const x = 8 + (W - 16) * i / Math.max(1, s.data.length - 1);
      const y = H - 8 - (H - 16) * (v - min) / (max - min + 1e-9);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
  });
  ctx.fillStyle = '#9fb4cc'; ctx.font = '20px sans-serif';
  ctx.fillText(labels.join(' / '), 10, 24);
}
function panelS34(run, snap) {
  const snaps = run.snapshots;
  $('#tl-label').textContent = `iter ${snap.iter} (${state.snap + 1}/${snaps.length})`;
  $('#tl-slider').value = state.snap;
  const und = snap.o.filter(o => o > 0.3 && o < 0.7).length;
  let h = `<h2>S3+4 — iter ${snap.iter}</h2>
    <table><tr><th class="l">항목</th><th>값</th></tr>
    <tr><td class="l">PSNR(eval)</td><td>${(snap.psnr_eval || 0).toFixed(2)}</td></tr>
    <tr><td class="l">λ_bin</td><td>${(snap.lambda_bin || 0).toFixed(3)}</td></tr>
    <tr><td class="l">게이트 ∂L/∂o 비영</td><td class="${snap.gate.grad_nonzero_frac > 0.5 ? 'good' : 'bad'}">${(snap.gate.grad_nonzero_frac * 100).toFixed(0)}%</td></tr>
    <tr><td class="l">미결정 셀(0.3~0.7)</td><td class="${und ? 'warn' : 'good'}">${und}</td></tr>
    <tr><td class="l">δ̂ [m]</td><td>[${snap.delta_hat.map(v => v.toFixed(3)).join(', ')}]</td></tr></table>
    <h2>손실 추이</h2><canvas class="chart" id="losschart"></canvas>
    <h2>점유 o (자유 셀)</h2><div class="legend">${snap.o.map(o =>
      `<span style="background:rgba(74,158,255,${o});border:1px solid #2e3542">${o.toFixed(2)}</span>`).join('')}</div>
    <h2>평면 Δ</h2>${planeTable(snap.planes, true)}
    <h2>렌더 ↔ 타깃</h2><div id="snapimgs">${(snap.renders || []).map(p =>
      `<img src="../${p}">`).join('')}</div>`;
  $('#panel').innerHTML = h;
  bindPlaneRows();
  const c = $('#losschart');
  const loaded = snaps.slice(0, state.snap + 1)
    .map(m => (m.ref ? (run._snapCache || {})[m.iter] : m)).filter(Boolean);
  chart(c, [
    { data: loaded.map(s => s.losses.photo) },
    { data: loaded.map(s => s.losses.bin) },
    { data: loaded.map(s => s.losses.prior || 0) },
    { data: loaded.map(s => s.psnr_eval / 40) },
  ], ['photo', 'bin', 'prior', 'psnr/40 (로드된 스냅샷만)']);
}
function evalTable(run) {
  if (!run.eval) return '';
  let h = '<h2>봉인 평가 (f1@0.5 / comp@0.25 / acc)</h2><table><tr><th class="l">GT</th><th>f1</th><th>comp</th><th>acc(m)</th></tr>';
  for (const gt of ['e1', 'lod2']) {
    const e = run.eval[gt];
    if (!e) continue;
    h += `<tr><td class="l">${gt}</td><td>${(+e['f1@0.5']).toFixed(3)}</td>` +
      `<td>${(+e['completeness@0.25']).toFixed(3)}</td><td>${(+e['acc_median']).toFixed(2)}</td></tr>`;
  }
  return h + '</table>';
}
function panelS5(run) {
  const ev = run.s5_evidence || [];
  const live = ev.filter(e => e.v_final > 0.5);
  let h = evalTable(run) + `<h2>S4 모델 (구조화 산출)</h2>
    <select id="evmode">
      <option value="class" ${state.evMode === 'class' ? 'selected' : ''}>의미 분류</option>
      <option value="support" ${state.evMode === 'support' ? 'selected' : ''}>이미지 지지도</option>
      <option value="prior" ${state.evMode === 'prior' ? 'selected' : ''}>prior 의존</option>
      <option value="delta" ${state.evMode === 'delta' ? 'selected' : ''}>Δ 초기 대비(판정 diff)</option>
      <option value="brep" ${state.evMode === 'brep' ? 'selected' : ''}>B-rep OBJ</option>
    </select>
    <label style="margin-left:8px"><input type="checkbox" id="fedgetgl" ${state.showFacetEdges !== false ? 'checked' : ''}> facet 윤곽</label>
    ${state.evMode === 'delta' ? `<p class="legend">회색=유지(초기·최종 모두 면),
    <span style="color:#f08c28">주황=판정이 새로 켠 면</span>,
    <span style="color:#e5484d">빨강=판정이 끈 면</span> — 재현 모델과의 차이가
    곧 최적화의 손길. 재현 런(pfreeze)에서는 전부 회색이어야 정상</p>` : ''}`;
  if (!run.s5_planes && run.s5_planes_ref) {
    fetch('../' + run.s5_planes_ref).then(r => r.json())
      .then(d => { run.s5_planes = d; renderTab(); }).catch(() => {});
  }
  const gs = run.metrics && run.metrics.group_counts_semantic;
  const gf = run.metrics && run.metrics.group_counts;
  const ps = run.s5_planes;
  if (gs || ps || gf) {
    const sem = gs || (ps && ps.reduce((a, r) => {
      a[r.class] = (a[r.class] || 0) + r.surfaces; return a; }, {})) || {};
    h += `<table><tr><th></th><th>roof</th><th>wall</th><th>ground</th></tr>
      <tr><td class="l">의미면 수</td>` +
      ['roof', 'wall', 'ground'].map(c => `<td>${sem[c] ?? '—'}</td>`).join('') +
      `</tr>${gf ? `<tr><td class="l">(facet 조각)</td>` +
      ['roof', 'wall', 'ground'].map(c => `<td>${gf[c] ?? 0}</td>`).join('') +
      '</tr>' : ''}</table>`;
  }
  if (ps && ps.length) {
    // per-plane judgment evidence, aggregated from s5_evidence facet rows
    const agg = {};
    ev.forEach(e => {
      const a = agg[e.plane_id] = agg[e.plane_id] ||
        {va: 0, sa: 0, area: 0, prior: false};
      a.va += e.v_final * e.area; a.sa += e.photo_support_proxy * e.area;
      a.area += e.area; a.prior = a.prior || e.has_prior;
    });
    h += `<h2>평면 단위 요약 (${ps.length}평면 — 행 클릭 = 3D 강조)</h2>
      <table><tr><th class="l">평면</th><th class="l">클래스</th><th>면</th>
      <th>facet</th><th>면적</th><th>v̄</th><th>지지</th><th class="l">prior</th></tr>` +
      ps.slice(0, 20).map(r => {
        const a = agg[r.plane_id];
        const sel = state.hl && state.hl.plane === r.plane_id;
        return `<tr data-pid="${esc(r.plane_id)}" style="cursor:pointer${sel ? ';background:#4a3d10' : ''}">
         <td class="l">${esc(r.plane_id)}</td><td class="l">${r.class}</td>
         <td>${r.surfaces}</td><td>${r.facets}</td><td>${r.area}</td>
         <td>${a && a.area ? (a.va / a.area).toFixed(2) : '—'}</td>
         <td>${a && a.area ? (a.sa / a.area).toFixed(2) : '—'}</td>
         <td class="l">${a ? (a.prior ? 'O' : '—') : '—'}</td></tr>`;
      }).join('') + '</table>';
  }
  $('#panel').innerHTML = h;
  $('#evmode').onchange = (e) => { state.evMode = e.target.value; renderTab(); };
  const fe = $('#fedgetgl');
  if (fe) fe.onchange = () => { state.showFacetEdges = fe.checked; renderTab(); };
  bindPlaneRows();
}
function renderQuant() {
  const runs = state.manifest.runs;
  const cols = [
    ['occupancy_accuracy', '점유정확도'], ['ghost_faces', '유령면'], ['missing_faces', '누락면'],
    ['o_undecided', '미결정셀'], ['o_decision', '결정도'], ['psnr_eval_final', 'PSNR'],
    ['cells', '셀'], ['faces', '면'], ['gaussians', '가우시안'], ['wall_s', '시간s']];
  let h = `<h2 style="color:#8ecbff">정량표 — 전체 런</h2>
    <button class="small" id="csv">CSV 내보내기</button>
    <table style="margin-top:8px"><tr><th class="l">실험</th><th class="l">런</th>${cols.map(c => `<th>${c[1]}</th>`).join('')}<th class="l">δ̂</th></tr>`;
  runs.forEach(r => {
    const m = r.metrics || {};
    h += `<tr><td class="l">${r.exp}</td><td class="l">${esc(r.name)}</td>`;
    cols.forEach(([k]) => {
      let v = m[k]; let c = '';
      if (k === 'occupancy_accuracy' && v !== undefined) c = v === 1 ? 'good' : 'bad';
      if ((k === 'ghost_faces' || k === 'missing_faces') && v !== undefined) c = v === 0 ? 'good' : 'bad';
      h += `<td class="${c}">${v === undefined ? '—' : (typeof v === 'number' ? +v.toFixed(3) : v)}</td>`;
    });
    h += `<td class="l">${m.delta_hat ? m.delta_hat.map(x => x.toFixed(2)).join(',') : '—'}</td></tr>`;
  });
  h += '</table>';
  for (const [exp, s] of Object.entries(state.manifest.summaries || {})) {
    if (s._verdict) h += `<h2 style="color:#8ecbff">${exp} 사전 등록 판정</h2>
      <pre style="font-size:11px;background:#12141a;padding:8px;border-radius:5px">${esc(JSON.stringify(s._verdict, null, 1))}</pre>`;
  }
  // per-snapshot metric table for current run
  if (state.run && state.run.snapshots.length) {
    h += `<h2 style="color:#8ecbff">스냅샷 추이 — ${esc(state.run.name)}</h2>
      <table><tr><th>iter</th><th>photo</th><th>bin</th><th>prior</th><th>PSNR</th><th>게이트%</th><th>λ_bin</th></tr>`;
    state.run.snapshots.forEach(m => {
      const s = m.ref ? (state.run._snapCache || {})[m.iter] : m;
      if (!s) return;
      h += `<tr><td>${s.iter}</td><td>${s.losses.photo.toFixed(4)}</td><td>${s.losses.bin.toFixed(4)}</td>
        <td>${(s.losses.prior || 0).toFixed(4)}</td><td>${(s.psnr_eval || 0).toFixed(2)}</td>
        <td>${(s.gate.grad_nonzero_frac * 100).toFixed(0)}</td><td>${(s.lambda_bin || 0).toFixed(2)}</td></tr>`;
    });
    h += '</table>';
  }
  $('#quantwrap').innerHTML = h;
  $('#csv').onclick = () => {
    let csv = 'exp,run,' + cols.map(c => c[0]).join(',') + ',delta_hat\n';
    runs.forEach(r => {
      const m = r.metrics || {};
      csv += `${r.exp},${r.name},` + cols.map(([k]) => m[k] ?? '').join(',') +
        `,"${m.delta_hat || ''}"\n`;
    });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = 'arrgs_quant.csv'; a.click();
  };
}

// ---------- boot ----------
const GROUPS = [
  ['ANCHOR', '앵커 w-스윕 (L_occ_prior) — 합성 게이트 + 실건물 3동', false],
  ['ORACLE', '오라클(무학습 대조군) 93동 — S5+E1로 prior 재현 확인', false],
  ['X1', '실건물 — 정상 대조 1동', false],
  ['X2', '실건물 — 변화/구멍 프로파일', false],
  ['X4', '실건물 93동 일괄', true],
  ['X3', '실건물 — δ 오염 주입(진단용)', true],
  ['X0', '합성 장난감 검증(개발용 — 실건물 아님)', true],
];
const TAB_DEFAULT_OVERLAY = {
  s1: { E7: true, E1: false, E2: false },   // S1 검수: 후보 평면 vs ALS 입력
  s2: { E7: true, E1: false, E2: false },
  s34: { E7: false, E1: false, E2: false },
  s5: { E7: false, E1: true, E2: false },   // 결과 검수: 모델 vs GT
};
fetch('./manifest.json').then(r => r.json()).then(man => {
  state.manifest = man;
  const list = $('#runs');
  const guide = document.createElement('div');
  guide.className = 'note';
  guide.style.cssText = 'border:1px solid #2e3542;border-radius:5px;padding:6px;margin-bottom:8px';
  guide.innerHTML = '<b style="color:#8ecbff">보는 법</b><br>' +
    '① 아래에서 건물 클릭 (B022/B173/B036 추천)<br>' +
    '② [S5 산출] 탭: 색면=결과 모델, <span style="color:#5b9bd5">파란 점=E1 GT</span> — 겹치면 성공<br>' +
    '③ [S1 후보] 탭: 반투명 면=후보 평면, <span style="color:#40cfe0">청록 점=ALS 입력</span> — 점이 면 밖에 많으면 S1 결함<br>' +
    '④ [S3+4] 탭: 하단 슬라이더로 학습 과정 재생';
  list.appendChild(guide);
  let firstBtn = null;
  GROUPS.forEach(([exp, label, collapsed]) => {
    const runs = man.runs.filter(r => r.exp === exp);
    if (!runs.length) return;
    const h = document.createElement('div');
    h.style.cssText = 'margin:8px 0 3px;color:#8ecbff;font-weight:600;cursor:pointer;font-size:12px';
    h.textContent = `${collapsed ? '▸' : '▾'} ${label} (${runs.length})`;
    list.appendChild(h);
    const box = document.createElement('div');
    box.style.display = collapsed ? 'none' : 'block';
    h.onclick = () => {
      const open = box.style.display === 'none';
      box.style.display = open ? 'block' : 'none';
      h.textContent = `${open ? '▾' : '▸'} ${label} (${runs.length})`;
    };
    runs.forEach(r => {
      const b = document.createElement('button');
      b.className = 'runbtn';
      let pretty = r.bkey ? r.bkey.split('_')[0] + ' · ' + r.bkey.split('_').pop() : r.name;
      if (r.bkey) {
        const suffix = r.name.replace(/^B\d+_?/, '').replace(/^(clean|changed|hole)$/, '');
        if (suffix && !r.name.startsWith('B0')) pretty += ` (${r.name})`;
        else if (suffix) pretty += ` (${suffix.replace('ablation_', '절제:')})`;
      }
      b.innerHTML = `<span class="exp">${r.exp}</span>${esc(pretty)}`;
      b.onclick = () => {
        document.querySelectorAll('.runbtn').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        state.run = r; state.snap = (r.snapshots || []).length - 1;
        Object.keys(cloudCache).forEach(k => { if (!k.startsWith(r.dir)) delete cloudCache[k]; });
        state.overlayOn = { ...(TAB_DEFAULT_OVERLAY[state.tab] || {}) };
        $('#hud').textContent = `${pretty} — 좌드래그 회전 · 우드래그 이동 · 휠 줌`;
        renderTab();
      };
      box.appendChild(b);
      if (!firstBtn) firstBtn = b;
    });
    list.appendChild(box);
  });
  if (firstBtn) firstBtn.click();
  resize();
});
document.querySelectorAll('#tabs button').forEach(b =>
  b.onclick = () => {
    state.tab = b.dataset.tab;
    if (TAB_DEFAULT_OVERLAY[state.tab]) state.overlayOn = { ...TAB_DEFAULT_OVERLAY[state.tab] };
    renderTab();
  });
$('#tl-slider').oninput = (e) => { state.snap = +e.target.value; renderTab(); };
$('#tl-play').onclick = () => {
  if (state.playing) { clearInterval(state.playing); state.playing = null; $('#tl-play').textContent = '▶'; return; }
  $('#tl-play').textContent = '⏸';
  state.playing = setInterval(() => {
    const n = (state.run.snapshots || []).length;
    state.snap = (state.snap + 1) % n; renderTab();
    if (state.snap === n - 1) { clearInterval(state.playing); state.playing = null; $('#tl-play').textContent = '▶'; }
  }, 700);
};
