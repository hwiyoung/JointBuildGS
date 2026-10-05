# 관측 근거 기반 source 가중 정책과 단계적 검증 설계 v3

- 작성일: 2026-09-11
- task_id: PHD-LOCAL-SOURCE-WEIGHT-DESIGN-v3
- 상태: DESIGN_COMPLETE / NUMERICAL_CALIBRATION_AND_EXECUTION_BINDING_PENDING
- scientific_verdict: null
- 범위: 사용자가 요청한 후속 방법·검증 설계. 기존 LC main_v2의 18조건과 source·입력·결과·서비스·자동 실행 권한을 변경하지 않는다. 새 방법의 계산·학습은 이번 문서 작성으로 실행하지 않는다.
- 기계 판독 설계: [SOURCE_WEIGHT_POLICY_DESIGN_v3.json](SOURCE_WEIGHT_POLICY_DESIGN_v3.json). 실행기용 config가 아니며 실행 가능 플래그는 false다.
- 최신 사용자 정정 [v3.6 값→가중치](SOURCE_SCORE_TO_WEIGHT_INTENT_ko_v3_6.md): source별 적합도에서 두 감독 계수를 설정하는 함수가 설계 대상이다. 아래 한쪽 source에 전체 계수를 주는 분기는 기존 후보안이며 사용자 확정 주정책이 아니다. 가중 함수와 normal을 활용한 점수 계산을 재검토 중이고 새 실행 결박은 없다.
- [v3.1 보완](MVS_VALIDATION_AND_NOTATION_ko_v3_1.md): MVS/DA3 생성용 G와 판정용 V를 학습 사진 내부에서 분리하며 최종 평가 T를 보존한다. 같은 생성 사진의 NCC는 내부 적합도 진단이다. 결손·거칠기와 정확성의 차이, 변수·지원 판정의 의미를 설명한다.
- 최신 [v3.2 실제 점수 열람·역할 재검토](OBSERVATION_WALKTHROUGH_ko_v3_2.md)는 G/V 분리를 기본 운용의 필수 조건 대신 보조 검사로 한정한다. 기존 입력으로8개 위치의 관측 점수를 단계별로 표시하며 GT 정확성·가중 선택과 구분한다.
- 계보: [v2.4 의도·수식 검토](SOURCE_AND_WEIGHT_DESIGN_REVIEW_ko_v2_4.md), [v2.5 문헌·픽셀 감사](SOURCE_RELIABILITY_AND_PIXEL_VALIDATION_ko_v2_5.md), 연구 헌장·DEC-P1-025. 현재 LC 분석은 개발 증거이며 canonical E1–E6와 별도다.

## 1. 먼저 검증할 주장

목표는 다음 세 가지를 순서대로 입증하는 것이다.

1. 허용된 현재 영상만으로, prior/영상 depth 후보 중 더 적절한 후보를 구별할 관측 근거가 있는가?
2. 그 근거가 감독의 배분과 강도에 의도대로 반영되고 실제 Gaussian 최적화까지 전달되는가?
3. 단순 전역 계수 감소보다 같은 장소의 필요한 수정을 늘리면서 기존 올바른 표면의 손상을 줄이는가?

1이 성립하지 않으면 정교한 weight 함수만으로 문제를 해결했다고 주장하지 않는다. 1·2가 통과해도 3은 별도 성능 평가다. 여기서 '정답에 가까운 가중치'는 GT를 사용해 weight를 맞춘다는 뜻이 아니라, GT 없이 고정한 관측 판단과 배분을 평가에서 검증한다는 뜻이다.

현재 LC의 큰 불일치→image 우선 규칙을 대칭적 관측 검사로 대체하는 것이 핵심 후보 변경이다. 불일치는 검사 위치/두 후보 간 거리를 설명하는 변수로 유지하되, 그 값 자체를 image 신뢰도라고 사용하지 않는다.

사용자 정정 [v3.5](SOURCE_SCORE_NORMAL_EXTENSION_ko_v3_5.md): source별 점수와 판단 구조를 유지하며 각 source normal을 점수 계산에 활용하는 방향을 검토한다. AGS식 Prior 필터로 주설계를 전환한다는 뜻이 아니다.

## 2. 사진에서 무늬·모서리를 비교하는 구체적인 방법

### 2.1 동일 ray에서 두 표면 가정을 만들기

Reference 카메라 i의 픽셀 p와 주위 작은 패치를 고정한다. 후보 s는 P(prior) 또는 I(image: 첫 단계 DA3, 후속 비교에서 MVS)다. World→camera 규약이 Xc=R_i Xw+t_i이고 depth가 camera-Z이면:

\[
X_s(u)=R_i^\top\{D_{s,i}(u)K_i^{-1}\tilde u-t_i\},\qquad
w_{s,ij}(u)=\pi\{K_j(R_jX_s(u)+t_j)\}.
\]

