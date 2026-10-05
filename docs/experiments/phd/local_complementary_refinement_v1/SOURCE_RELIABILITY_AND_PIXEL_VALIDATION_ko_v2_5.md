# Source 신뢰 근거와 픽셀 가중 검증 v2.5

- 작성일: 2026-09-11
- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- scientific_verdict: null
- 문헌 원리·후속 설계 검토이며 main_v2의 실행 명세를 변경하지 않는다.
- 논문 결과와 현재 P1/P2/P3의 방법 성능은 별개다. 새 source 선택기의 성능은 아직 검증하지 않았다.

## 두 depth의 차이 외에 사용할 수 있는 근거

불일치는 두 source를 더 조사할 필요를 알려주지만 어느 쪽이 맞는지 알려주지는 않는다. GT 없이 사용할 수 있는 추가 근거는 각 후보 표면이 현재 관측을 얼마나 설명하는가다. Source의 이름이나 현재 GS와의 가까움만으로 정확성을 부여하지 않는다.

예를 들어 reference 사진의 작은 패치에 대해 prior depth로 만든 표면 후보와 DA3 depth로 만든 표면 후보를 각각 구성한다. 알려진 카메라로 후보를 이웃 사진에 옮겼을 때 무늬·경계가 어느 후보에서 더 잘 맞는지 평가한다. 이 과정은 고정된 원사진 사이의 비교이며, GS가 색·불투명도를 조정한 뒤 얻는 RGB loss와는 다른 검사다. 가능한 경우 재투영 깊이의 일관성·시차·시야 내 지원도 함께 확인한다.

이 검사는 후보의 절대적인 적합도, 두 후보의 점수 차이, 판단할 수 있는 관측량을 구분해야 한다. 둘 중 덜 나쁘다는 이유만으로 신뢰해서는 안 된다. 가림·표면 경계·반복 무늬·저텍스처·작은 baseline 때문에 두 후보를 구분하지 못할 수 있다. 두 후보가 모두 틀릴 수도 있다. 넓은 MVS 결손에서 이 검사도 실패할 수 있으므로 결손을 해결한다고 보장하지 않는다.

## 원문과 공식 구현에서 확인한 선행연구

### Geometric Change Detection in Urban Environments using Images — TPAMI 2015

Taneja, Ballan, Pollefeys는 기존 도시 기하와 현재 파노라마 영상의 재투영 일관성으로 기하 변화를 검사한다. 모델의 작은 기하 오차와 pose 정합·넓은 baseline의 영상 비교 문제를 다룬다. 기존 기하의 현재 영상 설명력을 검사한다는 점에서 이번 source 판단의 직접적인 선행 원리다.

출력은 변화 검출이며 ALS/DA3의 가중치나 GS 업데이트가 아니다. 지상 도시 영상 방법을 항공 지붕·두 후보 비교에 옮기려면 가시성·표면·관측 조건을 별도 검증해야 한다. 저자는 강한 반사와 segmentation 오류의 오탐도 보고한다. 이 연구를 금속 지붕의 source 선택을 해결한 결과로 확대하지 않는다.

