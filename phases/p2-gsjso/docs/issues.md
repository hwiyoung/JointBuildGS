# P2 (GS-JSO) 이슈 로그 — 실패·예외 기록 (§4 규칙 7)

> 실패·예외는 숨기지 말고 기록 후 보고. P0 이슈는 `phases/p0-audit/docs/issues.md`.
> 신설 2026-06-22 — 이번까지의 P2 및 P0→P2 전이(P0c) 실패를 백필. 시간순(최근 위).

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
