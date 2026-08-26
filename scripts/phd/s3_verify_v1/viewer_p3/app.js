// S3 검증 페이지 3 — 공동 최적화(연속 구간) 정적 뷰어. NOT OFFICIAL · scientific_verdict: null.
// 데이터 계약: phd_s3_verify_s3a_v1 — ../runs/<name>/{manifest.json, s1_view.json, s2_faces.json}
// + S3a 추가분 {s3_views.json, s3_steps.jsonl, s3_face_residual.json, s3_tiles/<view_id>/*.png}.
// 3차 내부 단계(계획 문서 개정 주석 2026-08-27): 3a 렌더-온리(0 최적화 스텝 — 배선 자체 검증,
// backward 1회로 grad_norms만 기록) → 3b 색 → 3c δ → 3d 평면. 화면 축 = 사이클 타임라인 하나,
// 미구현 구간은 회색 "예정" — 페이지가 구현과 함께 자란다(스텝·구간 다수 전제).
// 렌더 상태(방법론 §2.1 r16): α_g=|o_a−o_b|∈{0,1} 유도(자유 알파 금지) · δ는 처음부터 렌더
// 인자로 배선하되 3a에서 0 고정 · 색 중립 회색 상수 · densification/pruning 금지(수명 규칙 ①)
// · 렌더러 gsplat(미분 가능 렌더링). S3a 부재 런은 빈 상태 안내(죽지 않음).
// three.js r160 vendored (CDN 금지). 궤도/팬/줌·다크 테마·판독 기록은 페이지 1·2 관행 승계.
import * as THREE from './three.module.min.js';

const $ = (s) => document.querySelector(s);
const esc = (x) => String(x).replace(/&/g, '&amp;').replace(/</g, '&lt;');
const escAttr = (x) => esc(x).replace(/"/g, '&quot;');
window.onerror = (msg, src, line) => {
  const el = $('#panel') || document.body;
  el.insertAdjacentHTML('afterbegin', `<div class="err">JS 오류: ${esc(msg)} (${line})</div>`);
};

// ---------- 색 관행 (페이지 1·2 계열 — 잔차 램프·차트 색은 검증기 통과 세트) ----------
const COL = {
  ghost: 0x3a4250,      // 잔차 없는 면 와이어 (게이트 0 등)
  domain: 0x2e3542,     // 도메인 외피 와이어
  border: 0x0e1013,     // 잔차 면 경계 (마크 분리)
  selFill: 0xffe066,    // 선택 윤곽 (맥동)
  ctx: 0x556070,
};
// 잔차 순차 램프 — 단일 색상(앰버) 어두움→밝음, 낮음=배경에 가깝게·높음=밝게.
const RAMP = [[0x2a, 0x20, 0x18], [0xb0, 0x6a, 0x1e], [0xff, 0xcf, 0x70]];
function rampRgb(t) {
  t = Math.min(1, Math.max(0, t));
  const [a, b] = t < 0.5 ? [RAMP[0], RAMP[1]] : [RAMP[1], RAMP[2]];
  const u = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u]
    .map(v => v / 255);
}
// 항별 손실 고정 색(엔티티 고정 — 순서 순환 금지). 미등록 항은 EXTRA에서, 소진 시 표에만.
const LOSS_COL = { photo: '#4a9eff', anchor: '#ff9a3c', area: '#2ee6c8', total: '#ffd866',
                   depth: '#cf9bff', silhouette: '#ff7b72' };
const LOSS_EXTRA = ['#8ecbff', '#d08a2e'];
const LOSS_ORDER = ['photo', 'anchor', 'area', 'depth', 'silhouette', 'total'];
// grad_norms 3군 — 배선 증거 (δ/평면/색)
const GRAD_DEF = [['delta', 'δ (P⁰⊕δ 강체 보정)', '#ff9a3c'],
                  ['planes', '평면 (미세조정 — 3a 동결)', '#4a9eff'],
                  ['colors', '색 (3a 중립 회색 상수)', '#7ee787']];
// 3차 내부 구간 등록부 — 미구현 구간은 회색 "예정" (계획 문서 개정 주석 2026-08-27)
const STAGES = [
  { id: '3a', label: '3a 렌더-온리', desc: '0 최적화 스텝 — 배선 자체 검증' },
  { id: '3b', label: '3b 색', desc: '색만 학습 (기하 동결)' },
  { id: '3c', label: '3c δ', desc: 'δ 해동 (주입 복원)' },
  { id: '3d', label: '3d 평면', desc: '평면 미세조정 (앵커 균형)' },
];

const state = {
  runs: [], runName: null, run: null, cache: {},
  selStep: null,     // index into d.s3.steps
  selView: null,     // view_id
  selFace: null,     // index into d.faces
  showGhost: true, showDomain: false,
  reading: {}, lastFit: null,
};

// ---------- three.js scaffold (페이지 1·2 승계) ----------
const view = $('#view3d');
let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  view.appendChild(renderer.domElement);
} catch (e) {  // WebGL 불가 환경 — 패널·타임라인·판독 기록은 그대로 동작
  view.innerHTML += `<div class="err" style="margin:10px">WebGL 사용 불가: ${esc(e.message)}</div>`;
}
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x14161a);
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 5000);
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
window.addEventListener('keydown', (e) => {  // ESC = 면 선택 해제
  if (e.key !== 'Escape' || !state.run) return;
  const t = e.target;
  if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.tagName === 'SELECT')) return;
  if (state.selFace !== null) { state.selFace = null; restyle(); renderPanel(); }
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

let heatGroup = new THREE.Group(),   // 잔차 면 채움(정점색) + 경계 와이어 + 픽
    wireGroup = new THREE.Group(),   // 잔차 없는 면(고스트)·도메인 외피 와이어
    ctxGroup = new THREE.Group(), selGroup = new THREE.Group();
scene.add(heatGroup, wireGroup, ctxGroup, selGroup);
function emptyGroup(g) {
  for (const o of [...g.children]) {
    g.remove(o);
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();
  }
}
function clear3d() {
  for (const g of [heatGroup, wireGroup, ctxGroup, selGroup]) { scene.remove(g); emptyGroup(g); }
  heatGroup = new THREE.Group(); wireGroup = new THREE.Group();
  ctxGroup = new THREE.Group(); selGroup = new THREE.Group();
  scene.add(heatGroup, wireGroup, ctxGroup, selGroup);
  hiliteMats = [];
}