- [저자 원문: §§3–4](https://lucaballan.altervista.org/pdfs/PAMI15.pdf)
- [저자 출판 목록](https://people.inf.ethz.ch/marc.pollefeys/publications.html)

### Pixelwise View Selection for Unstructured Multi-View Stereo — ECCV 2016

Schönberger et al.은 photometric/geometric 근거로 픽셀별 이웃 시선을 선택하고 깊이·법선을 추정하며, 여러 시점의 기하 일관성을 refinement와 fusion에 사용한다. 공식 포스터의 비용식은 photometric NCC와 제한된 geometric cost를 결합하고, 삼각측량 각도·해상도·입사각·가림 관련 근거를 명시한다.

이 연구는 후보 깊이를 원사진으로 검증하는 원리의 직접적인 근거다. 이를 prior/DA3 두 후보 평가에 사용하는 것은 구성요소 도입이며 그 자체를 새 방법으로 주장하지 않는다.

- [저자 소속 기관의 논문 소개](https://www.microsoft.com/en-us/research/publication/pixelwise-view-selection-for-unstructured-multi-view-stereo-2/)
- [공식 포스터: 비용식과 관측 기하](https://www.microsoft.com/en-us/research/uploads/prod/2019/09/P-2A-41.pdf)

### NeuRIS — ECCV 2022

현재 복원 depth·normal이 만드는 국소 평면을 이웃 영상으로 warp하여 patch NCC를 검사하고, 예측 normal prior의 사용을 조절한다. 이는 두 depth target 자체를 각각 평가하는 방법은 아니다. 초기 prior 감독 뒤 현재 재구성의 관측 적합성을 통해 감독을 판단한다.

2026-09-11에 확인한 공식 코드에는 현재/이전 NCC cost와 복원 법선↔prior 법선의 각도 조건이 함께 있다. 이웃 지원 부족과 패치 경계 밖을 처리하며, NCC 분모가0인 상수 패치는 NCC1로 처리해 prior 유지 쪽으로 둔다. 따라서 높은 NCC를 보정된 정확도 확률 또는 가시성 인증으로 읽으면 안 된다. 이 무텍스처 처리 역시 현재 두 높이 후보를 구분하는 증거가 아니다.

- [논문 v2 §3.2](https://arxiv.org/html/2206.13597v2)
- [공식 gate 구현](https://github.com/jiepengwang/NeuRIS/blob/main/exp_runner.py#L295-L350)
- [공식 patch NCC 구현](https://github.com/jiepengwang/NeuRIS/blob/main/models/patch_match_cuda.py#L109-L149)

### AGS-Mesh — 3DV 2025

DNC는 센서 depth에서 얻은 법선과 영상 예측 법선의 방향 차이로 depth 감독을 거른다. ANR는 현재 GS 기하와 예측 법선의 방향 차이로 normal 감독을 완화한다. 부정확한 기하 감독을 모두 동일하게 사용하지 않는 GS 선행 사례다.

평행한 두 평면은 높이가 달라도 같은 법선을 가질 수 있다. 따라서 방향 비교만으로 P1의 높이 차이를 식별할 수 없다는 것은 이 식에 대한 우리의 기하학적 해석이다. 해당 논문이 P1/P2에서 실패했다고 관측한 것은 아니다.

- [논문 v2 §4.1–4.2](https://arxiv.org/html/2411.19271v2)
- [공식 구현](https://github.com/XuqianRen/AGS_Mesh)

## 현재 입력에 적용할 첫 후보 원리

우선 prior와 image 후보에 동일한 현재 영상·이웃 선택·패치 규약을 제공하여 관측 근거를 비교한다. 후보별 유효 관측 집합이 달라지면 그 차이와 공통 지지에서의 비교를 별도로 기록한다. 한 후보에서 보이지 않는 영역을 편리하게 제외해 점수를 높이지 않는다. Pose와 ray 규약을 맞추고, 같은 가시 표면인지 확인하지 못하면 미지원으로 남긴다.

| 관측으로 판단 가능한 상황 | 후보 정책 |
|---|---|
| image 후보가 충분한 지지와 뚜렷한 우세를 가짐 | image 감독 유지/우선, prior 완화 |
| prior 후보가 충분한 지지와 뚜렷한 우세를 가짐 | prior 유지, 해당 image 감독 완화 |
| 두 후보가 같은 표면을 지지 | 공통 표면 유지; source 선택과 총강도 결정 분리 |
| 둘 다 불충분하거나 구분 불가 | 사용 가능한 prior를 기본값으로 유지; 현재 정확성 미확인으로 기록 |

추정 score는 정답 확률이 아니다. 현재 모델이 prior 쪽에 있으므로 prior가 맞다는 자기확증을 피하기 위해 두 후보를 가능한 한 대칭적으로 시험한다. 다중뷰 depth 일치만 사용하면 같은 모델의 공통 편향이 통과할 수 있으므로 원사진 근거도 함께 본다.

반영식의 설명용 예로, 낮을수록 좋은 두 관측 비용을 EP/EI라 하면 판단 가능한 곳에서 `q=sigmoid((EP-EI)/T)`를 사용할 수 있다. Image 후보의 비용이 작으면 q가 커진다. 이 q는 확률로 보정된 정확도가 아니며, T·비용 정의·절대 적합도·점수 차이·관측 지원 문턱은 아직 실행용으로 정하지 않았다. 두 비용이 모두 나쁘거나 관측이 부족하면 sigmoid 결과를 사용하지 않고 prior 기본 정책으로 돌아간다. 유효한 prior도 없으면 이 기본 정책으로 표면을 보장할 수 없다. 이 식은 후보 높이 차이 자체에 sigmoid를 적용하는 것과 판단 근거가 다르다.

DA3 confidence는 이미 존재하는 저비용 비교 신호이며 기존 GeoGS의 optional confidence도 강한 기준 후보다. 현재 main_v2에서는 비활성이다. 이를 켜는 것만으로 prior의 정확성/현재성을 판단하게 되는 것은 아니다. 신호 비교에서는 동일한 반영식·입력·예산을 사용하고, 반영식 비교에서는 동일한 신호를 제공한다.

GT 없이 생성한 신호·규칙을 먼저 고정하고 나서, 별도 평가에서 실제로 더 정확한 source에 높은 가중치를 주었는지 확인한다. 그 평가 결과를 학습 가중치·깊이 보정·문턱 선택으로 되돌리지 않는다. 기존 A–F는 사후 개발 사례이고 새로운 독립 검증을 대신하지 않는다.

## 픽셀별 가중이 잘 적용됐는지 확인하는 단계

1. **입력 위치:** 원사진·카메라 이름·shape·픽셀 중심·DP/DI·valid mask의 연결과 hash를 확인한다. 결손과 낮은 신뢰를 구분한다.
2. **공간 배율:** 사진 위에 delta, a, bP, bI를 표시한다. 그 위치에서 식대로 가중됐는지 본다. 기존 집계 trace의 평균만으로 공간 배치를 확인할 수 없다.
3. **최종 계수:** `kP=lambdaP*bP/NP`, `kI=lambdaI*bI/NI`, `kI/(kP+kI)`, `kP+kI`를 별도로 저장한다. 기여0과 결손을 구분하고 분모·실제 controller 계수·정밀도를 기록한다.
4. **prediction gradient:** `gP=kP*sign(pred-DP)`, `gI=kI*sign(pred-DI)`의 독립 계산과 실제 함수의 autograd를 source별/합계별 전체 픽셀에서 비교한다. L1 잔차0의 미분 선택은 sign0이다. 결손 잔차는 계산하지 않는다. 소수 픽셀의 finite difference 또는 가중치 위치 교환은 추가 독립 검사다.
5. **Gaussian 전달:** 동일 checkpoint의 모델·Adam·RNG·카메라·lambda·보호를 복제한 한 단계 분기에서 가중식만 바꾸고 parameter gradient, 실제 update, 고정 시점의 렌더 깊이 변화를 기록한다. prediction gradient 검증은 이 단계를 대신하지 않는다.
6. **선택의 타당성:** 고정 신호가 정확한 source를 더 지지했는지 별도 GT 평가로 검사하고, 같은 참조점의 수정·손상을 함께 본다. 코드가 식대로 동작하는지와 식이 좋은 선택을 하는지는 다른 검사다.

기존 CPU 감사는 관련16개 테스트와 실제 동결 결합식 AST의 합성 픽셀 검사를 통과했다. 실제 GPU probe는 complete Anchor 복원·첫 단계·scalar 기록을 확인했다. 기존 기록만으로 실제 장면 전체 픽셀 지도 또는 Gaussian별 수정 방향까지 검증했다고 말할 수 없다. 근거는 [v2.3 감사](DESIGN_IMPLEMENTATION_AUDIT_ko_v2_3.md)다.

## 이번 추가 픽셀 감사의 범위

P1 A와 P2 C에서 사용한 사진 두 장의 전체 봉인 입력을 대상으로 CPU map/gradient 감사를 별도 경로에서 완료했다. 사진 선택은 기존 개발 사례를 재사용하며 GT 배열은 계산에 마운트하지 않았다. lambdaI=.05, lambdaP=.005/.0005/0은 명시적인 계수 시나리오이며 학습 전체의 controller 궤적을 재현하는 것은 아니다. Prediction은 명시된 합성 배열이며 실제 Gaussian/Anchor 예측이 아니다. 실제 입력·mask에서 식과 공간 배치의 전달을 확인하는 기술 검사다.

### 완료 결과와 재현 경로

- 기술 상태: **PASS**, `scientific_verdict: null`.
- 출력: `JBGS_ARTIFACT_ROOT/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1/main_v2/pixel_weight_audit_v2_5/attempt_20260911T083708_267617Z`.
- 실행기: `scripts/phd/local_complementary_refinement_v1/run_pixel_weight_audit_v2_5.sh`; 설정: `configs/phd/local_complementary_refinement_v1/pixel_weight_audit_v2_5.json`. 실행기에서 GPU 없는 Docker CPU2/RAM4GiB 환경을 구성한다.
- 작성 시 저장소 HEAD: `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`. 이번 미커밋 감사 코드·설정·실행기와 실제 실행에 사용된 동결 helper는 출력 `snapshots/`에 별도 보존했다. HEAD만으로 이번 코드를 식별하지 않는다.
- 결과 `receipt.json` SHA256: `a1e501f06dd0400f918cc85b8a47412352b808cf2539da89597aa1fa372ba9df`.

| 검사항목 | P1 | P2 |
|---|---:|---:|
| 카메라 | DJI_20241217084553_0100_D.JPG | DJI_20241217084505_0076_D.JPG |
| 전체 픽셀 / image 유효 분모 | 1,418,200 | 1,418,200 |
| prior 유효 분모 | 815,018 | 585,385 |
| 독립 NumPy 대비 실제 helper의 bP/bI 최대 오차 | 0 | 0 |
| lambdaP=0에서 a=0이며 depth 총강도가 0인 픽셀 | 64,935 | 75,687 |

두 카메라 × prior 계수3개 × 합성 prediction3개(두 target 중간/둘보다 깊게/둘보다 얕게) × dtype2개 = **36개 전체 raster loss·gradient 검사 모두 통과**했다. Source별 및 합산 signed depth gradient를 독립 계산과 비교했다. 합산 gradient 최대 절대 오차는 float32 `7.105427357601002e-15`, float64 `1.3234889800848443e-23`이고, float32 계수 적용 총 loss 최대 절대 오차는 `2.9802322387695312e-08`이다. 입력16파일의 전후 hash와 출력26파일의 hash를 검증했다.

`P1_pixel_weight_maps.png`, `P2_pixel_weight_maps.png`와 `verification_table.png`를 시각 확인했다. 지도는 원사진, source별 배율, 최종 image 비중, 최종 총강도, 합성 prediction의 depth gradient를 구분한다. Gradient는 경사하강 이동량이 아니며 Gaussian 변위도 아니다. 총강도0인 곳의 비중은 정의되지 않아 회색으로 표시한다. Source 결손과 배율0은 NPZ의 별도 mask로 보존한다.

이번 PASS는 검사한 실제 target·mask에서 동결 가중식을 정확히 계산하고 prediction gradient에 전달했다는 근거다. 두 사진은 전체 학습 시점의 대표 표본이 아니며, 입력의 물리적 정합 정확성이나 source 선택의 정확성까지 증명하지 않는다. 새 학습 또는 새 source 선택기 성능을 이 감사로 주장하지 않는다. 감독 선택기의 관측 점수 계산·MVS 교체·CUDA Gaussian 업데이트 검사는 실행하지 않았다.
