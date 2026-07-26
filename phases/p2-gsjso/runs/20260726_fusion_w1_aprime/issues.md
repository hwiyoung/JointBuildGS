# issues — 20260726_fusion_w1_aprime

판정 필드는 두지 않는다. 상태, 수치, 예외, 처리만 누적한다.

## FUS-W1-APRIME-ATTR-001 — prior 가중치 귀속 정정

- Recorded: 2026-07-26 21:00 KST
- Status: RECORDED BEFORE A′ RESULTS
- `lambda_db=0.5`, `lambda_nb=0.05`는 GS4Buildings 논문 수치가 아니다.
  논문은 prior weight를 공개하지 않고 2단계 scheduling과 “2DGS hyperparameters
  unchanged”만 적는다. 본 run의 귀속은 각각 CityGaussianV2 계열과
  DN-Splatter 계열 범위다. 15k split, 10배 endpoint 감쇠, α estimator도
  이식판 사전등록 선택값이다.

## FUS-W1-APRIME-SMOKE-A-001 — 기존 arm A 지붕 opacity 붕괴와 readout 소멸

- Recorded: 2026-07-26 21:00 KST
- Status: PRESERVED OBSERVATION; A′ 판정 미사용
- 대상: `DEBY_LOD2_42364609`, arm A r1, 30k.
- 기존 full-state의 지붕 geometry proxy에서 opacity 중앙값은 init `0.25`,
  5k `0.00293739`, 10k `0.00269597`, 15k `0.00265593`, 30k
  `0.00265546`이고 모든 checkpoint에서 `opacity>0.5`는 0개다.
- collapse는 distortion 활성 15k보다 앞선 5k부터 관찰된다.
- 기존 alpha-point readout은 25,433점을 만들었으나 분류 class count가
  `{1:2188, 2:23245}`, footprint 내부 class 6이 0, roof density가 0이었다.
  관련 원 산출물과 실패 receipt는 `runs/20260724_fusion_w1/`에 그대로 보존한다.

## FUS-W1-APRIME-PROTECT-001 — seed protection 제거

- Recorded: 2026-07-26 21:00 KST
- Status: PREREGISTERED CONFIG CHANGE
- 기존 arm A의 누적 prune 후보 `10,589,306`개가 모두 seed-lineage 보호되어
  실제 prune 0개였다. A′는 GS4B의 무보호/default dynamics에 맞춰
  `seed_protect=false`, `surface_seed_protect=false`로 고정한다.
- 보호 코드는 삭제하지 않고 config에서 off한다. seed 잔존/opacity/prune은
  관찰 로그일 뿐 intervention에 쓰지 않는다.

## FUS-W1-APRIME-T2-IMPLEMENTATION-001 — 기존 `tsdf` 명칭 경로는 실제 TSDF가 아님

- Recorded: 2026-07-26 21:00 KST
- Status: OPEN PRE-T2 IMPLEMENTATION REQUIREMENT
- 기존 `tum_mob_tsdf_extract.py`는 surface depth 역투영, voxel consensus, SOR로
  점군을 만드는 경로이며 TSDF volume이나 Marching Cubes mesh를 만들지 않는다.
- T2 전에 Open3D ScalableTSDFVolume + triangle mesh 추출 경로를 구현하고,
  기존 arm A checkpoint로 리허설 receipt를 만들기 전에는 T2 PASS로 쓰지 않는다.
