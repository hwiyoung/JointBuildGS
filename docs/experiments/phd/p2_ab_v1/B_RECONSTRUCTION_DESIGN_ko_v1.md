# B — 판단을 고정한 P2 재구성 설계와 실행 계약

2026-09-06. 독립 B 개발 작업. `scientific_verdict: null`.

선택한 후보의 원점과 소속을 평면 Gaussian으로 옮기고, 현재 영상으로 외관을
맞춘다. 기하를 움직일 수 있는 성분과 범위가 인계된 경우에만 구조와 세부를
변형한다. 갱신 뒤에 같은 규칙으로 읽은 표면의 이동·소실·범위 침범을 검사한다.
이는 source 선택을 GS 안에서 다시 하는 절차가 아니다.

## 1. 입력과 표현

A의 `selected_geometry`는 `candidates.npz`의 정확한 `candidate_index`를 가리킨다.
IMAGE/PRIOR/FUSION 모두 이 좌표·법선만 읽는다. 전체 셀 원점으로 몰래 넓히지
않는다. FUSION은 A가 검정한 결합 후보를 그대로 사용한다. B의 원점 thinning은
후보·단위 내 0.2 m voxel당 최초 원행, 최대 64개이며 원점·소스·unit 소속을 저장한다.
이는 렌더 표현 규모이고, 새 면의 현재 사용 승인이나 새로운 독립 표본이 아니다.

각 Gaussian은 기준점 `p_i`, source patch/후보 소속, 국소 기준 법선 `n_i`, 접선
기저, 두 평면 크기, 불투명도, SH0 색을 가진다. 법선은 A의 원후보 법선이다.
평면 두 크기는 같은 후보 내 최근접점 간격에서 정하고, 법선 방향 두께는
gsplat의 planar representation으로 둔다. FUSION 원소를 두 출처로 중복 배치하지 않는다.
참조 UAS와 LoD2 RoofSurface/Z는 초기화·표본화·크기 결정에 들어오지 않는다.

유한 footprint인 Gaussian은 점 지지보다 넓다. 따라서 현재 실행의 footprint와
추출 표면은 `conditional_finite_footprint_not_certified_surface`다. 이 표현을
현재시점 면적 채택으로 세지 않는다. strict handoff가 ABSTAIN이면 strict 산출
기하는 없고, 측정된 conditional handoff의 개발 산출만 별도 보존한다.

## 2. 구조·세부와 허용 변수

같은 선택 후보의 국소 좌표를 `(u_i,v_i)`라 하고 `H=[1,u,v]`를 만든다.
구조 변수 `β`는 후보 전체의 거친 offset과 slope를, detail 변수 `d`는
그 affine 성분으로 다시 설명되지 않는 작은 변형을 맡는다.

\[
 h=H\beta+(I-HH^+)d,\qquad p_i(G)=p_i^0+e_i h_i.
\]

`H^+`는 Moore–Penrose 역행렬이다. `Hᵀ(I−HH⁺)d=0`이므로 detail이 구조의
offset/tilt를 중복 표현하지 않는다. 이 연산은 변수의 중복을 없애며, 세부의 현재
관측 지지를 새로 제공하지 않는다. 구조와 세부를 나누는 것 자체도 독창성 주장이 아니다.

| 성분 | v1 구현 | 근거와 제한 |
|---|---|---|
| 위치 | `p_i^0+e_i h_i` | A가 높이 성분을 검정하므로 실제 P2는 `e_i=scene-Z`; 중력이라는 주장은 하지 않음 |
| 구조 | 후보별 `β∈R³` | offset/두 slope; 후보 간 또는 다른 층 간 공유 없음 |
| 세부 | affine 직교 `d` | 표현 자유도이며 관측으로 새 형상을 검증했다는 뜻은 아님 |
| 면 안 위치·방향 | 고정 | A가 수평변위·법선오차 예산을 인계하지 않음 |
| scale·opacity | fixed arm 고정, prior arm 가변, constrained arm 검사 대상 | 표면에 영향을 주므로 외관 전용 변수로 취급하지 않음 |
| 외관 | SH0 RGB | 현재 train RGB 투영 median으로 초기화 후 L1 적합; 시점 의존 SH/노출 보정은 미구현 |

