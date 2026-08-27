// S3 검증 페이지 2 — 배열·초기값(S2) 정적 뷰어. NOT OFFICIAL · scientific_verdict: null.
// 데이터 계약: phd_s3_verify_s2_bundle_v1 — ../runs/<name>/{manifest.json, s1_points.ply,
// s1_planes.json, s1_view.json} + {s2_cells.json, s2_faces.json, s2_seeds.json} 지연 fetch.
// S2 파일이 아직 없으면(S1만 존재) 빈 상태 안내를 내고 죽지 않는다.
// o_init 확정값(방법론 r16): 셀 중심 단일 기둥(반경 0.75 m) 안 ALS 점 p90 = z_surf,
// 아래 0.75 / 위 0.15 / 무점 0.4 / footprint 밖 0 고정. ALS 전용(source==1). 다점 평균 폐기.
// 연계 판독(리뷰어 요청 2026-08-27): ① 평면별 절단 보기 — S1 평면 선택 시 그 평면이 만든
// 면(s1_plane_ids ∋ pid) 출처색 발광·나머지 감광 + 잘린 셀(cut_plane_ids ∋ pid)·면·면적 요약
// 카드(조각 진단) + 페이지 1 점프, ② 셀 카드 절단 평면 = 출처색 칩(클릭=①로 전환),
// ③ 출발 상태 요약 카드(변수 4군 o·t / P⁰ / δ / 색 — 런 로드 시 자동),
// ④ o_init 맵 모드 — 셀 색 라디오 켬/끔 ↔ 소프트 t 4범주(0.75 청 / 0.15 회청 / 0.4 무점 보라
// 강조(증축 탐지 감도의 자리) / 0.0 밖 회색), 면 색 = 인접 두 셀 중 큰 t. 앵커 항 C_k의
// 셀-단위 초기값 = t (loss의 사전 항 단위) — 범례 캡션 명기.
// ⑤ S1 평면 → 셀 절단 인과(리뷰어 요청 2026-08-27 확장): (a) 평면별 절단 보기에 3요소
// 오버레이 — 선택 평면의 S1 원형 support_local(증거 영역, 출처색 0.35) + 기존 면 발광
// (무한 절단 단면) + 잘린 셀 요약 유지, 카드 범례 "증거 영역 → 무한 절단(§1.1 그림 B)
// → 셀"; (b) 절단 누적 재생 — s2_cut_sequence.json(writer --cut-sequence-only, 접두
// 배열 전수) lazy fetch, 슬라이더 0..K + ◀▶로 평면 1..k의 면(칼금 자국)만 표시(RGBA
// 정점색 단일 메시 제자리 갱신 — 지오메트리 재생성 없음)·현재 평면 S1 원형 병행,
// k vs n_cells 미니 곡선, delta_cells 파편화 랭킹 상위 10(칩 클릭=평면 선택).
// 재생 모드는 셀/면/평면 선택과 배타 전환, ESC 해제, 판독 JSON에 사용 여부 기록.
// three.js r160 vendored (CDN 금지). 궤도/팬/줌·PLY 파서는 페이지 1 관행 승계.
import * as THREE from './three.module.min.js';

const $ = (s) => document.querySelector(s);
const esc = (x) => String(x).replace(/&/g, '&amp;').replace(/</g, '&lt;');
const escAttr = (x) => esc(x).replace(/"/g, '&quot;');
window.onerror = (msg, src, line) => {
  const el = $('#panel') || document.body;
  el.insertAdjacentHTML('afterbegin', `<div class="err">JS 오류: ${esc(msg)} (${line})</div>`);
};

// ---------- 색 관행 (페이지 1 계열) ----------
const COL = {
  occ: 0x4a9eff,        // o_state=1 셀 반투명 채움
  real: 0x8ecbff,       // F* 초기 실재 면 (오버레이 ON)
  sleep: 0x9fb4cc,      // 게이트 0 "잠든 면" (얇은 반투명)
  flipNew: 0xff9a3c,    // 뒤집기 신규 생성 면 (비용, 주황)
  flipGone: 0x2ee6c8,   // 뒤집기 소멸 면 (환급, 청록)
  selFill: 0xffe066,    // 선택 면 채움 / 선택 윤곽 (맥동)
  wireOcc: 0x6fa8d8, wireReal: 0x8ecbff, wireDim: 0x3a4250,
  als: 0xd08a2e,        // ALS prior 점 앰버 (페이지 1 관행)
  seedReal: 0xcf9bff, seedSleep: 0x6f5a86,
  colGlow: 0xffe066,    // 기둥 안 ALS 점 발광
  p90: 0x7ee787,        // p90 높이선
};
const VERDICT_KO = { below: '표면 아래(내부)', above: '표면 위(외부)',
                     empty: '기둥 무점', outside: 'footprint 밖(고정)' };
const T_KO = { below: '아래', above: '위', empty: '무점', outside: '밖' };
// 출처색 — 페이지 1 관행 승계 (계약 enum)
const SRC_COLORS = { prior: 0x4a9eff, mvs: 0xffa040, footprint: 0x9aa4b0,
                     gapfill: 0xb07fe8, synthetic_gt: 0x50d890, synthetic_distractor: 0xff5f6e };
const SRC_LABEL = { prior: 'prior(ALS)', mvs: 'MVS', footprint: 'footprint',
                    gapfill: 'gapfill', synthetic_gt: '합성 GT형', synthetic_distractor: '합성 교란' };
const srcCss = (s) => '#' + ((SRC_COLORS[s] ?? 0x888888).toString(16).padStart(6, '0'));

const state = {
  runs: [], runName: null, run: null, cache: {},
  selCell: null,        // 선택 셀 index (s2.cells)
  selFace: null,        // 선택 면 index (s2.faces)
  selPlane: null,       // 선택 S1 평면 plane_id — 평면별 절단 보기 (조각 진단)
  playK: null,          // 절단 누적 재생 위치 k (null=재생 모드 꺼짐 — 선택과 배타)
  cellColor: 'o',       // 셀 색 모드: 'o'(켬/끔 o_state) | 't'(o_init 맵 — 소프트 t 4범주)
  flip: false,          // 점유 뒤집기 — 화면 전용, 데이터 변경 없음
  showFstar: false, showSeeds: false, showAls: true, showDomain: true, showWire: true,
  pickMode: 'cell',     // 'cell' | 'face'
  reading: {}, lastFit: null,
};

// ---------- three.js scaffold (페이지 1 승계) ----------
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
window.addEventListener('keydown', (e) => {  // ESC = 선택/재생 해제 · ←→ = 재생 k 이동
  if (!state.run) return;
  const t = e.target;
  if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.tagName === 'SELECT')) return;
  if (e.key === 'Escape') {
    if (state.selCell !== null || state.selFace !== null || state.selPlane !== null ||
        state.playK !== null) clearSelection();
  } else if (state.playK !== null && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
    setPlayK(state.playK + (e.key === 'ArrowRight' ? 1 : -1));
    e.preventDefault();
  }
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

let cellGroup = new THREE.Group(),   // 채움 버킷(스타일별 병합 메시) + 픽 메시 + 와이어
    seedGroup = new THREE.Group(), ptsGroup = new THREE.Group(),
    ctxGroup = new THREE.Group(), selGroup = new THREE.Group(),
    colGroup = new THREE.Group(),    // 표면고 기둥 카드 3D
    evGroup = new THREE.Group(),     // 증거 영역(S1 원형 support_local) 오버레이
    cutGroup = new THREE.Group();    // 절단 누적 재생 — RGBA 정점색 단일 메시(제자리 갱신)
scene.add(cellGroup, seedGroup, ptsGroup, ctxGroup, selGroup, colGroup, evGroup, cutGroup);
function emptyGroup(g) {
  for (const o of [...g.children]) {
    g.remove(o);
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();
  }
}
function clear3d() {
  for (const g of [cellGroup, seedGroup, ptsGroup, ctxGroup, selGroup, colGroup,
                   evGroup, cutGroup]) {
    scene.remove(g); emptyGroup(g);
  }
  cellGroup = new THREE.Group(); seedGroup = new THREE.Group(); ptsGroup = new THREE.Group();
  ctxGroup = new THREE.Group(); selGroup = new THREE.Group(); colGroup = new THREE.Group();
  evGroup = new THREE.Group(); cutGroup = new THREE.Group();
  scene.add(cellGroup, seedGroup, ptsGroup, ctxGroup, selGroup, colGroup, evGroup, cutGroup);
  hiliteMats = [];
}

// ---------- binary PLY 파서 (페이지 1 승계 — 행 순서 = 인덱스 공간) ----------
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
      else if (name === 'source') src[i] = v;
    }
  }
  return { count, pos, src };
}

// ---------- S2 인덱스 구축 + 경량 자체 검사 ----------
function buildS2(d, cellsJ, facesJ, seedsJ) {
  const cells = cellsJ.cells || [], faces = facesJ.faces || [], seeds = seedsJ.seeds || [];
  const cellIdx = {}, faceIdx = {};
  cells.forEach((c, i) => { cellIdx[c.cell_id] = i; });
  faces.forEach((f, i) => { faceIdx[f.face_id] = i; });
  const refDetail = [];
  let refErrors = 0;
  const refErr = (msg) => { refErrors++; if (refDetail.length < 10) refDetail.push(msg); };
  // 셀 인접 면 (faces의 cell_a/cell_b에서 구축 — cell.face_ids는 검사로 교차 확인)
  const cellFaces = cells.map(() => []);
  // 평면별 절단 보기 색인 — 평면이 만든 면(facesByPlane) / 평면이 자른 셀(cellsByCutPlane)
  const facesByPlane = {}, cellsByCutPlane = {};
  faces.forEach((f, fi) => {
    for (const key of ['cell_a', 'cell_b']) {
      const cid = f[key];
      if (cid === null || cid === undefined) {
        if (key === 'cell_a') refErr(`${f.face_id}: cell_a 없음`);
        continue;  // cell_b null = 도메인 경계 (계약상 정상)
      }
      const ci = cellIdx[cid];
      if (ci === undefined) refErr(`${f.face_id}: ${key}=${cid} 실재하지 않음`);
      else cellFaces[ci].push(fi);
    }
    for (const pid of (f.s1_plane_ids || [])) {
      if (!d.planeById[pid]) refErr(`${f.face_id}: s1_plane_id=${pid} 실재하지 않음`);
      (facesByPlane[pid] = facesByPlane[pid] || []).push(fi);
    }
  });
  let seedRefBad = 0;
  const faceSeedCount = new Uint32Array(faces.length);
  const seedFace = new Int32Array(seeds.length).fill(-1);
  seeds.forEach((s, si) => {
    const fi = faceIdx[s.face_id];
    if (fi === undefined) { seedRefBad++; refErr(`${s.seed_id}: face_id=${s.face_id} 실재하지 않음`); }
    else { seedFace[si] = fi; faceSeedCount[fi]++; }
  });
  let colSrcBad = 0, oStateBad = 0;
  cells.forEach((c, ci) => {
    for (const fid of (c.face_ids || []))
      if (faceIdx[fid] === undefined) refErr(`${c.cell_id}: face_id=${fid} 실재하지 않음`);
    for (const pid of (c.cut_plane_ids || [])) {
      if (!d.planeById[pid]) refErr(`${c.cell_id}: cut_plane_id=${pid} 실재하지 않음`);
      (cellsByCutPlane[pid] = cellsByCutPlane[pid] || []).push(ci);
    }
    const idxs = ((c.surf || {}).col_pt_idx) || [];
    for (const pi of idxs) {
      if (!(pi >= 0 && pi < d.N)) refErr(`${c.cell_id}: col_pt_idx=${pi} 범위 밖`);
      else if (d.src[pi] !== 1) colSrcBad++;   // 정합(참고): 기둥 점은 전부 ALS(source==1)
    }
    if (((c.t > 0.5) ? 1 : 0) !== c.o_state) oStateBad++;
  });
  // F* 재계산 — o_state 산수로 실재 면 재유도, initial_real과 대조 (도메인 밖 = o=0)
  const occOf = (cid) => {
    if (cid === null || cid === undefined) return 0;
    const ci = cellIdx[cid];
    return ci === undefined ? 0 : (cells[ci].o_state ? 1 : 0);
  };
  let fstarBad = 0;
  const realNow = new Uint8Array(faces.length);
  faces.forEach((f, fi) => {
    realNow[fi] = Math.abs(occOf(f.cell_a) - occOf(f.cell_b)) === 1 ? 1 : 0;
    if (!!f.initial_real !== !!realNow[fi]) fstarBad++;
  });
  // 부피 검사 — Σ셀 = 프리즘 (상대 1e-3)
  let sumCells = 0;
  cells.forEach(c => { sumCells += (c.volume_m3 || 0); });
  const vols = (d.manifest || {}).volumes || {};
  const prism = vols.prism_m3 ?? cellsJ.prism_volume_m3 ?? null;
  const manifestSum = vols.sum_cells_m3 ?? cellsJ.sum_cell_volume_m3 ?? null;
  const volRel = prism ? Math.abs(sumCells - prism) / Math.abs(prism) : null;
  let seedHave = 0;
  for (let fi = 0; fi < faces.length; fi++) if (faceSeedCount[fi] > 0) seedHave++;
  return {
    cells, faces, seeds, grid: seedsJ.grid || {},
    cellIdx, faceIdx, cellFaces, facesByPlane, cellsByCutPlane,
    faceSeedCount, seedFace, realNow, occOf,
    checks: {
      refErrors, refDetail, colSrcBad, oStateBad, fstarBad,
      volume: { sumCells, prism, manifestSum, rel: volRel,
                pass: volRel === null ? null : volRel <= 1e-3 },
      seedCover: { have: seedHave, total: faces.length,
                   pass: faces.length > 0 && seedHave === faces.length },
    },
  };
}

