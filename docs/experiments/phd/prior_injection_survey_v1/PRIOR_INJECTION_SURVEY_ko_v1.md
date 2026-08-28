# 불확실한 외부 3D prior 주입 문헌 서베이 v1.1 — PHD-PRIOR-SURVEY-v1

- 상태: **SURVEY RECORD** — 조사 기록. 실행 권한 없음. `scientific_verdict: null`
- 최초 조사: 2026-08-27. 방법론 경계 최신화: 2026-08-28
- 계기: 지도교수 면담에서 "GS 기반 포인트 클라우드 최적화(= prior를 손실 항으로 넣는
  비정형 가우시안 연속 최적화, 이하 **(a)**)로 회귀" 제안. 사용자 확정 조사 질문:
  ① 기존 문헌은 왜 prior를 썼나 ② 어떻게 넣었나 ③ 무엇이 좋아졌나
  ④ (추가) **prior가 낡거나 어긋난 경우를 다루는가**.
- 방법: 병렬 조사 5축(각 축 8~16편, 웹 검색 기반). 본 문서는 에이전트 수집
  원자료의 취합·판정본. **논문 인용 전 원문 확인 필수** — §7.6 검증 유의 참조.
- 관련 문서: `docs/experiments/phd/research_narrative_v1/RESEARCH_NARRATIVE_V5_FOUNDATION_ko_v1.md`,
  `docs/experiments/phd/methodology_v1/MINIMUM_RISK_PRIOR_GUIDED_RECONSTRUCTION_ko_v1.md`.

## 0. 요약 (5줄)

1. 문헌에서 prior-as-loss가 성공한 설정은 거의 전부 **prior가 현재-일치**인 경우다
   — 같은 입력 영상에서 단안 추정했거나(낡음이 정의상 부재) 영상과 동시 취득한 센서다.
2. 우리 설정(수년 시차의 이종 자산 LoD2/ALS)에 가장 가까운 GS4Buildings(2025)와
   GeoGS(2026)는 각각 구조 prior와 영상 세부의 결합을 이미 강하게 다룬다.
   GS4Buildings는
   강한 prior 정칙화가 문·창·얇은 구조를 뭉갬을 확인하고(귀속: LoD2의 조악한
   해상도) "국소 장면 특성 기반 동적 가중"을 미래 과제로 남겼다[원문 확인
   2026-08-27]. 오류 축조차 추상화(해상도)까지만 갔고 낡음(시간)은 논의 자체가
   없다 — 우리 가중 딜레마의 공간(추상화)판 재현이며, 시간판은 미착수.
3. "적응 가중 함수 = 판정 함수"는 우리 논증이 아니라 **동치 정리**다
   (Black & Rangarajan 1996; 연속 완화의 수렴 극한이 이산 기각임은 GNC, Yang et al. 2020).
   즉 (a)를 이론적으로 끝까지 밀면 이산 채택/기각(현 S3 설계)에 도달한다.
4. 현재 snapshot에서 남는 후보 공백은 adaptive weighting 자체가 아니라 **시간적
   유효성과 공간 정합이 미확인된 외부 3D prior에 대해 source별 예상 기하위험을
   보정하고 image/prior/fusion/abstention을 국소 선택하는 현재시점 재구성**이다.
5. 공동 최적화는 연구 정의가 아니라 방법 가설이다. Wu & Vallet(2026)식
   `detect→remove→fuse`와 L2M-Reg식 uncertainty-aware registration을 결합한 강한
   순차 baseline이 같거나 더 낫다면 순차법을 채택해야 한다.

## 1. 조사 축

| 축 | 대상 | 핵심 질문 |
|---|---|---|
| A | 깊이·노멀·단안 prior를 손실로 주입하는 GS/미분 가능 재구성 | prior의 시점 관계는? 가중 딜레마를 다뤘나? |
| B | LiDAR/점군 prior (초기화·감독·융합) | 점군은 동시 취득 전제인가? 이시점 결합 전례는? |
| C | 구조·제약형 주입(메시·앵커·평면 결박) | 제약의 정당성 출처는? 틀린 제약의 탈출 장치는? |
| D | 이시점·낡은 prior·지도/모델 갱신 | 낡은 3D prior + 현재 관측의 공동 최적화 전례는? |
| E | 틀릴 수 있는 제약의 강건 처리 이론(SLAM/비전) | "연속 재가중 ↔ 이산 판정" 관계의 문헌 진술은? |

## 2. 축 A — 깊이·노멀·단안 prior (손실형)

