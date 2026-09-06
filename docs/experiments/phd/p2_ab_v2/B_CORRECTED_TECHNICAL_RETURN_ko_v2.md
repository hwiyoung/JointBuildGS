# B v2 수정 후 Technical Return

`scientific_verdict: null`. 기존 v2 결과는 [구현 오류와 수정 검산](B_GEOMETRY_ADAPTER_CORRECTION_ko_v2.md)에 따라 `INVALID_FOR_METHOD_CONCLUSION`으로 보존한다. 이 문서는 독립 plane geometry 합성으로 재실행한 조건부 개발 시험만 다룬다.

## 1. 시험하는 것

사용 지지된 과거 구조를 유지하며 현재 영상의 색과 관측 가능한 국소 형상을 복원하는 것이 B의 목적이다. 이번 시험은 **과거 ALS를 쓴다는 조건을 사전에 고정한 기제 시험**이며 A가 해당 ALS의 현재 사용을 승인한 실험이 아니다. 불확실한 A 변형 예산을 만들어 넣거나 detail을 전부 고정하지 않았다.

같은 ALS 초기 Gaussian에 대해 색만 변경, 기하만 변경, 자유 기하+색, 약/기본/강 soft prior, 구조 범위+detail을 비교했다. MVS image_only는 초기 source와 밀도가 다른 총효과 기준이다. native ALS 45,986개, MVS 266,361개, 4분할 ALS 183,944개 Gaussian의 실제 상태를 저장한다. 4분할은 부모 접선 좌표에서 ±0.5×scale 위치, 절반 scale의 네 자식이다. 원본 관측이나 새 구조를 네 배로 얻은 것이 아니며 opacity 합성·지원·그룹 배치도 바뀐다.

초기 색은 현재 train 영상의 조건부 가시 투영 중앙값이며 미관측 색은 0.5이다. SH0만 학습한다. 원본 undistorted crop과 33 train/11 eval 뷰를 사용하고 최대 변 1536px 및 768px train tile로 메모리를 제한했다. 초기 무최적화 상태·render도 보존한다. 모든 비교는 2,048회 같은 예산이며 수렴을 가정하지 않는다.

수정 native ALS의 상세 분모는 다음과 같다. 원본 1024×741 fullscene COLMAP depth의 2×2 표본이 모두 알려지고 그 최대 depth+1m도 G0보다 앞일 때만 해당 관측을 제외한다. depth 미상은 별도로 남기며 A의 prior 거부로 바꾸지 않는다.

| 초기 ray 분모 | train33 | eval11 |
|---|---:|---:|
| RGB alpha≥0.5 | 16,580,779 | 5,509,940 |
| 독립 geometry mass≥0.5 | 16,569,078 | 5,506,873 |
| 전경 제외 | 2,121,327 | 833,611 |
| 남은 조건부 관측 | 14,447,751 | 4,673,262 |
| geometry 지지 중 context depth 미상 | 2,466,218 | 2,003,608 |

관측 3뷰 이상인 native ALS 점은30,562개, 관측 rank를 반영한 가능한 위치 detail DOF 합은83,118이다. 이 뷰들은 과거 개발에 노출되었으며 조건부 source self-visibility를 새 독립 판단 증거로 부르지 않는다.

## 2. 실제 자유도와 손실

그룹의 affine 위치 성분과 그 성분에 직교한 관측점의 **3차원 위치 detail**을 분리한다. 관측 3뷰 미만 점의 detail·rotation은 0이고 원래 source 분모에는 남는다. 그 점에 대한 그룹 구조 이동은 조건부 구조 추론이다. 제안은 거친 이동 최대 0.15m와 관측점 평균 회전 벡터 5°를 제한한다. 공통 detail domain은 초기 scale×3을 [0.25,1.5]m로 제한한 값, 개별 회전은 35°, tangent scale 비율은 [0.4,2], opacity는 [0.05,0.995], decoded SH0는 [0,1]이다. 이 범위는 solver 설정이며 현재 표면 오차 보장이 아니다.

