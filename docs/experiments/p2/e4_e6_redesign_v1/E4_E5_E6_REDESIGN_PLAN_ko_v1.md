# E4/E5/E6 재설계 계획 v1 — 프라이어 조건 단일변수 재구축

## 문서 상태와 경계

- 상태: `PLANNING RECORD — NOT E4/E5/E6 EXECUTION AUTHORITY`
- 목적: 현행 E4/E5/E6 결과가 프라이어 효과 판단 근거로 무효인 이유를 정량 진단으로
  고정하고, 신형 E3 공통 베이스 위의 단일변수 프라이어 조건(E4/E5/E6)을 재정의한다.
- 이 문서는 학습, 프라이어 생성, surface extraction, Roofer, 평가 실행을 활성화하지
  않는다. 실행에는 별도 결정 항목(`DEC-P1-0xx`)과 exact input/checkpoint/config 봉인,
  두-호스트 handoff 규약이 필요하다.
- 모든 기술 Return은 `official_PASS_usable: null`, `scientific_verdict: null`을 유지한다.
- 근거 계약: `docs/research/00_RESEARCH_CHARTER.md` §7(조건 정의), H3a/H3b/H3c/H5/H6,
  `DEC-P1-017`(바운디드 C4), `DEC-P1-019`(공유 footprint), `DEC-P1-021`(E1–E6 명명),
  `DEC-P1-023`(E2 product 기준선), `DEC-P1-024`(개발용 auto O/X 뷰어).

## 1. 진단 요약 — 왜 지금 E4/E5/E6가 E3보다 나쁜가

v22 개발용 auto O/X(O50, 199동): E1 29 / E2 29 / E3 23 / **E4 13 / E5 13 / E6 3**.
이 격차는 프라이어의 효과가 아니라 다음 네 겹의 구조 문제다.

### 1.1 교차 계보 비교 (비교 자체가 무효)

`configs/p2/e1_e6_roofer_ox_review_v1/reference_auto_ox_v1.json`의 소스 바인딩 기준,
E3는 신형 풀신 런(`e3_full_scene_fused_normal_confidence_v1`: fused vis/normal-confidence
타깃, MVC 0.5, distort 0, opacity-reset 사실상 off)이고 E4/E5/E6는 레거시
`e1_e6_techdev_v1`(구식 colmap_dense 타깃, w_depth 0.2 Huber, MVC 없음, distort 100,
reset 3000)이다. `DEC-P1-022`/`DEC-P1-024`가 이미 "prior 효과 결론 금지"를 명시했다.
같은 계보의 techdev `runs/E3_GS_IMAGE` Roofer 산출물이 존재하나 v22 평가에 미사용.

### 1.2 레거시 프라이어 맵 자체의 오염 (2026-08-11 신규 측정)

techdev ALS 프라이어 뷰 15개 표본(495,872 px)을 당시 학습 타깃(COLMAP geometric
depth)과 대조한 결과:

| 측정 | 값 |
|---|---|
| MVS 지원 px 중 \|ALS−MVS\| 중앙값 | **30.6 m** |
| \|Δ\| > 2 m 비율 | **74.8 %** |
| \|Δ\| > 5 m 비율 | 70.3 % |
| p95 | 203 m |
| confidence | **전 픽셀 1.0 고정** (receipt: `ONE_ON_ALL_PROJECTED_CLASS_2_OR_6_POINTS`) |

원인: 0.75 m 복셀 점군을 픽셀별 z-buffer로만 투영(차폐 무시) → 희소 점 사이로
배경 지면/후면 표면이 전경 픽셀에 누출. 여기에 합성 변형(건물 제거/삽입/높이
0.7·1.3배)과 datum 잔차가 겹친다. 즉 "정답에 가까운 depth/normal"이라는 전제가
픽셀 수준에서 성립하지 않았다.

### 1.3 가중·게이트 설계가 오염을 전력 반영 (증폭기)

