# 요소별 집중 지점과 고정·수정 변수

2026-09-09 · `scientific_verdict: null`

한 논문의 여러 기여를 함께 표시한다. `N`=논문이 제안한 구성/절차, `U`=기존 방법 활용, `?`=확인하지 못한 기여/경로다. `N+U`는 기존 부품의 새로운 사용·결합까지 포함한다. 이는 최초성 판정도 성능 점수도 아니다. `?`에는 기능 없음이라는 뜻을 부여하지 않는다. 각 행의 근거와 범위는 연결한 원문 카드에 있다.

## 요소 비교

| 방법 | 입력·전처리 | 좌표·카메라·정합 | 표현 | 관측모형·렌더링 | 증거·감독·제약 | 초기화·최적화·모델 변경 | 추출·후처리 |
|---|---|---|---|---|---|---|---|
| [SRDM](cards/srdm.md) | U 정합/가림/prior 준비 | U 영상–LiDAR 정합 | U disparity/MRF | N+U HOG/Census/prior cost | N two-step prior·절단 비용 | N+U 재매칭·non-local propagation | U 점군화 |
| [Zhou](cards/zhou_2020.md) | N+U ALS plane 후보 | U 보정 stereo/공통 좌표 | N+U 후보 DSM·시차 구성 | N+U 유도 image matching | N 변화에서 ALS 배제 | N 재매칭·change/search 확장 | N+U NDVI/지도·갱신 점군 |
| [Wu 2023](cards/wu_2023.md) | U sensor mesh 처리 | U 정합·sensor viewpoint | N+U mesh의 시간·관계 연결 | N+U ray visibility | N change/quality/persistence | N+U face selection·QPBO | U 기존 seam/stitching의 통합 |
| [Wu 2026](cards/wu_vallet_2026.md) | N+U sensor mesh·stereo 학습자료 | U 정합 및 시점정보 | U sensor mesh/point cloud | N+U ray 비교 | N+U LiDAR label·confidence/filter | N+U matcher 재학습·갱신 규칙 | N+U region filter·point update |
| [Qin](cards/qin_2014.md) | N+U roof image/DSM 증거 | U 보정 stereo | U roof polygon·label | N+U roof projection/검정 | N evidence와 uncertainty | N+U SOM·MRF 판정 | ? 완성 mesh·texture |
| [3DGS](cards/3dgs.md) | U SfM sparse | U 고정 camera | N+U anisotropic GS | N+U fast rasterizer | U RGB loss | N 밀도 제어+기하/외관 갱신 | ? 표준 mesh |
| [2DGS](cards/2dgs.md) | U SfM | U camera | N+U planar GS | N ray–splat | N+U distortion/normal | U GS density/optimizer | U TSDF, 추출 비교 |
| [GS4Buildings](cards/gs4buildings.md) | N+U LoD2 점/깊이/법선 | U 정합 camera | U 2DGS | U GS·raycast | N+U geometry guidance | N+U prior 초기화·loss 일정·building modes | U TSDF |
| [GeoGS](cards/geogs.md) | N+U LoD2/DA3 dual depth | U 정합 pose | U 2DGS | U GS·raycast | N anchor+adaptive visual loss | N 구조 보호·초기화 | U TSDF |
| [ARSGaussian](cards/arsgaussian.md) | N+U LiDAR/영상 pipeline | N+U distortion·BA | U 3DGS | N+U distorted projection | N+U depth/normal/scale | N+U LiDAR growth/prune/split | U block merge; mesh ? |
| [AGS-Mesh](cards/ags_mesh.md) | N+U DNC·sensor/normal | U camera | U 2D/3DGS | U GS depth/normal | N DNC·ANR | N+U 선택 감독 일정 | N+U adaptive TSDF/IsoOctree |
| [SpotLessSplats](cards/spotlesssplats.md) | N+U semantic clusters | U camera | U GS+N classifier | U GS | N robust/semantic mask | N 교대·warm-up·UBP | ? 표준 mesh |
| [CL-Splats](cards/cl_splats.md) | N+U 특징 변화·3D mask | U calibrated camera | U 기존 GS | N+U gradient 보존 국소 커널·재투영 | N 국소 갱신·배경 보존 | N+U clone/prune/reprojection | N+U 변경 병합·이력 복구 |
| [GaussianUpdate](cards/gaussianupdate.md) | N+U 변화 영역·관측 선택 | U camera | U GS+N 보조 appearance | N+U relighting model | N 외관/기하 변화 분리 | N 3단계 선택 갱신 | U updated GS |
| [NeuRIS](cards/neuris.md) | U mono-normal | U camera | U SDF/radiance | U volume rendering | N photo gate·normal 사용 | N+U 렌더 표면으로 prior 기각 | U surface extraction |
| [BayesRays](cards/bayesrays.md) | U 학습된 NeRF·training rays | U camera | N+U spatial perturbation field | U NeRF derivatives | N spatial uncertainty | N+U Laplace/Hessian 근사 | N+U uncertainty-based filtering |
| [VCR-GauS](cards/vcr_gaus.md) | U mono normal·semantic | U camera | U flattened GS | N+U intersection/D-Normal | N view consistency weight | N 기하 gradient·split | U TSDF+semantic trimming |
| [HelixSurf](cards/helixsurf.md) | N+U MVS 연동 | U camera | U implicit surface | N+U SDF rendering·dynamic occupancy | N intertwined regularization | N MVS↔surface 반복 | U mesh extraction |
| [SceneEdited](cards/sceneedited_2026.md) | N synthetic edit benchmark | U calibrated image/cloud | U cloud·change labels | U projection·occlusion | N benchmark/change annotation | U pretrained baseline·정합/추가삭제 | N+U toolkit/update read-out |

