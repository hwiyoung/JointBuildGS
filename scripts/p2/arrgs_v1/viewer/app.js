import * as THREE from './three.module.min.js';

const $ = (s) => document.querySelector(s);
const state = { manifest: null, run: null, tab: 's5', snap: 0, playing: null, evMode: 'class' };
const TAB_GUIDE = {
  s1: 'S1 검수: 반투명 면 = 후보 평면(출처별 색). 청록 점(ALS 입력)이 면에 붙어 있어야 정상 — 면 밖 점 덩어리 = 후보 누락.',
  s2: 'S2 검수: 평면들이 자른 부피 조각(셀). 파랑 와이어 = 최적화 대상 셀, 자주 = footprint 밖 고정-빈 셀.',
  s34: 'S3+4 검수: 하단 슬라이더로 학습 재생. 면이 진해질수록 표면으로 확정(v↑). 오른쪽 표는 개발 진단용 — 점유 o와 렌더↔사진 비교만 봐도 됨.',
  s5: 'S5 검수: 최종 모델(적갈=지붕, 회=벽, 녹=지면). 파란 점 = E1 GT — 색면이 파란 점을 따라가면 성공, 벗어나면 실패.',
};

const SRC_COLORS = { prior_als: 0x4a9eff, mvs: 0xffa040, footprint: 0x9aa4b0,
                     gt: 0x50d890, distractor: 0xff5f6e, domain: 0x556070 };
const CLS_COLORS = { roof: 0xd06048, wall: 0xb8b0a0, ground: 0x5a8f5a };

// ---------- three.js scaffold ----------
const view = $('#view3d');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
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
  if (drag.btn === 0) { orbit.th -= dx * 0.008; orbit.ph = Math.min(Math.PI - 0.05, Math.max(0.05, orbit.ph - dy * 0.008)); }
  else { const s = orbit.r * 0.0015;
    const right = new THREE.Vector3().subVectors(camera.position, orbit.target).cross(camera.up).normalize();
    orbit.target.addScaledVector(right, -dx * s); orbit.target.z += dy * s; }
  applyOrbit();
});
view.addEventListener('wheel', (e) => { orbit.r *= (1 + Math.sign(e.deltaY) * 0.1); applyOrbit(); e.preventDefault(); }, { passive: false });
view.addEventListener('contextmenu', (e) => e.preventDefault());
function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
(function loop() { requestAnimationFrame(loop); renderer.render(scene, camera); })();

let group = new THREE.Group(); scene.add(group);
let overlayGroup = new THREE.Group(); scene.add(overlayGroup);
let faceMeshes = [];   // aligned to s2.faces indices
function clear3d() {
  scene.remove(group); group = new THREE.Group(); scene.add(group); faceMeshes = [];
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
  faces.forEach((f, i) => {
    const mat = new THREE.MeshLambertMaterial({
      color: colorFn(f, i), transparent: true, opacity: opacityFn(f, i),
      side: THREE.DoubleSide, depthWrite: false });
    const m = new THREE.Mesh(faceGeometry(f.poly3d), mat);
    m.userData.faceIdx = i;
    group.add(m); faceMeshes[i] = m;
  });
}
function addCellWires(cells, colorFn) {
  cells.forEach((c) => {
    if (!c.edges || !c.edges.length) return;
    const pts = [];
    c.edges.forEach(([a, b]) => pts.push(...a, ...b));
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    const line = new THREE.LineSegments(g, new THREE.LineBasicMaterial({
      color: colorFn(c), transparent: true, opacity: 0.55 }));
    group.add(line);
  });
}
function fitView(faces) {
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
  if (!run || !run.s2) { $('#panel').innerHTML = '<p>런을 선택하세요.</p>'; return; }
  clear3d();
  const faces = run.s2.faces;
  const interior = faces.filter(f => f.cell_b >= 0 && !f.plane_id.startsWith('domain:'));
  if (state.tab === 's1') {
    addFaces(faces.filter(f => !f.plane_id.startsWith('domain:')),
      (f) => { const p = (run.s1.planes || []).find(q => q.id === f.plane_id);
               return SRC_COLORS[p ? p.source : 'domain'] || 0x888888; },
      () => 0.38);
    panelS1(run);
  } else if (state.tab === 's2') {
    addCellWires(run.s2.cells, (c) => c.fixed === 0 ? 0x5a3040 : 0x3f77b0);
    addFaces(interior, () => 0x4a9eff, () => 0.10);
    panelS2(run);
  } else if (state.tab === 's34') {
    const snaps = run.snapshots || [];
    $('#tl-slider').max = Math.max(0, snaps.length - 1);
    if (state.snap >= snaps.length) state.snap = snaps.length - 1;
    const snap = snaps[state.snap];
    if (snap) {
      const vMap = {}; snap.renderable_faces.forEach((fi, s) => vMap[fi] = snap.face_v[s]);
      addFaces(faces, (f) => {
        const p = (run.s1.planes || []).find(q => q.id === f.plane_id);
        return SRC_COLORS[p ? p.source : 'domain'] || 0x667788;
      }, (f, i) => (vMap[i] !== undefined ? Math.min(0.95, vMap[i]) : 0));
      panelS34(run, snap);
    }
  } else if (state.tab === 's5') {
    if (state.evMode === 'brep' && run.s5_obj) {
      loadObj('../' + run.s5_obj);
    } else {
      const ev = run.s5_evidence || [];
      const evByFace = {}; ev.forEach(e => evByFace[e.face] = e);
      addFaces(faces, (f, i) => {
        const e = evByFace[i]; if (!e) return 0x333944;
        if (state.evMode === 'class') return CLS_COLORS[e.class] || 0x888888;
        if (state.evMode === 'support') {
          const t = Math.min(1, e.photo_support_proxy * 1.6);
          return new THREE.Color(1 - t, t, 0.25).getHex();
        }
        return e.has_prior ? 0x4a9eff : 0x50d890; // prior vs current
      }, (f, i) => { const e = evByFace[i]; return e && e.v_final > 0.5 ? 0.92 : 0.03; });
      panelS5(run);
    }
  }
  const g = TAB_GUIDE[state.tab];
  $('#panel').insertAdjacentHTML('afterbegin',
    (g ? `<div class="note" style="border:1px solid #2e3542;border-radius:5px;padding:6px;margin-bottom:6px">${g}</div>` : '')
    + overlayControlsHtml(run));
  bindOverlayControls();
  refreshOverlays();
  fitView(interior.length ? interior : faces);
}
function loadObj(path) {
  fetch(path).then(r => r.text()).then(txt => {
    const verts = []; let cls = 'roof'; const tris = { roof: [], wall: [], ground: [] };
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
      group.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({
        color: CLS_COLORS[c], side: THREE.DoubleSide })));
    }
    panelS5(state.run);
  });
}

