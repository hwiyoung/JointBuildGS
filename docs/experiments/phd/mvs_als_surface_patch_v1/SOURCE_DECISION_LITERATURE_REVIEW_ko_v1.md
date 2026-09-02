# MVS–Existing 3D source 판단 문헌 검토 v1

> **지위: TARGETED LITERATURE REVIEW — DRAFT, NON-CONFIRMATORY.**
> 검색 스냅샷: 2026-09-02. 이 문서는 현재 설계를 위한 표적 검토이며 체계적 문헌고찰의
> 완전성이나 신규성 증명을 주장하지 않는다. 인용은 논문 원문·출판사/학회 공식 페이지·
> 저자 공식 프로젝트 페이지로 제한했다. `scientific_verdict: null`.

## 1. 먼저 내릴 수 있는 판단

문헌은 이미 다음을 각각 강하게 다룬다.

- M3C2 기반 거리와 local level of detection(LoD)에 의한 점군 차이 후보화
- old LiDAR와 newer image-MVS의 변화 탐지 후 제거·융합
- visibility, 품질, 최신성, 공간 연결성을 함께 고려한 mesh piece 선택
- LoD2/ALS prior를 Gaussian 초기화·depth/normal loss·adaptive weight로 쓰는 재구성
- source/depth confidence에 따른 연속 가중
- 정합 불확실성을 명시한 LiDAR–도시모델 정합
- latent switch, robust weight, probabilistic association을 반복 갱신하는 최적화

따라서 **M3C2 사용, patch 생성, adaptive weighting, old LiDAR+new MVS 결합,
반복최적화 자체**는 차별성으로 주장할 수 없다. 현재 설계가 검증해야 할 더 좁은
연구가설은 이시점 이종 3D prior의 `정합 불확실성`, `시간적 유효성`, `source
authority/update permission`, `ABSTAIN`, `계보`, `비열화·오염 계약`을
미분 가능 렌더링 기반 Gaussian 재구성 안에서 함께 다루는 것이 실제로 강한
순차법보다 유용한가이다.

이는 방어 가능한 **후보 공백**이지, 신규성이 이미 입증됐다는 결론이 아니다.

## 2. 가장 가까운 직접 선행