마지막 두 행을 포함한 세부 기여 수준은 카드가 우선한다. 어떤 pretrained network를 사용했다는 이유만으로 학습 데이터와 독립인 관측을 얻었다고 보지 않는다. 미래 실험에서는 같은 pretrained 정보 접근권까지 comparator 계약에 포함한다.

## 고정·수정 변수와 제약

아래 고정 이유/해제 부작용은 명시된 경우를 제외하면 **우리 추론**이다. 후단 변수만 학습한다는 이유로 앞단 추정 자체가 없다고 하지 않는다.

| 방법 | 실제 수정/추정 | 고정/재사용 또는 강한 제약 | 풀 때 검토할 효과·부작용 |
|---|---|---|---|
| SRDM | disparity 1·2, retained prior membership | 등록된 원 LiDAR/RGB·camera; 둘째 prior 비용도 절단 | 원 LiDAR까지 움직이면 매칭 개선과 원 자산 왜곡을 분리해야 함 |
| Zhou | 후보 중 D1 선택·D2·change/search region | ALS 후보 plane와 camera; 변화 영역은 prior 배제 | plane/camera 갱신은 misregistration 보정 가능; 실제 변화 흡수 위험 |
| Wu 2023 | face change·품질 선택·접합 | 원 sensor mesh 주로 고정; stitching 경계점 병합 예외 | geometry refit은 seam 개선 가능; 선택 전 원형의 오차 구분 필요 |
| Wu 2026 | matcher weights(훈련 절차), change·filter·점 membership | 갱신 단계의 기존 mesh·camera·ray geometry | image mesh/pose를 갱신하면 오탐 감소 가능; label 의존/계산 증가 |
| Qin | roof change/uncertain 중간 label→최종 MRF label | 기존 roof geometry·camera·DSM 입력 | geometry 동시수정은 단순 검정과 다른 inverse problem |
| 3DGS | xyz/rotation/scale/opacity/SH/N | camera·RGB; SfM 파일만 고정, 초기 GS 위치는 가변 | camera까지 풀면 pose 보정과 형상 흡수가 경쟁 |
| 2DGS | planar GS parameters/N, rendered depth/normal | camera·RGB, 표면형 표현 | regularizer 완화는 세부 자유도와 잡음·다중층 모두 증가 가능 |
| GS4Buildings | GS parameters/N·단계별 loss | LoD2 mesh/raycast prior·camera | 유효 geometry 안정성과 잘못된 anchor 수정 사이 trade-off |
| GeoGS | GS parameters/N, DA3 weight history | LoD2/DA3 depth·pose; protected GS 이동/density 제한 | 보호 해제는 잘못된 구조 수정 및 유효 구조 손상 모두 가능 |
| ARSGaussian | 앞단 pose BA·depth propagation; GS parameters/N | GS 단계 LiDAR와 depth/normal 기준 | LiDAR proximity 해제는 미관측 세부 확장 및 floaters 모두 가능 |
| AGS-Mesh | GS parameters/N·ANR mask | raw depth, mono normal, DNC confidence | 재기각/재사용의 bias; 추출 해상도 변경은 별도 요인 |
| SpotLessSplats | GS·classifier·mask·histogram·N·appearance latent/MLP | feature/공간 cluster·RGB; 원논문 pose | 약관측 실제 구조의 오삭제와 transient 누출을 함께 확인 |
| CL-Splats | change GS·새 GS·dynamic reprojection | static/background GS 제약, 기존 상태 | background 해제는 정합오류 보정과 catastrophic forgetting 둘 다 가능 |
| GaussianUpdate | appearance MLP·새 GS·정해진 stage 변수 | stage별 기존 GS geometry/appearance 고정 범위 | 조명·재질·형상의 설명 책임이 바뀌어 geometry shortcut 가능 |
| NeuRIS | SDF/radiance·prior acceptance | pretrained normals·poses; 기각 normal 재사용 제한 | 재채택은 초기 오기각 회복 가능, 반복 자기확증도 검증 필요 |
| BayesRays | perturbation uncertainty 추정 | 원 NeRF weights·관측·pose | 본체 재학습은 post-hoc 불확실성 추정과 별개 방법 |
| VCR-GauS | GS geometry/appearance/N·confidence | mono normal·camera | confidence를 높이는 것과 실제 위치 정확도를 분리해야 함 |
| HelixSurf | implicit surface·MVS depth/normal | 원 영상·camera | 반복 비용·모델 오류의 상호 전파; new data 없이도 추정은 개선 가능 |
| SceneEdited | 예측 depth/pose/points·scale/alignment·added/deleted membership | baseline의 old map·GT change mask·known calibration; split은 평가 계약 | 원 baseline은 GT-mask oracle 진단. 예측 mask로 바꾸면 실제 조건과 가까워지나 판단·정합 오류가 추가됨 |

## 비교 설계에 주는 결론

같은 `depth prior`도 SRDM의 매칭 비용, GeoGS의 structural anchor, AGS-Mesh의 sensor supervision, ARS의 model pruning 기준은 변경되는 변수와 강제력이 다르다. 손실 계수 하나만 같게 두어 입력 영향이 통제되었다고 볼 수 없다.

공통 비교에서는 ① 원관측과 pretrained 정보 ② 초기화와 앞단 중간 결과 ③ 학습 가능한 변수 ④ 마스크·가중·기각·재채택 ⑤ density 변경 ⑥ 추출/후처리를 각각 기록한다. 동일한 재구성 결과에서 후처리만 바꾸는 대비와, 원입력에서 전체를 다시 계산하는 대비는 서로 다른 질문이다. 이 요구는 비교 해석을 위한 설계이며 새 실행 승인이 아니다.
