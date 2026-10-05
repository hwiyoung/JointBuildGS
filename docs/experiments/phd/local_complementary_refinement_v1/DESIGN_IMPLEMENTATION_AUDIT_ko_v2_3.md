# LC의 설계·구현·영상 적합·기하 정확도를 구분한 검토

2026-09-11. `scientific_verdict: null`. 기존 실행·입력·결과를 수정하지 않은 추가 검토다.

사용자는 “국소 가중 일반이 잘못된 것이 아니라, 현재 설계나 구현이 잘못된 것은 아닌가”를 질문했다. 이는 타당한 구분이다. 현재 LC의 결과가 약하다는 관측은 국소 가중 방법군의 실패를 입증하지 않는다. 또한 GT를 학습에 쓰지 않는 것은 이 악화의 충분한 설명이 아니다. 기존 G도 동일하게 GT 없이 학습한다. 검토해야 할 것은 코드가 정의한 목표를 실제로 최적화하는지, 그리고 그 목표가 의도한 현재 표면 복구를 유도하도록 설계되었는지다.

## 이전 표의 단면과 G .005 / LC .005의 정확한 뜻

윗단면/아랫단면은 그림의 행이다. 건물 상층/하층 구분이나 현재 3D 카메라가 보는 방향을 뜻하지 않는다. 공통 scene-local 미터 좌표를 사용하며 world shift는 `[690953,5336071,604]`다.

| 이전 표의 이름 | 실제 선택 띠 | 표시하는 두 축 |
|---|---|---|
| P1 윗단면 | `abs(X+8)<0.25m` | 가로 Y, 세로 Z |
| P2 윗단면 | `abs(X-134)<0.25m` | 가로 Y, 세로 Z |
| P2 아랫단면 | `abs(Y-109)<0.25m` | 가로 X, 세로 Z |

각 폭0.5m 띠의 전체 표면 표본을 투영한 그림이다. 정확한 mesh-plane 교선이 아니다. 이전 표는 띠 안 예측 표면 표본→전체 관측 UAS의 평균3D 최근접 거리이며, 화면에서 잰 수직 높이 차이가 아니다.

두 target이 유효한 픽셀에서 G .005는 prior L1에 `.005`, DA3 L1에 `lambdaV(t)`를 곱한다. LC .005는 각각 `.005*(1-a)`, `lambdaV(t)*a`를 곱한다. `a=clip((abs(DP-DV)-.5)/1.5,0,1)`이고, 한 source만 유효하면 그 source 배율은1이다. 각각 원래 source의 유효 픽셀 수로 나눈다. 두 방법의 RGB loss와 기하 정규화는 유지된다.

따라서 같은 lambdaV에서 LC가 DA3 감독의 절대 강도를 높이는 것은 아니다. a는0–1이므로 DA3 감독은 유지되거나 약해진다. 불일치가 큰 곳에서 prior를 줄여 영상 depth의 상대적 비중을 높이는 정책이다. .005라는 이름은 동일한 전역 prior 계수를 뜻하며, 실제 공간별 가중이나 결과 궤적이 같다는 뜻은 아니다.

## 실제 영상 쪽 목표를 더 잘 맞췄는데 기하가 나빠진 사례가 있다

P2 .005 native의 봉인된 G/LC trace에서8100–30000,100step 간격220쌍의 카메라가 같다. 로그 표본 산술평균은 다음과 같다. 서로 다른 카메라56개를 포함하며 한 사진만의 값이 아니다. G와 LC 간 비교이지 초기→최종 단조 수렴을 뜻하지 않는다.

| 항목 | G | LC |
|---|---:|---:|
| Raw DA3 depth L1 | 6.758252m | 4.486759m |
| RGB 학습 목적함수 | 0.11519854 | 0.11397218 |
| Raw prior depth L1 | 9.232047m | 82.890466m |
| 전체 참조점→raw mesh 평균 거리 | 0.737m | 1.070m |

같은220표본에서 전역 DA3 계수 차이는0이다. LC의 공간 가중을 적용한 prior L1 표본평균은0.140536m이므로, raw prior L1 82.89m와 목적함수에 실제 더해지는 값을 혼용하면 안 된다. 큰 오차가 있는 픽셀에 작은 가중을 주는 상관관계 때문에 평균 배율만으로 실제 loss 크기를 환산할 수도 없다.

별도9개 평가 카메라의 전체 PSNR 평균도 LC가0.837dB 높지만, 대표 사진의 고정 ROI는0.514dB 낮다. 따라서 “영상 목표에 전혀 맞춰지지 않았다”와 “영상에 더 맞았으므로3D GT에도 반드시 가까워진다”는 두 주장 모두 관측보다 강하다.

RGB 색·질감의 재현, 고정된 DA3 추정 depth와의 일치, 독립 UAS가 관측한 표면과의 일치는 서로 다른 기준이다. RGB는 기하 외에도 Gaussian의 색·방향별 색 표현·불투명도에 영향을 받는다. DA3는 영상에서 추정한 target으로, 원사진에서 보이는 실제 표면의 정확한 깊이라는 보장이 없다. 같은 현재 표면을 올바로 복구했다면 대응 GT가 개선되리라는 기대는 맞지만, 두 학습 loss의 감소만으로 그 전제를 입증하지 못한다.

