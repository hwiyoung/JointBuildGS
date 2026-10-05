# 조건–가정–잔여 오류–최종 복원 영향

2026-09-09 · `scientific_verdict: null`

각 방법의 실제 입력과 출력에 맞춰 해석한다. 기하 거리 F1, 변화 검출 F1, 렌더 PSNR, uncertainty AUSE는 서로 다른 양이다. 같은 이름의 지표도 참조·분모·표본화·지원영역이 다르면 논문 사이 수치 순위를 만들지 않는다. 아래 잔여 오류는 연결 카드에서 원문 위치와 저자 해석/우리 추론을 확인할 수 있다.

## 문헌별 조건과 영향

| 문헌 | 실제 조건·가정 | 확인된 성공 | 잔여 오류의 상태 | 오류가 생기거나 전달되는 곳·최종 영향 |
|---|---|---|---|---|
| [SRDM](cards/srdm.md) | 등록된 LiDAR+stereo; 시차로 prior 불일치를 구별 | 잡음·저텍스처의 LiDAR 유도 복원, 시기차 prior 기각 | **관측 실패/저자 한계:** 균일 강도와 depth jump의 mismatch(§5) | 원 LiDAR 투영/가림→prior 검증→시차 비용→점군. 실패 원인을 가중 하나로 귀속 불가 |
| [Zhou](cards/zhou_2020.md) | 과거 ALS+보정 stereo, plane·NIR/지도 정보 | 실제 2012 ALS/2018 영상의 변화·갱신 | **관측 실패+저자 해석:** Assen 12개 누락 중 10개를 2차 매칭 저텍스처/그림자로 설명 | change→prior 제외→image-only 재매칭 실패→갱신 건물 누락. 변경 판단과 재복원 능력 분리 |
| [Wu 2023](cards/wu_2023.md) | 정합된 시계열 sensor mesh·시점, 품질/피복 차이 | 품질·비관측 보존·접합, 거의 수평 ray는 거리검사로 완화 | **저자 한계:** 장기 주차차는 persistence만으로 제거 못함. 독립 surface GT 잔여오차 미평가 | 입력 mesh와 ray→face label/quality→QPBO→seam. 선택 오류와 seam 오류는 다름 |
| [Wu 2026](cards/wu_vallet_2026.md) | 기존 LiDAR+영상 sensor mesh, 좋은 정합 | dense match 보완과 partial-coverage 갱신 시연 | **저자 보고:** image mesh 오류·식생/가림 false detection. 수동 변화 GT 및 정량 갱신 품질은 미평가 | depth 생산·mesh→ray change→region filter→삭제/추가. matcher label 재학습은 존재 |
| [Qin](cards/qin_2014.md) | LoD2 roof+stereo/DSM; 실제 사례는 2010 모델을 2002 영상으로 검정, 합성 별도 | 무색 모델의 geometry/사진 change detection | **관측 실패:** 작은 구조·bridge/rail 오탐, uncertain band 과확대의 MRF 악화. 완성 mesh/외관은 범위 밖 | roof projection/DSM→불확실 label→MRF 이진 판정. uncertain은 최종 abstention이 아님 |
| [3DGS](cards/3dgs.md) | 정적 calibrated RGB·SfM | 높은 NVS 품질과 렌더 속도 | **관측 실패:** 약관측 영역 얼룩·늘어짐·popping | 관측/렌더 근사/밀도 최적화→Gaussian artifact; 최종 mesh 영향은 미평가 |
| [2DGS](cards/2dgs.md) | 불투명 표면·다중뷰 RGB | 표면/NVS·계산 개선 | **저자 한계:** 얇은 기하·반투명·과평활화; 추출 차이 실험 존재 | texture 중심 density→surface regularization→depth→TSDF의 세부 손실 가능 |
| [GS4Buildings](cards/gs4buildings.md) | 정합된 LoD2+UAV 영상 | 구조/피복·외관 보완 | **원문 수치:** scene별 completeness와 accuracy 방향 분리; **저자 한계:** prior에 없는 작은 기하 평활화 | LoD2 surface/depth/normal→anchor/감독→GS→TSDF. prior 문제와 추출 문제 분리 필요 |
| [GeoGS](cards/geogs.md) | LoD2+희소 RGB+DA3; prior/pose 교란 실험 포함 | 평균 구조 복원, protection 제거보다 full 성공 | **관측 악화:** 일부 지역 2DGS보다 기하 저하; Table7 교란에서 렌더 악화. 실제 temporal 존치 분류는 미평가 | input/pose→depth anchor/protection·visual controller→GS→mesh. 어느 단계가 지역 악화 원인인지 미확인 |
| [ARSGaussian](cards/arsgaussian.md) | 항공 RGB+LiDAR; calibration·metric support | 정합·floater 억제·depth/normal 보완 | **관측 악화:** noise·과도한 SOR·표면별 결손. **저자 인정:** LiDAR 기반 RMSE 참조 의존 | denoise 오배제는 저자 해석; 정합/ACMH→감독·prune→GS. 독립 현재 표면 손상률 미평가 |
| [AGS-Mesh](cards/ags_mesh.md) | 실내 RGB+sensor depth+pretrained normal | noisy priors filtering 및 mesh/NVS 개선 | **저자 한계:** IsoOctree 전체 개선 비일관; 지표/화소별 악화도 있음 | DNC/ANR 감독·render feedback→GS→adaptive TSDF. 일치한 biased plane 실패는 우리 추론/미확인 |
| [SpotLessSplats](cards/spotlesssplats.md) | transient가 있는 장면에서 정적 배경이 목표 | clutter 억제·Gaussian 수 절감 | **관측 실패/저자 해석:** 같은 의미의 근접 대상·가는 구조, 강한 UBP의 약관측 유효부 삭제 | feature/mask→gradient 차단·pruning→배경 결손. 영구 신축 갱신은 범위 밖 |
| [CL-Splats](cards/cl_splats.md) | 기존 색상 GS+국소 신규 RGB, 변화 영역 중심 | 정적부 보존·빠른 국소 갱신 | **관측 실패:** 얇은 변화 구조의 3D mask 과소피복 | 변화 검출→갱신 영역 제한→기하 수정 불가. camera 오류/조명 변화는 별도 조건 |
| [GaussianUpdate](cards/gaussianupdate.md) | 색상 GS+신규 영상, lighting/layout 변화 | appearance adaptation과 기하 갱신 | **관측/저자 한계:** 강한 반사, 일부 비교 열세·작은 forgetting | 조명/기하 설명 분리→selective new GS→공동 refinement. 독립 surface currentness는 미평가 |
| [NeuRIS](cards/neuris.md) | 실내 RGB+mono normal; multi-view patch 검정 | prior supervision의 유효 구간 선택·기하 향상 | **저자 한계:** 저조도·경사 시선·벽 그림; 초기 기각 재채택 없음 | 렌더 표면→NCC→영구 supervisor 기각→다음 SDF. 자기확증 실패 빈도는 미확인 |
| [BayesRays](cards/bayesrays.md) | 이미 학습된 NeRF·training rays의 post-hoc uncertainty | depth 오류순위/cleanup/관측 범위 진단 | **관측 실패:** inconsistent-view floater가 낮은 uncertainty인 사례 | 고정 잘못된 field→국소 perturbation uncertainty→오류를 놓치는 filtering. currentness 확률은 범위 밖 |
| [VCR-GauS](cards/vcr_gaus.md) | mono normal+RGB; 다중뷰 normal consistency | normal 감독의 위치 수정, surface F1 향상 | 일부 장면/Replica 경쟁법보다 낮음; full 잔여 원인 미확인. confidence 없는 돌출은 ablation 실패 | normal→D-Normal gradient/weight→scale/split→TSDF. 방향 confidence≠위치 참값 |
| [HelixSurf](cards/helixsurf.md) | posed RGB, MVS↔implicit surface | 앞단 재추정을 통한 기하·효율 개선 | **관측/저자 한계:** 무텍스처 고곡률에서 smoothing 가정 불충족 | smoothing→artifact는 저자 해석; 후속 MVS로 오류 재전파는 우리 추론/미확인 |
| [SceneEdited](cards/sceneedited_2026.md) | existing cloud+RGB, 실제 장면에 합성 과거 편집 | 과거형상/추가·삭제/비관측 갱신 평가 기반 | GT change mask를 사용하는 복원 비교, 실패 실행을 분리한 평균. 자연 변화/전체 자동 검출과 다름 | change/visibility→registration/reconstruction→updated map; 늘어난 view가 항상 이득은 아님 |