// ---------- s3_steps.jsonl 파서 ----------
function parseJsonl(text) {
  const steps = []; let badLines = 0;
  for (const ln of text.split('\n')) {
    const s = ln.trim();
    if (!s) continue;
    try { steps.push(JSON.parse(s)); } catch { badLines++; }
  }
  steps.sort((a, b) => (a.step ?? 0) - (b.step ?? 0));
  return { steps, badLines };
}

// ---------- 런 로드 (s1_points.ply·s2_seeds.json은 절대 로드하지 않음 — 무게) ----------
const S3_FILES = ['s3_views.json', 's3_steps.jsonl', 's3_face_residual.json'];
async function fetchRun(name) {
  const base = `../runs/${name}`;
  const optJson = (fn) => fetch(`${base}/${fn}`).then(r => r.ok ? r.json() : null).catch(() => null);
  const optText = (fn) => fetch(`${base}/${fn}`).then(r => r.ok ? r.text() : null).catch(() => null);
  const mR = await fetch(`${base}/manifest.json`);
  if (!mR.ok) throw new Error(`manifest.json ${mR.status}`);
  const manifest = await mR.json();
  const [viewJ, facesJ, viewsJ, stepsTxt, faceResJ] = await Promise.all([
    optJson('s1_view.json'), optJson('s2_faces.json'),
    optJson('s3_views.json'), optText('s3_steps.jsonl'), optJson('s3_face_residual.json')]);
  const faces = (facesJ && facesJ.faces) || [];
  const faceIdx = {};
  faces.forEach((f, i) => { faceIdx[f.face_id] = i; });
  const d = { name, manifest, view: viewJ || {}, faces, faceIdx,
              s2Missing: facesJ === null, s3: null, s3Missing: [] };
  d.s3Missing = S3_FILES.filter((fn, i) => [viewsJ, stepsTxt, faceResJ][i] === null);
  if (d.s3Missing.length < S3_FILES.length) {   // 부분 존재도 있는 만큼 표시
    const parsed = stepsTxt !== null ? parseJsonl(stepsTxt) : { steps: [], badLines: 0 };
    const perFace = (faceResJ && faceResJ.per_face) || {};
    const resVals = Object.values(perFace).filter(Number.isFinite);
    const byStage = {};
    parsed.steps.forEach((s, i) => {
      const st = String(s.stage ?? '?');
      (byStage[st] = byStage[st] || []).push(i);
    });
    d.s3 = {
      views: (viewsJ && viewsJ.views) || [],
      selectionRule: viewsJ ? (viewsJ.selection_rule ?? null) : null,
      steps: parsed.steps, badLines: parsed.badLines, byStage,
      method: faceResJ ? (faceResJ.method ?? null) : null,
      perFace,
      resStats: resVals.length ? {
        n: resVals.length,
        min: Math.min(...resVals), max: Math.max(...resVals),
        mean: resVals.reduce((a, b) => a + b, 0) / resVals.length,
      } : null,
    };
  }
  // bbox — 카메라 맞춤 (면 지오메트리 기준)
  const bb = { mn: [1e18, 1e18, 1e18], mx: [-1e18, -1e18, -1e18] };
  faces.forEach(f => (f.poly3d || []).forEach(p => {
    for (let k = 0; k < 3; k++) {
      if (p[k] < bb.mn[k]) bb.mn[k] = p[k];
      if (p[k] > bb.mx[k]) bb.mx[k] = p[k];
    }
  }));
  d.bb = faces.length ? bb : { mn: [0, 0, 0], mx: [10, 10, 10] };
  return d;
}

// ---------- 씬 구축 — 면별 잔차 히트맵 (s2_faces 지오메트리 재사용) ----------
function resNorm(d, v) {
  const st = d.s3 && d.s3.resStats;
  if (!st || !Number.isFinite(v)) return null;
  return st.max > st.min ? (v - st.min) / (st.max - st.min) : 0.5;
}
function buildScene(d) {
  clear3d();
  const fp = (d.view || {}).footprint_local;   // 맥락: footprint 윤곽 (페이지 1·2 관행)
  if (fp && fp.length >= 3) {
    for (const z of [d.view.ground_z, d.view.top_z]) {
      if (z === undefined || z === null) continue;
      const g = new THREE.BufferGeometry();
      const pts = [];
      fp.forEach(p => pts.push(p[0], p[1], z));
      g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
      ctxGroup.add(new THREE.LineLoop(g, new THREE.LineBasicMaterial({
        color: COL.ctx, transparent: true, opacity: 0.55 })));
    }
  }
  const perFace = (d.s3 && d.s3.perFace) || {};
  const heat = { tri: [], col: [], triFace: [], wire: [] };
  const ghost = [], domain = [];
  d.faceWire = {};   // face index -> 윤곽 세그먼트 (선택 맥동용)
  d.faces.forEach((f, fi) => {
    const poly = f.poly3d || [];
    if (poly.length < 3) return;
    const wire = [];
    for (let k = 0; k < poly.length; k++) {
      const a = poly[k], b = poly[(k + 1) % poly.length];
      wire.push(a[0], a[1], a[2], b[0], b[1], b[2]);
    }
    d.faceWire[fi] = wire;
    const t = resNorm(d, perFace[f.face_id]);
    if (t !== null && !f.domain) {
      const [r, g, b] = rampRgb(t);
      for (let k = 1; k + 1 < poly.length; k++) {   // 부채꼴 삼각화 (페이지 1 관행)
        heat.tri.push(...poly[0], ...poly[k], ...poly[k + 1]);
        heat.col.push(r, g, b, r, g, b, r, g, b);
        heat.triFace.push(fi);
      }
      heat.wire.push(...wire);
    } else if (f.domain) domain.push(...wire);
    else ghost.push(...wire);
  });
  d.heatMesh = null;
  if (heat.tri.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(heat.tri, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(heat.col, 3));
    d.heatMesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      vertexColors: true, side: THREE.DoubleSide }));
    d.heatMesh.userData = { triFace: Uint32Array.from(heat.triFace) };
    heatGroup.add(d.heatMesh);
    const wg = new THREE.BufferGeometry();
    wg.setAttribute('position', new THREE.Float32BufferAttribute(heat.wire, 3));
    heatGroup.add(new THREE.LineSegments(wg, new THREE.LineBasicMaterial({
      color: COL.border, transparent: true, opacity: 0.55 })));
  }
  d.ghostWire = null; d.domainWire = null;
  if (ghost.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(ghost, 3));
    d.ghostWire = new THREE.LineSegments(g, new THREE.LineBasicMaterial({
      color: COL.ghost, transparent: true, opacity: 0.5 }));
    wireGroup.add(d.ghostWire);
  }
  if (domain.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(domain, 3));
    d.domainWire = new THREE.LineSegments(g, new THREE.LineBasicMaterial({
      color: COL.domain, transparent: true, opacity: 0.4 }));
    wireGroup.add(d.domainWire);
  }
  restyle();
  if (state.lastFit !== d.name) {
    state.lastFit = d.name;
    orbit.target.set((d.bb.mn[0] + d.bb.mx[0]) / 2, (d.bb.mn[1] + d.bb.mx[1]) / 2,
                     (d.bb.mn[2] + d.bb.mx[2]) / 2);
    orbit.r = Math.hypot(d.bb.mx[0] - d.bb.mn[0], d.bb.mx[1] - d.bb.mn[1],
                         d.bb.mx[2] - d.bb.mn[2]) * 1.15 + 5;
    applyOrbit();
  }
}
function restyle() {
  const d = state.run;
  if (!d) return;
  if (d.ghostWire) d.ghostWire.visible = state.showGhost;
  if (d.domainWire) d.domainWire.visible = state.showDomain;
  emptyGroup(selGroup); hiliteMats = [];
  if (state.selFace !== null && d.faceWire && d.faceWire[state.selFace]) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(d.faceWire[state.selFace], 3));
    const mat = new THREE.LineBasicMaterial({ color: COL.selFill, transparent: true, opacity: 1 });
    selGroup.add(new THREE.LineSegments(g, mat));
    hiliteMats.push(mat);
  }
  renderSelBadge(); renderRampLegend();
}