// ---------- panels ----------
function esc(x) { return String(x).replace(/</g, '&lt;'); }
function planeTable(planes, extra) {
  let h = '<table><tr><th class="l">평면</th><th class="l">출처</th>' + (extra ? '<th>Δ각°</th><th>Δd m</th>' : '') + '</tr>';
  planes.forEach(p => {
    h += `<tr><td class="l">${esc(p.id)}</td><td class="l">${esc(p.source || '')}</td>`;
    if (extra) h += `<td>${(p.dn_deg || 0).toFixed(2)}</td><td>${(p.dd_m || 0).toFixed(3)}</td>`;
    h += '</tr>';
  });
  return h + '</table>';
}
function panelS1(run) {
  $('#panel').innerHTML = `<h2>S1 후보 평면 (${run.s1.planes.length})</h2>
    <div class="legend"><span style="background:#4a9eff">prior(ALS)</span>
    <span style="background:#ffa040">MVS</span><span style="background:#9aa4b0;color:#222">footprint</span>
    <span style="background:#50d890;color:#222">GT</span><span style="background:#ff5f6e">교란</span></div>
    ${planeTable(run.s1.planes)}`;
}
function panelS2(run) {
  const cells = run.s2.cells;
  const free = cells.filter(c => c.fixed !== 0);
  $('#panel').innerHTML = `<h2>S2 배열</h2>
    <table><tr><th class="l">항목</th><th>값</th></tr>
    <tr><td class="l">셀 (자유/고정빈)</td><td>${free.length} / ${cells.length - free.length}</td></tr>
    <tr><td class="l">면</td><td>${run.s2.faces.length}</td></tr>
    <tr><td class="l">렌더 가능 면</td><td>${(run.s2.renderable_faces || []).length}</td></tr>
    <tr><td class="l">가우시안 시드</td><td>${run.metrics ? run.metrics.gaussians : '—'}</td></tr></table>
    <p class="legend">파랑 와이어=자유 셀, 자주=고정 빈 셀(footprint 밖)</p>`;
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
  const c = $('#losschart');
  chart(c, [
    { data: snaps.slice(0, state.snap + 1).map(s => s.losses.photo) },
    { data: snaps.slice(0, state.snap + 1).map(s => s.losses.bin) },
    { data: snaps.slice(0, state.snap + 1).map(s => s.losses.prior || 0) },
    { data: snaps.slice(0, state.snap + 1).map(s => s.psnr_eval / 40) },
  ], ['photo', 'bin', 'prior', 'psnr/40']);
}
function panelS5(run) {
  const ev = run.s5_evidence || [];
  const live = ev.filter(e => e.v_final > 0.5);
  let h = `<h2>S5 산출</h2>
    <select id="evmode">
      <option value="class" ${state.evMode === 'class' ? 'selected' : ''}>의미 분류</option>
      <option value="support" ${state.evMode === 'support' ? 'selected' : ''}>이미지 지지도</option>
      <option value="prior" ${state.evMode === 'prior' ? 'selected' : ''}>prior 의존</option>
      <option value="brep" ${state.evMode === 'brep' ? 'selected' : ''}>B-rep OBJ</option>
    </select>`;
  if (run.metrics && run.metrics.group_counts) {
    const g = run.metrics.group_counts;
    h += `<table><tr><th>roof</th><th>wall</th><th>ground</th></tr>
      <tr><td>${g.roof}</td><td>${g.wall}</td><td>${g.ground}</td></tr></table>`;
  }
  h += `<h2>증거 카드 (활성 면 ${live.length})</h2>
    <table><tr><th class="l">면</th><th class="l">클래스</th><th>v</th><th>지지</th><th class="l">prior</th></tr>`;
  live.sort((a, b) => b.area - a.area).slice(0, 30).forEach(e => {
    h += `<tr><td class="l">${e.face}:${esc(e.plane_id)}</td><td class="l">${e.class}</td>
      <td>${e.v_final.toFixed(2)}</td><td>${e.photo_support_proxy.toFixed(2)}</td>
      <td class="l">${e.has_prior ? 'O' : '—'}</td></tr>`;
  });
  $('#panel').innerHTML = h + '</table>';
  $('#evmode').onchange = (e) => { state.evMode = e.target.value; renderTab(); };
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
    state.run.snapshots.forEach(s => {
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
      const pretty = r.bkey ? r.bkey.split('_')[0] + ' · ' + r.bkey.split('_').pop() +
        (r.name.includes('dx') || r.name.includes('dz') ? ' (δ' + r.name.split('_').pop() + ')' : '')
        : r.name;
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
