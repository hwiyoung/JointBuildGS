# P2 (GS-JSO) 이슈 로그 — 실패·예외 기록 (§4 규칙 7)

> 실패·예외는 숨기지 말고 기록 후 보고. P0 이슈는 `phases/p0-audit/docs/issues.md`.
> 신설 2026-06-22 — 이번까지의 P2 및 P0→P2 전이(P0c) 실패를 백필. 시간순(최근 위).

## FUS-W1 WIP 재현성 handoff (2026-07-30)

- **처리 상태**: 원 dirty checkout 42개 경로를 외부 snapshot으로 동결하고 disposable clone에서
  byte-identical 복구를 확인했다. 공용 구현, 현재 Fusion 연속 작업, 완료 receipt 결박 항목을 분리해
  처리했으며 세부 정본은 `docs/research/reproducibility/FUSION_W1_WIP_DISPOSITION_20260730.md`다.
- **기술 gate**: 공용 projection/TIN 21, Dense V2–V5 56, panel V6–V7 20, readout 60 — 합계
  **157 PASS / 0 FAIL**. 이 수치는 구현·경로·hash 계약 검증이며 과학적 판정이 아니다.
- **환경 gate 복구**: 첫 정본 `jointbuildgs:dev` 재실행은 Dockerfile에 없던 `laspy`, 이어서 `cjio`를
  각각 fail-closed로 검출했다. `laspy[lazrs]==2.6.1`과 `cjio==0.10.1`을 이미지 계약에 고정하고,
  historical requirements 해시는 source-lock에 유지한 채 현재 config에 명시적 content migration을
  기록한 후 동일 157-test 명령이 `OK`로 종료됐다.
- **완료 결과**: 외부 Dense V5 35개, V6 panel 1개, V7 panel 9개를 다시 해시했다. 상태는
  `INTEGRITY_VERIFIED_EXTERNAL_UNPROMOTED`, `scientific_verdict=null`이다.
- **과거 소스**: 완료 receipt와 readout lineage가 요구하는 40개 정확한 Git blob을 source-lock v4로
  materialize했다. 이후 변경된 현재 `train.py`를 과거 학습 소스로 대체하지 않는다.
- **제외**: superseded V2 payload에 대한 수동 QA 문서 1개는 현재 Git evidence로 승격하지 않고 복구
  snapshot에만 보존했다.

Dense family의 현재 기술 연속점은 V5, A′ 시각 backfill의 현재 기술 연속점은 V7이다. V1–V4와
A′ V5/V6의 개별 역할·회수 기록은 역사 provenance이며, 어느 버전도 별도 승인 없이 과학 정본이 아니다.

## FUS-W1 dense qualitative v1 — 구형 P0 투영 consumer 회수 (2026-07-28)

- **관찰 범위**: v1 `manifest.json`은 패널 **9개**, 패널당 사진 **3개**, 합계 **27개 photo receipt**를
  기록한다. 27/27 receipt에 단일 `locator_z_m`와 투영 footprint vertex 수가 있고, source record
  1건은 `phases/p0-audit/scripts/07_failure_diagnosis.py`를 직접 지목한다. 이 사진 행은 실제 XYZ
  지붕 경계가 아니라 단일 높이 footprint 투영이며, 독립 영상 정합 측정값은 기록돼 있지 않다.
- **보존·사용 제한**: v1 PNG 9개·PDF 1개·overview 1개·manifest/selection audit은 삭제하거나
  덮어쓰지 않았다. run 루트의 `RETRACTED.md`에 사진-풋프린트 첫 행과 `photo_receipts`의 경계·정합
  근거 사용 금지를 기록했다. 나머지 행과 selection 기록은 역사 산출물로만 남기며 재채점하지 않았다.
- **활성 경로 조치**: v1 renderer/config/wrapper/test의 활성 파일 수는 **0개**, 대응 v2
  renderer/config/wrapper/test는 별도 이름과 output namespace를 사용한다. 2026-07-28 v5 구현 회수와
  v6 추가 후 정적 inventory의 P2 panel/qualitative 활성 진입점 **16개**를 검사하는 policy test를 추가해 구형 파일 경로,
  `T7.project_points`, 로컬 `project_points`, 동일 AST 및 FULL_OPENCV distortion 수식 복제를 차단했다.
  역사 재현용 P0 파일 1개는 삭제하지 않았다.