- 단위 길이로 정규화한 ray에 camera-Z를 곱하지 않는다. Ray distance와 camera-Z, world Z는 별개다.
- 원사진의 undistortion, K 해상도, 픽셀 중심 규약, pose, depth 단위·축·유효 mask를 먼저 결박한다.
- 기존 prior의 반 픽셀 ray와 DA3 격자의 차이를 무시해 배열 인덱스만 맞추지 않는다. 공통 격자로 만드는 변환·보간·경계 처리를 새 derived 입력으로 기록하며, 이것만 바뀐 G 대조를 둔다.
- 주후보는 패치의 각 유효 ray를 해당 source depth로 역투영한다. 즉 source의 국소 depth patch 전체가 제안하는 표면을 검사한다. 상수 깊이로 모든 패치를 평행 이동시키거나 현재 GS normal을 빌려 쓰지 않는다.
- 이 비용은 중심 depth 하나뿐 아니라 주변 표면 모양·노이즈에도 영향을 받는다. 중심 높이의 오차만 측정했다고 부르지 않는다. 동일 규약의 국소 평면 적합은 후속 별도 비교안이며 주후보와 혼용하지 않는다.

동일 reference 픽셀 u의 밝기 A(u)=gray(I_i(u))와, 후보 s가 지정한 다른 사진 위치의 밝기 B_s(u)=gray(I_j(w_s(u)))를 비교한다. B는 bilinear sampling하며 사진 밖의 값을0으로 넣어 점수를 만들지 않는다. 재투영 후 후보마다 별도의 위치 이동/정합을 허용하면 잘못된 depth도 좋은 점수를 얻을 수 있으므로 주검사에서는 금지한다.

### 2.2 ZNCC로 밝기 패턴을 수치화하기

동일한 유효 표본 집합 M에서:

\[
\rho_s =
\frac{\sum_{u\in M}(A(u)-\bar A)(B_s(u)-\bar B_s)}
{\sqrt{\sum_{u\in M}(A(u)-\bar A)^2
       \sum_{u\in M}(B_s(u)-\bar B_s)^2}},
\qquad c_s=(1-\rho_s)/2.
\]

높은 rho, 낮은 c가 더 잘 맞는 패턴이다. 패치 평균을 빼고 대비 크기로 나누므로 일정한 밝기 차이/양의 대비 배율에 덜 민감하다. 그림자 이동·반사·반복무늬까지 해결하는 것은 아니다.

'모서리 비교'는 첫 후보에서 별도 semantic edge 판정을 뜻하지 않는다. 패치 안 밝기가 변하는 위치가 재투영 후 맞는지를 위 점수로 검사한다. 원 패치/후보별 warp/차이 그림을 함께 제시한다. Sobel 경계 그림은 위치 오차를 읽는 보조 표시이며, 별도 가중 edge loss는 주정책에 추가하지 않는다.

Reference 또는 warp 패치의 대비가 너무 작으면 NCC를1로 처리하지 않고 UNRESOLVED_TEXTURE로 남긴다. 한 후보의 warp만 무텍스처인 경우도 조용히 그 후보/시점을 제외하거나 자동 패배로 만들지 않는다. 원인과 지지 집합을 기록하고 주정책의 그 시점 비교는 보류한다. Epsilon은 수치 안정화 수단이지 관측 근거를 만드는 수단이 아니다.

### 2.3 같은 관측으로 비교하고, 쉽게 속는 조건을 따로 검사하기

- 이웃 카메라는 사진 점수를 보기 전에 train-only SfM overlap·카메라 기하로 결정한다. P/I에 같은 이웃 목록을 제공한다.
- 두 후보가 같은 reference 패치 표본과 동일 이웃에서 비교 가능한 공통 mask를 갖도록 한다. 후보별 원래 지원량·제외량도 별도 저장한다. 한 후보의 나쁜 관측만 삭제하여 평균 비용을 낮추지 않는다.
- 실제 가림은 모델 자체의 depth 가시성과 구분한다. MODEL_SELF_VISIBILITY는 현재 표면의 실제 가시성 인증이 아니다. MVS depth로 prior만 가리는 비대칭 veto를 쓰지 않는다.
- 첫 가시 지원 후보는 현재 사진의 독립 SfM 대응 또는 후보 warp와 별도로 구한 양방향 패치 대응이다. 두 후보가 예측한 위치를 동일 대응과 비교하고, 가시성의 근거·오대응 위험을 기록한다. Sparse 대응이 없는 주변 픽셀까지 자동 인증하지 않는다. 후보 warp의 역변환만으로 만든 cycle이나 source 자신의 depth 일치는 독립 지원으로 세지 않는다. 큰 MVS 결손에서 이 관측도 없으면 prior fallback으로 남는다.
- 검증된 독립 대응과 후보 투영의 위치 차이는 후보에 불리한 기하 근거로 보존한다. 이 차이를 이유로 그 후보를 공통 mask에서 제거하면 틀린 후보가 비교에서 사라진다. 대응 자체가 미확인인 UNKNOWN과, 확인된 관측을 후보가 설명하지 못한 MISMATCH를 구분한다. 사진 밖/실제 앞가림 등으로 관측을 비교할 수 없는 경우만 지원 부족으로 기록한다.
- 가림/경계/다른 표면 대응을 배제할 근거가 부족하면 UNRESOLVED_VISIBILITY다. 두 후보 중 하나의 가시성이 알려지지 않은 것을 나쁜 photometric 비용과 같게 취급하지 않는다.
- 여러 장이라는 수뿐 아니라 서로 다른 시차 방향/카메라 묶음의 지지가 필요하다. 같은 근접 카메라의 여러 쌍을 독립 증거 수로 세지 않는다.
- 후보 사이 투영 차이가 pose·보간 오차보다 작으면 사진이 둘을 구별할 수 없을 수 있다. 비용 차이가 있어도 선택을 보류한다.
- 이웃별 승자가 뒤집히거나, 후보 주변 깊이의 비용 곡선이 평평하거나 동등한 여러 최소값을 가지면 선택을 보류한다. 깊이 perturbation은 민감도 검사이며 바뀐 후보를 자동 오답으로 라벨하지 않는다.
- A→B→A에서 같은 후보 warp와 그 역변환을 사용하면 항등식에 가깝다. 독립적인 B의 대응/깊이 없이 이 cycle을 검증 근거로 세지 않는다. 같은 DA3 batch의 공통 편향은 독립 depth cycle도 통과할 수 있다.
- MVS 결손이 크면 이 검사도 충분한 근거를 못 얻을 수 있다. 그 영역을 DA3로 자동 채우거나 image가 맞다고 결정하지 않는다.