// ---------- 런 로드 ----------
async function fetchRun(name) {
  const base = `../runs/${name}`;
  const jf = (fn) => fetch(`${base}/${fn}`).then(r => {
    if (!r.ok) throw new Error(`${fn} ${r.status}`); return r.json();
  });
  const [manifest, planes, viewJ, plyBuf] = await Promise.all([
    jf('manifest.json'), jf('s1_planes.json'), jf('s1_view.json'),
    fetch(`${base}/s1_points.ply`).then(r => {
      if (!r.ok) throw new Error(`s1_points ${r.status}`); return r.arrayBuffer();
    }),
  ]);
  const pts = parsePly(plyBuf);
  const planeById = {};
  (planes.planes || []).forEach(p => { planeById[p.plane_id] = p; });
  const alsLocals = [];
  for (let i = 0; i < pts.count; i++) if (pts.src[i] === 1) alsLocals.push(i);
  const d = { name, manifest, planes, planeById, view: viewJ,
              N: pts.count, pos: pts.pos, src: pts.src, alsLocals, s2: null, s2Missing: [],
              cutSeq: null, cutSeqError: null };  // 절단 누적 재생 — lazy fetch 캐시
  // S2 3종 — 없으면 빈 상태 (writer가 아직 생성하지 않음)
  const opt = await Promise.all(['s2_cells.json', 's2_faces.json', 's2_seeds.json'].map(fn =>
    fetch(`${base}/${fn}`).then(r => r.ok ? r.json() : null).catch(() => null)));
  const missing = ['s2_cells.json', 's2_faces.json', 's2_seeds.json']
    .filter((fn, i) => opt[i] === null);
  if (missing.length) d.s2Missing = missing;
  else d.s2 = buildS2(d, opt[0], opt[1], opt[2]);
  // bbox — 카메라 맞춤 (면 우선, 없으면 점)
  const bb = { mn: [1e18, 1e18, 1e18], mx: [-1e18, -1e18, -1e18] };
  const feed = (x, y, z) => {
    if (x < bb.mn[0]) bb.mn[0] = x; if (x > bb.mx[0]) bb.mx[0] = x;
    if (y < bb.mn[1]) bb.mn[1] = y; if (y > bb.mx[1]) bb.mx[1] = y;
    if (z < bb.mn[2]) bb.mn[2] = z; if (z > bb.mx[2]) bb.mx[2] = z;
  };
  if (d.s2) d.s2.faces.forEach(f => (f.poly3d || []).forEach(p => feed(p[0], p[1], p[2])));
  else for (let i = 0; i < d.N; i++) feed(d.pos[i * 3], d.pos[i * 3 + 1], d.pos[i * 3 + 2]);
  d.bb = bb;
  return d;
}

// ---------- 씬 구축 — 면은 병합 BufferGeometry 묶음 + 삼각형→face 인덱스 맵 ----------
function buildFaceArrays(d) {
  const s2 = d.s2;
  // 픽/와이어는 도메인/내부 2분할 (도메인 외피 토글이 픽·표시 모두에서 빠지도록)
  const part = { inner: { tri: [], triFace: [], wire: [], wireFace: [] },
                 domain: { tri: [], triFace: [], wire: [], wireFace: [] } };
  s2.faceRange = [];   // per-face {part, triStart, triCount(정점수), wireStart, wireCount}
  s2.faces.forEach((f, fi) => {
    const poly = f.poly3d || [];
    const pt = f.domain ? part.domain : part.inner;
    const rec = { part: f.domain ? 'domain' : 'inner',
                  triStart: pt.tri.length, wireStart: pt.wire.length };
    for (let k = 1; k + 1 < poly.length; k++) {   // 부채꼴 삼각화 (페이지 1 관행)
      pt.tri.push(...poly[0], ...poly[k], ...poly[k + 1]);
      pt.triFace.push(fi);
    }
    for (let k = 0; k < poly.length; k++) {       // 닫힌 윤곽 세그먼트
      const a = poly[k], b = poly[(k + 1) % poly.length];
      pt.wire.push(a[0], a[1], a[2], b[0], b[1], b[2]);
      pt.wireFace.push(fi);
    }
    rec.triCount = pt.tri.length - rec.triStart;
    rec.wireCount = pt.wire.length - rec.wireStart;
    s2.faceRange.push(rec);
  });
  s2.part = {};
  for (const key of ['inner', 'domain']) {
    const p = part[key];
    const triPos = new Float32Array(p.tri);
    const wirePos = new Float32Array(p.wire);
    // 픽 메시 — opacity 0(표시 없음)·visible 유지 = 레이캐스트 대상 (페이지 1 관행)
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.BufferAttribute(triPos, 3));
    const pick = new THREE.Mesh(pg, new THREE.MeshBasicMaterial({
      transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false }));
    pick.userData = { kind: 'facepick', triFace: Uint32Array.from(p.triFace), part: key };
    pick.renderOrder = -1;
    // 와이어 — 정점색 RGB (제자리 재색칠, 지오메트리 재생성 없음)
    const wg = new THREE.BufferGeometry();
    wg.setAttribute('position', new THREE.BufferAttribute(wirePos, 3));
    wg.setAttribute('color', new THREE.BufferAttribute(new Float32Array(wirePos.length), 3));
    const wire = new THREE.LineSegments(wg, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.6 }));
    s2.part[key] = { triPos, pick, wire };
  }
}
function buildScene(d) {
  clear3d();
  // 맥락: footprint 윤곽 (ground_z / top_z — 페이지 1 관행)
  const fp = (d.view || {}).footprint_local;
  if (fp && fp.length >= 3) {
    for (const z of [d.view.ground_z, d.view.top_z]) {
      if (z === undefined || z === null) continue;
      const g = new THREE.BufferGeometry();
      const pts = [];
      fp.forEach(p => pts.push(p[0], p[1], z));
      g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
      ctxGroup.add(new THREE.LineLoop(g, new THREE.LineBasicMaterial({
        color: 0x556070, transparent: true, opacity: 0.55 })));
    }
  }
  // ALS prior 점 (앰버 — o_init 판정 입력이므로 기본 ON)
  if (d.alsLocals.length) {
    const apos = new Float32Array(d.alsLocals.length * 3);
    d.alsLocals.forEach((full, li) => {
      apos[li * 3] = d.pos[full * 3]; apos[li * 3 + 1] = d.pos[full * 3 + 1];
      apos[li * 3 + 2] = d.pos[full * 3 + 2];
    });
    const ag = new THREE.BufferGeometry();
    ag.setAttribute('position', new THREE.BufferAttribute(apos, 3));
    d.alsPoints = new THREE.Points(ag, new THREE.PointsMaterial({
      color: COL.als, size: 0.18, transparent: true, opacity: 0.85 }));
    ptsGroup.add(d.alsPoints);
  }
  if (d.s2) {
    if (!d.s2.part) buildFaceArrays(d);
    for (const key of ['inner', 'domain'])
      cellGroup.add(d.s2.part[key].pick, d.s2.part[key].wire);
    // 시드 점 (전수 — 게이트 0 면 포함, 수명 규칙 ②)
    const seeds = d.s2.seeds;
    if (seeds.length) {
      const sp = new Float32Array(seeds.length * 3);
      seeds.forEach((s, i) => { sp[i * 3] = s.mu[0]; sp[i * 3 + 1] = s.mu[1]; sp[i * 3 + 2] = s.mu[2]; });
      const sg = new THREE.BufferGeometry();
      sg.setAttribute('position', new THREE.BufferAttribute(sp, 3));
      sg.setAttribute('color', new THREE.BufferAttribute(new Float32Array(seeds.length * 3), 3));
      d.seedPoints = new THREE.Points(sg, new THREE.PointsMaterial({
        size: 0.09, vertexColors: true, transparent: true, opacity: 0.95 }));
      seedGroup.add(d.seedPoints);
    }
    restyle();
  }
  if (d.alsPoints) d.alsPoints.visible = state.showAls;
  if (state.lastFit !== d.name) {
    state.lastFit = d.name;
    orbit.target.set((d.bb.mn[0] + d.bb.mx[0]) / 2, (d.bb.mn[1] + d.bb.mx[1]) / 2,
                     (d.bb.mn[2] + d.bb.mx[2]) / 2);
    orbit.r = Math.hypot(d.bb.mx[0] - d.bb.mn[0], d.bb.mx[1] - d.bb.mn[1],
                         d.bb.mx[2] - d.bb.mn[2]) * 1.15 + 5;
    applyOrbit();
  }
}

// ---------- 뒤집기(화면 전용) — XOR 회계 ----------
function flipDelta(d, ci) {
  const s2 = d.s2, cell = s2.cells[ci];
  const res = { newFaces: [], goneFaces: [], areaNew: 0, areaGone: 0, dA: 0 };
  const flippedOcc = cell.o_state ? 0 : 1;
  for (const fi of s2.cellFaces[ci]) {
    const f = s2.faces[fi];
    const oa = (f.cell_a === cell.cell_id) ? flippedOcc : s2.occOf(f.cell_a);
    const ob = (f.cell_b === cell.cell_id) ? flippedOcc : s2.occOf(f.cell_b);
    const nw = Math.abs(oa - ob) === 1 ? 1 : 0;
    const old = s2.realNow[fi];       // o_state 산수 기준 (initial_real 불일치는 검사에 표기)
    if (nw && !old) { res.newFaces.push(fi); res.areaNew += (f.area_m2 || 0); }
    if (!nw && old) { res.goneFaces.push(fi); res.areaGone += (f.area_m2 || 0); }
  }
  res.dA = res.areaNew - res.areaGone;   // ΔA = Σ area·(new−old)
  return res;
}
function flipW(t) {   // 뒤집기 값 w·|log(t/(1−t))| — 초기 w=1. t∈{0,1} = 고정(∞)
  if (!(t > 0) || !(t < 1)) return Infinity;
  return Math.abs(Math.log(t / (1 - t)));
}