// ---------- 선택 · 픽 ----------
function selectFace(fi) {
  state.selFace = (state.selFace === fi) ? null : fi;
  restyle(); renderPanel();
  const card = $('#facecard');
  if (card) card.scrollIntoView({ block: 'nearest' });
}
const raycaster = new THREE.Raycaster();
function pickAt(e) {
  const d = state.run;
  if (!d || !d.heatMesh || !renderer) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1,
                                -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const hits = raycaster.intersectObject(d.heatMesh, false);
  if (!hits.length) {
    if (state.selFace !== null) { state.selFace = null; restyle(); renderPanel(); }
    return;
  }
  selectFace(d.heatMesh.userData.triFace[hits[0].faceIndex]);
}
function renderSelBadge() {
  const el = $('#selbadge');
  if (!el) return;
  const d = state.run;
  if (!d || state.selFace === null) { el.style.display = 'none'; return; }
  const f = d.faces[state.selFace];
  const v = d.s3 ? d.s3.perFace[f.face_id] : undefined;
  el.style.display = 'block';
  el.innerHTML = `<b style="color:#ffe066">${esc(f.face_id)}</b> ·
    잔차 ${Number.isFinite(v) ? (+v).toFixed(4) : '—'} ·
    ${f.initial_real ? 'F* 실재' : '게이트 0'} · ${(f.area_m2 ?? 0).toFixed(2)} m²
    <span class="note">재클릭·빈 공간·ESC=해제</span>`;
}
function renderRampLegend() {
  const el = $('#ramplegend');
  if (!el) return;
  const d = state.run;
  const st = d && d.s3 && d.s3.resStats;
  if (!st) { el.style.display = 'none'; return; }
  const cssStops = RAMP.map(c => `rgb(${c[0]},${c[1]},${c[2]})`).join(',');
  el.style.display = 'block';
  el.innerHTML = `면별 |잔차| 평균 (근사)<br>
    <span>${st.min.toFixed(3)}</span>
    <span style="display:inline-block;width:90px;height:9px;vertical-align:middle;
      border:1px solid #2e3542;background:linear-gradient(90deg,${cssStops})"></span>
    <span>${st.max.toFixed(3)}</span>`;
}

// ---------- 자동 검사 (체크리스트 ②·③의 근거) ----------
function autoChecks(d) {
  if (!d.s3 || !d.s3.steps.length) return null;
  const nSeedsManifest = ((d.manifest || {}).counts || {}).seeds;
  const res = { wiringOk: true, wiringDetail: [], invOk: true, invDetail: [], steps: d.s3.steps.length };
  for (const s of d.s3.steps) {
    const g = s.grad_norms || {};
    for (const [key] of GRAD_DEF) {
      const v = g[key];
      if (!(Number.isFinite(v) && v > 0)) {
        res.wiringOk = false;
        if (res.wiringDetail.length < 6)
          res.wiringDetail.push(`step ${s.step}: grad_norms.${key}=${v ?? '없음'}`);
      }
    }
    const inv = s.invariants || {};
    const bad = (msg) => {
      res.invOk = false;
      if (res.invDetail.length < 6) res.invDetail.push(`step ${s.step}: ${msg}`);
    };
    if (inv.alpha_binary !== true) bad('alpha_binary != true');
    if (nSeedsManifest !== undefined && inv.n_seeds !== nSeedsManifest)
      bad(`n_seeds ${inv.n_seeds} != manifest ${nSeedsManifest}`);
    if (String(s.stage) === '3a') {   // 3a 전용 기대값 — 후속 구간은 자체 계약으로 확장
      if (inv.delta_frozen !== true) bad('delta_frozen != true (3a)');
      if (!((s.param_step_norm ?? 0) === 0)) bad(`param_step_norm ${s.param_step_norm} != 0 (3a)`);
      if ((s.delta_hat || []).some(v => v !== 0)) bad(`delta_hat ${JSON.stringify(s.delta_hat)} != 0 (3a)`);
    }
  }
  return res;
}