### 2.4 비용 집계와 선택 조건

같은 유효 이웃 집합 J에서 E_s=median_j(c_sj), paired 차이는 Delta=median_j(c_Pj-c_Ij)로 기록한다. E_P-E_I와 paired median 차이는 일반적으로 같지 않으므로 혼용하지 않는다.

IMAGE_SUPPORTED는 아래 모두를 만족할 때만 부여한다.

1. 공통 유효 패치·이웃 수·관측 기하·가시성·대비 gate 통과.
2. E_I가 절대 적합도 문턱 이하.
3. Delta가 양의 선택 margin보다 큼.
4. 이웃별 차이의 충분한 비율이 같은 승자를 지지하고, 카메라 묶음별/pose 민감도 검사에서 승자 유지.
5. 후보 차이가 사진에서 구별 가능하고, 비용 곡선의 모호성 gate 통과.

PRIOR_SUPPORTED는 P/I를 바꿔 같은 조건으로 판정한다. 둘 다 절대 적합도가 나쁘면 상대 순위만으로 승자를 내지 않는다. 두 source가 충분히 지지되며 깊이 차이도 사전에 정한 공통 표면 허용범위 안이면 OBSERVED_AGREEMENT다. 깊이가 상당히 다른데 점수만 비슷한 경우는 agreement가 아닌 unresolved다.

이는 보정된 정답 확률이 아니다. Source 순위가 나오는 영역과 판단할 수 없는 영역을 함께 출력한다.

## 3. 가중 정책의 수식

### 3.1 배분과 총강도를 구분하는 좌표계

기존 G와 같은 source별 유효 target 집합 S_P,S_I, N_s=|S_s|를 사용한다. 유한 양수 target이라는 '존재'와 위 관측 gate를 통과한 '지지'는 별개다. 수치 오류 prediction을 조용히 제외해 분모를 줄이지 않으며 별도 실패로 기록한다.

각 카메라/step에서:

\[
c_P(p,t)=\frac{\lambda_P\,1_{S_P}(p)}{N_P},\quad
c_I(p,t)=\frac{\lambda_I(t)\,1_{S_I}(p)}{N_I},\quad
B=c_P+c_I,\quad q_0=c_I/B.
\]

빈 source는 해당 c를0으로 두고 계산하지 않는다. B=0이면 q는 undefined다. q는 원래 LC의 배율 a와 달리, 분모·전역 계수가 이미 반영된 최종 image 비중이다.

\[
L_D=\sum_p s_p\{(1-q_p)|\hat D_p-D_{P,p}|+
                         q_p|\hat D_p-D_{I,p}|\}
   =\sum_p k_{P,p}|\hat D_p-D_{P,p}|+
             k_{I,p}|\hat D_p-D_{I,p}|.
\]

k_P=s(1-q), k_I=sq다. 이미 분모를 c에 포함했으므로 바깥에서 평균을 한 번 더 취하지 않는다. 결손 target의 잔차는 평가하지 않는다. 정책/mask/score는 고정 입력에서 계산해 detach하고, rendered depth와 Gaussian의 미분 경로는 유지한다.

### 3.2 주정책: 근거 있는 선택에서는 예산 보존, 보류에서는 증폭 없는 prior 유지

첫 검증은 해석하기 쉬운 명시적 분기로 한다. 현재 큰 불일치 대신 soft sigmoid 하나를 바로 넣는 안은 주정책으로 채택하지 않는다.

