// S3 검증 페이지 3 — 공동 최적화(연속 구간) 정적 뷰어. NOT OFFICIAL · scientific_verdict: null.
// 데이터 계약: phd_s3_verify_s3a_v1 — ../runs/<name>/{manifest.json, s1_view.json, s2_faces.json}
// + S3a 추가분 {s3_views.json, s3_steps.jsonl, s3_face_residual.json, s3_tiles/<view_id>/*.png}
// + S3b 추가분(phd_s3_verify_s3b_v1 — 색만 학습·기하 동결): s3_steps.jsonl에 stage:"3b" 행 추가
//   (3a 행 보존), 체크포인트 행에만 views_psnr·color_stats, 체크포인트 타일은
//   s3_tiles/s<step>/<view_id>/{render,residual}.png (photo는 3a 타일 재사용),
//   s3_face_residual_final.json(step0=3a 것과 같은 근사·null 규약), manifest.s3b_def.
// + S3c 추가분(phd_s3_verify_s3c_v1 — δ 해동·주입 복원 검정): stage:"3c" 행 추가(3a·3b 행 보존),
//   학습 = δ(전역 평행이동 1벡터·회전 없음) + 색(3b 웜스타트), 평면·o 동결(체크섬), 목적 = photo만
//   (anchor·area는 진단 기록 — manifest.s3c_def.objective_note), 행에 delta_hat:[3] ·
//   param_step_norms{delta≥0, planes:0, colors≥0}, 체크포인트 타일은 s3_tiles/s3c_s<step>/
//   (3b 디렉터리와 충돌 금지), s3_face_residual_s3c_final.json, manifest.s3c_def.
//   주입 런(B022_DZ050·B173_DZ050)은 manifest.injection{delta_applied, route,
//   expected_delta_hat(부호 규약)} — δ̂ 궤적 vs 정답선이 판독 축. 비변화 통제는 0선·잔류 오차,
//   scope 0 런(B036·SYNTH)은 δ̂ 부동이 음성 기록.
// 3차 내부 단계(계획 문서 개정 주석 2026-08-27): 3a 렌더-온리(0 최적화 스텝 — 배선 자체 검증,
// backward 1회로 grad_norms만 기록) → 3b 색 → 3c δ → 3d 평면. 화면 축 = 사이클 타임라인 하나,
// 미구현 구간은 회색 "예정" — 페이지가 구현과 함께 자란다(스텝·구간 다수 전제, 수백 스텝은 씨닝).
// 렌더 상태(방법론 §2.1 r16): α_g=|o_a−o_b|∈{0,1} 유도(자유 알파 금지) · δ는 처음부터 렌더
// 인자로 배선하되 3a에서 0 고정 · 색 중립 회색 상수 · densification/pruning 금지(수명 규칙 ①)
// · 렌더러 gsplat(미분 가능 렌더링). S3a 부재 런은 빈 상태 안내(죽지 않음).
// 연계 판독(리뷰어 요청 2026-08-27): ① 스텝→3D 동기화 — 스텝 선택 시 면 히트맵을 그 시점
// 이하 최대 체크포인트 상태(step0/3b final/3c final)로 자동 전환(추적 토글 기본 ON, 수동
// 라디오 유지) + "3D 표시 중" 배지, ② S2 초기 상태(F*) 오버레이 — s2_cells.json lazy fetch로
// o_state 재유도(페이지 2 파서 이식)한 실재 면을 얇은 반투명 회백 병합 지오메트리 1회 생성 후
// visible 토글, ③ 3c δ̂ 평행이동 — prior 평면(s1_planes.json source=="prior")이 만든 면
// (히트맵+오버레이)을 shiftGroup.position=δ̂로 이동 표시(지오메트리 재생성 금지 · 부호 규약
// d_eff=d0+n·δ = prior를 +δ 평행이동), 3c 행 아니면 0.
// ④ 구간 산출물 요약 카드(사용자 지시 2026-08-27 "단계별 산출물을 보고 싶다"): 타임라인 구간
// 배지(seghead 3a/3b/3c/3d) 클릭 = 우측 패널 별도 섹션 #segsummary에 그 구간 고유 산출물
// 요약 — 공통 틀 3줄(해동 변수/고유 산출물/이 단계가 답한 질문, SEG_FRAME) + 구간별 수치
// (3a: grad 3군(gradBarsHtml 재사용, scope 0 = δ 구조적 0)·step0 photo·PSNR 중앙값·
// [s0 타일/히트맵] 버튼 / 3b: PSNR 중앙값 개선폭(manifest s3b_def.psnr_median, 폴백 jsonl
// 체크포인트 중앙값)·색 아티팩트(colors_artifact)·색 분화 최종값·[차이 히트맵] 버튼 /
// 3c: δ̂ 최종 vs 기대값(주입=정답·잔류 오차, 비변화=잔류 |δ̂|, scope 0=부동 확인)·
// [δ̂ 궤적으로] 스크롤 / 3d: 예정 안내만). 버튼은 기존 상태 세팅(selectStep·heatMode 수동
// 전환)을 재사용, 배지 클릭 자체는 스텝 선택과 독립(selStep 불변·재클릭=닫기), 열람은 판독
// JSON auto.segment_summary_viewed에 기록. seghead는 [산출물 요약] 미니 버튼 병기(접근성 —
// 사용자 지시 2026-08-27) + 첫 로드 힌트 배지 1회(닫기 가능·localStorage 기억) + HUD 안내.
// ⑤ 중간 산출물(체크포인트 면 잔차 — writer 확장 s3_face_residual_ckpt.json, 스키마
// phd_s3_verify_face_residual_ckpt_v1): 히트맵 상태가 끝점 3종에서 전 체크포인트로 확장 —
// 스텝 추적이 이제 s5/s15/s45/s130 중간 상태도 밟는다(선택 스텝 이하 최대 체크포인트,
// heatStatesOf 등록부). 공유 색 스케일은 전 체크포인트 최대 기준(resStatsShared), 라디오
// 3종은 "주요 상태" 단축으로 유지. 차이 모드는 임의 두 상태 비교로 일반화(대상/기준 드롭다운,
// 기본 = 3b final−step0 종전 동작). 판독 JSON auto.heat_ckpt_used에 사용 기록.
// ⑥ 체크포인트 필름스트립(사용자 요청 2026-08-27): 선택 뷰의 렌더/잔차(토글)를 현재 구간 전
// 체크포인트에 한 줄 썸네일(스텝·PSNR 라벨·클릭=스텝 선택) — "3b에서 개선이 있었는지"가
// 스크롤 없이 보이게. 기존 타일 파일 재사용(사진은 맨 앞 1장). auto.filmstrip 기록.
// ⑦ 앵커 가시화 2종(사용자 요청 2026-08-27, 히트맵 모드 추가 — 스텝 무관 상수):
// (a) 셀 앵커 비용 맵 C_k(o;t)=−[o·log t+(1−o)·log(1−t)] (§2.2, w=1) — "prior 증언이 현재
// 상태를 붙잡는 비용", 면 = 인접 셀 최대(경계를 붙잡는 더 강한 증언 긴장).
// (b) 뒤집기 값 ΔW 맵 |log(t/(1−t))| — "이 셀을 뒤집는 데 필요한 증거량", 면 = 인접 셀
// 최소(이 경계를 바꾸는 가장 싼 뒤집기); t∈{0,1}=∞ → 별색(블루)·범례 표기. s2_cells.json은
// F* 오버레이와 공유 lazy fetch(ensureCellsInfo), 면 지오메트리 경로 재사용. auto.anchor_map.
// ⑧ 히트맵 표시 범위(사용자 실화면 오독 정정 2026-08-27): 기본 = F*(initial_real) 면만 —
// 렌더에 실재하는 면은 F*뿐인데 잠든 gate-0 prior 단면까지 전부 칠하면 "3a가 만든 건물
// 기하"로 오독된다(실측 B173 1,152/1,580면 칠해짐 vs 실재 459면). '전체 후보 면' 토글
// (귀속용)을 켜면 잠든 면을 반투명 + 점선(ghost색) 윤곽으로 구분 표시. 공유 색 스케일도
// 범위별(F* 전용 스케일 기본 — 잠든 면 최대값에 램프가 눌리지 않게). 우상단 배지에 상시
// 라벨("잔차 귀속 지도 — F* 면만/전체 후보"), 잔차 램프는 dataviz --ordinal 검증 5단으로
// 교체(저단 2.26:1 vs 표면 — 칠해진 면은 저잔차여도 데이터로 읽힘). 앵커 맵도 같은 범위
// 원칙 적용; S2 오버레이(F*)는 원래 실재 면만 그린다. 판독 JSON auto.heat_scope 기록.
// ⑨ LoD2 오버레이(사용자 지시 2026-08-27 "대략적 검증 잣대"): s1_planes.json gt_planes
// (LoD2 지붕면 support_local 3D 링 — 페이지 1이 이미 그리는 데이터)를 토글 오버레이로 —
// 청록/초록 와이어 + 반투명 채움(페이지 1 GT_COLOR 0x30d060 승계 — 엔티티 고정색), 배지
// "LoD2 지붕면 (평가 전용 — 방법 입력 아님)" 필수. δ̂ 이동(shiftGroup)의 영향을 받지 않는
// 고정 기준면(비교 잣대라 heatGroup에 부착 — shiftGroup 금지).
// ⑩ 초기 점유 vs LoD2(구멍/과잉 셀 — 이전 분석의 화면화): 각 셀 중심을 gt_planes
// 수평·경사면(|n_z|>0.2)의 XY 포함 검사로 대조 — 포함 면들의 평면 z 최댓값 = gt 지붕고,
// ±0.3 m 여유. 구멍 = 끔(o=0)인데 중심이 gt 지붕 아래(적색 계열), 과잉 = 켬(o=1)인데
// gt 지붕 위(자주/보라 계열) — 셀 채움(face_ids의 s2_faces 지오메트리 재사용, x-ray
// depthTest 끔: 내부 구멍 셀이 실재 면에 가려지지 않게) + 카운트 배지("구멍 N · 과잉 M —
// 3e 이산 판정의 시험대"). 계산은 첫 켬 때 1회(JS point-in-polygon 직접 — 셀 수천×면
// ≤20). 파이썬 대조값: B022 구멍 59 · 과잉 234(같은 로직·여유 0.3 m). s2_cells.json은
// F* 오버레이·앵커 맵과 공유 lazy fetch(ensureCellsInfo — centroid·face_ids 추가 보존).
// 초기 점유(S2 동결) vs 고정 LoD2의 대조라 δ̂ 이동과 무관하게 고정 표시.
// ⑪ 학습 색(텍스처) 3D 미리보기: manifest.s3b_def.colors_artifact의 s3b_colors.f16.bin
// (시드 수×3, float16, s2_seeds.json 행 순서)을 fetch → DataView 수제 fp16→fp32 디코드
// → F*(initial_real) 면의 시드만 THREE.Points(정점색) — 잠든 면 시드 제외(실재 표면의
// 텍스처만). 시드 위치 mu는 s2_seeds.json 지연 로드(첫 켬 때만 — B022 120 MB 명시 경고;
// face_grid의 shapely 재현이 불가능해 위치 재유도 대신 원본을 읽는다). 표시 상한 30만
// 결정론 스트라이드 씨닝(기존 관행), 점 크기 = 시드 간격(grid.spacing_m 0.30 m)×√스트라이드
// (씨닝 후 커버리지 보존). 켜면 진단 칠(히트맵 채움)은 자동 숨김 — 두 색 체계 겹침 방지
// (라디오식 배타), 경계 와이어·램프 범례도 함께 정리. prior 계열 시드는 shiftGroup에
// 부착해 δ̂ 이동 추종(히트맵·F* 오버레이와 동일 규약). artifact 없으면 토글 비활성+사유.
// 캡션 "3b가 학습한 모델 색(텍스처) — 타일 렌더와 동일물의 3D 표시". sha256은
// crypto.subtle 가용 시에만 대조(HTTP LAN 환경은 생략) + 바이트 길이 계약 검증.
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
  fstar: 0xc8ccd4,      // S2 초기 상태(F*) 오버레이 — 얇은 반투명 회백
  lod2: 0x30d060,       // LoD2 지붕면 오버레이(⑨ 평가 전용) — 페이지 1 GT_COLOR 승계
  hole: 0xe25563,       // ⑩ 구멍 셀(끔인데 LoD2 지붕 아래) — 적색 계열
  excess: 0xb05ce0,     // ⑩ 과잉 셀(켬인데 LoD2 지붕 위) — 자주/보라 계열
};
// 잔차 순차 램프 — 단일 색상(앰버) 5단, dataviz --ordinal 검증 통과(단조 L · 인접 ΔL≥0.06 ·
// 저단 #6b4a1e 2.26:1 vs 표면 #14161a · 단일 색상 18°). 종전 3단은 저단 1.14:1로 배경에
// 묻혀 값 구분이 약했음(오독 지적 2026-08-27) — 칠해진 면은 저잔차여도 데이터로 읽혀야 한다.
const RAMP = [[0x6b, 0x4a, 0x1e], [0x94, 0x60, 0x1a], [0xbc, 0x7c, 0x24],
              [0xe0, 0xa6, 0x48], [0xff, 0xd9, 0x7e]];
function rampRgb(t) {
  t = Math.min(1, Math.max(0, t));
  const n = RAMP.length - 1;
  const i = Math.min(n - 1, Math.floor(t * n));
  const u = t * n - i;
  const a = RAMP[i], b = RAMP[i + 1];
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u]
    .map(v => v / 255);
}
// 항별 손실 고정 색(엔티티 고정 — 순서 순환 금지). 미등록 항은 EXTRA에서, 소진 시 표에만.
// anchor_plane = anchor 계열(진단 — 3c에서는 목적 밖) · total_recorded = total과 같은 엔티티
// (3c의 진단 총합 기록명 — 같은 색, 구간별 차트에서 공존하지 않음).
const LOSS_COL = { photo: '#4a9eff', anchor: '#ff9a3c', anchor_plane: '#d08a2e',
                   area: '#2ee6c8', total: '#ffd866', total_recorded: '#ffd866',
                   depth: '#cf9bff', silhouette: '#ff7b72' };
const LOSS_EXTRA = ['#8ecbff'];
const LOSS_ORDER = ['photo', 'anchor', 'anchor_plane', 'area', 'depth', 'silhouette',
                    'total', 'total_recorded'];
// grad_norms 3군 — 배선 증거 (δ/평면/색). 3b에서는 "색 수렴 중 기하 압력 변화" 관측 축.
const GRAD_DEF = [['delta', 'δ (3a·3b 동결 — 3c 해동)', '#ff9a3c'],
                  ['planes', '평면 (3a~3c 동결 — 3d 해동)', '#4a9eff'],
                  ['colors', '색 (3a 상수 · 3b/3c 학습 변수)', '#7ee787']];
// δ̂ 성분 고정 색 — x/y/z 엔티티 고정 (팔레트 검증기: 인접 CVD 최악 ΔE 12.4 deutan로 페이지
// 세트 중 최상 · z=주입 축이라 앰버 강조). 식별은 색 단독이 아님: 끝점 직접 라벨 + 인접 표.
const DELTA_DEF = [['x', '#cf9bff'], ['y', '#2ee6c8'], ['z', '#ff9a3c']];
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
  selSegment: null,  // 구간 배지 선택('3a'…) — 요약 카드(④), 스텝 선택과 독립
  selView: null,     // view_id
  selFace: null,     // index into d.faces
  showGhost: true, showDomain: false,
  logYLoss: false,   // 손실 곡선 로그 y 옵션
  logYGrad: false,   // grad 곡선 로그 y 옵션
  cmpPrev: false,    // 체크포인트 렌더 이전/현재 나란히 비교
  // 면 히트맵 모드: 'init'(3a step0) | 'final'(3b) | 'final3c' | 'ckpt:<구간>:<스텝>'
  // (중간 체크포인트 — s3_face_residual_ckpt.json) | 'diff'(대상−기준, 일반화) |
  // 'anchor_cost'·'anchor_flip'(앵커 가시화 — 스텝 무관 상수)
  heatMode: 'init',
  // 히트맵 표시 범위(오독 정정 2026-08-27): 'fstar'(기본 — 렌더에 실재하는 F*=initial_real
  // 면만 칠함) | 'all'(전체 후보 면 — 귀속용, 잠든 gate-0 면은 반투명+점선 윤곽으로 구분).
  // 잠든 prior 단면들을 전부 칠하면 "3a가 만든 건물 기하"로 오독된다(B173 1,152/1,580면).
  heatScope: 'fstar',
  diffTarget: 'final', diffBase: 'init',   // 차이 모드 대상/기준 상태 키(일반화)
  filmKind: 'render',  // 체크포인트 필름스트립 — 'render' | 'residual'
  autoHeat: true,    // 스텝→3D 동기화 — 스텝 선택 시 이하 최대 체크포인트 히트맵 자동 전환
  overlayS2: false,  // S2 초기 상태(F*) 오버레이 — 기본 OFF, lazy fetch 후 visible 토글
  // 검증 오버레이 3종(⑨~⑪ — 2026-08-27) : 전부 기본 OFF, 첫 켬 때만 지연 생성/로드
  overlayGt: false,      // ⑨ LoD2 지붕면(평가 전용) — δ̂ 이동 무관 고정 기준면
  overlayCellsGt: false, // ⑩ 초기 점유 vs LoD2 — 구멍/과잉 셀 채움(로드 시 1회 계산)
  colorPreview: false,   // ⑪ 학습 색(텍스처) 미리보기 — 켜면 진단 칠 자동 숨김(배타)
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
    ctxGroup = new THREE.Group(), selGroup = new THREE.Group(),
    shiftGroup = new THREE.Group();  // prior 계열 지오메트리 — 3c δ̂ 평행이동(position만 갱신)