// ---------- 체크리스트 (4항 — 참고 기준, 엄격 합불 아님: 판독 기록 2026-08-27 방침) ----------
function renderChecklist() {
  const d = state.run;
  if (!d) { $('#checkstrip').innerHTML = '<span class="note">런 없음</span>'; return; }
  const na = (t) => `<span class="badge na">${t}</span>`;
  let b2 = na('S3a 없음'), b3 = na('S3a 없음');
  const ck = autoChecks(d);
  if (ck) {
    b2 = `<span class="badge ${ck.wiringOk ? 'good' : 'bad'}">${ck.wiringOk ? '3군 전부 > 0' : '0/결측 있음'}</span>`;
    b3 = `<span class="badge ${ck.invOk ? 'good' : 'bad'}">${ck.invOk ? '전부 참' : '위반'}</span>`;
  }
  const sd = (d.manifest || {}).s3_def || {};
  $('#checkstrip').innerHTML = `
    <div class="chkrow">
      <span class="chkitem"><b>①</b> 렌더-사진 정렬이 실루엣 수준에서 겹침 ${na('육안')}</span>
      <span class="chkitem"><b>②</b> grad_norms 3군(δ/평면/색) 전부 0이 아님 — 배선 증거 ${b2}</span>
      <span class="chkitem"><b>③</b> 불변량 전부 참(n_seeds 일치·α 이진·δ 동결·이동량 0) ${b3}</span>
      <span class="chkitem"><b>④</b> SYNTH residual이 구조적으로 근소 ${na('육안')}</span>
    </div>
    <div class="chkrow meta">
      <span><span class="badge prop">참고 기준</span> 엄격 런별 합불 아님 — 판독 기록 2026-08-27 방침(발견 기록으로 갈음).</span>
      <span>3a 계약: 최적화 0스텝 + backward 1회(가중치 갱신 없음) · δ 렌더 인자 배선·값 ${JSON.stringify(sd.delta_value ?? [0, 0, 0])} 고정 ·
        색 ${esc(sd.color || 'neutral-gray')} · α_g=|o_a−o_b| 유도 · densification/pruning 금지(수명 규칙 ①) ·
        렌더러 ${esc(sd.renderer || 'gsplat')}(미분 가능 렌더링)</span>
    </div>`;
}

// ---------- 사이클 타임라인 — 구간 배지 + 스텝 마커 (스텝·구간 다수 전제) ----------
function renderTimeline() {
  const d = state.run;
  const el = $('#timeline');
  if (!d) { el.innerHTML = '<span class="tlabel">런 없음</span>'; return; }
  const byStage = (d.s3 && d.s3.byStage) || {};
  // 등록부 밖의 구간이 데이터에 있으면 뒤에 덧붙인다 (페이지가 구현과 함께 자란다)
  const known = new Set(STAGES.map(s => s.id));
  const extra = Object.keys(byStage).filter(id => !known.has(id)).sort()
    .map(id => ({ id, label: id, desc: '(등록부 밖 구간)' }));
  let h = '<span class="tlabel">사이클</span>';
  for (const sg of [...STAGES, ...extra]) {
    const idxs = byStage[sg.id] || [];
    const on = idxs.length > 0;
    const chips = idxs.map(i => {
      const s = d.s3.steps[i];
      return `<span class="stepchip ${state.selStep === i ? 'sel' : ''}" data-step="${i}"
        title="step ${s.step} · total ${fmtNum((s.losses || {}).total)}">${s.step}</span>`;
    }).join('');
    h += `<div class="seg ${on ? 'on' : 'off'}">
      <div class="seghead">${esc(sg.label)}${on ? ` <span class="note">스텝 ${idxs.length}</span>` : ''}</div>
      ${on ? chips : '<span class="planned">예정</span>'}
      <div class="segdesc">${esc(sg.desc)}</div></div>`;
  }
  el.innerHTML = h;
  el.querySelectorAll('.stepchip').forEach(c => {
    c.onclick = () => { state.selStep = +c.dataset.step; renderTimeline(); renderPanel(); };
  });
}