`prep/runtime_configs/E4.yaml`: `w_external_als_depth 0.2 = w_depth 0.2`(동급),
ALS normal 0.1 = MVS normal(0.05)의 2배, confidence 게이트 전무. 75 % 오염 맵이
현재 증거와 같은 힘으로 지오메트리를 당겼다. 결과 서명: Roofer 생성은 오히려 증가
(G0 통과 154 vs E3 115, 커버리지 0.977 vs 0.857)하되 지붕 수직 RMSE 중앙값 2.9배
악화(2.085 vs 0.727 m), `G3_PLANE_PRECISION_LOW` 130동, `G4_BIAS_HIGH` 70동,
학습 valid depth 비율 반토막(0.91→0.48).

### 1.4 시드 오염 — E5 가중의 사각지대

E4/E5는 `seed_dense_lidar.ply`(MVS dense + 합성 ALS 합집합)로 초기화하고
`seed_protect_until_iter 5000`으로 보호했다. E5의 건물별 w_b는 **손실만** 낮추므로
(변경 건물 w_b ≈ 2.7e-10이어도) 시드에 심긴 2022 유령 지오메트리는 남는다.
E6도 동일 구조(`seed_dense_lod.ply`).

### 1.5 반증 — 프라이어는 배선이 맞으면 극적으로 작동

매치드 베이스 단일 건물 실험(`e4_local_4906982_55v_als_prior_v1`, 실제 ALS,
5게이트 confidence, w 0.01/0.005, 7000스텝 분기): Roofer f-score 0.105→**0.985**,
XY 커버리지 0.056→0.9999, 참조 normal 중앙값 2.52°→0.55°. 단 노멀 항 제거 절제
(`ALS_DEPTH_ONLY`)는 컨트롤보다도 나쁨(0.059) — 노멀 항이 핵심 기여.

## 2. 재설계 목표와 추정량

`DEC-P1-023` 준수: product 기준선은 E2, E3는 메커니즘 절제.

- 주 추정량(product): `ΔN_pass^product(m) = N_pass(m) − N_pass(E2)`, m ∈ {E4, E5};
  `E2 X→m O`(rescue)와 `E2 O→m X`(비열화 위반)를 분리 보고.
- 프라이어 증분(mechanism): `E3 X ∧ m O` 및 `T_plus_R_prior(m) = count(E2 X, E3 X, m O)`.
- E5 대 E4: 무변경 건물 비열등 + 변경 건물 유령/재현 오차 감소(H3b).
- 변경 건물에서 프라이어 재현 성공은 `temporal_status = PRIOR_REPRODUCTION` 또는
  `CHANGE_UNRESOLVED`로 태깅하며 현재-지오메트리 성공으로 집계하지 않는다.
- Roofer/LoD2 O/X와 semantic textured-mesh O/X는 독립 기록(계약 불변식 12).

## 3. 공통 베이스와 분기 규약 (모든 프라이어 조건 동일)

| 항목 | 값 |
|---|---|
| 베이스 런 | 봉인된 신형 E3 풀신 런 `P2-E3-FULL-SCENE-FUSED-NORMAL-CONFIDENCE-v1` (재학습 없음, `DEC-P1-017`의 matched-control 패턴) |
| 분기점 | E3 full-state checkpoint **7000** (model/optimizer/RNG 복원, `intervention_start_update: 7001`) |
| 종료 | 30000 (E3 봉인 런과 동일) |
| 뷰/시드 | exact 937 뷰 manifest, seed 0, neutral dense seed — E3와 바이트 동일 |
| 프라이어 주입 경로 | **단계형**. 1차(S2): 손실 전용 — E3 대비 단일변수 귀속을 깨끗하게 확보. 2차(S2b): 동일 베이스에서 **게이트드 시드 주입 + 손실** 쌍을 추가 실험(§5.4) — 손실 전용이 MVS 구멍(가우시안 부재 영역)에서 지오메트리를 "생성"하지 못하는 한계를 정면 검증 |
| 스케줄 | ALS/LoD 항은 warmup 7000·ramp 5000 (E3의 depth/normal 스케줄과 동일 계열) |
| 학습 도구 | gsplat 기반 미분 가능 렌더링, Docker 실행, 컨테이너 `JBGS_ARTIFACT_ROOT` 해석 |

단일변수 원칙: E4/E5/E6 상호 간 및 E3 대비 차이는 **프라이어 채널 구성 하나**뿐이다.
E4·E5는 exact 동일 ALS 바이트·동일 프라이어 뷰 캐시를 공유하고 conflict 가중만
다르다(계약 `00_RESEARCH_CHARTER.md` §7, `05_HANDOFF_PROTOCOL.md` 활성화 점검).

