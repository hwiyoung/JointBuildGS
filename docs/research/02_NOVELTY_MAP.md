# Novelty Map

- Document status: `USER_APPROVED_PHD_METHOD_FRAMING / E1E6_UNCHANGED`
- 문서 버전: `E1E6_CANON_v3 + PHD_METHOD_ADDENDUM_v1`
- 문헌 snapshot: 2026-08-28
- 상태: `PROVISIONAL EVIDENCE / CURRENT E1–E6 + PHD METHOD DESIGN REFERENCE`
- 원칙: 문헌 사실, 본 연구의 해석, 제안 기여, 미확인 사항을 분리한다.

## 1. Evidence labels

- `SOURCE-SUPPORTED`: 인용한 논문·공식 문서가 직접 지원
- `INFERENCE`: 출처들을 바탕으로 본 연구가 도출한 해석
- `PROPOSED CONTRIBUTION`: 아직 실험으로 입증되지 않은 본 연구의 설계
- `TO VERIFY`: full-text·코드·데이터·추가 systematic search가 필요

이 문서는 선행연구의 완전한 systematic review가 아니다. 따라서 “최초”, “유일”,
“기존에 없음” 같은 배타적 신규성 표현을 사용하지 않는다.

`DEC-P1-025`의 박사학위 상위 문제정의는 기존 E1–E6를 소급 변경하지 않는다.
아래의 새 방법론 비교군과 공백은 향후 설계를 위한 addendum이며, 실행·threshold·
confirmatory claim을 승인하지 않는다.

## 2. 연구군별 지도