// ---------- SVG 차트 (직접 라벨 + <title> 툴팁 + 인접 표가 항상 동반) ----------
function fmtNum(v, n = 4) {
  if (v === null || v === undefined || Number.isNaN(+v)) return '—';
  const a = Math.abs(+v);
  return (a !== 0 && (a < 1e-3 || a >= 1e5)) ? (+v).toExponential(2) : (+v).toFixed(n);
}
function lossSeries(steps) {
  const keys = new Set();
  steps.forEach(s => Object.keys(s.losses || {}).forEach(k => {
    if (Number.isFinite((s.losses || {})[k])) keys.add(k);
  }));
  const order = [...LOSS_ORDER.filter(k => keys.has(k)),
                 ...[...keys].filter(k => !LOSS_ORDER.includes(k)).sort()];
  let extraUsed = 0;
  return order.map(k => {
    let col = LOSS_COL[k];
    if (!col) col = extraUsed < LOSS_EXTRA.length ? LOSS_EXTRA[extraUsed++] : null;  // 소진 시 표에만
    return { key: k, col };
  });
}
function lossCurveSvg(d) {
  const steps = d.s3.steps;
  if (!steps.length) return '<p class="note">스텝 없음</p>';
  const series = lossSeries(steps).filter(s => s.col);
  const W = 408, H = 132, L = 46, R = 70, T = 10, B = 20;
  const xs = steps.map(s => s.step ?? 0);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let vmax = 0;
  steps.forEach(s => series.forEach(sr => {
    const v = (s.losses || {})[sr.key];
    if (Number.isFinite(v)) vmax = Math.max(vmax, v);
  }));
  if (vmax === 0) vmax = 1;
  const X = (x) => x1 > x0 ? L + (x - x0) / (x1 - x0) * (W - L - R) : (L + (W - L - R) / 2);
  const Y = (v) => T + (1 - v / vmax) * (H - T - B);
  let h = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="스텝 범위 항별 손실 곡선">
    <line x1="${L}" y1="${Y(0)}" x2="${W - R}" y2="${Y(0)}" stroke="#2e3542"/>
    <line x1="${L}" y1="${T}" x2="${L}" y2="${Y(0)}" stroke="#2e3542"/>
    <text x="${L - 4}" y="${Y(0) + 3}" text-anchor="end">0</text>
    <text x="${L - 4}" y="${T + 8}" text-anchor="end">${fmtNum(vmax, 3)}</text>
    <text x="${X(x0)}" y="${H - 6}" text-anchor="middle">${x0}</text>
    ${x1 > x0 ? `<text x="${X(x1)}" y="${H - 6}" text-anchor="middle">${x1}</text>` : ''}`;
  const labels = [];
  series.forEach((sr) => {
    const pts = steps.map(s => [s.step ?? 0, (s.losses || {})[sr.key]])
      .filter(p => Number.isFinite(p[1]));
    if (!pts.length) return;
    if (pts.length > 1)
      h += `<polyline fill="none" stroke="${sr.col}" stroke-width="2"
        points="${pts.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')}"/>`;
    for (const p of pts)
      h += `<circle class="stepdot" cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="3.5"
        fill="${sr.col}"><title>${esc(sr.key)} @ step ${p[0]} = ${fmtNum(p[1])}</title></circle>`;
    const last = pts[pts.length - 1];
    labels.push({ x: X(last[0]) + 6, y: Y(last[1]) + 3, col: sr.col, key: sr.key });
  });
  // 끝점 직접 라벨 — 겹침 해소(위→아래 정렬 후 최소 10px 간격 강제)
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++)
    if (labels[i].y - labels[i - 1].y < 10) labels[i].y = labels[i - 1].y + 10;
  const overshoot = labels.length ? labels[labels.length - 1].y - (H - 4) : 0;
  if (overshoot > 0) {
    for (const lb of labels) lb.y -= overshoot;
    for (let i = labels.length - 2; i >= 0; i--)
      if (labels[i + 1].y - labels[i].y < 10) labels[i].y = labels[i + 1].y - 10;
  }
  for (const lb of labels)
    h += `<text x="${lb.x.toFixed(1)}" y="${lb.y.toFixed(1)}"
      style="fill:${lb.col}">${esc(lb.key)}</text>`;
  return h + '</svg>';
}
function gradBarsHtml(step) {
  const g = (step || {}).grad_norms || {};
  const vals = GRAD_DEF.map(([k]) => Number.isFinite(g[k]) ? g[k] : null);
  const vmax = Math.max(...vals.map(v => v ?? 0), 1e-30);
  let h = '<table>';
  GRAD_DEF.forEach(([key, label, col], i) => {
    const v = vals[i];
    const w = v === null ? 0 : Math.max(v / vmax * 100, v > 0 ? 2 : 0);
    h += `<tr><td class="l" style="width:44%">${esc(label)}</td>
      <td class="l" style="width:34%"><span title="grad_norms.${esc(key)} = ${fmtNum(v)}"
        style="display:inline-block;height:10px;width:${w.toFixed(1)}%;background:${col};
        border-radius:2px;vertical-align:middle"></span></td>
      <td>${fmtNum(v)} ${v !== null && v > 0 ? '' : '<span class="badge bad">0/결측 — 배선 끊김 의심</span>'}</td></tr>`;
  });
  return h + '</table>';
}
function psnrBarsSvg(step) {
  const ps = (step || {}).views_psnr || {};
  const ids = Object.keys(ps);
  if (!ids.length) return '';
  const n = ids.length, bw = Math.min(22, Math.max(8, Math.floor(360 / n) - 3));
  const W = Math.min(408, n * (bw + 3) + 40), H = 96, B = 14, T = 12;
  const vmax = Math.max(...ids.map(id => ps[id]).filter(Number.isFinite), 1);
  let h = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="뷰별 PSNR 분포">
    <line x1="30" y1="${H - B}" x2="${W - 4}" y2="${H - B}" stroke="#2e3542"/>
    <text x="26" y="${T + 6}" text-anchor="end">${vmax.toFixed(1)}</text>
    <text x="26" y="${H - B + 3}" text-anchor="end">0</text>`;
  ids.forEach((id, i) => {
    const v = ps[id];
    const bh = Number.isFinite(v) ? (v / vmax) * (H - T - B) : 0;
    const x = 32 + i * (bw + 3), sel = state.selView === id;
    h += `<rect class="vbar" data-vid="${escAttr(id)}" x="${x}" y="${(H - B - bh).toFixed(1)}"
      width="${bw}" height="${bh.toFixed(1)}" fill="#8ecbff" rx="2"
      ${sel ? 'stroke="#ffe066" stroke-width="2"' : ''}>
      <title>${esc(id)} · PSNR ${fmtNum(v, 2)} dB</title></rect>`;
    if (sel) h += `<text x="${x + bw / 2}" y="${Math.max(T, H - B - bh - 3).toFixed(1)}"
      text-anchor="middle" style="fill:#ffe066">${fmtNum(v, 1)}</text>`;
  });
  return h + '</svg><div class="note">막대 클릭 = 뷰 선택 (단일 계열 — PSNR dB, 0 기준)</div>';
}

