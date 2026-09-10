# v3.1 보완 — MVS 자기검사, 결손·불균일성, 변수와 판정의 의미

- 작성일: 2026-09-11
- task_id: PHD-LOCAL-SOURCE-WEIGHT-DESIGN-v3
- 상태: DESIGN_CLARIFICATION / NOT_EXECUTION_READY
- scientific_verdict: null
- 범위: [v3 설계](SOURCE_WEIGHT_POLICY_DESIGN_ko_v3.md)의 관측 독립성 보완과 표기 설명. 기존 main_v2, 입력, 코드, 결과, 실행 작업을 바꾸지 않는다. 새 MVS/DA3 생성이나 점수 계산을 이번 보완에서 수행하지 않았다.
- 변경점: v3의 train-only 조건만으로 MVS 생성과 판정 사이의 자기검사 문제가 해결되지는 않는다. 아래 영상 역할 분리를 새 실행 명세의 추가 요구로 둔다.
- 후속 보완: [v3.2 실제 열람·역할 재검토](OBSERVATION_WALKTHROUGH_ko_v3_2.md)는 G/V 분리의 입력 손실을 고려하여 이를 기본 운용의 필수 조건 대신 별도 생성 미사용 view 검사로 둔다. 현재 입력의 내부 적합도 기반 선택과 독립 정확성 평가를 구분한다.

## 1. 투영 가능한 사진을 모두 쓰는가

첫 개발 후보는 원래 v3처럼 사전 선정한 최대6개 이웃에서 비교한다. 유효한 공통 이웃3개 이상과 서로 다른 시차 묶음2개 이상을 초기 조건으로 둔다. 이 수는 기술 개발 후보이며 검증된 최적값이 아니다.

투영이 영상 범위 안에 들어오는 것, 같은 표면을 실제로 볼 수 있는 것, depth를 구별할 만큼 정보가 있는 것은 서로 다르다. 시차가 너무 작거나, 해상도가 낮거나, 가림·반사가 심한 사진을 모두 같은 표로 세지 않는다.

Depth 후보의 사진 점수를 보기 전에 overlap·pose·시차·해상도로 이웃을 선택한다. 두 후보에 같은 이웃 목록과 비교 표본을 제공한다. 선택한 각 이웃의 비용과 제외 이유를 모두 저장하고, 중앙값과 이웃별 승자 일치도를 함께 본다. 비용이 불리하다는 이유만으로 해당 이웃을 제외하지 않는다. 필요하면 전체 적격 이웃으로 확장한 민감도 검사를 별도 실시한다.

## 2. MVS가 만든 사진으로 MVS를 검사하는 문제

사용자의 지적대로 같은 사진·같은 비용을 다시 사용하면 MVS가 자신이 최적화한 목적에 잘 맞는지를 재측정하게 된다.

동일한 후보 집합에서 F를 정확히 최소화한 D_MVS라면 F(D_MVS)<=F(D_prior)다. 그 점수를 다시 비교하는 것은 독립적인 정확성 증거가 아니다. 실제 MVS는 근사 최적화, 이웃 선택, 기하 일관성, filtering/fusion, 다른 해상도 등을 사용하므로 모든 새 NCC 검사에서 항상 이긴다는 보장은 없다. 그러나 자기 적합에 유리한 구조라는 문제는 남는다.

후속 검사에서 사진 역할을 분리한다.

| 역할 | 허용 용도 |
|---|---|
| G: 후보 생성용 학습 사진 | MVS/DA3 target 생성과 필요한 multi-view refinement |
| V: 판정용 이웃 사진 | G로 만든 후보를 재투영해 score/support/선택을 생성 |
| T: 기존 최종 평가용 사진 | 최종 appearance 평가만; G/V에 사용하지 않음 |

- G/V는 기존 학습 사진 내부에서, depth 생성 전에 고정한다. V도 방법에 사용되는 학습 증거이므로 최종 held-out evaluation set이라고 부르지 않는다.
- Reference 사진은 G에 있을 수 있고 pose 계보도 공유할 수 있다. 따라서 '깊이 생성에 쓰지 않은 이웃 사진에서 검사'이며 완전히 독립적인 센서/장면 검증은 아니다.
- V의 사진·depth·법선이 MVS의 기하 refinement/fusion 또는 DA3 공동 추론에 간접 사용된 경우도 생성 참여로 센다. 판정 score나 candidate refinement로 V에 다시 맞추었다면 그 이후 V는 독립적인 재검사 자료가 아니다.
- 후보 생성은 원사진 membership과 이웃 그래프까지 결박한다. 기존 target을 만든 정확한 사진 목록을 모르면 사후에 일부를 V라고 이름 붙여 독립성을 주장하지 않는다.
- 기존 MVS/DA3를 같은 사진에 재투영한 결과는 INTERNAL_FIT_DIAGNOSTIC으로 보존할 수 있다. 제한된 새 입력 revision에서 G/V를 분리한 검사와 구분한다. 이를 위해 필요한 재생성 범위·자원은 새 실행 명세에서 정하며 이번 문서로 실행하지 않는다.
- G/V 분리는 현재 입력의 정보량도 바꾼다. 적은 사진으로 만든 결과와 전체 사진 결과를 같은 조건으로 비교하지 않는다. 모든 방법에 같은 생성/판정 입력을 제공한다.
- 공통 pose 오류, 반복무늬, 반사로 두 영상 묶음이 같은 오답을 지지할 수 있다. V 적합도가 좋아도 GT 정확성 보장은 아니며 별도 reference 평가가 필요하다.

