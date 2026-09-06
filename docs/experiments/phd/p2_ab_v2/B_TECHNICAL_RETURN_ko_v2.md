# B v2 Technical Return

**수정 공지 — 이 문서 아래의 최초 v2 수치 결과는 `INVALID_FOR_METHOD_CONCLUSION`이다.** `B2-008`에서 screen-filter RGB opacity로 유효하지 않은 무한 평면 교점 깊이를 합성하고 그 미분을 일부 누락한 구현 오류를 확인했다. 그 깊이가 관측 마스크·기하 손실·표면 추출에 쓰였으므로 최초 NATIVE/REPRESENTATION/PRIOR-SHIFT 및 FIXED 수정 run으로 연구 성패를 판단할 수 없다. 원래 수치와 파일은 이력으로 보존한다. 수정 원리·검산은 [B_GEOMETRY_ADAPTER_CORRECTION_ko_v2.md](B_GEOMETRY_ADAPTER_CORRECTION_ko_v2.md), 재실행 결과는 별도 반환 문서로 연결한다.

`scientific_verdict: null`. 이 문서는 개발 측정과 실행 범위를 설명한다. 방법 우월성·현재 사용 적격성·독립 확증 결과를 선언하지 않는다.

## 1. 이번에 실제로 달라진 시험

v1의 제안 arm은 대부분 기하 고정이었고 세부 복원 가설을 시험하지 못했다. v2는 같은 연속 ALS 초기 Gaussian에서 현재 색, 3차원 중심의 세부 잔차, Gaussian 방향·크기·opacity를 실제로 학습한다. 구조 제한의 기능과 현재 기하/외관/세부 정확도는 다른 평가이다.

| 비교 | 공통점 | 바뀌는 요소 |
|---|---|---|
| ALS G0의 geometry_fixed / color_fixed / prior_free / soft_prior_weak / soft_prior / soft_prior_strong / structured_detail | 같은 초기 Gaussian, 관측 마스크, 카메라, tile 순서, 2,048회 예산 | 색/기하 자유도, 추가 prior 손실, 구조 제한 |
| MVS G0의 image_only | 같은 영상·렌더러·기하 손실·반복 수 | 초기 source와 밀도도 달라지는 총효과 기준 |
| ALS 4분할 geometry_fixed / structured_detail | 각 원점의 접선 footprint 안에서 4개 표현 표본, 같은 관측 | 표현 해상도 및 해당 표현에서 최적화 효과 |
| ALS Z+1m의 prior_free / structured_detail | 동일하게 어긋난 초기 source, 같은 관측 규칙 | 틀린 구조를 유지하는 제약의 실패 가능성 |

기존 main 결과 metadata의 `four prior arms` 문자열은 초기 초안 설명이 남은 것이다. 실제 native 비교는 위의 **7개 ALS arm**이다. 기존 결과는 보존하고 이 표로 정정한다. shift 조건은 상대 prior 정합 오류이며 시간 변화나 camera/scene 공유오류를 검증한 조건이 아니다.

## 2. 초기 Gaussian과 실제 자유도

native ALS 45,986점을 전부 유지했다. 원본 patch ID·tile row·unit ID를 보존하며 4m 공간 셀로 국소 그룹 1,561개를 만들었다. 법선은 native source에서 가져와 정규화하고 동일 planar 면의 +Z 방향 표현으로 맞췄다. 초기 접선 scale은 같은 native patch의 최근접 3점 거리 중앙값 ×0.65, [0.04,0.6]m 범위이다. 실제 ALS scale 중앙값은 0.181498m, 최솟값은 0.067651m이다. 세 번째 scale은 1e-6m인 planar 2D Gaussian이며 gsplat을 사용한다.

초기 opacity는 0.85이다. 초기 RGB는 G0 깊이·alpha와 조건부 전경 마스크를 거친 학습 영상 투영 색의 중앙값이고, 색 관측이 없으면 0.5로 둔다. SH0만 사용한다. 초기 source 사용을 A가 승인했다는 뜻은 아니다.

위치 변화는 그룹의 상수/접평면 선형 성분과 그 성분에 직교하는 **3차원** detail 잔차로 나눈다. 좌표계를 고정하기 위한 분해이며 관측 없이 구조를 안다는 증명은 아니다. 관측 수와 design rank를 `als_detail_dof.json`에 기록했다. 최종 native 조건에서 3개 이상 조건부 source 가시 뷰를 가진 점은 30,197개, 가능한 위치 detail DOF 합은 82,065이다. 부족한 점은 원래 분모에 남고 detail/rotation을 0으로 유지한다. 거친 source 구조가 이 점을 함께 움직이는 것은 조건부 구조 추론이다.

