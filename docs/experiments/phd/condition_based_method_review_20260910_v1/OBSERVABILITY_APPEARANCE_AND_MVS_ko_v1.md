# 관측·외관·MVS에서 확장한 비교 후보

- 작성일: 2026-09-10
- 상태: 원문 및 공식 소스의 제한된 읽기 감사. 재현 실행 없음.
- scientific_verdict: null
- 역할: 기존 세 후보 목록 밖에서 조건에 맞는 경쟁 원리를 찾는다. 모든 논문의 모든 실험·코드를 감사했다는 뜻은 아니다.

## 1. 추가 선별 근거와 인용 연결

| 조건 | 새로 자세히 읽은 방법 | 역할 | 선택 이유 |
|---|---|---|---|
| 영상이 있어도 외관 변화가 기하 오차처럼 전달됨 | CoMe (2026) | 같은 GS 기반의 구성요소 경쟁; image-only surface baseline 후보 | 가중치뿐 아니라 생성 제어·외관 보정까지 이미 연결함 |
| RGB confidence와 실제 기하 신뢰가 다름 | GURecon (AAAI 2025) | 신뢰도 추정 도입 후보·원인 참고 | current surface에서 다중뷰 증거를 계산하고 조명 교란까지 보정함 |
| 무텍스처와 비평면·경계가 혼재 | ACMP (AAAI 2020) | MVS 비교·구성요소 도입 후보 | 학습 표현 없이도 planar prior와 사진 증거가 상보적으로 작동함 |
| 기하 오류처럼 보이는 pose/정합 오류 | SPARF (CVPR 2023) | 정합 원인 참고·조건부 구성요소 | current geometry와 pose를 대응점 제약으로 함께 갱신함 |

인용 확장 경로: CoMe §2는 VCR-GauS 등 pseudo-normal confidence 연구와 Bayes' Rays, FisherRF를 논의한다. GURecon §2는 NeuRIS를 포함하는 다중뷰 일치 활용 연구에서 기하 uncertainty로 질문을 확장한다. ACMP는 ACMM의 multi-scale consistency와 TAPA-MVS의 평면 가정을 대조한다. SPARF는 BARF 계열의 pose–representation 최적화에서 sparse/noisy pose 조건을 좁혀 다룬다. 이 연결은 계보·선별 근거이며 모든 후속 논문이 앞선 논문의 실패를 입증했다는 뜻은 아니다.