// ---------- 패널 카드 ----------
function reading() {
  return state.reading[state.runName] ||
    (state.reading[state.runName] = { verdict: null, memo: '', sign: '' });
}
function invariantBadges(d, step) {
  const inv = (step || {}).invariants || {};
  const nSeeds = ((d.manifest || {}).counts || {}).seeds;
  const is3a = String((step || {}).stage) === '3a';
  const B = (ok, txt) => `<span class="badge ${ok ? 'good' : 'bad'}">${txt}</span>`;
  const items = [
    B(nSeeds === undefined || inv.n_seeds === nSeeds,
      `시드 수 ${inv.n_seeds ?? '—'} ${nSeeds === undefined ? '(manifest 없음)' : (inv.n_seeds === nSeeds ? '= manifest' : `≠ manifest ${nSeeds}`)}`),
    B(inv.alpha_binary === true, `α=|o_a−o_b| 이진 ${inv.alpha_binary === true ? '유지' : '위반'}`),
  ];
  if (is3a) {
    items.push(B(inv.delta_frozen === true, `δ 동결 ${inv.delta_frozen === true ? '유지' : '위반'}`));
    items.push(B((step.param_step_norm ?? 0) === 0, `이동량 노름 ${fmtNum(step.param_step_norm ?? 0, 1)}`));
    items.push(B(!((step.delta_hat || []).some(v => v !== 0)),
      `δ̂ [${(step.delta_hat || []).map(v => fmtNum(v, 2)).join(', ')}]`));
  } else {
    items.push(`<span class="badge na">δ 동결 ${inv.delta_frozen === undefined ? '—' : inv.delta_frozen} · 이동량 ${fmtNum(step.param_step_norm, 3)} (구간 ${esc(step.stage)} 계약은 추후)</span>`);
  }
  return items.join(' ');
}
function s3DefCard(d) {
  const sd = (d.manifest || {}).s3_def || {};
  const s3 = d.s3;
  return `<div class="card">
    <table>
      <tr><td class="k">구간</td><td class="l">${esc(sd.stage ?? '—')} (렌더-온리 — 최적화 0스텝 + backward 1회)</td></tr>
      <tr><td class="k">δ 배선</td><td class="l">${sd.delta_wired === true ? '렌더 인자로 배선됨' : (sd.delta_wired === undefined ? '—' : '<span class="bad">배선 안 됨!</span>')} · 값 ${JSON.stringify(sd.delta_value ?? '—')} 고정</td></tr>
      <tr><td class="k">색 / 렌더러</td><td class="l">${esc(sd.color ?? '—')} / ${esc(sd.renderer ?? '—')} · optimizer=${esc(sd.optimizer ?? '—')}</td></tr>
      <tr><td class="k">뷰 수</td><td class="l">${sd.n_views ?? (s3 ? s3.views.length : '—')}</td></tr>
      <tr><td class="k">뷰 선정 규칙</td><td class="l">${esc(s3 && s3.selectionRule ? (typeof s3.selectionRule === 'string' ? s3.selectionRule : JSON.stringify(s3.selectionRule)) : '—')}</td></tr>
    </table>
    ${s3 && s3.badLines ? `<div class="err">s3_steps.jsonl 파싱 실패 행 ${s3.badLines}개</div>` : ''}</div>`;
}
function stepLossCard(d, step) {
  const losses = (step || {}).losses || {};
  const series = lossSeries(d.s3.steps);
  const rows = series.map(sr => `<tr>
    <td class="l">${sr.col ? `<span style="display:inline-block;width:9px;height:9px;background:${sr.col};border-radius:2px;margin-right:4px;vertical-align:middle"></span>` : ''}${esc(sr.key)}</td>
    <td>${fmtNum(losses[sr.key])}</td></tr>`).join('');
  return `<div class="card">
    <table><tr><th class="l">항 (가용 항 자동 표시 — depth/실루엣 추가 시 자동)</th><th>값</th></tr>${rows}</table>
    <div style="margin-top:5px">${lossCurveSvg(d)}</div>
    <div class="note">스텝 범위 손실 곡선 — 스텝 1개면 점. 축: X=스텝, Y=손실(0 기준).</div></div>`;
}
function viewsCard(d, step) {
  const s3 = d.s3;
  if (!s3.views.length) return '<p class="note">s3_views.json에 뷰 없음</p>';
  const vsel = state.selView;
  const v = s3.views.find(x => x.view_id === vsel) || s3.views[0];
  const psnr = ((step || {}).views_psnr || {})[v.view_id];
  const tile = (kind) => `../runs/${encodeURIComponent(state.runName)}/s3_tiles/${encodeURIComponent(v.view_id)}/${kind}.png`;
  const opts = s3.views.map(x =>
    `<option value="${escAttr(x.view_id)}" ${x.view_id === v.view_id ? 'selected' : ''}>${esc(x.view_id)}</option>`).join('');
  return `<div class="legend">뷰 <select id="viewsel">${opts}</select>
      <span class="note">${esc(v.image_ref || '')} · ${v.width ?? '?'}×${v.height ?? '?'}${psnr !== undefined ? ` · PSNR ${fmtNum(psnr, 2)} dB` : ''}</span></div>
    <div class="tiles">
      <figure><img src="${tile('photo')}" alt="사진" loading="lazy"
        onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'err',textContent:'photo.png 없음'}))">
        <figcaption>사진 (다운스케일 ≤640)</figcaption></figure>
      <figure><img src="${tile('render')}" alt="렌더" loading="lazy"
        onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'err',textContent:'render.png 없음'}))">
        <figcaption>렌더 (gsplat · S2 상태)</figcaption></figure>
      <figure><img src="${tile('residual')}" alt="잔차" loading="lazy"
        onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'err',textContent:'residual.png 없음'}))">
        <figcaption>|사진−렌더| 그레이 히트</figcaption></figure>
    </div>
    <div style="margin-top:5px">${psnrBarsSvg(step)}</div>`;
}
function faceResidualCard(d) {
  const s3 = d.s3, st = s3.resStats;
  let h = `<div class="card">
    <div class="note caption" style="margin-bottom:4px">근사 방식(숨기지 않음): ${esc(s3.method || '— method 명기 없음')}</div>`;
  if (!st) h += '<p class="note">per_face 잔차 값 없음</p>';
  else h += `<table>
      <tr><td class="k">잔차 보유 면</td><td>${st.n} / ${d.faces.length}</td></tr>
      <tr><td class="k">min · mean · max</td><td>${fmtNum(st.min)} · ${fmtNum(st.mean)} · ${fmtNum(st.max)}</td></tr>
    </table>
    <div class="note" style="margin-top:3px">3D 면 색 = 낮음(어두움)→높음(밝은 앰버) 램프 —
      s2_faces 지오메트리 재사용. 면 클릭 = 카드 + 페이지 2·1 점프.</div>`;
  h += '</div>';
  if (state.selFace !== null) {
    const f = d.faces[state.selFace];
    const v = s3.perFace[f.face_id];
    const p2 = (q) => `../viewer_p2/?run=${encodeURIComponent(state.runName)}${q}`;
    const planeRows = (f.s1_plane_ids || []).map(pid =>
      `<a href="../viewer_p1/?run=${encodeURIComponent(state.runName)}&plane=${encodeURIComponent(pid)}"
        style="color:#8ecbff">${esc(pid)} ↗페이지 1</a>`).join(' · ');
    h += `<div class="card" id="facecard"><b style="color:#ffe066">${esc(f.face_id)}</b>
      ${f.initial_real ? '<span class="badge good">F* 초기 실재</span>' : '<span class="badge na">게이트 0</span>'}
      <table style="margin-top:4px">
        <tr><td class="k">면별 |잔차| 평균</td><td>${fmtNum(v)}</td></tr>
        <tr><td class="l">면적</td><td>${fmtNum(f.area_m2, 2)} m²</td></tr>
        <tr><td class="l">양쪽 셀</td><td class="l">
          ${f.cell_a ? `<a href="${p2('&cell=' + encodeURIComponent(f.cell_a))}" style="color:#8ecbff">${esc(f.cell_a)} ↗</a>` : '—'} /
          ${f.cell_b ? `<a href="${p2('&cell=' + encodeURIComponent(f.cell_b))}" style="color:#8ecbff">${esc(f.cell_b)} ↗</a>` : '<span class="note">도메인</span>'}</td></tr>
        <tr><td class="l">소속 평면</td><td class="l">${planeRows || '—'}</td></tr>
        <tr><td class="l">페이지 2에서 이 면</td><td class="l">
          <a href="${p2('&face=' + encodeURIComponent(f.face_id))}" style="color:#8ecbff">셀/면 화면으로 점프 ↗</a></td></tr>
      </table></div>`;
  }
  return h;
}
function readingCard(d) {
  const rd = reading();
  return `<div class="card">
      <div class="legend">
        <label><input type="radio" name="verdict" value="합격" ${rd.verdict === '합격' ? 'checked' : ''}> 합격</label>
        <label><input type="radio" name="verdict" value="불합격" ${rd.verdict === '불합격' ? 'checked' : ''}> 불합격</label>
        <label><input type="radio" name="verdict" value="보류" ${rd.verdict === '보류' ? 'checked' : ''}> 보류</label>
      </div>
      <textarea id="memo" rows="4" placeholder="판독 메모 — 체크리스트 4항은 참고 기준(2026-08-27 방침), 발견 기록 중심으로">${esc(rd.memo)}</textarea>
      <div style="margin-top:5px">서명란 <input type="text" id="sign" placeholder="리뷰어 김휘영 서명" value="${esc(rd.sign)}" style="width:180px">
        <button class="small" id="dlbtn">판독 기록 JSON 다운로드</button></div>
      <div class="note" style="margin-top:4px">파일로만 저장 — 서버 전송 없음. scientific_verdict: null 유지(사람 판정은 별도 승인 문서).</div>
    </div>`;
}

