# Normal 활용과 AGS-Mesh 대응 관계 검토 v3.4

- 작성일: 2026-09-11
- task_id: PHD-LOCAL-SOURCE-WEIGHT-DESIGN-v3
- 상태: DESIGN_REVIEW_ONLY
- scientific_verdict: null
- 범위: Prior normal을 관측 검사에 활용하는 후보와 AGS-Mesh의 입력/필터 출력 구분. 새 normal 추정, 가중치 변경, 학습 실행 없음.

사용자 정정은 [v3.5 source별 점수의 normal 확장](SOURCE_SCORE_NORMAL_EXTENSION_ko_v3_5.md)에 기록했다. 주설계는 source별 점수→판정을 유지하며 normal을 점수 계산에 활용하는 것이다. 아래 AGS식 필터는 대조군이며 주설계 전환 요청으로 해석하지 않는다.

## 1. AGS-Mesh의 filtered는 별도 영상 depth를 뜻하지 않는다

확인 원문은 [AGS-Mesh arXiv 2411.19271v2 §4.1–4.3 식 4–10](https://arxiv.org/html/2411.19271v2#S4.SS1)이다. 논문에서 D는 센서 depth, Nd는 센서 depth로부터 얻은 normal, Np는 사전학습 단안 normal 모델의 출력이다. DNC는 Nd와 Np의 각도 차이로 D의 일부를 사용하지 않는다. Df의 유효 값은 원 D와 동일하며 새 영상 깊이로 교체되지 않는다.

ANR는 현재 GS 렌더 기하에서 얻은 normal Nhat과 Np의 각도 차이로 Np의 일부를 사용하지 않는다. Nf의 유효 값은 Np와 동일하다. 논문 식에서 0은 필터링된 값의 표시이며, 이를 유효 깊이 0m를 감독하는 것으로 해석하지 않는다.

| 사용자 제안 대응 | 판정 |
|---|---|
| Prior depth ↔ sensor depth D | 외부 기하 감독의 역할로 대응 가능. 과거 ALS의 시간차는 AGS 센서 설정과 별도 조건 |
| Image depth ↔ filtered depth Df | 동일하지 않음. Df는 D의 일부 제외이고, DA3/MVS는 별도 source에서 온 depth 값 |
| Prior normal ↔ normal from depth Nd | Prior depth에서 계산하면 계산 역할이 유사. ALS 점군/mesh 직접 normal은 별도 생성 경로 |
| Image normal ↔ filtered normal Nf | 먼저 raw image normal의 생성 경로를 구분해야 함. 단안 normal 예측은 Np에 가까우며 Nf는 Np를 필터링한 결과. DA3/MVS depth에서 미분한 normal은 Np와 같은 추정 경로가 아님 |

예를 들어 sensor depth가 60m이면 Df는 유지된 위치에서 60m다. 필터링 때문에 58m의 새 영상 target이 되는 것은 아니다. 현재 두-source 설계는 Prior 60m와 영상 58m처럼 값 자체가 다른 target 사이의 감독 배분을 다룬다.

그러나 Prior와 image normal의 불일치로 Prior depth 감독을 제거하는 안을 구현한다면 그것은 AGS DNC를 입력에 맞게 적용한 방식과 가깝다. 이를 새 가중 원리로 부르지 않고 강한 선행 기준방법으로 취급한다.

## 2. Normal을 활용할 수 있는 세 역할

| 역할 | 기대하는 기능 | 구분할 한계/요인 |
|---|---|---|
| 각 후보 depth+normal로 국소 평면을 만들고 사진 패치를 warp | 기울기를 명시하고 noisy depth patch의 재투영을 비교 | 기존 ray별 depth warp와 별도 후보. 경계/곡면에서 평면화가 실제 세부를 지울 수 있음 |
| Prior/image normal의 차이를 보조 진단 또는 감독 필터로 사용 | 방향·형상 불일치와 급격한 경계 문제를 관측 | 서로 다르다는 사실만으로 어느 source가 맞는지 결정되지 않음 |
| Normal loss를 GS에 추가 | 방향·국소 형상 감독 | 사진 점수 변경과 다른 최적화 요인. 동시에 추가하면 개선/손상 원인 분리가 어려움 |

현재 진단은 패치의 각 픽셀을 해당 source의 depth로 역투영한다. 따라서 주변 깊이가 만드는 기울기와 형상이 이미 warp에 반영된다. 명시적인 normal을 쓰지 않았다는 것이 중심 depth 하나로 패치 전체를 평행 이동했다는 뜻은 아니다. Normal을 추가할 때는 어떤 역할이 새로 들어가는지 명시한다.

같은 depth에서 계산한 normal은 그 depth의 파생량이다. 이를 별도의 독립 관측이 하나 더 생겼다고 세지 않는다. 별도 RGB normal 모델도 같은 사진에 의존하므로 오차 독립성을 자동 가정하지 않는다.

## 3. 위치 차이와 방향 차이를 구분한다

평행한 두 수평면은 높이가 달라도 normal이 같다. 예를 들어 서로 다른 높이의 평평한 지붕과 바닥은 모두 같은 방향의 normal을 가질 수 있다. 따라서 normal 일치 검사는 높이·현재성의 충분한 검정이 아니다. 이 예시는 기하적 반례이며 P1/P2의 실제 normal을 측정한 결과는 아니다.

반대로 normal 차이가 크더라도 어느 쪽이 올바른지는 normal 차이만으로 식별되지 않는다. 센서/추정 오류, 경계 혼합, 좌표계·방향 불일치, 실제 형상 변화가 모두 후보 원인이다. 사진 패턴과 후보의 위치·기울기를 함께 검사하는 근거가 필요하다. 사진도 무늬·시차·가림 때문에 판별력이 부족할 수 있으므로 보류는 유지한다.

## 4. 다음 관측 지도에 반영할 비교 후보

기존 [v3.3 지도 전 단계](OBSERVATION_PRECEDENTS_AND_MAP_PLAN_ko_v3_3.md)의 G1 안에서 다음 세 관측 방식부터 비교한다. 아직 실행 조건이나 새 기본 방식으로 확정하지 않는다.

1. 현재 raw depth의 ray별 warp와 사진 비용.
2. 각 source의 중심 depth와 해당 source에서 얻은 normal을 사용한 평면 warp와 사진 비용.
3. AGS DNC에 대응하는 normal 불일치 기반 Prior 필터. 재현 원리와 변경된 입력/normal 추정 경로를 명시한다. ANR까지 포함하려면 현재 GS normal과 시간별 갱신이 필요한 별도 비교가 된다.

비교 표본은 사전에 고정하고, 평탄 내부/기울어진 면/평행 높이 차이/경계/결손/거친 depth를 함께 다룬다. Normal 생성의 공간 support와 scale, 좌표계·부호, 유효성·정합을 결박한다. 불확실한 경계 normal을 주변으로 무조건 확장하지 않는다. 후보별 사진 비용, 미지원 범위, 선택 안정성과 추후 별도 GT의 선택 오류를 함께 평가한다.

Normal을 관측 비용에 더할 별도 계수나 새로운 normal loss를 이번 문서에서 정하지 않는다. 우선 사진 관측의 판별력이 향상되는지와 AGS식 간단 필터로 충분한지 확인한다. 기존 방식이 충분하면 그 결과를 채택하고 별도 방법의 필요성 주장을 줄인다. 기존 18개 결과, 뷰어 점수, 감독 입력과 실행 서비스는 보존한다.