| 입력/관측 상태 | 최종 (k_P,k_I) | 의미 |
|---|---|---|
| 두 source 활성, IMAGE_SUPPORTED | (0,B) | depth 총강도를 유지하며 image에 배분 |
| 두 source 활성, PRIOR_SUPPORTED | (B,0) | depth 총강도를 유지하며 prior에 배분 |
| 두 source 활성, OBSERVED_AGREEMENT | (c_P,c_I) | 기존 G와 같은 공통 표면 감독 |
| 두 source 활성, UNRESOLVED | (c_P,0) | 확인되지 않은 image 힘을 제거하고 기존 prior 강도 유지 |
| prior만 존재/활성 | (c_P,0) | prior 기본 유지, 현재 정확성 미확인 |
| image만 존재/활성, 절대 지지 검사 통과 | (0,c_I) | image만 감독; prior와의 상대 순위는 없음 |
| image만 존재/활성, 지지 불충분 | (0,0) | depth 감독 유보 |
| 둘 다 없거나 두 계수 모두0 | (0,0) | depth 감독 없음 |

- '활성'에는 lambda>0을 포함한다. lambdaP=0이면 어떠한 분기에서도 prior 감독을 다시 켜지 않는다. prior의 영상 정합을 조사하는 것은 가능하지만 예산을 prior로 넘기는 조건은 비활성이다. Image도0이면 같다.
- 둘 다 존재하나 한 source 계수만0인 ablation에서는 활성 source에 대한 절대 관측 검사만 사용하며, 지원 없는 image에는0, 사용 가능한 prior에는 c_P를 적용한다. 이를 image-only 초기화라고 부르지 않는다.
- UNRESOLVED의 s는 B가 아닌 c_P다. 이것은 의도적인 image 감독 제거이며 '항상 총강도 보존'으로 표현하지 않는다. B 전체를 prior로 넘기는 강화 fallback은 별도 비교 조건이다.
- 두 후보 모두 관측과 충돌해도 사용자 보존 정책에 따라 prior fallback을 쓸 수 있다. 이때 상태를 CONTRADICTED_PRIOR_FALLBACK으로 따로 기록하며 현재성·정확성을 주장하지 않는다.
- Depth fallback은 Gaussian 동결이나 NO-UPDATE를 뜻하지 않는다. RGB·다른 시점·기하 정규화·구조 보호는 계속 작동한다. 실제 이동 제한은 별도 방법 요인이며 이번 주정책에 슬쩍 추가하지 않는다.
- 첫 기제 검사에서는 lambdaP=.005, lambdaI=.05 고정, native 보호를 공통 사용한다. 이 값은 기존 조건과의 연결을 위한 개발 비교값이며 최적 계수 판정이 아니다. 낮은 prior .0005·0 및 release는 첫 단계를 통과한 뒤 별도 요인으로 확장한다.

### 3.3 이 식에서 기대할 수 있는 것과 없는 것

P와 I가 정확히 같은 target이고 agreement 분기를 통과하면 loss와 depth gradient가 기존 G와 정확히 같다. Agreement를 이유로 감독을 자동 감쇠하지 않는다.

반대로 판단 불충분이라 image를 끈 경우에는 두 target이 같아도 총강도가 줄 수 있다. 정확히 일치한다는 이유만으로 사진 관측이 충분했다고 판정하지 않는다. 이 차이는 branch status와 s 지도에 드러나야 한다.

독립적인 scalar depth에 대한 L1에서는 두 target 사이 gradient가 k_P-k_I(또는 부호 반대)다. 두 계수가 같으면 두 target 사이가 평평한 최소 구간이 되며, soft q가 '두 깊이 사이로 원하는 비율만큼 이동'을 보장하지 않는다. 실제 GS는 여러 픽셀과 RGB·정규화·Adam·보호가 결합되므로 q=.8이 image 쪽으로80% 변위라는 뜻은 더더욱 아니다.

신뢰된 winner로 B 전체를 옮기면 원래 source 계수보다 커질 수 있다. 이것이 의도한 감독 배분 변경인 동시에 잘못된 선택을 증폭할 위험이다. 주정책과 동일한 q에 현재 LC 총강도만 적용한 별도 진단으로 강도 효과를 분리한다. L1을 Huber/다른 robust loss로 바꾸는 것은 이 분리 이후의 요인이다.

B 보존은 계수 합 보존이다. 상쇄 이후 signed gradient, RGB와의 실제 경쟁, Adam update 크기까지 보존한다는 뜻은 아니다.

Soft q가 필요하면 주분기들을 검증한 뒤 지원된 영역에서만 score margin→q 변환을 추가한다. T·확률 보정·시간 smoothing을 한꺼번에 추가하지 않는다.

## 4. 가중치 지도를 무엇을 보며 읽을 것인가

### 4.1 기존 v2.5 그림의 정확한 읽는 법

- 첫 행: 원사진 / prior 배율 b_P / image 배율 b_I. 파란색은 해당 배율이 크다는 뜻이다. 파란색 자체가 정확하거나 좋은 선택이라는 뜻은 아니다.
- 둘째~넷째 행: prior 계수 .005 / .0005 / 0.
- 이 세 행의 왼쪽: 분모와 계수 적용 후 image 비중 k_I/(k_P+k_I). 가운데: 총강도 k_P+k_I. 오른쪽: 합성 중간 prediction에서의 dL/d(depth).
- 오른쪽 gradient가 양수면 독립 scalar 경사하강에서는 depth를 줄이는 방향이고, 음수면 늘리는 방향이다. Camera-Z 증가/감소를 world 높이 하강/상승 또는 Gaussian 이동과 동일시하지 않는다.
- Source 결손의 회색과 총강도0으로 비중이 undefined인 회색은 같은 현상이 아니다. 배열의 별도 mask로 확인한다. 총강도 그림의0도 함께 본다.
- 현재 그림의 lambdaI=.05는 진단 시나리오다. 실제 모든 학습 step의 controller 값을 표현하지 않는다.