## 4. 프라이어 전처리 v2 — ALS 3D → per-view 2D 감독 맵 생성 (공통 파이프라인)

범위: 학습이 소비하는 것은 ALS 점군 자체가 아니라 **뷰별 npz 맵**
(`pixel_y/pixel_x/depth/normal/confidence`)이다. 본 절은 그 맵을 만드는 3D→2D
변환 전체 — (1) datum/정합, (2) 차폐 인지 투영, (3) per-pixel confidence 게이트,
(4) 누출 QA — 를 재정의한다. 손실 설계(§5)와의 경계: 여기서 만든 confidence가
손실의 per-pixel weight로, hit 픽셀 집합이 mask로 들어간다.

### 4.1 입력과 정합

- 입력: Gate-S0 기록 4타일 raw ALS(`690_5335`~`691_5336`, class 2/6)만. 합성 변형
  없음(합성-변형 강건성 진단은 §8의 별도 diagnostic으로 분리).
- datum: +45.7 m 단일 상수(2022 정표고→2024 타원체고) 유지, 장면별 재검증 게이트
  통과 필수(|signed z 중앙값| ≤ 0.50 m, XY p95 ≤ 0.50 m — `DEC-P1-017` 게이트 유지).
  잔차를 강체 오프셋으로 재적합하지 않는다(프라이어는 GT가 아님).
- CRS: EPSG:25832 명기.

### 4.2 차폐 인지 투영 (핵심 교체)

점 z-buffer 투영을 폐기하고 **연속 표면 레이캐스트**로 교체한다.

- 권장(P-A): **E3 fused 타깃 생성기와 동일한 투영기 재사용**. 신형 E3의 depth/normal
  타깃은 이미 Open3D `RaycastingScene` 메시 레이캐스트로 생성된다
  (`scripts/p2/e3_full_scene_fused_normal_confidence_v1/prepare_targets.py:164-200`,
  소스 = OpenMVS 메시). 같은 레이캐스트·카메라·픽셀 정렬 규약을 그대로 쓰고
  **소스 표면만 ALS class 2+6 결합 2.5D DSM TIN(0.5 m 격자, datum 보정 후)으로
  교체**한다. 현재 채널과 프라이어 채널이 동일 투영기에 소스만 다른 구조가 되어
  방법론 대칭성과 코드 재사용을 동시에 얻고, 가시성이 명목이 아닌 실제 게이트가
  된다.
- 대안(P-B): per-view hidden-point-removal(Katz) 후 점 투영 — 경계부 파라미터 민감.
- 벽면: 항공 ALS의 벽 점밀도 한계를 감안, TIN 수직면의 normal은 planarity 게이트로
  자연 감쇠시키고 별도 벽 보정은 하지 않는다.

### 4.3 confidence 게이트 (E4/E5 공통 정적 부분)

`combine_confidence_gates`(현재 미사용, `src/stage2/external_als_prior.py:70`)를
실사용 경로로 승격: `registration × density × planarity × visibility`.
모든 게이트 [0,1], 감쇠 전용, 최종 `confidence ≥ 0.05` 컷. current-consistency는
정적 게이트에서 **제외**(E5 전용, §5.2).

| 게이트 | 산출 | 억제하는 오류 모드 |
|---|---|---|
| g_reg (전역 스칼라) | `exp(−|z 중앙 잔차|/0.5)` | datum/정합 전역 편향 |
| g_density (per-pixel) | 국소 점밀도 정규화 | 벽·경계 등 희소 관측 영역의 과신 |
| g_planarity (per-pixel) | 국소 거칠기 `exp(−r/0.2)` | 식생·잡음 점의 평면 감독 오염 |
| g_visibility (per-pixel) | 레이캐스트 hit 유효성·grazing 각 | 차폐 누출(§1.2의 주범) — 명목 게이트에서 실제 게이트로 |

**게이트 5종 전체와 조건 배치 — 왜 current-consistency만 E5인가**: 게이트는
성격이 두 부류다.