| 문헌 | source 판단 방식 | 판정 후 조치 | 현재 설계에 주는 경계 |
|---|---|---|---|
| [Lague, Brodu & Leroux, M3C2 (2013)](https://nicolas.brodu.net/common/recherche/publications/M3C2.pdf) | 국소 normal 방향의 두 점군 평균 위치 차이와 roughness·sampling에 기반한 confidence interval/LoD | 유의한 차이 위치를 검출 | 거리와 통계적 비교 가능성을 제공하지만 어느 epoch/source가 옳은지, 변화인지 정합오차인지 판정하지 않는다. 그러므로 일회성 후보 생성기로 한정하는 것이 논리적이다. |
| [Wu & Vallet, Image LiDAR based change detection and updating (2026)](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.html) | old LiDAR와 newer aerial dense-matching에서 mesh를 만들고 3D ray tracing으로 변화 탐지 | changed part를 제거한 뒤 point cloud fusion | 데이터 조합과 목적이 가장 가까운 강한 `detect→remove→fuse` 순차 전례다. 반복 GS가 필요하다는 주장에는 반드시 이 계열의 `B_SEQ` 반증 비교가 필요하다. |
| [Wu, Vallet & Demonceaux, Mobile Mapping Mesh Change Detection and Update (2023)](https://arxiv.org/abs/2303.07182) | distance+visibility change detection, 변화 지속성, 품질·시간과 공간적 연결을 고려한 global Boolean mesh mosaicking | 선택된 mesh piece를 경계 stitching으로 연결 | point별 독립 선택보다 연결된 표면 단위 판단과 짧고 일관된 경계가 중요하다는 선례다. patch/graph coherence도 그 자체로 신규하지 않다. |
| [GS4Buildings (2025)](https://isprs-annals.copernicus.org/articles/X-4-W6-2025/249/2025/) | LoD2 모델에서 Gaussian을 초기화하고 ray-cast prior depth/normal로 2DGS를 감독 | 구조 일관성과 건물 완전성을 높이는 prior-guided reconstruction | LoD2+항공영상+GS 자체가 이미 직접 전례다. 이 논문과의 차이는 prior 강도 조절이 아니라, stale/misaligned prior의 현재성·authority·reject/abstain을 분리 검증하는 데 두어야 한다. |
| [GeoGS (2026)](https://www.sciencedirect.com/science/article/pii/S0924271626003588) | 외부 도시 기하를 global structural anchor로 사용하고 visual-depth refinement와 dual-gated adaptive weighting으로 local detail을 조절 | 희소 view 도시 재구성에서 구조 보존과 세부 정제 | global/local 결합과 adaptive weighting은 이미 비교 대상이다. 공식 원문을 기준으로 explicit stale/change rejection과 abstention의 유무를 추가 대조해야 하며, 확인 전에는 부재를 단정하지 않는다. |
| [CDGS (2024)](https://isprs-archives.copernicus.org/articles/XLVIII-2-W7-2024/189/2024/index.html) | monocular depth를 sparse SfM depth에 정렬하고 RGB/depth/SfM의 multi-cue confidence로 depth loss를 동적 조절 | 신뢰도가 높은 depth supervision을 더 강하게 반영 | 영상/depth confidence 기반 연속 가중의 직접 비교다. image confidence 또는 adaptive weight만으로는 source authority·temporal validity·ABSTAIN의 차별성을 만들 수 없다. |
| [L2M-Reg (2026)](https://www.sciencedirect.com/science/article/pii/S0924271626000560) | LoD2의 일반화 불확실성을 고려한 plane correspondence와 2D–3D 분리 정합 | building-level LiDAR–model registration | 정합과 model uncertainty를 분리하는 것 자체가 최신 직접 전례다. 정합 잔차를 곧바로 시간 변화나 prior 기각으로 해석하면 안 된다. |

위 표의 논문들은 하나의 동일한 문제를 푸는 방법 목록이 아니다. 각 논문이 다루는
source 종류, epoch, 출력, 정답 조건이 다르므로, 표는 개별 기제를 현재 설계의
비교축으로 배치한 것이다.

## 3. 다른 문헌의 source 판단 방식 분류

### 3.1 통계적 차이 검정

M3C2 계열은 signed distance가 국소 변동과 sampling을 고려한 LoD를 넘는지를
판단한다. 장점은 3D 표면 방향과 불확실성을 함께 보며 단순 nearest-neighbor
distance보다 해석 가능하다는 점이다. 한계는 다음과 같다.

- `significant discrepancy`는 **source truth**가 아니다.
- source가 한쪽에만 있는 영역은 변화, 가림, sampling 부족, reconstruction failure를
  자체적으로 구분하지 못한다.
- registration covariance가 빠지면 정합오차를 변화로 오인할 수 있다.

따라서 본 설계에서는 M3C2를 반복 가중치가 아니라 `compatible / discrepancy /
MVS-only / prior-only / not-comparable` 후보지도의 근거로 한 번만 사용한다.

### 3.2 visibility·ray tracing 기반 비대칭 판정

Wu & Vallet 계열은 두 epoch의 mesh와 sensor ray를 이용해 단순 거리뿐 아니라
보였어야 하는데 없는 표면, 가림 때문에 비교할 수 없는 표면, 양쪽에서 일치하는
표면을 구분한다. 이는 특히 `MVS_ONLY_SUPPORT`와 `PRIOR_ONLY_SUPPORT`를 곧바로
신규/철거로 읽지 말고 current camera visibility와 free-space를 확인해야 한다는
근거다.

### 3.3 품질·최신성·공간 일관성을 포함한 graph 선택

[Mobile Mapping Mesh Change Detection and Update](https://arxiv.org/abs/2303.07182)는
mesh 조각의 품질과 acquisition time뿐 아니라 경계가 과도하게 복잡해지지 않도록
global Boolean optimization과 stitching을 사용한다. source 판단이 개별 점의
최저 잔차만 고르는 문제가 아니라 **국소 표면의 연결성과 seam 비용**을 포함한
구조적 선택 문제라는 근거다. 다만 공간 smoothness가 강하면 실제 작은 변화까지
지울 수 있으므로 raw relation core를 보존하고 patch purity·작은 fragment를 별도로
보고해야 한다.

### 3.4 confidence-aware 연속 가중

[CDGS](https://isprs-archives.copernicus.org/articles/XLVIII-2-W7-2024/189/2024/index.html),
[GS4Buildings](https://isprs-annals.copernicus.org/articles/X-4-W6-2025/249/2025/),
[GeoGS](https://www.sciencedirect.com/science/article/pii/S0924271626003588)는
각기 depth confidence, LoD2 depth/normal supervision, global/local 구조 prior와
adaptive weighting을 통해 불균일한 evidence를 최적화에 반영한다. 이 계열은
`B_FW`와 `B_CW`의 강한 근거다. 그러나 하나의 낮은 weight는 측정 품질 저하,
정합 불확실성, temporal invalidity, 다른 source의 우월성을 구분해 설명하지
못할 수 있다. 본 설계에서는 이를 `q`, `z`, `R`, `pi`로 분해해 검증한다.

### 3.5 정합 불확실성의 별도 추정

[L2M-Reg](https://www.sciencedirect.com/science/article/pii/S0924271626000560)는
LoD2 model uncertainty를 고려하고 2D–3D 정합 성분을 분리한다. 이에 따라 source
결정 전에 적어도 다음을 분리해야 한다.

1. source 자체의 측정오류
2. 좌표 정합과 그 불확실성
3. 목표시점에서 prior가 여전히 유효한지
4. 유효한 source 중 누가 해당 자유도를 갱신할 권한이 있는지

하나의 M3C2 residual이나 photometric residual로 이 네 원인을 동시에 판정하면
식별 문제가 생긴다.

### 3.6 latent switch·robust responsibility의 반복 갱신

반복 중 source 책임과 geometry를 번갈아 갱신하는 구조도 새로운 최적화 형식은
아니다.

| 선행 | 반복 기제 | 현재 설계에 주는 의미 |
|---|---|---|
| [Switchable Constraints](https://www.tu-chemnitz.de/etit/proaut/en/research/robustslam.html) | 잠재 switch를 상태와 함께 최적화해 잘못된 제약을 약화/제거 | prior 제약별 참여 변수를 두는 구조적 선례. 단 switch가 temporal validity나 authority를 자동 설명하지는 않는다. |
| [Graduated Non-Convexity for Robust Spatial Perception (2020)](https://arxiv.org/abs/1909.08605) | robust weight와 geometry를 단계적으로 갱신해 outlier rejection | 연속 재가중·강건 기각 자체는 기여가 아니라 baseline/이론 선례다. |
| [EM-Fusion (ICCV 2019)](https://openaccess.thecvf.com/content_ICCV_2019/html/Strecke_EM-Fusion_Dynamic_Object-Level_SLAM_With_Probabilistic_Data_Association_ICCV_2019_paper.html) | probabilistic data association과 scene/object 상태를 EM 방식으로 교대 갱신 | soft source responsibility와 geometry 교대의 직접적인 구조적 유사성. |
| [BundleFusion](https://graphics.stanford.edu/projects/bundlefusion/) | dense correspondence와 전역 pose/geometry를 반복 재최적화 | 새 evidence가 들어올 때 전역 재판단·재구성하는 전례. 반복의 정확도 이득과 계산비용을 함께 봐야 한다. |

따라서 `source decision → Gaussian reconstruction → rerender → source decision`은
합리적인 연구 설계지만, 반복 구조 자체가 신규성은 아니다. `B_SEQ` 대비 실제
추가가치, 수렴, action flip, 계산·메모리 비용을 검증해야 한다.

## 4. source 판단 cue family

아래 분류는 여러 선행을 현재 문제에 맞게 종합한 설계표다. 어느 한 논문이 모든
cue를 사용했다는 뜻은 아니다.

| cue family | 관측값 예 | 답하는 질문 | 오용 방지 |
|---|---|---|---|
| 3D compatibility | M3C2 signed distance/LoD, point-to-plane, normal angle, boundary offset | 두 source가 같은 표면을 지지하는가 | 차이가 곧 변화/정답은 아님 |
| coverage·visibility | view count, incidence, occlusion, ray free-space, silhouette | 차이를 current view에서 실제로 확인할 수 있는가 | 관측 부재는 prior 현재성의 증명이 아님 |
| source measurement quality `q` | density, local roughness, normal stability, MVS confidence, sensor precision | source가 해당 기하 성분을 얼마나 정밀하게 측정하는가 | precision과 currentness를 섞지 않음 |
| registration state | translation/rotation/vertical uncertainty, patch residual pattern | source가 같은 좌표계에서 비교 가능한가 | bias를 temporal change로 오인하지 않음 |
| image explanation | RGB residual, multi-view consistency, rendered depth/normal, image/geometry edge alignment | source geometry가 현재 영상을 일관되게 설명하는가 | photometric fit이 3D 정확도를 보장하지 않음 |
| temporal validity `z` | visible contradiction, persistence across views, expected/observed free-space | prior 표면이 목표시점에도 존재한다고 볼 수 있는가 | 가림·무텍스처이면 `UNIDENTIFIABLE` |
| patch/graph coherence | adjacency, planarity, label purity, seam length | 독립 점 결정을 연결된 표면 행동으로 만들 수 있는가 | 작은 실제 변화를 smoothing하지 않음 |
| choice risk `R` | action별 예상 geometry error와 contamination cost | IMAGE/PRIOR/FUSION 중 어느 선택의 위험이 낮은가 | calibration 없이 raw score 비교 금지 |
| authority·abstention | source epoch/lineage, update permission, abstain cost | 낮은 위험이어도 현재 형상을 바꿀 권한이 있는가 | 책임과 Gaussian 연산을 분리 |

권장 판정 순서는 `비교 가능성 → 정합 → 관측 가능성 → 측정 품질 → temporal
validity → action별 risk → authority/abstain`이다. source action은 patch 또는
안정된 surface unit에서 정하되, height·normal·boundary처럼 기하 자유도별 책임이
다를 수 있음을 허용한다.

## 5. 반드시 포함할 공정 비교법

| ID | 비교법 | 검증 질문 |
|---|---|---|
| `E2` | direct current-image MVS→동일 read-out | 제안 GS 결과가 현재 MVS 제품 기준을 비열화시키는가 |
| `B_I` | image-only current GS | external prior 없이 가능한 reconstruction인가 |
| `B_P` | prior-only read-out | prior 자체가 이미 목적 출력에 충분한가 |
| `B_PR` | registered-prior-only | 이득이 단순 정합만으로 설명되는가 |
| `B_U` | image/prior 단순 union | source 판단 없는 결합의 오염 비용은 얼마인가 |
| `B_FW` | fixed-weight prior-as-loss | 고정 prior 유도로 충분한가 |
| `B_CW` | confidence/adaptive-weight prior | CDGS/GeoGS 계열의 연속 가중으로 충분한가 |
| `B_SEQ` | `align→candidate→patch→decide once→fuse/reconstruct` | 반복 feedback이 정말 필요한가 |
| `M_ALT` | `decide↔Gaussian reconstruct↔rerender` | 판단과 geometry의 상호의존이 추가가치를 주는가 |
| `O_LOCAL` | score-only local oracle | 국소 source 선택의 달성 가능한 상한이 존재하는가 |

`O_LOCAL`은 평가 reference만 사용하는 상한이며 method feature, 학습 label,
임계값 선택에 넣지 않는다. `B_SEQ`와 `M_ALT`는 다음을 정확히 맞춰야 한다.

- 동일한 frozen M3C2 relation map과 surface patch
- 동일 camera, source renderer, cue, risk estimator, permission rule
- 동일 초기 Gaussian과 총 optimization/compute budget
- 동일 출력 read-out과 held-out/non-degradation 평가
- 유일한 차이는 재렌더 feedback에 따른 source 재판단 여부

`B_SEQ`가 같거나 더 좋으면 반복법을 제거하는 것이 연구적으로 올바른 결론이다.
`B_CW`가 같거나 더 좋으면 복잡한 source authority model을 단순화해야 한다.
`B_P`가 충분하면 GS 경로의 실용적 필요성부터 다시 검토해야 한다.

## 6. 박사 방법론의 차별성 경계

### 차별성으로 내세우면 안 되는 항목

- M3C2를 사용해 차이영역을 찾는 것
- 파편화된 core를 connected patch로 묶는 것
- source confidence를 adaptive weight로 바꾸는 것
- old LiDAR와 new image-MVS를 결합하는 것
- source 변수와 geometry를 반복해서 최적화하는 것
- GS에 depth/normal/LoD2/ALS prior를 주입하는 것

### 검증할 가치가 있는 좁은 결합가설

박사 방법론 후보로 방어할 수 있는 중심은 다음 요소의 **결합과 검증 계약**이다.

1. 이시점·이종 3D prior에 대해 source error, registration uncertainty, temporal
   validity, source authority를 분리한다.
2. `IMAGE / PRIOR / FUSION / ABSTAIN` 책임을 `KEEP / CORRECT / SPAWN / PRUNE /
   NO-UPDATE` Gaussian 연산과 분리한다.
3. prior 또는 영상 source가 선택돼도 3D seed·다시점 지지·현재성·허용 자유도를
   통과한 경우에만 실제 geometry update를 허가한다.
4. Gaussian마다 부모 source, epoch, 정합 이력, 마지막 geometry update, 예상 위험을
   보존한다.
5. 평균 개선뿐 아니라 benign non-degradation, stale-prior contamination,
   pass→fail, abstention risk–coverage와 local oracle gap을 함께 평가한다.
6. frozen one-shot candidate와 강한 `B_SEQ`를 두어, 반복이 안전성 이득을 만들지
   못하면 반복 주장을 철회한다.

이 결합이 실제 연구기여가 되려면 다음 증거가 필요하다.

- controlled `image strength × prior validity × alignment` factorial에서 원인별
  action이 예상대로 바뀌는 기제 검증
- real benign 조건의 non-degradation과 independent real conflict의 contamination 억제
- `B_FW`, `B_CW`, `B_SEQ` 대비 geometry·risk–coverage·비용의 사전 정의된 개선
- source action calibration, 수렴/flip, patch 단위와 더 단순한 단위의 비교
- 오류가 발생했을 때 source 판단, permission, Gaussian operation, rendering 중
  어느 단계가 원인인지 추적 가능한 계보
- 제출 전 데이터베이스·검색식·포함/제외 기준을 고정한 추가 systematic search

이 증거가 없으면 표현은 “source-aware 비열화 융합을 위한 설계가설”로 유지해야
하며, 자동 안전 융합이나 신규성이 입증됐다고 서술하지 않는다.

## 7. 1차 출처 목록

- Lague, D., Brodu, N., & Leroux, J. (2013), [Accurate 3D comparison of complex topography with terrestrial laser scanner: the M3C2 method](https://nicolas.brodu.net/common/recherche/publications/M3C2.pdf).
- Wu, T., & Vallet, B. (2026), [Image LiDAR based change detection and updating for urban 3D reconstruction](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.html).
- Wu, T., Vallet, B., & Demonceaux, C. (2023), [Mobile Mapping Mesh Change Detection and Update](https://arxiv.org/abs/2303.07182).
- Zhang, Q., Wysocki, O., & Jutzi, B. (2025), [GS4Buildings: Prior-Guided Gaussian Splatting for 3D Building Reconstruction](https://isprs-annals.copernicus.org/articles/X-4-W6-2025/249/2025/).
- [GeoGS: Geometric Prior-Guided Gaussian Splatting for robust urban reconstruction from sparse views (2026)](https://www.sciencedirect.com/science/article/pii/S0924271626003588).
- Zhang, Q., Wysocki, O., Urban, S., & Jutzi, B. (2024), [CDGS: Confidence-Aware Depth Regularization for 3D Gaussian Splatting](https://isprs-archives.copernicus.org/articles/XLVIII-2-W7-2024/189/2024/index.html).
- Xu, Z., Schwab, B., Yang, Y., Kolbe, T. H., & Holst, C. (2026), [L2M-Reg: Building-level uncertainty-aware registration of outdoor LiDAR point clouds and semantic 3D city models](https://www.sciencedirect.com/science/article/pii/S0924271626000560).
- Sünderhauf, N., & Protzel, P. (2012), [Switchable Constraints for Robust Pose Graph SLAM](https://www.tu-chemnitz.de/etit/proaut/en/research/robustslam.html).
- Yang, H. et al. (2020), [Graduated Non-Convexity for Robust Spatial Perception](https://arxiv.org/abs/1909.08605).
- Strecke, M., Stückler, J., & Cremers, D. (2019), [EM-Fusion: Dynamic Object-Level SLAM With Probabilistic Data Association](https://openaccess.thecvf.com/content_ICCV_2019/html/Strecke_EM-Fusion_Dynamic_Object-Level_SLAM_With_Probabilistic_Data_Association_ICCV_2019_paper.html).
- Dai, A. et al. (2017), [BundleFusion: Real-time Globally Consistent 3D Reconstruction using On-the-fly Surface Re-integration](https://graphics.stanford.edu/projects/bundlefusion/).