### 4.2 '잘 됐는가'를 판별할 세 층

| 질문 | 볼 것 | 충분한 판정 근거 |
|---|---|---|
| 정해진 식대로 적용됐나? | 같은 픽셀의 DP/DI, a, b, N, lambda, k, gradient | 독립 계산과 실제 코드의 일치 |
| 의도에 맞게 source를 택했나? | 원 패치·후보 warp·지지/비용·결정 이유 → k/q/s | 관측 근거가 없는 image에 권한을 주지 않는지; 양쪽 승자·보류·agreement 사례 |
| 그 선택이 실제로 도움이 됐나? | 같은 장소의 source 오차·업데이트·GT 거리·수정/손상 | GT는 별도 평가에서만 사용, 동일 참조점 및 같은 카메라 비교 |

기존 P1 A에서는 큰 a와 나쁜 image target의 채택이 함께 관측됐고, P2 C에서는 같은 큰 a가 유리한 회복을 유지했다. 같은 색으로 표시된 두 곳의 가치가 다르다는 것이 색만으로 성공을 판단할 수 없는 이유다. 이 사례는 사후 개발 사례이며 gate 문턱 선정 자료로 쓰지 않는다.

후속 표시의 한 행은 하나의 고정 장소/카메라다. 원사진에 같은 사각형을 표시하고 옆에 reference 패치, prior warp, image warp, 공통 mask, 이웃별 비용표, 결정 상태, q, s/B를 나란히 둔다. 별도 평가 영역에만 reference source 오차와 같은 점의 수정/손상을 표시한다. 픽셀을 누르면 D_P/D_I/차이/N_P/N_I/lambda/k_P/k_I/판정 이유/가림·무텍스처 여부를 읽을 수 있도록 설계한다.

좋은 사례만 고르지 않는다. 모든 결정 상태와 image 우선의 성공·손상, prior 유지의 성공·미수정, 넓은 MVS 결손, 경계·반사·반복무늬를 고정 방식으로 추출한다. 지원 없는 곳은 빈 결과로 숨기지 않는다. 새 뷰어 구현 완료를 이 설계 문서가 뜻하지는 않는다.

후속 [v3.3 선행근거·지도 전 단계](OBSERVATION_PRECEDENTS_AND_MAP_PLAN_ko_v3_3.md)는 NeuRIS/MVS의 직접 근거와 AGS-Mesh의 normal 기반 감독 필터를 구분하고, 국소 패치 비교를 사진 범위의 관측·판정·가중치 지도로 확장하는 순서를 설명한다.

## 5. 수치 문턱을 정하는 절차

공학적 첫 후보는 grayscale [0,1], bilinear, 9×9 patch, 최대6개 이웃, 공통 유효3개 이상이다. 서로 다른 시차 묶음2개 이상을 요구한다. 이는 개발 시작점이며 논문 최적값 또는 현 장면 검증값이 아니다. 카메라 묶음 정의와 선택 tie-break는 영상/pose만으로 먼저 결정해야 한다.

다음 수치는 현 단계에서 성능값처럼 채우지 않는다: 최소 대비, 절대 ZNCC 비용, margin, 공통 mask 비율, 시차/pose 허용 오차, 공통 표면 깊이 허용 오차, 이웃 지지 비율, 비용 곡선 모호성 문턱. 새 실행 config는 이 값과 선정 receipt가 모두 있어야 만들어진다.

선정 순서:

1. 분석용 train 카메라 목록과 공간 격자를 GT 열람 전에 hash/pose 규칙으로 고정한다. 첫 개발 표본은 지역별 최대6 reference 카메라, stride8 격자다. 기존 A–F는 설명용 별도 층이다.
2. 합성 카메라·알려진 표면·텍스처 fixture로 projection/색공간/경계/가림/노출 변화/반복무늬/저텍스처의 기술적 동작을 검사한다. 합성 진실값은 이 기술 검사 평가 전용이다.
3. 실제 train-only 원사진과 pose 잔차를 이용해 수치 노이즈·재투영 민감도·지원량을 계측한다. SfM 잔차가 source의 정확성을 증명하는 것은 아니다. 실측 pose 불확실성이 없으면 그 한계를 기록하고 민감도 범위를 시험한다.
4. GT 없이 미리 열거한 소수 문턱 후보를 카메라 묶음 간 안정성, 모호한 관측의 보류, 계산량으로 비교한다. 무조건 prior를 택하거나 전부 보류하는 정책도 별도로 드러내기 위해 상태별 coverage를 제시한다.
5. 첫 recipe와 모든 후보·선정 이유·input hash를 고정한 뒤 별도 GT 평가를 연다. Recipe는 GT로 가장 좋은 값을 찾지 않는다. GT를 본 뒤 변경된 recipe는 별도 revision/개발 결과이며 동일 표본을 독립 검증이라고 부르지 않는다.