| 논문(연도·venue·arXiv) | prior 출처·시점 관계 | 주입 방식 | 손실 가중 처리 | 개선 | prior 오류 처리 |
|---|---|---|---|---|---|
| MonoSDF (NeurIPS 2022, 2206.00665) | 단안망(Omnidata)이 학습 입력 영상에서 추정 → 현재-일치 | 스칼라 손실(SDF 렌더 깊이·노멀 감독) | 고정 스칼라 depth 0.1/normal 0.05, 배치별 scale-shift 정합 | 실내·희소뷰 implicit 재구성 성립(계열 원조) | 없음 |
| NeuRIS (ECCV 2022, 2206.13597) | 단안 노멀, 입력 영상에서 → 현재-일치 | **적응 가중(이산 게이트)** | 렌더 패치의 다시점 광도 일관성 불합격 시 해당 노멀 prior 기각 | ScanNet 세부 구조 보존 개선 | **있음** — 다시점 일관성 기반 자동 기각(오류 원인은 추정기 한계) |
| Depth-Regularized 3DGS (CVPRW 2024, 2311.13398) | 단안 metric 깊이(ZoeDepth), 입력 영상에서 | 스칼라 손실 + **스케줄(early-stop)** | "깊이 정칙화를 오래/세게 걸면 악화" 관찰 → 검증 손실로 중단 | few-shot floater 억제 | 시간축 스케줄로 딜레마 회피 |
| FSGS (ECCV 2024, 2312.00451) | 단안 깊이(DPT), 입력 영상에서 | 스칼라 손실(Pearson 상관형) + 성장 구조 | 절대 스케일을 버리는 손실 설계 | 희소뷰 NVS 대폭 개선 | 스케일 오류만 무력화 |
| DNGaussian (CVPR 2024, 2403.06912) | 단안 깊이, 입력 영상에서 | 스칼라 손실 + 구조 분리 | Global-Local 깊이 정규화 + 깊이 손실 시 shape 동결 | 희소뷰 NVS 개선 | 오류 전파 경로 차단만, 감지 없음 |
| SparseGS (3DV 2025, 2312.00206) | 단안 깊이, 입력 영상에서 | 스칼라 손실 + 이산 프루닝 | 패치 Pearson + mode/blended depth 괴리로 floater 제거 | 희소뷰 floater 제거 | 자기 기하 오류용, prior 오류용 아님 |
| DN-Splatter (WACV 2025, 2403.17822) | 센서 깊이 = **동시취득**(iPhone LiDAR) 또는 단안 | 스칼라 손실(edge-aware) | gradient 가중 logL1, λ_d 0.2/λ_n 0.1 고정 | mesh Acc 0.024 m 등; 센서깊이가 단안의 2배+ 우수 | 이미지 edge 감쇠뿐, 명시 신뢰도 없음 |
| VCR-GauS (NeurIPS 2024, 2406.05774) | 단안 노멀, 입력 영상에서. 문제의식=다시점 간 예측 불일치 | **픽셀 신뢰도 가중** | w=exp((N̂·N−1)/γ), γ=0.005 | T&T F1 0.40 vs 2DGS 0.30 | 있음 — 단 '틀림'의 정의가 뷰 간 불일치 |
| CDGS (2025, 2502.14684) | 단안+SfM 깊이, 입력 영상에서 | 픽셀 신뢰도 가중 | multi-cue 신뢰도 맵 | PSNR +2.31 dB 등 | 신뢰도 가중이 본체 |
| In Depth We Trust (2026, 2604.05715) | 단안 깊이 파운데이션 모델, 입력 영상에서 | **이산 마스크 + 선별 감독** | Depth-Inconsistency Mask(가상 스테레오 재투영 검정) | ScanNet++ +0.30 dB 등 | **가중 딜레마 명시 실측**: 맹목 감독 −0.52 dB |
| GPU-SDF (ICRA 2026, 2602.23926) | 기하 prior 불확실성 자체가 주제 | 적응·불확실도 연속 변조 | "기각=과소구속, 신뢰=오염" 명명 → 연속 가중 절충 | 실내 SDF 세부 향상 | 있음 — 우리 딜레마의 현재-prior 버전 |
| EnerGS (2026, 2604.26238) | 주행 LiDAR **동시취득**, 수직 FOV 부분성 | 공간 에너지장(occupied/free/unknown 3분할) | 공간적으로 내장된 가중 | KITTI PSNR +1.79 등 | 'prior 없는 곳' 처리만, '틀린 곳'(변화) 미정의 |
| ARSGaussian (ISPRS J. 2026, 2412.18380) | 항공 ALS + 항공영상, **동시대 취득**("단기간, 변화 미고려" 명시) | 초기화 + 적응 densification + 깊이·평면 손실 | 고정 계수, 픽셀급 정합(<1 m) | 기하 RMSE −79.9%(vs LetsGo) 등 | SOR outlier 제거 수준 |
| GS4Buildings (2025, 2508.07355) | **독립 과거 자산: CityGML LoD2** + 현재 UAV 영상(TUM2TWIN) — 우리와 최동형 | 초기화(LoD2 샘플링, SfM-free) + 스칼라 손실(레이캐스트 깊이·노멀) | **2단 스케줄**(전기 prior 강조 → 후기 감쇠) | M3C2 −32.8%, 완전성 +20.5%, VOC +63.9%, 프리미티브 −71.8% (정확도 참조=UAV **동시취득** 레이저 점군, 완전성 참조=**LoD3 유래 점군**=prior와 계보 정합 — 순환성 주의) | **부분** — 가시성 마스크+스케줄뿐. 문·창·얇은 구조 과평활 자인(정성 비교 기반, 귀속=LoD2 조악 해상도), "국소 특성 기반 동적 가중"=future work[원문 확인]. **명시적 낡음 처리 미확인** |
| GeoGS (ISPRS J. 2026, S0924271626003588) | **독립 외부 자산**(ALS·저 LoD 도시모델) + 희소뷰 영상 | global structural anchor와 local detail의 2단 결합 | prior/visual-depth의 dual-gated adaptive weighting | UAV·거리뷰 희소뷰 geometry 개선 | 현재 snapshot에서 explicit stale/change reject·abstain은 확인 필요 |

**축 A 판정**: 15편 중 11편의 prior가 현재-일치(입력 영상 유래 또는 동시취득) —
'낡음'이 정의상 부재. 가중 딜레마는 이 계열도 명시 실측(In Depth We Trust,
Chung et al., GPU-SDF, GS4Buildings)했으나 전부 **공간적 신뢰도**(어느 픽셀이
틀렸나)의 해법이고 **시간적 신뢰도**(자산이 아직 유효한가)를 다룬 손실 설계는
현재 snapshot에서 확인하지 못했다. 낡은 이종 자산을 직접 쓰는 최근접
GS4Buildings·GeoGS는 “영상이 약한 곳에서 외부 구조를 적응적으로 쓴다”는 설계
영역을 이미 차지한다. 따라서 우리 공백은 temporal/registration validity와 국소
source risk·abstention으로 좁혀야 한다.