## 정의한 식을 구현하는 경로와 설계의 타당성은 별도다

읽은 실제 동결 경로는 `source_v2/train.py`, `source_v2/jbgs_local_depth.py`, `source_v2/gaussian_renderer/__init__.py`, 그리고 기존 loader/입력 감사다. 현재 확인한 경로에서 가중 방향을 반대로 적용하거나 두 번 lambda를 곱한 증거는 발견하지 못했다.

- train.py837–847의 raw loss 계산만 no_grad이며 native controller 입력으로 사용한다.987–1002에서 같은 surf_depth로 국소 loss를 gradient가 있는 문맥에서 다시 계산하고, 각 전역 계수를 한 번만 곱해 RGB·정규화와 합친다.1006–1008에서 backward와 optimizer step을 호출한다.
- local_depth_loss_v2.py106–117의 no_grad는 validity와 고정 target 기반 gate를 만든다.118–119의 잔차 계산에서는 prediction gradient가 남는다. target·gate를 detach하는 것과 prediction까지 detach하는 것은 다르다.
- 실제 분모는 원래 각 source의 유효 픽셀 수이며 국소 가중 합으로 재정규화하지 않는다. 따라서 공간 배분과 전체 감독 강도가 함께 바뀐다. 이것은 v2 명세와 일치하지만 순수 공간 배분 효과를 분리하는 설계는 아니다.
- renderer의 surf_depth에는 detach가 없고, 기본 depth_ratio=0에서 불투명도 누적값으로 정규화한 expected depth를 사용한다. 이는 여러 Gaussian 기여의 평균 깊이이며 반드시 단일 실제 표면의 first hit와 같은 것은 아니다. 최종 TSDF도 이 렌더 깊이를 사용하지만, 평균 깊이 적합이 올바른 표면 복구를 보장하지 않는다.

CPU에서 loss→prediction gradient가 맞고 실제 결합식이 호출된다는 검증은 CUDA rasterizer 전체, Gaussian 파라미터별 gradient와 최종 표면 변위의 원인을 모두 검증한 것은 아니다. 기존 native 보호의 gradient hook도 Adam 아래에서 단순 학습률 배율과 같은 의미로 읽지 않는다. 이러한 남는 검증 범위를 “구현 오류가 완전히 배제됐다”로 바꾸지 않는다.

이번 추가 CPU 감사에서 관련 기존16개 테스트가 실패·오류·skip 없이 통과했고, 동결된 train/renderer의 실제 AST를 실행해 total_loss 및 prediction·expected-depth 분자·alpha gradient를 수작업 기대값과 대조했다. 코드5파일의 hash가 실제 P2 실행 invocation과 일치했다. `main_v2/implementation_audit/attempt_20260911T042717Z_dtypealigned_retry/receipt.json`이 근거다. CUDA backward wrapper의 depth gradient 전달은 source에서 확인했으며 이번에는 CUDA kernel 자체를 새로 실행하지 않았다.

## 현재 설계에서 직접 드러나는 부족

큰 불일치일 때 어느 source가 더 맞는지 판별하는 신호가 없다. 예를 들어 prior10m,DA3 12m이면 a=1로 영상 depth를 택한다. 실제 표면이10m인 경우와12m인 경우에 입력 불일치는 같지만 필요한 행동은 반대다. 현재 식은 이 둘을 구분할 수 없다. 이는 실제 GS의 전체 변위를 예측하는 모형이 아니라 gate가 이용하는 정보의 한계를 보이는 예다.

P1 노출 포장면 사례에서는 prior가 참조에 가깝고 DA3는 약2.44m 높은데 a=1이다. 이 연결은 “큰 불일치→영상 감독을 유지하고 prior를 제거”하는 정책의 위험을 보여준다. 국소 가중이라는 도구 일반의 실패가 아니다.

**source 선택과 감독 총강도를 함께 바꾸는 설계도 따로 문제 삼아야 한다.** 두 target이 정확히 같고 두 source의 유효 집합/분모가 같은 축약 예에서 a=0이다. G .005는 같은 depth 잔차에 .005+.05=.055를 곱하지만 LC .005는 DA3 항을 꺼서 .005만 남는다. 즉 동일 target을 향한 depth gradient가1/11이 된다. .0005에서는 .0505→.0005로1/101이고, prior계수0에서는 두 depth 항이 모두0이다. 이 비율은 lambdaV=.05와 동일 분모라는 예시 조건에 한정하며 실제 GS 위치 update 비율은 아니다.