## 공통 조건을 정의하는 방법

학위의 조건 축을 아래처럼 구별한다. 이는 **실험 설계 후보**이며 이미 확보된 참조 label이나 새 실행 condition이 아니다. 전 조합을 무작정 실행하기보다 가장 가까운 기존 방법을 반박할 수 있는 최소 대비를 선택한다.

| 축 | 구별할 조건 | 혼동하면 생기는 잘못된 결론 |
|---|---|---|
| 기하 품질 | 영상/prior 각각 양호·bias·잡음·outlier·결손; 둘 다 틀림 포함 | 현재 영상=정확, 유효 prior=완벽한 점군 |
| 정합 | global pose/rigid 오차·국소 residual·datum/scale | 높이 차이를 모두 변화 또는 기하 오류로 판단 |
| 표현 수준 | 원점 밀도·평면 단순화·곡면·edge/세부 scale | 실제 변화와 단순화 차이를 같은 오차로 집계 |
| 관측 가능성 | 시야 밖·가림·저시차·저텍스처·반사·기기 결손 | 자료 없음=현재 기하 없음, 빈 depth=삭제 근거 |
| 외관 | 조명·그림자·재질·노출·transient와 영구 기하 변화 | RGB residual=기하 변경, clean 배경=최신 세계 |
| 시기 | 동시/근접취득·자연 장기변화·합성 편집 | 잡음 robustness=실제 변화 갱신 검증 |
| 출력 | 점군·GS·depth·mesh·texture·LoD2 | Gaussian 중심 정확도=최종 표면, NVS=형상/현재성 |

## 원인 귀속과 평가의 최소 요구

동일한 구멍도 원영상 비관측, depth filter 오배제, prior 보호 해제, opacity 감소, TSDF 범위 제한, component 제거에서 생길 수 있다. 단면 또는 최종 거리표만으로 원인을 정하지 않는다. 입력→파생 기하→감독→학습 상태→native output→추출→후처리를 연결할 evidence가 필요하다.

개선된 곳·기존 양호한 곳의 악화·새로 복원된 곳·사라진 곳을 같은 고정 영역에서 기록한다. 모델이나 metric 실패를 평균에서 조용히 제외하지 않는다. 참조가 없는 면은 correctness를 강제 판정하지 않으며, 존재하는 독립 참조를 재현하지 못한 예측 부재와 구분한다. calibration은 예상오차와 실제오차의 관계, ranking은 오류의 순서, risk–coverage는 채택 범위별 손실로 각각 확인한다.

기존 GeoGS/Wu 로컬 개발 결과는 이 조건을 구체화하는 **프로젝트 사례**다. 저자의 native 입력·코드 실험과 합쳐 평균내거나 문헌 고유 실패로 치환하지 않는다. 현재 상태와 근거 경계는 [출처·맥락 문서](05_SOURCE_AUDIT_AND_CONTEXT_ko_v1.md)에 있다.