법선 이동 일반식은 코드에서 제공하지만 높이 검정의 예산을 법선 방향 권한으로
바꾸지 않는다. source normal을 고정한 상태에서 slope 이동을 허용하는 v1은
국소 surfel들의 배치 변형이며, 새로운 경사면 법선의 사용 지지를 확정하지 않는다.

## 3. 최적화와 갱신 검사

모든 arm이 같은 exact A 후보, 같은 Gaussian 초기 상태, 같은 train/eval 역할을
사용한다. 33 train과 11 appearance_eval은 과거 개발 66뷰의 분리이며, exact-937
MVS와도 공유된다. 독립 확증 영상이 아니다. 영상은 후보의 투영 bbox를 padding해
자르고 최대 384 pixel로 줄이며 K를 같은 비율로 변환한다. full source image SHA256과
crop/K를 저장한다. 좋은 점수의 영상만 고르지 않는다.

`surface_texturing`은 source surfel의 geometry/opacity/scale을 고정한 현재 RGB
투영 median이다. 별도 triangle atlas를 최적화한 강한 texture-mapping 재현은 아니다.
`fixed_gs`는 SH0만 학습한다. `prior_loss_gs`는 같은 시작점에서 RGB L1와 초기
렌더 깊이에 대한 metric smooth-L1를 최적화한다. 이는 local prior-loss 구성요소
비교이며 DN-Splatter 원논문 재현이라는 명칭을 쓰지 않는다.

`constrained_gs`는 24 step 외관 warm-up 이후 동일한 기하 변수의 후보 갱신을 만든다.
실제 A의 모든 사용 단위가 conditional displacement budget을 제공하면 그 최소값을
공통 상한으로 사용한다. 하나라도 미확정이면 기하는 고정한다. budget은 A의
유한 높이 가설·고정 카메라·미검증 대응 아래의 조건부 값이지 절대 현재오차 인증이 아니다.
별도 fixture의 임의 budget은 실제 인계 run에 넣을 수 없다.

실제 A-v1의 두 RANGE 인계는 **후보별 단일 scene-Z 이동**만 검사했으므로 이
실행의 constrained arm은 `β`의 offset 한 개만 갱신하고 slope/detail/scale/opacity는
고정한다. 일반 구조·세부 변수는 prior-loss 비교와 수학적 gauge 검증에 구현되어
있지만, 이번 A 인계를 그 전체 자유도의 권한으로 넓히지 않는다.

매 geometry step은 (1) 변수와 Adam moment 저장 → (2) 후보 update →
(3) 모든 train view의 고정 추출 표면 검사 → (4) 모두 통과하면 채택,
아니면 geometry와 optimizer moment 복원 순서다. SH0는 표면을 바꾸지 않아
색 update를 유지한다. 평균 loss가 작아도 단 하나의 ray가 범위를 넘거나
표면이 사라지면 허용 결과로 처리하지 않는다.

## 4. 표면 정의·경계·증감

이 실행의 `S_V(G)`는 고정한 카메라 집합 V에서 gsplat `RGB+ED` expected camera-Z를
alpha≥0.5인 pixel center ray로 역투영한 surfel 표본 집합이다. 원 Gaussian
중심 거리로 표면 보존을 판정하지 않는다. 초기·매 갱신·최종에 같은 depth/alpha
규칙을 쓰고, 평가뷰는 갱신 검사나 학습에 쓰지 않는다.

| 검사 | 고정 분모와 계산 |
|---|---|
| 위치 | 초기·최종 모두 존재하는 고정 pixel ray의 최대 `|D−D0|`; 직접 `max|h|`도 예산 이내 |
| 소실 | 초기 alpha≥0.5이고 최종은 미달인 pixel 수; 사라진 위치를 좋은 오차의 분모에서 제거하지 않음 |
| 범위 침범 | 초기 alpha<0.5인데 최종에서 새 표면이 된 pixel 수 |
| 경계 | 위 존재 mask 경계가 바뀌면 finite-view strict 검사에서 거부 |
| 법선 | 기준 quaternion 고정; 최종 depth-derived 실제 표면 법선의 동일성 인증은 미완료 |