| 연구군 / 대표 출처 | 입력 | 출력 | Prior / 최적화 | 평가 대상 | downstream LoD2/city model | 이미 지원되는 사실 | 남은 문제 / 본 연구와의 잠재 차이 | 상태 |
|---|---|---|---|---|---|---|---|---|
| Photogrammetric PC building modeling — [Xiong et al. 2014](https://doi.org/10.5194/isprsannals-II-3-197-2014) | MVS photogrammetric 또는 LiDAR point cloud | LoD2 building geometry | plane/structure boundary 기반 global model | roof structure와 geometry | 예, LoD2 모델 | MVS가 조밀해도 잡음으로 한 roof plane이 다분할되고 topology graph가 불안정할 수 있음 | 최신 GS와 같은 building set에서 Roofer gate 전파는 다루지 않음 | `SOURCE-SUPPORTED` |
| Point-cloud-driven city reconstruction — [City3D](https://arxiv.org/abs/2201.10276) | airborne LiDAR + footprint | compact watertight polygonal buildings | inferred vertical planes, hypothesis-and-selection, topology constraints | geometry RMSE, robustness, runtime | building surface model | 항공 LiDAR에서 wall이 누락될 수 있어 building-specific constraints가 유용함 | existing prior + current images의 학습 결합이나 GS-native failure chain은 아님 | `SOURCE-SUPPORTED` |
| Roofer/3DBAG — [official docs](https://innovation.3dbag.nl/roofer/) | point cloud + 2D roofprint | LoD1.2/1.3/2.2, CLI는 CityJSONSeq | automatic roof reconstruction, tunable parameters | success, density, nodata, RMSE, roof planes, val3dity 등 | 예 | 정확한 Roofer 입력은 roofprint와 point cloud이며 output serialization을 확인해야 함 | JointBuildGS는 E1–E6에 동일한 `R_shared` GroundSurface XY를 제공하고 evidence 차이를 비교 | `SOURCE-SUPPORTED` |
| Image-only 2DGS surface reconstruction — [Huang et al. 2024](https://doi.org/10.1145/3641519.3657428), [official code](https://github.com/hbb1/2d-gaussian-splatting) | posed multi-view images | 2D Gaussian surfels, rendered depth, mesh | depth distortion + normal consistency; depth fusion/TSDF mesh path | rendering, Chamfer/F-score 등 | 확인되지 않음 | planar disks와 geometry regularization으로 surface reconstruction을 직접 목표화 | city-model manufacturability와 building-level PASS는 별도 검증 필요 | `SOURCE-SUPPORTED` |
| Depth/normal-prior GS — [DN-Splatter](https://arxiv.org/abs/2403.17822) | images + depth/normal cues | Gaussians와 mesh | depth regularization, local smoothness, normal cues | indoor geometry와 rendering | 확인되지 않음 | depth/normal supervision이 ill-posed/textureless geometry를 보완할 수 있음 | urban aerial buildings, existing asset currentness, Roofer output은 범위 밖 | `SOURCE-SUPPORTED` |
| LiDAR-guided GS — [LI-GS](https://arxiv.org/abs/2409.12899) | co-acquired LiDAR scans + RGB | Gaussian surfels와 mesh | LiDAR-derived plane-constrained GMM initialization/normalization/density control | accuracy, completeness, Chamfer, F1, rendering | 확인되지 않음 | LiDAR를 initialization·optimization·mesh extraction 전반에 사용 가능 | 본 연구의 historical/incomplete LiDAR prior와 current-image 분리 시나리오는 같지 않음 | `SOURCE-SUPPORTED` |
| Building-model-prior GS — [GS4Buildings](https://doi.org/10.5194/isprs-annals-X-4-W6-2025-249-2025) | images + low-level LoD2 semantic building model | building surface reconstruction / Gaussians | LoD2에서 Gaussian initialization과 depth/normal prior 생성 | completeness, geometric accuracy, compactness | full-text downstream city-model 재생성은 `TO VERIFY` | LoD2 semantic model을 직접 geometry prior로 쓰는 prior-guided GS가 이미 제안됨 | 본 연구가 LoD1이라고 해도 생성 계보가 LoD2이면 차별성과 leakage가 약해질 수 있음 | `SOURCE-SUPPORTED` + `TO VERIFY` |
| GeoGS — [official article](https://www.sciencedirect.com/science/article/pii/S0924271626003588) | aerial images + low-LoD building model + visual-foundation depth | geometry-aware building GS | global structural anchor와 local detail을 분리하고 두 단계·adaptive weighting으로 결합 | urban building geometry/rendering | building reconstruction | “영상이 약한 곳에 prior를 더 쓰고, 구조와 세부를 서로 보완한다”는 아이디어는 이미 강한 인접선행에 속함 | prior의 시간적 유효성·정합오차·명시적 reject/abstain과 국소 최소위험 source arbitration은 별도 검증 필요 | `SOURCE-SUPPORTED` + `TO VERIFY` |
| Selective depth-prior GS — [In Depth We Trust](https://arxiv.org/abs/2604.05715) | images + estimated depth prior | 3DGS geometry | ill-posed geometry를 식별해 선택적으로 depth regularization | geometry/rendering | 확인되지 않음 | “불확실한 영상 영역만 prior로 보완”은 독립 기여로 주장하기 어려움 | 동일 장소의 외부 historical 3D와 temporal/registration conflict를 판정하는 문제는 아님 | `SOURCE-SUPPORTED` |
| Cross-temporal GS update — [Cross-Temporal 3DGS](https://ojs.aaai.org/index.php/AAAI/article/view/37217) | previous 3DGS + sparse current images | updated 3DGS | cross-temporal consistency와 selective update | rendering/current model preservation | 확인되지 않음 | 이전 3D 표현과 현재 영상을 함께 쓰는 문제 및 selective update가 이미 성립함 | prior가 동종 GS가 아닌 ALS/LoD/DSM이고, 정합·시효·source risk를 함께 추정하는지 구분 필요 | `SOURCE-SUPPORTED` + `TO VERIFY` |
| Image–LiDAR change update — [Wu & Vallet 2026](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.html) | older LiDAR + newer aerial imagery | changed-area-removed/fused point cloud | 양 시점 mesh와 ray tracing으로 변화 탐지 후 changed prior 제거·융합 | change detection/update | map/point-cloud update | 이질적 old LiDAR와 current imagery의 `detect→remove→fuse` 순차 해법이 존재함 | 본 연구의 강한 순차 baseline이며, 공동/반복 추정은 이를 이길 때만 정당화됨 | `SOURCE-SUPPORTED` |
| LiDAR–LoD2 registration — [L2M-Reg](https://www.sciencedirect.com/science/article/pii/S0924271626000560) | building LiDAR + LoD2 model | registered building data | plane 기반 2D/3D decoupled registration과 model uncertainty | five real-world datasets | LoD2 alignment | building별 prior 정합과 model uncertainty 자체도 이미 연구축임 | 현재 영상의 관측 공백·시간적 유효성·출처 선택과 결합한 문제는 별도 | `SOURCE-SUPPORTED` |
| Low-LoD model refinement — [MLS2LoD3](https://arxiv.org/abs/2402.06288) | low-LoD building model + MLS | semantic LoD3 building model | low-LoD geometry를 point-cloud evidence로 refine | LoD3 facade reconstruction | 예 | coarse semantic building model을 새 sensor evidence로 refine하는 연구방향이 이미 존재 | GS, aerial current images, Roofer LoD2.2, usable PASS 전이는 별도 질문 | `SOURCE-SUPPORTED` |
| Roof-plane benchmark — [ISPRS evaluation protocol](https://www.isprs.org/resources/datasets/benchmarks/UrbanSemLab/results/EvaluationBuildingReconstructionDocument/EvaluationBuildingReconstruction.html) | reconstructed/reference roof planes | correspondence, error maps, aggregate metrics | asymmetric overlap matching | per-area, per-plane, per-building completeness/correctness/quality, topology, RMS | 평가 protocol | roof-plane matching과 over/undersegmentation을 분리할 수 있음 | 예시 overlap threshold를 보편적 production PASS로 그대로 이식할 근거는 없음 | `SOURCE-SUPPORTED` + `INFERENCE` |
| CityJSON / geometry validation — [CityJSON validation](https://www.cityjson.org/tutorials/validation/), [val3dity](https://val3dity.readthedocs.io/) | CityJSON/CityJSONSeq geometry | validation reports | schema/internal consistency + ISO 19107 geometry validity | syntax, semantics arrays, indices, 3D primitive validity | 예 | schema/semantic validation과 geometric validity는 다른 gate로 분리해야 함 | 유효성 통과만으로 roof fidelity/accuracy를 보장하지 않음 | `SOURCE-SUPPORTED` + `INFERENCE` |
| TUM2TWIN — [dataset paper](https://doi.org/10.1016/j.isprsjprs.2025.12.013), [official portal](https://tum2t.win/datasets) | multimodal images, point clouds, semantic models | benchmark assets | 해당 없음 | multiple downstream tasks | LoD2/LoD3 assets 존재 | 같은 도시 공간의 UAS imagery/LiDAR, photogrammetry, ALS, semantic models 후보를 제공 | 실제 시점·coverage·공통 ID·LoD1·로컬 파일은 별도 감사 필요 | `SOURCE-SUPPORTED` + `TO VERIFY` |

## 3. 가장 가까운 prior-guided 방법과의 구분

### 3.1 문헌이 직접 지원하는 내용

GS4Buildings는 low-level **LoD2 semantic 3D building models**에서 Gaussian을
초기화하고 planar geometry로 depth/normal maps를 만들어 최적화에 사용한다
([paper](https://doi.org/10.5194/isprs-annals-X-4-W6-2025-249-2025)).
따라서 “building-model prior를 GS에 넣는 발상 자체”는 본 연구의 신규성으로 주장할
수 없다. `SOURCE-SUPPORTED`.

GeoGS는 같은 계열에서 global structural anchor와 local detail을 분리하고 adaptive
weighting을 사용한다. In Depth We Trust는 ill-posed 영역을 찾아 depth prior를
선택적으로 적용한다. 따라서 다음 수준만으로는 박사학위의 중심 기여가 되기 어렵다.

- 영상 confidence에 따라 prior weight를 조정한다.
- 영상이 약한 곳에서 prior를 더 쓴다.
- LoD/ALS로 전역 구조를 잡고 영상으로 상세를 만든다.

본 연구가 검증할 남은 교집합은 **외부 site-specific prior의 시간적 유효성과 공간
정합이 모두 미확인인 상태에서, 변화·정합오차·현재 영상 관측 실패를 구분하거나
식별 불가능으로 판정하고, 위치·자유도별 예상 기하위험에 따라 image/prior/fusion/
abstention을 결정하는 것**이다. `PROPOSED CONTRIBUTION`.

### 3.2 제안된 차이

| 축 | GS4Buildings에서 확인된 내용 | JointBuildGS 새 설계 | 판정 |
|---|---|---|---|
| model prior detail | LoD2 semantic building model | heterogeneous ALS/DSM/LoD를 source별 오차모형으로 분리 | 단순 prior 종류 추가가 아니라 risk calibration이 기여 후보 |
| LiDAR 시나리오 | 핵심 prior가 LoD2 model | historical/incomplete LiDAR도 temporal·registration validity 미확인 | `PROPOSED CONTRIBUTION` |
| currentness | prior-guided robust reconstruction | currentness eligibility와 geometric authority를 분리 | 실제 change case와 독립 reference 없으면 주장 불가 |
| source decision | schedule/weight 중심 | `I/P/F/abstain`의 국소·자유도별 최소위험 선택 | `PROPOSED CONTRIBUTION` |
| registration | method 입력 정합 전제 또는 별도 처리 | registration `δ`와 validity/source decision의 상호의존 추정 | L2M-Reg 및 순차법보다 추가가치 검증 필요 |
| downstream | GS building reconstruction | exact Roofer input과 LoD2.2 gate | full GS4Buildings 평가범위 확인 후 차이 확정 |
| endpoint | completeness/accuracy/compactness | building-level usable PASS와 transitions | `PROPOSED CONTRIBUTION` |
| failure localization | 논문 전체 확인 필요 | G-native→extraction→Roofer→LoD2 | `PROPOSED CONTRIBUTION` |
| output contract | semantic textured mesh의 독립 acceptance는 확인 필요 | Roofer/LoD2와 semantic textured mesh의 O/X를 독립 정의하고 네 joint cell을 보고 | `PROPOSED CONTRIBUTION` |

### 3.3 신규성 위험

1. `P_LoD1`을 official LoD2에서 단순화해 만들면 roof 정보의 잔류와 평가 reference
   공유가 발생할 수 있다.
2. LiDAR prior가 co-acquired current sensor이면 LI-GS와 유사해지고
   “existing/incomplete asset” 서사가 약해진다.
3. downstream Roofer 평가가 단순 adapter tuning 결과이면 GS method contribution과
   분리해 보고해야 한다.
4. `DEC-P1-019`의 공통 `R_shared`는 footprint 차이를 통제해 surface evidence가
   Roofer 결과에 미치는 영향을 건물별로 비교한다. GT-derived XY 공유는 공개하고
   LoD2 Z/RoofSurface/roof type은 평가 단계까지 차단한다.
5. Wu & Vallet식 `detect→remove→fuse`와 L2M-Reg식 사전 정합을 약한 baseline으로
   두면 안 된다. 같은 입력·판정 증거를 쓰는 강한 순차판과 직접 비교해야 한다.

## 4. Acceptance 연구 해석

### SOURCE-SUPPORTED

- ISPRS protocol은 per-area/per-roof-plane/per-building completeness, correctness,
  quality와 plane correspondence/topology 관계를 제공한다.
- CityJSON validation은 schema/internal consistency를 검사하고, val3dity는
  ISO 19107 기반 3D primitive validity를 검사한다.
- Roofer는 output attributes로 process success, point density, nodata fraction,
  RMSE, plane/ridge 수 및 LoD별 val3dity codes를 제공할 수 있다
  ([CLI docs](https://innovation.3dbag.nl/roofer/cli_application.html)).

### INFERENCE

이들 출처는 서로 다른 품질 차원을 제공하므로 `G0–G4` cascade를 설계할 근거가 된다.
그러나 source example의 matching threshold나 특정 benchmark 평균을 모든 건물에
적용되는 보편적 production `PASS_usable` threshold로 해석해서는 안 된다.

### TO VERIFY

- 최근 LoD2 benchmark와 공공 생산 수용 기준의 추가 systematic search
- application-specific RMSXY/RMSZ 허용오차
- reference uncertainty를 포함한 threshold calibration 방식
- fallback LoD1.1을 `G0` 성공으로 볼지 여부

## 5. 제안 contribution statements

아래 문장은 현재 원고에 확정형으로 넣지 않는다.

1. `PROPOSED CONTRIBUTION`: heterogeneous existing 3D prior의 측정오차·시간적
   유효성·정합오차를 현재 영상 관측오차와 분리해 모델링한다.
2. `PROPOSED CONTRIBUTION`: 위치·기하 자유도별 보정된 예상오차를 바탕으로
   image/prior/fusion/abstain을 선택하고 그 출처와 시제를 출력에 보존한다.
3. `PROPOSED CONTRIBUTION`: 정합·현재 유효성·source decision의 공동/반복 추정과
   강한 순차 `align→decide→fuse`를 동일 증거에서 비교해 복잡성이 필요한 경계를 밝힌다.
4. `PROPOSED CONTRIBUTION`: local oracle, risk–coverage, calibration, benign-case
   non-degradation으로 안전한 prior 재사용의 한계와 실패를 계량한다.
5. `PROPOSED CONTRIBUTION`: GS surface quality를 Roofer/LoD2 등 사전 선택한 복수
   downstream probe까지 추적하되, 상위 연구정의를 특정 응용에 고정하지 않는다.
6. `PROGRAM-SPECIFIC CONTRIBUTION`: 같은 E1–E6 evidence를 대상으로 Roofer/LoD2와
   semantic textured mesh의 O/X를 독립 판정하고 `R_O/M_O`, `R_O/M_X`,
   `R_X/M_O`, `R_X/M_X`를 모두 보고한다.
7. `PROGRAM-SPECIFIC CONTRIBUTION`: 같은 E3 image-derived base와 같은 Existing ALS를 쓰는
   E4 unweighted prior reproduction과 E5 conflict-aware prior fusion을 직접 비교하여,
   구조 rescue와 변화 영역의 prior 억제를 분리해 측정한다.

Roofer/LoD2가 첫 저널논문의 confirmatory primary인 이유는 이 프로그램의 중심 claim이
"자동 LoD2 생성 가능 범위의 확대"이기 때문이다. Semantic textured mesh는 중요도가
낮아서가 아니라 geometry·semantic·texture를 함께 묻는 별도 제품 계약이므로 key
secondary로 둔다. 두 output은 서로의 O/X를 대신하지 않으며, mesh 중심 논문에서는
통계적 primary/secondary 순서를 별도로 재동결할 수 있다.

## 6. Claim ledger

| Claim | Label | 승격 조건 |
|---|---|---|
| MVS는 density가 높아도 구조적으로 실패할 수 있다 | `SOURCE-SUPPORTED`; 대상 데이터는 `TO VERIFY` | P2 paired diagnostic |
| No-external-prior GS가 direct MVS의 usable gap을 줄인다 | `PROPOSED HYPOTHESIS` | Gate S0 common-base freeze 뒤 P2 frozen criterion 결과 |
| Existing ALS와 LoD prior가 서로 다른 실패를 회복한다 | `PROPOSED HYPOTHESIS` | P3 E4/E5/E6 rescue-set overlap·discordance와 failure-mode 분석 |
| conflict-aware E5가 E4의 prior reproduction 능력을 유지하면서 changed building의 stale-prior copying을 줄인다 | `PROPOSED HYPOTHESIS` | 독립 change label, E4/E5 paired comparison, frozen conflict metric |
| Roofer/LoD2 O/X와 semantic textured mesh O/X가 서로 다른 failure set을 만든다 | `PROPOSED HYPOTHESIS` | 두 독립 rubric과 네 joint-cell 결과 |
| 본 연구가 GS4Buildings와 신규하게 다르다 | `TO VERIFY` | full-text/code review + lineage audit |
| prior-guided GS가 LoD2 가능 영역을 확대한다 | `PROPOSED CONTRIBUTION` | P4 held-out net transitions |
| 최신화에 성공한다 | `TO VERIFY` | 실제 T0–T1 change cases와 conflict analysis |
| 국소 최소위험 중재가 고정 단일 출처보다 유리하다 | `PROPOSED HYPOTHESIS` | mixed-condition local oracle gap과 비누출 source predictor |
| 공동/반복 추정이 필요하다 | `PROPOSED HYPOTHESIS` | 동일 증거의 강한 순차 baseline 대비 유의한 이득 |
| benign case에서 더 정밀한 prior의 장점을 보존한다 | `PROPOSED HYPOTHESIS` | prior-only 대비 non-degradation와 calibration |

## 7. Primary sources

- Wysocki et al., TUM2TWIN:
  [journal article](https://doi.org/10.1016/j.isprsjprs.2025.12.013),
  [official data portal](https://tum2t.win/datasets)
- Roofer: [official documentation](https://innovation.3dbag.nl/roofer/),
  [source repository](https://github.com/3DBAG/roofer)
- Huang et al., 2DGS: [DOI](https://doi.org/10.1145/3641519.3657428),
  [official repository](https://github.com/hbb1/2d-gaussian-splatting)
- Turkulainen et al., DN-Splatter:
  [paper](https://arxiv.org/abs/2403.17822)
- Jiang et al., LI-GS:
  [paper](https://arxiv.org/abs/2409.12899)
- Zhang et al., GS4Buildings:
  [paper](https://doi.org/10.5194/isprs-annals-X-4-W6-2025-249-2025)
- GeoGS:
  [official article](https://www.sciencedirect.com/science/article/pii/S0924271626003588)
- In Depth We Trust:
  [paper](https://arxiv.org/abs/2604.05715)
- Cross-Temporal 3DGS:
  [AAAI article](https://ojs.aaai.org/index.php/AAAI/article/view/37217)
- Wu and Vallet, image-LiDAR change detection and update:
  [paper](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.html)
- L2M-Reg:
  [official article](https://www.sciencedirect.com/science/article/pii/S0924271626000560)
- Xiong et al., noisy photogrammetric point clouds:
  [paper](https://doi.org/10.5194/isprsannals-II-3-197-2014)
- Huang et al., City3D:
  [paper](https://arxiv.org/abs/2201.10276)
- ISPRS building reconstruction evaluation:
  [official benchmark protocol](https://www.isprs.org/resources/datasets/benchmarks/UrbanSemLab/results/EvaluationBuildingReconstructionDocument/EvaluationBuildingReconstruction.html)
- OGC CityGML:
  [official standard page](https://www.ogc.org/standards/citygml/)
- CityJSON:
  [validation](https://www.cityjson.org/tutorials/validation/),
  [CityJSONSeq](https://www.cityjson.org/cityjsonseq/)
- val3dity:
  [official documentation](https://val3dity.readthedocs.io/)