문턱 선택 알고리즘과 허용 후보 격자는 G0/G1 결과를 보고 GT 없이 별도 사전등록한다. 이 문서만으로 그 절차가 완료됐다고 주장하지 않는다. 기존 .5/2m나 Q50/Q90를 신뢰도 문턱으로 복사하지 않는다.

## 6. 단계별 검증과 다음 단계로 넘어갈 조건

| 단계 | 질문·입력 | 산출물 | 다음 단계 조건 |
|---|---|---|---|
| G0 입력·정합 계약 | train-only 사진/pose, exact prior/DA3, MVS 후보 계보, pixel/ray 규약 | input/camera/split/hash manifest, 왕복 투영·단위·mask fixture | GT/evaluation 사진 누출 없음, 공통 ray 규약 확인, 알려진 변환 오차 범위 통과 |
| G1 관측 점수 기술 검사 | 합성 표면과 GT 없는 고정 실제 패치 | 두 후보 warp/contact sheet, score/support/unknown 표, 선택 recipe freeze | source 이름 교환 대칭, 잘 알려진 합성 조건·보류 실패 처리 통과; 실제 점수가 정의되고 지지량 공개 |
| G2 고정 선택기의 평가 | 봉인 q/state와 별도 평가 reference | source 오류·oracle gap·선택 regret·risk–coverage, 상태별 사례 | GT 누출 없이 계산; 기술 완료와 '유용함'은 별도 판정. 판별력이 없으면 확대를 중단하며, 정책 변경은 별도 개발 revision·새 검증으로 다룸 |
| G3 가중식 검증 | recipe 고정, 실제 target/mask + 합성/저장 prediction | q/s/k 지도, 독립 L1/gradient 검산, 분기표 | 분모/0/NaN/동일target/source 교환/gradient·stopgrad/zero-lambda 검사 통과 |
| G4 실제 Gaussian 전달 | 같은 complete Anchor, optimizer/RNG/camera/controller/보호의 복제 분기 | loss별 parameter gradient, 보호 전후, Adam update, 고정 시점 depth 변화 | gradient 차이가 최종 결합식에 추적 가능하고 상태 동일성 확인; 한 단계가 모두 GT 쪽으로 움직일 것을 요구하지 않음 |
| G5 제한된 최적화 비교 | 고정 입력·recipe·예산, 새 대조군 | 동일 장소 수정/손상·단면·RGB·표면 지표·자원 | 사전 지정 step까지 모두 보고; 실패/무개선도 공개. 일반화/반복 근거 없이 본행렬 확대 결론 금지 |
| G6 확장 검증 | source/계수/보호/반복을 분리한 새 실행 명세 | 독립 장면 또는 명시적 개발 반복, matched controls | 새 명세·자원·평가 계약 결박 후 실행; scientific_verdict는 계속 null |

G2의 GT 평가는 weight 생성/튜닝 경로에서 물리적으로 분리한다. 실행 시스템의 gate는 기술적 완료 여부로만 다음 작업을 관리하고, 성능을 보고 스스로 threshold를 바꿔 재학습하지 않는다.

G2 평가에는 같은 가시 참조 표면과 대응 가능한 픽셀만 사용한다. Reference 공백은 NA로 남기고, 결손 source/미선택/보류를 성공에서 제외해 숨기지 않는다.

- 원 source 오차 e_P,e_I와 공통 지원에서 min(e_P,e_I)를 비교하여 score-only oracle 여지가 있는지 본다. Oracle은 실제 학습 가중치 또는 새로운 GT target이 아니다.
- q 배분 위험 (1-q)e_P+q e_I와 oracle의 차이는 '배분된 source 오차' 진단이다. 이 값은 최종 GS 표면 오차나 두 depth의 융합 결과 오차가 아니다.
- image가 더 정확한 곳/ prior가 더 정확한 곳 각각의 선택률·오선택률, 보류 coverage, 큰 오류 선택률을 보고한다. q나 NCC를 정답 확률로 보정했다고 주장하지 않는다.
- 기하 평가는 camera-Z, world XYZ/표면 거리, visibility와 reference 불확실성을 구분한다. 다른 카메라의 depth 잔차가 같아야 한다는 조건은 두지 않는다.
- G5에서는 동일 reference ID의 기존 성공 유지·새 수정·새 손상·미수정을 모두 보고하고, 연속 거리와 여러 사전 지정 tolerance를 함께 사용한다. 전역 F1만으로 판정하지 않는다.
- 지역/건물 단위 집계와 같은 위치의 단면, held-out native 렌더·ROI를 함께 보고한다. 관측용 train 사진 점수와 held-out appearance 점수는 섞지 않는다.

## 7. 원인과 효과를 분리하는 비교

### 7.1 먼저 weight 수식만 비교

첫 G4는 P1/P2, prior .005, native, lambdaI=.05 고정, 동일 Anchor에서 아래6개 분기를 비교한다. 두 지역 ×6분기 ×1step =12개 독립 기술 분기이며 이번 문서에서 실행하지 않았다. Forward/backward만의 검사와 Adam step은 각각 기록한다.

