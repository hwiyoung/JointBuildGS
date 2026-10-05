# B v2: 구조 유지와 관측 가능한 세부 복원의 독립 개발 설계

이 시험은 과거 ALS 전체 연속 표면을 Gaussian으로 초기화한 뒤, 그 구조를 유지하면서 현재 영상의 외관과 관측 가능한 세부를 복원할 수 있는지 확인한다. 구조 유지·현재 외관·국소 세부 형상을 별도 결과로 낸다. A의 현재 사용 가능성 판단을 검증하거나 그 판단으로 변형을 허가받은 실험은 아니다. `scientific_verdict: null`이다.

## 1. 초기 표현과 공정 비교

동일한 48×46 m P2 전체 영역의 native ALS를 공통 초기 중심으로 사용한다. 원점의 법선과 원본 membership을 보존하고, 법선에 접하는 planar 2D Gaussian을 배치한다. 크기는 실제 이웃 간격에서 정하고 색은 가시성 검사를 거친 현재 학습 영상으로 초기화한다. 정확한 간격·개수·크기·opacity·색 관측 수를 실행 config와 초기 상태에 저장한다. 표현 밀도 보강이 필요하면 동일 source 표면의 내부에서만 보간하고 원점 부모와 보간 여부를 기록한다. 흩어진 64개 셀만 고르지 않는다.

원본 FULL_OPENCV 영상에서 정확히 undistort한 P2 crop을 사용한다. 계산상 축소하면 배율과 카메라 내참수를 같이 기록한다. 33개 학습/11개 평가 뷰는 과거 개발에 노출된 영상이며 독립 확증 세트가 아니다. UAS는 B의 입력에 넣지 않는다.

| arm | 중심·법선·크기·opacity | 색 | 추가 구조 손실/제약 | 구분할 효과 |
|---|---|---|---|---|
| source_projection | 고정 | 초기 색 고정 | 없음 | 최적화 전 기준 |
| geometry_fixed | 고정 | 학습 | 없음 | 기하를 바꾸지 않은 외관 개선 |
| color_fixed | 제안과 같은 구조/세부 자유도 | 고정 | 조건부 구조 trust region | 외관 자유도 없는 기하 복원 |
| image_only | MVS G0에서 전체 학습 | 학습 | 없음 | 초기 source와 최적화의 총효과 기준 |
| prior_free | ALS G0에서 전체 학습 | 학습 | 없음 | 동일 prior 초기화의 자유 최적화 기준 |
| soft_prior | 전체 학습 | 학습 | 동일 ALS 구조의 유한 가중 손실 | soft prior의 효과/열화 |
| structured_detail | 거친 구조 제한, 세부 위치·방향 자유 | 학습 | 동일 ALS 구조의 trust region | 구조를 제한하면서 세부를 복원하는 효과 |

prior 최적화 arm은 같은 ALS G0·학습 뷰 순서·렌더러·반복 수를 사용한다. soft prior의 가중치는 사전 선언한 0.005/0.05/0.5를 비교한다. source projection은 공통 초기 상태이다. image-only는 같은 관측과 계산 예산이지만 MVS G0이므로 동일 초기화 비교가 아니다. ALS가 보완하는 MVS 결손도 전체 영역 분모에 남긴다. 시간적 상충/무대응 영역을 미리 제외하지 않고 관측 상태별로 보고한다.

## 2. 구조와 세부 자유도

native patch와 고정 공간 분할로 국소 그룹을 만들고, 각 그룹 중심 변화의 상수/접평면 선형 성분을 거친 구조로 정의한다. 세부 변화는 그 성분과 직교하도록 투영하여 위치·경사를 다시 숨겨 넣지 못하게 한다. 세부는 Z만이 아니라 3차원 잔차이며 quaternion, 접선 방향 크기, opacity도 학습한다. 그룹이 너무 작아 이 분해가 불가능하면 이를 기록하고 구조 prior를 부여하지 않는다.

이 B 독립 시험은 ALS 구조가 재사용 가능하다고 사전에 가정한 조건부 solver 시험이다. 이 가정은 시간적 유효성 증명이 아니며, 오래된/어긋난 prior에서 실패할 수 있다. proposed arm의 제한은 초기 ALS plane과 거친 중심/법선의 관계에 적용하며, 국소 세부 잔차와 방향 변화는 현재 영상 목적함수로 학습한다. 원점 이웃 범위 밖으로 이동하거나 관측이 부족한 원점의 세부 증가는 제한한다. MVS와의 대응/상충/무대응은 평가 하위상태로 남기며 결과가 나쁜 부분을 제외하는 선택 조건으로 쓰지 않는다.