// ---------- 면 스타일 재적용 (채움 = 스타일별 병합 버킷 재구축, 와이어 = 제자리 색) ----------
const FILL_STYLE = {  // key: [hex, opacity, renderOrder] — planeGlow hex는 선택 평면 출처색으로 대체
  flipNew: [COL.flipNew, 0.55, 3], flipGone: [COL.flipGone, 0.55, 3],
  selFace: [COL.selFill, 0.55, 2], selCell: [COL.occ, 0.4, 2],
  planeGlow: [COL.selFill, 0.6, 3],
  real: [COL.real, 0.38, 1], sleep: [COL.sleep, 0.05, 0], occ: [COL.occ, 0.15, 1],
  // o_init 맵 (소프트 t 4범주) — 면은 인접 두 셀 중 큰 t(더 찬 진술 우선)로 칠한다.
  // 무점 0.4 = 증축 탐지 감도의 자리 → 보라 강조(소수 셀이 한눈에 떠야 함).
  tBelow: [0x4a9eff, 0.30, 1],    // 0.75 찼음 진술 — 켬 채움과 같은 청색 계열(연속성)
  tAbove: [0x9fb4cc, 0.05, 0],    // 0.15 비었음 진술 — 잠든 면 회청(물러남)
  tEmpty: [0xcf9bff, 0.42, 2],    // 0.4  무점(약한 진술) — 보라 강조
  tOutside: [0x556070, 0.06, 0],  // 0.0  footprint 밖 고정 — 맥락 회색
};
let fillBucketMeshes = [];
function restyle() {
  const d = state.run;
  if (!d || !d.s2) return;
  const s2 = d.s2;
  const selC = state.selCell, selF = state.selFace, selP = state.selPlane;
  // 절단 누적 재생 — 채움은 RGBA 정점색 단일 메시(제자리 갱신), 버킷 채움 없음
  const cs = d.cutSeq;
  const playing = state.playK !== null && !!cs;
  const playK = playing ? state.playK : -1;
  let fd = null;
  if (state.flip && selC !== null) fd = flipDelta(d, selC);
  const inNew = new Set(fd ? fd.newFaces : []), inGone = new Set(fd ? fd.goneFaces : []);
  const cellFaceSet = new Set(selC !== null ? s2.cellFaces[selC] : []);
  // 평면별 절단 보기 — 선택 평면이 만든 면 집합 + 출처색 발광
  const planeFaceSet = new Set(selP !== null ? (s2.facesByPlane[selP] || []) : []);
  const planeGlowHex = selP !== null
    ? (SRC_COLORS[(d.planeById[selP] || {}).source] ?? COL.selFill) : COL.selFill;
  // o_init 맵 — 셀 t를 4범주 키로 (manifest o_init_def.t 기준, 정확 일치 1e-9)
  const odT = (((d.manifest || {}).o_init_def || {}).t) || {};
  const tCats = [['tBelow', odT.below ?? 0.75], ['tAbove', odT.above ?? 0.15],
                 ['tEmpty', odT.empty ?? 0.4], ['tOutside', odT.outside ?? 0.0]];
  const tKeyOf = (t) => {
    for (const [k, v] of tCats) if (Math.abs(t - v) <= 1e-9) return k;
    return null;   // 범주 밖 t — 채움 없음(와이어만)
  };
  const cellT = (cid) => {
    if (cid === null || cid === undefined) return -Infinity;   // 도메인 밖 — 비직렬화
    const ci = s2.cellIdx[cid];
    return ci === undefined ? -Infinity : +s2.cells[ci].t;
  };
  // 1) 채움 버킷 결정 (평면 모드: 그 평면이 만든 면만 발광 채움, 나머지는 와이어 감광)
  // 재생 모드: 버킷 채움 전면 억제 — 칼금 자국은 cutMesh(RGBA)가, 감광은 와이어가 맡는다.
  const buckets = {};   // styleKey -> [faceIdx...]
  if (!playing) s2.faces.forEach((f, fi) => {
    if (f.domain && !state.showDomain) return;
    let key = null;
    if (selP !== null) {
      if (planeFaceSet.has(fi)) key = 'planeGlow';
    } else if (inNew.has(fi)) key = 'flipNew';
    else if (inGone.has(fi)) key = 'flipGone';
    else if (selF === fi) key = 'selFace';
    else if (cellFaceSet.has(fi)) key = 'selCell';
    else if (state.showFstar) key = f.initial_real ? 'real' : 'sleep';
    else if (state.cellColor === 't') {   // o_init 맵 — 인접 두 셀 중 큰 t(더 찬 진술 우선)
      const t = Math.max(cellT(f.cell_a), cellT(f.cell_b));
      key = Number.isFinite(t) ? tKeyOf(t) : null;
    }
    else if (s2.occOf(f.cell_a) || s2.occOf(f.cell_b)) key = 'occ';  // o=1 셀 반투명 채움
    if (key) (buckets[key] = buckets[key] || []).push(fi);
  });
  for (const m of fillBucketMeshes) {
    cellGroup.remove(m); m.geometry.dispose(); m.material.dispose();
  }
  fillBucketMeshes = [];
  for (const [key, fis] of Object.entries(buckets)) {
    const [hex0, opacity, ro] = FILL_STYLE[key];
    const hex = key === 'planeGlow' ? planeGlowHex : hex0;
    let total = 0;
    for (const fi of fis) total += s2.faceRange[fi].triCount;
    const arr = new Float32Array(total);
    let off = 0;
    for (const fi of fis) {
      const r = s2.faceRange[fi];
      arr.set(s2.part[r.part].triPos.subarray(r.triStart, r.triStart + r.triCount), off);
      off += r.triCount;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3));
    const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      color: hex, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false }));
    mesh.renderOrder = ro;
    cellGroup.add(mesh);
    fillBucketMeshes.push(mesh);
  }
  // 2) 와이어 — o_state=0 셀은 와이어로만 읽힌다 (혼잡 완화용 감광 포함)
  const cw = new THREE.Color();
  for (const key of ['inner', 'domain']) {
    const wire = s2.part[key].wire;
    wire.visible = state.showWire && (key === 'inner' || state.showDomain);
    s2.part[key].pick.visible = (key === 'inner' || state.showDomain);
  }
  const anySel = selC !== null || selF !== null || selP !== null;
  s2.faces.forEach((f, fi) => {
    const r = s2.faceRange[fi];
    const inPlane = selP !== null && planeFaceSet.has(fi);
    if (playing) {   // 재생 모드 — 평면 1..k의 면만 출처색, 현재 k 최대 밝기, 나머지 감광
      const kf = cs.faceCutK[fi];   // 0=도메인, 1..K=그 면을 만든 절단 평면의 k
      if (kf >= 1 && kf <= playK) {
        cw.setHex(cs.faceSrcHex[fi]);
        if (kf !== playK) cw.multiplyScalar(0.7);
      } else { cw.setHex(COL.wireDim); cw.multiplyScalar(0.5); }
      const attr0 = s2.part[r.part].wire.geometry.getAttribute('color');
      for (let k = 0; k < r.wireCount; k += 3) {
        attr0.array[r.wireStart + k] = cw.r;
        attr0.array[r.wireStart + k + 1] = cw.g;
        attr0.array[r.wireStart + k + 2] = cw.b;
      }
      return;
    }
    let hex = COL.wireDim;
    if (inPlane) hex = planeGlowHex;                       // 평면 모드 — 멤버 면 출처색 발광
    else if (state.showFstar && f.initial_real) hex = COL.wireReal;
    else if (s2.occOf(f.cell_a) || s2.occOf(f.cell_b)) hex = COL.wireOcc;
    cw.setHex(hex);
    if (anySel && !cellFaceSet.has(fi) && selF !== fi && !inPlane) cw.multiplyScalar(0.45);  // 감광
    const attr = s2.part[r.part].wire.geometry.getAttribute('color');
    for (let k = 0; k < r.wireCount; k += 3) {
      attr.array[r.wireStart + k] = cw.r;
      attr.array[r.wireStart + k + 1] = cw.g;
      attr.array[r.wireStart + k + 2] = cw.b;
    }
  });
  for (const key of ['inner', 'domain'])
    s2.part[key].wire.geometry.getAttribute('color').needsUpdate = true;
  // 2b) 절단 누적 재생 메시 — 지오메트리 재생성 없이 RGBA 정점색만 제자리 갱신
  if (playing) { ensureCutMesh(d); applyCutColors(d); }
  if (s2.cutMesh) s2.cutMesh.visible = playing;
  // 3) 시드 색 — 실재 면 위 vs 잠든 면 위, 선택 면·셀 위는 발광 (숨김 시 재색칠 생략)
  if (d.seedPoints) {
    seedGroup.visible = state.showSeeds;
    if (state.showSeeds) {
      const attr = d.seedPoints.geometry.getAttribute('color');
      const cReal = new THREE.Color(COL.seedReal), cSleep = new THREE.Color(COL.seedSleep),
            cGlow = new THREE.Color(COL.colGlow);
      for (let si = 0; si < s2.seeds.length; si++) {
        const fi = s2.seedFace[si];
        let c = cSleep;
        if (fi >= 0) {
          if (fi === selF || cellFaceSet.has(fi) || planeFaceSet.has(fi)) c = cGlow;
          else if (s2.faces[fi].initial_real) c = cReal;
        }
        attr.array[si * 3] = c.r; attr.array[si * 3 + 1] = c.g; attr.array[si * 3 + 2] = c.b;
      }
      attr.needsUpdate = true;
    }
  }
  // 4) 선택 윤곽 (맥동) + 표면고 기둥 + 증거 영역(S1 원형) 오버레이
  emptyGroup(selGroup); emptyGroup(colGroup); emptyGroup(evGroup); hiliteMats = [];
  // 증거 영역 — 평면별 절단 보기: 선택 평면의 S1 원형 / 재생: 현재 k 평면의 링 전부
  if (selP !== null) addEvidencePolys(d, [selP]);
  else if (playing && playK >= 1) addEvidencePolys(d, cs.seq[playK - 1].plane_ref || []);
  const outlineFis = selF !== null ? [selF] : [...cellFaceSet];
  if (outlineFis.length) {
    let total = 0;
    for (const fi of outlineFis) total += s2.faceRange[fi].wireCount;
    const arr = new Float32Array(total);
    let off = 0;
    for (const fi of outlineFis) {
      const r = s2.faceRange[fi];
      const wpos = s2.part[r.part].wire.geometry.getAttribute('position').array;
      arr.set(wpos.subarray(r.wireStart, r.wireStart + r.wireCount), off);
      off += r.wireCount;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3));
    const mat = new THREE.LineBasicMaterial({ color: COL.selFill, transparent: true, opacity: 1 });
    selGroup.add(new THREE.LineSegments(g, mat));
    hiliteMats.push(mat);
  }
  if (selC !== null) buildColumnOverlay(d, s2.cells[selC]);
  renderSelBadge();
}

// ---------- 표면고 기둥 카드 3D — 반경 0.75 m 원기둥 + 기둥 안 ALS 점 발광 + p90 높이선 ----------
function buildColumnOverlay(d, cell) {
  const surf = cell.surf || {};
  const cx = surf.cx ?? (cell.centroid || [])[0], cy = surf.cy ?? (cell.centroid || [])[1];
  if (cx === undefined || cy === undefined) return;
  const rad = surf.radius_m ?? 0.75;
  const z0 = (d.view || {}).ground_z ?? d.bb.mn[2], z1 = (d.view || {}).top_z ?? d.bb.mx[2];
  // 원기둥 측면 (수직 기둥 — three 원기둥 축 Y → Z 회전)
  const cyl = new THREE.Mesh(
    new THREE.CylinderGeometry(rad, rad, Math.max(z1 - z0, 0.1), 32, 1, true).rotateX(Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: COL.col, transparent: true, opacity: 0.10,
                                  side: THREE.DoubleSide, depthWrite: false }));
  cyl.position.set(cx, cy, (z0 + z1) / 2);
  colGroup.add(cyl);
  // 셀 중심(판정 표본점 — r16: 단일 셀중심 기둥) + 수직 안내선
  const cg = new THREE.BufferGeometry();
  cg.setAttribute('position', new THREE.Float32BufferAttribute(cell.centroid || [cx, cy, z0], 3));
  colGroup.add(new THREE.Points(cg, new THREE.PointsMaterial({
    color: 0xffffff, size: 0.4 })));
  const lg = new THREE.BufferGeometry();
  lg.setAttribute('position', new THREE.Float32BufferAttribute([cx, cy, z0, cx, cy, z1], 3));
  colGroup.add(new THREE.Line(lg, new THREE.LineBasicMaterial({
    color: COL.col, transparent: true, opacity: 0.5 })));
  // p90 높이선 (z_surf 링) — 무점이면 없음
  if (surf.z_surf !== null && surf.z_surf !== undefined) {
    const ring = [];
    for (let k = 0; k < 48; k++) {
      const a = k / 48 * Math.PI * 2;
      ring.push(cx + rad * Math.cos(a), cy + rad * Math.sin(a), surf.z_surf);
    }
    const rg = new THREE.BufferGeometry();
    rg.setAttribute('position', new THREE.Float32BufferAttribute(ring, 3));
    colGroup.add(new THREE.LineLoop(rg, new THREE.LineBasicMaterial({ color: COL.p90 })));
  }
  // 기둥 안 ALS 점 발광 (col_pt_idx — s1_points.ply 행 인덱스, 전부 source==1 계약)
  const idxs = surf.col_pt_idx || [];
  if (idxs.length) {
    const pp = new Float32Array(idxs.length * 3);
    idxs.forEach((pi, k) => {
      if (pi >= 0 && pi < d.N) {
        pp[k * 3] = d.pos[pi * 3]; pp[k * 3 + 1] = d.pos[pi * 3 + 1];
        pp[k * 3 + 2] = d.pos[pi * 3 + 2];
      }
    });
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.BufferAttribute(pp, 3));
    colGroup.add(new THREE.Points(pg, new THREE.PointsMaterial({
      color: COL.colGlow, size: 0.3 })));
  }
}