| # | 게이트 | 무엇과 비교하나 | 성격 | 배치 |
|---|---|---|---|---|
| 1 | registration | 2022 ALS ↔ 현재 SfM sparse (전역 정합) | 프라이어 **자체 품질** | E4·E5 공통 |
| 2 | density | 2022 ALS 내부 (국소 점밀도) | 프라이어 자체 품질 | E4·E5 공통 |
| 3 | planarity | 2022 ALS 내부 (국소 거칠기) | 프라이어 자체 품질 | E4·E5 공통 |
| 4 | visibility | 카메라 기하 (레이캐스트 hit) | 투영 유효성 | E4·E5 공통 |
| 5 | current_consistency | **2022 ALS ↔ 2024 현재 MVS 깊이** | **시간 conflict/currentness** | **E5 전용** |

1–4는 "이 프라이어 데이터가 그 자체로 믿을 만한가"(2022 데이터 품질·투영 유효성)
이고, 5만 유일하게 **현재 증거와의 대조**로 "지금도 유효한가"를 묻는다. 계약이
정의하는 E4/E5의 단일 변수가 정확히 이 5번(conflict/currentness 가중)이므로,
E4에 5번을 남기면 두 조건 모두 conflict-aware가 되어 E4↔E5 대비(제안 기여의
핵심)가 소멸한다. 또한 H3a/H3b 검증 구조상 E4는 변경 건물에서 유령 재현을
**보여야**(무감쇠의 비용 관측) E5의 억제 효과가 측정 가능하다. 참고 계보: 바운디드
C4 런과 로컬 4906982 E4 런은 5게이트 전부를 포함했으므로 메커니즘상 E5에
가깝다 — 그 rescue 증거는 E5 실행 가능성의 근거로 재해석하고, 재설계 E4는
1–4만으로 얼마나 살아남는지를 새로 측정한다.

**전달 계약은 로컬 E4 실험과 동일 유지**: 뷰별 npz 스키마
(`pixel_y/pixel_x/depth/normal/confidence`)와 dataloader의 mask 의미론
(`mask = confidence > 0`, 투영 시 `≥ 0.05` 컷)은 검증된
`e4_local_4906982_55v_als_prior_v1` 계약을 바이트 호환으로 재사용한다 —
바뀌는 것은 맵의 **내용**(투영 방식·게이트 구성)뿐이며 dataloader는 무변경.

### 4.4 누출 QA 게이트 (신규 preflight)

fused MVS 지원 픽셀에서 `|prior − fused|` 분포를 계측해 receipt로 남기고,
점-투영 대비 개선을 정량 확인한다.

- 제안 임계(동결 전 제안값): 중앙값 ≤ 1.0 m, `>2 m` 비율 ≤ 25 %,
  그리고 §1.2의 점-투영 기준(74.8 %) 대비 `>2 m` 비율 절반 이하.
- 실제 시간 변화 픽셀이 포함되므로 임계는 변화 후보 마스크 제외 통계로 병기.
- 게이트 실패 시 학습 미시작, 실패 receipt 보존(`DEC-P1-017` 4게이트 규약 계승:
  해시/CRS receipt → 정합 잔차 → 비영 gradient → GPU 메모리 + 본 누출 QA).

## 5. 조건 정의 — 손실·mask·weight 설계

### 5.0 프라이어 손실의 공통 구조 (E4/E5 공유)

조건 정의의 실체는 "동결된 E3 손실 구성 위에 어떤 프라이어 항을 어떤 mask/weight로
추가하는가"이다. E3 항(photo/fused depth/fused normal/NC/MVC)은 바이트 수준 불변.

```
L_total = L_E3(불변)
        + w_als_d(t) · L_als_depth + w_als_n(t) · L_als_normal

L_als_depth  = Σ_{p∈M}  C(p) · Huber_δ( D̂(p) − D_als(p) ) / N
L_als_normal = Σ_{p∈M'} C(p) · ( 1 − |⟨n̂(p), n_als(p)⟩| ) / N'
```

- **mask** `M`: §4 레이캐스트 hit ∧ 유한값 ∧ `D_als > 0` ∧ `C ≥ 0.05`.
  mask 밖 픽셀은 값·gradient 모두 0 (프라이어 부재 = 무간섭).
- **weight** `C(p)`: E4 = `C_static(p) = g_reg · g_density(p) · g_planarity(p) · g_visibility(p)`;
  E5 = `C_static(p) · a_conflict(p)`. 전 성분 [0,1]·감쇠 전용·**detach**(가중으로
  gradient가 흐르지 않음 — `LOWER_ALS_CONFIDENCE_ONLY` 보장).