## 3. 축 B — LiDAR/점군 prior

| 논문(연도·venue·arXiv) | 시점 관계 | 주입 방식 | 정합 확보 | 개선 | 불일치 처리 |
|---|---|---|---|---|---|
| Urban Radiance Fields (CVPR 2022) | 동일 수집 주행(캠페인 동일) | expected-depth + line-of-sight 손실 | 동일 리그 캘리브레이션 | Street View NVS·표면 재구성(시조) | 없음 |
| S-NeRF (ICLR 2023, 2303.00749) | 주행 동시취득 | 깊이 감독 + **학습형 적응 가중** | 데이터셋 캘리브레이션, 깊이는 noisy 취급 | 합성 MSE 7~40%↓ | 부분 — 센서 잡음 대상 |
| LidaRF (CVPR 2024, 2405.00900) | 동기화 LiDAR+카메라 | 구조 융합 + occlusion-aware 깊이 감독(커리큘럼) | 센서 캘리브레이션 전제 | PandaSet PSNR 27.26 등 | 부분 — ghost point 온라인 배제 |
| Street Gaussians (ECCV 2024, 2401.01339) | ego 동시취득 | 초기화 + L1 깊이 손실 | 차량 캘리브레이션 | Waymo PSNR 34.61; LiDAR-init +0.59 | 없음 |
| DrivingGaussian (CVPR 2024, 2312.07920) | ego 동시취득 | 초기화 + LiDAR 위치 손실 | 캘리브레이션·trajectory | LiDAR-init 28.74 vs SfM-init 28.36 | 없음(동적 전경 전처리 제거) |
| TCLC-GS (ECCV 2024, 2404.02410) | 차량 동기 | SDF octree→메시 초기화 + 메시 렌더 깊이 감독 | 외부/내부 행렬 정확 전제 | depth AbsRel 0.42→0.03 등 | 없음 |
| LiHi-GS (2024, 2412.15447) | 동일 플랫폼, **프레임 간 시간차 명시 인정** | 초기화 + 미분 가능 LiDAR 렌더 감독 + 가시성 γ 분리 | 분리 포즈 최적화 | LiDAR depth L1 5.57→1.14 m | 있음(초 단위 미시 스케일) |
| LetsGo (SIGGRAPH Asia 2024, 2404.09748) | 핸드헬드 동시취득 | 다해상도 초기화 + unbiased depth regularizer | 동일 기기 | 대규모 렌더·floater 제거 | 없음 |
| LI-GS (2024, 2409.12899) | 동일 시스템 동시취득 | 2D surfel + 평면 제약 GMM(전 단계 주입) | 정밀 측정 전제 | Chamfer 52.6~68.7% 개선 | 없음 |
| LiV-GS (RA-L 2024, 2411.12185) | SLAM 동시 스트림 | 공유 공분산 정렬 + FOV 밖 조건부 제약 | front-end tracking | 야외 SLAM 종합 우위 | 부분 — '점군 없는 곳'만 |
| ARSGaussian (2025, 2412.18380) | **별도 플랫폼·별도 비행**(단 "단기간, 변화 무가정" 명시) | 초기화 + LiDAR 기준 적응 densification + 깊이·평면 손실 | strip adjustment + Colmap-PCD 픽셀급 | RMSE 1.626→0.327 m | 사실상 없음 |
| UAV geometry-aware 3DGS (2025, S1569843225002377) | 동일 캠페인, "정밀 정합" 전제 | 초기화 + 깊이·법선·곡률 감독 | 정밀 정합을 입력 조건으로 요구 | 대규모 UAV 개선(유료 미확보) | 없음(전제로 명시) |
| GTLR-GS (2026, 2603.23192) | 백팩 동시취득 | 곡률 배치 + metric 깊이 + per-pixel 신뢰도 | 전역 정합 전제 | ScanNet++ PSNR +0.61 | 부분 — 근거가 영상 텍스처 |
| PreSight (ECCV 2024, 2403.09079) | **과거 traversal prior** → 이후 주행 인식 | prior feature를 현재 feature에 concat(재구성 아님) | GPS 정합, 0.5 m 잡음 내성 실험 | HD-map +14.6 AP 등 | 부분 — 정적 마스킹으로 회피 |
| CL-Splats (ICCV 2025, 2506.21117) | **옛 3DGS 모델 + 나중 새 영상** — 구조 동형 | 변화 감지(DINOv2+HDBSCAN) → 변화 영역만 국소 재최적화, 나머지 동결 | 동일 좌표계 공유 전제 | naive 재학습 대비 우위 | **있음(핵심 전례)** — 이산 스위치, 단 판정이 최적화 밖 |

**축 B 판정**: LiDAR는 압도적으로 동시취득 전제(점군=참 기하 취급) — 충돌 장치가
원리적으로 불필요했다. 존재하는 불일치 장치는 전부 센서 잡음·초 단위 시간차
스케일. "과거·이시점 점군 + 현재 영상 결합에서 변화 충돌을 다루는 GS 재구성"
직접 전례 미발견. 최근접: ARSGaussian(변화를 설계에서 배제), PreSight(회피),
CL-Splats(가장 가까운 직접 장치 중 하나이나 prior가 이전 GS 모델·순차 판정).

## 4. 축 C — 구조·제약형 주입