scene.add(heatGroup, wireGroup, ctxGroup, selGroup, shiftGroup);
function emptyGroup(g) {
  for (const o of [...g.children]) {
    g.remove(o);
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();
  }
}
function clear3d() {
  // 1회 생성 캐시 오버레이(d.s2ov·gtOv·cellOv·colorPrev) — dispose 대상에서 먼저 분리
  // (visible 토글 계약: 지오메트리는 런 캐시에 존속, buildScene마다 재부착만)
  for (const name of Object.keys(state.cache)) {
    const c = state.cache[name] || {};
    const cached = [];
    if (c.s2ov) cached.push(c.s2ov.base, c.s2ov.prior);
    if (c.gtOv) cached.push(c.gtOv.fill, c.gtOv.wire);
    if (c.cellOv) cached.push(c.cellOv.holeFill, c.cellOv.holeWire,
                              c.cellOv.excFill, c.cellOv.excWire);
    if (c.colorPrev) cached.push(c.colorPrev.base, c.colorPrev.prior);
    for (const m of cached)
      if (m && m.parent) m.parent.remove(m);
  }
  for (const g of [heatGroup, wireGroup, ctxGroup, selGroup, shiftGroup]) {
    scene.remove(g); emptyGroup(g);
  }
  heatGroup = new THREE.Group(); wireGroup = new THREE.Group();
  ctxGroup = new THREE.Group(); selGroup = new THREE.Group();
  shiftGroup = new THREE.Group();
  scene.add(heatGroup, wireGroup, ctxGroup, selGroup, shiftGroup);
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
// 루프 집계 — 스프레드 금지: 체크포인트 파일 도입으로 공유 스케일 표본이 면수×상태수
// (B022 11,264×15 ≈ 17만)라 Math.min(...v)의 인자 한계를 넘는다.
function resStatsOf(vals) {
  let n = 0, mn = Infinity, mx = -Infinity, sum = 0;
  for (const x of vals) {
    if (!Number.isFinite(x)) continue;
    n++; sum += x;
    if (x < mn) mn = x;
    if (x > mx) mx = x;
  }
  return n ? { n, min: mn, max: mx, mean: sum / n } : null;
}
async function fetchRun(name) {
  const base = `../runs/${name}`;
  const optJson = (fn) => fetch(`${base}/${fn}`).then(r => r.ok ? r.json() : null).catch(() => null);
  const optText = (fn) => fetch(`${base}/${fn}`).then(r => r.ok ? r.text() : null).catch(() => null);
  const mR = await fetch(`${base}/manifest.json`);
  if (!mR.ok) throw new Error(`manifest.json ${mR.status}`);
  const manifest = await mR.json();
  const [viewJ, facesJ, planesJ, viewsJ, stepsTxt, faceResJ, faceResFinJ, faceResFin3cJ,
         faceResCkptJ] = await Promise.all([
    optJson('s1_view.json'), optJson('s2_faces.json'),
    optJson('s1_planes.json'),   // prior 출처 판별(3c δ̂ 이동·오버레이 분할) — source=="prior"
    optJson('s3_views.json'), optText('s3_steps.jsonl'), optJson('s3_face_residual.json'),
    optJson('s3_face_residual_final.json'),      // S3b — 없으면 null (3a-only 런 허용)
    optJson('s3_face_residual_s3c_final.json'),  // S3c — 없으면 null (3b까지 런 허용)
    optJson('s3_face_residual_ckpt.json')]);     // 체크포인트 통합 — 없으면 null (구세대 허용)
  const faces = (facesJ && facesJ.faces) || [];
  const faceIdx = {};
  faces.forEach((f, i) => { faceIdx[f.face_id] = i; });
  // F*(initial_real) 면 집합 — 히트맵 기본 표시 범위(렌더에 실재하는 면은 F*뿐).
  // 도메인 외피 위의 F* 면(바닥·마진 절단면)은 페이지 관행상 히트맵 대상 밖(외피 토글로만
  // 와이어 표시)이라 집합에서 제외 — 스케일·통계가 칠해지는 면과 일치해야 한다.
  const realFaceSet = new Set();
  let nRealTotal = 0;
  faces.forEach(f => {
    if (!f.initial_real) return;
    nRealTotal++;
    if (!f.domain) realFaceSet.add(f.face_id);
  });
  // prior 계열 면 — s1_plane_ids에 source=="prior" 평면이 하나라도 있으면 prior 계열
  // (혼합 링이면 prior 우선 — δ̂ 이동 표시 대상)
  const priorPlaneSet = new Set(((planesJ && planesJ.planes) || [])
    .filter(p => p.source === 'prior').map(p => p.plane_id));
  const faceIsPrior = new Uint8Array(faces.length);
  faces.forEach((f, i) => {
    if ((f.s1_plane_ids || []).some(pid => priorPlaneSet.has(pid))) faceIsPrior[i] = 1;
  });
  // LoD2 지붕면(⑨·⑩) — gt_planes는 평가 전용(방법 입력 아님), 링 3점 미만은 제외
  const gtPlanes = ((planesJ && planesJ.gt_planes) || [])
    .filter(g => (g.support_local || []).length >= 3);
  const d = { name, manifest, view: viewJ || {}, faces, faceIdx,
              realFaceSet, nRealTotal,
              priorPlaneSet, faceIsPrior, s1PlanesMissing: planesJ === null,
              gtPlanes,
              gtNote: planesJ ? (planesJ.gt_evaluation_only ?? null) : null,
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
    // 체크포인트 집합 — views_psnr 보유 행 ∪ manifest.s3b_def/s3c_def.checkpoints
    const ckpt = {};
    for (const [st, idxs] of Object.entries(byStage)) {
      const set = new Set();
      idxs.forEach(i => { if (parsed.steps[i].views_psnr) set.add(parsed.steps[i].step ?? 0); });
      if (st === '3b') ((manifest.s3b_def || {}).checkpoints || []).forEach(s => set.add(+s));
      if (st === '3c') ((manifest.s3c_def || {}).checkpoints || []).forEach(s => set.add(+s));
      ckpt[st] = set;
    }
    const perFaceFinal3c = (faceResFin3cJ && faceResFin3cJ.per_face) || null;
    // 체크포인트 통합 파일(phd_s3_verify_face_residual_ckpt_v1) — 중간 상태 히트맵의 원천
    const ckptFR = (faceResCkptJ && Array.isArray(faceResCkptJ.entries))
      ? faceResCkptJ.entries
          .filter(e => e && e.per_face && Number.isFinite(+e.step))
          .map(e => ({ stage: String(e.stage), step: +e.step,
                       perFace: e.per_face }))
      : null;
    // 공유 스케일 — step0/끝점 2종 + 전 체크포인트 최대 기준(전환 비교가 같은 램프에서).
    // F* 범위 전용 스케일을 함께 집계(기본 표시 범위 — 잠든 면 최대값에 램프가 눌리지 않게).
    const initVals = Object.values(perFace);
    const bothVals = initVals
      .concat(perFaceFinal ? Object.values(perFaceFinal) : [])
      .concat(perFaceFinal3c ? Object.values(perFaceFinal3c) : []);
    const realVals = [];
    const pushReal = (map) => {
      for (const fid in map) if (realFaceSet.has(fid)) realVals.push(map[fid]);
    };
    pushReal(perFace);
    if (perFaceFinal) pushReal(perFaceFinal);
    if (perFaceFinal3c) pushReal(perFaceFinal3c);
    if (ckptFR)
      for (const e of ckptFR) {
        for (const fid in e.perFace) bothVals.push(e.perFace[fid]);
        pushReal(e.perFace);
      }
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
      perFaceFinal3c,
      finalStep3c: faceResFin3cJ ? (faceResFin3cJ.step ?? null) : null,
      finalMethod3c: faceResFin3cJ ? (faceResFin3cJ.method ?? null) : null,
      resStatsFinal3c: perFaceFinal3c ? resStatsOf(Object.values(perFaceFinal3c)) : null,
      ckptFR,                       // [{stage, step, perFace}] — 중간 상태 히트맵
      ckptSchema: faceResCkptJ ? (faceResCkptJ.schema ?? null) : null,
      resStatsShared: resStatsOf(bothVals),
      resStatsSharedReal: resStatsOf(realVals),   // F* 범위 공유 스케일(기본)
      diffStats: diffVals.length ? {
        n: diffVals.length, maxAbs: Math.max(...diffVals.map(Math.abs), 1e-12),
        mean: diffVals.reduce((a, b) => a + b, 0) / diffVals.length,
      } : null,
      finalMissing: (manifest.s3b_def !== undefined || /3b/.test(String(manifest.stage || '')))
                    && faceResFinJ === null,
      finalMissing3c: (manifest.s3c_def !== undefined || /3c/.test(String(manifest.stage || '')))
                      && faceResFin3cJ === null,
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
// ---------- 히트 상태 등록부 (⑤ 중간 산출물) ----------
// step0(3a) + ckpt 파일의 중간 체크포인트 + 끝점 2종. 구간 최종 체크포인트 엔트리는
// 'final'/'final3c' 키로 승격(끝점 파일과 같은 계산 — writer가 최종 entry를 재사용, 테스트
// 보증)해 라디오 "주요 상태" 단축과 겹치지 않는다. (구간, 스텝) 오름차순.
function heatStatesOf(d) {
  const s3 = d && d.s3;
  if (!s3) return [];
  const states = [{ key: 'init', label: '3a s0', ord: 0, step: 0, map: s3.perFace }];
  const fin = { '3b': s3.perFaceFinal ? (s3.finalStep ?? null) : null,
                '3c': s3.perFaceFinal3c ? (s3.finalStep3c ?? null) : null };
  for (const e of (s3.ckptFR || [])) {
    if (fin[e.stage] !== null && fin[e.stage] !== undefined && fin[e.stage] === e.step)
      continue;   // 끝점 라디오 상태가 대표(같은 값)
    states.push({ key: `ckpt:${e.stage}:${e.step}`, label: `${e.stage} s${e.step}`,
                  ord: STAGE_ORD[e.stage] ?? 9, step: e.step, map: e.perFace, ckpt: true });
  }
  if (s3.perFaceFinal)
    states.push({ key: 'final', label: `3b s${s3.finalStep ?? '?'} (final)`,
                  ord: 1, step: s3.finalStep ?? Infinity, map: s3.perFaceFinal });
  if (s3.perFaceFinal3c)
    states.push({ key: 'final3c', label: `3c s${s3.finalStep3c ?? '?'} (final)`,
                  ord: 2, step: s3.finalStep3c ?? Infinity, map: s3.perFaceFinal3c });
  states.sort((a, b) => (a.ord - b.ord) || (a.step - b.step));
  return states;
}
function heatStateByKey(d, key) {
  return heatStatesOf(d).find(s => s.key === key) || null;
}
// 현재 히트 모드의 면별 값·스케일·색 함수 — 잔차 상태들은 공유 스케일(전 체크포인트 최대
// 기준, 전환 비교 가능). diff = 임의 두 상태 비교(대상−기준). anchor_* = 스텝 무관 상수.
function heatData(d) {
  const s3 = d.s3;
  if (!s3) return null;
  let mode = state.heatMode;
  if (mode === 'anchor_cost' || mode === 'anchor_flip') return anchorHeatData(d, mode);
  const scopeAll = state.heatScope === 'all';
  if (mode === 'diff') {
    const a = heatStateByKey(d, state.diffTarget)
      || heatStateByKey(d, 'final') || heatStateByKey(d, 'final3c');
    const b = heatStateByKey(d, state.diffBase) || heatStateByKey(d, 'init');
    if (!a || !b) mode = 'init';   // 상태 2개 미만 — 아래 단일 상태 경로로
    else {
      let n = 0, maxAbs = 1e-12, sum = 0;
      for (const fid in b.map) {
        if (!scopeAll && !d.realFaceSet.has(fid)) continue;   // 기본 = F* 범위 통계
        const v0 = b.map[fid], v1 = a.map[fid];
        if (!Number.isFinite(v0) || !Number.isFinite(v1)) continue;
        const dv = v1 - v0;
        n++; sum += dv;
        if (Math.abs(dv) > maxAbs) maxAbs = Math.abs(dv);
      }
      const st = n ? { n, maxAbs, mean: sum / n } : null;
      return { mode: 'diff', label: `Δ|잔차| (${a.label} − ${b.label})`,
        value: (fid) => {
          const v0 = b.map[fid], v1 = a.map[fid];
          return (Number.isFinite(v0) && Number.isFinite(v1)) ? v1 - v0 : undefined;
        },
        norm: (v) => (st && Number.isFinite(v)) ? v / st.maxAbs : null,   // [−1,1]
        rgb: rampDivRgb,
        stats: st ? { min: -st.maxAbs, max: st.maxAbs, mean: st.mean, n: st.n } : null,
        diverging: true, pair: { target: a.key, base: b.key } };
    }
  }
  let hs = heatStateByKey(d, mode);
  if (!hs) {   // 폴백 사슬(종전 관행): final3c→final→init, ckpt 부재→init
    hs = (mode === 'final3c' && heatStateByKey(d, 'final'))
      || heatStateByKey(d, 'init');
    if (!hs) return null;
    mode = hs.key;
  }
  // 전 잔차 상태 공유 스케일 — 표시 범위별(기본 F*: 잠든 면 최대값에 램프가 눌리지 않게)
  const st = scopeAll ? s3.resStatsShared : s3.resStatsSharedReal;
  return { mode, label: `면별 |잔차| 평균 — ${hs.label}${hs.ckpt ? ' (체크포인트)' : ''}`,
    value: (fid) => hs.map[fid],
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
  // prior 계열(δ̂ 평행이동 대상 — shiftGroup) / 기저를 분리 축적. 병합 지오메트리 각 1회 생성,
  // 이동은 shiftGroup.position만 갱신(지오메트리 재생성 금지 — B022 11,264면 성능 계약).
  // 표시 범위(오독 정정): 기본은 F*(initial_real) 면만 칠한다 — 렌더에 실재하는 면은 F*뿐.
  // '전체 후보 면' 토글 시 잠든 gate-0 면도 칠하되 반투명 + 점선(ghost색) 윤곽으로 구분.
  const showAll = state.heatScope === 'all';
  const mk = () => ({ tri: [], col: [], triFace: [], wire: [] });
  const heat = mk(), heatPrior = mk(), sleep = mk(), sleepPrior = mk();
  const ghost = [], ghostPrior = [], domain = [];
  const painted = { real: 0, sleeping: 0 };
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
    const isPrior = !!(d.faceIsPrior && d.faceIsPrior[fi]);
    const isReal = !!f.initial_real;
    const t = hd ? hd.norm(hd.value(f.face_id)) : null;
    // 실재(F*) 면은 도메인(footprint 벽·지면·상판) 포함 전부 칠한다 — 렌더에
    // 실재하는 표면이 "실제 결과"다. 표본 없는 실재 면은 사라지지 않고 중립
    // 회색("채점 기록 없음")으로. 잠든 면은 '전체 후보' 토글에서만, 표본 있는
    // 비도메인에 한정(도메인 잠든 면 = 프리즘 외피 — 칠하면 상자 오독 재발).
    const paintSleep = showAll && !isReal && !f.domain && t !== null;
    if (isReal || paintSleep) {
      const ht = isReal ? (isPrior ? heatPrior : heat)
                        : (isPrior ? sleepPrior : sleep);
      painted[isReal ? 'real' : 'sleeping']++;
      const [r, g, b] = t !== null ? hd.rgb(t) : [0.32, 0.35, 0.40];
      for (let k = 1; k + 1 < poly.length; k++) {   // 부채꼴 삼각화 (페이지 1 관행)
        ht.tri.push(...poly[0], ...poly[k], ...poly[k + 1]);
        ht.col.push(r, g, b, r, g, b, r, g, b);
        ht.triFace.push(fi);
      }
      ht.wire.push(...wire);
    } else if (f.domain) domain.push(...wire);          // 도메인 면 — s1 평면 없음(비 prior)
    else (isPrior ? ghostPrior : ghost).push(...wire);
  });
  d.paintCounts = { scope: state.heatScope, ...painted };
  d.heatMesh = null; d.heatMeshPrior = null;
  d.heatMeshSleep = null; d.heatMeshSleepPrior = null;
  const mkHeat = (ht, group, sleeping) => {
    if (!ht.tri.length) return null;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(ht.tri, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(ht.col, 3));
    const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      vertexColors: true, side: THREE.DoubleSide,
      ...(sleeping ? { transparent: true, opacity: 0.3, depthWrite: false } : {}) }));
    if (sleeping) mesh.renderOrder = 1;   // F* 오버레이(2)보다 아래, 실재 면 위
    mesh.userData = { triFace: Uint32Array.from(ht.triFace) };
    group.add(mesh);
    const wg = new THREE.BufferGeometry();
    wg.setAttribute('position', new THREE.Float32BufferAttribute(ht.wire, 3));
    const line = new THREE.LineSegments(wg, sleeping
      ? new THREE.LineDashedMaterial({ color: COL.ghost, dashSize: 0.45, gapSize: 0.3,
                                       transparent: true, opacity: 0.6 })
      : new THREE.LineBasicMaterial({ color: COL.border, transparent: true,
                                      opacity: 0.55 }));
    if (sleeping) line.computeLineDistances();
    group.add(line);
    return mesh;
  };
  d.heatMesh = mkHeat(heat, heatGroup, false);
  d.heatMeshPrior = mkHeat(heatPrior, shiftGroup, false);
  d.heatMeshSleep = mkHeat(sleep, heatGroup, true);
  d.heatMeshSleepPrior = mkHeat(sleepPrior, shiftGroup, true);
  d.ghostWire = null; d.ghostWirePrior = null; d.domainWire = null;
  const mkWire = (arr, hex, opacity, group) => {
    if (!arr.length) return null;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
    const w = new THREE.LineSegments(g, new THREE.LineBasicMaterial({
      color: hex, transparent: true, opacity }));
    group.add(w);
    return w;
  };
  d.ghostWire = mkWire(ghost, COL.ghost, 0.5, wireGroup);
  d.ghostWirePrior = mkWire(ghostPrior, COL.ghost, 0.5, shiftGroup);
  d.domainWire = mkWire(domain, COL.domain, 0.4, wireGroup);
  attachOverlay(d);      // S2 초기 상태(F*) 오버레이 — 캐시돼 있으면 재부착(visible 토글 계약)
  applyDeltaShift();     // 3c 선택 행의 δ̂ 평행이동(아니면 0) + 동기화 배지
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
  if (d.ghostWirePrior) d.ghostWirePrior.visible = state.showGhost;
  if (d.domainWire) d.domainWire.visible = state.showDomain;
  if (d.s2ov) {   // S2 초기 상태(F*) 오버레이 — visible 토글만 (지오메트리 불변)
    if (d.s2ov.base) d.s2ov.base.visible = state.overlayS2;
    if (d.s2ov.prior) d.s2ov.prior.visible = state.overlayS2;
  }
  if (d.gtOv) {   // ⑨ LoD2 지붕면 — visible 토글만 (고정 기준면)
    if (d.gtOv.fill) d.gtOv.fill.visible = state.overlayGt;
    if (d.gtOv.wire) d.gtOv.wire.visible = state.overlayGt;
  }
  if (d.cellOv)   // ⑩ 구멍/과잉 셀 — visible 토글만 (로드 시 1회 계산)
    for (const m of [d.cellOv.holeFill, d.cellOv.holeWire,
                     d.cellOv.excFill, d.cellOv.excWire])
      if (m) m.visible = state.overlayCellsGt;
  if (d.colorPrev) {   // ⑪ 학습 색 미리보기 — visible 토글만
    if (d.colorPrev.base) d.colorPrev.base.visible = state.colorPreview;
    if (d.colorPrev.prior) d.colorPrev.prior.visible = state.colorPreview;
  }
  // ⑪ 배타 규약 — 색 미리보기 ON이면 진단 칠(히트맵 채움)은 자동 숨김(두 색 체계 겹침
  // 방지). 경계 와이어는 남겨 기하 맥락 유지, 램프 범례는 renderRampLegend가 함께 숨김.
  const paintOn = !state.colorPreview;
  for (const m of [d.heatMesh, d.heatMeshPrior, d.heatMeshSleep, d.heatMeshSleepPrior])
    if (m) m.visible = paintOn;
  emptyGroup(selGroup); hiliteMats = [];
  if (state.selFace !== null && d.faceWire && d.faceWire[state.selFace]) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(d.faceWire[state.selFace], 3));
    const mat = new THREE.LineBasicMaterial({ color: COL.selFill, transparent: true, opacity: 1 });
    const line = new THREE.LineSegments(g, mat);
    if (d.faceIsPrior && d.faceIsPrior[state.selFace]) {   // prior 면 윤곽도 δ̂ 위치 추종
      const sh = currentDeltaShift();
      line.position.set(sh[0], sh[1], sh[2]);
    }
    selGroup.add(line);
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
  if (!d || !renderer) return;
  const meshes = [d.heatMesh, d.heatMeshPrior,          // prior 분할 메시 포함
                  d.heatMeshSleep, d.heatMeshSleepPrior // 잠든 면(전체 토글 시) — 귀속 픽
                 ].filter(Boolean);
  if (!meshes.length) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1,
                                -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const hits = raycaster.intersectObjects(meshes, false);
  if (!hits.length) {
    if (state.selFace !== null) { state.selFace = null; restyle(); renderPanel(); }
    return;
  }
  selectFace(hits[0].object.userData.triFace[hits[0].faceIndex]);
}
// ---------- 스텝 선택 + 3D 동기화 (연계 판독 ①·③) ----------
const STAGE_ORD = { '3a': 0, '3b': 1, '3c': 2, '3d': 3 };
// 히트맵 상태 등록부(heatStatesOf — ckpt 파일이 있으면 s5/s15/s45/s130 중간 상태 포함)
// 중 선택 스텝 이하 최대를 고른다. 파일 없으면 종전 3종(step0/3b final/3c final)과 동일.
function heatModeForStep(d, step) {
  if (!d || !d.s3 || !step) return state.heatMode;
  const so = STAGE_ORD[String(step.stage)] ?? 99, sn = step.step ?? 0;
  const states = heatStatesOf(d);
  if (!states.length) return state.heatMode;
  let best = states[0];
  for (const st of states)   // 오름차순 — 마지막 충족 상태 = 이하 최대
    if (st.ord < so || (st.ord === so && st.step <= sn)) best = st;
  return best.key;
}
function heatStateLabel(d, mode) {
  const s3 = d && d.s3;
  if (!s3) return '—';
  if (mode === 'diff') {
    const a = heatStateByKey(d, state.diffTarget), b = heatStateByKey(d, state.diffBase);
    return `차이(${a ? a.label : '?'} − ${b ? b.label : '?'})`;
  }
  if (mode === 'anchor_cost') return '셀 앵커 비용 C_k (상수)';
  if (mode === 'anchor_flip') return '뒤집기 값 ΔW (상수)';
  const hs = heatStateByKey(d, mode);
  return hs ? hs.label : '—';
}
// 선택 스텝이 3c 행이면 그 행의 delta_hat, 아니면 0 — prior 계열 평행이동량(m).
function currentDeltaShift() {
  const d = state.run;
  const step = (d && d.s3 && state.selStep !== null) ? d.s3.steps[state.selStep] : null;
  if (!step || String(step.stage) !== '3c') return [0, 0, 0];
  const dh = (step.delta_hat || []).map(Number);
  return (dh.length === 3 && dh.every(Number.isFinite)) ? dh : [0, 0, 0];
}
function applyDeltaShift() {
  const sh = currentDeltaShift();
  shiftGroup.position.set(sh[0], sh[1], sh[2]);
  renderSyncBadge();
}
// 3D 동기화 배지 — "3D 표시 중: <구간> s<step> 히트맵" + 3c면 "prior δ̂ 적용: [x,y,z] m"
function renderSyncBadge() {
  const el = $('#syncbadge');
  if (!el) return;
  const d = state.run;
  const hd = d && heatData(d);
  if (!hd) { el.style.display = 'none'; return; }
  el.style.display = 'block';
  let h = `3D 표시 중: <b style="color:#8ecbff">${esc(heatStateLabel(d, hd.mode))} 히트맵</b>` +
    (state.autoHeat ? '' : ' <span style="color:#7a8494">(스텝 추적 꺼짐)</span>');
  // 상시 라벨(오독 정정) — 이 화면은 잔차 "귀속 지도"이며 렌더에 실재하는 면은 F*뿐
  h += `<br><span style="color:#9fb4cc">잔차 귀속 지도 — ${state.heatScope === 'all'
    ? '<b style="color:#ffd866">전체 후보 면</b>(잠든 면=반투명·점선 — 렌더 실재는 F*뿐)'
    : '<b style="color:#c8ccd4">F* 면만 표시 중</b> (잠든 후보 면은 토글)'}</span>`;
  const step = (d.s3 && state.selStep !== null) ? d.s3.steps[state.selStep] : null;
  if (step && String(step.stage) === '3c') {
    const sh = currentDeltaShift();
    h += `<br>prior δ̂ 적용: <b style="color:#ff9a3c">[${sh.map(v => fmtNum(v, 3)).join(', ')}] m</b>` +
      (d.s1PlanesMissing ? ' <span class="bad">(s1_planes.json 없음 — prior 판별 불가·이동 대상 0)</span>'
       : d.faceIsPrior && d.faceIsPrior.some(v => v) ? '' : ' <span style="color:#7a8494">(prior 면 0)</span>');
  }
  if (state.overlayS2) h += `<br><span style="color:#c8ccd4">S2 초기 상태(F*) 오버레이 ON</span>`;
  if (state.overlayGt)   // ⑨ 필수 배지 문구 — 평가 전용, δ̂ 이동 무관 고정
    h += `<br><span style="color:#5fe08a">LoD2 지붕면 ON (평가 전용 — 방법 입력 아님 · δ̂ 이동 무관 고정)</span>`;
  if (state.overlayCellsGt) {   // ⑩ 카운트 — 계산 완료 전엔 로딩 표기
    const st = d.cellOv && d.cellOv.stats;
    h += `<br><span style="color:#ff9b93">초기 점유 vs LoD2 ON${st
      ? ` — 구멍 ${st.holes} · 과잉 ${st.excess}` : ' (계산 중…)'}</span>`;
  }
  if (state.colorPreview) {     // ⑪ 배타 상태 명시
    const st = d.colorPrev && d.colorPrev.stats;
    h += `<br><span style="color:#d9a0ff">학습 색(텍스처) 미리보기 ON — 진단 칠 자동 숨김${st
      ? ` · 점 ${st.shown.toLocaleString()}` : ' (로딩 중…)'}</span>`;
  }
  el.innerHTML = h;
}
// 스텝 선택 단일 경로 — 타임라인 칩·체크포인트 점프·곡선 점 클릭 공용.
// autoHeat ON이면 히트맵을 이하 최대 체크포인트 상태로 전환(씬 재구축은 모드 변경 때만).
function selectStep(i) {
  state.selStep = i;
  const d = state.run;
  if (d && d.s3 && state.autoHeat && state.selStep !== null) {
    const want = heatModeForStep(d, d.s3.steps[i]);
    if (want !== state.heatMode) { state.heatMode = want; buildScene(d); }
  }
  applyDeltaShift();   // 3c 행의 δ̂ 평행이동(아니면 0) — 재구축 없는 경로에서도 항상
  restyle();           // prior 선택 윤곽의 δ̂ 추종 갱신
  renderTimeline(); renderPanel();
}
// s2_cells.json 공유 lazy fetch — F* 오버레이(o_state 재유도)·앵커 가시화(⑦ — o_state·t)·
// 초기 점유 vs LoD2(⑩ — centroid·face_ids)가 같은 1회 로드를 나눠 쓴다.
// 실패 시 null 기록(각자 폴백/오류 안내).
async function ensureCellsInfo(d) {
  if (d.cellsInfo !== undefined) return d.cellsInfo;
  if (d.cellsInfoLoading) return d.cellsInfoLoading;
  d.cellsInfoLoading = (async () => {
    let info = null;
    try {
      const r = await fetch(`../runs/${encodeURIComponent(d.name)}/s2_cells.json`);
      if (r.ok) {
        const cellsJ = await r.json();
        const byId = {};
        let n = 0;
        (cellsJ.cells || []).forEach(c => {
          byId[c.cell_id] = { o: c.o_state ? 1 : 0,
                              t: Number.isFinite(c.t) ? c.t : null,
                              cen: (Array.isArray(c.centroid) && c.centroid.length === 3)
                                ? c.centroid : null,      // ⑩ 셀 중심 — gt 지붕고 대조
                              faces: c.face_ids || [] };  // ⑩ 셀 채움 지오메트리 참조
          n++;
        });
        info = { byId, n };
      }
    } catch { /* null 기록 */ }
    d.cellsInfo = info;
    d.cellsInfoLoading = null;
    return info;
  })();
  return d.cellsInfoLoading;
}
// S2 초기 상태(F*) 오버레이 — s2_cells.json lazy fetch로 o_state 재유도(페이지 2 파서 이식),
// 실패 시 s2_faces.initial_real 폴백. 병합 지오메트리 base/prior 2개를 1회만 생성해 캐시.
async function ensureS2Overlay(d) {
  if (d.s2ov) return d.s2ov;
  if (d.s2ovLoading) return d.s2ovLoading;
  d.s2ovLoading = (async () => {
    let real = null;
    const info = await ensureCellsInfo(d);
    if (info) {
      const occOf = (cid) => (cid === null || cid === undefined) ? 0
        : (info.byId[cid] ? info.byId[cid].o : 0);
      real = d.faces.map(f => Math.abs(occOf(f.cell_a) - occOf(f.cell_b)) === 1);
      d.s2ovSource = 's2_cells.json o_state 재유도(|Δo|=1 — 페이지 2 파서 이식)';
    }
    if (!real) {
      real = d.faces.map(f => !!f.initial_real);
      d.s2ovSource = 's2_cells.json 없음 — s2_faces.initial_real 폴백';
    }
    const tri = [], triPrior = [];
    d.faces.forEach((f, fi) => {
      if (!real[fi]) return;
      const poly = f.poly3d || [];
      const dst = (d.faceIsPrior && d.faceIsPrior[fi]) ? triPrior : tri;
      for (let k = 1; k + 1 < poly.length; k++)
        dst.push(...poly[0], ...poly[k], ...poly[k + 1]);
    });
    const mkOv = (arr) => {
      if (!arr.length) return null;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
        color: COL.fstar, transparent: true, opacity: 0.16, side: THREE.DoubleSide,
        depthWrite: false, polygonOffset: true,               // 히트맵 동일면 z-fighting 회피
        polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
      m.renderOrder = 2;
      m.visible = false;
      return m;
    };
    d.s2ov = { base: mkOv(tri), prior: mkOv(triPrior),
               nReal: real.reduce((a, b) => a + (b ? 1 : 0), 0) };
    d.s2ovLoading = null;
    return d.s2ov;
  })();
  return d.s2ovLoading;
}
// ---------- ⑨ LoD2 지붕면 오버레이 (평가 전용 — 방법 입력 아님) ----------
// gt_planes support_local 링 → 병합 채움(부채꼴) + 병합 와이어. δ̂ 이동(shiftGroup)의
// 영향을 받지 않는 고정 기준면이라 heatGroup에만 부착한다(비교 잣대 계약).
function ensureGtOverlay(d) {
  if (d.gtOv !== undefined) return d.gtOv;
  const tri = [], wire = [];
  for (const g of d.gtPlanes) {
    const poly = g.support_local;
    for (let k = 1; k + 1 < poly.length; k++)   // 부채꼴 삼각화 (페이지 1 관행)
      tri.push(...poly[0], ...poly[k], ...poly[k + 1]);
    for (let k = 0; k < poly.length; k++) {
      const a = poly[k], b = poly[(k + 1) % poly.length];
      wire.push(a[0], a[1], a[2], b[0], b[1], b[2]);
    }
  }
  if (!tri.length) { d.gtOv = null; return null; }
  const fg = new THREE.BufferGeometry();
  fg.setAttribute('position', new THREE.Float32BufferAttribute(tri, 3));
  const fill = new THREE.Mesh(fg, new THREE.MeshBasicMaterial({
    color: COL.lod2, transparent: true, opacity: 0.16, side: THREE.DoubleSide,
    depthWrite: false, polygonOffset: true,          // 동일 지붕면 z-fighting 회피
    polygonOffsetFactor: -3, polygonOffsetUnits: -3 }));
  fill.renderOrder = 3;                              // F* 오버레이(2) 위
  const wg = new THREE.BufferGeometry();
  wg.setAttribute('position', new THREE.Float32BufferAttribute(wire, 3));
  const wireObj = new THREE.LineSegments(wg, new THREE.LineBasicMaterial({
    color: COL.lod2, transparent: true, opacity: 0.9 }));
  wireObj.renderOrder = 3;
  fill.visible = false; wireObj.visible = false;
  d.gtOv = { fill, wire: wireObj, n: d.gtPlanes.length };
  return d.gtOv;
}
// ---------- ⑩ 초기 점유 vs LoD2 — 구멍/과잉 셀 (이전 분석의 화면화) ----------
// 파라미터는 파이썬 대조 분석과 동일 고정: 지붕면 |n_z|>0.2, 여유 ±0.3 m
// (B022 대조값: 구멍 59 · 과잉 234). 평면 규약 n·p = d → z = (d − n_x·x − n_y·y)/n_z.
const CELLGT = { nzMin: 0.2, marginM: 0.3 };
function pointInRingXY(x, y, ring) {   // ray casting — 셀 수천×면 ≤20이라 가벼움
  let inside = false;
  const n = ring.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi)
      inside = !inside;
  }
  return inside;
}
function computeCellsVsGt(d) {
  const roof = d.gtPlanes.filter(g =>
    Math.abs((g.n || [])[2] ?? 0) > CELLGT.nzMin);
  const holes = [], excess = [];
  let covered = 0, judged = 0;
  for (const [cid, c] of Object.entries(d.cellsInfo.byId)) {
    if (!c.cen) continue;
    judged++;
    const [cx, cy, cz] = c.cen;
    let zmax = null;
    for (const g of roof) {
      if (!pointInRingXY(cx, cy, g.support_local)) continue;
      const [nx, ny, nz] = g.n;
      const z = (g.d - nx * cx - ny * cy) / nz;
      if (zmax === null || z > zmax) zmax = z;
    }
    if (zmax === null) continue;   // gt 지붕 XY 밖 — 판정 근거 없음(대조 제외)
    covered++;
    if (c.o === 0 && cz < zmax - CELLGT.marginM) holes.push(cid);
    if (c.o === 1 && cz > zmax + CELLGT.marginM) excess.push(cid);
  }
  return { holes, excess, covered, judged, roofPlanes: roof.length };
}
// 셀 채움 지오메트리 — 셀 face_ids의 s2_faces poly3d 재사용(중복 면은 1회, 구멍 우선).
// x-ray(depthTest 끔): 내부 구멍 셀이 불투명 실재 면에 가려지지 않아야 한다(진단 오버레이).
function cellFillObjs(d, cellIds, hex, exclude) {
  const tri = [], wire = [], seen = new Set();
  for (const cid of cellIds) {
    const c = d.cellsInfo.byId[cid];
    if (!c) continue;
    for (const fid of c.faces) {
      if (seen.has(fid) || (exclude && exclude.has(fid))) continue;
      seen.add(fid);
      const fi = d.faceIdx[fid];
      const poly = fi !== undefined ? (d.faces[fi].poly3d || []) : [];
      if (poly.length < 3) continue;
      for (let k = 1; k + 1 < poly.length; k++)
        tri.push(...poly[0], ...poly[k], ...poly[k + 1]);
      for (let k = 0; k < poly.length; k++) {
        const a = poly[k], b = poly[(k + 1) % poly.length];
        wire.push(a[0], a[1], a[2], b[0], b[1], b[2]);
      }
    }
  }
  if (!tri.length) return { fill: null, wireObj: null, faceSet: seen };
  const fg = new THREE.BufferGeometry();
  fg.setAttribute('position', new THREE.Float32BufferAttribute(tri, 3));
  const fill = new THREE.Mesh(fg, new THREE.MeshBasicMaterial({
    color: hex, transparent: true, opacity: 0.4, side: THREE.DoubleSide,
    depthWrite: false, depthTest: false }));
  fill.renderOrder = 4;                         // 진단 x-ray — 항상 판독 가능
  const wg = new THREE.BufferGeometry();
  wg.setAttribute('position', new THREE.Float32BufferAttribute(wire, 3));
  const wireObj = new THREE.LineSegments(wg, new THREE.LineBasicMaterial({
    color: hex, transparent: true, opacity: 0.55, depthTest: false }));
  wireObj.renderOrder = 4;
  fill.visible = false; wireObj.visible = false;
  return { fill, wireObj, faceSet: seen };
}
// 첫 켬 때 1회 계산·생성 후 캐시. 초기 점유(S2 동결) vs 고정 LoD2의 대조라
// δ̂ 이동과 무관 — 전부 heatGroup 부착(고정 표시).
async function ensureCellsVsGt(d) {
  if (d.cellOv !== undefined) return d.cellOv;
  if (d.cellOvLoading) return d.cellOvLoading;
  d.cellOvLoading = (async () => {
    let ov = null;
    const info = await ensureCellsInfo(d);
    if (!info) d.cellOvNote = 's2_cells.json 로드 실패 — 대조 불가';
    else if (!d.gtPlanes.length) d.cellOvNote = 'gt_planes 없음 — 대조 불가';
    else {
      const r = computeCellsVsGt(d);
      const hole = cellFillObjs(d, r.holes, COL.hole, null);
      const exc = cellFillObjs(d, r.excess, COL.excess, hole.faceSet);  // 구멍 우선
      ov = { holeFill: hole.fill, holeWire: hole.wireObj,
             excFill: exc.fill, excWire: exc.wireObj,
             stats: { holes: r.holes.length, excess: r.excess.length,
                      covered: r.covered, cells: r.judged,
                      roof_planes: r.roofPlanes, nz_min: CELLGT.nzMin,
                      margin_m: CELLGT.marginM } };
      d.cellOvNote = null;
    }
    d.cellOv = ov;
    d.cellOvLoading = null;
    return ov;
  })();
  return d.cellOvLoading;
}
// ---------- ⑪ 학습 색(텍스처) 3D 미리보기 ----------
// DataView 수제 fp16→fp32 (numpy float16 tofile — 리틀 엔디언 IEEE 754 half)
function fp16ToF32(h) {
  const s = (h & 0x8000) ? -1 : 1, e = (h >> 10) & 0x1f, m = h & 0x3ff;
  if (e === 0) return s * m * 2 ** -24;              // ±0·서브노멀
  if (e === 31) return m ? NaN : s * Infinity;
  return s * (1 + m / 1024) * 2 ** (e - 15);
}
const COLOR_PREV_MAX = 300000;   // 표시 상한 — 결정론 스트라이드 씨닝(기존 관행)
async function ensureColorPreview(d) {
  if (d.colorPrev !== undefined) return d.colorPrev;
  if (d.colorPrevLoading) return d.colorPrevLoading;
  d.colorPrevLoading = (async () => {
    let cp = null;
    const ca = ((d.manifest || {}).s3b_def || {}).colors_artifact || null;
    if (!ca) d.colorPrevNote = 'manifest.s3b_def.colors_artifact 없음 (3b 미완주 런)';
    else try {
      const base = `../runs/${encodeURIComponent(d.name)}`;
      const [binR, seedsR] = await Promise.all([
        fetch(`${base}/${ca.file || 's3b_colors.f16.bin'}`),
        fetch(`${base}/s2_seeds.json`)]);   // 첫 켬 때만 — B022 120 MB 명시 경고(패널)
      if (!binR.ok) throw new Error(`${ca.file} ${binR.status}`);
      if (!seedsR.ok) throw new Error(`s2_seeds.json ${seedsR.status}`);
      const buf = await binR.arrayBuffer();
      const seedsJ = await seedsR.json();
      const seeds = seedsJ.seeds || [];
      const spacing = ((seedsJ.grid || {}).spacing_m) || 0.30;
      if (buf.byteLength !== seeds.length * 3 * 2)
        throw new Error(`바이트 길이 ${buf.byteLength} ≠ 시드 ${seeds.length}×3×2 — ` +
                        '번들 재생성 중이거나 계약 불일치');
      // sha256 대조 — crypto.subtle 가용 시에만(HTTP LAN 환경은 생략, null)
      let shaOk = null;
      if (ca.sha256 && typeof crypto !== 'undefined' && crypto.subtle) {
        try {
          const dig = await crypto.subtle.digest('SHA-256', buf);
          const hex = [...new Uint8Array(dig)]
            .map(b => b.toString(16).padStart(2, '0')).join('');
          shaOk = hex === ca.sha256;
        } catch { /* null 유지 */ }
      }
      const dv = new DataView(buf);
      // F*(initial_real) 면의 시드만 — 잠든 면 시드 제외(실재 표면의 텍스처만)
      const keptIdx = [];
      for (let i = 0; i < seeds.length; i++) {
        const fi = d.faceIdx[seeds[i].face_id];
        if (fi !== undefined && d.faces[fi].initial_real) keptIdx.push(i);
      }
      const stride = Math.max(1, Math.ceil(keptIdx.length / COLOR_PREV_MAX));
      const pos = [], col = [], posP = [], colP = [];
      let shown = 0;
      for (let j = 0; j < keptIdx.length; j += stride) {
        const i = keptIdx[j];
        const s = seeds[i];
        const mu = s.mu;
        if (!mu || mu.length !== 3) continue;
        const o = i * 6;
        const r = Math.min(1, Math.max(0, fp16ToF32(dv.getUint16(o, true))));
        const g = Math.min(1, Math.max(0, fp16ToF32(dv.getUint16(o + 2, true))));
        const b = Math.min(1, Math.max(0, fp16ToF32(dv.getUint16(o + 4, true))));
        const fi = d.faceIdx[s.face_id];
        const isPrior = !!(d.faceIsPrior && d.faceIsPrior[fi]);
        (isPrior ? posP : pos).push(mu[0], mu[1], mu[2]);
        (isPrior ? colP : col).push(r, g, b);
        shown++;
      }
      // 점 크기 = 시드 간격 × √스트라이드 (씨닝 후 커버리지 근사 보존 — 임의 결정)
      const size = spacing * Math.sqrt(stride);
      const mkPts = (p, c) => {
        if (!p.length) return null;
        const g = new THREE.BufferGeometry();
        g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
        g.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
        const pts = new THREE.Points(g, new THREE.PointsMaterial({
          size, vertexColors: true, sizeAttenuation: true }));
        pts.visible = false;
        return pts;
      };
      cp = { base: mkPts(pos, col), prior: mkPts(posP, colP),
             stats: { seeds: seeds.length, kept_fstar: keptIdx.length, shown,
                      stride, point_size_m: +size.toFixed(3),
                      spacing_m: spacing, sha_ok: shaOk,
                      sha_expected: ca.sha256 ? String(ca.sha256).slice(0, 12) : null } };
      d.colorPrevNote = null;
    } catch (e) {
      d.colorPrevNote = `학습 색 로드 실패: ${e.message}`;
    }
    d.colorPrev = cp;
    d.colorPrevLoading = null;
    return cp;
  })();
  return d.colorPrevLoading;
}
function attachOverlay(d) {
  if (!d) return;
  const put = (m, group, vis) => {
    if (!m) return;
    if (m.parent !== group) group.add(m);
    m.visible = vis;
  };
  if (d.s2ov) {
    put(d.s2ov.base, heatGroup, state.overlayS2);
    put(d.s2ov.prior, shiftGroup, state.overlayS2);
  }
  if (d.gtOv) {          // ⑨ LoD2 — 고정 기준면(shiftGroup 금지)
    put(d.gtOv.fill, heatGroup, state.overlayGt);
    put(d.gtOv.wire, heatGroup, state.overlayGt);
  }
  if (d.cellOv) {        // ⑩ 구멍/과잉 — 초기 상태 고정 표시
    for (const m of [d.cellOv.holeFill, d.cellOv.holeWire,
                     d.cellOv.excFill, d.cellOv.excWire])
      put(m, heatGroup, state.overlayCellsGt);
  }
  if (d.colorPrev) {     // ⑪ 학습 색 — prior 시드는 δ̂ 추종(히트맵 규약)
    put(d.colorPrev.base, heatGroup, state.colorPreview);
    put(d.colorPrev.prior, shiftGroup, state.colorPreview);
  }
}
// ---------- 앵커 가시화 2종 (⑦ — 셀별 상수를 면(경계) 위에 집계, 스텝 무관) ----------
// (a) 셀 앵커 비용 C_k(o;t) = −[o·log t + (1−o)·log(1−t)] (§2.2, w=1) — 면 = 인접 셀 최대
//     ("경계를 붙잡는 더 강한 증언 긴장"; 상태·증언 상충 극단은 ∞).
// (b) 뒤집기 값 ΔW(t) = |log(t/(1−t))| (w=1 초기) — 면 = 인접 셀 최소("이 경계를 바꾸는
//     가장 싼 뒤집기"); t∈{0,1} = ∞ → 별색(블루). t 없는 셀(구계약) = null(미표시).
// 도메인 외피 면 제외(잔차 히트맵 관행), cell_b 없는 면은 cell_a만.
const ANCHOR_INF_T = 2;   // norm 특수값 — rgb에서 별색 분기
function buildAnchorMaps(d) {
  if (d.anchorMaps) return d.anchorMaps;
  if (!d.cellsInfo) return null;
  const byId = d.cellsInfo.byId;
  const cost = new Array(d.faces.length).fill(null);
  const flip = new Array(d.faces.length).fill(null);
  const cellCost = (c) => {
    if (!c || !Number.isFinite(c.t)) return null;
    const term = c.o ? Math.log(c.t) : Math.log(1 - c.t);
    return term === -Infinity ? Infinity : -term;
  };
  const cellFlip = (c) => {
    if (!c || !Number.isFinite(c.t)) return null;
    if (c.t <= 0 || c.t >= 1) return Infinity;
    return Math.abs(Math.log(c.t / (1 - c.t)));
  };
  d.faces.forEach((f, fi) => {
    if (f.domain) return;
    const cells = [byId[f.cell_a],
                   (f.cell_b === null || f.cell_b === undefined) ? null : byId[f.cell_b]];
    let mxCost = null, mnFlip = null;
    for (const c of cells) {
      const cc = cellCost(c), cf = cellFlip(c);
      if (cc !== null && (mxCost === null || cc > mxCost)) mxCost = cc;
      if (cf !== null && (mnFlip === null || cf < mnFlip)) mnFlip = cf;
    }
    cost[fi] = mxCost;
    flip[fi] = mnFlip;
  });
  const statsOf = (arr, realOnly) => {
    let n = 0, inf = 0, fn = 0, mn = Infinity, mx = -Infinity, sum = 0;
    for (let i = 0; i < arr.length; i++) {
      const v = arr[i];
      if (v === null) continue;
      if (realOnly && !d.faces[i].initial_real) continue;   // F* 범위(기본)
      n++;
      if (v === Infinity) { inf++; continue; }
      fn++; sum += v;
      if (v < mn) mn = v;
      if (v > mx) mx = v;
    }
    return n ? { n, inf, min: fn ? mn : 0, max: fn ? mx : 0,
                 mean: fn ? sum / fn : null } : null;
  };
  d.anchorMaps = { cost, flip,
                   costStats: statsOf(cost, false), flipStats: statsOf(flip, false),
                   costStatsReal: statsOf(cost, true), flipStatsReal: statsOf(flip, true) };
  return d.anchorMaps;
}
function anchorHeatData(d, mode) {
  const isCost = mode === 'anchor_cost';
  const label = isCost
    ? '셀 앵커 비용 C_k = −[o·log t + (1−o)·log(1−t)] — 상수(스텝 무관)'
    : '뒤집기 값 ΔW = |log(t/(1−t))| — 상수(스텝 무관)';
  const am = d.anchorMaps;
  if (!am)
    return { mode, label: label + (d.cellsInfo === null
               ? ' · s2_cells.json 없음(값 없음)' : ' · s2_cells 로딩 중…'),
             value: () => undefined, norm: () => null, rgb: rampRgb,
             stats: null, diverging: false, anchorConst: true };
  const arr = isCost ? am.cost : am.flip;
  const scopeAll = state.heatScope === 'all';   // 표시 범위 — 잔차 히트맵과 같은 원칙
  const st = scopeAll ? (isCost ? am.costStats : am.flipStats)
                      : (isCost ? am.costStatsReal : am.flipStatsReal);
  return { mode, label,
    value: (fid) => {
      const fi = d.faceIdx[fid];
      if (fi === undefined) return undefined;
      return arr[fi] === null ? undefined : arr[fi];
    },
    norm: (v) => v === Infinity ? ANCHOR_INF_T
      : (st && Number.isFinite(v))
      ? (st.max > st.min ? (v - st.min) / (st.max - st.min) : 0.5) : null,
    rgb: (t) => t > 1.5 ? [0.42, 0.55, 1.0] : rampRgb(t),   // ∞ 별색 = 블루
    stats: st, diverging: false, anchorConst: true,
    aggNote: isCost ? '면 = 인접 셀 최대 (경계를 붙잡는 더 강한 증언 긴장)'
                    : '면 = 인접 셀 최소 (이 경계를 바꾸는 가장 싼 뒤집기)' };
}
function renderSelBadge() {
  const el = $('#selbadge');
  if (!el) return;
  const d = state.run;
  if (!d || state.selFace === null) { el.style.display = 'none'; return; }
  const f = d.faces[state.selFace];
  const hd = heatData(d);
  const v = hd ? hd.value(f.face_id) : undefined;
  const vTxt = v === Infinity ? '∞' : Number.isFinite(v) ? (+v).toFixed(4) : '—';
  const vName = !hd ? '잔차'
    : hd.mode === 'diff' ? 'Δ잔차'
    : hd.mode === 'anchor_cost' ? 'C_k'
    : hd.mode === 'anchor_flip' ? 'ΔW' : '잔차';
  el.style.display = 'block';
  el.innerHTML = `<b style="color:#ffe066">${esc(f.face_id)}</b> ·
    ${vName} ${vTxt} ·
    ${f.initial_real ? 'F* 실재' : '게이트 0'} · ${(f.area_m2 ?? 0).toFixed(2)} m²
    <span class="note">재클릭·빈 공간·ESC=해제</span>`;
}
function renderRampLegend() {
  const el = $('#ramplegend');
  if (!el) return;
  const d = state.run;
  // ⑪ 색 미리보기 ON — 진단 칠이 숨겨진 상태라 램프 범례도 숨긴다(오독 방지)
  if (state.colorPreview) { el.style.display = 'none'; return; }
  const hd = d && heatData(d);
  const st = hd && hd.stats;
  if (!st) { el.style.display = 'none'; return; }
  const stops = hd.diverging
    ? [-1, -0.5, 0, 0.5, 1].map(t => hd.rgb(t))
    : [0, 0.5, 1].map(t => hd.rgb(t));
  const cssStops = stops.map(c =>
    `rgb(${c.map(x => Math.round(x * 255)).join(',')})`).join(',');
  el.style.display = 'block';
  el.innerHTML = `${esc(hd.label)}${hd.anchorConst ? '' : ' (근사)'}<br>
    <span>${st.min.toFixed(3)}</span>
    <span style="display:inline-block;width:90px;height:9px;vertical-align:middle;
      border:1px solid #2e3542;background:linear-gradient(90deg,${cssStops})"></span>
    <span>${st.max.toFixed(3)}</span>` +
    (hd.diverging ? '<br><span>청록=감소(색으로 설명) · 앰버=잔존/증가(기하 신호)</span>' : '') +
    (hd.anchorConst && st.inf ? `<br><span style="color:#6b8cff">■</span>
       <span>∞ (t∈{0,1}) — ${st.inf}면 별색</span>` : '');
}

