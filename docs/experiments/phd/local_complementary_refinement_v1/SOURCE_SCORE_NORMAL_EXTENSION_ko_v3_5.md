# Source별 점수에 normal을 활용한다는 사용자 의도 명확화 v3.5

- 작성일: 2026-09-11
- task_id: PHD-LOCAL-SOURCE-WEIGHT-DESIGN-v3
- 상태: DESIGN_INTENT_CLARIFICATION
- scientific_verdict: null
- 범위: 사용자 정정에 따른 주설계/대조군 구분. 기존 source·점수·가중치·학습·서비스 변경 없음.

추가 사용자 정정 [v3.6](SOURCE_SCORE_TO_WEIGHT_INTENT_ko_v3_6.md): 핵심은 source별 점수에서 **가중치를 설정**하는 것이다. 아래 '판단'을 승자 선택이 필수인 구조로 해석하지 않는다. 두 source 계수를 정하는 함수와 normal을 활용한 점수 계산을 각각 설계한다.

## 1. 유지할 주설계

사용자는 원래의 'source별 값을 계산하고 그 값으로 판단한다'는 구조를 유지하면서, normal을 그 값 계산에 추가로 활용하자는 뜻이었다. 이를 '사진 정합 방식 대신 normal 불일치로 Prior를 제거하는 방식으로 전환'하자는 요청으로 해석한 것은 잘못이다.

원래 구조는 다음과 같다. I는 한 비교에서 DA3 또는 MVS이며, O는 허용된 현재 사진·카메라와 검증된 관측 근거다.

    Prior 점수 E_P = F(D_P, N_P; O)
    Image 점수 E_I = F(D_I, N_I; O)
    같은 규칙의 source별 점수와 지원 상태 → 판단 → 위치별 감독 계수

F는 아직 normal 포함 세부식이 확정되지 않은 공통 평가 함수다. source 이름만 바꾸었을 때 검사 규칙은 대칭이어야 한다. 현재 구현된 F는 각 source의 raw depth patch를 ray별로 재투영한 사진 비용이며 명시적 normal 항이 없다. 기존 depth patch의 형상은 이미 warp에 반영된다.

## 2. Normal을 source별 점수 계산에 넣을 방법

첫 구체적 후보는 각 source의 depth와 해당 source normal로 국소 표면 방향을 표현하여 패치를 재투영하고, 같은 사진 관측에서 ZNCC/cost를 계산하는 것이다. Normal은 재투영 기하에 참여하며, 점수는 여전히 사진 적합도다. 이는 기존 ray별 depth warp와 동일 표본에서 비교할 수 있다.

별도의 normal 일관성 항을 F에 넣는 방법도 검토 가능하다. 그러나 각 source를 같은 기준으로 검사할 관측/대응과 normal의 생성 경로를 먼저 정해야 한다. source별 다중 시점 기하 일관성인지, 별도 추정 normal과의 일치인지, 같은 source 내부의 평활성인지에 따라 점수 의미가 다르다. 같은 depth에서 계산한 normal을 그 depth가 맞다는 독립 증거로 세지 않는다.

Prior normal과 image normal의 각도 하나는 '두 source가 얼마나 다른가'를 나타낸다. 이 공통 차이 하나만으로 서로 다른 정확성 점수 E_P와 E_I가 생기는 것은 아니다. 따라서 그 차이를 바로 Prior 기각으로 연결하는 규칙을 주설계에 넣지 않는다. 사진 점수에 normal 항을 더하는 계수·문턱은 이번 정정에서 임의로 정하지 않는다.

## 3. 선행연구 분류는 주 판정 신호 기준이며 배타적이지 않다

| 연구의 검사 부분 | 주된 판정 신호 | Normal의 역할 |
|---|---|---|
| NeuRIS §3.2 | 사진 일치도 NCC | 현재 depth와 함께 평면 warp 기하를 구성 |
| AGS-Mesh DNC/ANR | normal 각도 불일치 | 서로 다른 경로의 normal을 비교하여 감독 필터 구성 |
| COLMAP MVS | 사진 비용 + 기하 재투영 일관성 | depth와 함께 국소 표면을 표현하며 view 선택/추정에 참여 |

근거: [NeuRIS](https://arxiv.org/html/2206.13597v2#S3.SS2), [AGS-Mesh](https://arxiv.org/html/2411.19271v2#S4.SS1), [COLMAP 저자 포스터](https://www.microsoft.com/en-us/research/uploads/prod/2019/09/P-2A-41.pdf).

Normal을 사용한다는 사실만으로 사진 정합 방식이 아닌 것으로 분류하면 안 된다. 재투영에 쓰는 입력과 후보를 평가하는 신호는 다른 분류 축이다.

## 4. v3.4의 대조군 해석 정정

v3.4의 raw depth warp와 depth+normal warp는 source별 사진 점수 계산 방식을 비교하는 주설계 내부의 후보다. AGS DNC에 대응하는 Prior 필터는 비교할 선행 기준방법이다. 이 세 항목을 모두 주설계를 대체할 동등한 사용자 선택 요청으로 해석하지 않는다.

다음에 구체화할 것은 F의 normal 활용 방식과 그 검증 절차다. source별 평가를 생략하거나, Prior만 평가하고 나머지를 영상 depth로 채우는 방식으로 넘어가지 않는다. 가중치 지도와 GS 적용은 이 점수와 판정의 검증 뒤에 연결한다.