공통 손실은 0.8 RGB L1 +0.2 (1−masked SSIM11), geometry mass coverage 목표0.7의 hinge 가중치0.1, 유효 기하 이웃의 depth-normal 일관성0.05, train-view multiview 일관성0.1이다. multiview는 4회마다 source와 target 기하 및 관측 mask를 모두 확인하며 camera-Z smooth L1(β0.1m), 법선×0.1, image warp L1×0.1을 사용한다. 0.5m depth gate는 계산상 inlier 조건이지 독립 현재성 증거가 아니다.

soft prior는 거친 위치/0.15m 및 평균 회전/5°의 smooth L1 합에 0.005/0.05/0.5를 곱한다. 제안은 해당 거친 변수 범위를 projected Adam으로 지키되 가능한 비영 detail을 남긴다. 같은 source의 prior_free는 soft weight0으로 기하/색을 함께 학습한다. 이 비교는 local solver 기제 비교이며 강한 논문 전체 재현보다 우월함을 검증한 것이 아니다.

Adam 학습률은 coarse/detail/rotation0.001, scale0.003, opacity0.01, 색0.015다. 기하100회 warmup, 마지막까지0.1배로 줄어드는 공통 학습률, gradient norm clip10을 사용한다. 사전 설정은 변경하지 않았고 UAS를 B의 선택·보정·학습에 사용하지 않았다.

## 3. 기하와 외관의 분리 계약

RGB는 기존 gsplat C4 filtered splat, 기하는 독립 C8 plane-only opacity·transmittance로 계산한다. 같은 기하 weight의 camera-Z 기대값과 world-frame 법선 합을 사용하며 기하 mass가0이면 missing이다. RGB alpha와 geometry mass를 별도 파일로 저장한다. 기하 depth/normal/mass가 초기 관측·가림·손실·표면 추출에 일관되게 사용된다.

표면은 geometry mass≥0.5, finite positive depth의 stride2 pixel center를 world/local XYZ로 역투영한다. image ID/pixel UV/법선/source association을 함께 보존한다. 이는 mesh·단일 실제 표면·watertight 보장이 아니다. 중심 깊이 정렬과 projected tile 지원을 쓰므로 여러 면의 기대 깊이 혼합과 실제 hit visibility 문제는 남는다. source의 현재성, parameter 구조 제한, 추출 표면 보존, 현재 정확도를 각각 평가해야 한다.

현재 solver는 **출력 표면 경계의 hard constraint, 지붕/벽 교선의 위상 제약, 새로운 관측 구조의 adaptive Gaussian 증감**을 구현하지 않았다. 고정 표현 내 scale·opacity 변화와 사전 4분할 비교만 실행했다. 따라서 prior에 없던 배관이나 새 구조까지 생성·복원했다는 주장은 할 수 없다. 거친 변수의 범위 유지와 경계/표면 구조 유지 사이의 간극을 출력 지표로 드러내는 단계다.

최초 수정 native 표면은 1,377,299점이고 bbox는 [109.433,85.298,−49.667]~[158.567,132.569,−17.201]m로 기존 km tail이 사라졌다. 고정 P2 XY 밖14,359점과 최근접 seed association p90 1.078m/p99 4.048m/max9.566m는 별도로 남긴다. 기대 깊이의 혼합이 실제 source 점 사이에 표면을 만들 수 있다는 한계를 감추지 않는다.

## 4. 실행/검산 근거

- corrected native, representation, prior-shift의 세 run은 [b_run_corrected_docker.sh](../../../../scripts/phd/p2_ab_v2/b_run_corrected_docker.sh)와 `b_corrected_*_v1.json`으로 실행한다. 같은 이름이 이미 존재하면 중단한다.
- adapter 최종 CUDA 검산은 `PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-AUDIT-v3`의 31항목 PASS이다. normal은 nonidentity camera에서 world-frame 방향축으로 검산했다. FD 최대 절대차는0.000164이며 해당 매끄러운 5좌표에 대한 결과다.
- 원래 audit config·state·views·RGB baseline·source hash join은 `PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-AUDIT-BINDING-v1`에 보존한다. 보존 입력의 사후 결속이라는 시점도 명시했다.
- Docker의 `tests.phd.test_p2_ab_v2_reconstruction` 5개 검사는 부분 관측 affine detail·회전 제약 교집합·비영 가능한 변화·실제 state·4분할 부모 결속을 통과했다.