- `D̂` = expected depth(RGB+ED) — 동결된 E3 레시피의 `depth_supervision_mode:
  expected`와 **동일 렌더 통계**를 감독한다(현재 채널과 프라이어 채널의 통계 혼합
  충돌 방지; median/surface-intersection 모드는 사용하지 않음). `n̂` = 렌더 노멀
  (world frame; ALS 노멀도 world frame으로 정렬). depth는 Huber(δ=1.0 m: ≤1 m 이차→정밀 수렴, >1 m 선형→시간 변화·
  outlier에서 gradient 크기 상한), normal은 부호 불변 1−|dot|(2DGS 프리미티브 노멀
  부호 임의성 대응, [0,2] 유계라 outlier 폭주 없음).

**정규화 결함과 수정(G6, 필수)**: 현행 `robust_als_depth_loss`는 `N = Σ C`
(confidence-가중 평균)이다. 이 경우 균일 감쇠가 **상쇄**된다 — 한 뷰의 ALS 지원
전체가 `C=0.001`이어도 `(Σ C·h)/(Σ C) = 평균 h`로 복원되어, 변경 건물이 지배하는
뷰에서 E5의 conflict 감쇠가 무효가 된다. 수정: `N`을 weight와 무관한 값(유효 픽셀
수 `|M|`, 또는 `Σ C_static` 고정)으로 바꿔 `a_conflict`(및 정적 게이트)가 **절대
감쇠**로 작동하게 한다. 이 변경은 손실 스케일을 바꾸므로 `w` 제안값은 S1 파일럿
에서 재캘리브레이션한다.

**빈 픽셀(α≈0) 거동 — 시드 문제와 동전의 양면**: expected depth는 α≈0에서 0으로
치우쳐 residual ≈ `D_als`(수십 m)가 되고, Huber 선형 구간의 상수 크기 gradient가
"이 픽셀을 ALS 깊이로 덮으라"는 채움 압력으로 작동한다. 선택지:

- (A) `M &= α > τ_α` alpha-gate — 손실이 기존 표면 교정만 담당. 공백 영역 생성
  능력이 사라지므로 구멍 채움은 시드 주입(§5.4)이 전담.
- (B) 게이트 없음(현행) — 채움 압력 유지, 대신 저-α gradient의 부작용 감사(G5) 필요.

S1 파일럿에서 A/B를 같은 베이스로 비교 후 동결한다(D9).

### 5.1 E4_GS_ALS_unweighted (프라이어 재현/rescue 메커니즘 arm)

- 프라이어: §4의 실제 ALS depth+normal 뷰 캐시.
- confidence: **정적 게이트만**(registration·density·planarity·visibility).
  current-consistency 없음 — 계약의 "conflict 감쇠 없는" 정의를 복원한다.
  (주의: `DEC-P1-017`의 바운디드 C4는 current-consistency를 포함했으므로 사실상
  E5 메커니즘이었다. C4 계보는 그대로 보존하고, 재설계 E4는 이 정의로 되돌린다.)
- 손실: depth = Huber(δ=1.0 m, metric camera-Z), normal = sign-invariant 1−|dot|
  (`external_als_prior.py` 기존 구현 유지).
- 가중(제안): `w_external_als_depth 0.01`, `w_external_als_normal 0.005`
  — 로컬 4906982 실증값, MVS `w_depth 0.03` 이하 유지. 노멀 항 포함 필수(§1.5 절제 근거).

### 5.2 E5_GS_ALS_conflict_aware (배포형 product arm)

E4와 exact 동일 입력·캐시·가중에 **동결 conflict/currentness 가중 하나만 추가**.
conflict는 감쇠 전용(현재 항 불변, `LOWER_ALS_CONFIDENCE_ONLY`).

conflict 항 후보(동결 결정 필요, §9-D2):