| 논문(연도·venue·arXiv) | 제약 출처 | 결박 강도 | 남는 변수 | 개선 | 틀린 제약의 거동·탈출 |
|---|---|---|---|---|---|
| SuGaR (CVPR 2024, 2311.12775) | 자체 추정(선행 GS→Poisson 메시) | 혼합: 1단 소프트 → 2단 **하드**(barycentric 결박) | 메시 정점 + 면 위 가우시안·색 | 고품질 렌더+빠른 메시 | 자산 시효 문제 자체가 없음(자체 증류). 위상 오류 고정, 색이 은폐 |
| Gaussian Frosting (ECCV 2024, 2403.14554) | 자체 추정(SuGaR류 메시) | **하드 + 적응 슬랙**(불확실성 따라 층 두께 가변) | 층 내부 좌표·색 | SuGaR 대비 향상 + 볼륨 효과 | "제약 불신 → 슬랙 확대"의 연속형 탈출(이산 아님) |
| GaMeS (2024, 2402.01459) | 외부 메시 가능 또는 자체 학습 면 | **하드 모수화**(면이 기하 소유) | 정점·면 위 파라미터·색 | 렌더+실시간 변형 | **탈출 없음** — 메시 오류가 렌더로 전가, 검증 기제 부재 |
| Scaffold-GS (CVPR 2024, 2312.00109) | 자체 추정(SfM 앵커 격자) | 혼합(앵커 하드, 오프셋 연속) | 앵커 특징·오프셋·MLP | 동급+ PSNR, 저장량↓ | 앵커 성장/가지치기 = 이산 구조 갱신(신호는 내부 통계) |
| Octree-GS (TPAMI 2025, 2403.17898) | 자체(LOD 계층) | 혼합 | 레벨별 앵커 | 대규모 속도·확장성 | 기하 가정 아님 — 해당 없음 |
| 2DGS (SIGGRAPH 2024, 2403.17888) | 보편 가정(국소 평면) — 표현 수준 | 프리미티브 하드(두께 0 디스크) + 소프트 정칙화 | 디스크 전체 자유도 | DTU CD ≈0.80 mm(3DGS ≈1.96) | 볼륨성 물질에서 저하, 프리미티브별 탈출 없음. 우리 S2 표현 근거 |
| PGSR (TVCG 2024, 2406.06521) | 자체("기하 prior 없음" 명시) | 소프트(평면화 손실) | 전체 자유도 | DTU CD 0.53, TnT F1 0.51 | 다중뷰 일관성 연속 게이팅 |
| PlanarGS (NeurIPS 2025, 2510.23930) | 외부 일반 모델(시각-언어 평면 후보) | 소프트(공면성 손실+감독) | 전체 자유도 | 실내 기하 SOTA급 | **사용 전 검증**(cross-view 융합 정련 후 채택) — 단 이산 기각 기록 없음 |
| PlanarSplatting (CVPR 2025, 2412.03451) | 보편 가정(실내=평면 집합) | **하드**(기하=평면 프리미티브 그 자체) | 평면 파라미터·개수 | ScanNet 계열 기하 우위, 3분 | 비평면 표현 불가(실패가 표현에 내장). "평면이 기하 소유"의 최근접 표현 전례 |
| 3D Gaussian Flats (2025, 2509.16423) | 자체(워밍업 GS→SAMv2+RANSAC 평면) | 혼합-이산(평면 귀속=하드, 나머지 자유) | 평면·면내 2D·자유 3D | 깊이 RMSE 0.27(2DGS 0.39) | **이산 채택은 편도(one-way)** — 역방향 방출(기각·복귀) 없음 |
| ManhattanSDF (CVPR 2022, 2205.02836) | 보편 가정(맨해튼) + 시맨틱 | 소프트(시맨틱 확률 가중 법선 손실) | SDF·색·시맨틱 필드 | 무텍스처 벽/바닥 대폭 개선 | 학습된 탈출: 위반 영역은 시맨틱 확률이 낮아져 제약 자체 해제(연속) |
| NeuRIS (ECCV 2022) | 외부 일반 모델(단안 노멀) | 소프트 + **이산 게이팅** | SDF·색 | 얇은 구조 보존 | **채택/기각의 원형** — 다시점 일관성으로 prior 충실도 즉석 평가·불합격 기각 |
| ND-SDF (2024, 2408.12598) | 외부 일반 모델(단안) | 소프트 + **학습된 편차장** | SDF·색·편차장 | 실내 일관 개선 | 이탈 허용을 변수로 승격(연속 모델링) |
| GS4Buildings (2025, 2508.07355) | **외부 자산 — LoD2**(우리와 동일 유형) | 소프트 + 스케줄(초기화+레이캐스트 감독) | 2DGS 전체 자유도 | M3C2 −32.8% 등 | 과평활 한계 자인(귀속=LoD2 해상도; '오류 감지 기제 없음'은 명시 표현이 아니라 부재 사실[원문 확인]), 동적 가중 future work — 딜레마의 추상화판 재현 |
| PolyFit (ICCV 2017) + City3D (RS 2022) | PolyFit: 자체 평면 가설 / City3D: **외부 footprint(하드)** + LiDAR 지붕 평면 | **하드 + 이산 선택**(면별 0/1 정수계획, manifold 하드 제약) | 면별 채택/기각 이산 변수만 | 워터타이트 보장, LoD2 자동화 | **이산 채택/기각의 원형** — 단 가설 집합 밖 복원 불가, City3D의 외부 footprint에는 **기각권 없음**(결함 직결 전파) |

**축 C 판정**: 하드 모수화의 정당성 출처는 대부분 자체 증류(같은 장면의 선행
최적화 산물) — 자산 시효 문제를 애초에 회피. 탈출 장치 스펙트럼: 화소 게이팅
(NeuRIS) → 편차장(ND-SDF) → 시맨틱 재가중(ManhattanSDF) → 두께 슬랙(Frosting) →
스케줄 감쇠(GS4Buildings) → 이산 편입(Flats, 편도) → 가설-선택(PolyFit).
**"틀릴 수 있는 외부 자산 + 하드 모수화 + 이산 채택/기각(방출 포함)" 3요소를
모두 갖춘 전례 미발견.** 최근접 3건이 각 1요소씩 결여: GS4Buildings(소프트),
City3D(기각권 없음), Flats(역방향 방출 없음).