- **v2 첫 렌더 중단과 추가 조치**: 최초 v2 렌더는 raw 원본 사진 `5280×3956`과 adopted COLMAP
  camera `1400×1013`의 크기 불일치를 감지하고 출력 게시 전에 중단됐다. 이미지 입력을 동일 sparse 모델과
  결합된 `phases/p0-audit/data/work/mvs/colmap_dense/images`의 `1400×1013` 픽셀로 교체하고,
  선택된 모든 사진에서 image/camera 크기 완전 일치를 `check`와 렌더 양쪽에서 fail-closed 검증한다.
- **v2 게시 기록**: 대체판은 패널 **9개**, 출력 ledger **13개**를 원자적으로 게시했고 `verify`를 통과했다.
  공용 projector에 빈/singular scene transform fail-closed 검증을 추가한 뒤 기존 bundle을 임시 보관하고
  동일 namespace에 다시 원자 게시했다. `verify`는 이제 manifest의 source ledger **49건**도 실제 파일
  bytes/SHA-256으로 재검사한다. 최종 output-set SHA-256은
  `d6850ae48a2142242143ae3ee0d95041752051b17513d5208cf968245329ab90`이다.

## FUS-W1 A′ 4907182 panel v5 회수와 v6 관찰 (2026-07-28)

- **v5 회수**: `review_v5_backfill` 첫 행은 GroundSurface XY를 한 개 median height에 올린 평면
  locator였으므로 사진–지붕 정합 근거에서 제외했다. 기존 panel/receipt는 덮어쓰지 않고 run 루트
  `RETRACTED.md`에 사용 제한을 기록했다. 오작동 재진입을 막기 위해 untracked 활성 위치의 v5
  renderer/config/wrapper/test **4개는 제거**하고, 정적 policy test가 네 경로의 부재를 확인한다.
- **v4 임시 예외**: v4에도 같은 계열의 flat-height locator가 남아 있으나, 2026-07-28 현재 실행 중인
  `jointbuildgs-fusion-w1-aprime-overnight-v4-repair1.service`가 v4 네 파일과 현재 HEAD를 해시 잠금해
  후속 job의 정성 hook으로 사용 중이다. 실행 중 파일 삭제·수정·HEAD 변경은 본 학습/후처리 큐를
  중단시키므로 이번 변경에서는 v4를 건드리지 않았다. 정적 policy는 flat locator 정의가 이 한 renderer
  밖으로 확산되지 않도록 검사하며, 큐 종료 뒤 layout helper 추출과 v4 네 실행 파일 회수가 필요하다.
- **v6 대체 경로**: 원 visibility NPZ의 ALS class 6 unfiltered XYZ로 supervision과 같은 TIN을 다시
  만들고 incidence-one actual-Z boundary **634개 선분, 31개 component, Z 514.751–526.961 m**와
  k≥3 seed **1,751점**을 공용 explicit-datum projector로 투영했다. 선택 뷰에서 boundary endpoint
  **1,268/1,268**, seed **1,751/1,751**가 유효·in-frame이고 additional pose transform은 0이다.
  M_j·reference GML·output CityJSON은 뷰 선정·자격·crop에 사용하지 않았다.
- **시각 관찰 제한**: v6는 좌표·출처 계약을 fail-closed로 검증하지만 선택 사진에서 target roof가
  가림과 source support 복잡성 때문에 한눈에 식별되지 않는다. 따라서 첫 행은 `REVIEW_NEEDED`이며,
  RGB 독립 roof segmentation/edge 또는 evaluation-only reference boundary를 선정 이후 별도 겹쳐 보는
  관문 없이는 “항상 올바른 정합”으로 보고하지 않는다. 학습·readout·assembly·score는 변경하지 않았다.