| 후보 | 정의 | 강점 | 약점 |
|---|---|---|---|
| F1 픽셀형 | `exp(−|d_ALS − d_fused|/τ)`, fused 지원 없으면 중립 1.0 | 부분 변화 감지 | MVS 구멍에서 무방비(단, §4.2로 leak 자체가 제거됨) |
| F2 건물형 | DSM(MVS)−DSM(ALS) 중앙 절대차 로지스틱 w_b (techdev 계보 재사용) | 건물 단위 변화(신축/철거/증축)와 O/X 의미 일치, 강건 | 부분 변화 미분해능 |
| **F1×F2 (권장)** | 두 감쇠의 곱 | 두 해상도 모두 커버, 감쇠 전용 성질 유지 | 항 수 증가(둘 다 동결 필요) |

τ(제안 2.0 m), w_b 파라미터(σ0/τ/β)는 학습 전 동결하고 receipt에 고정한다.
w_b 산출은 영상 유래 DSM만 사용(GT/참조 불사용).

### 5.3 E6_GS_LoD_prior_diagnostic (진단 arm — primary 차단 유지)

- 허용 정보(계약): footprint/범위, 개략 높이 envelope, 벽 수직성, 건물/비건물.
  금지: 실제 지붕 경사/능선, 지붕면 수/경계/인접, LoD2 지붕 topology·Z·유형.
- 메커니즘(제안): (a) footprint 경계대 벽 수직성 손실, (b) 건물별 높이 envelope
  밴드 소프트 제약. 지붕면 평면 샘플 프라이어는 **사용하지 않는다**(허용 정보 초과
  + techdev G4 coverage 0.0065 붕괴의 재발 방지 — 붕괴 기전 진단 전 재실행 금지).
- 독립성 게이트: 평가 LoD2에서 유도한 LoD1은 `REFERENCE_DERIVED_DIAGNOSTIC_ONLY`.
  독립 소스 LoD 프라이어가 결정으로 바인딩되기 전까지 E6는 diagnostic 해석만
  가능하며 primary 비교표에서 별도 열로 격리한다(`DEC-P1-024` 격리 규약 계승).

### 5.4 시드 주입 실험 (S2b — 손실 전용 다음 단계)

손실 전용의 구조적 한계: expected-depth 손실은 **이미 존재하는** 가우시안을
이동·교정할 뿐, E3 densification이 도달하지 못한 완전 공백 영역(α≈0)에서의 생성
압력은 간접적이다(§5.0-B). 시드 주입은 그 영역에 프리미티브를 직접 배치하는
유일한 직접 경로이므로, 손실 전용(S2)으로 귀속을 확보한 **다음** 동일 베이스에서
쌍으로 검증한다.

시드 위생 규칙 (레거시 §1.4 사각지대 재발 방지):

1. 시드 소스는 §4 파이프라인과 동일한 차폐·게이트 통과 ALS 점만
   (`C_static ≥ τ_seed`, 제안 0.3) — 오염 점의 시드 유입 차단.
2. **E5-v2s의 시드는 conflict 가중으로도 게이트**(`w_b < τ_b` 건물의 시드 제외).
   "conflict 감쇠는 프라이어의 모든 주입 채널(손실+시드)에 적용된다"를 E4↔E5
   단일 변수의 정의로 명문화(D4).
3. `seed_protect` 금지 또는 ≤500 — 틀린 시드가 photo/depth 증거로 prune될 수
   있어야 함(레거시는 5000 보호가 유령을 고착).
4. 초기 opacity 0.1(기존 `mvs_seed_init_opacity` 관례), 중복 복셀은 dense MVS 우선
   제거(techdev `seed_unions` 규칙 재사용).
5. 시드 provenance(ALS 유래 플래그) 기록 — 사후 유령 귀속 분석용.

arm 구성: `E4-v2s`, `E5-v2s` (S2의 손실 구성과 동일, 시드만 추가) → 2×2 매트릭스
(손실만/손실+시드 × 무감쇠/conflict). 평가는 §7에 더해 **구멍 한정 지표**(E3
체크포인트 기준 α<τ 영역의 채움율·정확도)를 별도 집계해 시드 기여를 분리한다.

## 6. 구현 갭 (재설계 실행 전 필요 작업)

