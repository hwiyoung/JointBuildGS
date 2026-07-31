# Data and Baseline Scope

- Document status: `USER_APPROVED_CANONICAL_DATA_CONTRACT`
- 문서 버전: `C1C5_CANON_v1`
- 작성일: 2026-07-31
- 상태: `GATE S0 EVIDENCE TECHNICAL CLOSED / PROPOSED BLOCKED / HUMAN DECISION PENDING`
- Gate S0 snapshot: exact target bytes verified; scientific readiness remains
  `PARTIAL/MISSING/UNKNOWN`

## 1. 목적과 원칙

이 계약은 입력 prior, reconstruction evidence, Roofer control input, evaluation
reference를 분리한다. 공식 데이터셋에 asset이 존재한다는 사실과 현재 로컬 artifact
backend에 정확한 파일이 검증되어 있다는 사실을 구분한다.

- 공식 TUM2TWIN portal은 동일 도시 공간에 UAS photos, UAS laser scanning,
  image-based photogrammetry, real ALS, LoD2/LoD3 semantic models 후보가 있음을
  지원한다 ([portal](https://tum2t.win/datasets)).
- 저장소의 실제 payload는 `artifacts/manifests/`와
  `JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS`를 통해 해석한다.
- P1에서는 데이터를 다운로드, 이동, 복사, 삭제하거나 재분류하지 않는다.
- P0/geospatial output의 연구 CRS는 `EPSG:25832`이다. source CRS, transformation,
  vertical datum은 별도 기록한다.

## 2. 필요한 TUM2TWIN 자료

| Asset ID | 공식 후보 | 연구 역할 | 공식 source에서 확인 | 로컬 가용성 | 취득 시점 | Accuracy | Density / coverage | Format / CRS |
|---|---|---|---|---|---|---|---|---|
| `IMG_CURRENT` | UAS photographs | C2–C5 current imagery | RTK-georeferenced UAS images, UAS laser campaign 중 취득 ([official](https://tum2t.win/datasets/im-uas)) | `PARTIAL`: exact 962 images; 937 included + 25 excluded ledger | `TO VERIFY` | `TO VERIFY` | building view support `TO VERIFY` | image archive/member hashes verified; CRS `TO VERIFY` |
| `CAM_CURRENT` | OPF/camera/trajectory | MVS/GS poses | official tutorial은 `images.zip`, `opf.zip`, OPF camera parameters/geolocation/sparse reconstruction을 기술 ([official](https://tum2t.win/tutorials/im-gaussiannerf)) | `PARTIAL`: exact OPF; 937 calibrated poses; 25 explicit no-pose exclusions | image archive와 exact files verified | pose uncertainty `TO VERIFY` | building coverage `TO VERIFY` | SfM sparse initialization identity/hash/frame/role `TO VERIFY` |
| `LIDAR_UAS_CURRENT` | UAS laser scanning | `L_upper`, geometry reference 후보 | DJI M350 RTK + Zenmuse L2, nadir/oblique scans ([official](https://tum2t.win/datasets/pc-uas)) | `PARTIAL`: manual/nadir candidates | `TO VERIFY` | `TO VERIFY` | point density/coverage `TO VERIFY` | selection, class, CRS/datum 미동결 |
| `MVS_CURRENT` | UAS image-based scan | C2 baseline only; C3–C5 dense initialization/supervision에는 금지 | Pix4Dmatic 1.58.1 point cloud와 orthophoto ([official](https://tum2t.win/datasets/pc-uasp)) | `PARTIAL`: candidate identified | UAS campaign과 동일성 `TO VERIFY` | `TO VERIFY` | density/coverage `TO VERIFY` | exact image/pose base 미동결 |
| `ALS_EXISTING` | Bavarian real ALS tiles | `P_LiDAR` 후보 | official portal에 real ALS tiles와 download source가 제시됨 ([official](https://tum2t.win/datasets/pc-als)) | `PARTIAL`: four candidate tiles | UAS 대비 시점차 `TO VERIFY` | `TO VERIFY` | density/coverage `TO VERIFY` | C1 independence, CRS/datum/interface 미동결 |
| `LOD1_EXISTING` | TUM2TWIN LoD1 | `P_LoD1` 후보 | 이번 공식 web 조사에서 직접 확인하지 못함 | `MISSING` | `UNKNOWN` | `UNKNOWN` | building coverage `UNKNOWN` | 독립 lineage 미발견 |
| `LOD2_REFERENCE` | Bavarian LoD2 / textured LoD2 | structure reference 또는 roofprint lineage audit | official page는 CityGML LoD2와 stable object IDs를 기술 ([official](https://tum2t.win/datasets/cm-buildings)) | `PARTIAL`: two candidate tiles | acquisition/model vintage `TO VERIFY` | portal 표기의 accuracy 해석 `TO VERIFY` | 대상 building coverage `TO VERIFY` | scoring-only guard와 CRS/datum 미동결 |
| `LOD3_REFERENCE` | manually modeled LoD3 | structure reference 후보 | official page는 LoD2+MLS 기반 수동 LoD3와 per-building download를 기술 | `UNKNOWN` | `UNKNOWN` | review protocol `UNKNOWN` | 대상 수/coverage `UNKNOWN` | CityGML 2.0/CAD 후보 |
| `R_DERIVED_PROTOCOL` | condition evidence에서 동일 code/config로 생성 | 모든 condition의 통제된 Stage 3 derivative | 외부 polygon input이 아님 | P1 후보 `PARTIAL` | method output과 동일 | XY uncertainty `TO VERIFY` | method별 coverage 보고 | polygon/hash와 derivation lineage 필요 |

공식 portal의 “openly available” 표시는 데이터셋 배포 상태에 관한
`SOURCE-SUPPORTED` 사실이다. 현재 checkout 또는 sibling artifact root에 정확한
payload가 있다는 뜻은 아니다.

Gate S0 evidence와 Work Host 교차검토가 확인한 현재 준비도는 다음처럼 축약한다.

- images 962개와 calibrated poses 937개의 차이는 25건의 결정론적 exclusion ledger로
  해소됐다. 다만 C2 MVS가 exact 937 base에서 파생됐다는 hash-linked receipt는 없다.
- C1 UAS LiDAR는 manual/nadir 선택·병합, class 2/6, vertical datum과 registration이 미동결이다.
- C4 Existing ALS는 C1과의 독립성 및 future prior interface가 미동결이다.
- 독립 LoD1은 발견되지 않아 C5가 `MISSING`이다.
- C3–C5 표준 initialization에 사용할 SfM sparse artifact의 identity/hash/frame/role이
  미동결이다. Dense MVS 금지 계약의 `READY`와 execution readiness를 혼동하지 않는다.
- geometry/structure reference ID/version/production lineage와 C1 input-reference
  self-reference evaluation class가 미동결이다.
- `U_target`과 `E_paired`는 `UNKNOWN`이다.

이 상태는 입력 부재를 다른 asset으로 대체할 권한이 아니라 새 Gate S0 remediation
task의 조사 대상이다. 원 evidence와 Work Host 보완 검토는 각각
`preregistration/gate_s0/GATE_S0_EVIDENCE_REPORT_v1.md`와
`preregistration/gate_s0/WORK_HOST_CROSS_REVIEW_v1.md`에 있다.

### 2.1 두 LiDAR asset의 독립 역할

독자는 “LiDAR가 왜 두 개인가?”를 다음처럼 해석해야 한다.

| 구분 | Current UAS/Drone LiDAR | Existing ALS |
|---|---|---|
| Canonical asset | `LIDAR_UAS_CURRENT` | `ALS_EXISTING` |
| 예상 취득 regime | target UAS image campaign과 가까운 drone survey | 기존 regional airborne laser-scanning survey |
| 실험 역할 | `C1_L_upper`의 직접 Roofer baseline | `C4_GS_lidar_prior`의 coarse/incomplete prior |
| reference 가능성 | geometry reference 후보이나 self-reference 위험 있음 | primary reference가 아님 |
| 핵심 질문 | 고품질 current sensor evidence가 Roofer에서 도달하는 성능은? | 낡거나 성긴 기존 point evidence가 current-image GS의 실패를 회복하는가? |

P1 audit의 `DATA_AND_COORDINATE_AUDIT.md`에는 두 자산의 exact file/version, 취득일,
platform/sensor, point density 정의, roof/ground/building coverage, 정확도, classification,
CRS/vertical datum, registration residual, temporal change, 공통 building overlap,
input/reference lineage와 role eligibility를 한 표에서 비교한다. 확인 불가능한 셀은
추정하지 않고 `UNKNOWN`으로 남긴다.

같은 파일 또는 실질적으로 같은 survey derivative를 두 역할에 쓰지 않는다. 감사 결과
두 asset이 시점·품질·coverage regime에서 구분되지 않으면 `C1`–`C4` contrast는
`BLOCKED`이며, ALS를 `P_LiDAR`로 채택하지 않는다.

## 3. Source and derivative lineage

각 asset은 최소 다음 provenance record를 가져야 한다.

| Field | 설명 |
|---|---|
| `asset_id` | 위 canonical asset ID |
| `source_provider` | TUM2TWIN, LDBV 등 |
| `source_url_or_record` | 공식 record/DOI |
| `source_acquisition_start/end` | 실제 센서 취득 시점 |
| `model_or_release_date` | LoD 모델 제작/배포 시점 |
| `source_crs` | horizontal CRS |
| `vertical_crs_or_datum` | ellipsoidal/orthometric/unknown |
| `target_crs` | `EPSG:25832` |
| `transform_pipeline` | axis, unit, geoid/vertical offset 포함 |
| `raw_checksum` | immutable source hash |
| `derivative_script/config/commit` | 재현 lineage |
| `spatial_extent` | bbox/tiles/building IDs |
| `density_accuracy_coverage` | 계산 정의와 단위 포함 |
| `role` | input/prior/control/reference |
| `allowed_conditions` | C1–C5 |
| `leakage_notes` | shared source 또는 derivative 관계 |

Raw input과 canonical result는 explicit retention review 없이 수정하지 않는다.

## 4. Reconstruction condition별 입력 계약

| Condition | Current images | Current MVS | Current UAS LiDAR | Existing ALS prior | Existing LoD1 prior | Roofprint protocol | Evaluation reference |
|---|---:|---:|---:|---:|---:|---:|---:|
| `C1_L_upper` | 아니오 | 아니오 | reconstruction input | 아니오 | 아니오 | `R_derived` protocol | score only |
| `C2_MVS` | MVS 생성 source | reconstruction input | 아니오 | 아니오 | 아니오 | `R_derived` protocol | score only |
| `C3_GS_image` | training input | dense MVS geometry/depth/normal 입력 금지 | 아니오 | 아니오 | 아니오 | `R_derived` protocol | score only |
| `C4_GS_lidar_prior` | training input | C3와 같은 image base; dense MVS 입력 금지 | 아니오 | prior only | 아니오 | `R_derived` protocol | score only |
| `C5_GS_lod1_prior` | training input | C3와 같은 image base; dense MVS 입력 금지 | 아니오 | 아니오 | prior only | `R_derived` protocol | score only |

`C4`와 `C5`를 한 arm으로 합치지 않는다. Evaluation reference는 학습 loss,
initialization, crop, early stopping, hyperparameter selection에 사용하지 않는다.

`C3`–`C5`의 공통 GS base는 current RGB images와 camera calibration/poses를 사용한다.
표준 GS가 요구하는 SfM sparse points는 initialization support로 허용하되 source와
역할을 기록한다. Dense MVS point cloud, rendered/estimated dense MVS depth 또는
normal을 loss/initialization prior로 넣지 않는다. 이를 넣어야 한다면 `Image-only GS`
명칭과 C2/C3 contrast를 변경하는 별도 사용자 결정이 먼저 필요하다.

`C2_MVS`도 원칙적으로 C3–C5와 같은 Gate S0 동결 image/camera ledger에서 생성한다.
기존 vendor MVS가 다른 image subset, pose solution 또는 preprocessing을 사용했다면
그 차이를 숨기지 않고 sensor-processing bundle baseline으로 표시하며 C2-vs-C3의
직접적인 method-only 해석을 제한한다.

## 5. `L_upper`와 `P_LiDAR` 구분

| 차원 | Current UAS/Drone LiDAR (`L_upper`) | Existing ALS (`P_LiDAR`) |
|---|---|---|
| 목적 | sensor-evidence experimental upper baseline | reusable existing asset prior |
| 기대 품질 | current/high-quality 후보 | historical, sparse, incomplete 가능 |
| 사용 위치 | Roofer baseline branch | C4 GS initialization/regularization 후보 |
| reference 지위 | ground truth 아님 | reference 아님 |
| 동일 파일 허용 | 원칙적으로 아니오 | `L_upper`와 다름을 입증 |
| 필수 감사 | currentness, accuracy, density, coverage | date gap, incompleteness, alignment, overlap |

같은 point cloud를 label만 바꾸어 두 역할에 사용하는 것은 허용하지 않는다.

## 6. `P_LoD1` 가용성과 허용 정보

허용 정보:

- building footprint/extent
- coarse height envelope
- vertical wall structure
- building/non-building spatial support

금지 정보:

- 실제 roof slope, ridge, hip
- roof-plane 수, boundary, adjacency
- LoD2 roof topology
- RoofSurface Z 또는 roof type/semantic evaluation label

현재 공식 TUM2TWIN building-model page에서 확인되는 것은 LoD2/LoD3이며 직접
LoD1 asset은 확인되지 않았다. 다음 세 경우를 구분한다.

1. **독립 existing LoD1이 존재:** 가장 강한 후보.
2. **독립 cadastral footprint+height에서 LoD1 생성:** lineage와 uncertainty를 기록.
3. **evaluation LoD2를 단순화해 LoD1 생성:** 현행 `AGENTS.md`와 이 charter의
   GT-separation 원칙상 primary honest arm에는 **사용 금지**이다. LoD2 Z에서 만든
   height envelope도 금지 정보다. Root policy가 별도 승인 절차로 명시적으로 바뀌지
   않는 한 leakage diagnostic 이외의 후보가 될 수 없다.

## 7. Reference 계약

### Geometry reference 후보

Current UAS LiDAR를 우선 검토한다. 센서 오차, coverage hole, facade/roof sampling,
registration uncertainty를 함께 보고한다. `L_upper`와 같은 source를 reference로
사용하더라도 reconstruction input과 score 계산의 자기비교 위험을 명시한다.

### Structure reference 후보

검수된 LoD2/LoD3 roof surfaces를 검토한다. geometry reference와 시점, object ID,
roof topology가 일치하는지 확인한다. reference 자체의 roof-plane 분할 convention을
평가 protocol로 오인하지 않는다.

### Reference separation

- geometry score와 structure score는 reference ID/version을 각각 가진다.
- model 제작에 UAS LiDAR, ALS, footprint가 사용되었는지 계보를 조사한다.
- shared source가 있으면 독립 검증이 아니라 conditional evaluation임을 보고한다.

## 8. Roofprint protocol

모든 condition에 reference-independent한 `R_derived` roofprint protocol을 적용해
surface evidence의 Roofer manufacturability를 비교한다. Roofer 공식 문서는
point cloud와 2D roofprint polygon을 입력으로 요구한다
([official docs](https://innovation.3dbag.nl/roofer/)).

현행 `AGENTS.md`와 `00_RESEARCH_CHARTER.md`에 따라 Stage 3는 외부 roofprint를
사용하지 않는다.

| Protocol | P1/P2–P4 지위 | 설명 |
|---|---|---|
| `R_derived`: point-evidence-derived roofprint | `AUTHORITATIVE PRIMARY` | 모든 방법에 같은 derivation algorithm/parameter를 쓰되 polygon은 방법별 evidence에서 생성; surface와 roofprint error가 결합되는 한계를 함께 보고 |
| `R_ext`: 공통 external roofprint | `OUT_OF_SCOPE / NOT EXECUTED` | 통제 진단 후보이나 root policy에 대한 별도 명시 승인과 정본 변경 전에는 사용 금지 |

Reference-derived `GroundSurface` XY 사용은 기존 승인잠금의 지정 C001/E5 예외를
넘어 자동 허용되지 않는다.

## 9. Common eligible building set

두 모집단을 구분한다.

- `U_target`: P2 Gate S0에서 outcome 없이 동결한 AOI boundary 안에서 current
  imagery와 stable building ID가 있는 모든 candidate building. 데이터 coverage와
  외적 타당성의 분모이다.
- `E_paired`: `U_target` 중 C1–C5를 모두 시도할 수 있고 공통 좌표계에서 reference
  scoring이 가능한 paired experiment universe이다.

건물은 threshold와 method outcome을 보기 전에 다음 조건으로 `E_paired`
eligibility를 정한다.

1. common stable building ID가 모든 필요한 asset에 매핑된다.
2. current imagery에 정해진 최소 view support가 있다.
3. `L_upper`, MVS, ALS/LoD1 prior의 coverage status를 계산할 수 있고, P2 Gate S0에서
   outcome 없이 동결한 minimum input-availability rule을 C1–C5 모두 만족한다.
   미충족 건물은 `U_target → E_paired` exclusion으로 사유를 보고한다.
4. 모든 condition에 같은 `R_derived` derivation code/config를 쓰며 method별
   polygon/hash를 보존한다.
5. geometry/structure reference가 score 가능하고 uncertainty가 기록된다.
6. 모든 coordinate transform과 vertical datum이 검증된다.
7. split assignment가 building/model 결과 전에 동결된다.
8. input/reference leakage class가 판정된다.
9. 실제 demolition/new construction 등 change building은 RQ6용으로 미리 flag한다.
10. method failure는 사후 exclusion하지 않고 G0 failure로 유지한다.

`U_target → E_paired` 흐름은 building ID별 포함 여부, 제외 사유, asset별 coverage를
남긴다. Prior 또는 reference 부재로 `E_paired`에서 제외된 건물을 조용히 삭제하지
않고, `U_target` 대비 실험 coverage와 적용 가능 범위의 한계로 보고한다.

## 10. Split과 held-out의 의미

`PROVISIONAL` 기본안:

| Split | 언제 접근하는가 | 용도 |
|---|---|---|
| spatially disjoint pilot/development | P2–P3 | pipeline 안정화, 빠른 실패 분석, method 개발 |
| validation | P2–P3 | adapter·threshold·criterion·hyperparameter 선택과 blind review |
| held-out building test | P4에서 최초 접근 | 동결된 C1–C5의 최종 일반화 평가 |

**Held-out building**은 건물 또는 공간 group 전체를 pilot/validation에서 떼어 두어,
P2 threshold와 P3 method/loss/schedule을 정할 때 결과를 보지 않는다는 뜻이다.
P4 primary에서는 held-out test에 배정된 모든 건물에 C1–C5 전체 condition matrix를
실행한다. 이는 전체 eligible population을 뜻하지 않는다.

**Held-out view**는 같은 pilot/validation building 안에서 GS 학습에 사용하지 않은
camera image이며 rendering diagnostic에 사용할 수 있다. held-out building test와
동일한 표현으로 해석하지 않는다.

`EXHAUSTIVE_PARTITION`에서는 P2/P3의 development+validation 결과와 P4 held-out
결과를 합쳐 `E_paired` 전 건물 matrix를 만든다. `STRATIFIED_SAMPLE`이면 P4 primary
결과와 해석을 잠근 뒤 필요할 경우 `E_paired` 전수 rerun을 supplementary coverage
atlas로 만들 수 있다. 이는 threshold, 방법 선택 또는 primary claim을 변경하는
근거가 아니다.

동일 building/roof complex의 인접 part, 동일 source model에서 파생된 geometry,
공간 autocorrelation이 split을 가로지르지 않도록 group split을 검토한다. 수량과
경계는 P1 data audit 뒤 P2에서 결과를 보기 전에 결정한다.

### 10.1 전수 우선, 표본 fallback

1. P1 감사는 `U_target`/`E_paired`를 동결하지 못했다. Gate S0 preparation은 후보 수,
   coverage, 공간 group, missingness와
   building×C1–C5 예상 compute/storage 비용을 AOI 후보별로 산출한다. candidate
   AOI는 imagery/UAS LiDAR/ALS/LoD1/reference footprint의 교집합, stable-ID
   coverage, 연속성, 면적과 비용으로만 기술하며 performance run은 하지 않는다.
2. P2의 첫 baseline 결과 전 Gate S0에서 `EXHAUSTIVE_PARTITION` 또는
   `STRATIFIED_SAMPLE`을 사용자 승인으로 선택하고 exact AOI polygon/hash를 함께
   동결한다. AOI 선택에 roof type, 평가 label 또는 method result를 쓰지 않는다.
3. 기본 우선안 `EXHAUSTIVE_PARTITION`은 `E_paired` 전 건물을
   development/validation/held-out에 배정한다. P2/P3와 P4 결과를 합치면 최종적으로
   `E_paired` 전체의 C1–C5 matrix가 된다.
4. `STRATIFIED_SAMPLE`은 전수가 비용·시간·가용성상 불가능할 때만 허용한다.
   spatial block, current-image observation support, ALS coverage/density/temporal
   gap, 비-GT input-side size/height proxy를 사용한다. roof type, LoD2
   `RoofSurface`, semantic evaluation label, method result는 split 변수로 금지한다.
5. 표본 수는 paired binary endpoint의 목표 신뢰구간 정밀도 또는 detectable net
   PASS change/검정력, 예상 attrition과 compute budget으로 정한다. exact 식과
   가정은 P2 protocol에서 동결한다.
6. split manifest에는 `U_target`/`E_paired` IDs, split IDs, spatial group,
   AOI polygon/hash, seed/algorithm, strata, source hashes, inclusion/exclusion
   reason, sample-size rationale, compute/storage ceiling을 기록한다.

P3는 development에서 C4/C5를 개발하고 validation에서 final method를 선택·동결한다.
그 뒤 frozen C4/C5를 development+validation 전 건물에 적용한다. C1/C2는
exact-compatible P2 결과, C3는 hash-compatible frozen result 또는 protocol-matched
rerun을 사용하여 이 pool의 C1–C5 matrix를 완성한다.

P4의 “확장”은 결과를 보고 건물을 추가하는 과정이 아니라, P2에서 동결한 held-out
membership을 처음 여는 과정이다. Sampled fallback에서 전수 coverage가 필요하면
P4 primary 잠금 뒤 `E_paired` census를 별도 실행한다. 이 census가 없으면
`E_paired` 전체 coverage 또는 전수 확장을 주장하지 않는다.

## 11. Leakage risk register

| Risk | 예 | 영향 | 완화 | 상태 |
|---|---|---|---|---|
| prior–reference shared model | LoD2를 단순화해 LoD1 prior 생성 후 같은 LoD2로 score | roof extent/Z/topology 누출 | C5 honest arm에서 금지; 별도 leakage diagnostic도 명시적 승인 필요 | `PROHIBITED_PRIMARY` |
| roofprint–reference shared XY | LoD2 GroundSurface에서 roofprint 파생 | planimetric score와 topology 조건화 | 독립 footprint 우선, shared XY 공개 | `TO VERIFY` |
| `L_upper`–geometry reference identity | 같은 UAS LiDAR로 reconstruct/score | optimistic upper baseline | upper는 self-reference임을 표시하거나 독립 TLS/LoD3 검토 | `TO VERIFY` |
| MVS derivative reuse | official Pix4D MVS로 pose/GS init/score 모두 사용 | 비교 독립성 저하 | role별 허용을 동결 | `TO VERIFY` |
| split leakage | 같은 building parts가 validation/test에 분산 | threshold overfit | group/spatial split | `PROVISIONAL` |
| held-out peeking | P4 held-out building 결과를 P2/P3 method·threshold 결정에 사용 | 선택 편향 | P4 전 접근 금지, criterion/method/selection rule 사전 동결 | `FROZEN` 원칙 |

## 12. Baseline 해석 제한

- `C1_L_upper` 성능은 theoretical maximum이 아니다.
- `C2_MVS` 실패는 MVS 일반의 보편적 한계가 아니라 지정 pipeline/data의 결과이다.
- `C3_GS_image`는 prior effect의 기준선이며, renderer/backbone이 다르면 비교가
  무효화될 수 있다.
- C4/C5 개선은 prior 자체, initialization, regularization, extraction 변화 중
  어디에서 생겼는지 G-native chain으로 분리한다.
- 모든 arm의 roofprint, terrain, class 2/6, crop/buffer, density normalization 및
  Roofer parameter를 같게 하거나 차이를 명시한다.

## 13. TO VERIFY checklist

### Data and time

- [ ] exact file paths/checksums와 manifest resolver
- [ ] image/OPF/camera/trajectory version
- [ ] UAS image와 LiDAR co-acquisition date
- [ ] UAS/Drone LiDAR와 ALS의 exact file/version 및 derivative independence
- [ ] platform/sensor, density, accuracy, classification, coverage, registration 비교표
- [ ] photogrammetric point-cloud software/config/version
- [ ] ALS acquisition date와 UAS 대비 temporal gap
- [ ] LoD1 실제 파일, provider, creation lineage
- [ ] LoD2/LoD3 production date와 source sensors

### Geometry and coordinates

- [ ] source CRS, axis order, unit
- [ ] target `EPSG:25832` transform
- [ ] vertical datum/geoid/offset
- [ ] cross-modal residual과 scale
- [ ] point density, roof coverage, nodata 정의
- [ ] common ID mapping과 duplicate/multipart 규칙

### Roles and leakage

- [ ] `L_upper ≠ P_LiDAR`
- [ ] LoD1에 roof slope/topology가 없음
- [ ] geometry/structure reference separation
- [ ] `R_derived` code/config와 method별 polygon/hash
- [ ] prior/reference/roofprint shared provenance
- [ ] existing C001/E5 exception 범위 비확장

### Repository support

- [ ] actual loaders/parsers/configs
- [ ] raw immutability와 external artifact paths
- [ ] Docker reproduction
- [ ] storage/runtime/memory estimates

## 14. Consistency review

- `RESOLVED`: no-external-roofprint 정본을 유지하며 `R_derived`만 primary.
  `R_ext`는 별도 정책 승인 전까지 비실행 범위 밖이다.
- `MAJOR`: 공식 source에서 직접 LoD1을 확인하지 못함.
- `RESOLVED BY DEC-P1-008`: TUM2TWIN 중심 C1–C5가 현재 data-role 정본이며
  `docs/evidence/archive/pre_c1c5_research/EXPERIMENT_PLAN.md`의 dataset-role은 역사 기록이다.
- `PARTIAL`: Gate S0 표적 11개 payload는 Experiment Host에서 exact bytes로 검증됐다.
  다만 독립 LoD1, C3–C5 sparse initialization, condition별 변환·registration·coverage
  lineage는 아직 exact payload/derivative 계약과 연결되지 않았다.
- `TO VERIFY`: source/target CRS와 vertical datum. 연구 output은 `EPSG:25832`를
  유지하지만 source 변환을 추정하지 않는다.