## 5. 축 D — 이시점·낡은 prior·갱신

| 논문(연도·venue·arXiv) | 과거 자산·시차 | 현재 관측 | 충돌 판정 | 판정 후 조치 | 한 최적화 vs 순차 | 정량 |
|---|---|---|---|---|---|---|
| Cross-Temporal 3DGS (AAAI 2026, 2512.00534) | 이전 학습 3DGS(시차 임의) | 희소 새 영상 | 간섭 기반 신뢰도 초기화 | 불변 보존, 변화만 갱신 | 중간형(판정→가중 최적화 반복) | 초록 수치 미기재 |
| LTGS (2025, 2510.09881) | 초기 3DGS(장기 시계열) | few-shot 영상 | 객체 템플릿 수준 판정 | 템플릿 정련 | 순차 | 초록 수치 미기재 |
| CL-Splats (ICCV 2025, 2506.21117) | 이전 3DGS 상태 | 희소 신규 촬영 | 학습형 변화 세그먼트 | 변화 영역만 국소 최적화 | 순차(탐지→국소 최적화) | 초록 수치 미기재 |
| GaussianUpdate (ICCV 2025, 2508.08867) | 과거 3DGS | 현재 영상 | 다단계 변화 유형 모델링 | generative replay 보존 갱신 | 순차·다단계 | 초록 수치 미기재 |
| LT-Gaussian (IV 2025, 2508.01704) | 낡은 GS 지도(주행) | 현재 LiDAR | 기하 잔차형 구조 변화 탐지 | 변화부 표적 갱신 | 순차 3모듈 | 초록 수치 미기재 |
| GaME (2025, 2506.06909) | 온라인 3DGS 지도 | 연속 키프레임 | stale 키프레임 판별 | 낡은 관측 폐기+지도 반영 | 순차(SLAM식) | PSNR +29.7% 등 |
| CL-NeRF (NeurIPS 2023) | 학습 완료 NeRF | 소수 새 영상 | **충돌 인지 지식 증류**(손실 수준) | expert adaptor가 변화부만 적응 | **준(準)공동** — 판정이 목적함수 안 | 초록 수치 미기재 |
| C-NeRF (2023, 2312.02751) | 시점1 NeRF | 시점2 영상(별도 NeRF) | 방향 일관성 차이 | 변화 지도 렌더(보고만) | 순차 | 초록 수치 미기재 |
| 3DGS-CD (2024, 2411.03706) | 변화 전 3DGS | 최소 1장 변화 후 영상 | 렌더 vs 실영상 + EfficientSAM | 3D 변화 마스크·모델 갱신 응용 | 순차 | 정확도 +14%, 18초 |
| GS-DIFF (2026, 2605.07203) | 변화 전 가우시안 | 변화 후 다시점 영상 | **프리미티브 수준** 드리프트 이방성 모델 | 구조 vs 색 변화 구분 보고 | 순차(단위가 표현 원소) | mIoU +17% |
| MapEX (WACV 2025, 2311.10517) | 벡터 HD 지도 — **낡음 3유형 명시 모델링** | 차량 센서 | 학습된 매칭 신뢰 배분 | 기각 아닌 융합(공동 추정) | 단일 네트워크(feedforward, per-scene 아님) | 잡음 지도 +38% |
| TbV (NeurIPS 2021 D&B, 2212.07312) | HD 지도(9개월 노후, 실변화) | 780만+ 영상 | 지도-센서 불일치 학습 분류 | 변화 플래그(보고) | 순차(탐지 전용) | 벤치마크 구축이 기여 |
| LT-mapper (ICRA 2022, 2107.07712) | 과거 LiDAR 세션(일~년 시차) | 신규 LiDAR | 점유 차이 기반 분류 | 변화 분리·지도 갱신 | 순차 모듈러 | 실환경 검증 |
| Qin 2014 (ISPRS JPRS 96) | **LoD2 건물 모델(수년 경과)** | 신규 스테레오 위성영상 | **면(face) 단위** 기하·높이·텍스처 지표 | 변화 건물 보고(재구성 없음) | 순차 | 면 단위 지표 확립 |
| Wu & Vallet (ISPRS Annals 2026) | **older LiDAR** | newer aerial imagery | 양 시점 mesh와 ray tracing 기반 변화 탐지 | changed prior 제거 후 point cloud fusion | **순차 `detect→remove→fuse`** | 프랑스 2개 데이터셋 |
| L2M-Reg (ISPRS J. 2026) | LoD2 model | building LiDAR | plane 대응과 explicit model uncertainty | building별 2D/3D decoupled registration | 사전 정합 모듈 | real-world 5개 데이터셋 |
| GS4Buildings + GeoGS (재등재) | **LoD2/ALS를 GS prior로 직접 사용** | 항공 영상 | **충돌 판정 없음**(prior=참 가정) | 해당 없음(무조건 수용) | 한 최적화이나 충돌 항 부재 | (축 A 참조) |

주변: CLNeRF/WAT(ICCV 2023, 2308.14816) 시계열 벤치마크; Planet-NeRF(2411.02972)
외관 변화만; 다중시기 역사 항공영상 매칭(ISPRS 2021, 2112.04255) — 정합 오차 축의
대표(충돌 판정 없음); GeoInformatica 2025 지형도 갱신(전형적 순차); SceneEdited(2511.15153).