expected-depth는 여러 surfel의 혼합·alpha에 의존하고 정확한 ray–surfel 교점 또는
연속 표면의 인증과 같지 않다. 추출점을 가장 가까운 원 seed의 unit에 연결하고
`association_distance_m`를 저장하므로 먼 점을 대응 성공으로 숨기지 않는다.
다뷰 duplicate를 독립 표면 면적으로 세지 않으며, 초기/최종과 UAS 실제 오류를 따로 평가한다.

다른 unit/층, ABSTAIN 경계는 v1에서 접합하지 않는다. 같은 현재 면이라는 A의
연결 권한이 없으므로 weld·hole fill·TSDF smoothing으로 사용 범위를 늘리지 않는다.
같은 층의 검증된 접합 권한이 들어올 경우, 대응 edge의 위치/법선 연속성을 비용에
더하고 위 표면·존재 검사를 그대로 적용하는 것이 다음 구현 조건이다.

분할/복제의 규칙은 자식의 실제 footprint를 원 지원 polygon에 검사하고, 원점
소속과 같은 support를 상속한 뒤 동일 렌더 표면 검사로 허용한다. 제거는 남은
Gaussian으로 원 support가 유지되는 경우에만 허용한다. v1 main run에는 support
polygon과 topology allowance가 없으므로 증감은 비활성이다. 단순 출처 태그 상속이나
낮은 opacity만으로 이 권한을 대신하지 않는다. 따라서 이 실행은 증감·접합 효과를
실증한 완성 방법이 아니며, 현재 구현의 구체 한계로 유지한다.

## 5. 비교의 해석과 구현 근거

기하 고정에서도 외관은 개선될 수 있다. prior loss가 영상 잔차와 교환하여 허용 범위를
넘는지, explicit 검사 때문에 세부 개선까지 막히는지 실제 결과로 구분한다. 어느
방법이 현재 geometry를 더 정확히 만드는지는 평가 전용 UAS로 확인하며 source
보존의 성공과 동일시하지 않는다. 출력 누락/유보와 양호 영역 열화를 함께 집계한다.

2DGS의 oriented disk 표현·미분 가능 렌더링·normal/depth regularization은 기존
계산이다([2DGS 원논문](https://arxiv.org/abs/2403.17888)).
gsplat은 별도 라이브러리이며 실제 container의 1.4.0 API를 확인해 기존 repository
renderer를 재사용했다([gsplat API](https://docs.gsplat.studio/versions/1.5.3/apis/rasterization.html)).
DN-Splatter는 depth/normal prior와 meshing의 강한 비교 후보이며, source/representation
adapter를 붙이면 그 확장을 명시해야 한다([공식 코드](https://github.com/maturk/dn-splatter),
[WACV 논문](https://openaccess.thecvf.com/content/WACV2025/html/Turkulainen_DN-Splatter_Depth_and_Normal_Priors_for_Gaussian_Splatting_and_Meshing_WACV_2025_paper.html)).

추가로 pinned DN-Splatter `97588b4` 원코드를 수정하지 않고 96 step 실행했다.
같은 선택 source point와 33/11 crop에 source GS 초기 expected depth와 mask를
adapter로 공급했다. `sensor_depth`는 upstream API 키이며 현재 UAS가 아니다.
normal supervision=`depth`는 렌더 깊이에서 만든 normal consistency이고, 초기
normal은 upstream source-PCA를 사용한다. 초기 scale/opacity·3DGS 표현·optimizer는
본 B solver와 다르다. default SH3 shape를 쓰지만 96 step은 SH-degree 증가 전이다.
이는 source-prior로 확장한 원구현의 짧은 개발 비교이며, 논문 수렴 성능의 재현은 아니다.

코드: `src/phd/p2_ab_v1/reconstruction.py`, `scripts/phd/p2_ab_v1/b_run.py`.
8개 Docker 검증은 strict handoff/ABSTAIN/FUSION exact geometry, source group 보존,
affine gauge, 소실, 침범, 최대값 제약을 확인한다. 실제 결과는 별도 B Technical Return에 기록한다.