DS-NeRF는 sparse depth uncertainty 활용이라는 관련성을 [공식 프로젝트](https://www.cs.cmu.edu/~dsnerf/)에서 확인했으나 이번 정밀 카드에서는 제외했다. 현 질문에 대한 직접성은 위치별 손상·수정 제어를 다룬 후보보다 낮으며, '검토 제외=방법 실패'가 아니다. Bayes' Rays/FisherRF는 uncertainty 비교 확장 후보로만 남기고 원문·코드 상세를 확인하지 않은 신규 성능 주장을 하지 않는다.

## 2. CoMe — 감독·생성·외관의 연결은 이미 가까운 경쟁 원리

**입출력·가정:** posed RGB→3DGS→mesh. 기존 LiDAR/LoD/DSM을 수정하는 원방법은 아니다. 충분한 시선 피복을 전제한다.

**원문 확인:** [v2 §3.2–3.4, §4.2 Tables 3–4, §5](https://arxiv.org/html/2603.24725v2). primitive confidence로 RGB 손실을 조절하고 기하 정규화와 균형을 맞춘다. confidence는 densification threshold에도 연결된다. 외관 보정된 밝기와 원 렌더의 contrast/structure를 분리하는 D-SSIM 설계도 제시한다. Table 3에서 precision·recall 및 F1 개선을 보고한다. 가중치만의 무력함을 보여주는 실패 표로 해석할 수 없다.

**남는 상태:** §5의 심한 가림·미관측 영역 구멍, 원거리 세부 부족은 저자 한계다. 이 중 정보 부족을 prior 활용 실패와 동일시하지 않는다. 유효한 외부 기하의 손상과 틀린 외부 기하 수정의 동시 성능은 이 논문의 평가 범위에서 확인하지 않았다.

**공식 구현:** `caf62f6402dd82a301f7aa9d43350209f7309911`의 [train.py](https://github.com/r4dl/CoMe/blob/caf62f6402dd82a301f7aa9d43350209f7309911/train.py#L181)는 learnable rendered confidence로 RGB 항을 구성한다. [gaussian_model.py](https://github.com/r4dl/CoMe/blob/caf62f6402dd82a301f7aa9d43350209f7309911/scene/gaussian_model.py#L779)의 split/clone 경로는 confidence를 사용한다. 원문 식과 이 두 경로를 대조했으며 rasterizer 전체·수치 재현은 확인하지 않았다.

**우리 추론·최소 비교:** 외관 보정만으로 개선되는 효과, confidence 효과, 생성 제어 효과를 분리해야 한다. '감독과 수정량을 연결'만으로 신규성을 주장할 수 없다. 동일 prior와 초기 상태를 사용하는 도입 비교에서는 CoMe 원방법 재현과 prior를 추가한 adaptation을 구분한다.

## 3. GURecon — 신뢰도 향상과 형상 향상을 분리하는 선행

**입출력·흐름:** posed RGB·마스크→표면/외관 및 연속 기하 uncertainty. 현재 표면 교차점에서 patch의 다중뷰 일치를 계산해 uncertainty를 증류한다. 시선 의존 외관을 분리한 뒤 uncertainty를 재정제한다. 최종 정제 단계에서는 다른 field를 고정한다. [원문 v1 §3.2–3.5](https://arxiv.org/html/2412.14939v1)

**검증·성공:** Tables 1–3는 uncertainty의 오차 순위 평가와 ablation을, §4.3은 새 시선 선택을 통한 incremental reconstruction을 보고한다. 같은 geometry에 post-hoc uncertainty를 비교한 행의 AUSE 향상을 geometry 정확도 향상으로 읽으면 안 된다. 또한 새 시선 획득의 이득을 동일 입력 실험의 이득으로 전용할 수 없다. [원문 §4](https://arxiv.org/html/2412.14939v1#S4)

**공식 구현 상태:** [공식 저장소](https://github.com/zju3dv/GURecon/tree/9aa519e13a04efad64f73c852467e49fa56996a6)의 recursive tree와 Readme를 확인했다. 조회한 main에는 README·mesh assets 등이 있고 학습 코드는 찾지 못했다. 이는 구현 대조의 한계이며 방법의 실패가 아니다. 프로젝트 페이지의 web 조회 오류는 HTTP 직접 읽기로 해결하여 공식 repo 연결을 확인했다.

**우리 질문:** 다중뷰 증거가 별도 기하 신뢰를 얼마나 설명하는가. 작은 planar patch 근사·가시성·반복무늬가 깨지는 조건을 확인해야 한다. 공통 bias에 대한 일반 보증이나 임의 외부 prior 갱신의 성공은 미확인이다. GT 없는 학습을 유지하되 AUSE는 평가 GT로만 계산한다. 낮은 AUSE가 확률 calibration까지 입증하지 않는다.

## 4. ACMP — 평면 prior와 사진 증거의 단순한 결합도 강한 비교다

**입출력:** calibrated images에서 얻은 credible correspondences→triangulation 기반 planar hypotheses→depth/normal 및 fused point cloud. 외부 기존 기하 입력이 원방법의 필수는 아니다.

**원문:** [AAAI 원문 pp.12517–12521, Figures 2–3 및 실험](https://cdn.aaai.org/ojs/6940/6940-13-10169-1-10-20200525.pdf). 무텍스처에서 평면 prior로 보완하고, 사진 일치가 충분한 비평면 부분에서는 잘못된 평면 제안을 수정하도록 비용을 구성한다. 시선 선택과 가시성 추정도 포함한다. 부정확한 단순 평면 모델의 blocking artifact는 제안한 결합이 겨냥해 개선한 문제이며, 완성 방법의 공통 실패로 분류하지 않는다.

**공식 코드:** `574c8e078b6f7bd93237bd180d46f5adf1169a19`의 [ACMP.cpp](https://github.com/GhiXu/ACMP/blob/574c8e078b6f7bd93237bd180d46f5adf1169a19/ACMP.cpp#L432) `SetPlanarPriorParams`, `CudaPlanarPriorInitialization`과 [저장소 구조](https://github.com/GhiXu/ACMP/tree/574c8e078b6f7bd93237bd180d46f5adf1169a19)를 확인했다. CUDA 비용식 전체 동등성·런타임은 미감사다.

**직접성·남는 질문:** '기하=구조, 영상=세부'라는 보편 역할을 강제할 근거가 아니다. 본 방법의 유리한 국소 조건을 설명하는 전략이다. 오래되거나 상세한 외부 geometry를 보존하면서 교정하는 성능은 범위 차이가 있다. 외부 planar prior를 넣는다면 adaptation이며, 영상 파생 감독을 더 잘 만드는 ACMP 계열의 도입만으로 후단 문제가 해결되는지도 먼저 확인할 가치가 있다.

## 5. SPARF — 정합을 confidence 실패로 오진하지 않는 비교

**입출력·가정:** sparse RGB·noisy poses·사전학습 matcher의 대응/confidence→갱신 pose와 radiance field. [원문 §4.1–4.3 및 §5](https://openaccess.thecvf.com/content/CVPR2023/papers/Truong_SPARF_Neural_Radiance_Fields_From_Sparse_and_Noisy_Poses_CVPR_2023_paper.pdf)는 현재 rendered depth와 pose를 재투영 제약에 사용하고, 후속 depth consistency로 정제한다. sparse/noisy pose의 성능 개선을 보고한다. 단계가 있어도 geometry→projection→pose/geometry 피드백이 존재한다.

**공식 코드:** `91e633b708c9468cd64aa45934acdc9e781471c1`의 [corres_loss.py](https://github.com/google-research/sparf/blob/91e633b708c9468cd64aa45934acdc9e781471c1/source/training/core/corres_loss.py#L29)에서 `CorrespondencesPairRenderDepthAndGet3DPtsAndReproject`의 current poses 및 rendered depth 경로를 확인했다. [README](https://github.com/google-research/sparf/blob/91e633b708c9468cd64aa45934acdc9e781471c1/README.md)는 많은 시선의 전수 대응 계산 시 메모리 위험을 명시한다.

**우리 추론:** 영상 pose 오차와 외부 geometry의 frame 오차는 별개 변수다. SPARF 성공을 prior 정합 해결의 증거로 바꾸지 않는다. 동일한 비-GT 정합 결과를 모든 방법에 주는 비교와, 정합 갱신을 모든 비교군에 동등하게 허용하는 별도 비교가 필요하다. 더 나은 대응/정합만으로 문제가 사라지면 새로운 감독 제어가 원인 해법이라는 주장을 축소한다.

## 6. 확인 범위

2026-09-10에 논문 본문 및 명시한 공식 소스를 읽었다. 논문 간 표의 절대값을 순위표로 합치지 않았다. 새 프로젝트 코드나 방법 실험을 실행하지 않았다. 저자 결과는 JointBuildGS 결과가 아니며 문헌의 GT RGB라는 표현은 관측 영상 표기를 뜻할 때가 있다. 우리 새 설계에서 참조 3D geometry는 평가 전용이다.