| 조건 | 바꾸는 것 |
|---|---|
| G-fixed | 새 공통 입력 규약에서 기존 G 식; controller 대신 공통 고정 계수 |
| LC-fixed | 같은 입력·계수에서 현재 불일치 배율 식 |
| E-support-only | 각 source의 절대 관측 지지만으로 기존 c를 유지/제거; 상대 승자 선택·B 예산 전송 없이, 둘 다 미지원이면 prior c_P 유지 |
| E-budget | 이번 관측 기반 q와 위 분기별 s |
| E-global-mass | E-budget과 source별 합계 계수가 같은 전역 대조 |
| E-old-strength | E-budget의 q를 유지하고 s만 현재 LC의 총강도로 대체한 강도 진단 |

E-global-mass는 source별로 k_s^global = sum_p(k_s^E)/N_s를 원래 유효 집합 전체에 배분한다. 각 source의 합계 가중치는 정확히 같고 위치만 바뀐다. 잔차나 실제 parameter gradient까지 같은 대조는 아니며, 공간 배분으로 gradient가 달라지는 것이 비교 대상이다. source 결손은 동일하게 유지한다.

E-old-strength는 수학적 강도 진단이다. 현재 LC의 총강도0 때문에 E의 선택도 비활성일 수 있음을 명시한다. fallback에서 B를 prior로 전부 넘기는 E-strong-fallback은 별도 후순위 대조이며 주정책에 섞지 않는다.

### 7.2 source를 바꾸는 비교

DA3/MVS × G/LC/E-budget의2×3 비교를 제안하되 G1–G4 이후 별도 실행 명세로 정한다.

- 공통 valid mask·분모·q/s·controller를 고정한 target-only 진단과, 각 source의 실제 결손까지 포함한 운용 비교를 분리한다.
- MVS 결손을 DA3로 채우지 않는 첫 비교에서 prior fallback을 명시한다. MVS 존재 여부 자체를 정확성 라벨로 사용하지 않는다.
- MVS depth는 현재 카메라별 geometric depth 후보를 검토한다. 기존 fused/vendor geometry를 이름만 바꿔 투입하지 않는다. 현재 코드·정확한 카메라 membership·해상도·지지/가시성 lineage를 먼저 확인한다.
- 기존 DA3 또는 MVS 생성에 평가용 사진이 들어갔다면 새로운 honest 비교 입력으로 바로 재사용하지 않는다. 기존 결과는 보존하고 그 입력의 진단 범위와 필요 재생성 범위를 기록한다.

### 7.3 controller·보호·반복

G4의 고정 .05 비교는 native controller 재현이 아니다. 장기 비교에서는 exact per-step controller 계수의 동일 replay와 각 방법의 자유 controller 운용을 분리한다. 100step 간격 scalar 로그를 보간한 것을 exact replay라고 부르지 않는다. 충분한 trace가 없으면 새 G 대조를 별도 실행해 trace를 생성하거나 고정 계수 비교로 범위를 제한한다.

구조 보호 native/release는 source gate와 독립 요인이다. 초기 비교에서 동일하게 유지하고, 실제 gradient가 보호에 막히는 것을 본 뒤 보호 변경을 원인 분리 실험으로 다룬다.

기존 18G와 LC 결과는 기존 조건의 결과로 계속 재사용하되, 입력 정합·controller·가중 예산이 달라진 새 조건의 exact matched control로 자동 승격하지 않는다. 작은 차이 재현성에는 독립 최적화 반복이 필요하다. 같은 Anchor에서 seed만 달리한 refinement 반복과 Anchor 초기화까지 다른 반복은 다른 추론 범위다.

## 8. 구현 재사용·자원·실행 결박

재사용 후보:

- [기존 symmetric photometry](../../../../src/phd/source_candidate_v1/photometry.py): projection, common support, ZNCC, 이름 교환·무텍스처 등 [테스트](../../../../tests/phd/test_source_candidate_photometry.py)의 원리. 기존 MVS/ALS cell-plane evaluator를 raw depth-patch 구현으로 그대로 부르지 않는다. 기존 문턱과 low_target_texture_cost=.5는 이번 gate에 검증된 값이 아니다. 기존 함수의 reference 저분산→NaN, target만 저분산→비용.5 처리는 v3의 양쪽 저텍스처 보류와 다르다. 각 ray warp·noisy depth·경계·새 보류 분기는 별도 검증한다.
- 기존 v2.5 독립 NumPy/autograd 검사와 input/hash receipt 형식을 새 source/helper에 맞춰 확장한다. 과거36 PASS는 v3 코드나 Gaussian update의 PASS가 아니다.
- complete Anchor8k, raw input, 기존 G/LC mesh/렌더/평가를 읽기 전용으로 재사용한다.

실행을 준비할 때 새 source/derived target/score/policy/output은 별도 v3 root로 저장한다. 실행 명세는 원 입력·카메라 목록·전처리·recipe·q/state cache·source 코드·컨테이너·Anchor·평가 contract·자원 hash를 결박하고, mismatch 또는 null threshold를 만나면 실행을 거부해야 한다. 평가 reference는 score/학습 컨테이너에 마운트하지 않는다.

