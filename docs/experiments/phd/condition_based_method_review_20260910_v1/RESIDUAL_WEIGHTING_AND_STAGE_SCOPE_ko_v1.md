# 단계 범위와 depth 불일치 기반 국소 가중의 의미

- 작성일: 2026-09-10
- task_id: `PHD-RESIDUAL-WEIGHTING-SCOPE-20260910`
- 상태: `DESIGN_CLARIFICATION / BASELINE_CANDIDATE`
- scientific_verdict: null
- 새 학습·추론·렌더·재구성·방법 실험 없음. GT는 평가 전용. 기존 실행·계약·서비스·문서를 보존한 별도 정리.

## 1. Anchor 단계 변경을 제안한 것은 아니다

앞선 국소 가중식은 **동일한 complete Anchor8k 이후 refinement에 남는 prior depth 항과 영상 depth 항을 조절하는 첫 비교**였다. Anchor부터 prior 가중을 바꾸는 설계는 초기 기하까지 바뀌는 별도 질문이다. 국소 loss 제어 자체는 coarse-to-fine 순서나 특정 표현을 필수로 요구하지 않는다.

GeoGS도 prior 가중을 모든 단계에서 동일하게 두지는 않는다. Anchoring에는 `lambda_lod_init`, refinement에 남는 prior에는 `lambda_lod_anchor`를 쓰고 DA3 깊이를 추가한다. 해당 변수명의 anchor는 refinement에 남는 anchoring 항을 가리키므로 Anchor 학습 단계와 구분한다. 공통 DA3 계수의 adaptive 제어와 국소 prior/영상 타당성 제어도 다르다. [확인한 공식 train.py](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py), stage-based weighting 및 dynamic DA 제어.

## 2. 사용자가 제시한 규칙은 직접 비교할 기준선이다

동일 ray·단위·가시 표면의 두 유효 target에서 불일치를 다음처럼 정의할 수 있다.

\[
\Delta_p=|D_P(p)-D_V(p)|,\qquad a_p=f(\Delta_p),\quad 0\le a_p\le1,\quad f\text{는 증가 함수}.
\]

큰 차이에서 영상 감독의 상대적 요구를 늘리는 한 가지 구현 예시는 다음과 같다.

\[
L_{D,p}=\lambda_P(1-a_p)\rho(\hat D-D_P)
+\lambda_Va_p\rho(\hat D-D_V).
\]

이는 실제로 구현 가능한 **불일치 기반 국소 감독 제어**다. 별도 source classifier를 요구하지 않으며, 기존 전역 제어보다 수정·보존을 잘할 가능성을 미리 부정하지 않는다. f의 형태·척도·유효 mask·가중 정규화는 비교 전에 정의해야 한다. 이 식의 큰 a는 영상 쪽 loss를 상대적으로 강하게 한다는 뜻이며 Gaussian의 실제 변위가 a나 불일치 크기에 비례한다는 뜻은 아니다. 특히 실제 GeoGS의 metric depth는 L1이고, primitive 보호·다른 loss·optimizer·depth 합성도 실제 변화를 좌우한다.

## 3. 불일치 크기와 수정의 타당성은 다른 정보다

다음 숫자는 설명용 반례이며 실험 결과나 학습 GT가 아니다.

| D_P | D_V | 실제 현재 깊이 | 불일치 | 필요한 동작 |
|---:|---:|---:|---:|---|
| 10m | 12m | 12m | 2m | 영상 방향 수정 |
| 10m | 12m | 10m | 2m | prior 보존·영상 감독 억제 |

동일한 두 입력 차이에 서로 반대 동작이 필요할 수 있다. 따라서 `큰 차이→prior 오류/시간 변화→영상으로 더 이동`은 **영상 depth가 그 충돌에서 더 믿을 만하다**는 추가 가정을 포함한다. 작은 차이도 두 target의 정확성을 보증하지 않는다. 다른 가시 표면·정합·피복 차이 때문에 큰 잔차가 생길 수 있으므로 단위만 맞추는 것으로 충분하지 않다.

앞선 r_P/r_V는 target 간 깊이 차이가 아니라 **여러 현재 영상에서 어느 기하 가설이 더 잘 설명되는가**를 계산하려는 후보였다. 조절하는 위치는 같은 depth loss지만, 가중을 결정하는 근거가 다르다. 이 추가 근거가 항상 맞거나 잔차 규칙보다 유리하다는 결과는 아직 없다.

사용자가 잔차를 `|D_hat-D_P|`, `|D_hat-D_V|`로 뜻했다면 이는 현재 복원이 각 target에 얼마나 가까운지다. 초기 복원이 prior에서 시작하면 prior 잔차가 작아지는 것은 자연스러우며 prior 정확성의 독립 증거가 아니다. 이 model-dependent 잔차로 만든 제어는 학습 중 바뀔 수 있지만 자기확증을 검사해야 한다. 고정된 D_P/D_V의 차이만 사용하는 가중은 국소적이지만 정적이다.

## 4. 최소 비교와 판단

같은 complete Anchor·depth target·다른 loss·구조 보호·학습 일정·추출에서 다음을 비교한다.

1. 기존 공통 가중 제어.
2. 사용자 제안의 depth 불일치 기반 국소 가중.
3. 같은 depth 불일치를 기본 정보로 사용하되, 현재 영상의 가설별 정합·구별력을 추가한 국소 가중.

3은 추가 영상 비용을 계산하므로 계산량도 기록하고, 필요하면2가 동일 정보를 사용할 수 있는 기존 결합 규칙과도 비교한다. 입력품질(DA3/ACMP) 교체와 가중 규칙 변경을 동시에 섞어 원인을 추정하지 않는다. 기존 P1/P2/P3 실행은 조건과 실제 공통 계수 일정이 일치하는 기준 셀에 재사용한다.

영상 depth가 더 정확한 충돌에서는2의 성공을, prior가 더 정확한 충돌에서는2의 손상 가능성을 함께 평가한다. 두 target이 함께 틀린 조건과 두 target이 모두 유효한 조건도 제외하지 않는다. 이 분류는 평가용이며 학습 weight에 GT 정답을 넣지 않는다.

2로 필요한 수정과 유효 구조 보존이 충분하면3의 필요성을 축소한다. 3이 같은 손상 수준에서 더 수정하거나 같은 수정 수준에서 손상을 줄이지 못하면 추가 관측 지지 추정의 효과를 기각한다. 국소 가중 사용 자체는 신규성 근거가 아니다.