// ---------- 패널 ----------
function renderPanel() {
  const d = state.run;
  if (!d) { $('#panel').innerHTML = '<p class="note">런을 선택하세요.</p>'; return; }
  let h = `<div class="note caption">페이지 3 = 공동 최적화(연속 구간) — 사이클 타임라인의 구간
    3a(렌더-온리)부터. 지금 구간의 물음: "광도 잔차가 δ·평면·색까지 실제로 흘러오는가"(배선 증거).
    이산 라운드·판정 기록은 다음 차수.</div>`;
  if (!d.s3) {
    h += `<div class="err">S3a 파일 없음: ${d.s3Missing.map(esc).join(', ')}<br>
      writer가 S3a 산출물(s3_views/s3_steps/s3_face_residual/s3_tiles)을 아직 생성하지 않았다 —
      생성 후 새로고침. ${d.faces.length ? 'S2 면 지오메트리를 고스트 와이어로만 표시 중.' : ''}</div>`;
    if (d.s2Missing) h += '<div class="err">s2_faces.json도 없음 — 3D 표시 불가(페이지 2 writer 선행).</div>';
  } else {
    if (d.s3Missing.length)
      h += `<div class="err">S3a 일부 파일 없음: ${d.s3Missing.map(esc).join(', ')} — 있는 만큼 표시.</div>`;
    const step = state.selStep !== null ? d.s3.steps[state.selStep] : null;
    h += `<h2>S3a 정의 <span class="note">(manifest.s3_def + s3_views)</span></h2>${s3DefCard(d)}`;
    if (!step) {
      h += '<p class="note">타임라인에서 스텝을 클릭하세요.</p>';
    } else {
      h += `<h2>스텝 ${step.step} (구간 ${esc(step.stage)}) — 항별 손실</h2>${stepLossCard(d, step)}
        <h2>그라디언트 노름 3군 <span class="badge eval">배선 증거</span></h2>
        <div class="card">${gradBarsHtml(step)}
          <div class="note" style="margin-top:3px">최적화 0스텝·backward 1회(가중치 갱신 없음) —
            광도 잔차가 δ/평면/색 변수군까지 실제로 흘러오는가의 증거. 전부 0이 아니어야 함(체크 ②).</div></div>
        <h2>불변량 배지</h2>
        <div class="card">${invariantBadges(d, step)}
          <div class="note" style="margin-top:4px">n_seeds == manifest counts.seeds(전수 유지 — 수명 규칙 ①) ·
            α 이진 유도 · δ 동결(3a) · param_step_norm=0(3a).</div></div>
        <h2>뷰 — 사진 / 렌더 / 잔차 + PSNR 분포</h2>
        <div class="card">${viewsCard(d, step)}</div>`;
    }
    h += `<h2>면별 잔차 히트맵 <span class="note">(s3_face_residual — 근사)</span></h2>
      ${faceResidualCard(d)}
      <div class="legend">
        <label><input type="checkbox" id="ghostTgl" ${state.showGhost ? 'checked' : ''}>
          잔차 없는 면 와이어</label>
        <label><input type="checkbox" id="domainTgl" ${state.showDomain ? 'checked' : ''}>
          도메인 외피</label>
      </div>`;
  }
  h += `<h2>판독 기록 (리뷰어: 김휘영)</h2>${readingCard(d)}`;
  $('#panel').innerHTML = h;
  bindPanel();
}
function bindPanel() {
  const on = (id, ev, fn) => { const el = $(id); if (el) el[ev] = fn; };
  on('#ghostTgl', 'onchange', () => { state.showGhost = $('#ghostTgl').checked; restyle(); });
  on('#domainTgl', 'onchange', () => { state.showDomain = $('#domainTgl').checked; restyle(); });
  on('#viewsel', 'onchange', () => { state.selView = $('#viewsel').value; renderPanel(); });
  document.querySelectorAll('#panel svg .vbar').forEach(r => {
    r.onclick = () => { state.selView = r.dataset.vid; renderPanel(); };
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
  const ck = autoChecks(d);
  const now = new Date().toISOString();
  const step = (d.s3 && state.selStep !== null) ? d.s3.steps[state.selStep] : null;
  const obj = {
    schema: 'phd_s3_verify_p3_reading_v1',
    page: 'p3_joint_opt_continuous',
    run: state.runName,
    bundle: {
      schema: d.manifest.schema, bundle_name: d.manifest.bundle_name,
      stage: d.manifest.stage, dataset: d.manifest.dataset,
      counts: d.manifest.counts, s3_def: d.manifest.s3_def ?? null,
    },
    checklist: [
      '① 렌더-사진 정렬이 실루엣 수준에서 겹침 (육안)',
      '② grad_norms 3군(δ/평면/색) 전부 0이 아님 (자동 — 배선 증거)',
      '③ 불변량 전부 참: n_seeds 일치·α 이진·δ 동결·param_step_norm 0 (자동)',
      '④ SYNTH residual이 구조적으로 근소 (육안)',
    ],
    checklist_policy: '참고 기준 — 엄격 런별 합불 아님 (판독 기록 2026-08-27 방침, 발견 기록으로 갈음)',
    auto: d.s3 ? {
      steps: d.s3.steps.length,
      stages: Object.keys(d.s3.byStage),
      wiring_ok: ck ? ck.wiringOk : null, wiring_detail: ck ? ck.wiringDetail : [],
      invariants_ok: ck ? ck.invOk : null, invariants_detail: ck ? ck.invDetail : [],
      selected_step: step ? { step: step.step, stage: step.stage, losses: step.losses,
                              grad_norms: step.grad_norms, param_step_norm: step.param_step_norm } : null,
      n_views: d.s3.views.length,
      face_residual: { method: d.s3.method, stats: d.s3.resStats },
      jsonl_bad_lines: d.s3.badLines,
      s3_missing: d.s3Missing,
    } : { s3_missing: d.s3Missing },
    verdict: rd.verdict, memo: rd.memo,
    reviewer: '김휘영', signature: rd.sign,
    saved_at: now, transport: 'file-download-only',
    not_official: true, scientific_verdict: null,
  };
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)],
                                        { type: 'application/json' }));
  a.download = `p3_reading_${state.runName}_${now.replace(/[:.]/g, '-')}.json`;
  a.click();
}