- **resolver 열람 공시**: 최종 v6 view ranking·eligibility·crop에는 actual boundary와 seed만 들어가지만,
  재사용한 v3 base resolver는 그 전에 M_j와 evaluation reference를 읽는다. 최종 좌표 dataflow에는
  연결되지 않으며 receipt에 `inherited_read_unused_by_v6_alignment`로 공시했다. v6를 1동 backfill 밖으로
  일반화하기 전에는 first-row-free resolver 분리가 필요하다.

## E5 파일럿 B3 조립 — C001 근접 동 중복 산출 병합 실패 (2026-07-07)

- **증상**: `e5p_gate_20260707_C001` 첫 조립 시 `sparse_r1/run_1` 병합 단계에서
  `Duplicate CityObject id ... DEBY_LOD2_108247350`로 중단.
- **원인**: C001의 근접 동에서는 동별 bbox Roofer 실행이 타깃 동뿐 아니라 이웃 동 CityJSONFeature도 함께 내보냄.
  동별 실행 산출을 전부 병합하면 이웃 동이 여러 번 들어가 중복 id가 생긴다.
- **처리**: Roofer 설정·입력 종류별 튜닝은 바꾸지 않고, `roofer_DEBY_LOD2_xxx_run_n` 산출에서 `xxx` 타깃 동 feature만
  병합하도록 후처리 필터를 추가. 실패 중간 산출은
  `phases/p0-audit/runs/e5p_gate_20260707_C001_failed_duplicate_20260707_0842`로 보존.
- **추가 중단**: 재실행 중 val3dity report 디렉토리 미생성으로 report 저장이 실패해 유효성 열이 비게 되는 문제가 확인됨.
  `val3dity/` 디렉토리를 실행 전 생성하도록 보강하고, 해당 중간 산출은
  `phases/p0-audit/runs/e5p_gate_20260707_C001_failed_val3dity_path_20260707_0847`로 보존.

## D6 survey — 참조 roofType가 관찰 라벨과 불일치 / 곡면 0동 (2026-06-27)

- **참조 `<bldg:roofType>`가 관찰 라벨과 어긋남 (전제 위반, 비-STOP)** — D6 survey 착수 지시는 "곡면 4906969·평지붕
  4906972·복합 42364659" 검증을 요구하나, 권위 속성(AdV Dachform)·LoD2 기하는 정반대로 분류: 4906969=**1000
  Flachdach(평·3 수평면)**, 4906972=**3100 Satteldach(박공·경사 24°/35°)**, 42364659=**1000 평**. 즉 참조 LoD2가
  4906969의 실제 곡률을 담지 않음(coarse 단순화). 코드 증거: GML iterparse로 bid→roofType·RoofSurface 면수
  (11 mob에서 `baselines.json`과 면수 일치 검증). **곡면(3700 Bogendach)은 통제 93동에 0동**(전체 690_53xx 타일쌍
  6동, 통제셋엔 없음). → "곡면군 동별 표" 작성 불가.
- **결정(추정 회피)**: 데이터·산출 전부 존재하므로 **STOP 안 함**. 권위 roofType로 4분류 + 매핑 공개, 과분할은
  동별 분포(93)로 답함. "곡면군" → **경험적 과분할 상위군 + 4906969 명시 강조**로 대체. 결과: 과분할은 유형무관
  광범위(DIM>ref 57/85, 4906969는 20/85위), LiDAR도 과분할(ALS>ref 54/92, med DIM−ALS=0). 본보고 `docs/W_D6_survey.md`.
  (관찰만, 레버·판정=김휘영.)
- **이슈 로그 위치** — 착수 지시는 `docs/issues.md`였으나 해당 파일 없음·§4 규칙은 "해당 phase의 issues 로그" →
  본 P2 phase 로그(`phases/p2-gsjso/docs/issues.md`)에 기록.

## P0c 완전성/조립 재검증 (2026-06-22)

- **SMRF가 ACMP 지붕을 ground로 오분류 (조립실패 주원인)** — generic SMRF(04_classify, DIM용 파라미터)가
  ACMP의 노이즈/저기복 지붕점을 ground(2)로 분류 → footprint overlay가 비-ground만 building(6)으로 올려
  Roofer building 입력이 0–4 pt/m²로 굶음(grdfrac 0.4–0.98). 영향: 조립실패 ~25동이 전처리 artifact.
  진단·우회(force-build) → `docs/experiments/p0_assembly_failure_cause.md`. (해결 아님, 관찰)