이 변경은 v3의 '어떤 source가 영상에 더 잘 맞나'를 더 설득력 있게 검사하기 위한 것이다. MVS를 사용한다는 사실 자체나 높은 NCC만으로 image source에 우선권을 부여하지 않는다.

## 3. 결손과 기하 불균일성은 무엇으로 알 수 있는가

| 문제 | 측정 가능한 진단 | 그 진단만으로 알 수 없는 것 |
|---|---|---|
| MVS depth 결손 | 카메라별 valid mask, 고정 영역의 피복, 연결된 구멍 크기, 다른 시점 지원 | 비어 있는 곳의 정답 높이, prior의 정확성 |
| 실제 관측 부족 | 시야/가림 상태, usable view 수, 시차·텍스처·매칭 모호성 | prior가 현재에도 유효하다는 사실 |
| 표면의 국소 불균일성 | 고정 물리 범위의 국소 평면 잔차, 법선 분산, 깊이 불연속 | 잔차가 오류인지 실제 구조물·경계인지 |
| 시점별 기하 불안정 | 같은 가시 표면을 공통 좌표로 옮긴 불일치, 생성용 view 묶음 변경에 대한 변동 | 여러 시점에서 일관된 공통 편향의 부재 |
| source의 실제 정확성 | 별도 평가 reference와 같은 표면의 거리·높이/방향 오차 | reference가 없는 영역의 정답 |

한 카메라의 결손은 모든 카메라에서의3D 결손과 같지 않다. 다른 시점에 유효 표면이 있으면 그 지원을 따로 기록하되, 그 depth를 옮겨 target을 채우는 것은 새 입력 생성으로 결박한다.

빈 곳에는 image target 자체가 없으므로 두 후보의 depth/patch 점수 비교가 정의되지 않는다. Prior 후보만 현재 사진으로 검사할 수는 있지만, 그 결과가 다른 유효 image depth를 새로 만드는 것은 아니다. Prior도 사진과 충돌한다면 CONTRADICTED_PRIOR_FALLBACK을 기록한다.

거친 MVS가 잘못됐다는 가능성을 조사할 수는 있다. 그러나 매끈한 prior가 오래된 잘못된 높이에 놓여도 plane 잔차는 작을 수 있다. 실제 작은 구조물이 있는 MVS는 더 거칠지만 더 정확할 수 있다. 따라서 거칠기만으로 q를 prior 쪽으로 보내지 않는다. 먼저 평면 내부/경계·세부를 분리한 진단에서 사진 지지와 시점 간 안정성을 확인한다. 거칠기 지표의 gate 반영은 별도 후속 설계이며 v3 주정책에 이미 들어간 것으로 읽지 않는다.

## 4. 수식 변수 사전

표기의 충돌을 피하기 위해 이 보완에서는 source index를 h∈{P,I}, 사진 비용을 e_hj, depth loss의 계수를 c_h, 총계수를 s_p로 쓴다. v3의 사진 비용 c_s와 loss 계수 c_P/c_I는 같은 물리량이 아니다.

| 변수 | 의미 |
|---|---|
| p, t | 사진의 픽셀 위치, 학습 step |
| P / I | prior source / image source(DA3 또는 해당 비교의 MVS) |
| D_P,p / D_I,p | 해당 픽셀 ray에서 두 source가 제공하는 target depth, 단위m |
| Dhat_p | 현재 Gaussian을 그 카메라에서 렌더한 depth |
| lambda_P / lambda_I(t) | source 전체에 사용하는 공통 loss 계수; 정확도 확률이 아님 |
| N_P / N_I | 그 카메라에서 source별 유효 target 픽셀 수; 관측 품질 gate 이전의 분모 |
| c_P / c_I | lambda/N과 유효 mask를 반영한 기존 G의 픽셀별 depth loss 계수 |
| B=c_P+c_I | 그 픽셀의 기존 두 depth 계수 합 |
| q_p | 새 정책이 배분한 최종 image 비중, 0~1; 정답 확률이나 변위 비율이 아님 |
| s_p | 새 정책에서 실제 사용할 두 depth 계수 합 |
| k_P=s(1-q), k_I=sq | prior/image 잔차에 실제 곱하는 최종 계수 |
| ell_p | 해당 픽셀의 depth loss 기여; 전체 depth loss는 픽셀별 합 |