// ---------- 헤더 ----------
function renderHeader() {
  const d = state.run;
  if (!d) { $('#countsline').textContent = '런 없음 — writer(s1+s2+s3a 번들)를 먼저 실행'; return; }
  const c = d.manifest.counts || {};
  const sd = d.manifest.s3_def || {};
  const off = d.manifest.local_offset || [];
  $('#countsline').textContent =
    `${d.manifest.bundle_name || state.runName} · stage=${d.manifest.stage || 's1'}` +
    (d.s3 ? ` · 구간 ${sd.stage || '3a'} · 스텝 ${d.s3.steps.length} · 뷰 ${sd.n_views ?? d.s3.views.length}` +
            ` · 렌더러 ${sd.renderer || 'gsplat'}`
          : ' · S3a 없음(빈 상태)') +
    ` · 면 ${c.faces ?? d.faces.length} · 시드 ${c.seeds ?? '?'}` +
    ` · CRS ${d.manifest.crs || '?'} (offset −[${off.map(x => (+x).toFixed(1)).join(', ')}])`;
  $('#hud').textContent = `${state.runName} — 좌드래그 회전 · 우드래그 이동 · 휠 줌 · ` +
    `면 클릭=잔차 카드(페이지 2·1 점프) · 재클릭·빈 공간·ESC=해제 · ` +
    `면 색 = |잔차| 램프(어두움→밝은 앰버) · 타임라인 스텝 클릭=손실·grad·뷰 타일`;
}

// ---------- 런 전환 ----------
async function loadRun(name) {
  state.runName = name; state.selStep = null; state.selView = null; state.selFace = null;
  $('#panel').innerHTML = `<p class="note">${esc(name)} 로딩 중…</p>`;
  try {
    if (!state.cache[name]) state.cache[name] = await fetchRun(name);
  } catch (e) {
    $('#panel').innerHTML =
      `<div class="err">런 ${esc(name)} 로드 실패: ${esc(e.message)}<br>
       writer가 s1/s2/s3a 번들을 아직 생성하지 않았을 수 있다.</div>`;
    $('#checkstrip').innerHTML = '<span class="note">—</span>';
    $('#timeline').innerHTML = '<span class="tlabel">—</span>';
    return;
  }
  state.run = state.cache[name];
  const d = state.run;
  if (d.s3 && d.s3.steps.length) {          // 기본 선택: 마지막 스텝 + 첫 뷰
    state.selStep = d.s3.steps.length - 1;
    state.selView = d.s3.views.length ? d.s3.views[0].view_id : null;
  }
  buildScene(d);
  renderHeader();
  renderChecklist();
  renderTimeline();
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
                              : ds.stable_id ? ` (${ds.stable_id})` : '') +
                    (r.s3_ready === false ? ' [S3a 없음]' : '');
    sel.appendChild(o);
  });
  sel.onchange = () => loadRun(sel.value);
  const qRun = new URLSearchParams(location.search).get('run');
  const first = state.runs.some(r => r.name === qRun) ? qRun
              : (state.runs.length ? state.runs[0].name : null);
  if (first) { sel.value = first; loadRun(first); }
  else {
    $('#countsline').textContent = '런 0개 — writer(s1+s2+s3a 번들) 실행 후 build_verify_pages.py 재실행';
    $('#panel').innerHTML = '<p class="note">runs/ 아래에 번들이 없다.</p>';
    $('#checkstrip').innerHTML = '<span class="note">—</span>';
    $('#timeline').innerHTML = '<span class="tlabel">—</span>';
  }
  resize();
}).catch(e => {
  $('#panel').innerHTML = `<div class="err">viewer manifest 로드 실패: ${esc(e.message)} —
    build_verify_pages.py로 뷰어를 번들 루트에 배포한 뒤 8885로 서빙해야 한다.</div>`;
});
resize();
applyOrbit();