// ---------- 자동 검사 (체크리스트 ②·③·⑨~⑪의 근거) ----------
// δ scope(δ가 걸리는 prior 평면 수) — s3c_def 우선, 없으면 3a의 s3_def 기록.
function deltaScopeOf(d) {
  const m = d.manifest || {};
  return (m.s3c_def || {}).delta_scope_planes ?? (m.s3_def || {}).delta_scope_planes ?? null;
}
// 3c 런 분류 — 주입(manifest.injection) / scope 0(음성) / 비변화 통제.
function runKind3c(d) {
  const inj = (d.manifest || {}).injection || null;
  if (inj) return 'injected';
  return deltaScopeOf(d) === 0 ? 'scope0' : 'control';
}
// 주입 정답 벡터 — expected_delta_hat이 수치 3벡터면 그 값(부호 규약은 writer 명기),
// 문자열(부호 규약 산문)뿐이면 −delta_applied 폴백(주입을 상쇄하는 방향 가정)을 출처와 함께.
function expectedDeltaVec(inj) {
  if (!inj) return null;
  const num3 = (v) => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);
  if (num3(inj.expected_delta_hat))
    return { vec: inj.expected_delta_hat.map(Number), src: 'manifest.injection.expected_delta_hat' };
  if (num3(inj.delta_applied))
    return { vec: inj.delta_applied.map(v => -v),
             src: '폴백 −delta_applied (expected_delta_hat 수치 아님 — 상쇄 방향 가정)' };
  return null;
}
const vecNorm3 = (v) => (Array.isArray(v) && v.length === 3 && v.every(Number.isFinite))
  ? Math.hypot(v[0], v[1], v[2]) : null;
