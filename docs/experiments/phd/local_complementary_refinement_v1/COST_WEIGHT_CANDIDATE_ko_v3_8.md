# source 비용과 감독 가중치의 구체적 검증 후보 v3.8

- task_id: PHD-LOCAL-COST-WEIGHT-CANDIDATE-v3.8
- 작성일: 2026-09-11
- 상태: CANDIDATE_FORMULAS / OBSERVATION_GATE_NOT_BOUND / NOT_TRAINING_READY
- scientific_verdict: null
- 사용자 요청: 비용식과 가중치 변환식을 구체화하고, 현재 비용이 맞는지 확인하는 절차와 연결한다.
- 이 문서는 새 개발 후보다. v3.7 비용·평가, 기존 LC 학습·설정·서비스를 변경하지 않는다. GT는 별도 평가 전용이다.
- [기계 판독 설계](COST_WEIGHT_CANDIDATE_v3_8.json), [이전 실제 반례](NORMAL_PHOTOMETRY_RESULT_ko_v3_7.md), [사용자 의도](SOURCE_SCORE_TO_WEIGHT_INTENT_ko_v3_6.md).

## 1. AGS에서 가져올 부분

AGS-Mesh의 원래 조합은 sensor **depth**와 pretrained monocular **normal**이다. DNC는 sensor depth에서 유도한 normal과 monocular normal을 비교해 sensor depth 감독을 거른다. ANR는 monocular normal과 현재 렌더 기하의 normal을 비교해 normal 감독을 거른다. 남긴 target 값은 기존 값을 유지한다. sensor depth를 제거한 위치에 별도의 영상 depth를 대입하는 두-depth 교체식은 아니다. [AGS-Mesh §4.1–4.2](https://arxiv.org/html/2411.19271v2#S4.SS1)

따라서 불량 기하 감독을 국소적으로 약하게 만드는 설계·대조군으로 관련성이 있다. 그러나 ALS와 DA3/MVS라는 두 깊이의 현재성·적합도에 따라 감독을 배분하는 전체 해법으로 바로 복제할 수는 없다. 특히 높이만 다른 평행 표면은 normal이 같을 수 있다. 같은 depth에서 계산한 normal도 별도의 독립 관측은 아니다.

normal은 먼저 후보 표면의 기울기를 반영해 사진 패치를 투영하는 데 사용한다. 이는 depth와 normal로 평면 재투영 후 NCC를 계산하는 [NeuRIS §3.2](https://arxiv.org/html/2206.13597v2#S3.SS2)의 기하·사진 비용을 참고한 것이다. 아래 두-source 가중식이 그 논문에서 검증되었다는 뜻은 아니다.

## 2. 비용식: 사진 적합도를 같은 조건에서 계산

픽셀 p, source s∈{P,I}, 이웃 카메라 j, 패치 한 변 r∈{9,17,33}에 대해:

\[
e_{s,j,r}(p)=\frac{1-\operatorname{ZNCC}(A_{p,r},W_{s,j,p,r})}{2},
\qquad E_{s,r}(p)=\operatorname{median}_{j\in J^*}e_{s,j,r}(p).
\]

A는 원사진 패치, W는 그 source의 표면 가정으로 다른 사진에서 가져온 패치다. E는 0이면 밝기 패턴이 일치하고 1이면 반대인 비용이다. 정확성 확률이나 미터 단위 오차가 아니다.

- raw branch: source의 실제 국소 depth 배열로 각 픽셀을 투영한다.
- plane branch: 같은 source의 중심 depth를 보존하고 9×9 depth에서 추정한 normal로 평면을 만들어 투영한다. 원 결손은 채우지 않는다. normal 유효성이 없으면 해당 branch는 unavailable이다.
- 두 branch는 별도 고정 비교안이다. source마다 더 싼 branch를 선택하거나 세 패치 중 최소 비용만 고르지 않는다.
- J*는 사전 기하로 정한 동일 이웃 목록에서 두 source와 세 크기 모두 수치상 비교 가능한 카메라의 교집합이다. 최소 2장을 요구한다. raw/plane 간 직접 비교에는 추가로 branch 교집합을 사용하고 사라진 지원량을 기록한다.
- 비용마다 두 source는 같은 reference 픽셀 mask를 사용한다. 공통 mask≥80%, 원패치와 두 warp의 grayscale 표준편차≥.02, 유효 depth·양수 camera-Z·보간 가능한 영상 내부가 수치 요건이다. 사용하지 못한 시점과 이유도 저장한다.
- 비교상대가 결손이면 가능한 source의 own-support 비용을 따로 계산한다. 이것으로 존재하지 않는 두-source 우열을 만들지 않는다.
- 요약 표에는 평균 E_s=(E_s,9+E_s,17+E_s,33)/3도 표시하지만 가중치는 이 평균 하나로 결정하지 않는다. paired cost 차이와 source별 median 차이도 혼용하지 않는다.

## 3. 비용→지지·반박·불명 값

첫 수식 검증 후보의 수치는 아래처럼 정한다. clip(x)=min(1,max(0,x))다.

\[
f_+(e)=\operatorname{clip}\left(\frac{.30-e}{.20}\right),
\qquad f_-(e)=\operatorname{clip}\left(\frac{e-.30}{.20}\right).
\]

\[
S_s=g_s\min_r f_+(E_{s,r}),\qquad
R_s=g_s\min_r f_-(E_{s,r}),\qquad U_s=1-S_s-R_s.
\]

| 세 크기에서 관측되는 비용 | g=1일 때 해석 |
|---|---|
| 모두 ≤.10 (ZNCC≥.80) | S=1, R=0: 강한 사진 지지 |
| 모두 .20 | S=.5, R=0: 부분 지지 |
| 모두 .30 | S=0, R=0: 판단 불충분 |
| 모두 .40 | S=0, R=.5: 부분 반박 |
| 모두 ≥.50 (ZNCC≤0) | S=0, R=1: 강한 사진 불일치 |
| .10/.30/.50처럼 크기별로 뒤집힘 | S=0, R=0: 판단 불충분 |

세 크기의 가장 보수적인 지지/반박을 취한다. 좋은 크기만 골라 높은 확신을 만들지 않기 위해서다. 반면 큰 패치가 경계를 넘으면 올바른 후보도 지지를 잃을 수 있다. 이는 검증할 약점이며 좋은 설계라고 미리 판정하지 않는다.

**.10/.30/.50은 첫 개발 후보의 명시적 수치이며 현재 장면의 정확성에 보정된 문턱이 아니다.** 기존 P2 반례를 본 뒤 작성한 설계다. 그 사례를 다시 통과시키더라도 독립 검증으로 세지 않는다. 사진 점수 구간의 의미를 기준으로 정한 ramp이며 UAS 잔차로 계수를 최적화하지 않았다. 후속 민감도는 (.05,.25,.45), (.10,.30,.50), (.15,.35,.55) 세 묶음을 모두 보고하고 GT 성능이 가장 높은 묶음만 채택하지 않는다.

### g가 뜻하는 것과 현재 비어 있는 부분

g_s는 그 비용을 표면에 관한 근거로 해석할 수 있는지 나타내는 관측 적격 값이다. 첫 실제 운용 후보는 인증된 1 또는 미확인 0을 사용한다. 수식 모듈은 향후 보정 가능성을 위해 [0,1]을 허용하지만, 그 자체가 보정 함수를 제공하지는 않는다.

g=1의 입력 계약은 다음과 같다.

1. 위 수치 지원 요건을 통과한다.
2. 현재 사진의 대응/가시성 근거가 있다. 사진 내부에 투영됐다는 사실, source 자신의 depth z-buffer, 후보 warp와 그 역변환으로 만든 항등 cycle만으로 인증하지 않는다.
3. 반복무늬의 여러 대응, 앞가림, 서로 다른 표면을 섞은 패치가 해소되지 않았거나 시점별 비용 방향이 불안정하면 0이다. source에 불리한 실제 대응 오차는 mask에서 지워서는 안 된다.
4. 인증 자료의 사진·픽셀 ID와 계산기·설정 hash를 기록한다. GT, 현재 GS와의 자기 일치, source 생성에 사용한 사진의 수를 독립 정확성 증명으로 사용하지 않는다.

**이 인증 자료를 생성할 대응/가시성 계산기는 아직 결박되지 않았다.** 현재 v3.7의 visibility는 unknown이므로 그 자료만으로는 g=1을 부여할 수 없다. 실제 정책 입력으로는 g=0이다. g=1을 가정한 수치 예시는 `HYPOTHETICAL_COST_ONLY`로 표시하고 실제 검증된 가중치 지도와 구분한다. 이 미완료를 숨기고 새 학습에 연결하지 않는다. 단순 sigmoid/softmax가 이 결손을 해결하지는 않는다.

관측을 못 했다는 것과 관측했는데 맞지 않는다는 것은 다르다. 높은 비용만으로 잘못된 depth라고 단정하지 않는 것이 g의 목적이다. g와 S/R/U는 정답 확률이 아니다.

## 4. 지지·반박→실제 loss 계수

기존 전역 계수와 유효 픽셀 분모를 반영한 픽셀별 기본값은 다음과 같다.

\[
c_s(p,t)=\lambda_s(t)\,1_{\text{valid target }s}(p)/N_s,\quad
B=c_P+c_I,\quad A_s=1[c_s>0].
\]

N_s=0이면 해당 c_s=0이다. N_s는 관측 gate 통과 수가 아닌 원래 source 유효 target 수다. controller가 있다면 해당 step의 lambda_I를 사용한다. 실제 학습 연결 전에는 controller 고정/동일 replay와 원 reduction parity를 별도 결박해야 한다.

\[
\boxed{w_P=A_P\{c_P(1-R_P)+c_I S_P R_I\},\qquad
w_I=A_I S_I\{c_I+c_P R_P\}.}
\]

prior의 기본 강도는 반박되지 않은 만큼 남긴다. 반박된 몫은 image가 지지되는 만큼 image로 넘긴다. image의 기본 강도는 지지되는 만큼 사용하며, image가 반박되고 prior가 지지될 때만 prior로 넘긴다. 받는 source도 원래 활성 상태여야 한다. 남은 미사용 강도를 합=1 정규화로 다시 증폭하지 않는다.

두 source가 활성일 때의 끝점:

| Prior / image 관측 상태 | w_P | w_I |
|---|---:|---:|
| 둘 다 지지 | c_P | c_I |
| Prior 반박, image 지지 | 0 | B |
| Prior 지지, image 반박 | B | 0 |
| 둘 다 불명 | c_P | 0 |
| Prior 불명, image 지지 | c_P | c_I |
| 둘 다 반박 | 0 | 0 |

부분적인 지지·반박은 중간 계수를 만든다. source 하나를 반드시 고르는 규칙은 아니다. 영상 결손·관측 부재에서 prior를 남기는 것은 보수적 운영 정책이며 prior가 정답이라는 판정이 아니다. 둘 다 실제로 반박된 경우에는 두 depth 감독을 끄는 후보를 택했다. 이를 포함한 정책 끝점은 새 제안이고 사용자 승인된 최종 방법이나 성능 결론이 아니다.

항상 0≤w_P+w_I≤B다. lambda_P=0인 조건에서 prior를 되살리지 않는다. 하지만 image 예산을 prior에 넘기면 기존 작은 c_P보다 prior가 크게 강해질 수 있으므로 배율 지도도 함께 확인해야 한다.

\[
L_D=\sum_p w_P(p)|\hat D(p)-D_P(p)|+
                 w_I(p)|\hat D(p)-D_I(p)|.
\]

계수에 이미 분모를 포함했으므로 바깥에서 평균을 다시 취하지 않는다. 결손 target 잔차를 계산한 뒤 0을 곱하는 방식은 NaN 위험이 있으므로 유효 target에서만 평가한다. 비용·가중치는 detach하고 렌더 depth의 미분 경로는 유지한다. 출력은 w_P,w_I뿐 아니라 총강도 s=w_P+w_I, image 비중 q=w_I/s(s>0), 원계수 대비 배율, 실제 depth gradient를 포함한다.

동일 target이고 둘 다 지지되면 기존 감독과 같다. 두 target이 같다는 사실만으로 정확성은 인증되지 않는다. 두 L1 target 사이의 gradient는 계수 차이로 결정되므로 부드러운 가중치가 중간 깊이나 비례한 Gaussian 변위를 보장하지 않는다. 전체 GS에는 RGB·다른 시점·구조 보호·optimizer도 작동한다.

## 5. 현재 실제 반례에 대입하면

P2_high의 normal-plane 비용은 Prior [.3637,.5001,.6557], DA3 [.5235,.5095,.1276]이다. 이미 본 개발 사례의 반올림된 수치로 식을 설명하는 것이며 동일 J*를 다시 집계한 실제 신규 실행 결과가 아니다.

- g=1을 가정해도 Prior는 S=0, R≈.3185, DA3는 S=R=0이다.
- 그러면 w_P≈.6815c_P, w_I=0이다. 낮은 평균 비용이라는 이유로 DA3에 큰 강도를 주지 않는다.
- 실제 v3.7처럼 관측 인증이 없으면 g=0이므로 (w_P,w_I)=(c_P,0)이다.
- **어느 경우도 이 사례에서 더 정확한 DA3를 찾아낸 성공이 아니다.** 불안정한 비용에 대한 확신을 억제할 뿐이며, 잘못된 prior를 보존할 수 있다. 필요한 변화의 미수정률도 반드시 평가한다.

P2 가까운 depth의 plane 비용은 Prior [.0312,.0343,.0617], DA3 [.4172,.6057,.4229]다. g=1이라는 가정에서는 S_P=1,R_P=0,S_I=0,R_I≈.586으로 w_P=c_P+.586c_I, w_I=0이 된다. 이 위치에는 현재 참조 지원이 없으므로 이 선택이 맞는지 모른다. 이 예시는 가중식이 prior를 얼마나 강화할 수 있는지 보여준다.

## 6. 채택 전 검증과 기각 기준

1. **수식 전달**: 9개 명확한 상태 조합, source 비활성·결손, 총량 상한, 연속 입력의 단조성, scalar L1의 독립 수치 미분을 검사한다. 성공은 구현 검증이며 지도 정확성이나 Gaussian 이동 검증이 아니다.
2. **비용 식별력**: 사진만으로 생성한 알려진 기하 장면에서 같은 normal/다른 높이, 기울어진 평면, 두 후보 모두 오답, 반복무늬, 무텍스처, 앞가림, 경계 혼합을 검사한다. 원 depth/plane, 단일 크기/다중 크기를 모두 고정 비교한다. 무텍스처·가림을 높은 R로 바꾸거나 평행 높이 차이를 구별하지 못하는 경우를 실패로 남긴다.
3. **실제 관측 gate**: 실제 RGB 대응 자료를 결박하고 가시성·대응 모호성·시점 지지를 별도로 점검한다. 기존 8개만으로 문턱을 맞추지 않는다. 기존 P2 반례와 이미 열람한 GT 사례는 개발 회귀 사례다. 현재 gate 미결박 상태에서는 이 단계가 통과하지 않은 것이다.
4. **동일 위치 지도 평가**: 점수와 규칙을 고정·해시 기록한 뒤 별도 UAS 평가를 한다. 가중치를 더 받은 source의 참조 근접성, 틀린 source에 준 강도, 올바른 source의 제거, 변경부 미수정과 고정부 손상을 함께 본다. 판단 가능한 면적/참조 지원량도 보고한다. 전부 fallback하는 정책은 정확한 source를 판별한 성공으로 세지 않는다.
5. **최적화 분리**: 비용/gate가 식별력을 보여준 뒤에만 동일 Anchor·source·reduction에서 기존 G, 현 LC, 새 정책을 비교한다. 평균 강도 전역 대조·controller 고정 또는 replay·반복이 없으면 공간 배분 고유효과나 작은 차이의 재현성을 확정하지 않는다. 가중 정책과 DA3→MVS 교체는 별도 요인이다.

처음부터 성공이라고 해석할 평균 정확도 목표를 임의로 채우지 않는다. 첫 실험의 목적은 위 반례 종류에서 비용과 가중식이 의도와 다르게 작동하는지 찾는 것이다. 실제 gate, 평가 지원, 운용 수치가 결박되기 전까지 이 문서는 학습 실행 명세가 아니다.

## 7. 이번에 완료한 구현·검증

- 별도 모듈 `src/phd/local_source_weight_v3_8.py`: 위 S/R/U와 w_P/w_I만 구현했다. 사진·GT·GS 의존성이 없으며 관측 gate 추정기는 아니다.
- `tests/phd/local_complementary_refinement_v1/test_source_weight_v3_8.py`: Docker CPU 15개 테스트 통과. 9개 상태 조합, 계수 0 유지, 20,000개 무작위 총량 검사, 10,000개 evidence 분할, 유효 입력·결손 처리, 단조성, scalar L1 유한차분을 확인했다.
- 재실행 도구 `scripts/phd/local_complementary_refinement_v1/verify_cost_weight_v3_8.py`가 설계 JSON·코드·테스트·자기 자신의 hash, commit, Docker digest, Python/NumPy, 테스트 로그를 기록한다.
- receipt: `JBGS_ARTIFACT_ROOT/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1/main_v2/cost_weight_v3_8/algebra_20260911T120635Z/receipt.json` — PASS_ALGEBRA_ONLY, 15 tests, failures/errors 0. CPU 2, RAM 2 GiB, network none, repository read-only. Python 3.10.20, NumPy 1.26.4.
- 최초 경계 테스트 실패와 수정은 [이슈 기록](ISSUES_COST_WEIGHT_ko_v3_8.md)에 보존했다.
- 실제 새 비용 계산·가중치 지도·관측 gate·Gaussian 업데이트는 이번에 검증하지 않았다. 이전 18조건과 v3.7 결과 및 서비스는 보존했다.

재현할 때 저장소를 `/repo` read-only, 새 외부 산출물 부모를 `/output`으로 마운트한 위 설계 JSON의 Docker image에서 다음을 실행한다. `<new-attempt>`는 존재하지 않는 하위 디렉터리이고 `<actual-commit>`은 현재 Git commit이다. CPU/메모리/네트워크 한도도 JSON과 동일하게 준다.

```bash
python scripts/phd/local_complementary_refinement_v1/verify_cost_weight_v3_8.py \
  --config docs/experiments/phd/local_complementary_refinement_v1/COST_WEIGHT_CANDIDATE_v3_8.json \
  --output /output/<new-attempt> --commit <actual-commit> \
  --image sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
```