제안과 color_fixed는 거친 위치 변화의 그룹 최대값을 0.15m, 관측점의 평균 회전 벡터를 5°로 제한한다. 다른 기하 학습 arm의 거친 이동 domain은 1.5m이다. 모든 기하 학습 arm의 detail domain은 초기 scale ×3을 [0.25,1.5]m로 제한한 값, 개별 회전 domain은 35°, scale 비율은 [0.4,2], opacity는 [0.05,0.995]이다. 이 수치는 **사전 선언한 solver 설정**이며 A의 ε/U나 정확도 보장이 아니다. 매 step의 projected Adam에서 가능한 비영 변형을 유지한다.

거친 moment 제한을 만족하더라도 Gaussian의 크기·opacity·국소 회전 때문에 렌더 깊이와 경계가 변할 수 있다. 따라서 parameter 제한과 실제 추출 표면 보존을 별도로 측정한다.

## 3. 관측과 손실

5280×3956 원본 영상에서 FULL_OPENCV 왜곡을 제거한 P2 crop을 사용한다. B에 쓰는 44개 뷰(33 train/11 eval) 중 31개는 native crop 해상도 그대로, 13개는 최대 변을 1536px로 명시 축소했다. 가장 작은 축척은 약 0.397이다. 학습은 그 영상의 최대 768px tile이다. `views.json`의 원래 크기·축척·K가 정확한 해상도 계약이다. 이 영상들은 과거 개발에 노출된 뷰이다.

fullscene current COLMAP depth는 **전경 가림 제외**에만 쓴다. 1024×741 depth의 별도 K와 원본 crop ray를 대응시키고, 2×2 depth가 전부 알려졌으며 가장 먼 depth+1m도 G0 앞인 경우에만 뒤쪽 source 관측에서 제외한다. depth 미상은 별도 상태로 남긴다. 원점 투영으로 검산한 fullscene MVS 감사에서 435/400의 큰 차이는 주로 P2 밖 전경임을 확인했지만 모든 깊이 경계를 보증한 것은 아니다. 이 감사의 point 분모와 B renderer pixel 분모도 서로 다르다.

| native ALS ray 분모 | train 33뷰 | eval 11뷰 |
|---|---:|---:|
| 원래 G0 alpha≥0.5 지지 | 16,580,779 | 5,509,940 |
| 전경 제외 | 2,127,407 | 835,167 |
| 남은 조건부 관측 | 14,453,372 | 4,674,773 |
| 2×2 context depth 미상인 원래 지지 | 2,471,359 | 2,005,049 |

같은 필터를 초기 색·관측수·photo/coverage·multiview 양쪽에 적용했다. 미상 부분의 RGB는 조건부 관측이지 가시성 확증이 아니다. 원래 G0 지지와 전경/미상/관측 mask를 모두 저장해 제외로 인한 분모 변화를 숨기지 않는다.

공통 외관 손실은 0.8 RGB L1 +0.2 (1−masked SSIM11)이다. 기하 학습에는 coverage(alpha 목표 0.7) 가중치 0.1, 렌더 법선과 ray–surfel 깊이 유래 법선의 일관성 0.05, 학습 뷰 사이의 재투영 일관성 0.1을 더한다. multiview는 4 step마다 계산하며, source camera-Z와 reference 렌더 깊이의 smooth L1(β=0.1m), 법선 항 ×0.1, 현재 영상 warp RGB L1 ×0.1을 사용한다. 0.5m 일관성 inlier gate가 있으며 이것도 학습 목적함수의 조건이다. 같은 학습 뷰로 만든 일관성을 독립 증거로 부르지 않는다.

