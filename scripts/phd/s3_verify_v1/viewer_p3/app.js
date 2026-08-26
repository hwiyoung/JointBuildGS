// S3 검증 페이지 3 — 공동 최적화(연속 구간) 정적 뷰어. NOT OFFICIAL · scientific_verdict: null.
// 데이터 계약: phd_s3_verify_s3a_v1 — ../runs/<name>/{manifest.json, s1_view.json, s2_faces.json}
// + S3a 추가분 {s3_views.json, s3_steps.jsonl, s3_face_residual.json, s3_tiles/<view_id>/*.png}
// + S3b 추가분(phd_s3_verify_s3b_v1 — 색만 학습·기하 동결): s3_steps.jsonl에 stage:"3b" 행 추가
//   (3a 행 보존), 체크포인트 행에만 views_psnr·color_stats, 체크포인트 타일은
//   s3_tiles/s<step>/<view_id>/{render,residual}.png (photo는 3a 타일 재사용),
//   s3_face_residual_final.json(step0=3a 것과 같은 근사·null 규약), manifest.s3b_def.
// 3차 내부 단계(계획 문서 개정 주석 2026-08-27): 3a 렌더-온리(0 최적화 스텝 — 배선 자체 검증,
// backward 1회로 grad_norms만 기록) → 3b 색 → 3c δ → 3d 평면. 화면 축 = 사이클 타임라인 하나,
// 미구현 구간은 회색 "예정" — 페이지가 구현과 함께 자란다(스텝·구간 다수 전제, 수백 스텝은 씨닝).
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
// grad_norms 3군 — 배선 증거 (δ/평면/색). 3b에서는 "색 수렴 중 기하 압력 변화" 관측 축.
const GRAD_DEF = [['delta', 'δ (P⁰⊕δ 강체 보정)', '#ff9a3c'],
                  ['planes', '평면 (미세조정 — 3a·3b 동결)', '#4a9eff'],
                  ['colors', '색 (3a 상수 · 3b 학습 변수)', '#7ee787']];