**축 D 판정**: ① 낡은 3D prior + 현재 영상의 공동 최적화는 이 snapshot에서 좁은
후보 공백으로 남지만, Cross-Temporal 3DGS는 “재구성은 어렵지만 prior의 보존/변화
판정은 가능한 영역”의 존재와 반복 갱신 가능성을 강하게 뒷받침한다. 차이는 주로
외부 heterogeneous prior, 정합 불확실성, 데이터 조건과 출력 계약이다. ②
탐지→갱신 **순차 파이프라인이 강한 선행**이며, Wu & Vallet은 older LiDAR와 newer
aerial imagery라는 매우 가까운 반례다. ③ 그러므로 공동/반복 추정은 정의상 기여가
아니라 강한 순차법 대비 검증할 가설이다. **외관 부재**는 확정적 “전무”가 아니라
추가 systematic search가 필요한 보조 축으로 낮춘다.

## 6. 축 E — 강건 제약 처리 이론 계보

| 논문(연도·venue) | 틀릴 수 있는 항 | 처리 기제 | 연속↔이산 이론 진술 | 이산 산출물? | 이식 메모 |
|---|---|---|---|---|---|
| Blake & Zisserman, Visual Reconstruction (1987) | 표면 불연속(이산 line 변수) | 단계적 완화(GNC 원조) | **이산 line process를 소거하면 절단형 강건 비용** — 최초 동치 | 사실상 예 | "이산을 직접 못 푸니 연속족으로 완화" 전략의 원류 |
| **Black & Rangarajan (IJCV 1996)** | outlier 관측·불연속 | 강건 커널 ↔ 보조 가중 변수 | **정리: min ρ(r) ≡ min_{w∈[0,1]} w·r²+Ψ(w)** — 커널↔페널티 사전 제공 | 해석상 0/1 근방 | **"적응 가중 함수=판정 함수" 논증의 문헌상 정본** |
| Sünderhauf & Protzel, Switchable Constraints (IROS 2012) | 거짓 loop closure | latent 스위치 s∈[0,1]을 상태와 **공동 최적화** | 스위치 = "간선 제거" 이산 결정의 연속 완화 명시 | 사실상 예(기각 목록) | prior 항별 스위치 = 우리 채택/기각/유보의 직접 선례. 단 스위치 prior 강도가 새 하이퍼파라미터(딜레마 재출현) |
| SC의 GNSS 적용 (2012–13) | **절대 관측/사전 정보 factor**(다중경로 오염) | factor별 스위치 | (SC 전용) | 예 | "절대계 사전 제약이 틀릴 수 있다"를 factor 스위치로 — ALS/LoD2 prior factor와 구조 동형 |
| Olson & Agarwal, max-mixture (RSS 2012/IJRR 2013) | 거짓 loop closure | **latent 이산 선택**(정상 vs null 가설 argmax) | max 연산 = 명시적 이산 스위치의 근사, null 컴포넌트 = 기각 옵션 | 예 | 유보(abstain)는 제3 컴포넌트로 자연 확장 |
| Agarwal et al., DCS (ICRA 2013) | 거짓 loop closure | 스위치 최적값의 닫힌형 → 연속 재가중 | **스위치 소거 ≡ 잔차 함수 연속 가중** — 둘은 동일물 | 아니오 | "연속 재가중과 스위치 설계는 같은 축의 양 끝이 아니라 동일물"의 실증 |
| Latif et al., RRR (RSS 2012/IJRR 2013) | 거짓 loop closure | **완전 이산 판정**(χ² 일관성 검정, 최대 일관 부분집합) | 완화 아닌 검정 기반 — 반대 극 | **예** | 셀/면 단위 prior 채택 검정으로 이식 가능 |
| Lee et al., EM loop closure (IROS 2013) | 거짓 loop closure | latent 이진 inlier + EM | soft 책임도의 경화 극한 = 이산 분류 | 수렴 후 경화 | 유보 = '사후확률 중간대' 정의 근거 |
| Zach (ECCV 2014; 2018) | BA outlier | 커널 lifting(명시 가중 변수 공동 최적화) | **2018: IRLS·lifting·GNC(smoothing)를 동일 목적함수의 세 전략으로 통일** | 아니오 | 한 논문으로 "세 방식=한 축" 커버, 인용 가치 높음 |
| Barron (CVPR 2019) + Chebrolu (RA-L 2021) | 임의 outlier | 형상 파라미터 α의 연속 커널족, α 공동 추정 | **α 극한이 절단(기각) 커널** — 적응의 극한에 판정형 손실 | 아니오 | "가중을 적응형으로 만들면 판정이 된다"의 실물 |
| **Yang et al., GNC (RA-L 2020)** | 70–80% outlier | Black–Rangarajan 쌍대성 + GNC 스케줄 | **TLS 가중이 μ→∞ 극한에서 w∈{0,1} 수렴 = "Global Outlier Rejection"** | **예** | "연속 재가중의 극한 = 이산 판정"의 가장 명시적 현대 진술 — 결정적 인용 |
| NeRF-W (CVPR 2021) | transient 오염 관측 | 별도 채널 분해 + 불확실성 β | 없음 | 아니오 | "오염을 기각 대신 별도 채널로 흡수" — '과거-시점 채널 분리 유지' 옵션의 선례 |
| RobustNeRF (CVPR 2023) | 학습 영상 distractor | IRLS + trimmed → **패치 이진 마스크** | robust estimation 정식화, "outlier process" 명시 인용 | 예 | Black–Rangarajan 계보의 렌더링 직결 — 단 대상이 관측이지 prior 아님 |
| SpotLessSplats (2024→TOG 2025) | 3DGS distractor | semantic 클러스터 단위 이산 분류 | 판정 단위를 의미 덩어리로 승격 | 예 | 판정 단위=구조 단위(우리: 셀·면)의 선례, GS에서 이산 판정의 학습 안정성 실증 |
| Roessle et al., Dense Depth Priors (CVPR 2022) | **prior 항 자체의 오류** | 불확실성 연속 가중(NLL형) | 없음 | 아니오 | prior 항 연속 가중의 표준형 = 우리가 실측한 딜레마의 설계 지점, 비교 기준선 |
| In Depth We Trust (2026) | 단안 깊이 prior 오류 | 검정 기반 이진 마스크 | 없음(설계 사례) | 예 | prior 항 이산 판정의 최근접 선례 — 단 대상이 모델 예측 prior, '낡은 실측 지도'가 아님. 신규성 경계선 |

