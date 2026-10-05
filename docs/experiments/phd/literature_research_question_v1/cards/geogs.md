# GeoGS — 근거 카드

`reviewed_at: 2026-09-09` · `scientific_verdict: null` · 직접 비교 핵심: 정합된 LoD2+현재 RGB/pose→planar GS+mesh. 위성 영상의 동명 GeoGS와 구별한다.

## 원문·버전·확인 범위

- Zhang, Wysocki, Jutzi, **GeoGS: Geometric Prior-Guided Gaussian Splatting for robust urban reconstruction from sparse views**, ISPRS JPRS 240 (2026), 184–201. [DOI](https://doi.org/10.1016/j.isprsjprs.2026.07.011), [출판사](https://www.sciencedirect.com/science/article/pii/S0924271626003588).
- 확보된 18쪽 출판 PDF를 Docker의 pypdf 6.0.0으로 직접 읽고 method·Table3/6/7·discussion을 대조했다. 원본 `/home/innopam/.codex/attachments/74f36af2-99b5-411a-93e5-7fa2ce39fe8d/1-s2.0-S0924271626003588-main.pdf`, SHA256 **21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4** 현재 재확인. 아래 페이지는 PDF 기준이며 인쇄 페이지=PDF+183이다.
- [공식 구현](https://github.com/zqlin0521/GeoGS/tree/db40c95c657ec03ff21c83cb99cf39f4e90247a6), live HEAD `db40c95c657ec03ff21c83cb99cf39f4e90247a6` 재확인. 확보 `train.py` SHA256 `4c09f6a117d7f4a13e3bd3c5d9eb49b1830e428950a53c0f86be4001637c7a10`. 공식 LoD2 조건과 로컬 ALS 변환 적용은 다른 실험이다.

## 1. 문제와 입출력

희소 관측에서 안정적인 도시 구조와 영상 관측 세부·외관을 함께 복원한다. **실제 관측**=RGB 및 camera 취득/추정 기반 정보. **외부 prior**=LoD2 city mesh. **파생 기하**=LoD2 sampled points/raycast structural depth, current RGB+pose의 DA3 visual depth. **사전학습 정보**=DA3의 learned prior. DA3 depth는 독립 측량 관측이 아니다. 결과는 2D Gaussian 장면·NVS 및 TSDF mesh이며 CityGML 의미/roof readout이 아니다. [§3, Fig2, PDF3–7]

알려진 카메라, 동일 metric/local frame, 구조적으로 상당 부분 유효한 LoD2를 전제한다. 시간차는 별도 분류 변수로 검증하지 않는다. LoD2 없는 지면·식생·동적 물체는 visual guidance/densification에 더 의존한다. SfM point initialization 의존성을 제거하지만 pose 정확도 의존성은 유지한다. raw ALS를 그대로 받지 않으므로 ALS mesh/depth 생성 오차는 별도 입력 변환이다. [§3.2–3.3, §6 PDF17]

## 2. 기여의 위치

`N=논문 제안`, `U=기존 사용`, `?=미확인`이며 N은 보편적 신규성 verdict가 아니다.

| 요소 | 구분·근거 |
|---|---|
| 입력·전처리 | **N+U**: LoD2 sampling/visibility와 dual-depth 결합; raycast·trimesh/Open3D·DA3 추론은 기존 방법. §3.2–3.3 |
| 좌표·카메라·정합 | **U**: Pix4Dmatic/제공 pose와 지리참조 좌표 변환. joint pose refinement는 future work. §4.3, §6 |
| 표현 | **U**: 2DGS planar Gaussian. §3.1 |
| 관측모형·렌더링 | **U**: 2DGS 미분 가능 렌더링·depth/normal, raycasting. §3.1–3.3 |
| 증거 사용·감독·제약 | **N+U**: structural/visual depth 분리, 약한 구조 anchor, dual-gated visual weight; 기본 RGB/distortion/normal 손실 재사용. §3.4 식11–19 |
| 초기화·최적화·모델 변경 | **N+U**: LoD2 초기화, anchor/refinement, 근접도 기반 geometry protection; density control/Adam 기본 구조 사용. §3.2,3.4 |
| 추출·후처리 | **U**: 2DGS TSDF와 mesh 평가; Gaussian 중심과 mesh를 구분. §4.2,5.2 |

## 3. 무엇을 고정하고 무엇을 수정하는가

| 대상 | 고정/추정/강한 제약 및 근거 |
|---|---|
| LoD2 mesh·표본·두 prior depth·camera | offline 입력으로 고정. 학습 중 mesh correction, camera BA, DA3 재추론 없음. §3.2–3.3/4.3 |
| Gaussian 중심·rotation·scale·opacity·SH | 학습 변수가 됨. 기본 densification/pruning으로 수 변경 |
| 구조 보호 대상 | anchor 뒤 prior 표본까지 거리 <.2m를 기준으로 정함. 기본 경로에서 원 자산 유효성의 재판정 아님 |
| 보호 primitive | xyz/rotation/scale gradient×.01; clone/split/prune 제한. opacity/SH까지 전부 고정하지 않음. gradient 배율은 Adam 실제 이동 배율과 다름 |
| LoD2 depth loss | 0–8k=.08; refinement=.005(후자는 코드 default). prior 영향은 0이 되지 않음 |
| DA3 depth weight | 8k 이후 initial .05, loss history의 depth guard+RGB benefit로 감쇠/유지/lock. 고정된 depth 자체를 수정하는 것은 아님 |

원 depth loss는 finite/positive prior pixel만 사용한다. 공개 코드의 선택적 confidence weighting은 **DA3**에 적용되며 LoD2 confidence/currentness를 판정하는 입력은 아니다. [train.py L294–324](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L294), [L794–816](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L794). 이 pixel mask와 지역별 prior 타당성 검정은 구분한다.

코드 근거: [gradient hooks L603](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L603), [dual-gate와 total loss L866–960](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L866), [mask 생성 L1140](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L1140), [density/prune L397–461](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/scene/gaussian_model.py#L397). 논문 §3.4/PDF6–7, §4.3/PDF9.

**정보 흐름:** `LoD2→점/구조depth→anchor→보호 집합`, `RGB+pose→offline DA3`, 이후 `GS 렌더→RGB·DA3 depth 잔차→visual weight controller→다음 GS 갱신`. 따라서 **최적화 상태/가중 feedback은 있다**. 후단이 앞단 LoD2·camera·DA3 관측을 재추정하는 경로와는 다르다. LoD2 loss 계수는 DA3 controller가 재선택하지 않는다. 보호를 풀면 구조 drift/결손 증가와 잘못된 구조 수정 가능성이 함께 생긴다. 제약 완화만으로 반복 재판단 필요성을 입증할 수 없다.

## 4. 실제 검증 범위

- TUM2TWIN 9지역, egenioussBench 5거리 지역. 전자는 UAV RGB+LoD2 및 UAV LiDAR reference, 후자는 smartphone/정밀 reference poses+LoD2 및 airborne oblique reference mesh. 관측 방식과 reference provenance가 다르다. 주 설정 15 total views, 희소도 {15,12,9,6,3}; 세부 ablation/오류 실험 Region1 K=13로 표시. [§4.1–4.3 PDF8–9, Fig6]
- NVS PSNR/SSIM/LPIPS, Gaussian centers와 extracted mesh 각각 CD/M3C2/F1@.2/.5. 3DGS/2DGS/PGSR/SuGaR, DN-Gaussian/FatesGS 및 일부 효율 비교의 CityGaussian. 표마다 comparator 범위가 다르다. **직접 MVS·prior-only·정합 prior-only·SRDM/Zhou 조합은 본문의 주 비교군이 아니다.** [Tables1–6, PDF10–15]
- Table6 PartA는 초기점만 LoD2로 바꾼 2DGS/PGSR에서 NVS 일부 향상과 geometry 악화를 확인한다. PartB는 초기화/LoD2 depth/DA3/protection/dynamic/gate 제거, C/D는 threshold 민감도. 동일 anchor 분기의 완전 상태 일치 여부와 seed 반복은 원문에서 확인되지 않는다.
- **이미 수행된 오류 검증:** Table7/PDF16, LoD2 height +.25/.5/1m, horizontal .5m, 일부 면 제거; camera translation σ=.1m, rotation σ=.5°, 결합. 변경 후 초기점/pose-dependent priors 재생성. 부정확/불완전 prior를 전혀 평가하지 않았다는 공백은 기각한다. 제거 면 membership/비율, 자연 시간차 철거/신축·국소 비악화의 체계적 검증은 확인되지 않는다.
- 성공: Table3 mesh 평균 M3C2 .635 vs 2DGS .741, F1@.5 .678 vs .640. **악화도 있음:** Region9 mesh F1@.5 .531 vs 2DGS .748, M3C2 .671 vs .546; Region6 F1@.2 .364 vs .448. 같은 지역의 모든 기준을 개선한 것은 아니다.
- Table6 full→w/o protection M3C2 .378→.389, F1@.5 .788→.775. 구조 보호는 성공 조건에서 유용했다. Table7 camera noise는 렌더 악화가 특히 크다. Table5 Region1 training 36m14s는 전처리·mesh·전체 city pipeline 시간 보장이 아니다.
- DA3의 정확한 train/eval 입력 membership, seed, 추출 세부값과 전처리 비용을 출판 PDF만으로 완전히 고정할 수 없다. **누출을 확정하지 않는다.** F1 distance tolerance를 topology/정확한 세부 기능 검정과 동일시하지 않는다.
- Table6 PartD의 default F1@.2는 .459로 PartB/C의 .469와 다르다. 표기 불일치 원인은 미확인이므로 서로 다른 Part를 합쳐 미세 효과나 허용오차를 계산하지 않는다.

## 5. 남은 오류와 전달 경로

| 조건·잔여 오류 | 사실/해석·상태 | 전달 경로·다른 원인 |
|---|---|---|
| LoD2/pose perturbation 뒤 LPIPS·PSNR 악화 | **관측된 실패/악화**, Table7 | input misalignment→projection/depth anchoring→optimization; 저자는 국소 정합 영향으로 해석. 보호만의 원인으로 분리되지 않음 |
| 평균 향상 중 Region9 mesh 악화 | **원문 수치 사실**, Table3b; 정확한 원인 **미확인** | 입력 피복, prior 단순화, depth 품질, GS 최적화, TSDF 각각 가능. 표만으로 오보존/변화 detection 실패 확정 불가 |
| 강한 LoD2 오정합·큰 pose 오차 | §6의 **저자 한계/후속 방향**; tested 범위 밖의 보편 실패율 **미평가** | joint pose·adaptive LoD2 correction 제안; 이미 성공한 moderate perturbation과 구별 |
| 비건물·차량·식생 artifact/결손 | §6 **저자 보고/해석** | LoD2 초기화·보호 미지원→visual/density에 의존. semantic/motion mask를 후속책으로 제안 |
| 오래된 구조의 현시점 유효성·새 구조 복원 | **미평가** | 근접 protection이 currentness 판단이라는 주장 불가. 실제 오류 잔존 여부를 확인할 별도 비교 필요 |

**로컬 현재 맥락은 별도:** [P2_REVIEW](../../geogs_p1p2p3_v1/P2_REVIEW_ko_v1.md)와 [FACTOR_CONTRASTS](../../geogs_p1p2p3_v1/FACTOR_CONTRASTS_ko_v1.md)는 2026-09-08 완료된 실제 ALS 파생 입력 18조건 결과를 기록한다. 결과가 없다는 옛 상태는 폐기한다. 단일 실행·공통 anchor·ALS 변환·원 adaptive DA3·추출/후처리가 묶인 기술 진단이므로 원 LoD2 GeoGS의 포괄 실패 증거나 문헌 독립 재현으로 사용하지 않는다. 본 문헌 카드에서 로컬 결과를 재계산하지 않았다.

## 6. 연구 공백 후보

**이미 해결:** 구조 안정성+세부+외관의 목표, dual-source depth, LoD2 초기화, 적응 visual-depth 가중, geometry protection, moderate prior/pose error robustness. ‘GS가 prior를 수정한다’, ‘반복한다’, ‘가중치를 바꾼다’ 자체는 신규성이 아니다.

**근거가 남는 후보:** 오류의 종류·정합·피복·관측 충분성에 따라 유효한 구조의 손상을 통제하면서 잘못된 강한 제약을 완화할 수 있는가. 방법론적 후보와 새 적용조건/검증 부족을 구분한다. 가장 가까운 해결은 GeoGS 자체, SRDM/Zhou 오류 제거를 연결한 강한 순차 처리, 단순 confidence/mask와 camera 정합 개선이다.

**최소 비교:** 같은 evidence·초기화/추출 계약으로 native GeoGS, 전처리 정합/오류 제거+GeoGS, 고정 국소 가중, 제안 방식. 유효/결손/잘못된 prior와 충분/부족 관측을 교차하고 image-only·prior-only·registered-prior-only 및 GS 없는 강한 복원도 둔다. 재판단을 제안한다면 동일 판단의 1회 적용과 반복 적용을 추가 비교한다. metric 평균뿐 아니라 수정된 곳·보존된 곳·악화된 곳·판단 불가를 추적한다. **기각:** 단순 처리로 해결되거나, 반복 이득이 없거나, 개선이 추가 입력·추출/계산량·다른 구역의 손실로 설명되면 후보를 축소/폐기한다. 현재 문헌은 GS/판단 모듈/반복의 필요성을 확정하지 않는다.