- **Roofer overlay PROJ "utm: Invalid latitude"** — footprint geojson에 CRS 미선언 → PDAL filters.overlay가
  UTM 좌표(690000대)를 lon/lat로 해석해 재투영 실패. 해결: `ogr2ogr -a_srs EPSG:25832`로 GPKG 태깅 후 사용
  (`p0c_acmp_forcebuild.json`).
- **SMRF 159M점 과중·저속** — ACMP 풀해상도 712 pt/m²에서 SMRF 형태소 필터가 격자(224k셀)·window18로 느림
  (34분+ 미완). 해결: 0.1 m voxel 다운샘플(→159 pt/m²)로 SMRF/Roofer 처리 가능화. 단 희소동 회복은 하한.
- **ACMP PLY→LAS 변환 시 LAZ 손상** — readers.ply가 `NormalX/Y/Z`를 extra-bytes VLR로 기록 → 잘못된 VLR 길이로
  포인트 오프셋 깨짐("VLR size too large -- flows into point data"). 해결: writers.las를 04_classify식 최소셋
  (minor_version4/dataformat3/lazperf, extra dim 미요청)으로 → 정상.
- **컨테이너 /tmp 미마운트로 산출 유실** — 호스트 /tmp에 쓴 스크립트/산출이 `docker run -v $PWD:...` 컨테이너 내부
  /tmp에서 안 보임. 해결: 마운트된 repo 경로(`results/...`) 아래에 쓰기. (반복 발생 패턴)

## 구현 ② 깊이연결 / E-R3 seeding (2026-06-20~21)

- **clean label ~48 m geoid 오정합** — make_clean_labels가 orthometric GML 메시를 ellipsoidal shift(604)로 배치 →
  GS-surface 커버리지 65.5%. 원인=Munich geoid ~48 m. 해결: `shift_z=556`(=604−48) → 94.3%. (P2-6 결과는 이 버그로
  교란되어 라벨 재생성 + E-R3만 재실행).
- **seed config 키 충돌** — `seed_semantic.yaml`에서 seeding 블록을 `seed:`로 두면 RNG seed(int)와 충돌해
  `set_seed()` launch crash. 해결: `seed_cfg:`로 분리(18-agent 리뷰가 HIGH로 검출).
- **E-R3 carve 기본 z-band 빗나감** — 스크립트 기본 [-20,80]이 GS-local 음수 z(roofs ≈ −24…−40)를 전부 놓침.
  해결: 회복 band `[-55,5]`(er3_diag.json 정확 재현).

## 무텍스처 신호진단 C / ACMP 빌드 (2026-06-21, 일부 보류)

- **ACMMP cmake 실패** — ACMMP가 ACMP에 없는 추가 의존 필요. 해결: 이미지 빌드에서 ACMMP는 best-effort(비치명)로,
  ACMP 단독으로 plane-prior MVS 충족(`Dockerfile.acmp`).
- **colmap2mvsnet_acm.py cv2 누락 + mp.Pool view-selection 데드락** — 해결: python3-opencv 레이어 추가, view-selection
  직렬화(colmap2mvsnet_serial.py).
- **188-view 서브샘플이 per-building 커버리지 starve** — 6/8 footprint n=0(거짓 음성). 원인=뷰 기아. 해결: full-937 ACMP
  사용 시 8/8 footprint 복구. (188은 뷰 부족 artifact)
- **신호진단 C geoid 보고방식 미결 → task 보류** — geoid 상수 보고 vs 재실행 선택 대기(판정=사람). 스크립트는
  `wip/textureless-signal` 브랜치에 분리 보존.

## make-or-break / distortion (2026-06-18~)

- **TUM metric depth에서 distortion 손실 붕괴** — w_distort 1.0/0.1/0.01 모두 collapse/불안정. 해결: fallback
  w_distort=0.0(검증된 base)로 5-arm 학습.