// ---------- S1 평면 → 셀 절단 인과 ----------
// 증거 영역(S1 원형 support_local) — 출처색 반투명 0.35 + 윤곽 (부채꼴 삼각화, 페이지 1 관행)
function addEvidencePolys(d, pids) {
  for (const pid of pids) {
    const p = d.planeById[pid];
    const ring = (p || {}).support_local || [];
    if (ring.length < 3) continue;
    const hex = SRC_COLORS[p.source] ?? 0x888888;
    const tri = [];
    for (let k = 1; k + 1 < ring.length; k++)
      tri.push(...ring[0], ...ring[k], ...ring[k + 1]);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(tri, 3));
    const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      color: hex, transparent: true, opacity: 0.35,
      side: THREE.DoubleSide, depthWrite: false }));
    mesh.renderOrder = 4;
    evGroup.add(mesh);
    const flat = [];
    ring.forEach(v => flat.push(v[0], v[1], v[2]));
    const lg = new THREE.BufferGeometry();
    lg.setAttribute('position', new THREE.Float32BufferAttribute(flat, 3));
    evGroup.add(new THREE.LineLoop(lg, new THREE.LineBasicMaterial({
      color: hex, transparent: true, opacity: 0.9 })));
  }
}
// s2_cut_sequence.json lazy fetch + 색인 (writer --cut-sequence-only 산출물)
async function loadCutSeq(d) {
  if (d.cutSeq || d.cutSeqError || !d.s2) return d.cutSeq;
  try {
    const r = await fetch(`../runs/${d.name}/s2_cut_sequence.json`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const doc = await r.json();
    const seq = doc.sequence || [];
    const K = seq.length;
    const idToK = {};   // s1 p### → 그 링을 처음 자른 접두 k (같은 (n,d) 중복은 첫 절단)
    seq.forEach(e => (e.plane_ref || []).forEach(pid => {
      if (!(pid in idToK)) idToK[pid] = e.k;
    }));
    const s2 = d.s2;
    const faceCutK = new Int32Array(s2.faces.length);   // 0=도메인/미상
    const faceSrcHex = new Array(s2.faces.length).fill(0x888888);
    s2.faces.forEach((f, fi) => {
      if (f.domain) return;
      let m = Infinity;
      for (const pid of (f.s1_plane_ids || []))
        if (idToK[pid] !== undefined && idToK[pid] < m) m = idToK[pid];
      faceCutK[fi] = Number.isFinite(m) ? m : 0;
      const p0 = d.planeById[(f.s1_plane_ids || [])[0]];
      faceSrcHex[fi] = SRC_COLORS[(p0 || {}).source] ?? 0x888888;
    });
    const base = doc.baseline || {};
    const nCellsByK = [base.n_cells ?? 1];
    seq.forEach(e => nCellsByK.push(e.n_cells));
    let mismatch = null;
    if (!K) mismatch = 'sequence 비어 있음';
    else if (seq[K - 1].n_cells !== s2.cells.length ||
             seq[K - 1].n_faces !== s2.faces.length)
      mismatch = `cut_sequence 최종 ${seq[K - 1].n_cells}셀/${seq[K - 1].n_faces}면 ≠ ` +
                 `s2 ${s2.cells.length}셀/${s2.faces.length}면 — 세대 불일치`;
    d.cutSeq = { doc, seq, K, idToK, faceCutK, faceSrcHex, nCellsByK,
                 baseCells: base.n_cells ?? 1, baseNote: base.note || null,
                 mismatch, used: false, lastK: null, chartDims: null };
  } catch (e) { d.cutSeqError = e.message; }
  return d.cutSeq;
}
// 칼금 자국 메시 — 위치는 기존 inner triPos 공유(1회 구축), 이후 RGBA만 제자리 갱신
function ensureCutMesh(d) {
  const s2 = d.s2;
  if (!s2.cutMesh) {
    const pos = s2.part.inner.triPos;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.BufferAttribute(
      new Float32Array((pos.length / 3) * 4), 4));   // RGBA — 정점 알파
    const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      vertexColors: true, transparent: true,
      side: THREE.DoubleSide, depthWrite: false }));
    mesh.renderOrder = 2;
    s2.cutMesh = mesh;
  }
  if (s2.cutMesh.parent !== cutGroup) cutGroup.add(s2.cutMesh);
  return s2.cutMesh;
}
function applyCutColors(d) {
  const cs = d.cutSeq, s2 = d.s2, k = state.playK;
  if (!cs || !s2.cutMesh) return;
  const attr = s2.cutMesh.geometry.getAttribute('color');
  const arr = attr.array;
  const col = new THREE.Color();
  s2.faces.forEach((f, fi) => {
    const r = s2.faceRange[fi];
    if (r.part !== 'inner') return;
    const kf = cs.faceCutK[fi];
    const a = (kf >= 1 && kf <= k) ? (kf === k ? 0.8 : 0.4) : 0.0;
    col.setHex(cs.faceSrcHex[fi]);
    const nVert = r.triCount / 3;
    let off = (r.triStart / 3) * 4;
    for (let v = 0; v < nVert; v++) {
      arr[off] = col.r; arr[off + 1] = col.g; arr[off + 2] = col.b; arr[off + 3] = a;
      off += 4;
    }
  });
  attr.needsUpdate = true;
}
// 재생 위치 이동 — 진입 시 선택 해제(배타), 스크럽은 제자리 갱신(전체 패널 재렌더 없음)
function setPlayK(k) {
  const d = state.run;
  if (!d || !d.cutSeq) return;
  const cs = d.cutSeq;
  k = Math.max(0, Math.min(cs.K, Math.round(k)));
  const entering = state.playK === null;
  if (!entering && state.playK === k) return;
  if (entering) {
    state.selCell = null; state.selFace = null; state.selPlane = null; state.flip = false;
  }
  state.playK = k;
  cs.used = true; cs.lastK = k;
  restyle();
  if (entering) renderPanel(); else updateCutReadout();
}
function planeChipSpan(d, pid) {   // data-pid 없는 표시 전용 칩 (행 클릭과 중복 방지)
  const p = d.planeById[pid] || {};
  const css = srcCss(p.source);
  return `<span class="pchip" style="color:${css};border-color:${css}55">${esc(pid)}</span>`;
}
// 미니 곡선 k vs 누적 내부 셀 수 — 단일 계열(2px), 현재 k 마커(r4 + 표면 링), 축 회색 실선
function cutChartSvg(d) {
  const cs = d.cutSeq;
  const W = 384, H = 86, padL = 40, padR = 34, padT = 12, padB = 16;
  const ymax = Math.max(...cs.nCellsByK, 1);
  cs.chartDims = { W, H, padL, padR, padT, padB, ymax };
  const x = (k) => padL + (W - padL - padR) * (cs.K ? k / cs.K : 0);
  const y = (v) => padT + (H - padT - padB) * (1 - v / ymax);
  const pts = cs.nCellsByK.map((v, k) => `${x(k).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const k0 = state.playK ?? cs.K;
  return `<svg id="cutChart" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"
      style="display:block;margin:6px 0;max-width:100%;cursor:crosshair;touch-action:none">
    <line x1="${padL}" y1="${y(0)}" x2="${W - padR}" y2="${y(0)}" stroke="#2e3542"/>
    <line x1="${padL}" y1="${y(ymax)}" x2="${W - padR}" y2="${y(ymax)}" stroke="#2e3542"/>
    <text x="${padL - 5}" y="${y(ymax) + 3.5}" fill="#9fb4cc" font-size="10" text-anchor="end">${ymax}</text>
    <text x="${padL - 5}" y="${y(0) + 3.5}" fill="#9fb4cc" font-size="10" text-anchor="end">0</text>
    <text x="${padL}" y="${H - 4}" fill="#7a8494" font-size="10" text-anchor="middle">k=0</text>
    <text x="${W - padR}" y="${H - 4}" fill="#7a8494" font-size="10" text-anchor="middle">${cs.K}</text>
    <polyline points="${pts}" fill="none" stroke="#8ecbff" stroke-width="2"
      stroke-linejoin="round" stroke-linecap="round"/>
    <text x="${W - padR + 5}" y="${y(cs.nCellsByK[cs.K]) + 3.5}" fill="#dde3ea"
      font-size="10">${cs.nCellsByK[cs.K]}</text>
    <circle id="cutMark" cx="${x(k0).toFixed(1)}" cy="${y(cs.nCellsByK[k0]).toFixed(1)}"
      r="4" fill="#8ecbff" stroke="#1b1f27" stroke-width="2"/>
  </svg>`;
}
// 파편화 랭킹 — delta_cells 내림차순 상위 10 (행 클릭 = 평면별 절단 보기 전환)
function cutRankHtml(d) {
  const cs = d.cutSeq;
  const rows = [...cs.seq]
    .sort((a, b) => (b.delta_cells - a.delta_cells) || (a.k - b.k)).slice(0, 10)
    .map((e, i) => {
      const pid = (e.plane_ref || [])[0];
      const p = d.planeById[pid] || {};
      const more = (e.plane_ref || []).length - 1;
      return `<tr data-pid="${escAttr(pid)}" class="${state.selPlane === pid ? 'sel' : ''}">
        <td>${i + 1}</td>
        <td class="l">${planeChipSpan(d, pid)}${more > 0 ? `<span class="note">외 ${more}</span>` : ''}</td>
        <td class="l" style="color:${srcCss(p.source)}">${esc(SRC_LABEL[p.source] || p.source || '?')}</td>
        <td>${e.k}</td>
        <td><b>${e.delta_cells >= 0 ? '+' : ''}${e.delta_cells}</b></td>
        <td>${e.n_cells}</td></tr>`;
    }).join('');
  return `<div class="scrollbox"><table>
    <tr><th>#</th><th class="l">평면 (클릭=평면별 절단 보기)</th><th class="l">출처</th>
      <th>k</th><th>Δ셀</th><th>누적</th></tr>${rows}</table></div>`;
}
function cutSeqSectionHtml(d) {
  let h = `<h2>절단 누적 재생 — S1 평면 → 셀 절단 인과
    <span class="note">(재생 ↔ 선택 배타 · ESC=해제)</span></h2>`;
  const cs = d.cutSeq;
  if (d.cutSeqError) {
    h += `<div class="card"><span class="note">s2_cut_sequence.json 없음(${esc(d.cutSeqError)})
      — writer <b>build_s2_bundle.py --cut-sequence-only</b> 실행 후 새로고침.</span></div>`;
  } else if (!cs) {
    h += `<div class="card">접두 배열 통계는 필요할 때만 내려받는다(lazy).
      <button class="small" id="cutLoad">절단 재생 데이터 로드</button></div>`;
  } else {
    const K = cs.K, k = state.playK;
    h += `<div class="card">
      <div class="note caption">증거 영역(S1 원형) → 무한 절단(§1.1 그림 B) → 셀
        — 한 칼질이 도메인 전체를 지나며 셀을 쪼갠다</div>`;
    if (cs.mismatch) h += `<div class="err">${esc(cs.mismatch)}</div>`;
    if (k === null) {
      h += `<div><button class="small" id="cutPlay" ${cs.mismatch ? 'disabled' : ''}>재생 시작 (k=0)</button>
        <span class="note">K=${K} · 최종 ${cs.nCellsByK[K]}셀 · 곡선 클릭으로도 진입</span></div>`;
    } else {
      h += `<div style="display:flex;gap:6px;align-items:center">
          <button class="small" id="cutPrev">◀</button>
          <input type="range" id="cutK" min="0" max="${K}" step="1" value="${k}" style="flex:1">
          <button class="small" id="cutNext">▶</button>
          <button class="small" id="cutExit">종료</button></div>
        <div id="cutkline" style="margin:5px 0 2px"></div>`;
    }
    h += cutChartSvg(d) +
      `<div class="note">k vs 누적 내부 셀 수 — writer가 build_arrangement(레거시 무수정)를
        평면 1..k 접두로 재실행한 실측(연속 접두 차 = delta). 절단 순서는 구축 순서이며 최종
        배열은 순서 불변(order_note). 곡선 클릭/드래그·◀▶·←→ = k 이동.</div></div>
      <div style="margin:6px 0 2px"><b>파편화 랭킹</b>
        <span class="note">delta_cells 상위 10 — 한 칼질의 셀 증가(과분할 진단)</span></div>` +
      cutRankHtml(d);
  }
  return h;
}
// 스크럽 제자리 갱신 — 패널 전체 재렌더 없이 읽기줄·슬라이더·차트 마커만
function updateCutReadout() {
  const d = state.run;
  if (!d || !d.cutSeq) return;
  const cs = d.cutSeq, k = state.playK;
  const sl = $('#cutK');
  if (sl && k !== null && +sl.value !== k) sl.value = k;
  const line = $('#cutkline');
  if (line) {
    if (k === null) line.innerHTML = '';
    else if (k === 0) {
      line.innerHTML = `<b>0/${cs.K}</b> · 절단 전 — footprint 프리즘 내부 <b>${cs.baseCells}</b>셀` +
        (cs.baseNote ? ` <span class="note">(${esc(cs.baseNote)})</span>` : '');
    } else {
      const e = cs.seq[k - 1];
      const pid = (e.plane_ref || [])[0];
      const p = d.planeById[pid] || {};
      line.innerHTML = `<b>${k}/${cs.K}</b> · ${planeChipSpan(d, pid)}
        <span style="color:${srcCss(p.source)}">${esc(SRC_LABEL[p.source] || p.source || '?')}</span>
        · 이 칼질로 셀 <b class="warn">${e.delta_cells >= 0 ? '+' : ''}${e.delta_cells}</b>
        (누적 <b>${e.n_cells}</b>셀 · 면 ${e.n_faces})`;
    }
  }
  const mark = $('#cutMark');
  if (mark && cs.chartDims) {
    const dm = cs.chartDims, kk = k ?? cs.K;
    mark.setAttribute('cx', (dm.padL + (dm.W - dm.padL - dm.padR)
      * (cs.K ? kk / cs.K : 0)).toFixed(1));
    mark.setAttribute('cy', (dm.padT + (dm.H - dm.padT - dm.padB)
      * (1 - cs.nCellsByK[kk] / dm.ymax)).toFixed(1));
  }
  renderSelBadge();
}

function renderSelBadge() {
  const el = $('#selbadge');
  if (!el) return;
  const d = state.run;
  if (!d || !d.s2 ||
      (state.selCell === null && state.selFace === null && state.selPlane === null &&
       state.playK === null)) {
    el.style.display = 'none'; return;
  }
  el.style.display = 'block';
  if (state.playK !== null && d.cutSeq) {
    const cs = d.cutSeq, k = state.playK;
    if (k === 0) {
      el.innerHTML = `<b style="color:#8ecbff">절단 재생 0/${cs.K}</b> · 절단 전
        (내부 ${cs.baseCells}셀) <span class="note">◀▶·←→·슬라이더 = 진행 · ESC=종료</span>`;
    } else {
      const e = cs.seq[k - 1];
      const pid = (e.plane_ref || [])[0], p = d.planeById[pid] || {};
      el.innerHTML = `<b style="color:#8ecbff">절단 재생 ${k}/${cs.K}</b> ·
        <b style="color:${srcCss(p.source)}">${esc(pid)}</b>
        ${esc(SRC_LABEL[p.source] || p.source || '?')} ·
        이 칼질로 셀 ${e.delta_cells >= 0 ? '+' : ''}${e.delta_cells}
        (누적 ${e.n_cells}) <span class="note">ESC=종료</span>`;
    }
    return;
  }
  if (state.selPlane !== null) {
    const pid = state.selPlane, p = d.planeById[pid] || {};
    const nf = (d.s2.facesByPlane[pid] || []).length;
    const nc = (d.s2.cellsByCutPlane[pid] || []).length;
    el.innerHTML = `<b style="color:${srcCss(p.source)}">${esc(pid)}</b> ·
      ${esc(SRC_LABEL[p.source] || p.source || '?')} ·
      <b>이 평면이 만든 면 ${nf}개 / 잘린 셀 ${nc}개</b>
      <span class="note">재클릭·빈 공간·ESC=해제</span>`;
  } else if (state.selCell !== null) {
    const c = d.s2.cells[state.selCell];
    el.innerHTML = `<b style="color:#ffe066">${esc(c.cell_id)}</b> ·
      o=${c.o_state} · t=${(+c.t).toFixed(2)} · ${esc(VERDICT_KO[(c.surf || {}).verdict] || '—')}
      ${state.flip ? '<span class="flipnew">[뒤집기 미리보기]</span>' : ''}
      <span class="note">재클릭·빈 공간·ESC=해제</span>`;
  } else {
    const f = d.s2.faces[state.selFace];
    el.innerHTML = `<b style="color:#ffe066">${esc(f.face_id)}</b> ·
      ${f.initial_real ? 'F* 실재' : '게이트 0(잠든 면)'} ·
      ${f.domain ? '도메인 ' + esc(f.domain) : (f.s1_plane_ids || []).length + '개 평면'} ·
      ${(f.area_m2 ?? 0).toFixed(2)} m² <span class="note">재클릭·빈 공간·ESC=해제</span>`;
  }
}

// ---------- 선택 (절단 재생 모드와 배타 — 어느 한쪽 진입 시 다른 쪽 해제) ----------
function clearSelection() {
  state.selCell = null; state.selFace = null; state.selPlane = null; state.flip = false;
  state.playK = null;
  restyle(); renderPanel();
}
function selectCell(ci) {
  if (state.selCell === ci) { clearSelection(); return; }
  state.selCell = ci; state.selFace = null; state.selPlane = null; state.flip = false;
  state.playK = null;
  restyle(); renderPanel();
  const key = 'c' + ci;
  const row = document.querySelector(`#panel tr[data-cid="${key}"]`);
  if (row) row.scrollIntoView({ block: 'nearest' });
}
function selectFace(fi) {
  if (state.selFace === fi) { clearSelection(); return; }
  state.selFace = fi; state.selCell = null; state.selPlane = null; state.flip = false;
  state.playK = null;
  restyle(); renderPanel();
}
// 평면별 절단 보기 — 셀/면 선택·재생 모드와 배타 전환(랭킹 행/칩 클릭 = 이 보기), 재클릭=해제
function selectPlane(pid) {
  if (state.selPlane === pid || pid === null || pid === undefined) { clearSelection(); return; }
  state.selPlane = pid; state.selCell = null; state.selFace = null; state.flip = false;
  state.playK = null;
  restyle(); renderPanel();
  const row = document.querySelector(`#panel tr[data-pid="${CSS.escape(pid)}"]`);
  if (row) row.scrollIntoView({ block: 'nearest' });
}
const raycaster = new THREE.Raycaster();
function pickAt(e) {
  const d = state.run;
  if (!d || !d.s2 || !renderer) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1,
                                -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const picks = [];
  for (const key of ['inner', 'domain'])
    if (d.s2.part[key].pick.visible) picks.push(d.s2.part[key].pick);
  const hits = picks.length ? raycaster.intersectObjects(picks, false) : [];
  if (!hits.length) {
    if (state.selCell !== null || state.selFace !== null || state.selPlane !== null ||
        state.playK !== null) clearSelection();
    return;
  }
  const h = hits[0];
  const fi = h.object.userData.triFace[h.faceIndex];
  if (state.pickMode === 'face') { selectFace(fi); return; }
  // 셀 모드: 광선이 통과해 들어가는 쪽(면 뒤의 셀)을 선택 — 채워진 셀을 보고 클릭하는 직관
  const f = d.s2.faces[fi];
  const dir = raycaster.ray.direction;
  let target = null;
  for (const cid of [f.cell_a, f.cell_b]) {
    if (cid === null || cid === undefined) continue;
    const ci = d.s2.cellIdx[cid];
    if (ci === undefined) continue;
    const c = d.s2.cells[ci].centroid || [0, 0, 0];
    const dot = dir.x * (c[0] - h.point.x) + dir.y * (c[1] - h.point.y) + dir.z * (c[2] - h.point.z);
    if (dot > 0) { target = ci; break; }
    if (target === null) target = ci;   // 후보 유지 (양쪽 다 카메라 쪽이면 첫 실재 셀)
  }
  if (target !== null) selectCell(target);
  else selectFace(fi);   // 양쪽 모두 실재하지 않는 참조 오류 면 — 면 카드로 폴백
}

// ---------- 체크리스트 (5항 — 참고 기준, 엄격 합불 아님: 판독 기록 2026-08-27 방침) ----------
function renderChecklist() {
  const d = state.run;
  if (!d) { $('#checkstrip').innerHTML = '<span class="note">런 없음</span>'; return; }
  const s2 = d.s2;
  const na = (t) => `<span class="badge na">${t}</span>`;
  let b1 = na('S2 없음'), b2 = na('S2 없음'), b5 = na('S2 없음');
  if (s2) {
    const ck = s2.checks;
    b1 = `<span class="badge ${ck.refErrors === 0 ? 'good' : 'bad'}">오류 ${ck.refErrors}</span>`;
    const v = ck.volume;
    b2 = v.rel === null ? na('프리즘 부피 없음')
      : `<span class="badge ${v.pass ? 'good' : 'bad'}">상대 ${v.rel.toExponential(1)} ${v.pass ? '≤' : '>'} 1e-3</span>`;
    b5 = `<span class="badge ${ck.seedCover.pass ? 'good' : 'bad'}">보유면 ${ck.seedCover.have}/${ck.seedCover.total}</span>`;
  }
  const od = (d.manifest || {}).o_init_def || {};
  const ot = od.t || {};
  $('#checkstrip').innerHTML = `
    <div class="chkrow">
      <span class="chkitem"><b>①</b> 참조 무결성 오류 0(면→셀·평면, 시드→면 — 로드 시 자체 검사) ${b1}</span>
      <span class="chkitem"><b>②</b> Σ셀 부피 = 프리즘 부피 ${b2}</span>
      <span class="chkitem"><b>③</b> 분류-붕괴 건물(B036)에서 표면고 판정 정상 — 면역 확인 ${na('육안')}</span>
      <span class="chkitem"><b>④</b> 초기 경계가 prior 형상으로 읽힘 ${na('육안')}</span>
      <span class="chkitem"><b>⑤</b> 시드가 게이트 0 면에도 존재(수명 규칙 ②) ${b5}</span>
    </div>
    <div class="chkrow meta">
      <span><span class="badge prop">참고 기준</span> 엄격 런별 합불 아님 — 판독 기록 2026-08-27 방침(발견 기록으로 갈음).</span>
      <span>o_init(r16): 셀 중심 단일 기둥 r=${od.radius_m ?? 0.75} m · ${od.stat || 'p90'} ·
        t 아래 ${ot.below ?? 0.75}/위 ${ot.above ?? 0.15}/무점 ${ot.empty ?? 0.4}/밖 ${ot.outside ?? 0.0} ·
        ALS 전용${od.als_only === false ? ' 아님(!)' : ''} · o_state=[t>0.5] 반올림 · 소프트 t는 앵커 목표 존속</span>
    </div>`;
}

// ---------- 우측 패널 ----------
function reading() {
  return state.reading[state.runName] ||
    (state.reading[state.runName] = { verdict: null, memo: '', sign: '' });
}
function fmt(v, n = 2) { return (v === null || v === undefined || Number.isNaN(+v)) ? '—' : (+v).toFixed(n); }
// t 값 표기 — 0→"0.0", 0.4→"0.4", 0.75→"0.75" (스펙 표기 관행)
function fmtT(v) { return (+v).toFixed(2).replace(/0$/, ''); }
function faceLabel(d, f) {
  if (f.domain) return `도메인 ${esc(f.domain)}`;
  const ids = f.s1_plane_ids || [];
  return ids.length ? ids.map(esc).join(' ') : '—';
}
function page1Link(d, pid) {
  return `../viewer_p1/?run=${encodeURIComponent(state.runName)}&plane=${encodeURIComponent(pid)}`;
}
// 절단 평면 출처색 칩 — 클릭 = 평면별 절단 보기 전환 (bindPanel [data-pid])
function planeChip(d, pid) {
  const p = d.planeById[pid] || {};
  const css = srcCss(p.source);
  return `<a href="#" class="pchip" data-pid="${escAttr(pid)}" title="${escAttr(SRC_LABEL[p.source] || p.source || '?')} · 클릭=평면별 절단 보기"
    style="color:${css};border-color:${css}55">${esc(pid)}</a>`;
}
// ---------- 출발 상태 요약 (변수 4군 — 런 로드 시 자동) ----------
function computeStartState(d) {
  const s2 = d.s2;
  if (!s2) return null;
  const od = (d.manifest || {}).o_init_def || {};
  const tDef = od.t || {};
  const tOrder = [['below', tDef.below ?? 0.75], ['above', tDef.above ?? 0.15],
                  ['empty', tDef.empty ?? 0.4], ['outside', tDef.outside ?? 0.0]];
  const tCnt = tOrder.map(() => 0);
  let tOther = 0, occOn = 0;
  s2.cells.forEach(c => {
    if (c.o_state === 1) occOn++;
    const k = tOrder.findIndex(([, v]) => Math.abs((+c.t) - v) <= 1e-9);
    if (k >= 0) tCnt[k]++; else tOther++;
  });
  const bySrc = {};
  (d.planes.planes || []).forEach(p => { bySrc[p.source] = (bySrc[p.source] || 0) + 1; });
  return { occOn, occOff: s2.cells.length - occOn, tOrder, tCnt, tOther,
           nPlanes: (d.planes.planes || []).length, bySrc };
}
function startStateCardHtml(d) {
  const ss = computeStartState(d);
  if (!ss) return '';
  const tTxt = ss.tOrder.map(([k, v], i) =>
    `${T_KO[k] || k} ${fmtT(v)}: <b>${ss.tCnt[i]}</b>`).join(' · ') +
    (ss.tOther ? ` · 기타 ${ss.tOther}` : '');
  const srcTxt = Object.entries(ss.bySrc).map(([s, n]) =>
    `<span style="color:${srcCss(s)}">${esc(SRC_LABEL[s] || s)} ${n}</span>`).join(' · ');
  return `<div class="card">
    <div class="note caption">S2가 만드는 초기값의 본체 = o_state·t; P⁰=S1, δ·색=정의</div>
    <table>
      <tr><th class="l">변수군</th><th class="l">출발값</th></tr>
      <tr><td class="l">점유 o (이산)</td><td class="l">켬 <b>${ss.occOn}</b> / 끔 <b>${ss.occOff}</b> 셀 ·
        t 분포 — ${tTxt}</td></tr>
      <tr><td class="l">평면 P⁰</td><td class="l">${ss.nPlanes}장 — ${srcTxt || '—'}</td></tr>
      <tr><td class="l">δ</td><td class="l">0 (정의)</td></tr>
      <tr><td class="l">색</td><td class="l">중립 회색 (정의)</td></tr>
    </table></div>`;
}
// o_init 맵 범례 — 4범주 값의 뜻 + 셀 수 (색은 FILL_STYLE.t* 와 동일 원천)
function tLegendCardHtml(d) {
  const ss = computeStartState(d);
  if (!ss) return '';
  const sw = (key) => {
    const [hex] = FILL_STYLE[key];
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;
      margin-right:4px;vertical-align:middle;background:#${hex.toString(16).padStart(6, '0')}"></span>`;
  };
  const MEAN = {
    below: [`tBelow`, `찼음 진술 — 셀 중심이 기둥 p90 표면고 아래(내부)`],
    above: [`tAbove`, `비었음 진술 — 표면고 위(외부)`],
    empty: [`tEmpty`, `<b>무점(약한 진술)</b> — 기둥에 ALS 점 없음 · 증축 탐지 감도의 자리(r16 재선정 0.4)`],
    outside: [`tOutside`, `footprint 밖 — o=0 고정`],
  };
  const rows = ss.tOrder.map(([k, v], i) => {
    const [styleKey, meaning] = MEAN[k] || ['occ', k];
    return `<tr><td class="l">${sw(styleKey)}t=${fmtT(v)}</td>
      <td class="l">${meaning}</td><td><b>${ss.tCnt[i]}</b>셀</td></tr>`;
  }).join('');
  return `<div class="card">
    <div class="note caption">앵커 항 C_k에 들어가는 셀-단위 초기값 = t (loss의 사전 항 단위)</div>
    <table><tr><th class="l">값</th><th class="l">뜻</th><th>셀</th></tr>${rows}</table>
    <div class="note" style="margin-top:3px">면 색 = 인접 두 셀 중 큰 t(더 찬 진술 우선) ·
      ${ss.tOther ? `범주 밖 t ${ss.tOther}셀(채움 없음) · ` : ''}켬/끔 라디오로 복귀</div></div>`;
}
// ---------- 평면별 절단 보기 (조각 진단) ----------
function planeCardHtml(d, pid) {
  const s2 = d.s2, p = d.planeById[pid];
  const fis = s2.facesByPlane[pid] || [];
  const cis = s2.cellsByCutPlane[pid] || [];
  let area = 0;
  for (const fi of fis) area += (s2.faces[fi].area_m2 || 0);
  const css = srcCss((p || {}).source);
  return `<div class="card"><b style="color:${css}">${esc(pid)}</b>
    <span style="color:${css}">${esc(SRC_LABEL[(p || {}).source] || (p || {}).source || '실재하지 않음')}</span>
    <button class="small" id="planeClear" style="float:right">해제</button>
    <div class="note caption" style="margin-top:5px">증거 영역(S1 원형)
      <span style="color:${css}">■0.35</span> → 무한 절단(§1.1 그림 B)
      <span style="color:${css}">발광 단면</span> → 셀</div>
    <div style="margin:5px 0"><b>이 평면이 만든 면 ${fis.length}개 / 잘린 셀 ${cis.length}개</b>
      <span class="note">— 조각(과분할) 진단 축</span></div>
    ${fis.length === 0 ? `<div class="note" style="margin:3px 0">0면 = 배열 비기여 —
      같은 절단 평면으로 병합됐거나 도메인(프리즘) 안에서 면을 만들지 못한 평면(데이터 사실).</div>` : ''}
    <table>
      <tr><td class="l">면 (s1_plane_ids ∋ 이 평면)</td><td class="l">${fis.length}개 · Σ면적 ${fmt(area)} m²</td></tr>
      <tr><td class="l">잘린 셀 (cut_plane_ids ∋ 이 평면)</td><td class="l">${cis.length}개</td></tr>
      <tr><td class="l">inlier</td><td class="l">${(p || {}).inlier_count ?? '—'}</td></tr>
    </table>
    <div style="margin-top:5px"><a href="${page1Link(d, pid)}" style="color:#8ecbff">페이지 1에서 이 평면 보기 ↗</a></div>
    <div class="note" style="margin-top:3px">3D: 증거 영역(S1 원형 support_local) 출처색 반투명
      + 이 평면이 만든 면(무한 절단 단면)만 출처색 발광 · 나머지 감광 · 잘린 셀 표시 유지.
      재클릭·빈 공간·ESC=해제.</div></div>`;
}
function planeListHtml(d) {
  const s2 = d.s2;
  const rows = (d.planes.planes || []).map(p => {
    const pid = p.plane_id;
    const nf = (s2.facesByPlane[pid] || []).length, nc = (s2.cellsByCutPlane[pid] || []).length;
    return `<tr data-pid="${escAttr(pid)}" class="${state.selPlane === pid ? 'sel' : ''}">
      <td class="l">${esc(pid)}</td>
      <td class="l" style="color:${srcCss(p.source)}">${esc(SRC_LABEL[p.source] || p.source)}</td>
      <td>${p.inlier_count ?? '—'}</td><td>${nf}</td><td>${nc}</td></tr>`;
  }).join('');
  return `<div class="scrollbox"><table>
    <tr><th class="l">평면(클릭=절단 보기)</th><th class="l">출처</th><th>inlier</th><th>면</th><th>셀</th></tr>
    ${rows}</table></div>`;
}
function cellCardHtml(d, ci) {
  const s2 = d.s2, c = s2.cells[ci], surf = c.surf || {};
  const w = flipW(c.t);
  const wTxt = Number.isFinite(w) ? w.toFixed(2) : '∞ (t 고정)';
  const fd = state.flip ? flipDelta(d, ci) : null;
  let flipHtml;
  if (c.fixed) {
    flipHtml = `<div class="note">고정 셀(footprint 밖, o=0 고정) — 점유 뒤집기 없음</div>`;
  } else {
    flipHtml = `<div class="legend" style="margin-top:5px">
      <label><input type="checkbox" id="flipTgl" ${state.flip ? 'checked' : ''}>
        <b class="warn">점유 뒤집기</b> (화면 전용 — 데이터 변경 없음)</label>
      <button class="small" id="flipReset" ${state.flip ? '' : 'disabled'}>원복</button></div>`;
    if (fd) {
      flipHtml += `<table style="margin-top:4px">
        <tr><td class="l flipnew">신규 생성 면 (비용)</td>
          <td>${fd.newFaces.length}개</td><td>+${fmt(fd.areaNew)} m²</td></tr>
        <tr><td class="l flipgone">소멸 면 (환급)</td>
          <td>${fd.goneFaces.length}개</td><td>−${fmt(fd.areaGone)} m²</td></tr>
        <tr><td class="l">ΔA (XOR 회계 Σ area·(new−old))</td><td colspan="2">${fd.dA >= 0 ? '+' : ''}${fmt(fd.dA)} m²</td></tr>
        <tr><td class="l">ΔW (뒤집기 값)</td><td colspan="2">${wTxt}</td></tr>
      </table>
      <div class="note">신규 면 ${fd.newFaces.map(fi => esc(s2.faces[fi].face_id)).join(' ') || '없음'} ·
        소멸 면 ${fd.goneFaces.map(fi => esc(s2.faces[fi].face_id)).join(' ') || '없음'}</div>`;
    }
  }
  const adj = s2.cellFaces[ci];
  const adjRows = adj.map(fi => {
    const f = s2.faces[fi];
    const other = f.cell_a === c.cell_id ? f.cell_b : f.cell_a;
    return `<tr data-fid="f${fi}" class="${state.selFace === fi ? 'sel' : ''}">
      <td class="l">${esc(f.face_id)}</td>
      <td class="l">${other ? esc(other) : '<span class="note">도메인</span>'}</td>
      <td class="l">${faceLabel(d, f)}</td>
      <td>${fmt(f.area_m2)}</td>
      <td class="${f.initial_real ? 'good' : ''}">${f.initial_real ? 'F*' : '잠듦'}</td>
      <td>${s2.faceSeedCount[fi]}</td></tr>`;
  }).join('');
  return `<div class="card"><b style="color:#ffe066">${esc(c.cell_id)}</b>
    ${c.fixed ? '<span class="badge na">고정(footprint 밖)</span>' : ''}
    <table style="margin-top:4px">
      <tr><td class="l">중심 · 부피</td><td class="l">[${(c.centroid || []).map(v => fmt(v)).join(', ')}] · ${fmt(c.volume_m3, 3)} m³</td></tr>
      <tr><td class="l">표면고 z_surf (p90)</td><td class="l">${surf.z_surf === null || surf.z_surf === undefined ? '무점(null)' : fmt(surf.z_surf, 3) + ' m'}
        <span style="color:#7ee787">— 3D 초록 링</span></td></tr>
      <tr><td class="l">기둥 (r=${surf.radius_m ?? 0.75} m, 셀 중심)</td>
        <td class="l">ALS 점 ${surf.n_col_pts ?? (surf.col_pt_idx || []).length}개 <span style="color:#ffe066">발광</span></td></tr>
      <tr><td class="l">판정</td><td class="l">${esc(VERDICT_KO[surf.verdict] || surf.verdict || '—')}</td></tr>
      <tr><td class="l">소프트 t (o_init)</td><td class="l">${fmt(c.t, 2)}</td></tr>
      <tr><td class="l">초기 이산 o_state=[t>0.5]</td><td class="l"><b>${c.o_state}</b>
        ${((c.t > 0.5 ? 1 : 0) === c.o_state) ? '' : '<span class="bad">≠ 반올림!</span>'}</td></tr>
      <tr><td class="l">앵커 목표 t_k (소프트 존속)</td><td class="l">${fmt(c.t, 2)}</td></tr>
      <tr><td class="l">w (초기)</td><td class="l">1</td></tr>
      <tr><td class="l">뒤집기 값 w·|log(t/(1−t))|</td><td class="l">${wTxt}${Math.abs(c.t - 0.4) < 1e-9 ? ' <span class="note">(무점 t=0.4 → ≈0.41)</span>' : ''}</td></tr>
      <tr><td class="l">절단 평면 (칩 클릭=평면별 절단 보기)</td>
        <td class="l">${(c.cut_plane_ids || []).map(pid => planeChip(d, pid)).join('') || '—'}</td></tr>
    </table>
    ${flipHtml}
    <div style="margin-top:6px"><b>인접 면 ${adj.length}개</b> (클릭=면 카드)</div>
    <div class="scrollbox"><table>
      <tr><th class="l">면</th><th class="l">상대 셀</th><th class="l">평면/도메인</th><th>m²</th><th>F*</th><th>시드</th></tr>
      ${adjRows}</table></div></div>`;
}
function faceCardHtml(d, fi) {
  const s2 = d.s2, f = s2.faces[fi];
  const cellLink = (cid) => {
    if (!cid) return '<span class="note">도메인 경계(밖 o=0)</span>';
    const ci = s2.cellIdx[cid];
    return ci === undefined ? `<span class="bad">${esc(cid)} 실재하지 않음</span>`
      : `<a href="#" data-cid="c${ci}" style="color:#8ecbff">${esc(cid)}</a>`;
  };
  const planeRows = (f.s1_plane_ids || []).map(pid => {
    const p = d.planeById[pid];
    return `<tr><td class="l">${esc(pid)}</td>
      <td class="l">${p ? esc(p.source) : '<span class="bad">실재하지 않음</span>'}</td>
      <td>${p ? (p.inlier_count ?? '—') : '—'}</td>
      <td class="l"><a href="${page1Link(d, pid)}" style="color:#8ecbff">페이지 1에서 이 평면 보기 ↗</a></td></tr>`;
  }).join('');
  return `<div class="card"><b style="color:#ffe066">${esc(f.face_id)}</b>
    ${f.initial_real ? '<span class="badge good">F* 초기 실재</span>' : '<span class="badge na">게이트 0 (잠든 면)</span>'}
    ${f.domain ? `<span class="badge na">도메인 ${esc(f.domain)}</span>` : ''}
    ${!!f.initial_real === !!s2.realNow[fi] ? '' : '<span class="badge bad">F* 재계산 불일치</span>'}
    <table style="margin-top:4px">
      <tr><td class="l">양쪽 셀 a / b</td><td class="l">${cellLink(f.cell_a)} / ${cellLink(f.cell_b)}</td></tr>
      <tr><td class="l">면적</td><td class="l">${fmt(f.area_m2)} m²</td></tr>
      <tr><td class="l">n · d</td><td class="l">[${(f.n || []).map(v => fmt(v, 3)).join(', ')}] · ${fmt(f.d, 3)}</td></tr>
      <tr><td class="l">시드</td><td class="l">${s2.faceSeedCount[fi]}개 (게이트 0 면에도 전부 — 수명 규칙 ②)</td></tr>
    </table>
    ${planeRows ? `<div style="margin-top:5px"><b>소속 s1 평면</b> (한 절단 평면의 링 전부)</div>
      <table><tr><th class="l">평면</th><th class="l">출처</th><th>inlier</th><th class="l">점프</th></tr>${planeRows}</table>`
      : '<div class="note" style="margin-top:4px">도메인 면 — s1 평면 없음</div>'}</div>`;
}
function checksCardHtml(s2) {
  const ck = s2.checks;
  const B = (ok) => `<span class="badge ${ok ? 'good' : 'bad'}">${ok ? '통과' : '위반'}</span>`;
  const v = ck.volume;
  return `<div class="card">
    <table>
      <tr><td class="l">참조 존재(면→셀·평면 / 시드→면 / 셀→면·절단평면 / col_pt 범위)</td>
        <td class="l">${ck.refErrors}건 ${B(ck.refErrors === 0)}</td></tr>
      <tr><td class="l">col_pt_idx 전부 source==1 (ALS 전용)</td>
        <td class="l">위반 ${ck.colSrcBad}건 ${B(ck.colSrcBad === 0)}</td></tr>
      <tr><td class="l">o_state == [t &gt; 0.5]</td>
        <td class="l">위반 ${ck.oStateBad}건 ${B(ck.oStateBad === 0)}</td></tr>
      <tr><td class="l">F* 재계산 일치 (|o_a−o_b|=1, 밖 o=0)</td>
        <td class="l">불일치 ${ck.fstarBad}건 ${B(ck.fstarBad === 0)}</td></tr>
      <tr><td class="l">모든 면 시드 ≥ 1</td>
        <td class="l">${ck.seedCover.have}/${ck.seedCover.total} ${B(ck.seedCover.pass)}</td></tr>
    </table>
    <table style="margin-top:5px">
      <tr><td class="l">프리즘 부피 (footprint×높이)</td><td>${v.prism === null ? '—' : fmt(v.prism, 3) + ' m³'}</td></tr>
      <tr><td class="l">Σ셀 부피 (뷰어 재합산)</td><td>${fmt(v.sumCells, 3)} m³</td></tr>
      <tr><td class="l">Σ셀 부피 (manifest)</td><td>${v.manifestSum === null ? '—' : fmt(v.manifestSum, 3) + ' m³'}</td></tr>
      <tr><td class="l">상대 오차 (기준 1e-3)</td>
        <td>${v.rel === null ? '—' : v.rel.toExponential(2)} ${v.pass === null ? '' : v.pass ? '<span class="badge good">합</span>' : '<span class="badge bad">불</span>'}</td></tr>
    </table>
    ${ck.refDetail.length ? `<div class="err">첫 오류: ${ck.refDetail.map(esc).join(' · ')}</div>` : ''}
    <div class="note" style="margin-top:3px">뷰어 경량 자체 검사 — 정식 검사 계약은 tests/ 자동 테스트 소관.</div>
  </div>`;
}
function renderPanel() {
  const d = state.run;
  if (!d) { $('#panel').innerHTML = '<p class="note">런을 선택하세요.</p>'; return; }
  const s2 = d.s2;
  const rd = reading();
  let h = `<div class="note caption">페이지 2 = 배열·초기값(S2) — 절단 평면이 만든 셀 배열,
      기둥 p90 표면고의 o_init, 초기 실재 면 F*, 면 위 시드. 판정·최적화는 페이지 3.</div>`;
  if (!s2) {
    h += `<div class="err">S2 파일 없음: ${d.s2Missing.map(esc).join(', ')}<br>
      writer가 S2 번들(s2_cells/s2_faces/s2_seeds)을 아직 생성하지 않았다 —
      생성 후 새로고침. S1 맥락(ALS 점·footprint)만 표시 중.</div>
      <div class="legend"><label><input type="checkbox" id="alsTgl" ${state.showAls ? 'checked' : ''}>
        <span style="color:#d08a2e">ALS prior 점</span></label></div>`;
  } else {
    h += `<h2>출발 상태 요약 <span class="note">(변수 4군 — 런 로드 시 자동)</span></h2>
    ${startStateCardHtml(d)}
    <h2>표시</h2>
    <div class="legend">
      <label><input type="checkbox" id="fstarTgl" ${state.showFstar ? 'checked' : ''}>
        <span style="color:#8ecbff">F* 오버레이</span> (실재 면 채움 강조 · 게이트 0 = 잠든 면)</label>
      <label><input type="checkbox" id="seedTgl" ${state.showSeeds ? 'checked' : ''}>
        <span style="color:#cf9bff">시드</span></label>
      <label><input type="checkbox" id="alsTgl" ${state.showAls ? 'checked' : ''}>
        <span style="color:#d08a2e">ALS prior 점</span></label>
    </div>
    <div class="legend">
      <label><input type="checkbox" id="domainTgl" ${state.showDomain ? 'checked' : ''}>
        도메인 외피(벽·지면·상단)</label>
      <label><input type="checkbox" id="wireTgl" ${state.showWire ? 'checked' : ''}>
        와이어(빈 셀 = 와이어만)</label>
    </div>
    <div class="legend">셀 색:
      <label><input type="radio" name="cellcolor" value="o" ${state.cellColor === 'o' ? 'checked' : ''}>
        켬/끔 (o_state)</label>
      <label><input type="radio" name="cellcolor" value="t" ${state.cellColor === 't' ? 'checked' : ''}>
        o_init 맵 (소프트 t 4범주)</label>
    </div>
    ${state.cellColor === 't' ? tLegendCardHtml(d) : ''}
    <div class="legend">클릭 대상:
      <label><input type="radio" name="pickmode" value="cell" ${state.pickMode === 'cell' ? 'checked' : ''}> 셀</label>
      <label><input type="radio" name="pickmode" value="face" ${state.pickMode === 'face' ? 'checked' : ''}> 면</label>
      <span class="note">셀 모드 = 면 뒤(광선 진행 쪽) 셀 선택</span>
    </div>
    <h2>자체 검사 <span class="note">(체크리스트 ①·②·⑤의 근거)</span></h2>
    ${checksCardHtml(s2)}`;
    if (state.selCell !== null) h += `<h2>선택 셀 — 초기값 카드</h2>${cellCardHtml(d, state.selCell)}`;
    if (state.selFace !== null) h += `<h2>선택 면</h2>${faceCardHtml(d, state.selFace)}`;
    // S1 평면 → 셀 절단 인과 — 접두 재생 + 파편화 랭킹 (s2_cut_sequence.json lazy)
    h += cutSeqSectionHtml(d);
    // 평면별 절단 보기 — S1 평면 목록(항상) + 선택 시 절단 요약 카드
    h += `<h2>S1 평면 — 평면별 절단 보기 <span class="note">(조각 진단 · 클릭=발광/감광)</span></h2>`;
    if (state.selPlane !== null) h += planeCardHtml(d, state.selPlane);
    h += planeListHtml(d);
    // 셀 목록
    const occN = s2.cells.filter(c => c.o_state === 1).length;
    h += `<h2>셀 (${s2.cells.length} — o=1 ${occN} · o=0 ${s2.cells.length - occN})</h2>
      <div class="scrollbox"><table>
      <tr><th class="l">셀(클릭=카드)</th><th>o</th><th>t</th><th class="l">판정</th><th>m³</th><th class="l">고정</th></tr>` +
      s2.cells.map((c, ci) => `<tr data-cid="c${ci}" class="${state.selCell === ci ? 'sel' : ''}">
        <td class="l">${esc(c.cell_id)}</td><td>${c.o_state}</td><td>${fmt(c.t, 2)}</td>
        <td class="l">${esc(VERDICT_KO[(c.surf || {}).verdict] || '—')}</td>
        <td>${fmt(c.volume_m3, 2)}</td><td class="l">${c.fixed ? '고정' : ''}</td></tr>`).join('') +
      `</table></div>`;
    // 시드 요약
    const g = s2.grid || {};
    const fstarN = s2.faces.filter(f => f.initial_real).length;
    h += `<h2>면 · 시드</h2><div class="card">
      면 ${s2.faces.length}개 — F* 실재 ${fstarN} · 게이트 0 ${s2.faces.length - fstarN} ·
      도메인 ${s2.faces.filter(f => f.domain).length}<br>
      시드 ${s2.seeds.length}개 전수(서브샘플 금지) — 격자 간격 ${g.spacing_m ?? '—'} m ·
      크기 ${g.size_m ?? '—'} m (레거시 arrgs_train 상수)<br>
      <span class="${s2.checks.seedCover.pass ? 'good' : 'bad'}">시드 0개 면: ${s2.faces.length - s2.checks.seedCover.have}개</span>
      — 게이트 0 면에도 전부 존재해야 함(수명 규칙 ②)</div>`;
  }
  // 판독 기록 — 파일 다운로드만, 서버 전송 없음 (페이지 1 관행)
  h += `<h2>판독 기록 (리뷰어: 김휘영)</h2>
    <div class="card">
      <div class="legend">
        <label><input type="radio" name="verdict" value="합격" ${rd.verdict === '합격' ? 'checked' : ''}> 합격</label>
        <label><input type="radio" name="verdict" value="불합격" ${rd.verdict === '불합격' ? 'checked' : ''}> 불합격</label>
        <label><input type="radio" name="verdict" value="보류" ${rd.verdict === '보류' ? 'checked' : ''}> 보류</label>
      </div>
      <textarea id="memo" rows="4" placeholder="판독 메모 — 체크리스트 5항은 참고 기준(2026-08-27 방침), 발견 기록 중심으로">${esc(rd.memo)}</textarea>
      <div style="margin-top:5px">서명란 <input type="text" id="sign" placeholder="리뷰어 김휘영 서명" value="${esc(rd.sign)}" style="width:180px">
        <button class="small" id="dlbtn">판독 기록 JSON 다운로드</button></div>
      <div class="note" style="margin-top:4px">파일로만 저장 — 서버 전송 없음. scientific_verdict: null 유지(사람 판정은 별도 승인 문서).</div>
    </div>`;
  $('#panel').innerHTML = h;
  bindPanel();
}
function bindPanel() {
  const on = (id, ev, fn) => { const el = $(id); if (el) el[ev] = fn; };
  on('#fstarTgl', 'onchange', () => { state.showFstar = $('#fstarTgl').checked; restyle(); });
  on('#seedTgl', 'onchange', () => { state.showSeeds = $('#seedTgl').checked; restyle(); });
  on('#alsTgl', 'onchange', () => {
    state.showAls = $('#alsTgl').checked;
    if (state.run && state.run.alsPoints) state.run.alsPoints.visible = state.showAls;
  });
  on('#domainTgl', 'onchange', () => { state.showDomain = $('#domainTgl').checked; restyle(); });
  on('#wireTgl', 'onchange', () => { state.showWire = $('#wireTgl').checked; restyle(); });
  document.querySelectorAll('input[name="pickmode"]').forEach(r => {
    r.onchange = () => { state.pickMode = r.value; };
  });
  document.querySelectorAll('input[name="cellcolor"]').forEach(r => {
    r.onchange = () => { state.cellColor = r.value; restyle(); renderPanel(); };
  });
  on('#flipTgl', 'onchange', () => { state.flip = $('#flipTgl').checked; restyle(); renderPanel(); });
  on('#flipReset', 'onclick', () => { state.flip = false; restyle(); renderPanel(); });
  document.querySelectorAll('[data-cid]').forEach(el => {
    el.onclick = (e) => { e.preventDefault(); selectCell(+el.dataset.cid.slice(1)); };
  });
  document.querySelectorAll('[data-fid]').forEach(el => {
    el.onclick = (e) => { e.preventDefault(); selectFace(+el.dataset.fid.slice(1)); };
  });
  document.querySelectorAll('[data-pid]').forEach(el => {
    el.onclick = (e) => { e.preventDefault(); selectPlane(el.dataset.pid); };
  });
  on('#planeClear', 'onclick', () => clearSelection());
  // 절단 누적 재생 — lazy 로드 / 진입 / 스크럽(제자리 갱신) / 종료
  on('#cutLoad', 'onclick', async () => {
    const d = state.run;
    await loadCutSeq(d);
    renderPanel();
  });
  on('#cutPlay', 'onclick', () => setPlayK(0));
  on('#cutPrev', 'onclick', () => setPlayK((state.playK ?? 0) - 1));
  on('#cutNext', 'onclick', () => setPlayK((state.playK ?? 0) + 1));
  on('#cutExit', 'onclick', () => clearSelection());
  on('#cutK', 'oninput', () => setPlayK(+$('#cutK').value));
  const svg = $('#cutChart');
  if (svg && state.run && state.run.cutSeq) {
    const cs = state.run.cutSeq;
    const toK = (ev) => {
      const r = svg.getBoundingClientRect();
      const dm = cs.chartDims;
      const fx = (ev.clientX - r.left) * (dm.W / r.width);   // viewBox 좌표
      return Math.round((fx - dm.padL) / (dm.W - dm.padL - dm.padR) * cs.K);
    };
    svg.onpointerdown = (ev) => {
      if (cs.mismatch) return;
      try { svg.setPointerCapture(ev.pointerId); } catch (_e) { /* no-op */ }
      setPlayK(toK(ev)); ev.preventDefault();
    };
    svg.onpointermove = (ev) => { if (ev.buttons && !cs.mismatch) setPlayK(toK(ev)); };
  }
  if (state.playK !== null) updateCutReadout();
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
  const s2 = d.s2;
  const now = new Date().toISOString();
  const obj = {
    schema: 'phd_s3_verify_p2_reading_v1',
    page: 'p2_arrangement_init',
    run: state.runName,
    bundle: {
      schema: d.manifest.schema, bundle_name: d.manifest.bundle_name,
      stage: d.manifest.stage, dataset: d.manifest.dataset,
      counts: d.manifest.counts, o_init_def: d.manifest.o_init_def ?? null,
      volumes: d.manifest.volumes ?? null,
      synthetic_als: d.manifest.synthetic_als ?? null,
    },
    checklist: [
      '① 참조 무결성 오류 0 (면→셀·평면, 시드→면 — 로드 시 자체 검사)',
      '② Σ셀 부피 = 프리즘 부피 (상대 1e-3)',
      '③ 분류-붕괴 건물(B036)에서 표면고 판정 정상 — 면역 확인 (육안)',
      '④ 초기 경계가 prior 형상으로 읽힘 (육안)',
      '⑤ 시드가 게이트 0 면에도 존재 (수명 규칙 ②)',
    ],
    checklist_policy: '참고 기준 — 엄격 런별 합불 아님 (판독 기록 2026-08-27 방침, 발견 기록으로 갈음)',
    auto: s2 ? {
      ref_errors: s2.checks.refErrors,
      col_src_violations: s2.checks.colSrcBad,
      o_state_rounding_violations: s2.checks.oStateBad,
      fstar_recompute_mismatch: s2.checks.fstarBad,
      volume: s2.checks.volume,
      seed_faces: s2.checks.seedCover,
      cells: s2.cells.length, faces: s2.faces.length, seeds: s2.seeds.length,
      start_state: (() => {   // 출발 상태 요약 카드와 같은 산수
        const ss = computeStartState(d);
        return ss ? {
          occ_on: ss.occOn, occ_off: ss.occOff,
          t_hist: Object.fromEntries(ss.tOrder.map(([k, v], i) => [`${k}(${v})`, ss.tCnt[i]])),
          t_other: ss.tOther, planes_p0: ss.nPlanes, planes_by_source: ss.bySrc,
          delta: '0 (정의)', color: '중립 회색 (정의)',
        } : null;
      })(),
      selected_plane: state.selPlane,
      cell_color_mode: state.cellColor,   // 'o'(켬/끔) | 't'(o_init 맵 — 소프트 t 4범주)
      cut_sequence: d.cutSeq ? {          // 절단 누적 재생(S1→셀 인과) 사용 기록
        available: true,
        n_cut_planes: d.cutSeq.K,
        prefix_mode: (d.cutSeq.doc || {}).prefix_mode ?? null,
        baseline_n_cells: d.cutSeq.baseCells,
        final_n_cells: d.cutSeq.nCellsByK[d.cutSeq.K] ?? null,
        mismatch: d.cutSeq.mismatch,
        playback_used: d.cutSeq.used,
        last_k: d.cutSeq.lastK,
        playing_now_k: state.playK,
      } : { available: false,
            reason: d.cutSeqError || 'lazy 미요청(로드 버튼 미사용)' },
    } : { s2_missing: d.s2Missing },
    verdict: rd.verdict, memo: rd.memo,
    reviewer: '김휘영', signature: rd.sign,
    saved_at: now, transport: 'file-download-only',
    not_official: true, scientific_verdict: null,
  };
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)],
                                        { type: 'application/json' }));
  a.download = `p2_reading_${state.runName}_${now.replace(/[:.]/g, '-')}.json`;
  a.click();
}