각 run에는 실행 CUDA SHA와 adapter/audit SHA를 대조한 receipt, 코드 snapshot, config, 입력 SHA, Docker image, Git head, torch/gsplat/CUDA 버전이 들어간다. 실제 Gaussian state는 `gaussians_initial.npz` / `gaussians_final.npz` 및 최종 `.pt`다. browser 표시용으로 학습 원점을 줄이지 않았다.

## 5. 수정 native 측정

같은 ALS G0의 11개 조건부 관측 mask를 사용한 수치다. 초기 RGB MAE는 뷰 평균0.191453, 픽셀 가중0.182965이며 분모는4,673,262픽셀이다.

| arm | 최종 MAE 뷰 평균 | 최종 MAE 픽셀 가중 | coarse RMS(m) | detail RMS(m) |
|---|---:|---:|---:|---:|
| geometry_fixed | 0.188480 | 0.192636 | 0 | 0 |
| color_fixed | 0.176869 | 0.175045 | 0.07608 | 0.08229 |
| prior_free | 0.176720 | 0.180252 | 0.07736 | 0.07294 |
| soft prior0.005 | 0.176936 | 0.180379 | 0.06120 | 0.07259 |
| soft prior0.05 | 0.177227 | 0.180512 | 0.03553 | 0.07316 |
| soft prior0.5 | 0.177680 | 0.181190 | 0.01226 | 0.07420 |
| structured_detail | 0.176893 | 0.180543 | 0.06573 | 0.07288 |

제안의 픽셀 가중 외관 오차 감소는 약0.00242로 작다. 색만 바꾼 geometry_fixed는 뷰 평균은 좋아져도 픽셀 가중 MAE는 악화했다. 관측 면적이 다른 뷰를 어떻게 합산하는지에 따라 결론이 달라질 수 있어 둘 다 보고한다. 색을 고정하고 기하만 바꾼 arm도 RGB 오차를 줄이므로 RGB 개선을 곧 텍스처 또는 올바른 세부 형상 복원으로 해석할 수 없다.

저장 8bit RGB의 같은 조건부 mask에서 SSIM11 뷰 평균은 제안0.302848→0.367584, 기하 고정 최종0.338542, 색 고정 최종0.379354였다. 실제 수정 결과의 542번 target/final도 직접 확인했다. 지붕·벽면의 색 번짐, 늘어진 부분, 창/경계의 흐림이 크게 남아 **고품질 텍스처 복원 완료로 볼 수 없다.** P2 source 밖 검은 배경은 복원 대상 범위와 구분해야 하지만, source가 보이는 영역의 흐림도 분명하다. 고정 SH0·밀도·위상, prior 오류, 가림/혼합과 학습의 한계가 함께 남는다.

제안은 거친 최대 이동0.15000004m와 비영 detail을 유지했지만, 유지된 초기 ray의 기하 depth 변화는 **뷰 평균의 평균1.05455m**였다. 초기 지지 중8,979픽셀이 사라지고290,371픽셀이 추가됐다. `coarse parameter 범위 준수`와 `출력 표면 구조 보존`은 동일하지 않다. soft prior를 강하게 하면 coarse RMS는 작아지지만 scale/opacity/detail과 ray 혼합을 통한 출력 변화는 남는다.

MVS image_only는 자체 G0와 자체 mask에서 뷰 평균 MAE0.184822→0.153058, 픽셀 가중0.139627→0.125583이었다. 초기 source와 Gaussian 수가 다른 기준이며 위 ALS 표와 직접 순위를 매기지 않는다. source간 비교는 C의 고정 공통 ray에서 해야 한다.

4분할 ALS의 동일 초기 mask에서 뷰 평균 MAE는 기하 고정0.192310→0.187470, 제안0.192310→0.176282였다. 제안 detail RMS는0.057327m, 1mm 이상 detail 변화는117,813개다. 표현 변화로 초기 지지와 색도 바뀌므로 native 값과 직접 성능 순위를 매기지 않는다. 실제 세부의 정확도는 Gaussian 수나 DOF 변화만으로 판정하지 않는다.