soft prior는 거친 위치를 0.15m, 평균 회전을 5°로 정규화한 smooth L1 손실을 0.005/0.05/0.5로 비교한다. 제안은 해당 거친 성분에 유한 범위를 직접 적용한다. 이 비교는 새 local solver의 구성 요소 비교이며 강한 기존 논문 전체 재현이 아니다. planar 표현과 normal/depth 정규화의 출처는 [2DGS](https://arxiv.org/abs/2403.17888), depth/normal prior 비교의 문헌 맥락은 [DN-Splatter](https://openaccess.thecvf.com/content/WACV2025/papers/Turkulainen_DN-Splatter_Depth_and_Normal_Priors_for_Gaussian_Splatting_and_Meshing_WACV_2025_paper.pdf)이다.

Adam 학습률은 색 0.015, 거친 위치/detail/회전 각각 0.001, scale 0.003, opacity 0.01이다. 기하 학습률은 처음 100회 증가하고 전체 학습률은 끝에 초기값의 0.1배로 감소한다. 2,048회 손실과 gradient를 매회 저장하고 256회마다 평가 뷰 추세를 저장했다. gradient norm clip은 10이다. 평가 추세를 보았다고 수렴 또는 성능 확증을 주장하지 않는다.

## 4. 결과 계약과 검산

각 arm은 실제 전체 `gaussians_initial.npz` / `gaussians_final.npz`를 내보낸다. `xyz/scales/quats/opacity/rgb/group`와 source ID를 포함하고 display decimation은 없다. 새 corrected/density/shift 실행은 raw `sh0`도 함께 저장한다. native main의 geometry-active arm raw SH0는 `.pt`에 남아 있으며 RGB domain 제한이 적용되어 export RGB와 일치한다.

NATIVE-v1의 geometry_fixed는 색 범위 제한 누락으로 decoded RGB가 [−0.0452,2.3352]였다. 해당 결과와 실패 증거를 보존하고 최종 비교/뷰어에서는 제외한다. **NATIVE-FIXED-v2의 geometry_fixed**가 동일 [0,1] 색 범위로 수정한 공정 기준이다. 자세한 오류와 조치는 [B_ISSUES_ko_v2.md](B_ISSUES_ko_v2.md)에 남겼다.

표면은 감사된 gsplat overlay의 alpha 가중 ray–surfel intersection 깊이를 alpha로 나눈 expected surface에서 읽는다. camera-Z 중심 평균으로 경사 면을 대체하지 않는다. alpha≥0.5의 고정 stride 2 ray를 역투영하고 image ID·pixel UV·normal·source association을 보존한다. `initial_extracted_surface.npz` / `extracted_surface.npz`는 mesh나 watertight 보장이 아니며 겹층의 혼합이나 가림 뒤 source 표면이 포함될 수 있다.

저장 metric은 RGB MAE/PSNR(원래 고정 G0 지지·조건부 관측·전체 valid crop·유지된 지지), alpha 지지 소실/증가, 렌더 깊이·법선 변화, alpha 경계 대칭 거리이다. 최종 B verification은 저장 8bit RGB에서 조건부 관측 mask의 SSIM11도 별도로 계산한다. 이 SSIM은 원래 float RGB metric과 양자화 수준이 다르다. 다른 G0의 mask는 같지 않으므로 source간 순위는 C의 공통 ray 평가로 확인해야 한다.

UAS를 B 입력/파라미터 선택에 사용하지 않았다. 현재 형상과 세부의 개선 여부는 C의 고정 reference 분모와 별도 국소 형상 진단으로 확인한다. parameter 변화·잘 그려진 RGB·source 보존만으로 현재 geometry/detail 성공을 선언하지 않는다.

## 5. B 측정 결과와 현재 한계

다음은 같은 ALS G0 및 같은 조건부 관측 mask의 11개 평가 뷰 평균이다. 모든 native prior arm의 초기 MAE는 0.191326, 저장 RGB SSIM은 0.30080이다. 외관 개선과 현재 기하 개선을 구분한다.

| native arm | 최종 MAE | 최종 SSIM | 거친 위치 RMS(m) | detail RMS(m) |
|---|---:|---:|---:|---:|
| geometry_fixed (수정 v2) | 0.18798 | 0.33509 | 0 | 0 |
| color_fixed | 0.17684 | 0.37882 | 0.07590 | 0.08062 |
| prior_free | 0.17619 | 0.36837 | 0.07670 | 0.07195 |
| soft prior 0.005 | 0.17653 | 0.36755 | 0.06105 | 0.07179 |
| soft prior 0.05 | 0.17700 | 0.36708 | 0.03621 | 0.07270 |
| soft prior 0.5 | 0.17738 | 0.36604 | 0.01224 | 0.07300 |
| structured_detail | 0.17647 | 0.36724 | 0.06671 | 0.07206 |

제안의 조건부 관측 MAE를 **픽셀 수로 가중**하면 0.182500→0.180451이다. 뷰마다 남은 픽셀 수가 크게 달라 단순 뷰 평균의 변화가 더 크게 보인다. 가림을 제외하기 전 고정 G0 지지의 픽셀 가중 MAE는 0.191348→0.189141이다. 이 수치만으로 큰 외관 이득이나 고품질 텍스처 복원 완료를 주장하지 않는다. 542번 등 실제 렌더에는 벽·지붕 경계의 흐림과 늘어짐이 남았다. SH0의 시점 독립적인 상수색, 고정 topology와 유한 source 밀도, 최적화/기하 손실의 한계가 있다.

제안은 coarse 최대 0.15m 제한을 지켰지만, 유지된 alpha ray의 초기→최종 intersection depth 변화는 **뷰 평균의 평균 1.58329m**였다. 원래 지지에서 7,764픽셀이 사라지고 291,719픽셀이 추가됐다. scale/opacity/회전과 ray 혼합이 출력 표면을 바꾸므로, **거친 parameter 제한은 추출 표면 구조 보존을 달성한 증거가 아니다.** 이 문제는 surface 기반 제한과 가림/겹층 처리의 추가 설계 과제로 남는다.

표현 4분할은 183,944개 Gaussian으로 구성했고, 초기→최종 조건부 MAE는 기하 고정 0.19201→0.18752, 제안 0.19201→0.17595였다. 제안의 detail RMS는 0.05959m이고 1mm 이상 움직인 detail 점은 115,736개였다. 표현을 조밀하게 만든 것과 실제 세부 형상이 맞아진 것은 다른 주장이다. 초기 ray 지지도 달라지므로 native 표의 MAE와 직접 순위를 매기지 않는다.

MVS image-only는 266,361개 초기 Gaussian이고 자체 mask MAE 0.18485→0.15238이었다. 초기 입력/밀도가 다르며 직접 source 우열은 C의 공통 분모 평가에서 다룬다. Z+1m stress에서는 자체 mask MAE가 prior_free 0.18667→0.17073, 제안 0.18667→0.17077이었다. 잘못 움직인 prior에서도 RGB 손실이 줄 수 있으므로 낮은 RGB 오차가 올바른 현재 구조를 뜻하지 않는다.

학습 추세는 제안의 마지막 256회 평균 photo가 직전 256회 0.19580에서 0.19397로 줄었고, 고정 일부 평가 뷰 평균도 1,792회 0.190390에서 2,048회 0.189972로 변했다. 학습은 계속 변하고 있어 수렴을 보증하지 않는다. 최종 reference 결과를 보고 추가 튜닝하지 않았다.

`VERIFICATION-v2`는 12개 결과의 finite 실제 상태·raw SH0/export RGB 일치·고정 기하/색·부족 관측의 detail 0·동일 초기화 3개 그룹에 PASS이다. MVC는 native/4분할 제안에서 각각 512회 호출되고 497회 비영 손실이었다(유효 표본 합 각각 4,075,084 / 3,842,382; 반복 표본 수이며 독립 관측 수가 아님). console의 64회 간격과 MVC 실행 위상이 달라 일부 console만 보면 0으로 보이지만 `training.jsonl`은 모든 회차를 보존한다.

`GRADIENT-AUDIT-v1`은 최종 native 제안 상태의 296↔297 뷰에서 optimizer **0회**로 RGB/normal/MVC 각 항을 따로 미분했다. 세 항 모두 structure/detail/rotation/scale/opacity의 유한 비영 gradient를 확인했다. MVC의 유효 픽셀은 28,537개이고 detail gradient norm은 0.07014(가중 전)였다. 이는 구현의 연결성 검산이며 세부 복원의 정확성 증거는 아니다.

## 6. 재실행과 보존

- main: `PHD-P2-AB-V2-B-NATIVE-v1` (geometry_fixed 원 arm은 제외)
- 수정 기준: `PHD-P2-AB-V2-B-NATIVE-FIXED-v2`
- 표현 해상도: `PHD-P2-AB-V2-B-REPRESENTATION-v1`
- 상대 prior shift: `PHD-P2-AB-V2-B-PRIOR-SHIFT-v1`
- 독립 검산: `PHD-P2-AB-V2-B-VERIFICATION-v2` (v1도 보존)
- loss별 gradient: `PHD-P2-AB-V2-B-GRADIENT-AUDIT-v1`

모두 `/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v2/` 아래 새 run이다. [b_run_docker.sh](../../../../scripts/phd/p2_ab_v2/b_run_docker.sh)와 각 [config](../../../../configs/phd/p2_ab_v2/b_native_v1.json)가 실행을 나타내고, 각 run은 config·코드 snapshot·입력/overlay SHA256·Docker image·Git head·torch/gsplat/CUDA 버전을 기록한다. 동일 이름의 결과를 재사용하거나 덮어쓰지 않는다. v1 전체 산출물, 역사 payload와 기존 서비스는 유지했다.