**축 E 판정**: ① "적응 가중의 극한 = 이산 판정"은 **양방향 모두 정리 형태로
실재**(Black–Rangarajan 1996 동치; GNC 2020 수렴; DCS 소거; Zach 2018 통일;
Barron/Chebrolu 커널족 극한). 우리 논증은 이 동치 정리의 재진술로 인용 가능.
② 미분 가능 렌더링 적용은 **관측 오염 쪽 계보가 강함**(RobustNeRF→SpotLessSplats),
prior 항은 연속 불확실성 가중이 표준. "낡은 실측 3D prior의 시간적 유효성을
switchable/GNC 계보의 채택·기각·유보로 최적화 내에서 판정하는 GS/NeRF 사례는
확인되지 않음(공백)." 인접 map-update 계열은 이산 갱신을 하되 강건 백엔드
이론과 연결하지 않음.

## 7. 통합 판정

### 7.1 주입 방식 분류 — 문헌과 우리 실험의 위치

| 주입 방식 | 문헌 대표 | 우리 실험 대응 | 상태 |
|---|---|---|---|
| 초기화(시드) | Street Gaussians, DrivingGaussian, GS4Buildings | 레거시 E4/E5 시드 주입 | 오염원 실측 → 재설계에서 제거 |
| 고정 스칼라 손실 | MonoSDF, DN-Splatter, GS4Buildings | E4 w 0.2 / 재설계 w 0.01·0.005 | **딜레마 양끝 실측**(오염 vs 불활성) |
| 스케줄 감쇠 | Chung et al., GS4Buildings 2단 | (미시도 — 문헌도 회피책일 뿐) | 시간축 우회, 판정 아님 |
| 픽셀 신뢰도 연속 가중 | VCR-GauS, CDGS, Roessle, ManhattanSDF | E5 conflict 게이트 exp(−\|r\|/2m), F1 | 시도함 — OX 레벨에서 노이즈 범위 |
| 이산 마스크/게이팅 | NeuRIS, In Depth We Trust, RobustNeRF | (판정전 변화 판정 AUC 0.88~0.96) | 관측·모델-prior 대상만 존재 |
| 하드 구조 모수화 | GaMeS, PlanarSplatting, City3D footprint | **S3: 평면 배열이 기하 소유, 가우시안=색만** | 문헌은 자체 증류·기각권 없음 |
| 이산 가설 선택(채택/기각) | PolyFit 정수계획, RRR, max-mixture | **S3: 점유 이산 3값 두-세계 검정** | 문헌은 자체 가설·SLAM 간선 대상 |

### 7.2 공백 판정 (5축 교차)

현재 snapshot에서 가장 방어 가능한 공백은 다음 네 요소의 교집합이다.

1. 시간적 유효성과 공간 정합이 모두 미확인인 site-specific heterogeneous 3D prior
2. 현재 영상 관측 실패·temporal invalidity·registration error의 구분 또는
   식별 불가능성 판정
3. 위치·기하 자유도별 보정된 source risk와 `image/prior/fusion/abstain`
4. benign case non-degradation과 risk–coverage를 포함한 현재시점 3D 출력 계약

이는 “5축 62편 어디에도 없다”는 완전성 주장 대신, 이번 검색에서 정확히 일치하는
방법을 확인하지 못했다는 **잠정 공백**으로 기록한다. 각 인접 축은 다음과 같다.

- 축 A/B: prior가 현재-일치라 (i) 부재.
- 축 C: 하드 결박은 자체 증류라 (i) 부재, 외부 자산(City3D)엔 기각권이 없어 (ii) 부재.
- 축 D: (i)(ii)의 상당 부분과 강한 순차법이 존재; 공동법의 추가가치는 입증 책임.
- 축 E: (ii)(iii)의 이론은 완비되어 있으나 렌더링 적용은 관측 오염까지만.

부수 공백 2건: **정합 오차(δ) 축**은 시기간 매칭 문헌이 다루되 충돌 판정과 분리;
**외관 부재 축**(과거 자산에 색 없음 → 광도 판정의 조건)은 이번 snapshot에서
명시적 방법을 확인하지 못했으며 추가 검색이 필요하다.

### 7.3 최근접 문헌과의 차이 (related work 1순위)