// ---------- 헤더 ----------
function renderHeader() {
  const d = state.run;
  if (!d) { $('#countsline').textContent = '런 없음 — writer(s1+s2 번들)를 먼저 실행'; return; }
  const c = d.manifest.counts || {};
  const v = d.manifest.volumes || {};
  const off = d.manifest.local_offset || [];
  $('#countsline').textContent =
    `${d.manifest.bundle_name || state.runName} · stage=${d.manifest.stage || 's1'}` +
    (d.s2 ? ` · 셀 ${c.cells ?? d.s2.cells.length} · 면 ${c.faces ?? d.s2.faces.length}` +
            ` · 시드 ${c.seeds ?? d.s2.seeds.length}` +
            (v.prism_m3 ? ` · 프리즘 ${(+v.prism_m3).toFixed(1)} m³` : '')
          : ' · S2 없음(빈 상태)') +
    (d.manifest.synthetic_als ? ' · 의사-ALS(GT 면 결정론 샘플)' : '') +
    ` · ALS 점 ${c.points_als ?? d.alsLocals.length}` +
    ` · CRS ${d.manifest.crs || '?'} (offset −[${off.map(x => (+x).toFixed(1)).join(', ')}])`;
  $('#hud').textContent = `${state.runName} — 좌드래그 회전 · 우드래그 이동 · 휠 줌 · ` +
    `클릭=셀(면 뒤쪽)/면 선택(패널 라디오로 전환) · 재클릭·빈 공간·ESC=해제 · ` +
    `o=1 셀 반투명 채움 / o=0 셀 와이어 · F* 토글=실재 면 강조 · ALS 앰버 = o_init 입력 · ` +
    `패널 평면 목록/절단 평면 칩 클릭 = 평면별 절단 보기(증거 영역+단면 발광) · ` +
    `절단 누적 재생 = 패널 슬라이더(선택과 배타)`;
}