두 source가 일치하는 곳에서도 다른 목적함수나 이웃 Gaussian의 영향으로 기하가 움직일 수 있으므로, target끼리의 일치가 그곳의 depth 감독을 약화해도 된다는 보장은 아니다. 이 동작은 명세대로 구현됐지만, “맞는 구조는 지키면서 필요한 곳을 고친다”는 목적에 적절한 설계인지는 별도로 검증해야 한다. 이 효과가 실제 손상의 전부라고 확정하지 않는다.

현재 gate는 고정 입력으로 정해져 학습 중 갱신되지 않는다. 해당 국소 업데이트가 여러 영상에서 표면 기하를 개선했는지 확인하고 되돌리는 절차도 이 새 모듈에는 없다. 기반 GS가 여러 사진의 RGB와 기하 정규화를 사용하지 않는다는 뜻은 아니다. 새 정책 자체가 허용한 국소 행동의 적절성을 별도로 판별하지 않는다는 뜻이다.

입력 감사에 남긴 camera-Z와 거리 정의, 반픽셀 ray convention 차이, 결손 경계의 보간, prior와 DA3가 같은 가시 표면을 가리키는지 여부도 구분해야 한다. 단위·해상도가 맞는다는 사실만으로 source의 정확성이나 같은 표면 대응이 보장되지는 않는다. 기존 G와 공유하는 입력 차이라도 LC가 불일치를 문턱으로 사용하면 영향이 달라질 수 있다. 현재 결과에서 그 기여 크기를 분리한 실험은 없다.

추가 입력 경로 검토에서는 카메라 이름/array shape 혼동, camera-Z와 ray 거리 혼동, DA3 역척도 적용 오류를 발견하지 못했다. 현재 loader의 입력과 출력 크기는 같아 일반 resize 경계 문제를 이번 악화의 확인된 원인으로 제시하지 않는다. 다만 DA3 API는 pose 기반 scale로 depth를 조정한 뒤 반환 pose를 입력 pose로 교체하므로, 반환 pose가 입력과 같다는 검사는 원 예측 pose·척도의 정확성을 입증하지 못한다. 당시 scale 인자와 교체 전 pose가 저장되지 않아 그 생성 단계의 정확성을 현재 파일만으로 완전히 재검증할 수는 없다. 수십~수백m target 불일치의 원인은 source 오류·가시성·표현·정합 사이에서 여전히 미분리다.

현재 판단은 **현재 구현이 명세와 다르게 작동한다는 오류는 확인되지 않았지만, 현재의 불일치→DA3 상대 우선 설계가 의도한 국소 표면 보정을 충분히 표현한다는 근거도 없다**는 것이다. 앞의 기여 분석은 이 특정 구현·정책에 한정한다. 국소 보정·가중치 방법군을 기각하지 않는다. GT는 계속 평가 전용이다.

## 증거 경로

- 실행 계약: `configs/phd/local_complementary_refinement_v1/experiment_v2.json`과 `MAIN_SPEC_ko_v2.md`.
- Loss 구현: `scripts/phd/local_complementary_refinement_v1/local_depth_loss_v2.py`, `prepare_source_v2.py`, 외부 task root의 `source_v2/`.
- P2 trace 원표: `main_v2/trace_monitor/attempt_20260910T153454Z_final_P2_D005/condition_summary.csv`, SHA256 `5c58e230b4e5e9548ccaba7760ca28dc9c6596aa5a49826e45ef39fb045813fe`.
- 같은 trace attempt의 `source_snapshots/G/`, `source_snapshots/LC/`와 `trace_summary.json`.
- 기하 연속거리: `main_v2/contribution_review_v2_2/attempt_20260911T025441_538040Z/continuous_metrics.csv`.
- 고정 단면: `scripts/phd/local_complementary_refinement_v1/evaluation_visuals_v2.py:34`, 기존 보고서의 고정 표본 띠.
- 사진·target 사례: `PHOTO_TARGET_CASE_REVIEW_ko_v2.md`; 평균·대표 사진 구분: `INTERIM_P2_D005_ko_v2.md`.
- 이번 loss/renderer CPU 감사: `main_v2/implementation_audit/attempt_20260911T042717Z_dtypealigned_retry/receipt.json` 및 `AUDIT_NOTES_ko.md`.
- 입력 정의 감사: 외부 task root `preflight/input_audit_v2/input_audit_v2.json`; 기존 G task의 `runtime/camera_projection_v1/receipt.json`, `sources/Depth-Anything-3/src/depth_anything_3/api.py:341`.

조회 과정에서 존재하지 않는 `src/phd/local_depth_loss.py`, `trace_v2.py` 경로가 각 exit2를 반환했다. 실제 `local_depth_loss_v2.py`, `summarize_traces_v2.py`를 찾아 읽었으며 원본 파일을 수정하지 않았다. 이 조회 실패는 실험/입력 실패가 아니다.

첫 추가 합성 fixture는 depth float64/RGB float32를 섞어 dtype 동일성 assertion에서 실패했다. 원 실패 attempt를 보존하고 fixture의 dtype만 맞춘 별도 attempt에서 통과했다. 실제 LC 코드나 수치를 고친 것이 아니며 원 실험 실패로 분류하지 않는다.