| 논문 | 공유 요소 | 결정적 차이 |
|---|---|---|
| GS4Buildings (2025) | 항공영상+LoD2 prior+GS(2DGS 백본) — 설정 최동형 | 충돌 개념 없음(prior=참). 과평활 자인(귀속=해상도)·동적 가중=future work[원문 확인], **낡음 축은 논의 부재** — 우리 E4/딜레마의 문헌 대응물(단 그들의 오류 축은 추상화, 시간 축은 공백) |
| GeoGS (2026) | 외부 구조 prior + 항공/거리뷰 영상, global/local 결합과 adaptive weighting | adaptive/local weighting 자체는 차별점이 아님; stale/misaligned prior의 source-risk calibration과 reject/abstain이 남는 비교축 |
| Wu & Vallet (2026) | older LiDAR + newer aerial imagery, 변화 제거 후 융합 | 가장 가까운 강한 순차 baseline; 공동 추정이 필요한지 직접 반증 가능 |
| L2M-Reg (2026) | LoD2 uncertainty를 고려한 building-level registration | registration 축 자체는 차별점이 아님; current image gap과 temporal validity/source decision의 결합이 남음 |
| CL-Splats (ICCV 2025) | 이시점 prior + 새 영상, 이산 스위치, 국소 갱신 | prior가 이전 GS 모델(동종), 판정이 최적화 **밖**(DINOv2 사전 감지 순차) |
| Qin 2014 | LoD2 + 신규 영상 + **면 단위** 충돌 판정 | 탐지 전용(재구성·최적화 없음) |
| LT-Gaussian (2025) | 낡은 지도 vs 현재 관측 판정 + 표적 갱신 | 주행 장면, 동종 GS 지도, 순차 3모듈 |
| City3D (2022) | 외부 자산(footprint) 하드 제약 + 면 이산 선택 | 외부 자산에 기각권 없음(결함 직결 전파), 렌더링 무관 |
| Switchable Constraints / GNC | 틀릴 수 있는 제약의 공동 최적화 내 이산 지향 판정 | SLAM factor graph — 렌더링·3D 재구성 prior 미적용 |

### 7.4 교수 질문("prior-as-loss로 회귀?")에 대한 문헌의 답 — 3문장

1. 문헌에서 prior-as-loss가 좋아진 곳은 **prior가 현재-일치인 설정**뿐이다(같은
   입력 영상에서 추정했거나 동시 취득 — 낡음이 정의상 없음). [축 A·B]
2. 우리 설정과 가장 가까운 GS4Buildings/GeoGS는 구조–세부 결합과 adaptive
   weighting을 이미 다루므로,
   GS4Buildings는 prior를 세게 걸면 실물 디테일(문·창·얇은 구조)이 죽음을
   확인하고 "동적 가중"을 미래 과제로 남겼다[원문 확인] — 그들의 오류 인식조차
   추상화(해상도)까지이고 낡음(시간)은 미착수. **우리 딜레마의 이웃판 재현 +
   시간·정합 유효성과 source arbitration을 추가로 입증해야 한다. [축 A·C·D]
3. 그 과제를 풀려고 가중을 적응형으로 만들면 가중 함수가 곧 판정 변수라는 것은
   Black–Rangarajan(1996) 동치 정리이고, 그 연속 완화의 수렴 극한이 이산 기각
   (GNC 2020)이다 — **즉 (a)의 개선 수순은 '이산 판정을 내장한 최적화'로
   수렴한다.** 단, 판정 변수를 어디에 다는가(자유 가우시안 유지 vs 평면 구조
   소유)는 정리가 아니라 실측이 결정한다(재합성 crispness 열세 실측 → 후자 =
   현 S3). 사다리 위에는 중간 종점 "자유 가우시안 + prior 항 이산 스위치"도
   존재하며 실험 가능한 변형이다. [축 E]

### 7.5 정직한 한계·예상 반론

- **공백 ≠ 성공.** 문헌에 없다는 것은 신규성 근거이지 방법이 작동한다는 증거가
  아니다. S3는 여전히 같은 시험("기존 방법이 안 되는 곳에서의 개선")을 통과해야
  한다 [예정: 3e 이산 1차·N12 시장].
- **공백의 가치 조건.** 공백은 "아무도 필요 없어서 빈 곳"과 "필요·재료가
  최근에야 생긴 곳"으로 갈린다. 후자의 정황은 있다(GS-LoD2 결합 자체가 2025년
  등장, 등장 즉시 GS4Buildings가 가중 문제에 부딪혀 future work 선언; 갱신
  문헌의 탐지→갱신 순차 관행은 미분 가능 렌더링 이전 시대의 유산). 그러나
  공백이 기여가 되려면 **"순차로는 안 되는 조건의 존재"를 실측**해야 한다 —
  아래 순차 반론과 같은 입증 책임이며, 순차 baseline vs 공동의 판별 실험이
  본 실험 설계에 포함되어야 한다.
- **순차 반론**: "CL-Splats처럼 탐지→국소 갱신 순차로 충분하지 않은가?" 우리
  답은 서사 ⑦의 얽힌 미지수 논증(δ를 보정해야 채택 판정 가능, 잔차 귀속 혼합 —
  순차는 오차 전파 재발) [논리]이나, 이는 실험으로 보여야 할 주장이다 [예정].
  CL-Splats뿐 아니라 Wu & Vallet식 변화 제거와 L2M-Reg식 정합을 결합한
  순차판을 직접 대비해야 한다.
- 스위치 변수 설계도 자체 하이퍼파라미터(스위치 prior 강도)를 가진다는 것이
  SC 문헌에 실측되어 있다 — 우리 λ_a 보정 스윕(S3 미결 1)이 같은 문제의식.

### 7.6 검증 유의 (인용 전 원문 확인 목록)

- 에이전트 웹 수집본(2026-08-27, 2026-08-28 addendum). 아래는 2차 출처·초록 수준
  확인이라 인용 전
  원문 대조 필요: Lee et al. EM(IROS 2013)·GNSS-SC 서지 세부, DCS 닫힌형 유도
  (AEROS 서베이 경유 확인), PGSR 다중뷰 게이팅 세부, PlanarSplatting 감독원,
  2DGS DTU 수치(≈0.80, 통용 수치), GeoGS의 세부 실험·ablation, LTGS의 "CVPR 2026
  Findings" venue 표기, 축 D 다수 논문의 초록 수치 미기재 행.
- arXiv ID·venue는 수집 시점 기준. 게재 확정본과 다를 수 있음.