// ---------- 런 전환 ----------
async function loadRun(name) {
  state.runName = name; state.selCell = null; state.selFace = null; state.selPlane = null;
  state.flip = false; state.playK = null;
  $('#panel').innerHTML = `<p class="note">${esc(name)} 로딩 중…</p>`;
  try {
    if (!state.cache[name]) state.cache[name] = await fetchRun(name);
  } catch (e) {
    $('#panel').innerHTML =
      `<div class="err">런 ${esc(name)} 로드 실패: ${esc(e.message)}<br>
       writer가 s1/s2 번들을 아직 생성하지 않았을 수 있다.</div>`;
    $('#checkstrip').innerHTML = '<span class="note">—</span>';
    return;
  }
  state.run = state.cache[name];
  buildScene(state.run);
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
                              : ds.stable_id ? ` (${ds.stable_id})` : '') +
                    (r.s2_ready === false ? ' [S2 없음]' : '');
    sel.appendChild(o);
  });
  sel.onchange = () => loadRun(sel.value);
  const qRun = new URLSearchParams(location.search).get('run');
  const first = state.runs.some(r => r.name === qRun) ? qRun
              : (state.runs.length ? state.runs[0].name : null);
  if (first) { sel.value = first; loadRun(first); }
  else {
    $('#countsline').textContent = '런 0개 — writer(s1+s2 번들) 실행 후 build_verify_pages.py 재실행';
    $('#panel').innerHTML = '<p class="note">runs/ 아래에 번들이 없다.</p>';
    $('#checkstrip').innerHTML = '<span class="note">—</span>';
  }
  resize();
}).catch(e => {
  $('#panel').innerHTML = `<div class="err">viewer manifest 로드 실패: ${esc(e.message)} —
    build_verify_pages.py로 뷰어를 번들 루트에 배포한 뒤 8885로 서빙해야 한다.</div>`;
});
resize();
applyOrbit();