| # | 항목 | 현재 상태 |
|---|---|---|
| G1 | `external_als_warmup/schedule/ramp_steps` 키 | train.py에 없음(기존 `_scheduled_weight` 재사용으로 소규모) |
| G2 | E5 conflict 채널(픽셀 conflict 맵 or 건물 w_b 소비) | train.py에 없음(techdev 구현은 현행 트리 밖; npz `building_weight` 필드는 존재) |
| G3 | 차폐 인지 투영 스크립트(§4.2) + 누출 QA preflight(§4.4) | 신규 |
| G4 | E6 LoD 채널(벽 수직성·높이 envelope) | 신규(기존 `external_lod_*`는 현행 트리에 없음) |
| G5 | ALS depth 손실의 저-alpha 픽셀 거동 감사(expected-depth vs alpha 게이트, §5.0 A/B) | 감사 항목 — 로컬 E4에서는 문제 미발현, 풀신 재확인 |
| G6 | **손실 정규화 수정**: 분모를 weight-독립값으로 교체(§5.0). 기존 함수를 직접 변경하지 말고 `normalization=` 옵션(기본값 = 레거시 confidence_sum)으로 추가해 C4/로컬 E4 레거시 재현성을 보존 — 신규 config만 새 값 사용 | 필수 코드 변경 + 단위 테스트(`tests/p2/c4_existing_als_v1/test_external_als_prior.py` 확장) |
| G7 | 게이트드 시드 생성기(§5.4 위생 규칙 1·2·4·5) + provenance 기록 | 신규(S2b 전까지; TB `seed/fp_*` 계보 로깅은 기존 활용) |
| G8 | TensorBoard 스칼라 추가: E5 conflict 가중 분포(`stats/external_als_conflict_*`), 구멍 한정 지표 | 소규모(기존 `loss/external_als_*`, `loss_weight/external_als_*`, valid_pixel_count 로깅은 이미 존재) |

## 7. 평가 계획

- 평가기: v22 `ROOFER_REFERENCE_AUTO_OX_DEVELOPMENT_v3_NOT_OFFICIAL`, O50–O80,
  공유 표준 footprint(`DEC-P1-019`, exact LoD2 GroundSurface XY + stable ID) 동일 적용.
- 비교표: **같은 계보 6조건**(E1/E2 기존 산출 + 신형 E3 + 재설계 E4/E5/E6)만 한 표에.
- 페어드 전이표: `E2→E4/E5`(product rescue/비열화), `E3→E4/E5`(프라이어 증분),
  `E4↔E5`(conflict 가중 효과), 건물별 CSV로 산출.
- 변경 건물 태깅: `temporal_status` 필수, 현재-지오메트리 성공과 분리 집계.
- 모든 산출 `official_PASS_usable: null`, `scientific_verdict: null`,
  임계 `NOT_FROZEN` 캐비앳 유지. 확증적 추론·모집단 일반화 주장 금지.

## 8. 단계별 실행 계획 (각 단계 별도 결정으로 개시)

| 단계 | 내용 | 학습 비용 |
|---|---|---|
| S0-a | v22 평가기를 techdev 같은-계보 E3에 적용 → 현행 23 vs 13 격차 중 계보 효과 몫 정량화 | 없음 |
| S0-b | §1.2 누출 계측의 전 뷰 확장 receipt + 차폐 인지 투영 프로토타입 QA(§4.4 기준 충족 확인) | 없음 |
| S0-c | 로컬 4906982 절제 이상(depth-only < control) 원인 감사 — 노멀 항 기여 기전 확인 후 가중 동결 | 없음 |
| S1 | 로컬 4906982 55뷰 파일럿: conflict 후보 F1/F2/F1×F2 비교(D2), 빈 픽셀 A/B(D9), G6 정규화 반영 가중 재캘리브레이션(D7) | 소 |
| S2 | 풀신 937뷰 E4-v2, E5-v2 분기 런(7000→30000, seed 0, 각 1런) — **손실 전용** | 중 |
| S2b | 동일 베이스 `E4-v2s`/`E5-v2s` 게이트드 시드+손실 쌍(§5.4) — 구멍 한정 지표 포함 | 중 |
| S3 | §7 평가 + 페어드 전이표 + 기술 Return (S2·S2b 2×2 통합) | 소 |
| S4 | (별도 결정) 합성-변형 conflict 강건성 diagnostic(H6 폴백), E6 독립 소스 확보 후 E6-v2 | — |

## 9. 결정 필요 항목 (인간 리뷰어 승인 대상)