trust region의 m/radian 단위와 기준(ALS/MVS spacing, plane residual, 명시적인 solver 설정)을 config에 남긴다. A의 ε/U 또는 정확도 보장으로 부르지 않는다. finite step projection/backtracking으로 제한을 만족시키며 모든 픽셀의 0변화 조건으로 최적화를 폐기하지 않는다. 실제 gradient, 제안 step, 적용 step, 거친/세부 이동, 법선 회전과 크기/opacity 변화를 기록한다.

거친 좌표/회전 moment 제한은 렌더·추출 표면 보존 보장이 아니다. scale/opacity와 서로 상쇄하는 국소 변형이 추출 깊이와 경계를 바꿀 수 있으므로, 제한 만족과 실제 표면 변화/지지 소실을 반드시 별도 보고한다. 관측점 수 및 그룹 design rank로 실제 비어 있는 detail 자유도도 기록한다.

## 3. 최적화 목적과 출처

공통 외관 목적은 robust RGB와 masked SSIM이다. 기하 학습 arm에는 렌더 법선과 깊이 유래 법선의 일관성, 학습 뷰 사이의 깊이/법선 재투영 일관성을 사용한다. 이는 동일 학습 영상의 정합 목적이지 새로운 독립 증거가 아니다. 2DGS의 planar primitive 및 surface regularization은 기존 방법이며 본 시험의 신규성 주장 대상이 아니다. [2DGS 원논문](https://arxiv.org/abs/2403.17888), [공식 구현](https://github.com/hbb1/2d-gaussian-splatting), [DN-Splatter 원논문](https://openaccess.thecvf.com/content/WACV2025/papers/Turkulainen_DN-Splatter_Depth_and_Normal_Priors_for_Gaussian_Splatting_and_Meshing_WACV_2025_paper.pdf).

geometry loss에는 Gaussian 중심의 카메라 Z 평균을 경사 표면 깊이와 혼동하지 않도록 ray–surfel intersection 깊이를 사용한다. 기존 감사가 통과한 gsplat 보조 출력 overlay를 별도 캐시에 재사용하고 소스/hash/gradient 검산을 기록한다. 공식 2DGS fork를 실행하지 않는다.

soft prior는 동일 조건부 ALS의 거친 plane 위치/법선 오차를 유한 가중 손실로 적용한다. 제안은 같은 구조 성분의 허용 영역을 명시적으로 제한한다. 유효 prior가 틀렸거나 오래되었으면 두 방식 모두 편향될 수 있다. 이 개발 시험은 판단을 대체하지 않으며, prior shift 조건을 통해 실패가 가려지는지 점검한다. 모든 가중치·schedule·학습률은 reference 평가 전에 고정하고 gradient 크기와 loss 추세를 공개한다.

## 4. 성공/실패를 구분하는 측정

- 구조: 초기/최종 metric depth·법선·거친 plane 관계, 고정 초기 ray support의 소실, 경계 이동. 제한 만족은 solver 기능 검산이며 정확도 향상 자체는 아니다.
- 외관: 동일 평가 뷰의 고정 초기 support 분모 및 whole valid crop에서 RGB 오차/SSIM, alpha coverage, 미복원 픽셀 수. missing을 빼고 얻은 값도 따로 표기한다.
- 세부: 실제 detail DOF·법선 회전의 비영 변화, 관측 수별 변화, 국소 high-pass 형상 변화. 현재 reference와의 세부 일치 평가는 별도 C에서 수행하며 단순 NN 오차 감소만으로 세부 복원 성공을 부르지 않는다.

학습 중 정해진 간격으로 loss·gradient·DOF 변화·평가 추세를 저장한다. 96회 smoke 결과를 성능 결론으로 쓰지 않으며 설정한 반복 수에서도 수렴하지 않으면 그대로 보고한다. 실제 Gaussian 전체의 `xyz/scales/quats/opacity/rgb/group`를 `gaussians_initial.npz`와 `gaussians_final.npz`에 저장하고, 원점 seed ID 및 초기/최종 gsplat RGB/depth/alpha/normal을 함께 내보낸다. 증감이 없으면 고정 표현 해상도의 한계를 밝히고, 충분한 간격·화소 지지를 별도 검사한다.