유효 source에 대해 c_P=lambda_P/N_P, c_I=lambda_I/N_I다. 없는 source의 계수는0이다. 이미 분모를 적용했으므로 ell을 합한 뒤 또 평균내지 않는다.

\[
\ell_p=s_p[(1-q_p)|\hat D_p-D_{P,p}|+
                 q_p|\hat D_p-D_{I,p}|].
\]

식은 target 잔차를 어떤 비중과 강도로 적용하는지를 정한다. 어느 target이 맞는지를 스스로 알아내는 식은 아니다. 그 판단을 아래 관측 검사가 공급해야 한다.

설명용으로 N_P=N_I=N, lambda_P=.005, lambda_I=.05라고 가정하면 B=.055/N이고 기존 image 비중은 .05/.055≈.909다. 이것은 image가90.9% 확률로 정확하다는 뜻이 아니다. 실제 감사 사진은 두 source의 유효 N이 다르므로 이 설명용 비율을 그대로 적용하면 안 된다.

## 5. 'image 후보 지지'와 'prior 후보 지지'의 구체적 의미

판정용 이웃 j마다 e_Pj와 e_Ij를 같은 관측에서 구한다. 각각은 (1-ZNCC)/2이며 낮을수록 사진 패턴에 잘 맞는다.

\[
E_P=\operatorname{median}_j e_{Pj},\quad
E_I=\operatorname{median}_j e_{Ij},\quad
\Delta=\operatorname{median}_j(e_{Pj}-e_{Ij}).
\]

두 종류의 조건을 구분한다.

- 관측 자격 Q: 공통 유효 지지, 충분한 텍스처/시차, 가림/대응 근거, 이웃 묶음의 안정성, 모호하지 않은 비용 곡선.
- 비용 판단: 절대 비용 문턱 tau_abs와 후보 간 차이 문턱 m.

IMAGE_SUPPORTED는 Q를 통과하고 E_I<=tau_abs이며 Delta>m이고, 충분한 이웃/시차 묶음이 같은 승자를 지지할 때다. PRIOR_SUPPORTED는 같은 기준에서 E_P<=tau_abs, Delta<−m이다. 관련 수치들은 아직 선정·동결되지 않았다.

두 후보가 모두 절대 적합도 기준을 통과하고 깊이도 공통 표면 허용범위 안이면 OBSERVED_AGREEMENT다. 서로 다른 깊이가 비슷하게 좋은 점수를 받는 것은 agreement가 아니라 ambiguous다. 둘 다 나쁘거나 Q가 부족하면 UNRESOLVED다.

- IMAGE_SUPPORTED: q=1, s=B.
- PRIOR_SUPPORTED: q=0, s=B.
- OBSERVED_AGREEMENT: q=c_I/B, s=B.
- UNRESOLVED이며 사용 가능한 prior 있음: q=0, s=c_P.
- Prior 없음, image 단독 절대 지지 충분: q=1, s=c_I.
- Prior 없음, image 지지 불충분: s=0, q undefined.
- Lambda=0인 source를 다른 source의 예산으로 다시 켜지 않는다.

여기서 '지지'는 제한된 관측 검사 통과다. 실제 source의 정답 판정과 가중 정책의 개선 여부는 고정 이후 별도 GT 평가에서 확인한다. 큰 불일치→image를 선택한 현재 LC와 달리, image가 실제로 관측을 설명한다는 추가 조건이 필요하다.

## 6. 검증·실행 명세에 추가할 항목

1. G0: G/V/T 목록·pose·source 생성 이웃/배치 membership과 간접 사용을 결박한다.
2. G1: INTERNAL_FIT_DIAGNOSTIC과 생성 미사용 view 검사 결과를 분리 출력한다. 기존 데이터만으로 후자가 불가능하면 미측정으로 둔다.
3. G2: 관측 판별력, coverage/holes, geometry irregularity, reference 정확성을 별도 표로 평가한다. 거칠기/결손을 source 정오 라벨로 바꾸지 않는다.
4. G3 이후: 가중 q/s를 만든 정확한 score·Q·threshold hash를 함께 저장한다.
5. 기존 v3의 실행 가능 false와 미확정 문턱을 유지한다. 이번 보완은 실행 코드·새 성능 결과가 아니다.

## 근거

- [Schönberger et al., ECCV2016 공식 포스터](https://www.microsoft.com/en-us/research/uploads/prod/2019/09/P-2A-41.pdf): NCC와 기하 비용, 관측별 선택과 filtering/fusion. 같은 생성 목적의 재평가가 독립 정확성 증거가 아니라는 결론은 이 목적 구조에 대한 본 설계의 추론이다.
- [COLMAP 공식 FAQ](https://colmap.github.io/faq.html#improving-dense-reconstruction-results-for-weakly-textured-surfaces): 약한 텍스처에서의 depth 추정·filtering과 정확도/완전성 절충. 현재 입력의 파라미터가 이 문서와 동일하게 설정되었다는 뜻은 아니다.