- D1. 재설계 E4 정의 복원: current-consistency 제외(§5.1) — 기존 C4 계보와의 라벨
  관계 정리 포함.
- D2. E5 conflict 항 동결: F1 / F2 / **F1×F2(권장)** 및 τ, w_b 파라미터.
- D3. 분기 규약: 7000 분기(권장) vs 처음부터 재학습.
- D4. 시드 정책 확정: 단계형(S2 손실 전용 → S2b 게이트드 시드 쌍) 채택 여부와,
  "conflict 감쇠는 손실+시드 모든 주입 채널에 적용"을 E4↔E5 단일 변수 정의로
  명문화(§5.4 규칙 2).
- D5. 누출 QA 임계(§4.4 제안값) 동결.
- D6. E6 독립 LoD 소스 후보와 바인딩 절차(확보 전 diagnostic 유지).
- D7. 가중 최종값(0.01/0.005 제안) — G6 정규화 변경 반영 재캘리브레이션 포함,
  S1 파일럿 결과로 동결.
- D8. 본 계획의 실행 결정 번호 발행과 두-호스트 handoff 경로.
- D9. 빈 픽셀 정책(§5.0 A alpha-gate vs B 채움 압력 유지) — S1 A/B 비교 후 동결.

## 10. 코드 반영·커밋 전략

원칙: **"실험 다 하고 정리"는 금지**한다. 리포 불변식 2·3(재현성, one task one
commit)상 각 런의 receipt는 실행 시점의 커밋/해시를 기록해야 하므로, 런에 쓰이는
코드·config가 미커밋 상태면 계보가 성립하지 않는다. 러너블 단위로 **선커밋 →
실행 → receipt 커밋** 순서를 지킨다.

| 순서 | 커밋 단위(각각 태스크 ID 1개, Docker 검증 후) | 성격 |
|---|---|---|
| 0 | 현재 워킹트리에 쌓인 미커밋 자산(로컬 E3/E4 실험 config·script·doc)을 소속 태스크별로 분리 커밋해 베이스 정리 | 백로그 청산 |
| 1 | 본 계획 문서 | 설계 기록 |
| 2 | G6 손실 정규화 옵션 + 단위 테스트 (동작 변경 없는 opt-in — 레거시 기본값 유지) | src/tests |
| 3 | 투영기 v2(prepare_targets 재사용 계열) + 누출 QA preflight + config | scripts/configs |
| 4 | train.py 채널 확장(스케줄·conflict 소비·G8 로깅) + 테스트 | src/tests |
| 5 | (S2b 전) 게이트드 시드 생성기 G7 + 테스트 | scripts/tests |
| 6+ | 각 실험 단계(S0/S1/S2/S2b)의 config 선커밋 → 런 → 컴팩트 receipt 커밋 | 단계별 반복 |

- 커밋마다 해당 태스크 외 무관 변경 미포함(불변식 3), 실패는 receipt로 가시화
  (불변식 4).
- 레거시 함수·config는 바이트 보존: 동작 변경은 전부 새 키/옵션의 opt-in으로
  넣어 과거 런 재현성을 깨지 않는다(G6 방식).
- 검증 루틴: `python scripts/repository/validate_agent_instructions.py` 및
  해당 워크스트림 unittest를 컨테이너에서 실행 후 커밋.

## 11. 계약 준수 체크리스트

- [ ] LoD2 Z / RoofSurface / 지붕 유형 / semantic class / 최종 지붕 모델을 학습·초기화·
      crop·조기종료·하이퍼파라미터 선택에 불사용 (footprint XY+ID만, Stage-3 공유 통제)
- [ ] E4·E5 exact 동일 ALS 바이트·베이스·시드·스케줄, conflict 가중만 상이
- [ ] ALS와 LoD 프라이어를 한 arm에 병합하지 않음
- [ ] 평가 참조는 evaluation-only, 프라이어는 GT로 재적합하지 않음
- [ ] Docker 실행, script+config 재현성, 도구 버전·커밋·해시 기록
- [ ] EPSG:25832 및 datum 변환 기록, gravity는 지형 MVS normal에서 1회 추정
- [ ] 용어: gsplat, "미분 가능 렌더링" (뉴럴 렌더링 표기 금지)
- [ ] 실패는 issue log에 가시화, `scientific_verdict: null` 유지