수정 최종 native 상태의 별도 gradient 감사는 optimizer0회로 296↔297 뷰의 RGB/normal/MVC 항을 각각 미분했다. 세 항 모두 structure/detail/rotation/scale/opacity에 유한 비영 gradient를 전달했다. detail gradient norm은 각각0.010563/0.019424/0.012215이고 MVC 유효 표본은28,540개였다. 이는 동작 검산이며 현재 세부 복원 성공 증거가 아니다.

ALS Z+1m stress의 뷰 평균 MAE는 초기0.187170에서 free0.171506, 제안0.171712로 줄었다. 픽셀 가중은 초기0.184018에서 각각0.179457/0.179822이다. 잘못 이동한 source에서도 사진 손실이 줄어드는 사례이므로 이를 정합 오류 해결·현재성 회복으로 해석하지 않는다. 상대 prior shift만 바꾼 조건이며 camera/scene 공유오류를 검증한 것이 아니다.

제안의 마지막 256회 평균 photo는 직전0.195701에서0.193629로 계속 줄었다. 예고된 평가 추세에서도 555번 MAE가 step1의0.185552에서 마지막0.193500으로 나빠진 반면 다른 뷰는 좋아졌다. 이 유한 예산으로 수렴이나 모든 양호 영역의 열화 통제를 주장하지 않는다. native와 4분할 제안의 MVC는 각각512회 호출,497회 비영이며 유효 표본 합은4,172,555 /3,846,586이다. 반복 표본 수이고 독립 관측 수가 아니다.

## 6. 완료 상태와 다음 판단 범위

`CORRECTED-VERIFICATION-v1/verification.json`은 12개 arm 전체 PASS이며 native ALS7개, 4분할2개, shift2개의 초기 상태 array hash가 각각 동일함을 확인했다. 모든 arm은 실제 optimizer2,048회를 실행했다. raw SH0와 export RGB 일치, 유한 state와 기하 output, 기하 고정 arm의 실제 변수·깊이·mass exact 보존, 부족 관측 detail0, CUDA/audit/source snapshot 연결을 확인했다. 이 PASS는 구현·산출물 계약의 통과이며 과학적 우월성의 통과가 아니다.

기하 유지·현재 외관·현재 세부는 별개로 남는다. 이번 결과는 비영 detail을 가진 조건부 재구성 기제와 그 한계를 실제로 측정했다. 출력 표면의 구조 제한, 실제 현재 형상/세부 정확도, prior의 현재 적격성과 좋은 영역 열화 통제까지 달성했다는 결론은 내리지 않는다. 그 판단은 C의 고정 reference/공통 ray/국소 형상 진단 및 A의 성분별 현재 사용 판단과 함께 해야 한다. 참조 결과를 본 추가 튜닝은 실행하지 않았다.

| 새 run | 완료 결과 수 | run 전체 시간(s) |
|---|---:|---:|
| `PHD-P2-AB-V2-B-CORRECTED-NATIVE-v1` | 8 | 641.10 |
| `PHD-P2-AB-V2-B-CORRECTED-REPRESENTATION-v1` | 2 | 166.50 |
| `PHD-P2-AB-V2-B-CORRECTED-PRIOR-SHIFT-v1` | 2 | 175.51 |

검산은 `PHD-P2-AB-V2-B-CORRECTED-VERIFICATION-v1`, loss 연결성 감사는 `PHD-P2-AB-V2-B-CORRECTED-GRADIENT-AUDIT-v1`이다. [b_corrected_followups_docker.sh](../../../../scripts/phd/p2_ab_v2/b_corrected_followups_docker.sh)가 native 이후 순서를 기록한다. 기존 v1/v2 결과와 역사 overlay는 보존했고 source snapshot으로 과거 실행 코드도 남아 있다.

최종 B 소유 코드·config·문서·검사의 SHA256과 snapshot, 위 실행/검산 receipt의 SHA256은 `PHD-P2-AB-V2-B-CORRECTED-RETURN-v1/manifest.json`에 결속한다. [b_freeze_corrected_return_docker.sh](../../../../scripts/phd/p2_ab_v2/b_freeze_corrected_return_docker.sh)가 새 반환 디렉터리만 작성하며 기존 run에는 쓰지 않는다.