function autoChecks(d) {
  if (!d.s3 || !d.s3.steps.length) return null;
  const nSeedsManifest = ((d.manifest || {}).counts || {}).seeds;
  const scope0 = deltaScopeOf(d) === 0;
  const res = { wiringOk: true, wiringDetail: [], invOk: true, invDetail: [],
                steps: d.s3.steps.length, scope0 };
  for (const s of d.s3.steps) {
    const g = s.grad_norms || {};
    for (const [key] of GRAD_DEF) {
      const v = g[key];
      if (key === 'delta' && scope0) continue;   // δ scope 0 — grad 0이 구조적(음성 기록)
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
    if (String(s.stage) === '3c') {   // 3c: δ 해동 — 평면·o 동결만 계약(delta_frozen 요구 없음)
      if (inv.planes_frozen !== true) bad('planes_frozen != true (3c)');
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
  // 3c 요약 — δ̂ 최종/최대·정답 잔차(주입)·잔류(비변화)·부동(scope 0)·anchor_plane 진단
  const rows3c = d.s3.steps.filter(s => String(s.stage) === '3c');
  if (rows3c.length) {
    const kind = runKind3c(d);
    const s3c = { steps: rows3c.length, kind, scope: deltaScopeOf(d),
                  frozenOk: true, frozenDetail: [], colorsMoved: 0, deltaMoved: 0, psnr: null };
    for (const s of rows3c) {
      const p = s.param_step_norms || {};
      if (!((p.planes ?? null) === 0)) {
        s3c.frozenOk = false;
        if (s3c.frozenDetail.length < 6)
          s3c.frozenDetail.push(`step ${s.step}: param_step_norms.planes=${p.planes ?? '없음'}`);
      }
      if (Number.isFinite(p.colors) && p.colors > 0) s3c.colorsMoved++;
      if (Number.isFinite(p.delta) && p.delta > 0) s3c.deltaMoved++;
    }
    const cks3c = rows3c.filter(s => s.views_psnr)
      .map(s => {
        const vs = Object.values(s.views_psnr).filter(Number.isFinite);
        return { step: s.step, mean: vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null };
      }).filter(c => c.mean !== null);
    if (cks3c.length >= 2) {
      const first = cks3c[0], last = cks3c[cks3c.length - 1];
      s3c.psnr = { firstStep: first.step, lastStep: last.step,
                   first: first.mean, last: last.mean, improved: last.mean > first.mean };
    }
    const dh0 = ((rows3c[0].delta_hat) || []).map(Number);
    const dh = ((rows3c[rows3c.length - 1].delta_hat) || []).map(Number);
    s3c.delta_hat_first = dh0;
    s3c.delta_hat_final = dh;
    s3c.delta_norm_first = vecNorm3(dh0);
    s3c.residual_norm = vecNorm3(dh);            // |δ̂_final| — 비변화 런의 잔류 오차
    s3c.max_abs_delta_hat = Math.max(0,
      ...rows3c.flatMap(s => (s.delta_hat || []).map(v => Math.abs(+v || 0))));
    s3c.immobile = s3c.max_abs_delta_hat === 0;  // scope 0 런의 δ̂ 부동
    const expObj = expectedDeltaVec((d.manifest || {}).injection || null);
    s3c.expected = expObj ? expObj.vec : null;
    s3c.expected_src = expObj ? expObj.src : null;
    s3c.residual_vs_expected = (expObj && vecNorm3(dh) !== null)
      ? Math.hypot(dh[0] - expObj.vec[0], dh[1] - expObj.vec[1], dh[2] - expObj.vec[2]) : null;
    s3c.anchor_plane_first = (rows3c[0].losses || {}).anchor_plane ?? null;
    s3c.anchor_plane_last = (rows3c[rows3c.length - 1].losses || {}).anchor_plane ?? null;
    res.s3c = s3c;
  } else res.s3c = null;
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
    b2 = gb(ck.wiringOk, `3군 전부 > 0${ck.scope0 ? ' (δ 제외 — scope 0 구조적)' : ''}`, '0/결측 있음');
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
  // 3c 4항 — 주입 δ̂ 수렴(자동: 잔류 오차)·비변화 잔류 표기·scope 0 부동(자동)·anchor_plane 진단
  const sc3 = ck && ck.s3c;
  const naAll3c = na('3c 없음');
  let b9 = naAll3c, b10 = naAll3c, b11 = naAll3c, b12 = naAll3c;
  if (sc3) {
    b9 = sc3.kind !== 'injected' ? na('주입 런 아님')
      : sc3.expected === null ? gb(false, '', '정답 벡터 불명(injection)')
      : `<span class="badge prop">잔류 |δ̂−정답| ${fmtNum(sc3.residual_vs_expected, 3)} m</span>`;
    b10 = sc3.kind !== 'control' ? na('비변화 런 아님')
      : `<span class="badge prop">잔류 |δ̂| ${fmtNum(sc3.residual_norm, 3)} m</span>`;
    b11 = sc3.kind !== 'scope0' ? na('scope 0 런 아님')
      : gb(sc3.immobile, 'δ̂ 부동 (전 스텝 0)', `이동 감지 max|δ̂| ${fmtNum(sc3.max_abs_delta_hat, 4)}`);
    b12 = na(`진단 anchor_plane ${fmtNum(sc3.anchor_plane_first, 3)}→${fmtNum(sc3.anchor_plane_last, 3)}
      · |δ̂| ${fmtNum(sc3.delta_norm_first, 3)}→${fmtNum(sc3.residual_norm, 3)}`);
  }
  const row3c = `
    <div class="chkrow">
      <span class="chkitem"><b>⑨</b> [3c] 주입 런: δ̂ 정답선 수렴 — 최종 잔류 오차 ${b9}</span>
      <span class="chkitem"><b>⑩</b> [3c] 비변화 런: δ̂ 잔류 오차 표기 ${b10}</span>
      <span class="chkitem"><b>⑪</b> [3c] scope 0 런: δ̂ 부동 ${b11}</span>
      <span class="chkitem"><b>⑫</b> [3c] anchor_plane 곡선 ∝ |δ̂| 증가(진단 — 3d 예고) ${b12}</span>
    </div>`;
  const meta3b = sbd ? ` · 3b 계약: 색 A_g만 학습(trained=${esc((sbd.trained || []).join(','))}) ·
        steps ${sbd.steps ?? '—'} · lr ${sbd.lr ?? '—'} · ${esc(sbd.optimizer ?? '—')} ·
        기하 바이트 불변 ${sbd.frozen_checksum_ok === true ? '<span class="badge good">checksum ok</span>' : '<span class="badge bad">미확인</span>'}` : '';
  const scd = (d.manifest || {}).s3c_def || null;
  const meta3c = scd ? ` · 3c 계약: δ+색 학습(trained=${esc((scd.trained || []).join(','))}) ·
        목적 ${esc(scd.objective ?? 'photo')}만(anchor·area는 진단 기록) · steps ${scd.steps ?? '—'} ·
        lr_delta ${scd.lr_delta ?? '—'} · lr_rgb ${scd.lr_rgb ?? '—'} ·
        평면·o 동결 ${scd.frozen_checksum_ok === true ? '<span class="badge good">checksum ok</span>' : '<span class="badge bad">미확인</span>'}` : '';
  $('#checkstrip').innerHTML = `
    <div class="chkrow">
      <span class="chkitem"><b>①</b> 렌더-사진 정렬이 실루엣 수준에서 겹침 ${na('육안')}</span>
      <span class="chkitem"><b>②</b> grad_norms 3군(δ/평면/색) 전부 0이 아님 — 배선 증거 ${b2}</span>
      <span class="chkitem"><b>③</b> 불변량 전부 참(n_seeds 일치·α 이진·δ 동결·이동량 0) ${b3}</span>
      <span class="chkitem"><b>④</b> SYNTH residual이 구조적으로 근소 ${na('육안')}</span>
    </div>${row3b}${row3c}
    <div class="chkrow meta">
      <span><span class="badge prop">참고 기준</span> 엄격 런별 합불 아님 — 판독 기록 2026-08-27 방침(발견 기록으로 갈음).</span>
      <span>히트맵 표시 범위 기본 = <b>F*(initial_real) 면만</b> — 렌더에 실재하는 면은 F*뿐이고
        잠든 gate-0 후보 면은 '전체 후보 면' 토글(귀속용, 반투명·점선)로만 표시(오독 정정 2026-08-27).</span>
      <span>3a 계약: 최적화 0스텝 + backward 1회(가중치 갱신 없음) · δ 렌더 인자 배선·값 ${JSON.stringify(sd.delta_value ?? [0, 0, 0])} 고정 ·
        색 ${esc(sd.color || 'neutral-gray')} · α_g=|o_a−o_b| 유도 · densification/pruning 금지(수명 규칙 ①) ·
        렌더러 ${esc(sd.renderer || 'gsplat')}(미분 가능 렌더링)${meta3b}${meta3c}</span>
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
    const selSeg = state.selSegment === sg.id;
    h += `<div class="seg ${on ? 'on' : 'off'} ${selSeg ? 'segsel' : ''}">
      <div class="seghead" data-seg="${escAttr(sg.id)}"
        title="클릭 = 구간 산출물 요약 카드 (스텝 선택 유지 · 재클릭=닫기)">${esc(sg.label)}${summary}
        <button class="segbtn" data-seg="${escAttr(sg.id)}"
          title="구간 산출물 요약 카드 ${selSeg ? '닫기' : '열기'}">${selSeg ? '요약 닫기' : '산출물 요약'}</button></div>
      ${body}
      <div class="segdesc">${esc(sg.desc)}</div></div>`;
  }
  el.innerHTML = h;
  el.querySelectorAll('.stepchip').forEach(c => {
    c.onclick = () => selectStep(+c.dataset.step);   // 3D 동기화(히트맵·δ̂ 이동) 공용 경로
  });
  el.querySelectorAll('.seghead[data-seg]').forEach(sh => {   // ④ 구간 배지 = 요약 카드 토글
    sh.onclick = () => toggleSegment(sh.dataset.seg);
  });
  el.querySelectorAll('.segbtn[data-seg]').forEach(b => {     // 명시적 버튼 — 같은 토글 경로
    b.onclick = (e) => { e.stopPropagation(); toggleSegment(b.dataset.seg); };
  });
}
// 첫 로드 힌트 배지 1회(닫기 가능) — 구간 산출물 요약 카드 안내. localStorage에 닫음 기억
// (접근 불가 환경은 세션 1회로 동작).
const SEG_HINT_LS_KEY = 'p3_seghint_v1_closed';
let segHintShown = false;
function maybeShowSegHint() {
  if (segHintShown) return;
  segHintShown = true;
  try { if (localStorage.getItem(SEG_HINT_LS_KEY) === '1') return; } catch { /* 무시 */ }
  const el = document.createElement('div');
  el.id = 'seghint';
  el.innerHTML = `힌트: 타임라인의 <b>[산출물 요약]</b> 버튼(구간 배지)을 누르면 그 단계의
    고유 산출물 요약 카드가 우측 패널에 열립니다.
    <button class="small" id="seghintClose">닫기</button>`;
  document.body.appendChild(el);
  const close = el.querySelector('#seghintClose');
  if (close) close.onclick = () => {
    el.remove();
    try { localStorage.setItem(SEG_HINT_LS_KEY, '1'); } catch { /* 무시 */ }
  };
}
// ④ 구간 배지 클릭 — 요약 카드는 별도 섹션(#segsummary), 스텝 선택(selStep)은 건드리지 않는다.
// 열람은 런별 d.segViews에 누적(판독 JSON auto.segment_summary_viewed).
function toggleSegment(sg) {
  state.selSegment = (state.selSegment === sg) ? null : sg;
  const d = state.run;
  if (d && state.selSegment) {
    d.segViews = d.segViews || { opens: 0, segments: {} };
    d.segViews.opens++;
    d.segViews.segments[state.selSegment] = (d.segViews.segments[state.selSegment] || 0) + 1;
  }
  renderTimeline(); renderPanel();
  if (state.selSegment !== null) {
    const card = $('#segsummary');
    if (card) card.scrollIntoView({ block: 'start' });
  }
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
// δ̂ 성분별 궤적 (구간 3c) — 음수 허용 y축 + 0선 + 주입 정답선(수평 점선, 성분 색).
// multiCurveSvg는 0 기준 y축이라 별도 구현. 점 클릭=스텝 선택(data-sidx — bindPanel 공용),
// 강조 점=체크포인트, 식별 = 색 + 끝점 직접 라벨 + <title> 툴팁 + 인접 표(색 단독 아님).
function deltaHatSvg(d, refVec) {
  const series = DELTA_DEF.map(([k, col], ci) => ({ key: `δ̂${k}`, col,
    pts: stagePts(d, '3c', (s) => (s.delta_hat || [])[ci]).filter(p => Number.isFinite(p.v)) }));
  const allV = series.flatMap(sr => sr.pts.map(p => p.v));
  if (!allV.length) return '<p class="note">3c 행에 delta_hat 값 없음</p>';
  const refs = (refVec || []).filter(Number.isFinite);
  const W = 408, H = 150, L = 46, R = 70, T = 12, Bm = 20;
  let vmin = Math.min(...allV, ...refs, 0), vmax = Math.max(...allV, ...refs, 0);
  const span = (vmax - vmin) || 1e-6;
  vmin -= span * 0.08; vmax += span * 0.08;
  const xs = series.flatMap(sr => sr.pts.map(p => p.x));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const X = (x) => x1 > x0 ? L + (x - x0) / (x1 - x0) * (W - L - R) : L + (W - L - R) / 2;
  const Y = (v) => T + (1 - (v - vmin) / (vmax - vmin)) * (H - T - Bm);
  let h = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img"
      aria-label="δ̂ 성분별(x·y·z) 스텝 궤적 — 구간 3c">
    <line x1="${L}" y1="${T}" x2="${L}" y2="${H - Bm}" stroke="#2e3542"/>
    <text x="${L - 4}" y="${T + 8}" text-anchor="end">${fmtNum(vmax, 3)}</text>
    <text x="${L - 4}" y="${H - Bm + 3}" text-anchor="end">${fmtNum(vmin, 3)}</text>
    <text x="${X(x0).toFixed(1)}" y="${H - 6}" text-anchor="middle">${x0}</text>
    ${x1 > x0 ? `<text x="${X(x1).toFixed(1)}" y="${H - 6}" text-anchor="middle">${x1}</text>` : ''}
    <line x1="${L}" y1="${Y(0).toFixed(1)}" x2="${W - R}" y2="${Y(0).toFixed(1)}"
      stroke="#556070" stroke-dasharray="4,3"/>
    <text x="${L + 3}" y="${(Y(0) - 3).toFixed(1)}">0</text>`;
  if (refVec) DELTA_DEF.forEach(([k, col], ci) => {   // 정답선 — 0 성분은 0선이 대신
    const rv = refVec[ci];
    if (!Number.isFinite(rv) || Math.abs(rv) < 1e-9) return;
    h += `<line x1="${L}" y1="${Y(rv).toFixed(1)}" x2="${W - R}" y2="${Y(rv).toFixed(1)}"
        stroke="${col}" stroke-dasharray="6,4" stroke-width="1.3" opacity="0.8"/>
      <text x="${L + 3}" y="${(Y(rv) - 3).toFixed(1)}" style="fill:${col}">정답 ${k} ${fmtNum(rv, 3)}</text>`;
  });
  const labels = [];
  series.forEach(sr => {
    const pts = sr.pts;
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
  labels.sort((a, b) => a.y - b.y);   // 끝점 직접 라벨 — 겹침 해소 (multiCurveSvg 관행)
  for (let i = 1; i < labels.length; i++)
    if (labels[i].y - labels[i - 1].y < 10) labels[i].y = labels[i - 1].y + 10;
  const overshoot = labels.length ? labels[labels.length - 1].y - (H - 4) : 0;
  if (overshoot > 0) {
    for (const lb of labels) lb.y -= overshoot;
    for (let i = labels.length - 2; i >= 0; i--)
      if (labels[i + 1].y - labels[i].y < 10) labels[i].y = labels[i + 1].y - 10;
  }
  for (const lb of labels)
    h += `<text x="${lb.x.toFixed(1)}" y="${lb.y.toFixed(1)}" style="fill:${lb.col}">${esc(lb.key)}</text>`;
  return h + '</svg>';
}
// δ̂ 궤적 카드 — 3c 행이 있으면 선택 스텝과 무관하게 표시(주입 복원 검정의 판독 축)
function deltaHatCard(d) {
  const idxs = ((d.s3 && d.s3.byStage) || {})['3c'] || [];
  if (!idxs.length) return '';   // 3c 부재 — 섹션 생략(타임라인은 '예정')
  const sc3 = (autoChecks(d) || {}).s3c;
  if (!sc3) return '';
  const inj = (d.manifest || {}).injection || null;
  const refVec = sc3.expected;
  const swatch = (col) => `<span style="display:inline-block;width:9px;height:9px;background:${col};border-radius:2px;margin-right:4px;vertical-align:middle"></span>`;
  const rows = DELTA_DEF.map(([k, col], ci) => {
    const fin = (sc3.delta_hat_final || [])[ci];
    const ref = refVec ? refVec[ci] : undefined;
    return `<tr><td class="l">${swatch(col)}δ̂${k}</td><td>${fmtNum(fin)}</td>
      <td>${Number.isFinite(ref) ? fmtNum(ref) : '—'}</td>
      <td>${(Number.isFinite(fin) && Number.isFinite(ref)) ? fmtNum(fin - ref) : '—'}</td></tr>`;
  }).join('');
  let caption, badge;
  if (sc3.kind === 'injected') {
    const expTxt = inj && typeof inj.expected_delta_hat === 'string'
      ? esc(inj.expected_delta_hat) : esc(JSON.stringify((inj || {}).expected_delta_hat ?? '—'));
    caption = `<div class="note caption">주입 런 — delta_applied=${esc(JSON.stringify((inj || {}).delta_applied ?? '—'))} ·
        route=${esc((inj || {}).route ?? '—')}<br>기대 δ̂(부호 규약, manifest.injection): ${expTxt}<br>
        정답선(점선, 성분 색) 수치 출처: ${esc(sc3.expected_src ?? '없음 — 정답선 미표시')}</div>`;
    badge = sc3.expected === null
      ? '<span class="badge bad">정답 벡터 불명 — expected_delta_hat/delta_applied 수치 없음</span>'
      : `<span class="badge prop">최종 잔류 |δ̂−정답| = ${fmtNum(sc3.residual_vs_expected, 4)} m</span>`;
  } else if (sc3.kind === 'scope0') {
    caption = `<div class="note caption">δ scope 0 런(δ가 걸리는 prior 평면 0) — δ̂ 부동이 기대되는
        음성 기록. 0선(점선)만 표시.</div>`;
    badge = sc3.immobile ? '<span class="badge good">δ̂ 부동 — 전 스텝 0</span>'
      : `<span class="badge bad">δ̂ 이동 감지 max|δ̂| ${fmtNum(sc3.max_abs_delta_hat, 4)}</span>`;
  } else {
    caption = `<div class="note caption">비변화 통제 런 — δ̂≈0 기대(0선), 잔류 오차가 판독 대상
        (오이동 = 위험 신호).</div>`;
    badge = `<span class="badge prop">최종 잔류 |δ̂| = ${fmtNum(sc3.residual_norm, 4)} m</span>`;
  }
  return `<div class="card">${caption}
    ${deltaHatSvg(d, refVec)}
    <table style="margin-top:4px"><tr><th class="l">성분</th><th>최종 δ̂ (m)</th><th>정답</th><th>잔차</th></tr>${rows}</table>
    <div style="margin-top:5px">${badge}
      <span class="badge na">진단 anchor_plane ${fmtNum(sc3.anchor_plane_first, 3)}→${fmtNum(sc3.anchor_plane_last, 3)} (|δ̂| 비례 기대 — 3d 예고)</span></div>
    <div class="note" style="margin-top:4px">축: X=3c 스텝, Y=δ̂ 성분(m — 음수 허용, 0선 점선).
      anchor·area는 3c 목적이 아니라 진단 기록(평면 앵커 목표가 P⁰⊕δ라 평면 동결 중엔 |δ̂| 비례
      벌점이 되기 때문 — manifest.s3c_def.objective_note). 점 클릭=스텝 전환 · 강조 점=체크포인트.</div></div>`;
}
function gradBarsHtml(d, step) {
  const g = (step || {}).grad_norms || {};
  const scope0 = deltaScopeOf(d) === 0;
  const vals = GRAD_DEF.map(([k]) => Number.isFinite(g[k]) ? g[k] : null);
  const vmax = Math.max(...vals.map(v => v ?? 0), 1e-30);
  let h = '<table>';
  GRAD_DEF.forEach(([key, label, col], i) => {
    const v = vals[i];
    const w = v === null ? 0 : Math.max(v / vmax * 100, v > 0 ? 2 : 0);
    const flag = (v !== null && v > 0) ? ''
      : (key === 'delta' && scope0)
      ? '<span class="badge na">0 — 구조적(δ scope 0 · 음성 기록)</span>'
      : '<span class="badge bad">0/결측 — 배선 끊김 의심</span>';
    h += `<tr><td class="l" style="width:44%">${esc(label)}</td>
      <td class="l" style="width:34%"><span title="grad_norms.${esc(key)} = ${fmtNum(v)}"
        style="display:inline-block;height:10px;width:${w.toFixed(1)}%;background:${col};
        border-radius:2px;vertical-align:middle"></span></td>
      <td>${fmtNum(v)} ${flag}</td></tr>`;
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
// ---------- 3b·3c 체크포인트 도우미 ----------
// 타일 디렉터리 — 3a: s3_tiles/<view>/ · 3b 체크포인트: s3_tiles/s<step>/<view>/ ·
// 3c 체크포인트: s3_tiles/s3c_s<step>/<view>/ (3b와 충돌 금지). photo는 전 구간 3a 재사용.
function tileDir(stageId, stepNum, viewId) {
  const root = `../runs/${encodeURIComponent(state.runName)}/s3_tiles/`;
  const st = String(stageId);
  if (st === '3a') return `${root}${encodeURIComponent(viewId)}/`;
  if (st === '3c') return `${root}s3c_s${stepNum}/${encodeURIComponent(viewId)}/`;
  return `${root}s${stepNum}/${encodeURIComponent(viewId)}/`;   // 3b
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
// 이전 체크포인트 — 같은 구간의 직전, 없으면 이전 구간의 최종(3b→3a, 3c→3b final→3a):
// 렌더 비교 기준선.
function prevCkpt(d, step) {
  const st = String(step.stage);
  if (!d.s3 || (st !== '3b' && st !== '3c')) return null;
  const rows = ckptRows(d, st).filter(r => (r.row.step ?? 0) < (step.step ?? 0));
  if (rows.length) {
    const r = rows[rows.length - 1];
    return { row: r.row, idx: r.idx, stage: st, step: r.row.step,
             label: `${st === '3c' ? '3c ' : ''}s${r.row.step}`,
             dir: (vid) => tileDir(st, r.row.step, vid) };
  }
  for (const ps of (st === '3c' ? ['3b', '3a'] : ['3a'])) {
    const a = ckptRows(d, ps);
    if (!a.length) continue;
    const r = a[a.length - 1];
    return { row: r.row, idx: r.idx, stage: ps, step: r.row.step,
             label: ps === '3a' ? '3a' : `3b s${r.row.step}`,
             dir: (vid) => tileDir(ps, r.row.step, vid) };
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
  } else if (String((step || {}).stage) === '3c') {
    // 3c: δ 해동 + 색 — 평면·o 동결이 계약(param_step_norms.planes=0). δ̂는 학습 변수라
    // delta_frozen을 요구하지 않는다. scope 0 런은 δ 이동량 0이 기대(부동 = 음성 기록).
    const p = step.param_step_norms || {};
    const c3 = ((d.s3 || {}).byStage || {})['3c'] || [];
    const lastStep3c = c3.length ? (d.s3.steps[c3[c3.length - 1]].step ?? null) : null;
    const scdSteps = ((d.manifest || {}).s3c_def || {}).steps;
    const isEvalRow = (scdSteps !== undefined && step.step === scdSteps) || step.step === lastStep3c;
    const scope0 = deltaScopeOf(d) === 0;
    items.push(B(inv.planes_frozen === true, `평면 동결 ${inv.planes_frozen === true ? '유지' : '위반'}`));
    items.push(B((p.planes ?? null) === 0, `평면 이동량 ${fmtNum(p.planes, 1)} ${(p.planes ?? null) === 0 ? '(동결군 0)' : '(0 아님!)'}`));
    items.push(`<span class="badge na">δ̂ [${(step.delta_hat || []).map(v => fmtNum(v, 3)).join(', ')}] (학습 변수 — 해동)</span>`);
    if (scope0)
      items.push(B((p.delta ?? 0) === 0, `δ 이동량 ${fmtNum(p.delta, 1)} (scope 0 — 부동 기대)`));
    else if (isEvalRow && (p.delta ?? 0) === 0 && (p.colors ?? 0) === 0)
      items.push(`<span class="badge na">δ·색 이동량 0.0 (최종 행 = 평가 전용 — 갱신 없음)</span>`);
    else {
      items.push(B(Number.isFinite(p.delta), `δ 이동량 ${fmtNum(p.delta)}`));
      items.push(B(Number.isFinite(p.colors) && p.colors > 0, `색 이동량 ${fmtNum(p.colors)} ${Number.isFinite(p.colors) && p.colors > 0 ? '(학습 중)' : '(0/결측 — 학습 정지?)'}`));
    }
  } else {
    items.push(`<span class="badge na">δ 동결 ${inv.delta_frozen === undefined ? '—' : inv.delta_frozen} · 이동량 ${fmtNum(step.param_step_norm, 3)} (구간 ${esc(step.stage)} 계약은 추후)</span>`);
  }
  return items.join(' ');
}
function s3DefCard(d) {
  const sd = (d.manifest || {}).s3_def || {};
  const sbd = (d.manifest || {}).s3b_def || null;
  const scd = (d.manifest || {}).s3c_def || null;
  const inj = (d.manifest || {}).injection || null;
  const s3 = d.s3;
  const s3bRows = sbd ? `
      <tr><td class="k">구간 3b</td><td class="l">색만 학습(기하 동결·웜업) — trained=${esc(JSON.stringify(sbd.trained ?? ['colors']))} ·
        steps ${sbd.steps ?? '—'} · lr ${sbd.lr ?? '—'} · optimizer=${esc(sbd.optimizer ?? '—')}</td></tr>
      <tr><td class="k">3b 체크포인트</td><td class="l">[${(sbd.checkpoints || []).join(', ')}] ·
        기하 바이트 불변 ${sbd.frozen_checksum_ok === true
          ? '<span class="badge good">frozen_checksum_ok</span>'
          : '<span class="badge bad">미확인/실패</span>'}</td></tr>` : '';
  const s3cRows = scd ? `
      <tr><td class="k">구간 3c</td><td class="l">δ 해동(전역 평행이동 1벡터 — 회전 없음) + 색(3b 웜스타트) —
        trained=${esc(JSON.stringify(scd.trained ?? ['delta', 'colors']))} · steps ${scd.steps ?? '—'} ·
        lr_delta ${scd.lr_delta ?? '—'} · lr_rgb ${scd.lr_rgb ?? '—'} · δ scope 평면 ${scd.delta_scope_planes ?? '—'}</td></tr>
      <tr><td class="k">3c 목적</td><td class="l">${esc(scd.objective ?? 'photo')}만 역전파 — ${esc(scd.objective_note ?? 'anchor·area는 진단 기록(objective_note 미명기)')}</td></tr>
      <tr><td class="k">3c 체크포인트</td><td class="l">[${(scd.checkpoints || []).join(', ')}] ·
        평면·o 동결 바이트 ${scd.frozen_checksum_ok === true
          ? '<span class="badge good">frozen_checksum_ok</span>'
          : '<span class="badge bad">미확인/실패</span>'}</td></tr>` : '';
  const injRows = inj ? `
      <tr><td class="k">주입</td><td class="l"><span class="badge prop">주입 dz=${Array.isArray(inj.delta_applied) ? +inj.delta_applied[2] : '?'}</span>
        delta_applied=${esc(JSON.stringify(inj.delta_applied ?? '—'))} · route=${esc(inj.route ?? '—')}</td></tr>
      <tr><td class="k">기대 δ̂</td><td class="l">${esc(typeof inj.expected_delta_hat === 'string'
          ? inj.expected_delta_hat : JSON.stringify(inj.expected_delta_hat ?? '—'))}</td></tr>` : '';
  return `<div class="card">
    <table>
      <tr><td class="k">구간 3a</td><td class="l">${esc(sd.stage ?? '—')} (렌더-온리 — 최적화 0스텝 + backward 1회)</td></tr>
      <tr><td class="k">δ 배선</td><td class="l">${sd.delta_wired === true ? '렌더 인자로 배선됨' : (sd.delta_wired === undefined ? '—' : '<span class="bad">배선 안 됨!</span>')} · 값 ${JSON.stringify(sd.delta_value ?? '—')} 고정</td></tr>
      <tr><td class="k">색 / 렌더러</td><td class="l">${esc(sd.color ?? '—')} / ${esc(sd.renderer ?? '—')} · optimizer=${esc(sd.optimizer ?? '—')}</td></tr>${s3bRows}${s3cRows}${injRows}
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
// 체크포인트 필름스트립 (⑥) — 선택 뷰의 렌더/잔차를 구간 전 체크포인트에 한 줄로.
// 기존 타일 파일 재사용(체크포인트 계약), 사진은 맨 앞 1장(3a 타일). 클릭 = 스텝 선택.
function filmstripHtml(d, stageId, v, step) {
  if (stageId !== '3b' && stageId !== '3c') return '';   // 3a = 단일 s0(스트립 무의미)
  const cks = ckptRows(d, stageId);
  if (cks.length < 2) return '';
  const kind = state.filmKind === 'residual' ? 'residual' : 'render';
  const cells = cks.map(r => {
    const s = r.row.step ?? 0;
    const psnr = (r.row.views_psnr || {})[v.view_id];
    const src = tileDir(stageId, s, v.view_id) + `${kind}.png`;
    const sel = r.idx === state.selStep;
    return `<figure class="filmcell ${sel ? 'sel' : ''}" data-step="${r.idx}"
        title="s${s} 선택${Number.isFinite(psnr) ? ` · PSNR ${fmtNum(psnr, 2)} dB` : ''}">
      <img src="${src}" alt="${escAttr(`${kind} s${s}`)}" loading="lazy"
        onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'err',textContent:'s${s} 타일 없음'}))">
      <figcaption>s${s}${Number.isFinite(psnr) ? ` · ${fmtNum(psnr, 1)}dB` : ''}</figcaption></figure>`;
  }).join('');
  const photoSrc = tileDir('3a', 0, v.view_id) + 'photo.png';
  return `<div style="margin-top:6px"><div class="legend">체크포인트 필름스트립 — ${esc(v.view_id)}
      <label><input type="radio" name="filmkind" value="render" ${kind === 'render' ? 'checked' : ''}> 렌더</label>
      <label><input type="radio" name="filmkind" value="residual" ${kind === 'residual' ? 'checked' : ''}> 잔차</label>
      <span class="note">사진 1장 + 구간 ${esc(stageId)} 체크포인트 ${cks.length}개 · 썸네일 클릭=스텝 선택</span></div>
    <div class="filmrow">
      <figure class="filmcell photo"><img src="${photoSrc}" alt="photo" loading="lazy"
        onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'err',textContent:'photo 없음'}))">
        <figcaption>사진</figcaption></figure>
      ${cells}</div></div>`;
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
  // 체크포인트 스텝 전환 내비 (3b·3c — PSNR 막대·타일이 함께 전환)
  const is3bc = stageId === '3b' || stageId === '3c';
  let prev = null;
  if (is3bc) {
    const cks = ckptRows(d, stageId);
    const pos = cks.findIndex(r => r.idx === state.selStep);
    const btn = (idx, txt) => idx !== null
      ? `<button class="small ckjump" data-step="${idx}">${txt}</button>`
      : `<button class="small" disabled>${txt}</button>`;
    prev = prevCkpt(d, step);   // 같은 구간 직전, 없으면 이전 구간 최종(3c→3b final→3a)
    const prevIdx = pos >= 0 && prev ? prev.idx : null;
    const nextIdx = pos >= 0 && pos < cks.length - 1 ? cks[pos + 1].idx : null;
    head += `<div class="legend">체크포인트 전환 ${btn(prevIdx, '◀ 이전 CP')} ${btn(nextIdx, '다음 CP ▶')}
      <label style="margin-left:8px"><input type="checkbox" id="cmpPrevTgl" ${state.cmpPrev ? 'checked' : ''}>
        이전/현재 렌더 나란히</label></div>`;
  }
  if (!isCkptStep(d, step)) {   // 3b·3c 비체크포인트 행 — 타일 없음(계약: 체크포인트만 저장)
    const cks = ckptRows(d, stageId);
    let nearest = null, best = Infinity;
    for (const r of cks) {
      const dd = Math.abs((r.row.step ?? 0) - (step.step ?? 0));
      if (dd < best) { best = dd; nearest = r; }
    }
    return `${head}<div class="note">스텝 ${step.step}은 체크포인트가 아니라 타일이 없다
      (계약: s3_tiles/${stageId === '3c' ? 's3c_s' : 's'}&lt;step&gt;/는 체크포인트만). ${nearest
        ? `가장 가까운 체크포인트: <button class="small ckjump" data-step="${nearest.idx}">s${nearest.row.step}로 이동</button>` : ''}</div>
      ${filmstripHtml(d, stageId, v, step)}
      <div style="margin-top:5px">${psnrBarsSvg(step, prev)}</div>`;
  }
  const base = tileDir(stageId, step.step ?? 0, v.view_id);
  let tiles = fig(photoSrc, 'photo', `사진 (다운스케일 ≤640${stageId !== '3a' ? ' · 3a 타일 재사용' : ''})`);
  if (is3bc && state.cmpPrev && prev)
    tiles += fig(prev.dir(v.view_id) + 'render.png', `이전 렌더`,
                 `렌더 — 이전 CP ${esc(prev.label)}`);
  tiles += fig(base + 'render.png', 'render',
               stageId === '3c' ? `렌더 3c s${step.step} (δ+색 학습 중)`
               : stageId === '3b' ? `렌더 s${step.step} (색 학습 중)` : '렌더 (gsplat · S2 상태)');
  tiles += fig(base + 'residual.png', 'residual', '|사진−렌더| 그레이 히트');
  return `${head}<div class="tiles">${tiles}</div>
    ${filmstripHtml(d, stageId, v, step)}
    <div style="margin-top:5px">${psnrBarsSvg(step, prev)}</div>`;
}
function faceResidualCard(d) {
  const s3 = d.s3;
  const hasFinal = !!s3.perFaceFinal;
  const has3c = !!s3.perFaceFinal3c;
  const states = heatStatesOf(d);
  const nCkpt = states.filter(x => x.ckpt).length;
  const hd = heatData(d);
  const st = hd && hd.stats;
  const isAnchor = state.heatMode === 'anchor_cost' || state.heatMode === 'anchor_flip';
  const modeRadio = (val, label, dis) => `<label ${dis ? 'style="opacity:.5"' : ''}>
      <input type="radio" name="heatmode" value="${val}" ${state.heatMode === val ? 'checked' : ''}
        ${dis ? 'disabled' : ''}> ${label}</label>`;
  const methodTxt = (state.heatMode === 'final3c' && has3c) ? s3.finalMethod3c
    : (state.heatMode === 'final' && hasFinal) ? s3.finalMethod : s3.method;
  let h = `<div class="card">
    <div class="legend"><span class="badge eval">3D 표시 중: ${esc(heatStateLabel(d, hd ? hd.mode : state.heatMode))} 히트맵</span>
      <label><input type="checkbox" id="heatAutoTgl" ${state.autoHeat ? 'checked' : ''}>
        스텝 추적(자동)</label>
      <span class="note">스텝 클릭 = 이하 최대 체크포인트 히트맵 자동 전환${nCkpt
        ? ` (중간 s5/s15/s45/s130… ${nCkpt}개 포함 — s3_face_residual_ckpt.json)` : ''} ·
        수동 라디오 선택 시 추적 해제</span></div>
    <div class="legend">표시 범위
      <label><input type="checkbox" id="heatScopeTgl" ${state.heatScope === 'all' ? 'checked' : ''}>
        전체 후보 면(귀속용 — 잠든 gate-0 면은 반투명·점선)</label>
      <span class="note">기본 = <b style="color:#c8ccd4">F*(initial_real) 면만</b> — 렌더에
        실재하는 면은 F*뿐, 잠든 prior 단면을 전부 칠하면 모델 기하로 오독됨${
        d.realFaceSet ? ` (F* ${d.nRealTotal}면 — 외피 절단면 ${d.nRealTotal - d.realFaceSet.size}
        제외 → 히트맵 대상 ${d.realFaceSet.size} / 전체 ${d.faces.length}면)` : ''}</span></div>
    <div class="legend">주요 상태
      ${modeRadio('init', 'step0 (3a)', false)}
      ${modeRadio('final', `3b final${hasFinal ? ` (s${s3.finalStep ?? '?'})` : ''}`, !hasFinal)}
      ${modeRadio('final3c', `3c final${has3c ? ` (s${s3.finalStep3c ?? '?'})` : ''}`, !has3c)}
      ${modeRadio('diff', '차이 (대상−기준)', states.length < 2)}
      ${hasFinal ? '' : '<span class="note">3b final은 s3_face_residual_final.json 생성 후</span>'}
      ${has3c || !hasFinal ? '' : '<span class="note">· 3c final은 s3_face_residual_s3c_final.json 생성 후</span>'}
      ${nCkpt ? '' : '<span class="note">· 중간 체크포인트는 s3_face_residual_ckpt.json 생성 후(스텝 추적)</span>'}</div>
    <div class="legend">앵커 가시화 <span class="note">(상수 — 스텝 무관 · s2_cells 지연 로드)</span>
      ${modeRadio('anchor_cost', '셀 앵커 비용 C_k', false)}
      ${modeRadio('anchor_flip', '뒤집기 값 ΔW', false)}</div>`;
  if (state.heatMode === 'diff' && states.length >= 2) {
    const opt = (sel) => states.map(x =>
      `<option value="${escAttr(x.key)}" ${x.key === sel ? 'selected' : ''}>${esc(x.label)}</option>`).join('');
    h += `<div class="legend">차이 비교: 대상 <select id="diffTargetSel">${opt((hd && hd.pair) ? hd.pair.target : state.diffTarget)}</select>
      − 기준 <select id="diffBaseSel">${opt((hd && hd.pair) ? hd.pair.base : state.diffBase)}</select>
      <span class="note">임의 두 체크포인트 상태 비교 (기본 = 3b final − step0)</span></div>`;
  }
  if (isAnchor) {
    h += `<div class="note caption" style="border-left-color:#ff9a3c;margin-bottom:4px">${
      state.heatMode === 'anchor_cost'
        ? `셀 앵커 비용 맵 — <b>prior 증언이 현재 상태를 붙잡는 비용(§2.2)</b>:
           C_k(o_state; t) = −[o·log t + (1−o)·log(1−t)], w=1. 스텝과 무관한 상수(o·t는 S2 동결).`
        : `뒤집기 값 맵 — <b>이 셀을 뒤집는 데 필요한 증거량</b>: ΔW = |log(t/(1−t))|, w=1 초기.
           t=0.5 근방 싸고 극단 비쌈; t∈{0,1} = ∞ → 별색(블루). 스텝과 무관한 상수.`}
      ${hd && hd.aggNote ? ` ${esc(hd.aggNote)}.` : ''}
      ${d.cellsInfo === null ? ' <span class="bad">s2_cells.json 로드 실패 — 값 없음.</span>'
        : d.cellsInfo === undefined ? ' <span class="note">s2_cells.json 로딩 중…</span>' : ''}</div>`;
  } else {
    h += `<div class="note caption" style="margin-bottom:4px">근사 방식(숨기지 않음): ${esc(
      methodTxt || '— method 명기 없음')}</div>`;
  }
  if (state.heatMode === 'diff' && states.length >= 2)
    h += `<div class="note caption" style="border-left-color:#2ee6c8;margin-bottom:4px">
      차이 판독: 잔차 <b style="color:#2ee6c8">감소(청록)</b> = 색으로 설명된 잔차 ·
      <b style="color:#ffcf70">잔존/증가(앰버)</b> = 기하 신호 후보(3c/3d·이산 라운드의 표적).
      판독 힌트: B173 저층 지붕동 잔존 확인 — 해당 면(f00879 등)은 gate-0이라
      <b>'전체 후보 면' 토글</b>을 켜고 조기 체크포인트 기준으로(r17 — 누락 검출은 조기
      체크포인트·gate-0 귀속).</div>`;
  const scopeTxt = state.heatScope === 'all'
    ? `전체 후보 면 (실재 ${d.paintCounts ? d.paintCounts.real : '?'} + 잠든 ${
        d.paintCounts ? d.paintCounts.sleeping : '?'})`
    : `F* 면만 (칠해진 면 ${d.paintCounts ? d.paintCounts.real : '?'})`;
  if (!st) h += '<p class="note">per_face 값 없음</p>';
  else h += `<table>
      <tr><td class="k">표시 범위</td><td class="l">${scopeTxt}</td></tr>
      <tr><td class="k">${isAnchor ? '값 보유 면(∞ 포함)' : '잔차 보유 면(범위 내)'}</td><td>${st.n ?? '—'} / ${d.faces.length}${
        isAnchor && st.inf ? ` (∞ ${st.inf})` : ''}</td></tr>
      <tr><td class="k">min · mean · max${isAnchor ? ' (유한값)' : ''}</td><td>${fmtNum(st.min)} · ${fmtNum(st.mean)} · ${fmtNum(st.max)}</td></tr>
    </table>
    <div class="note" style="margin-top:3px">${hd.diverging
      ? '3D 면 색 = 발산 램프(청록=감소·앰버=잔존/증가, 양쪽 값 있는 면만)'
      : isAnchor
      ? '3D 면 색 = 5단 앰버 램프(저→고) · ∞=블루 — 셀 상수(스텝 무관)'
      : '3D 면 색 = 5단 앰버 램프(저→고, dataviz 검증) — 전 체크포인트 상태 공유 스케일(전환 비교 가능)'} —
      범위 스케일 ${state.heatScope === 'all' ? '전체' : 'F*'} 기준 · s2_faces 지오메트리 재사용.
      면 클릭 = 카드 + 페이지 2·1 점프.</div>`;
  h += '</div>';
  if (state.selFace !== null) {
    const f = d.faces[state.selFace];
    const v = s3.perFace[f.face_id];
    const vFin = hasFinal ? s3.perFaceFinal[f.face_id] : undefined;
    const vFin3c = has3c ? s3.perFaceFinal3c[f.face_id] : undefined;
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
        ${hasFinal ? `<tr><td class="k">|잔차| 평균 3b final (s${s3.finalStep ?? '?'})</td><td>${fmtNum(vFin)}</td></tr>` : ''}
        ${has3c ? `<tr><td class="k">|잔차| 평균 3c final (s${s3.finalStep3c ?? '?'})</td><td>${fmtNum(vFin3c)}</td></tr>` : ''}
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
// ---------- 검증 오버레이 3종 카드 (⑨~⑪ — 2026-08-27) ----------
function verifyOverlaysCard(d) {
  // ⑨ LoD2 — s1_planes 없음/링 0이면 비활성 + 사유
  const gtDis = d.s1PlanesMissing ? 's1_planes.json 없음' :
    (!d.gtPlanes.length ? 'gt_planes 0 (LoD2 링 없음)' : null);
  let h = `<div class="card">
    <div class="legend">
      <label ${gtDis ? 'style="opacity:.5"' : ''}><input type="checkbox" id="gtOvTgl"
        ${state.overlayGt ? 'checked' : ''} ${gtDis ? 'disabled' : ''}>
        <span style="color:#5fe08a">LoD2 지붕면</span></label>
      <span class="badge gt">LoD2 지붕면 (평가 전용 — 방법 입력 아님)</span>
      ${gtDis ? `<span class="badge na">비활성 — ${esc(gtDis)}</span>`
        : `<span class="note">gt_planes ${d.gtPlanes.length}면 · 청록/초록 와이어+반투명 채움 ·
           δ̂ 이동(shiftGroup)의 영향을 받지 않는 <b>고정 기준면</b>(비교 잣대)${
           d.gtNote ? ` · ${esc(String(d.gtNote)).slice(0, 60)}` : ''}</span>`}
    </div>`;
  // ⑩ 초기 점유 vs LoD2 — 구멍/과잉 셀
  const cgDis = gtDis || (d.s2Missing ? 's2_faces.json 없음' : null)
    || (d.cellsInfo === null ? 's2_cells.json 로드 실패' : null)
    || (d.cellOv === null && d.cellOvNote ? d.cellOvNote : null);
  const cgSt = d.cellOv && d.cellOv.stats;
  h += `<div class="legend" style="margin-top:5px">
      <label ${cgDis ? 'style="opacity:.5"' : ''}><input type="checkbox" id="cellGtTgl"
        ${state.overlayCellsGt ? 'checked' : ''} ${cgDis ? 'disabled' : ''}>
        초기 점유 vs LoD2</label>
      ${cgDis ? `<span class="badge na">비활성 — ${esc(cgDis)}</span>`
        : cgSt ? `<span class="badge hole">구멍 ${cgSt.holes}</span>
                  <span class="badge exc">과잉 ${cgSt.excess}</span>`
        : state.overlayCellsGt || d.cellOvLoading
        ? '<span class="note">s2_cells 로드·대조 계산 중…</span>'
        : '<span class="note">첫 켬 때 1회 계산 (s2_cells 공유 로드)</span>'}
    </div>`;
  if (cgSt)
    h += `<div class="note caption" style="border-left-color:#e25563">
      구멍 ${cgSt.holes} · 과잉 ${cgSt.excess} — <b>3e 이산 판정의 시험대</b>.
      로직(이전 분석과 동일): 셀 중심을 gt_planes 수평·경사면(|n_z|&gt;${CELLGT.nzMin})의
      XY 포함 검사로 대조, 포함 면들의 평면 z 최댓값 = gt 지붕고, ±${CELLGT.marginM} m 여유.
      <span style="color:#ff9b93">구멍 = 끔인데 중심이 gt 지붕 아래(적색)</span> ·
      <span style="color:#d9a0ff">과잉 = 켬인데 gt 지붕 위(자주/보라)</span> ·
      x-ray 표시(내부 셀이 가려지지 않게) · 대상 셀 ${cgSt.covered}/${cgSt.cells}
      (gt 지붕 XY 안) · 지붕면 ${cgSt.roof_planes} · 초기 상태 고정(δ̂ 무관).</div>`;
  // ⑪ 학습 색(텍스처) 미리보기
  const ca = ((d.manifest || {}).s3b_def || {}).colors_artifact || null;
  const cpDis = (!ca ? 'manifest.s3b_def.colors_artifact 없음 (3b 미완주 런)' : null)
    || (d.s2Missing ? 's2_faces.json 없음' : null)
    || (d.colorPrev === null && d.colorPrevNote ? d.colorPrevNote : null);
  const cpSt = d.colorPrev && d.colorPrev.stats;
  h += `<div class="legend" style="margin-top:5px">
      <label ${cpDis ? 'style="opacity:.5"' : ''}><input type="checkbox" id="colorPrevTgl"
        ${state.colorPreview ? 'checked' : ''} ${cpDis ? 'disabled' : ''}>
        학습 색(텍스처) 미리보기</label>
      ${cpDis ? `<span class="badge na">비활성 — ${esc(cpDis)}</span>`
        : cpSt ? `<span class="badge eval">점 ${cpSt.shown.toLocaleString()}</span>`
        : state.colorPreview || d.colorPrevLoading
        ? '<span class="note">s3b_colors + s2_seeds 로딩 중… (수십 MB — 첫 켬 때만)</span>'
        : `<span class="note">첫 켬 때 s2_seeds.json 지연 로드 — 큰 런은 무거움(B022 120 MB) ·
           켜면 진단 칠(히트맵) 자동 숨김(배타)</span>`}
    </div>`;
  if (cpSt)
    h += `<div class="note caption" style="border-left-color:#b05ce0">
      <b>3b가 학습한 모델 색(텍스처) — 타일 렌더와 동일물의 3D 표시</b>
      (s3b_colors.f16.bin, DataView fp16→fp32).
      시드 ${cpSt.seeds.toLocaleString()} → F* 면 시드 ${cpSt.kept_fstar.toLocaleString()}
      (잠든 면 제외) → 표시 ${cpSt.shown.toLocaleString()}
      (스트라이드 ${cpSt.stride} 결정론 씨닝, 상한 ${COLOR_PREV_MAX.toLocaleString()}) ·
      점 크기 ${cpSt.point_size_m} m(간격 ${cpSt.spacing_m} m×√스트라이드) ·
      sha256 ${cpSt.sha_ok === true ? '<span class="good">일치</span>'
        : cpSt.sha_ok === false ? '<span class="bad">불일치!</span>'
        : '미대조(crypto.subtle 불가)'} ·
      prior 계열 시드는 δ̂ 이동 추종 · 진단 칠(히트맵)은 자동 숨김 — 라디오식 배타.</div>`;
  return h + `<div class="note" style="margin-top:4px">3종 전부 평가 전용 오버레이 —
    방법 입력이 아니며 판정·파라미터 선택에 불참(GT 분리 원칙). 켬/카운트는 판독 JSON
    auto에 기록.</div></div>`;
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

// ---------- 구간 산출물 요약 카드 (④ — 구간 배지 클릭, 스텝 선택과 독립) ----------
// 공통 틀 3줄 — 해동 변수 / 고유 산출물 / 이 단계가 답한 질문. 값은 HTML-안전 상수 문구.
const SEG_FRAME = {
  '3a': { unfrozen: '없음 (0 최적화 스텝 — backward 1회만)',
          outputs: 'grad_norms 3군(배선 증거) · step0 렌더/잔차 타일 · 면별 잔차 히트맵(step0)',
          question: '광도 잔차가 δ·평면·색 변수군까지 실제로 흘러오는가 (배선 자체 검증)' },
  '3b': { unfrozen: '색 A_g (시드당 RGB — δ·평면·o 동결)',
          outputs: '학습 색 저장물(colors_artifact) · 3b final 면 잔차 · PSNR 개선 · 색 분화 통계',
          question: '색이 수렴하는 동안 기하 압력이 어떻게 변하는가 (색으로 설명되는 잔차의 분리)' },
  '3c': { unfrozen: 'δ (전역 평행이동 1벡터) + 색 (3b 웜스타트 — 평면·o 동결)',
          outputs: 'δ̂ 궤적(스텝별 delta_hat) · 3c final 면 잔차 · 주입 복원 잔류 오차',
          question: '주입된 이동을 δ̂가 복원하는가 (광도 단독 식별성 검정)' },
  '3d': { unfrozen: '평면 P (예정)',
          outputs: '미세조정 평면 + 앵커 장력 (예정)',
          question: '(예정 — 3d 구현과 함께 등록)' },
};
function medianOf(vals) {
  const v = (vals || []).filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = v.length >> 1;
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}
function segmentSummaryCard(d, sg) {
  const idxs = ((d.s3 && d.s3.byStage) || {})[sg] || [];
  const fr = SEG_FRAME[sg];
  if (!fr)   // 등록부 밖 구간 — 요약 계약 없음(타임라인 자동 등재 구간)
    return `<div class="card"><div class="note">등록부 밖 구간 ${esc(sg)} —
      요약 카드 계약 없음 (행 ${idxs.length}개)</div></div>`;
  let h = `<div class="card"><table>
      <tr><td class="k">해동 변수</td><td class="l">${fr.unfrozen}</td></tr>
      <tr><td class="k">고유 산출물</td><td class="l">${fr.outputs}</td></tr>
      <tr><td class="k">이 단계가 답한 질문</td><td class="l">${fr.question}</td></tr></table>`;
  const planned = `<div class="note" style="margin-top:5px"><span class="badge na">예정</span>
      이 구간 행 없음 — 페이지가 구현과 함께 자란다.</div>`;
  if (sg === '3a') {
    if (!idxs.length) h += planned;
    else {
      const row = d.s3.steps[idxs[0]];   // 3a = step0 단일 행 계약
      const med = medianOf(Object.values(row.views_psnr || {}));
      const scope0 = deltaScopeOf(d) === 0;
      h += `<div style="margin-top:6px"><b>grad_norms 3군 — 배선 증거${
          scope0 ? ' <span class="badge na">δ 구조적 0 (scope 0)</span>' : ''}</b></div>
        ${gradBarsHtml(d, row)}
        <table style="margin-top:4px">
          <tr><td class="k">step0 photo 손실</td><td class="l">${fmtNum((row.losses || {}).photo)}</td></tr>
          <tr><td class="k">step0 PSNR 중앙값</td><td class="l">${fmtNum(med, 3)} dB
            <span class="note">(뷰 ${Object.keys(row.views_psnr || {}).length}개 중앙값)</span></td></tr>
        </table>
        <div style="margin-top:5px">
          <button class="small" id="segS0Tiles">s0 타일 보기</button>
          <button class="small" id="segS0Heat">s0 히트맵</button>
          <span class="note">기존 스텝 선택·히트맵 상태 세팅 재사용</span></div>`;
    }
  } else if (sg === '3b') {
    if (!idxs.length) h += planned;
    else {
      const sbd = (d.manifest || {}).s3b_def || {};
      const pm = sbd.psnr_median || null;
      let psnrHtml, psnrSrc;
      if (pm && Number.isFinite(pm.step0) && Number.isFinite(pm.final)) {
        const dd = pm.final - pm.step0;
        psnrHtml = `${fmtNum(pm.step0, 3)} → ${fmtNum(pm.final, 3)} dB
          (<b class="${dd > 0 ? 'good' : 'warn'}">${dd >= 0 ? '+' : ''}${fmtNum(dd, 3)}</b>)`;
        psnrSrc = 'manifest.s3b_def.psnr_median';
      } else {
        const cks = idxs.filter(i => d.s3.steps[i].views_psnr);
        if (cks.length >= 2) {
          const m0 = medianOf(Object.values(d.s3.steps[cks[0]].views_psnr));
          const m1 = medianOf(Object.values(d.s3.steps[cks[cks.length - 1]].views_psnr));
          psnrHtml = `${fmtNum(m0, 3)} → ${fmtNum(m1, 3)} dB (${m1 - m0 >= 0 ? '+' : ''}${fmtNum(m1 - m0, 3)})`;
          psnrSrc = 'jsonl 체크포인트 중앙값(첫↔끝) 폴백';
        } else { psnrHtml = '—'; psnrSrc = '체크포인트 < 2'; }
      }
      const ca = sbd.colors_artifact || null;
      const csIdxs = idxs.filter(i => d.s3.steps[i].color_stats);
      const csLast = csIdxs.length ? d.s3.steps[csIdxs[csIdxs.length - 1]] : null;
      h += `<table style="margin-top:6px">
        <tr><td class="k">PSNR 중앙값 개선폭 (s0→final)</td><td class="l">${psnrHtml}
          <span class="note">(${psnrSrc})</span></td></tr>
        <tr><td class="k">색 아티팩트 (colors_artifact)</td><td class="l">${ca
          ? `<span class="badge good">유</span> ${esc(ca.file || '?')} ·
             shape ${esc(JSON.stringify(ca.shape ?? '—'))} ${esc(ca.dtype || '')} ·
             sha ${esc(String(ca.sha256 || '').slice(0, 8))}…`
          : '<span class="badge bad">무 — s3b_def.colors_artifact 없음</span>'}</td></tr>
        <tr><td class="k">색 분화 최종값${csLast ? ` (s${csLast.step})` : ''}</td><td class="l">${csLast
          ? `평균 채도 ${fmtNum(csLast.color_stats.mean_saturation)} ·
             색 분산 ${fmtNum(csLast.color_stats.color_var)}`
          : '— color_stats 행 없음'}</td></tr></table>
        <div style="margin-top:5px">
          <button class="small" id="segDiffHeat" ${d.s3.perFaceFinal ? '' : 'disabled'}>s0 vs 3b final 잔차 차이</button>
          <span class="note">${d.s3.perFaceFinal
            ? '히트맵 차이 모드로 전환(기존 상태 세팅 재사용)'
            : 's3_face_residual_final.json 없음'}</span></div>`;
    }
  } else if (sg === '3c') {
    const sc3 = idxs.length ? (autoChecks(d) || {}).s3c : null;
    if (!sc3) h += planned;
    else {
      const dh = sc3.delta_hat_final || [];
      let verdictRows;
      if (sc3.kind === 'injected') {
        verdictRows = `<tr><td class="k">기대값 (정답)</td><td class="l">[${
            (sc3.expected || []).map(v => fmtNum(v, 3)).join(', ')}] m
            <span class="note">(${esc(sc3.expected_src || '없음')})</span></td></tr>
          <tr><td class="k">잔류 오차 |δ̂−정답|</td><td class="l"><b class="warn">${
            fmtNum(sc3.residual_vs_expected, 4)} m</b></td></tr>`;
      } else if (sc3.kind === 'scope0') {
        verdictRows = `<tr><td class="k">δ scope 0</td><td class="l">${sc3.immobile
          ? '<span class="badge good">부동 확인 — 전 스텝 δ̂=0</span>'
          : `<span class="badge bad">이동 감지 max|δ̂| ${fmtNum(sc3.max_abs_delta_hat, 4)}</span>`}</td></tr>`;
      } else {
        verdictRows = `<tr><td class="k">비변화 기준 잔류 |δ̂|</td><td class="l"><b class="warn">${
            fmtNum(sc3.residual_norm, 4)} m</b>
            <span class="note">(기대 0 — 오이동 = 위험 신호)</span></td></tr>`;
      }
      h += `<table style="margin-top:6px">
        <tr><td class="k">δ̂ 최종 [x, y, z]</td><td class="l">[${
          dh.map(v => fmtNum(v, 4)).join(', ')}] m</td></tr>
        ${verdictRows}</table>
        <div style="margin-top:5px"><button class="small" id="segDeltaScroll">δ̂ 궤적으로</button>
          <span class="note">궤적 카드로 스크롤 (정답선·점 클릭=스텝 전환)</span></div>`;
    }
  } else {   // 3d — 예정 안내만
    h += `<div style="margin-top:6px"><span class="badge na">예정</span>
      <span class="note">해동 변수: 평면 P / 산출물: 미세조정 평면 + 앵커 장력${
      idxs.length ? ` (행 ${idxs.length}개 감지 — 요약 수치 계약은 3d 구현과 함께)` : ''}</span></div>`;
  }
  return h + `<div class="note" style="margin-top:5px">구간 배지 클릭으로 열림 —
    스텝 선택과 독립(별도 섹션) · 재클릭=닫기 · 열람은 판독 JSON에 기록.</div></div>`;
}

// ---------- 패널 ----------
function renderPanel() {
  const d = state.run;
  if (!d) { $('#panel').innerHTML = '<p class="note">런을 선택하세요.</p>'; return; }
  let h = `<div class="note caption">페이지 3 = 공동 최적화(연속 구간) — 사이클 타임라인의 구간
    3a(렌더-온리)부터. 3a의 물음: "광도 잔차가 δ·평면·색까지 실제로 흘러오는가"(배선 증거).
    3b의 물음: "색이 수렴하는 동안 기하 압력이 어떻게 변하는가"(색만 학습·기하 동결 웜업).
    3c의 물음: "주입된 이동을 δ̂가 복원하는가"(δ 해동 — 주입 복원 검정, 목적=photo만).
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
    if (d.s3.finalMissing3c)
      h += `<div class="err">3c 흔적은 있는데 s3_face_residual_s3c_final.json이 없다 —
        writer 완주 후 새로고침(면 히트맵 3c final 모드는 그때 열린다).</div>`;
    // ④ 구간 산출물 요약 — 별도 섹션(스텝 선택·카드와 독립, 구간 배지 클릭으로 토글)
    if (state.selSegment !== null) {
      const sgDef = STAGES.find(s => s.id === state.selSegment);
      h += `<h2 id="segsummary">구간 산출물 요약 — ${esc(sgDef ? sgDef.label : state.selSegment)}
        <span class="badge eval">구간 배지</span></h2>` + segmentSummaryCard(d, state.selSegment);
    }
    const step = state.selStep !== null ? d.s3.steps[state.selStep] : null;
    h += `<h2>S3 정의 <span class="note">(manifest.s3_def/s3b_def + s3_views)</span></h2>${s3DefCard(d)}`;
    if (!step) {
      h += '<p class="note">타임라인에서 스텝을 클릭하세요.</p>';
    } else {
      const stageId = String(step.stage);
      const gradNote = stageId === '3c'
        ? `δ+색만 갱신(평면·o 동결) — 목적은 photo뿐이고 anchor·area는 진단 기록
           (manifest.s3c_def.objective_note). δ̂ 궤적 카드가 주입 복원 검정의 판독 축. 곡선 축: X=스텝.`
        : stageId === '3b'
        ? `색만 갱신하되 backward는 전 리프로 흘려 <b>동결군(δ·평면)의 그라디언트 노름도 기록</b> —
           "색이 수렴하는 동안 기하 압력이 어떻게 변하는가"의 관측. 곡선 축: X=스텝.`
        : `최적화 0스텝·backward 1회(가중치 갱신 없음) —
           광도 잔차가 δ/평면/색 변수군까지 실제로 흘러오는가의 증거. 전부 0이 아니어야 함(체크 ②).`;
      const gradBadge = stageId === '3c' ? 'δ 해동 — 주입 복원 관측'
        : stageId === '3b' ? '색 수렴 중 기하 압력 변화' : '배선 증거';
      h += `<h2>스텝 ${step.step} (구간 ${esc(stageId)}) — 항별 손실</h2>${stepLossCard(d, step)}
        <h2>그라디언트 노름 3군 <span class="badge eval">${gradBadge}</span></h2>
        <div class="card">${gradBarsHtml(d, step)}
          <div class="legend" style="margin-top:4px">
            <label><input type="checkbox" id="logYGradTgl" ${state.logYGrad ? 'checked' : ''}> 로그 y</label></div>
          ${gradCurveSvg(d, stageId)}
          <div class="note" style="margin-top:3px">${gradNote}</div></div>
        <h2>불변량 배지${stageId === '3b' || stageId === '3c' ? ' <span class="badge eval">동결군 0 확인</span>' : ''}</h2>
        <div class="card">${invariantBadges(d, step)}
          <div class="note" style="margin-top:4px">n_seeds == manifest counts.seeds(전수 유지 — 수명 규칙 ① ·
            densify/prune 금지) · α_g=|Δo| 이진 유도(자유 알파 금지) ·
            ${stageId === '3c' ? '3c: 평면·o 동결 — param_step_norms.planes=0, delta·colors 학습(δ̂ 해동).'
             : stageId === '3b' ? '3b: 기하(δ·평면) 동결 — param_step_norms.delta/planes=0, colors>0.'
                               : 'δ 동결(3a) · param_step_norm=0(3a).'}</div></div>
        <h2 id="viewscard">뷰 — 사진 / 렌더 / 잔차 + PSNR 분포</h2>
        <div class="card">${viewsCard(d, step)}</div>`;
      if (stageId === '3b' || stageId === '3c') {
        const cs = colorStatsSvg(d, stageId);
        h += `<h2>색 분화 타임랩스 <span class="note">(구간 ${esc(stageId)} 체크포인트 color_stats)</span></h2>
          <div class="card">${cs || `<p class="note">color_stats 없는 ${esc(stageId)} 행뿐 — 체크포인트 행에만 기록되는 계약.</p>`}
          <div class="note" style="margin-top:3px">${stageId === '3c'
            ? '3b 웜스타트 색이 δ 해동 중 추가 분화하는가 — 평균 채도·색 분산의 스텝 추이(렌더 타일과 대조).'
            : '중립 회색(0.5 상수)에서 출발한 색이 실재 면에서 분화하는가 — 평균 채도·색 분산의 스텝 추이(체크 ⑧ 육안 근거, 렌더 타일과 대조).'}</div></div>`;
      }
    }
    if (d.s3.byStage && d.s3.byStage['3c'] && d.s3.byStage['3c'].length)
      h += `<h2 id="deltahatsec">δ̂ 궤적 <span class="badge eval">주입 복원 검정 (구간 3c)</span></h2>${deltaHatCard(d)}`;
    h += `<h2>면별 잔차 히트맵 <span class="note">(s3_face_residual — 근사)</span></h2>
      ${faceResidualCard(d)}
      <div class="legend">
        <label><input type="checkbox" id="ghostTgl" ${state.showGhost ? 'checked' : ''}>
          잔차 없는 면 와이어</label>
        <label><input type="checkbox" id="domainTgl" ${state.showDomain ? 'checked' : ''}>
          도메인 외피</label>
        <label><input type="checkbox" id="s2ovTgl" ${state.overlayS2 ? 'checked' : ''}>
          <span style="color:#c8ccd4">S2 초기 상태(F*)</span></label>
        <span class="note">얇은 반투명 회백 — 출발 기하 위에 잔차가 어디 붙는지${
          state.run && state.run.s2ov && state.run.s2ov.nReal !== undefined
            ? ` (실재 면 ${state.run.s2ov.nReal}개 · ${esc(state.run.s2ovSource || '')})` : ' (첫 켬 때 s2_cells.json 지연 로드)'}</span>
      </div>
      <h2>검증 오버레이 3종 <span class="badge eval">평가 전용 — 방법 입력 아님</span></h2>
      ${verifyOverlaysCard(d)}`;
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
  on('#heatAutoTgl', 'onchange', () => {   // 스텝 추적 토글 — 켜면 현재 스텝으로 즉시 동기화
    state.autoHeat = $('#heatAutoTgl').checked;
    if (state.autoHeat && state.selStep !== null) selectStep(state.selStep);
    else { renderSyncBadge(); renderPanel(); }
  });
  on('#s2ovTgl', 'onchange', () => {       // S2 초기 상태(F*) — 첫 켬 때만 lazy fetch·생성
    state.overlayS2 = $('#s2ovTgl').checked;
    const d = state.run;
    if (d && state.overlayS2 && !d.s2ov) {
      ensureS2Overlay(d).then(() => {
        if (state.run !== d) return;   // 그 사이 런 전환 — 캐시만 유지
        attachOverlay(d); restyle(); renderSyncBadge(); renderPanel();
      });
    } else { restyle(); renderSyncBadge(); }
  });
  on('#gtOvTgl', 'onchange', () => {       // ⑨ LoD2 지붕면 — 데이터는 이미 로드(동기 생성)
    state.overlayGt = $('#gtOvTgl').checked;
    const d = state.run;
    if (d && state.overlayGt) {
      if (d.gtOv === undefined) { ensureGtOverlay(d); attachOverlay(d); }
      d.verifyOvUse = d.verifyOvUse || {};
      d.verifyOvUse.gt = (d.verifyOvUse.gt || 0) + 1;
    }
    restyle(); renderSyncBadge();
  });
  on('#cellGtTgl', 'onchange', () => {     // ⑩ 초기 점유 vs LoD2 — 첫 켬 때 1회 계산
    state.overlayCellsGt = $('#cellGtTgl').checked;
    const d = state.run;
    if (d && state.overlayCellsGt) {
      d.verifyOvUse = d.verifyOvUse || {};
      d.verifyOvUse.cells = (d.verifyOvUse.cells || 0) + 1;
      if (d.cellOv === undefined) {
        ensureCellsVsGt(d).then(() => {
          if (state.run !== d) return;
          attachOverlay(d); restyle(); renderSyncBadge(); renderPanel();
        });
      }
    }
    restyle(); renderSyncBadge(); renderPanel();   // 로딩/카운트 표시 갱신
  });
  on('#colorPrevTgl', 'onchange', () => {  // ⑪ 학습 색 — 첫 켬 때 bin+seeds 지연 로드
    state.colorPreview = $('#colorPrevTgl').checked;
    const d = state.run;
    if (d && state.colorPreview) {
      d.verifyOvUse = d.verifyOvUse || {};
      d.verifyOvUse.color = (d.verifyOvUse.color || 0) + 1;
      if (d.colorPrev === undefined) {
        ensureColorPreview(d).then(() => {
          if (state.run !== d) return;
          attachOverlay(d); restyle(); renderSyncBadge(); renderPanel();
        });
      }
    }
    restyle(); renderSyncBadge(); renderPanel();   // 배타 숨김·램프 범례·통계 갱신
  });
  document.querySelectorAll('input[name="heatmode"]').forEach(r => {
    r.onchange = () => {   // 히트맵 모드 — 면 색 재계산이 필요해 씬 재구축. 수동 선택 = 추적 해제
      state.autoHeat = false;
      state.heatMode = r.value;
      const d = state.run;
      if (d && (r.value === 'anchor_cost' || r.value === 'anchor_flip')) {
        // 앵커 가시화(⑦) — s2_cells 첫 필요 시 지연 로드 후 맵 1회 계산·캐시 + 사용 기록
        d.anchorViews = d.anchorViews || { cost: 0, flip: 0 };
        d.anchorViews[r.value === 'anchor_cost' ? 'cost' : 'flip']++;
        if (!d.anchorMaps) {
          ensureCellsInfo(d).then(() => {
            if (state.run !== d) return;
            buildAnchorMaps(d);
            if (state.heatMode === 'anchor_cost' || state.heatMode === 'anchor_flip') {
              buildScene(d); renderPanel();
            }
          });
        }
      }
      if (state.run) buildScene(state.run);
      renderPanel();
    };
  });
  on('#heatScopeTgl', 'onchange', () => {   // 표시 범위 — F* 기본 / 전체 후보(귀속용)
    state.heatScope = $('#heatScopeTgl').checked ? 'all' : 'fstar';
    if (state.run) buildScene(state.run);
    renderPanel();
  });
  // 차이 모드 일반화 — 대상/기준 상태 드롭다운(임의 두 체크포인트 비교)
  on('#diffTargetSel', 'onchange', () => {
    state.diffTarget = $('#diffTargetSel').value;
    if (state.run) buildScene(state.run);
    renderPanel();
  });
  on('#diffBaseSel', 'onchange', () => {
    state.diffBase = $('#diffBaseSel').value;
    if (state.run) buildScene(state.run);
    renderPanel();
  });
  // 체크포인트 필름스트립(⑥) — 썸네일 클릭=스텝 선택, 렌더/잔차 토글
  document.querySelectorAll('#panel .filmcell[data-step]').forEach(f => {
    f.onclick = () => {
      const d = state.run;
      if (d) d.filmClicks = (d.filmClicks || 0) + 1;
      selectStep(+f.dataset.step);
    };
  });
  document.querySelectorAll('input[name="filmkind"]').forEach(r => {
    r.onchange = () => { state.filmKind = r.value; renderPanel(); };
  });
  document.querySelectorAll('#panel .ckjump').forEach(b => {
    b.onclick = () => selectStep(+b.dataset.step);
  });
  // ④ 구간 요약 카드 버튼 — 기존 상태 세팅 재사용(selectStep / heatmode 수동 라디오 경로)
  on('#segS0Tiles', 'onclick', () => {     // 3a step0 스텝 선택 + 뷰 타일 카드로 스크롤
    const d = state.run;
    const a3 = ((d && d.s3 && d.s3.byStage) || {})['3a'] || [];
    if (!a3.length) return;
    selectStep(a3[0]);
    const el = $('#viewscard');
    if (el) el.scrollIntoView({ block: 'start' });
  });
  on('#segS0Heat', 'onclick', () => {      // 수동 히트맵 전환 — 라디오 핸들러와 동일 경로
    state.autoHeat = false; state.heatMode = 'init';
    if (state.run) buildScene(state.run);
    renderPanel();
  });
  on('#segDiffHeat', 'onclick', () => {    // s0 vs 3b final 잔차 차이 — 기존 diff 모드
    state.autoHeat = false; state.heatMode = 'diff';
    if (state.run) buildScene(state.run);
    renderPanel();
  });
  on('#segDeltaScroll', 'onclick', () => { // δ̂ 궤적 카드로 스크롤
    const el = $('#deltahatsec');
    if (el) el.scrollIntoView({ block: 'start' });
  });
  document.querySelectorAll('#panel svg .stepdot[data-sidx]').forEach(c => {
    c.onclick = () => selectStep(+c.dataset.sidx);
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
    schema: 'phd_s3_verify_p3_reading_v6',   // v6: 검증 오버레이 3종(⑨ lod2_overlay ·
                                             //     ⑩ cells_vs_gt 구멍/과잉 카운트 ·
                                             //     ⑪ color_preview — 전부 평가 전용)
                                             // v5: heat_ckpt_used(중간 체크포인트 히트맵 ⑤) +
                                             //     filmstrip(⑥) + anchor_map(⑦) + 일반화 diff 쌍 +
                                             //     heat_scope(F* 기본 표시 범위 ⑧ — 오독 정정)
                                             // v4: segment_summary_viewed(구간 배지 요약 카드 ④)
                                             // v3: 3c 항 ⑨~⑫ + auto.s3c + 3c final 히트맵 + injection
    page: 'p3_joint_opt_continuous',
    run: state.runName,
    bundle: {
      schema: d.manifest.schema, bundle_name: d.manifest.bundle_name,
      stage: d.manifest.stage, dataset: d.manifest.dataset,
      counts: d.manifest.counts, s3_def: d.manifest.s3_def ?? null,
      s3b_def: d.manifest.s3b_def ?? null,
      s3c_def: d.manifest.s3c_def ?? null,
      injection: d.manifest.injection ?? null,
    },
    checklist: [
      '① 렌더-사진 정렬이 실루엣 수준에서 겹침 (육안)',
      '② grad_norms 3군(δ/평면/색) 전부 0이 아님 (자동 — 배선 증거 · δ scope 0 런은 δ 제외)',
      '③ 불변량 전부 참: n_seeds 일치·α 이진·δ 동결·param_step_norm 0 (자동)',
      '④ SYNTH residual이 구조적으로 근소 (육안)',
      '⑤ [3b] PSNR 개선 — 첫↔끝 체크포인트 평균 (자동)',
      '⑥ [3b] 동결군(δ·평면) step norm 0 유지 (자동)',
      '⑦ [3b] 잔차가 기하 신호로 정화 — 히트맵 차이 모드 (육안)',
      '⑧ [3b] 색 분화가 실재 면에서 진행 — 렌더·color_stats (육안)',
      '⑨ [3c] 주입 런: δ̂가 정답선에 수렴 — 최종 잔류 오차 (자동 표시)',
      '⑩ [3c] 비변화 런: δ̂ 잔류 오차 표기 (자동 표시)',
      '⑪ [3c] scope 0 런: δ̂ 부동 (자동)',
      '⑫ [3c] anchor_plane 곡선 ∝ |δ̂| 증가 (진단 라벨 — 3d 예고)',
    ],
    checklist_policy: '참고 기준 — 엄격 런별 합불 아님 (판독 기록 2026-08-27 방침, 발견 기록으로 갈음)',
    auto: d.s3 ? {
      steps: d.s3.steps.length,
      stages: Object.keys(d.s3.byStage),
      wiring_ok: ck ? ck.wiringOk : null, wiring_detail: ck ? ck.wiringDetail : [],
      wiring_delta_exempt_scope0: ck ? (ck.scope0 ?? false) : null,
      invariants_ok: ck ? ck.invOk : null, invariants_detail: ck ? ck.invDetail : [],
      s3b: ck ? ck.s3b : null,
      s3c: ck ? ck.s3c : null,
      selected_step: step ? { step: step.step, stage: step.stage, losses: step.losses,
                              grad_norms: step.grad_norms, param_step_norm: step.param_step_norm,
                              param_step_norms: step.param_step_norms ?? null,
                              delta_hat: step.delta_hat ?? null,
                              color_stats: step.color_stats ?? null } : null,
      n_views: d.s3.views.length,
      face_residual: { method: d.s3.method, stats: d.s3.resStats },
      face_residual_final: d.s3.perFaceFinal ? { step: d.s3.finalStep,
        method: d.s3.finalMethod, stats: d.s3.resStatsFinal, diff: d.s3.diffStats } : null,
      face_residual_final3c: d.s3.perFaceFinal3c ? { step: d.s3.finalStep3c,
        method: d.s3.finalMethod3c, stats: d.s3.resStatsFinal3c } : null,
      heat_mode: state.heatMode,
      heat_auto_track: state.autoHeat,   // 연계 판독 ① — 스텝→히트맵 동기화 상태
      heat_shown: heatStateLabel(d, (heatData(d) || {}).mode || state.heatMode),
      heat_scope: {                      // 표시 범위(오독 정정) — F* 기본 / 전체 후보(귀속용)
        scope: state.heatScope,
        painted: d.paintCounts ?? null,  // { scope, real, sleeping }
        real_faces_total: d.nRealTotal ?? null,
        real_faces_paintable: d.realFaceSet ? d.realFaceSet.size : null,   // 외피 절단면 제외
        faces_total: d.faces.length,
        note: '기본 = F*(initial_real) 면만 — 렌더에 실재하는 면은 F*뿐, 잠든 gate-0 후보는 귀속용 토글(반투명·점선); 외피 위 F* 절단면은 페이지 관행상 히트맵 대상 밖(외피 토글)',
      },
      heat_ckpt_used: {                  // ⑤ 중간 체크포인트 히트맵 — ckpt 파일 사용 기록
        file_present: !!d.s3.ckptFR,
        schema: d.s3.ckptSchema,
        entries: (d.s3.ckptFR || []).map(e => ({ stage: e.stage, step: e.step })),
        diff_pair: state.heatMode === 'diff'
          ? { target: state.diffTarget, base: state.diffBase } : null,
      },
      filmstrip: {                       // ⑥ 체크포인트 필름스트립 사용 기록
        kind: state.filmKind, thumb_clicks: d.filmClicks || 0,
      },
      anchor_map: {                      // ⑦ 앵커 가시화 사용 기록(열람 횟수 + 통계)
        opens: d.anchorViews || { cost: 0, flip: 0 },
        active: (state.heatMode === 'anchor_cost' || state.heatMode === 'anchor_flip')
          ? state.heatMode : null,
        cost_stats: d.anchorMaps ? d.anchorMaps.costStats : null,
        flip_stats: d.anchorMaps ? d.anchorMaps.flipStats : null,
      },
      s2_overlay: { on: state.overlayS2, source: d.s2ovSource ?? null,   // 연계 판독 ②
                    real_faces: d.s2ov ? d.s2ov.nReal : null },
      lod2_overlay: {                    // ⑨ LoD2 지붕면 — 평가 전용, δ̂ 무관 고정 기준면
        on: state.overlayGt,
        gt_planes: d.gtPlanes ? d.gtPlanes.length : null,
        s1_planes_missing: d.s1PlanesMissing ?? null,
        fixed_frame: true, opens: (d.verifyOvUse || {}).gt || 0,
        note: '평가 전용 — 방법 입력 아님',
      },
      cells_vs_gt: {                     // ⑩ 초기 점유 vs LoD2 — 구멍/과잉 셀(1회 계산)
        on: state.overlayCellsGt, opens: (d.verifyOvUse || {}).cells || 0,
        computed: !!(d.cellOv && d.cellOv.stats),
        ...(d.cellOv && d.cellOv.stats ? d.cellOv.stats : {}),
        fail_note: d.cellOvNote ?? null,
        logic: '셀 중심 XY∈gt 지붕면(|n_z|>0.2) → 포함 면 평면 z 최댓값=gt 지붕고, ±0.3 m — 구멍=끔&지붕아래, 과잉=켬&지붕위 (파이썬 대조: B022 구멍 59·과잉 234)',
      },
      color_preview: {                   // ⑪ 학습 색(텍스처) 미리보기 — F* 시드만
        on: state.colorPreview, opens: (d.verifyOvUse || {}).color || 0,
        loaded: !!(d.colorPrev && d.colorPrev.stats),
        ...(d.colorPrev && d.colorPrev.stats ? d.colorPrev.stats : {}),
        fail_note: d.colorPrevNote ?? null,
        exclusive_hide_heat: true,       // 진단 칠 자동 숨김(라디오식 배타)
      },
      delta_shift_applied_m: currentDeltaShift(),   // 연계 판독 ③ — prior δ̂ 평행이동량
      segment_summary_viewed: d.segViews ? {        // ④ 구간 배지 요약 카드 열람 기록
        used: true, opens: d.segViews.opens,
        segments: d.segViews.segments,              // 구간 id → 열람 횟수
        selected_now: state.selSegment,
      } : { used: false },
      prior_faces: d.faceIsPrior ? d.faceIsPrior.reduce((a, b) => a + b, 0) : null,
      s1_planes_missing: d.s1PlanesMissing ?? null,
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
  const inj = d.manifest.injection;
  $('#countsline').textContent =
    `${d.manifest.bundle_name || state.runName} · stage=${d.manifest.stage || 's1'}` +
    (inj ? ` · 주입 dz=${Array.isArray(inj.delta_applied) ? +inj.delta_applied[2] : '?'}(${inj.route || 'route?'})` : '') +
    (d.s3 ? ` · 구간 ${stageTxt || sd.stage || '3a'} · 뷰 ${sd.n_views ?? d.s3.views.length}` +
            ` · 렌더러 ${sd.renderer || 'gsplat'}`
          : ' · S3a 없음(빈 상태)') +
    ` · 면 ${c.faces ?? d.faces.length} · 시드 ${c.seeds ?? '?'}` +
    ` · CRS ${d.manifest.crs || '?'} (offset −[${off.map(x => (+x).toFixed(1)).join(', ')}])`;
  $('#hud').textContent = `${state.runName} — 좌드래그 회전 · 우드래그 이동 · 휠 줌 · ` +
    `면 클릭=잔차 카드(페이지 2·1 점프) · 재클릭·빈 공간·ESC=해제 · ` +
    `히트맵 = F* 면 기본(잠든 후보는 '전체 후보 면' 토글 — 귀속용) · 면 색 = 5단 앰버 램프 · ` +
    `타임라인 스텝 클릭=손실·grad·뷰 타일` +
    ` + 히트맵 자동 동기화(우상단 배지 — 중간 체크포인트 포함) · 3c 스텝=prior δ̂ 평행이동 · ` +
    `F* 오버레이 토글=출발 기하 · 타임라인 [산출물 요약] 버튼(구간 배지)=단계 산출물 카드 · ` +
    `검증 오버레이 3종(LoD2 지붕면·초기 점유 vs LoD2·학습 색)=우측 카드(평가 전용)`;
}

// ---------- 런 전환 ----------
async function loadRun(name) {
  state.runName = name; state.selStep = null; state.selView = null; state.selFace = null;
  state.selSegment = null;   // ④ 구간 요약은 런별 — 전환 시 닫기(열람 기록은 d.segViews에 존속)
  $('#panel').innerHTML = `<p class="note">${esc(name)} 로딩 중…</p>`;
  try {
    if (!state.cache[name]) state.cache[name] = await fetchRun(name);
  } catch (e) {
    $('#panel').innerHTML =
      `<div class="err">런 ${esc(name)} 로드 실패: ${esc(e.message)}<br>
       writer가 s1/s2/s3a 번들을 아직 생성하지 않았을 수 있다.</div>`;
    $('#checkstrip').innerHTML = '<span class="note">—</span>';
    $('#timeline').innerHTML = '<span class="tlabel">—</span>';
    const sb = $('#syncbadge');
    if (sb) sb.style.display = 'none';
    return;
  }
  state.run = state.cache[name];
  const d = state.run;
  if (d.s3 && d.s3.steps.length) {          // 기본 선택: 마지막 스텝(3b면 final 체크포인트) + 첫 뷰
    state.selStep = d.s3.steps.length - 1;
    state.selView = d.s3.views.length ? d.s3.views[0].view_id : null;
  }
  // 기본 히트 모드 — 최신 구간의 final이 판독 축: 3c final > 3b final > step0
  // (스텝 추적 ON + 기본 선택=마지막 스텝과 정합 — heatModeForStep과 같은 결과)
  state.heatMode = (d.s3 && d.s3.perFaceFinal3c) ? 'final3c'
                 : (d.s3 && d.s3.perFaceFinal) ? 'final' : 'init';
  buildScene(d);
  // 런 전환 시 오버레이 토글이 켜져 있으면 새 런 것도 지연 생성해 이어 표시
  if (state.overlayS2 && !d.s2ov)
    ensureS2Overlay(d).then(() => {
      if (state.run === d) { attachOverlay(d); restyle(); renderSyncBadge(); }
    });
  if (state.overlayGt && d.gtOv === undefined) { ensureGtOverlay(d); attachOverlay(d); }
  if (state.overlayCellsGt && d.cellOv === undefined)
    ensureCellsVsGt(d).then(() => {
      if (state.run === d) { attachOverlay(d); restyle(); renderSyncBadge(); renderPanel(); }
    });
  if (state.colorPreview && d.colorPrev === undefined)
    ensureColorPreview(d).then(() => {
      if (state.run === d) { attachOverlay(d); restyle(); renderSyncBadge(); renderPanel(); }
    });
  renderHeader();
  renderChecklist();
  renderTimeline();
  renderPanel();
  maybeShowSegHint();   // 첫 성공 로드 시 1회 — 구간 산출물 요약 힌트(닫기 가능)
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
    const injBadge = r.injection
      ? ` [주입 dz=${Array.isArray((r.injection || {}).delta_applied)
          ? +r.injection.delta_applied[2] : '?'}]` : '';
    o.textContent = r.name + (ds.kind === 'synthetic' ? ` (합성 ${ds.synth_kind || ''})`
                              : ds.stable_id ? ` (${ds.stable_id})` : '') + injBadge +
                    (r.s3_ready === false ? ' [S3a 없음]'
                      : r.s3c_ready === true ? ' [+3c]'
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
// 헤드리스 검증 훅(읽기 전용 + 기존 단일 경로 재사용) — 모듈 스코프라 CDP가 내부 상태를
// 못 보므로 최소 창구만 노출: 상태 조회·스텝 선택(selectStep 공용 경로)·히트 데이터 표본.
// UI 조작 자체는 실제 DOM 경로(라디오·버튼 click)로 검증한다. 판독·기록에는 불참.
window.__p3 = {
  state,
  run: () => state.run,
  selectStep,
  heatData: () => (state.run ? heatData(state.run) : null),
  heatStates: () => (state.run ? heatStatesOf(state.run) : []),
  // 검증 오버레이 3종(⑨~⑪) — 헤드리스 대조용 조회/생성 창구(UI 조작은 DOM 토글 경로로)
  ensureGtOverlay: () => (state.run ? ensureGtOverlay(state.run) : null),
  ensureCellsVsGt: () => (state.run ? ensureCellsVsGt(state.run) : Promise.resolve(null)),
  ensureColorPreview: () => (state.run ? ensureColorPreview(state.run) : Promise.resolve(null)),
  cellsVsGtStats: () => (state.run && state.run.cellOv ? state.run.cellOv.stats : null),
  colorPreviewStats: () => (state.run && state.run.colorPrev ? state.run.colorPrev.stats : null),
};
