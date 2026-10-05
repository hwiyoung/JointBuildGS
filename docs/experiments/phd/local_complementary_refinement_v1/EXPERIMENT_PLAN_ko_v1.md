# 국소 상보 depth refinement — 실행·평가 계획

- 작성일: 2026-09-10
- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- 상태: `PLAN_FOR_NEXT_SESSION / MAIN_EXPERIMENT_NOT_STARTED`
- scientific_verdict: null
- 기존 기술 준비 config 초안: [experiment_v1.json](../../../../configs/phd/local_complementary_refinement_v1/experiment_v1.json). 이 파일의 이전 Q50/Q90·완료 진행 문구는 최신 실행 범위를 나타내지 않는다. 본실험 config는 다음 세션의 명세에 맞춰 별도로 결박한다.
- 방법·학위 기여 판단: [별도 검토](PHD_CONTRIBUTION_REVIEW_ko_v1.md)
- 자원·기존 산출물 재사용 근거: [자원 검토](RESOURCE_AND_REUSE_REVIEW_ko_v1.md)

**사용자의 최신 정정에 따라 실험은 새 세션에서 진행하고, 이번 대화에서는 계획을 정리한다. 전체 18조건 본실험은 시작하지 않았다.** 앞선 완료 시각 관련 지시를 현재 실험 실행으로 해석하는 과정에서 P2 native의 GPU 1-step 기술 probe가 이미 수행됐다. 이 범위 오해와 실제 실행을 [ISSUES](ISSUES_ko_v1.md#lc-scope-002--실험-세션-범위-오해와-p2-native-1-step-probe)에 명시하고, 추가 실행·종속 구현·검증은 중단했다. 기존 실험 계약·코드·입력·결과·서비스와 이미 생긴 기술 산출물은 보존한다. 아래 조건과 순서는 **다음 세션의 실험 계획**이며 현재 실행 지시가 아니다.

## 1. 검증할 질문과 방법의 정확한 범위

완성 GeoGS의 기존 ALS 적용판에 비해, 동일한 prior·DA3 depth의 **국소 불일치를 상보 가중으로 배분**하면 필요한 수정과 유효 구조 손상의 균형이 개선되는지 검토한다. 기존 전역 prior 가중의 세 수준과 독립적인 native/release 보호 상태를 함께 대조한다. 기존 GeoGS가 이미 성공한 수정·보존을 기준 성과로 인정하고, 새 방법의 악화도 같은 표에 포함한다.

첫 후보는 추가 신뢰도 추정기·normal 감독·원영상 다중 시점 loss·새 depth target을 도입하지 않는다. 고정된 두 target에서 정해지는 정적 국소 제어다. 이 선택은 이번 최소 비교의 범위이며, ALS·DA3·GS를 학위 연구 전체의 필수 입력이나 유일한 표현으로 확정하지 않는다.

동일 ray·미터 단위의 prior depth를 \(D_P\), 현재 영상 파생 depth를 \(D_V\), GS의 렌더링 depth를 \(\hat D_t\)라 한다. 두 target이 모두 유효한 곳에서

\[
\Delta_p=|D_{P,p}-D_{V,p}|,\qquad
a_p=\operatorname{clip}\!\left(\frac{\Delta_p-\tau_0}{\tau_1-\tau_0},0,1\right),
\qquad 0\le\tau_0<\tau_1.
\]

작은 불일치에서는 prior 요구를 유지하고, 큰 불일치에서는 영상 depth 요구를 허용하는 정책이다. **큰 불일치가 영상의 정확성을 입증하는 것은 아니다.** 동일한 \(D_P,D_V\)에 대해 실제로 prior가 맞는 경우와 영상 target이 맞는 경우는 같은 \(a_p\)를 얻는다. 따라서 이 규칙의 유효 범위와 반례를 실험으로 확인해야 한다.

## 2. 입력 결박과 아직 확정하지 않은 문턱

각 지역의 기존 봉인 입력과 complete Anchor8k를 재사용한다. 입력 manifest·각 파일 hash·Anchor receipt와 checkpoint hash의 일치를 확인한다. 새 scene 정합, DA3 추론, Anchor 재학습은 계획하지 않는다. 학습 컨테이너에는 해당 지역 입력·Anchor·새 source를 필요한 범위로만 연결하고 평가 참조는 연결하지 않는다.

GT·test 영상·최종 복원 오차를 이용해 문턱이나 지역별 최적값을 고르지 않는다. 동일 단위·ray·resize·유효 mask의 입력 target을 사용하는지 먼저 확인하고, **전체 18조건에 하나의 공통 미터값 쌍**을 적용하는 계획을 유지한다. 다만 본실험의 \(\tau_0,\tau_1\)은 아직 확정하지 않았다.

초기 기술 준비에서는 [prepare_inputs.py](../../../../scripts/phd/local_complementary_refinement_v1/prepare_inputs.py)로 train view마다 유효 flattened index에서 최대 4,096개를 균일 간격으로 선택하고, 지역별 최대 200,000개를 다시 같은 수로 맞춰 Q50/Q90을 계산했다. 이는 건물별·면적별 균등 표본이 아니라 **view의 pixel 표본을 지역 간 같은 수로 맞춘 분포**이며, 여러 시점의 중복 관측도 남는다. 이 절차에서 약 **30.8266m / 138.2346m**가 나왔고 P2 1-step 기술 probe에 사용됐다. 이 값이 건물의 필요한 보정 규모를 잘 구별하는 문턱인지 의문이 제기돼 본실험 적용을 확정하지 않았다. 이는 기술 준비의 결과이며 방법 성능에 대한 실패 판정은 아니다.

현재 검토 후보는 **\(\tau_0=0.5\)m, \(\tau_1=2.0\)m의 공통 고정 경계**다. 이 경우 0.5m 이하에서는 prior 요구를 유지하고, 0.5–2m 구간에서 전이하며, 2m 이상에서는 공통 유효 영역의 영상 depth 요구를 허용한다. 과거 설명용 수치를 이번에 검토 후보로 명시하는 것이며, 이미 검증·동결됐다는 뜻이 아니다. 이 물리적 범위가 실제 prior·영상 target의 정합 오차와 필요한 보정 범위를 구별하는지, 유효 prior에 대한 영상 오류까지 과도하게 허용하는지 다음 세션의 명세에서 따져야 한다. 새 신뢰도 estimator를 자동으로 도입하는 결정도 아니다.

초기 Q50/Q90 binding과 probe는 그대로 보존한다. 본실험 정책을 정할 때 그 값을 기존 `contracts/input_binding.json`에 덮어쓰지 않고 **새 계약 revision의 `input_binding.json`**과 실행 receipt에 기록한다. 준비 중인 main revision 경로는 `contracts/main_v1/`이며, 그 디렉터리나 draft 파일이 존재한다는 사실은 실행 준비 완료를 뜻하지 않는다. 현재 `execution_gate.py`도 미검증 초안이며 실행하지 않았다.

## 3. 실제 loss와 결손·분모 규약

기존 native depth loss와 같은 source별 유효 집합을 \(S_P,S_V\)라 한다. Target은 유한·양수, prediction은 유한이어야 한다. Prediction의 음수값은 기존 함수와 마찬가지로 유효하게 남겨 metric 오차로 벌점을 준다. Source mask가 있으면 같은 mask의 양수 영역을 사용한다.

| Target 유효성 | prior의 국소 배율 \(b_{P,p}\) | 영상의 국소 배율 \(b_{V,p}\) |
|---|---:|---:|
| 둘 다 유효 | \(1-a_p\) | \(a_p\) |
| prior만 유효 | 1 | 0 |
| 영상만 유효 | 0 | 1 |
| 둘 다 없음 또는 prediction 비유한 | 0 | 0 |

공통 유효 영역 밖의 결손을 큰 불일치나 \(a=0\)으로 대체하지 않는다. 결손 시 한쪽 감독을 사용한다는 것은 그 source의 정확성을 인증한다는 뜻이 아니다.

Confidence 옵션이 비활성일 때 실제 stage-2 depth 항은

\[
L_D(t)=\lambda_P\frac{\sum_{p\in S_P}b_{P,p}|\hat D_{t,p}-D_{P,p}|}{|S_P|}
+\lambda_V(t)\frac{\sum_{p\in S_V}b_{V,p}|\hat D_{t,p}-D_{V,p}|}{|S_V|}.
\]

해당 source의 유효 집합이 비면 그 source 항은 0이다. **Source별 기존 valid-pixel 분모를 유지**하며 \(\sum b_P\), \(\sum b_V\)로 재정규화하지 않는다. 두 source의 유효 집합이 같을 때만 하나의 공통 분모로 줄여 쓸 수 있다.

이번 대응 실행의 confidence 옵션은 비활성으로 유지한다. 구현의 선택적 confidence 경로를 설명하면, 기존 실행에서 이 옵션이 활성인 경우 기존 normalized confidence \(c_p\)와 native 분모를 유지하여 영상 항을

\[
\lambda_V(t)\frac{\sum_{p\in S_V}c_p b_{V,p}|\hat D_{t,p}-D_{V,p}|}{\sum_{p\in S_V}c_p+10^{-6}}
\]

로 계산한다. Confidence 합이 0이면 native와 같은 valid-pixel mean fallback을 쓴다. 원 실행의 옵션을 새 실험에서 임의 활성화하지 않으며, valid source의 비유한·음수 confidence는 실행 오류로 드러낸다.

\(\lambda_P,\lambda_V(t)\)는 source별 전역 계수이고 \(a_p\)는 픽셀별 배율이다. \(\lambda_P\ne\lambda_V\)이면 \(a=.5\)에서 두 최종 계수는 같지 않고, 전체 depth 감독 강도도 위치에 따라 달라진다. \(D_P=D_V\)이고 \(a=0\)이면 동일 깊이를 prior 항이 계속 감독한다.

동일 valid-count·confidence 비활성·독립적인 한 깊이 변수의 L1 축약에서는 두 계수의 교차가 \(\lambda_P(1-a)=\lambda_Va\)에서 일어난다. \(\lambda_P=.005,\lambda_V=.05\)이면 \(a=1/11\approx.091\)이다. 이 값보다 작으면 prior, 크면 영상 target이 해당 축약의 최소해이며, 동률에서는 두 target 사이가 모두 최소해다. 이는 실제 GS·RGB·보호·생성/삭제가 결합된 이동을 예측하는 식이 아니다.

특히 \(\lambda_P=0\) 조건은 영상 항 \(\lambda_V(t)a_pL_V\)의 공간적 감쇠를 시험한다. \(a_p\) 계산과 Anchor·보호 이력에 prior가 남으므로 no-prior 조건이라고 부르지 않는다.

## 4. 변경 경로와 보존하는 제어

[local_depth_loss.py](../../../../scripts/phd/local_complementary_refinement_v1/local_depth_loss.py)는 stage 2의 total loss에 들어가는 두 depth 항에만 국소 배율을 적용한다. RGB·기존 활성 기하 정규화·renderer·원 depth 정의·다른 학습 정책은 동일하게 둔다.

- 원래 `lod_depth_loss`, `da_depth_loss`의 **가중 전 값과 계산 정의**를 controller·기존 로그에 그대로 전달한다. Enabled stage 2에서는 이 raw 값의 불필요한 autograd graph만 생략한다. Stage 1과 disabled 모드는 원 loss 경로를 유지한다.
- 기존 adaptive DA3 정책은 그대로 작동한다. 기하 궤적이 바뀌면 raw loss 경과와 실제 \(\lambda_V(t)\)가 달라질 수 있다. 첫 비교는 **국소 배율과 기존 controller 반응을 합친 변경 효과**이며, 동일한 실현 계수 궤적의 비교라고 부르지 않는다.
- \(a_p\)와 target은 gradient에서 분리하고, \(\hat D_t\)의 gradient는 유지한다. 배율을 자유롭게 학습해 loss를 0으로 만드는 새 estimator는 없다.
- 환경변수 `JBGS_LOCAL_DEPTH_MODE=complementary`, `JBGS_LOCAL_TAU0`, `JBGS_LOCAL_TAU1`로 실행한다. 새 argparse 항목을 추가하지 않는다. `disabled`는 원 depth loss 객체를 그대로 반환한다.
- [prepare_source.py](../../../../scripts/phd/local_complementary_refinement_v1/prepare_source.py)는 원 source를 새 디렉터리로 복사하고 exact-string assertion 후 선언된 경로만 패치한다. 기존 checkpoint의 parent source/implementation hash와 현재 prepared source hash를 모두 검증하며, 원 checkpoint의 hash 검사를 무조건 건너뛰지 않는다. 기존 source·checkpoint bytes는 바꾸지 않는다.

Prior depth의 계수와 구조 보호는 별도 요인이다. Native는 기존 gradient 감쇠와 생성/삭제 보호를 유지하고, release는 기존 비교에서 정의한 보호 해제 설정을 재사용한다. Release는 여러 보호 경로를 함께 바꾸는 묶음이므로 그것만으로 특정 보호 경로의 원인을 확정하지 않는다. 국소 depth 배율이 0이라는 사실도 Gaussian 전체나 최종 표면이 고정된다는 뜻은 아니다.

## 5. 18조건과 실행 순서

새 조건은 **3지역 × 3전역 prior 계수 × 2보호 상태 = 18개**, 각 1회다. 지역마다 같은 complete Anchor8k에서 8,001–30,000의 22,000 step을 수행한다. 총 새 refinement step은 396,000이다. 기존 18개는 새 학습을 반복하지 않고 대응 대조로 재사용한다.

| 신규 조건 ID | 기존 대응 조건 | \(\lambda_P\) | 보호 |
|---|---|---:|---|
| `LC_D005_Pnative` | `D005_Pnative` | .005 | native |
| `LC_D005_Prelease` | `D005_Prelease` | .005 | release |
| `LC_D0005_Pnative` | `D0005_Pnative` | .0005 | native |
| `LC_D0005_Prelease` | `D0005_Prelease` | .0005 | release |
| `LC_D0_Pnative` | `D0_Pnative` | 0 | native |
| `LC_D0_Prelease` | `D0_Prelease` | 0 | release |

지역별 Anchor 위치·receipt hash는 [자원 검토 §2](RESOURCE_AND_REUSE_REVIEW_ko_v1.md#2-정확한-재사용-경로), 실행 시 실제 검증 결과는 input binding이 기준이다. PLY만으로 재초기화하지 않고 모델·optimizer·RNG·카메라 stack·controller·보호 상태가 포함된 complete checkpoint를 사용한다.

다음 세션의 예정 실행 순서는 `.005` 여섯 조건, `.0005` 여섯 조건, `0` 여섯 조건이다. 각 그룹에서 P2, P1, P3의 native/release 대응 쌍을 우선한다. 자원 gate에 따라 두 GPU에 최대 두 학습을 병렬 배치하되 기존 서비스를 종료하거나 다른 실행을 덮어쓰지 않는다. 이 순서는 완료 우선순위이며 유리한 결과만 골라 보고하는 기준이 아니다. 실제 실행 시 중간 결과를 기록·제시한다. 이번 대화에서는 queue를 시작하지 않는다.

## 6. 질문별 최소 비교·관측·기각 조건

| 질문 | 이번 최소 비교 | 관측할 것 | 기각·축소 또는 후속 분리 조건 |
|---|---|---|---|
| 국소 상보 가중이 기존 제어보다 수정·보존을 개선하는가? | 각 지역·계수·보호가 같은 기존 G와 신규 LC의 대응 비교; 기존 3계수의 성공도 함께 공개 | 같은 부위의 필요한 보정과 유효 구조 손상, 정확도·완전성·표면 피복 | 기존 전역 제어의 좋은 조건이 같은 균형을 달성하면 국소 규칙의 증분 기여 축소; LC가 손상만 늘리면 해당 유효성 가설 기각 |
| 큰 불일치에서 영상을 우선하는 정책이 타당한가? | 동일 \(\Delta\) 범위 안에서 prior가 유효한 부분과 영상 target이 유효한 부분의 평가 결과 대조 | 큰 \(a\)가 적용된 위치, 두 target의 평가 전용 오차, LC의 실제 이동·손상 | 영상 target이 틀린 큰 불일치에서 정확한 prior를 손상하면 정책의 적용 가정이 깨짐; 불일치 자체를 정확성 신뢰도로 해석하지 않음 |
| 변화가 보호 제어만으로 설명되는가? | `(LC−G)_native`와 `(LC−G)_release`, 같은 계수의 native/release | 보호된 Gaussian 수, 표면 이동, 새 생성·삭제와 경계·세부 변화 | 기존 release만으로 동등한 수정이면 LC 기여 축소; release에서만 LC가 유리하면 보호와의 상호작용까지만 해석 |
| LC의 효과가 국소 배분보다 평균 감독 강도 감소 때문인가? | 이번 18개에서 source별 평균 배율·유효 pixel 수·weighted/raw loss를 기록하고 기존 계수 수준과 대조 | 평균 유효 계수와 geometry 변화의 동행, \(\lambda_P=0\)에서 영상 감쇠 효과 | 첫 18개만으로 완전히 분리되지 않으면 평균 배율을 맞춘 전역 상보 대조를 후속 설계; 이 대조 없이 국소 배분만의 효과로 확정하지 않음 |
| 기존 adaptive DA3 반응이 결과 차이에 기여했는가? | 대응 G/LC의 raw depth/RGB·phase·\(\lambda_V(t)\) trace | 실제 controller 궤적의 동일·상이 여부와 변경 시점 | 궤적 차이가 있으면 전체 효과로 보고; 국소 배율만 분리해야 하면 동일 baseline schedule을 양쪽에 고정 재생하는 별도 대조 필요 |
| 결손·두 target 오류를 가중만으로 해결할 수 있는가? | single-valid/both-valid/neither와 두 target 오류의 평가 strata | 영상의 관측 가능성, Anchor부터 누락된 기하, 현재 GS·추출 표면 차이 | 두 target이 틀려 수정 방향이 부족하면 가중 재배분의 한계로 기록; RGB의 추가 기하 효과까지 부정하지 않고 정보 부족/활용 실패를 구분 |
| 효과가 renderer·추출·평가 피복에 의존하는가? | 같은 cameras·깊이 정의·512 TSDF 설정의 Anchor/G/LC 및 raw/postprocessed 표면 | rendered depth와 mesh의 차이, 후처리 제거량, 평가 가능한 reference 범위 | 평가 범위나 후처리 차이로 개선이 설명되면 학습 기하 개선 주장 축소; 해상도·후처리를 섞은 표로 우열 판단 금지 |

평균 배율 대조·controller replay·추가 관측 estimator는 이번 18개에 자동 포함하지 않는다. 이번 결과와 trace에서 해석이 갈리는 경우 후속 최소 비교로 구체화한다. 조건별 1회이므로 반복 안정성이나 모집단 일반화를 확정하지 않는다.

## 7. 평가와 보고

정확도, 완전성, 현재성을 뒷받침하는 근거, 관측 가능한 세부, 외관, 계산량을 분리한다. **필요한 수정과 유효 구조 손상을 같은 공간 영역에서 함께 평가**한다. Prior/원영상의 O/X는 평가 조건이며 학습 라벨이 아니다. 원영상은 관측 가능하지만 DA3 target이 틀린 경우를 별도로 표시한다.

- 원영상·고정 카메라·동일 단면·동일 영역에서 Anchor, 기존 G, 신규 LC를 나란히 비교한다. 지표 집계에 들어가는 reference 피복과 prediction 결손을 함께 기록한다.
- 기하 평가는 config의 동일 512 TSDF를 사용하며 raw 표면이 주 비교, 동일 후처리 표면은 보조 비교다. 기존 같은 설정 산출물이 있으면 그대로 재사용한다. 필요한 동일 설정 후처리·평가는 봉인된 기존 checkpoint의 별도 파생 경로에 작성하고 학습을 다시 수행하지 않는다.
- P2의 낮은 prior 계수에서 형상도 좋아졌다는 기존 관찰을 평균 F1만으로 부정하지 않는다. 정확도·완전성·평가 범위를 나눠 해석한다. P3에서 낮은 가중이 악화될 것이라고 미리 판정하지 않는다.
- GT는 평가에만 사용한다. 문턱·loss·ROI 선택·학습 감독에 참조 표면이나 평가 라벨을 전달하지 않는다. 현재성도 prior 재현만으로 인정하지 않는다.
- `local_trace.jsonl`은 첫 stage-2 step과 매 100 step의 raw/weighted source loss, 유효·결손 pixel 수, \(a\) 평균·포화 수, 실제 전역 계수와 평균 유효 계수를 기록한다. 기존 `jbgs_trace.jsonl`·complete-state receipt와 연결한다.
- 계산량은 22,000 refinement step의 wall time, GPU peak memory, host memory, Gaussian 수와 평가·추출 비용을 구분한다. 같은 step 수를 같은 wall time이나 primitive 계산량으로 부르지 않는다.

모든 대응 조건의 성공·악화·실행 실패를 보고한다. 결과를 보고 지역별 최적 조건만 선택한 방법을 배포 가능한 규칙으로 제시하지 않는다. 분석·구현 검증·개발 성능·과학적 결론은 구분하며 모든 기술 receipt는 `scientific_verdict: null`을 유지한다.

## 8. 자원·기술 검증·실행 편차

기존 고정 Docker 이미지 `jointbuildgs:geogs-official-db40c95-compat-v1`을 재사용한다. Config는 작업당 CPU 8개·RAM 32GiB, 최대 병렬 학습 2개, 기존 native allocator 설정을 명시한다. 실제 시작은 GPU·host 가용량 gate를 확인한 시점에만 수행한다. 기존 viewer·플랫폼·브라우저·remote desktop을 변경해 자원을 확보하지 않는다.

전체 18개 학습·준비는 **약 17–20시간의 계획 추정이며 평가·추출 시간은 추가**다. 기존 실행 비용과 두 GPU 병렬화를 이용한 추정이고 새 방법의 실측 완료 시간은 아니다. 다음 세션에서 실행할 때 첫 대응 쌍의 실제 시간·메모리로 남은 예상 시간을 갱신한다. 이전 완료 시각 논의보다 최신의 **새 세션에서 실험**이라는 범위 정정을 우선하며, 이 추정을 현재 실행이나 완료 보장으로 사용하지 않는다.

CPU Docker 단위검증은 exact multipixel L1/gradient, unequal 전역 계수, \(\lambda_P=0\), 동일 target, mask·결손·NaN·음수 prediction, confidence 분모·fallback, disabled 경로, trace 간격, source provenance의 오류 검출을 포함한다. 원본 source의 임시 복사에서는 exact patch와 raw native loss AST 불변·parent/runtime hash 검증을 확인했다. 상세 실패와 조치는 [ISSUES](ISSUES_ko_v1.md)에 기록한다. 이 CPU 통과를 GPU 수렴·메모리 충분성·연구 성과의 증거로 확대하지 않는다.

OOM·입력 hash 불일치·문턱 퇴화·restore 실패·평가 예외가 발생하면 원 산출물을 보존하고 새 시도의 상태·오류·변경을 기록한다. 학습량·해상도·생성/삭제 정책을 몰래 줄이거나 실패 run을 삭제하지 않는다. 승인된 범위 안의 재시도도 동일 실패가 반복되는 이유와 실제 편차를 확인한 뒤 별도 receipt로 남긴다.

## 9. 이번 세션의 실제 진행 상태와 다음 세션 경계

| 항목 | 실제 상태 |
|---|---|
| 국소 loss·source 복사 patch | 초안 구현 작성; CPU 단위검증 16개 및 실제 source 임시 복사 검증 통과 |
| 입력 기반 Q50/Q90 계산 | 기술 준비에서 수행; 초기 binding·표본 보존; 본실험 문턱으로 미확정 |
| P2 `.005 × native` GPU probe | complete Anchor8000에서 8001까지 1 step 수행; 기술 PASS와 scope 오해를 함께 기록 |
| `.005 × release` 및 다른 GPU probe | 이 계획에서 완료했다고 주장하지 않음; 추가 실행 중단 |
| 전체 18개 refinement 본실험 | **미시작; 새 세션의 예정 작업** |
| 신규 본실험 mesh·외관·기하 평가 | 미시작 |
| 실행 gate·queue·평가 driver | 작성된 초안 보존; `execution_gate.py`는 실행·검증하지 않음; 추가 종속 구현 중단 |

이 문서와 이슈 기록의 정리는 계속하되, 이번 대화에서 새 학습·추론·렌더·재구성·방법 실험을 추가로 시작하지 않는다. 기술 probe의 성공을 실험 완료나 가설 검증으로 바꾸지 않는다.