// color_stats 2계열 — 색 분화 타임랩스 (3b 체크포인트 행)
const CSTAT_DEF = [['mean_saturation', '평균 채도', '#cf9bff'],
                   ['color_var', '색 분산', '#2ee6c8']];
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
  logYLoss: false,   // 손실 곡선 로그 y 옵션
  logYGrad: false,   // grad 곡선 로그 y 옵션
  cmpPrev: false,    // 체크포인트 렌더 이전/현재 나란히 비교
  heatMode: 'init',  // 면 히트맵: 'init'(3a step0) | 'final'(3b) | 'diff'(final−init)
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
function resStatsOf(vals) {
  const v = vals.filter(Number.isFinite);
  return v.length ? { n: v.length, min: Math.min(...v), max: Math.max(...v),
                      mean: v.reduce((a, b) => a + b, 0) / v.length } : null;
}
async function fetchRun(name) {
  const base = `../runs/${name}`;
  const optJson = (fn) => fetch(`${base}/${fn}`).then(r => r.ok ? r.json() : null).catch(() => null);
  const optText = (fn) => fetch(`${base}/${fn}`).then(r => r.ok ? r.text() : null).catch(() => null);
  const mR = await fetch(`${base}/manifest.json`);
  if (!mR.ok) throw new Error(`manifest.json ${mR.status}`);
  const manifest = await mR.json();
  const [viewJ, facesJ, viewsJ, stepsTxt, faceResJ, faceResFinJ] = await Promise.all([
    optJson('s1_view.json'), optJson('s2_faces.json'),
    optJson('s3_views.json'), optText('s3_steps.jsonl'), optJson('s3_face_residual.json'),
    optJson('s3_face_residual_final.json')]);   // S3b — 없으면 null (3a-only 런 허용)
  const faces = (facesJ && facesJ.faces) || [];
  const faceIdx = {};
  faces.forEach((f, i) => { faceIdx[f.face_id] = i; });
  const d = { name, manifest, view: viewJ || {}, faces, faceIdx,
              s2Missing: facesJ === null, s3: null, s3Missing: [] };
  d.s3Missing = S3_FILES.filter((fn, i) => [viewsJ, stepsTxt, faceResJ][i] === null);
  if (d.s3Missing.length < S3_FILES.length) {   // 부분 존재도 있는 만큼 표시
    const parsed = stepsTxt !== null ? parseJsonl(stepsTxt) : { steps: [], badLines: 0 };
    const perFace = (faceResJ && faceResJ.per_face) || {};
    const perFaceFinal = (faceResFinJ && faceResFinJ.per_face) || null;
    const byStage = {};
    parsed.steps.forEach((s, i) => {
      const st = String(s.stage ?? '?');
      (byStage[st] = byStage[st] || []).push(i);
    });
    // 체크포인트 집합 — views_psnr 보유 행 ∪ manifest.s3b_def.checkpoints (3b)
    const ckpt = {};
    for (const [st, idxs] of Object.entries(byStage)) {
      const set = new Set();
      idxs.forEach(i => { if (parsed.steps[i].views_psnr) set.add(parsed.steps[i].step ?? 0); });
      if (st === '3b') ((manifest.s3b_def || {}).checkpoints || []).forEach(s => set.add(+s));
      ckpt[st] = set;
    }
    // init/final 공유 스케일 — 토글 비교가 같은 램프에서 읽히도록
    const initVals = Object.values(perFace);
    const bothVals = perFaceFinal ? initVals.concat(Object.values(perFaceFinal)) : initVals;
    const diffVals = [];
    if (perFaceFinal)
      for (const [fid, v0] of Object.entries(perFace)) {
        const v1 = perFaceFinal[fid];
        if (Number.isFinite(v0) && Number.isFinite(v1)) diffVals.push(v1 - v0);
      }
    d.s3 = {
      views: (viewsJ && viewsJ.views) || [],
      selectionRule: viewsJ ? (viewsJ.selection_rule ?? null) : null,
      steps: parsed.steps, badLines: parsed.badLines, byStage, ckpt,
      method: faceResJ ? (faceResJ.method ?? null) : null,
      perFace,
      resStats: resStatsOf(initVals),
      perFaceFinal,
      finalStep: faceResFinJ ? (faceResFinJ.step ?? null) : null,
      finalMethod: faceResFinJ ? (faceResFinJ.method ?? null) : null,
      resStatsFinal: perFaceFinal ? resStatsOf(Object.values(perFaceFinal)) : null,
      resStatsShared: resStatsOf(bothVals),
      diffStats: diffVals.length ? {
        n: diffVals.length, maxAbs: Math.max(...diffVals.map(Math.abs), 1e-12),
        mean: diffVals.reduce((a, b) => a + b, 0) / diffVals.length,
      } : null,
      finalMissing: (manifest.s3b_def !== undefined || /3b/.test(String(manifest.stage || '')))
                    && faceResFinJ === null,
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
// 차이 모드 발산 램프 — 감소(청록: 색으로 설명된 잔차) ↔ 0(어두움) ↔ 잔존/증가(앰버: 기하 신호)
function rampDivRgb(t) {   // t ∈ [−1, 1]
  t = Math.min(1, Math.max(-1, t));
  const mid = [0x22, 0x26, 0x2e], teal = [0x2e, 0xe6, 0xc8], amber = [0xff, 0xcf, 0x70];
  const [a, u] = t < 0 ? [teal, -t] : [amber, t];
  return [mid[0] + (a[0] - mid[0]) * u, mid[1] + (a[1] - mid[1]) * u,
          mid[2] + (a[2] - mid[2]) * u].map(v => v / 255);
}
// 현재 히트 모드의 면별 값·스케일·색 함수 — init/final은 공유 스케일(토글 비교 가능)
function heatData(d) {
  const s3 = d.s3;
  if (!s3) return null;
  let mode = state.heatMode;
  if ((mode === 'final' || mode === 'diff') && !s3.perFaceFinal) mode = 'init';
  if (mode === 'diff') {
    const st = s3.diffStats;
    return { mode, label: `Δ|잔차| (final−step0)`,
      value: (fid) => {
        const a = s3.perFace[fid], b = s3.perFaceFinal[fid];
        return (Number.isFinite(a) && Number.isFinite(b)) ? b - a : undefined;
      },
      norm: (v) => (st && Number.isFinite(v)) ? v / st.maxAbs : null,   // [−1,1]
      rgb: rampDivRgb, stats: st ? { min: -st.maxAbs, max: st.maxAbs, mean: st.mean, n: st.n } : null,
      diverging: true };
  }
  const map = mode === 'final' ? s3.perFaceFinal : s3.perFace;
  const st = s3.resStatsShared;   // init/final 공유 스케일
  return { mode, label: mode === 'final'
             ? `면별 |잔차| 평균 — final (s${s3.finalStep ?? '?'})` : '면별 |잔차| 평균 — step0 (3a)',
    value: (fid) => map[fid],
    norm: (v) => (st && Number.isFinite(v))
      ? (st.max > st.min ? (v - st.min) / (st.max - st.min) : 0.5) : null,
    rgb: rampRgb, stats: st, diverging: false };
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
  const hd = heatData(d);
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
    const t = hd ? hd.norm(hd.value(f.face_id)) : null;
    if (t !== null && !f.domain) {
      const [r, g, b] = hd.rgb(t);
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
  const hd = heatData(d);
  const v = hd ? hd.value(f.face_id) : undefined;
  el.style.display = 'block';
  el.innerHTML = `<b style="color:#ffe066">${esc(f.face_id)}</b> ·
    ${hd && hd.mode === 'diff' ? 'Δ잔차' : '잔차'} ${Number.isFinite(v) ? (+v).toFixed(4) : '—'} ·
    ${f.initial_real ? 'F* 실재' : '게이트 0'} · ${(f.area_m2 ?? 0).toFixed(2)} m²
    <span class="note">재클릭·빈 공간·ESC=해제</span>`;
}
function renderRampLegend() {
  const el = $('#ramplegend');
  if (!el) return;
  const d = state.run;
  const hd = d && heatData(d);
  const st = hd && hd.stats;
  if (!st) { el.style.display = 'none'; return; }
  const stops = hd.diverging
    ? [-1, -0.5, 0, 0.5, 1].map(t => hd.rgb(t))
    : [0, 0.5, 1].map(t => hd.rgb(t));
  const cssStops = stops.map(c =>
    `rgb(${c.map(x => Math.round(x * 255)).join(',')})`).join(',');
  el.style.display = 'block';
  el.innerHTML = `${esc(hd.label)} (근사)<br>
    <span>${st.min.toFixed(3)}</span>
    <span style="display:inline-block;width:90px;height:9px;vertical-align:middle;
      border:1px solid #2e3542;background:linear-gradient(90deg,${cssStops})"></span>
    <span>${st.max.toFixed(3)}</span>` +
    (hd.diverging ? '<br><span>청록=감소(색으로 설명) · 앰버=잔존/증가(기하 신호)</span>' : '');
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
    if (String(s.stage) === '3b') {   // 3b: 색만 학습 — 기하(δ·평면) 동결이 계약
      if (inv.delta_frozen !== true) bad('delta_frozen != true (3b)');
      if (inv.planes_frozen !== true) bad('planes_frozen != true (3b)');
    }
  }
  // 3b 요약 — 동결군 step norm 0(자동) + PSNR 개선(자동, 체크포인트 첫↔끝)
  const rows3b = d.s3.steps.filter(s => String(s.stage) === '3b');
  if (rows3b.length) {
    const s3b = { steps: rows3b.length, frozenOk: true, frozenDetail: [],
                  colorsMoved: 0, psnr: null };
    for (const s of rows3b) {
      const p = s.param_step_norms || {};
      for (const k of ['delta', 'planes'])
        if (!((p[k] ?? null) === 0)) {
          s3b.frozenOk = false;
          if (s3b.frozenDetail.length < 6)
            s3b.frozenDetail.push(`step ${s.step}: param_step_norms.${k}=${p[k] ?? '없음'}`);
        }
      if (Number.isFinite(p.colors) && p.colors > 0) s3b.colorsMoved++;
    }
    const cks = rows3b.filter(s => s.views_psnr)
      .map(s => {
        const vs = Object.values(s.views_psnr).filter(Number.isFinite);
        return { step: s.step, mean: vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null };
      }).filter(c => c.mean !== null);
    if (cks.length >= 2) {
      const first = cks[0], last = cks[cks.length - 1];
      s3b.psnr = { firstStep: first.step, lastStep: last.step,
                   first: first.mean, last: last.mean, improved: last.mean > first.mean };
    }
    res.s3b = s3b;
  } else res.s3b = null;
  return res;
}

// ---------- 체크리스트 (3a 4항 + 3b 4항 — 참고 기준, 엄격 합불 아님: 판독 기록 2026-08-27 방침) ----------
function renderChecklist() {
  const d = state.run;
  if (!d) { $('#checkstrip').innerHTML = '<span class="note">런 없음</span>'; return; }
  const na = (t) => `<span class="badge na">${t}</span>`;
  const gb = (ok, y, n) => `<span class="badge ${ok ? 'good' : 'bad'}">${ok ? y : n}</span>`;
  let b2 = na('S3a 없음'), b3 = na('S3a 없음');
  const ck = autoChecks(d);
  if (ck) {
    b2 = gb(ck.wiringOk, '3군 전부 > 0', '0/결측 있음');
    b3 = gb(ck.invOk, '전부 참', '위반');
  }
  // 3b 4항 — PSNR 개선(자동)·동결군 step norm 0(자동)·잔차 정화(육안)·색 분화(육안)
  const sb = ck && ck.s3b;
  let b5 = na('3b 없음'), b6 = na('3b 없음'), b7 = na(sb ? '육안' : '3b 없음'),
      b8 = na(sb ? '육안' : '3b 없음');
  if (sb) {
    b5 = sb.psnr
      ? gb(sb.psnr.improved,
           `개선 ${fmtNum(sb.psnr.first, 2)}→${fmtNum(sb.psnr.last, 2)} dB`,
           `비개선 ${fmtNum(sb.psnr.first, 2)}→${fmtNum(sb.psnr.last, 2)} dB`)
      : na('체크포인트 < 2');
    b6 = gb(sb.frozenOk, 'δ·평면 0 유지', '0 아님');
  }
  const sd = (d.manifest || {}).s3_def || {};
  const sbd = (d.manifest || {}).s3b_def || null;
  const row3b = `
    <div class="chkrow">
      <span class="chkitem"><b>⑤</b> [3b] PSNR 개선(첫↔끝 체크포인트 평균) ${b5}</span>
      <span class="chkitem"><b>⑥</b> [3b] 동결군(δ·평면) step norm 0 유지 ${b6}</span>
      <span class="chkitem"><b>⑦</b> [3b] 잔차가 기하 신호로 정화(히트맵 차이 모드) ${b7}</span>
      <span class="chkitem"><b>⑧</b> [3b] 색 분화가 실재 면에서 진행(렌더·color_stats) ${b8}</span>
    </div>`;
  const meta3b = sbd ? ` · 3b 계약: 색 A_g만 학습(trained=${esc((sbd.trained || []).join(','))}) ·
        steps ${sbd.steps ?? '—'} · lr ${sbd.lr ?? '—'} · ${esc(sbd.optimizer ?? '—')} ·
        기하 바이트 불변 ${sbd.frozen_checksum_ok === true ? '<span class="badge good">checksum ok</span>' : '<span class="badge bad">미확인</span>'}` : '';
  $('#checkstrip').innerHTML = `
    <div class="chkrow">
      <span class="chkitem"><b>①</b> 렌더-사진 정렬이 실루엣 수준에서 겹침 ${na('육안')}</span>
      <span class="chkitem"><b>②</b> grad_norms 3군(δ/평면/색) 전부 0이 아님 — 배선 증거 ${b2}</span>
      <span class="chkitem"><b>③</b> 불변량 전부 참(n_seeds 일치·α 이진·δ 동결·이동량 0) ${b3}</span>
      <span class="chkitem"><b>④</b> SYNTH residual이 구조적으로 근소 ${na('육안')}</span>
    </div>${row3b}
    <div class="chkrow meta">
      <span><span class="badge prop">참고 기준</span> 엄격 런별 합불 아님 — 판독 기록 2026-08-27 방침(발견 기록으로 갈음).</span>
      <span>3a 계약: 최적화 0스텝 + backward 1회(가중치 갱신 없음) · δ 렌더 인자 배선·값 ${JSON.stringify(sd.delta_value ?? [0, 0, 0])} 고정 ·
        색 ${esc(sd.color || 'neutral-gray')} · α_g=|o_a−o_b| 유도 · densification/pruning 금지(수명 규칙 ①) ·
        렌더러 ${esc(sd.renderer || 'gsplat')}(미분 가능 렌더링)${meta3b}</span>
    </div>`;
}

// ---------- 사이클 타임라인 — 구간 배지 + 스텝 마커 (스텝·구간 다수 전제) ----------
// 수백 스텝 구간은 씨닝해 표시 — 체크포인트(views_psnr 보유 ∪ s3b_def.checkpoints)는 항상
// 강조 마커(ckpt), 선택 스텝은 씨닝돼도 항상 포함.
const TL_MAX_CHIPS = 16;
function thinStageIdxs(d, idxs, ckSet) {
  if (idxs.length <= TL_MAX_CHIPS) return { shown: idxs, thinned: false };
  const ck = idxs.filter(i => ckSet.has(d.s3.steps[i].step ?? 0));
  const rest = idxs.filter(i => !ckSet.has(d.s3.steps[i].step ?? 0));
  const chosen = new Set(ck);
  const budget = Math.max(2, TL_MAX_CHIPS - ck.length);
  for (let j = 0; j < budget && rest.length; j++)
    chosen.add(rest[Math.round(j * (rest.length - 1) / Math.max(1, budget - 1))]);
  if (state.selStep !== null && idxs.includes(state.selStep)) chosen.add(state.selStep);
  return { shown: idxs.filter(i => chosen.has(i)), thinned: true };
}
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
    let body = '<span class="planned">예정</span>', summary = '';
    if (on) {
      const ckSet = (d.s3.ckpt || {})[sg.id] || new Set();
      const { shown, thinned } = thinStageIdxs(d, idxs, ckSet);
      body = shown.map(i => {
        const s = d.s3.steps[i];
        const isCk = ckSet.has(s.step ?? 0);
        return `<span class="stepchip ${isCk ? 'ckpt' : ''} ${state.selStep === i ? 'sel' : ''}"
          data-step="${i}" title="step ${s.step}${isCk ? ' · 체크포인트' : ''} · total ${fmtNum((s.losses || {}).total)}">${s.step}</span>`;
      }).join('');
      if (thinned) body += `<div class="thinnote">표시 ${shown.length}/${idxs.length} (씨닝 — 강조=체크포인트)</div>`;
      const last = d.s3.steps[idxs[idxs.length - 1]];
      summary = ` <span class="note">스텝 ${idxs.length} · 최종 total ${fmtNum((last.losses || {}).total, 3)}</span>`;
    }
    h += `<div class="seg ${on ? 'on' : 'off'}">
      <div class="seghead">${esc(sg.label)}${summary}</div>
      ${body}
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
// 공통 다중 곡선 SVG — 직접 라벨 + <title> 툴팁 + 로그 y 옵션. 점(stepdot)에 data-sidx가
// 있으면 클릭=스텝 선택(bindPanel). 수백 스텝은 점만 씨닝(폴리라인은 전체), 체크포인트 점은
// 항상 표시·강조.
function multiCurveSvg(series, opts = {}) {
  const { H = 132, logY = false, aria = '곡선' } = opts;
  const W = 408, L = 46, R = 70, T = 10, B = 20;
  const ok = (v) => Number.isFinite(v) && (!logY || v > 0);
  const finite = [];
  series.forEach(sr => sr.pts.forEach(p => { if (ok(p.v)) finite.push(p); }));
  if (!finite.length)
    return `<p class="note">${logY ? '로그 y — 양수 값 없음' : '표시할 값 없음'}</p>`;
  const xs = finite.map(p => p.x);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const vs = finite.map(p => p.v);
  let vmax = Math.max(...vs);
  const vmin = logY ? Math.min(...vs) : 0;
  if (!logY && vmax === 0) vmax = 1;
  const X = (x) => x1 > x0 ? L + (x - x0) / (x1 - x0) * (W - L - R) : (L + (W - L - R) / 2);
  const ly = Math.log10;
  const Y = logY
    ? (v) => ly(vmax) > ly(vmin)
        ? T + (1 - (ly(v) - ly(vmin)) / (ly(vmax) - ly(vmin))) * (H - T - B)
        : T + (H - T - B) / 2
    : (v) => T + (1 - v / vmax) * (H - T - B);
  const yBase = T + (H - T - B);
  let h = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${escAttr(aria)}">
    <line x1="${L}" y1="${yBase}" x2="${W - R}" y2="${yBase}" stroke="#2e3542"/>
    <line x1="${L}" y1="${T}" x2="${L}" y2="${yBase}" stroke="#2e3542"/>
    <text x="${L - 4}" y="${yBase + 3}" text-anchor="end">${logY ? fmtNum(vmin, 2) : 0}</text>
    <text x="${L - 4}" y="${T + 8}" text-anchor="end">${fmtNum(vmax, 3)}</text>
    <text x="${X(x0)}" y="${H - 6}" text-anchor="middle">${x0}</text>
    ${x1 > x0 ? `<text x="${X(x1)}" y="${H - 6}" text-anchor="middle">${x1}</text>` : ''}`;
  const labels = [];
  series.forEach((sr) => {
    const pts = sr.pts.filter(p => ok(p.v));
    if (!pts.length) return;
    if (pts.length > 1)
      h += `<polyline fill="none" stroke="${sr.col}" stroke-width="2"
        points="${pts.map(p => `${X(p.x).toFixed(1)},${Y(p.v).toFixed(1)}`).join(' ')}"/>`;
    const every = Math.max(1, Math.ceil(pts.length / 60));   // 점 씨닝 — 폴리라인은 전체 유지
    pts.forEach((p, i) => {
      if (!(p.ck || i % every === 0 || i === pts.length - 1)) return;
      h += `<circle class="stepdot" ${p.sidx !== undefined ? `data-sidx="${p.sidx}"` : ''}
        cx="${X(p.x).toFixed(1)}" cy="${Y(p.v).toFixed(1)}" r="${p.ck ? 4.2 : 3}"
        fill="${sr.col}" ${p.ck ? 'stroke="#ffe066" stroke-width="1.2"' : ''}>
        <title>${esc(sr.key)} @ step ${p.x} = ${fmtNum(p.v)}${p.ck ? ' · 체크포인트' : ''}</title></circle>`;
    });
    const last = pts[pts.length - 1];
    labels.push({ x: X(last.x) + 6, y: Y(last.v) + 3, col: sr.col, key: sr.key });
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
// 구간(stage) 스텝 인덱스·체크포인트 → 계열 점 목록
function stagePts(d, stageId, valueOf) {
  const idxs = ((d.s3 && d.s3.byStage) || {})[stageId] || [];
  const ckSet = ((d.s3 && d.s3.ckpt) || {})[stageId] || new Set();
  return idxs.map(i => {
    const s = d.s3.steps[i];
    return { x: s.step ?? 0, v: valueOf(s), sidx: i, ck: ckSet.has(s.step ?? 0) };
  });
}
function lossCurveSvg(d, stageId) {
  const idxs = ((d.s3 && d.s3.byStage) || {})[stageId] || [];
  if (!idxs.length) return '<p class="note">스텝 없음</p>';
  const stageSteps = idxs.map(i => d.s3.steps[i]);
  const series = lossSeries(stageSteps).filter(s => s.col)
    .map(sr => ({ key: sr.key, col: sr.col,
                  pts: stagePts(d, stageId, (s) => (s.losses || {})[sr.key]) }));
  return multiCurveSvg(series, { logY: state.logYLoss,
    aria: `구간 ${stageId} 항별 손실 곡선` });
}
function gradCurveSvg(d, stageId) {
  const series = GRAD_DEF.map(([key, , col]) => ({ key, col,
    pts: stagePts(d, stageId, (s) => (s.grad_norms || {})[key]) }));
  return multiCurveSvg(series, { H: 110, logY: state.logYGrad,
    aria: `구간 ${stageId} 그라디언트 노름 3군 곡선 — 색 수렴 중 기하 압력 변화` });
}
function colorStatsSvg(d, stageId) {
  const rows = (((d.s3 && d.s3.byStage) || {})[stageId] || [])
    .filter(i => d.s3.steps[i].color_stats);
  if (!rows.length) return null;
  return CSTAT_DEF.map(([key, label, col]) => {
    const series = [{ key: label, col,
      pts: stagePts(d, stageId, (s) => ((s.color_stats || {})[key])) }];
    return multiCurveSvg(series, { H: 84, aria: `색 분화 타임랩스 — ${label}` });
  }).join('');
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
function psnrBarsSvg(step, prevCk) {
  const ps = (step || {}).views_psnr || {};
  const prev = (prevCk && prevCk.row && prevCk.row.views_psnr) || null;
  const ids = Object.keys(ps);
  if (!ids.length) return '';
  const n = ids.length, bw = Math.min(22, Math.max(8, Math.floor(360 / n) - 3));
  const W = Math.min(408, n * (bw + 3) + 40), H = 96, B = 14, T = 12;
  const all = ids.map(id => ps[id]).concat(prev ? ids.map(id => prev[id]) : []);
  const vmax = Math.max(...all.filter(Number.isFinite), 1);
  let h = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="뷰별 PSNR 분포">
    <line x1="30" y1="${H - B}" x2="${W - 4}" y2="${H - B}" stroke="#2e3542"/>
    <text x="26" y="${T + 6}" text-anchor="end">${vmax.toFixed(1)}</text>
    <text x="26" y="${H - B + 3}" text-anchor="end">0</text>`;
  ids.forEach((id, i) => {
    const v = ps[id];
    const pv = prev ? prev[id] : undefined;
    const bh = Number.isFinite(v) ? (v / vmax) * (H - T - B) : 0;
    const x = 32 + i * (bw + 3), sel = state.selView === id;
    const dTxt = Number.isFinite(pv) && Number.isFinite(v)
      ? ` · Δ vs ${esc(prevCk.label)} ${v - pv >= 0 ? '+' : ''}${fmtNum(v - pv, 2)} dB` : '';
    h += `<rect class="vbar" data-vid="${escAttr(id)}" x="${x}" y="${(H - B - bh).toFixed(1)}"
      width="${bw}" height="${bh.toFixed(1)}" fill="#8ecbff" rx="2"
      ${sel ? 'stroke="#ffe066" stroke-width="2"' : ''}>
      <title>${esc(id)} · PSNR ${fmtNum(v, 2)} dB${dTxt}</title></rect>`;
    if (Number.isFinite(pv)) {   // 이전 체크포인트 값 — 고스트 눈금(비교)
      const py = H - B - (pv / vmax) * (H - T - B);
      h += `<line x1="${x - 1}" y1="${py.toFixed(1)}" x2="${x + bw + 1}" y2="${py.toFixed(1)}"
        stroke="#ffd866" stroke-width="1.5" stroke-dasharray="2,2"/>`;
    }
    if (sel) h += `<text x="${x + bw / 2}" y="${Math.max(T, H - B - bh - 3).toFixed(1)}"
      text-anchor="middle" style="fill:#ffe066">${fmtNum(v, 1)}</text>`;
  });
  return h + `</svg><div class="note">막대 클릭 = 뷰 선택 (단일 계열 — PSNR dB, 0 기준)${
    prev ? ` · 점선 눈금 = 이전 체크포인트(${esc(prevCk.label)})` : ''}</div>`;
}
// ---------- 3b 체크포인트 도우미 ----------
// 타일 디렉터리 — 3a: s3_tiles/<view>/ · 3b 체크포인트: s3_tiles/s<step>/<view>/ (photo는 3a 재사용)
function tileDir(stageId, stepNum, viewId) {
  const root = `../runs/${encodeURIComponent(state.runName)}/s3_tiles/`;
  return String(stageId) === '3a'
    ? `${root}${encodeURIComponent(viewId)}/`
    : `${root}s${stepNum}/${encodeURIComponent(viewId)}/`;
}
function isCkptStep(d, step) {
  if (!step) return false;
  if (String(step.stage) === '3a') return true;   // 3a 단일 행 = 타일 보유
  const set = ((d.s3 && d.s3.ckpt) || {})[String(step.stage)] || new Set();
  return set.has(step.step ?? 0);
}
// 같은 구간의 체크포인트 행 목록(스텝 오름차순) — 스텝 전환·비교의 축
function ckptRows(d, stageId) {
  return (((d.s3 && d.s3.byStage) || {})[stageId] || [])
    .filter(i => isCkptStep(d, d.s3.steps[i]))
    .map(i => ({ idx: i, row: d.s3.steps[i] }));
}
// 이전 체크포인트 — 3b 첫 체크포인트의 이전은 3a 행(렌더 비교 기준선)
function prevCkpt(d, step) {
  if (!d.s3 || String(step.stage) !== '3b') return null;
  const rows = ckptRows(d, '3b').filter(r => (r.row.step ?? 0) < (step.step ?? 0));
  if (rows.length) {
    const r = rows[rows.length - 1];
    return { row: r.row, idx: r.idx, stage: '3b', step: r.row.step,
             label: `s${r.row.step}`, dir: (vid) => tileDir('3b', r.row.step, vid) };
  }
  const a = ckptRows(d, '3a');
  if (a.length) {
    const r = a[a.length - 1];
    return { row: r.row, idx: r.idx, stage: '3a', step: r.row.step,
             label: '3a', dir: (vid) => tileDir('3a', r.row.step, vid) };
  }
  return null;
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
  } else if (String((step || {}).stage) === '3b') {
    // 3b: 색만 학습 — 동결군(δ·평면) 이동량 0 확인 배지 + 색 이동량 > 0.
    // 예외: 최종 행은 평가 전용(row_semantics — 갱신 없음)이라 colors 0.0이 정상.
    const p = step.param_step_norms || {};
    const b3 = ((d.s3 || {}).byStage || {})['3b'] || [];
    const lastStep3b = b3.length ? (d.s3.steps[b3[b3.length - 1]].step ?? null) : null;
    const sbdSteps = ((d.manifest || {}).s3b_def || {}).steps;
    const isEvalRow = (sbdSteps !== undefined && step.step === sbdSteps) || step.step === lastStep3b;
    items.push(B(inv.delta_frozen === true, `δ 동결 ${inv.delta_frozen === true ? '유지' : '위반'}`));
    items.push(B(inv.planes_frozen === true, `평면 동결 ${inv.planes_frozen === true ? '유지' : '위반'}`));
    items.push(B((p.delta ?? null) === 0, `δ 이동량 ${fmtNum(p.delta, 1)} ${(p.delta ?? null) === 0 ? '(동결군 0)' : '(0 아님!)'}`));
    items.push(B((p.planes ?? null) === 0, `평면 이동량 ${fmtNum(p.planes, 1)} ${(p.planes ?? null) === 0 ? '(동결군 0)' : '(0 아님!)'}`));
    if (isEvalRow && (p.colors ?? 0) === 0)
      items.push(`<span class="badge na">색 이동량 0.0 (최종 행 = 평가 전용 — 갱신 없음)</span>`);
    else
      items.push(B(Number.isFinite(p.colors) && p.colors > 0, `색 이동량 ${fmtNum(p.colors)} ${Number.isFinite(p.colors) && p.colors > 0 ? '(학습 중)' : '(0/결측 — 학습 정지?)'}`));
  } else {
    items.push(`<span class="badge na">δ 동결 ${inv.delta_frozen === undefined ? '—' : inv.delta_frozen} · 이동량 ${fmtNum(step.param_step_norm, 3)} (구간 ${esc(step.stage)} 계약은 추후)</span>`);
  }
  return items.join(' ');
}
function s3DefCard(d) {
  const sd = (d.manifest || {}).s3_def || {};
  const sbd = (d.manifest || {}).s3b_def || null;
  const s3 = d.s3;
  const s3bRows = sbd ? `
      <tr><td class="k">구간 3b</td><td class="l">색만 학습(기하 동결·웜업) — trained=${esc(JSON.stringify(sbd.trained ?? ['colors']))} ·
        steps ${sbd.steps ?? '—'} · lr ${sbd.lr ?? '—'} · optimizer=${esc(sbd.optimizer ?? '—')}</td></tr>
      <tr><td class="k">3b 체크포인트</td><td class="l">[${(sbd.checkpoints || []).join(', ')}] ·
        기하 바이트 불변 ${sbd.frozen_checksum_ok === true
          ? '<span class="badge good">frozen_checksum_ok</span>'
          : '<span class="badge bad">미확인/실패</span>'}</td></tr>` : '';
  return `<div class="card">
    <table>
      <tr><td class="k">구간 3a</td><td class="l">${esc(sd.stage ?? '—')} (렌더-온리 — 최적화 0스텝 + backward 1회)</td></tr>
      <tr><td class="k">δ 배선</td><td class="l">${sd.delta_wired === true ? '렌더 인자로 배선됨' : (sd.delta_wired === undefined ? '—' : '<span class="bad">배선 안 됨!</span>')} · 값 ${JSON.stringify(sd.delta_value ?? '—')} 고정</td></tr>
      <tr><td class="k">색 / 렌더러</td><td class="l">${esc(sd.color ?? '—')} / ${esc(sd.renderer ?? '—')} · optimizer=${esc(sd.optimizer ?? '—')}</td></tr>${s3bRows}
      <tr><td class="k">뷰 수</td><td class="l">${sd.n_views ?? (s3 ? s3.views.length : '—')}</td></tr>
      <tr><td class="k">뷰 선정 규칙</td><td class="l">${esc(s3 && s3.selectionRule ? (typeof s3.selectionRule === 'string' ? s3.selectionRule : JSON.stringify(s3.selectionRule)) : '—')}</td></tr>
    </table>
    ${s3 && s3.badLines ? `<div class="err">s3_steps.jsonl 파싱 실패 행 ${s3.badLines}개</div>` : ''}</div>`;
}
function stepLossCard(d, step) {
  const losses = (step || {}).losses || {};
  const stageId = String(step.stage);
  const series = lossSeries(d.s3.steps);
  const rows = series.map(sr => `<tr>
    <td class="l">${sr.col ? `<span style="display:inline-block;width:9px;height:9px;background:${sr.col};border-radius:2px;margin-right:4px;vertical-align:middle"></span>` : ''}${esc(sr.key)}</td>
    <td>${fmtNum(losses[sr.key])}</td></tr>`).join('');
  return `<div class="card">
    <table><tr><th class="l">항 (가용 항 자동 표시 — depth/실루엣 추가 시 자동)</th><th>값</th></tr>${rows}</table>
    <div class="legend" style="margin-top:5px">
      <label><input type="checkbox" id="logYLossTgl" ${state.logYLoss ? 'checked' : ''}> 로그 y</label></div>
    ${lossCurveSvg(d, stageId)}
    <div class="note">구간 ${esc(stageId)} 전체 손실 곡선 — 스텝 1개면 점. 축: X=스텝,
      Y=손실(${state.logYLoss ? '로그' : '0 기준'}). 점 클릭=스텝 전환 · 강조 점=체크포인트.</div></div>`;
}
function viewsCard(d, step) {
  const s3 = d.s3;
  if (!s3.views.length) return '<p class="note">s3_views.json에 뷰 없음</p>';
  const vsel = state.selView;
  const v = s3.views.find(x => x.view_id === vsel) || s3.views[0];
  const stageId = String(step.stage);
  const psnr = ((step || {}).views_psnr || {})[v.view_id];
  const opts = s3.views.map(x =>
    `<option value="${escAttr(x.view_id)}" ${x.view_id === v.view_id ? 'selected' : ''}>${esc(x.view_id)}</option>`).join('');
  const fig = (src, alt, cap) => `<figure><img src="${src}" alt="${escAttr(alt)}" loading="lazy"
        onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'err',textContent:'${escAttr(alt)} 타일 없음'}))">
        <figcaption>${cap}</figcaption></figure>`;
  const photoSrc = tileDir('3a', 0, v.view_id) + 'photo.png';   // photo는 3a 타일 재사용
  let head = `<div class="legend">뷰 <select id="viewsel">${opts}</select>
      <span class="note">${esc(v.image_ref || '')} · ${v.width ?? '?'}×${v.height ?? '?'}${psnr !== undefined ? ` · PSNR ${fmtNum(psnr, 2)} dB` : ''}</span></div>`;
  // 체크포인트 스텝 전환 내비 (3b — PSNR 막대·타일이 함께 전환)
  let prev = null;
  if (stageId === '3b') {
    const cks = ckptRows(d, '3b');
    const pos = cks.findIndex(r => r.idx === state.selStep);
    const btn = (idx, txt) => idx !== null
      ? `<button class="small ckjump" data-step="${idx}">${txt}</button>`
      : `<button class="small" disabled>${txt}</button>`;
    const prevIdx = pos > 0 ? cks[pos - 1].idx : (pos === 0 && ckptRows(d, '3a').length
      ? ckptRows(d, '3a')[0].idx : null);
    const nextIdx = pos >= 0 && pos < cks.length - 1 ? cks[pos + 1].idx : null;
    head += `<div class="legend">체크포인트 전환 ${btn(prevIdx, '◀ 이전 CP')} ${btn(nextIdx, '다음 CP ▶')}
      <label style="margin-left:8px"><input type="checkbox" id="cmpPrevTgl" ${state.cmpPrev ? 'checked' : ''}>
        이전/현재 렌더 나란히</label></div>`;
    prev = prevCkpt(d, step);
  }
  if (!isCkptStep(d, step)) {   // 3b 비체크포인트 행 — 타일 없음(계약: 체크포인트만 저장)
    const cks = ckptRows(d, stageId);
    let nearest = null, best = Infinity;
    for (const r of cks) {
      const dd = Math.abs((r.row.step ?? 0) - (step.step ?? 0));
      if (dd < best) { best = dd; nearest = r; }
    }
    return `${head}<div class="note">스텝 ${step.step}은 체크포인트가 아니라 타일이 없다
      (계약: s3_tiles/s&lt;step&gt;/는 체크포인트만). ${nearest
        ? `가장 가까운 체크포인트: <button class="small ckjump" data-step="${nearest.idx}">s${nearest.row.step}로 이동</button>` : ''}</div>
      <div style="margin-top:5px">${psnrBarsSvg(step, prev)}</div>`;
  }
  const base = tileDir(stageId, step.step ?? 0, v.view_id);
  let tiles = fig(photoSrc, 'photo', `사진 (다운스케일 ≤640${stageId === '3b' ? ' · 3a 타일 재사용' : ''})`);
  if (stageId === '3b' && state.cmpPrev && prev)
    tiles += fig(prev.dir(v.view_id) + 'render.png', `이전 렌더`,
                 `렌더 — 이전 CP ${esc(prev.label)}`);
  tiles += fig(base + 'render.png', 'render',
               stageId === '3b' ? `렌더 s${step.step} (색 학습 중)` : '렌더 (gsplat · S2 상태)');
  tiles += fig(base + 'residual.png', 'residual', '|사진−렌더| 그레이 히트');
  return `${head}<div class="tiles">${tiles}</div>
    <div style="margin-top:5px">${psnrBarsSvg(step, prev)}</div>`;
}
function faceResidualCard(d) {
  const s3 = d.s3;
  const hasFinal = !!s3.perFaceFinal;
  const hd = heatData(d);
  const st = hd && hd.stats;
  const modeRadio = (val, label, dis) => `<label ${dis ? 'style="opacity:.5"' : ''}>
      <input type="radio" name="heatmode" value="${val}" ${state.heatMode === val ? 'checked' : ''}
        ${dis ? 'disabled' : ''}> ${label}</label>`;
  let h = `<div class="card">
    <div class="legend">히트맵
      ${modeRadio('init', 'step0 (3a)', false)}
      ${modeRadio('final', `final${hasFinal ? ` (s${s3.finalStep ?? '?'})` : ''}`, !hasFinal)}
      ${modeRadio('diff', '차이 (final−step0)', !hasFinal)}
      ${hasFinal ? '' : '<span class="note">final은 s3_face_residual_final.json 생성 후</span>'}</div>
    <div class="note caption" style="margin-bottom:4px">근사 방식(숨기지 않음): ${esc(
      (state.heatMode === 'final' && hasFinal ? s3.finalMethod : s3.method) || '— method 명기 없음')}</div>`;
  if (state.heatMode === 'diff' && hasFinal)
    h += `<div class="note caption" style="border-left-color:#2ee6c8;margin-bottom:4px">
      차이 판독: 잔차 <b style="color:#2ee6c8">감소(청록)</b> = 색으로 설명된 잔차 ·
      <b style="color:#ffcf70">잔존/증가(앰버)</b> = 기하 신호 후보(3c/3d·이산 라운드의 표적).
      판독 힌트: B173 저층 지붕동 잔존 확인.</div>`;
  if (!st) h += '<p class="note">per_face 잔차 값 없음</p>';
  else h += `<table>
      <tr><td class="k">잔차 보유 면</td><td>${st.n ?? '—'} / ${d.faces.length}</td></tr>
      <tr><td class="k">min · mean · max</td><td>${fmtNum(st.min)} · ${fmtNum(st.mean)} · ${fmtNum(st.max)}</td></tr>
    </table>
    <div class="note" style="margin-top:3px">${hd.diverging
      ? '3D 면 색 = 발산 램프(청록=감소·앰버=잔존/증가, 양쪽 값 있는 면만)'
      : '3D 면 색 = 낮음(어두움)→높음(밝은 앰버) 램프 — step0/final 공유 스케일(토글 비교 가능)'} —
      s2_faces 지오메트리 재사용. 면 클릭 = 카드 + 페이지 2·1 점프.</div>`;
  h += '</div>';
  if (state.selFace !== null) {
    const f = d.faces[state.selFace];
    const v = s3.perFace[f.face_id];
    const vFin = hasFinal ? s3.perFaceFinal[f.face_id] : undefined;
    const p2 = (q) => `../viewer_p2/?run=${encodeURIComponent(state.runName)}${q}`;
    const planeRows = (f.s1_plane_ids || []).map(pid =>
      `<a href="../viewer_p1/?run=${encodeURIComponent(state.runName)}&plane=${encodeURIComponent(pid)}"
        style="color:#8ecbff">${esc(pid)} ↗페이지 1</a>`).join(' · ');
    const dRow = (Number.isFinite(v) && Number.isFinite(vFin))
      ? `<tr><td class="k">Δ (final−step0)</td><td>${fmtNum(vFin - v)}
           ${vFin - v < 0 ? '<span class="good">감소 — 색으로 설명</span>'
                          : '<span class="warn">잔존/증가 — 기하 신호 후보</span>'}</td></tr>` : '';
    h += `<div class="card" id="facecard"><b style="color:#ffe066">${esc(f.face_id)}</b>
      ${f.initial_real ? '<span class="badge good">F* 초기 실재</span>' : '<span class="badge na">게이트 0</span>'}
      <table style="margin-top:4px">
        <tr><td class="k">|잔차| 평균 step0 (3a)</td><td>${fmtNum(v)}</td></tr>
        ${hasFinal ? `<tr><td class="k">|잔차| 평균 final (s${s3.finalStep ?? '?'})</td><td>${fmtNum(vFin)}</td></tr>` : ''}
        ${dRow}
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
    3a(렌더-온리)부터. 3a의 물음: "광도 잔차가 δ·평면·색까지 실제로 흘러오는가"(배선 증거).
    3b의 물음: "색이 수렴하는 동안 기하 압력이 어떻게 변하는가"(색만 학습·기하 동결 웜업).
    이산 라운드·판정 기록은 다음 차수.</div>`;
  if (!d.s3) {
    h += `<div class="err">S3a 파일 없음: ${d.s3Missing.map(esc).join(', ')}<br>
      writer가 S3a 산출물(s3_views/s3_steps/s3_face_residual/s3_tiles)을 아직 생성하지 않았다 —
      생성 후 새로고침. ${d.faces.length ? 'S2 면 지오메트리를 고스트 와이어로만 표시 중.' : ''}</div>`;
    if (d.s2Missing) h += '<div class="err">s2_faces.json도 없음 — 3D 표시 불가(페이지 2 writer 선행).</div>';
  } else {
    if (d.s3Missing.length)
      h += `<div class="err">S3a 일부 파일 없음: ${d.s3Missing.map(esc).join(', ')} — 있는 만큼 표시.</div>`;
    if (d.s3.finalMissing)
      h += `<div class="err">3b 흔적은 있는데 s3_face_residual_final.json이 없다 —
        writer 완주 후 새로고침(면 히트맵 final/차이 모드는 그때 열린다).</div>`;
    const step = state.selStep !== null ? d.s3.steps[state.selStep] : null;
    h += `<h2>S3 정의 <span class="note">(manifest.s3_def/s3b_def + s3_views)</span></h2>${s3DefCard(d)}`;
    if (!step) {
      h += '<p class="note">타임라인에서 스텝을 클릭하세요.</p>';
    } else {
      const stageId = String(step.stage);
      const gradNote = stageId === '3b'
        ? `색만 갱신하되 backward는 전 리프로 흘려 <b>동결군(δ·평면)의 그라디언트 노름도 기록</b> —
           "색이 수렴하는 동안 기하 압력이 어떻게 변하는가"의 관측. 곡선 축: X=스텝.`
        : `최적화 0스텝·backward 1회(가중치 갱신 없음) —
           광도 잔차가 δ/평면/색 변수군까지 실제로 흘러오는가의 증거. 전부 0이 아니어야 함(체크 ②).`;
      h += `<h2>스텝 ${step.step} (구간 ${esc(stageId)}) — 항별 손실</h2>${stepLossCard(d, step)}
        <h2>그라디언트 노름 3군 <span class="badge eval">${stageId === '3b' ? '색 수렴 중 기하 압력 변화' : '배선 증거'}</span></h2>
        <div class="card">${gradBarsHtml(step)}
          <div class="legend" style="margin-top:4px">
            <label><input type="checkbox" id="logYGradTgl" ${state.logYGrad ? 'checked' : ''}> 로그 y</label></div>
          ${gradCurveSvg(d, stageId)}
          <div class="note" style="margin-top:3px">${gradNote}</div></div>
        <h2>불변량 배지${stageId === '3b' ? ' <span class="badge eval">동결군 0 확인</span>' : ''}</h2>
        <div class="card">${invariantBadges(d, step)}
          <div class="note" style="margin-top:4px">n_seeds == manifest counts.seeds(전수 유지 — 수명 규칙 ① ·
            densify/prune 금지) · α_g=|Δo| 이진 유도(자유 알파 금지) ·
            ${stageId === '3b' ? '3b: 기하(δ·평면) 동결 — param_step_norms.delta/planes=0, colors>0.'
                               : 'δ 동결(3a) · param_step_norm=0(3a).'}</div></div>
        <h2>뷰 — 사진 / 렌더 / 잔차 + PSNR 분포</h2>
        <div class="card">${viewsCard(d, step)}</div>`;
      if (stageId === '3b') {
        const cs = colorStatsSvg(d, '3b');
        h += `<h2>색 분화 타임랩스 <span class="note">(체크포인트 color_stats)</span></h2>
          <div class="card">${cs || '<p class="note">color_stats 없는 3b 행뿐 — 체크포인트 행에만 기록되는 계약.</p>'}
          <div class="note" style="margin-top:3px">중립 회색(0.5 상수)에서 출발한 색이 실재 면에서
            분화하는가 — 평균 채도·색 분산의 스텝 추이(체크 ⑧ 육안 근거, 렌더 타일과 대조).</div></div>`;
      }
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
  on('#logYLossTgl', 'onchange', () => { state.logYLoss = $('#logYLossTgl').checked; renderPanel(); });
  on('#logYGradTgl', 'onchange', () => { state.logYGrad = $('#logYGradTgl').checked; renderPanel(); });
  on('#cmpPrevTgl', 'onchange', () => { state.cmpPrev = $('#cmpPrevTgl').checked; renderPanel(); });
  document.querySelectorAll('input[name="heatmode"]').forEach(r => {
    r.onchange = () => {   // 히트맵 모드 — 면 색 재계산이 필요해 씬 재구축
      state.heatMode = r.value;
      if (state.run) buildScene(state.run);
      renderPanel();
    };
  });
  document.querySelectorAll('#panel .ckjump').forEach(b => {
    b.onclick = () => { state.selStep = +b.dataset.step; renderTimeline(); renderPanel(); };
  });
  document.querySelectorAll('#panel svg .stepdot[data-sidx]').forEach(c => {
    c.onclick = () => { state.selStep = +c.dataset.sidx; renderTimeline(); renderPanel(); };
  });
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
    schema: 'phd_s3_verify_p3_reading_v2',   // v2: 3b 항 ⑤~⑧ + auto.s3b + face_residual final/diff
    page: 'p3_joint_opt_continuous',
    run: state.runName,
    bundle: {
      schema: d.manifest.schema, bundle_name: d.manifest.bundle_name,
      stage: d.manifest.stage, dataset: d.manifest.dataset,
      counts: d.manifest.counts, s3_def: d.manifest.s3_def ?? null,
      s3b_def: d.manifest.s3b_def ?? null,
    },
    checklist: [
      '① 렌더-사진 정렬이 실루엣 수준에서 겹침 (육안)',
      '② grad_norms 3군(δ/평면/색) 전부 0이 아님 (자동 — 배선 증거)',
      '③ 불변량 전부 참: n_seeds 일치·α 이진·δ 동결·param_step_norm 0 (자동)',
      '④ SYNTH residual이 구조적으로 근소 (육안)',
      '⑤ [3b] PSNR 개선 — 첫↔끝 체크포인트 평균 (자동)',
      '⑥ [3b] 동결군(δ·평면) step norm 0 유지 (자동)',
      '⑦ [3b] 잔차가 기하 신호로 정화 — 히트맵 차이 모드 (육안)',
      '⑧ [3b] 색 분화가 실재 면에서 진행 — 렌더·color_stats (육안)',
    ],
    checklist_policy: '참고 기준 — 엄격 런별 합불 아님 (판독 기록 2026-08-27 방침, 발견 기록으로 갈음)',
    auto: d.s3 ? {
      steps: d.s3.steps.length,
      stages: Object.keys(d.s3.byStage),
      wiring_ok: ck ? ck.wiringOk : null, wiring_detail: ck ? ck.wiringDetail : [],
      invariants_ok: ck ? ck.invOk : null, invariants_detail: ck ? ck.invDetail : [],
      s3b: ck ? ck.s3b : null,
      selected_step: step ? { step: step.step, stage: step.stage, losses: step.losses,
                              grad_norms: step.grad_norms, param_step_norm: step.param_step_norm,
                              param_step_norms: step.param_step_norms ?? null,
                              color_stats: step.color_stats ?? null } : null,
      n_views: d.s3.views.length,
      face_residual: { method: d.s3.method, stats: d.s3.resStats },
      face_residual_final: d.s3.perFaceFinal ? { step: d.s3.finalStep,
        method: d.s3.finalMethod, stats: d.s3.resStatsFinal, diff: d.s3.diffStats } : null,
      heat_mode: state.heatMode,
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
  const stageTxt = d.s3
    ? Object.entries(d.s3.byStage).map(([k, v]) => `${k}(${v.length})`).join('+')
    : null;
  $('#countsline').textContent =
    `${d.manifest.bundle_name || state.runName} · stage=${d.manifest.stage || 's1'}` +
    (d.s3 ? ` · 구간 ${stageTxt || sd.stage || '3a'} · 뷰 ${sd.n_views ?? d.s3.views.length}` +
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
  if (d.s3 && d.s3.steps.length) {          // 기본 선택: 마지막 스텝(3b면 final 체크포인트) + 첫 뷰
    state.selStep = d.s3.steps.length - 1;
    state.selView = d.s3.views.length ? d.s3.views[0].view_id : null;
  }
  // 기본 히트 모드 — final이 있으면 final(3b 판독 축), 없으면 step0
  state.heatMode = (d.s3 && d.s3.perFaceFinal) ? 'final' : 'init';
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
                    (r.s3_ready === false ? ' [S3a 없음]'
                      : r.s3b_ready === true ? ' [+3b]' : '');
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