제안 출력 root는 JBGS_ARTIFACT_ROOT/phase-payloads/phd/local_source_weight_v3/PHD-LOCAL-SOURCE-WEIGHT-DESIGN-v3다. 이 경로는 이번 문서 작성에서 생성하지 않았다. 카메라 독립 대응/가시성 지원 구현과 문턱은 G1에서 결박해야 하며 기존 plane evaluator의 부가 출력으로 이미 충족됐다고 간주하지 않는다.

| 단계 | 제안 자원 상한 | 실행 전 결박할 항목 |
|---|---|---|
| G0/G1/G3 CPU 개발 | Docker CPU4/RAM8GiB, GPU없음, 동시1개, 첫 개발 attempt wall2시간/출력10GiB | 정확한 표본 목록·처리율·예상 총량. 상한 도달은 PARTIAL이고 표본을 조용히 줄이지 않음 |
| G2 평가 | Docker CPU4/RAM8GiB, 평가 전용 reference mount | same-reference 지원 계약·평가 config hash |
| G4 Gaussian 검사 | Docker CPU8/RAM32GiB/GPU1, 순차, 기존 이미지 재사용 | 실제 가용 RAM/VRAM, 보호·optimizer 복원, 정확한 step/camera; score는 사전 CPU 계산 |
| G5/G6 | G4 실측 후 별도 확정 | step 수·조건 수·반복·저장량·시간·실패 재시도·평가 완료 기준 |

과거32GiB/3090 자원 기록은 현재 가용성 보장이 아니다. 기존18개 queue·서비스·remote desktop을 중지하거나 메모리 확보를 위해 기존 결과를 지우지 않는다. 새 GPU 작업은 실행 범위가 확정된 뒤 자원 여유가 있을 때만 진행한다. 종료시각을 임의로 만들지 않는다.

새 구현·recipe가 결박된 이후의 반복 실행은 OS worker가 관리하도록 한다. Agent는 단계 산출물의 검토와 실패 분석에 개입하고, 학습을 지속 polling하는 구조로 만들지 않는다.

## 9. 연구 기여와 중단·축소 조건

- 문제 차별성: 시점·정확성이 다른 외부 prior와 현재 영상의 부분적 관측/오류가 공존한다.
- 원인 설명: source 불일치, 감독 품질, 배분, 총강도, controller, 보호, 표현/추출을 구분해 손상과 수정의 전달 경로를 검증한다.
- 방법 신규성: ZNCC나 국소 가중 자체는 신규성이 아니다. 대칭적인 후보 검사, 관측 부족의 명시적 처리, source 배분·총강도 정책이 기존 단순/선행 방법보다 유용한지는 미확인이다.
- 검증 기여: source 수준 오류→정책→gradient/update→같은 참조점의 수정/손상을 연결하는 재현 가능한 검사와 실패 범위다.

같은 지원에서 oracle 여지가 거의 없으면 source 선택보다 감독 자체/표현을 재검토한다. Oracle 여지는 있지만 사진으로 구별할 근거가 없으면 prior fallback/판정 유보의 범위를 공개하고 자동 선택 주장을 축소한다. 더 간단한 prior 계수 감소·confidence·순차 검사로 같은 결과가 나면 그 설명과 방법을 우선한다. 현재 P1/P2/P3는 개발 자료이며 최종 일반화에는 독립 검증이 필요하다.

## 10. 이번 설계에서 확인한 문헌과 상태

- [Schönberger et al., ECCV2016 공식 포스터](https://www.microsoft.com/en-us/research/uploads/prod/2019/09/P-2A-41.pdf): NCC·기하 비용, view 선택·시차·가림의 원리. 본 두-source weight 정책은 그 논문의 재현이 아니다.
- [NeuRIS, ECCV2022 §3.2](https://arxiv.org/html/2206.13597v2): 다중뷰 photo consistency로 normal 감독을 조절하는 사례. 현재 재구성의 평면 검사와 이번 두 target patch 검사는 구분한다.
- 추가 문헌과 범위는 [v2.5](SOURCE_RELIABILITY_AND_PIXEL_VALIDATION_ko_v2_5.md)에 있다.

이번 산출물은 이 설계와 JSON checklist, 입구 링크다. 신규 점수 계산·문턱 선정·v3 가중 구현·학습·성능 평가는 아직 수행하지 않았다. 기존 v2.5 전체 픽셀 감사는 보존된 선행 기술 증거다.

### 작성 검증·예외 기록

고정 Docker 이미지 sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e, CPU1/RAM256MiB/network none/read-only/GPU 없음으로 설계 JSON을 읽었다. JSON 구문, execution_ready=false, scientific_verdict=null, G0–G6 순서, G4의 2지역×6조건×1step=12분기와 본문 일치를 확인했다. 모두 PASS다. 이는 문서 형식 검증이며 설계된 알고리즘의 테스트가 아니다.

작성 중 patch 두 건이 거절됐다(동일 파일 Delete/Add 중복 연산, 부분 문장 context 불일치). 해당 patch는 적용되지 않았고 단일 Update와 정확한 문장 context로 처리했다. 데이터/학습 실행의 실패가 아니며 기존 입력·실험 코드에는 영향이 없다. 저장소 diff 공백 검사도 통과했다.
