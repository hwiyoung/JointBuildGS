# 0100_D 단일 R1 마스크 재점검

## 그림을 읽는 법 — 현재 감독 범위와 평가 경계

`0100_D_outside_P1_and_actual_weights.pdf`는 **이전 revision 1 정책의 진단 자료**다.
그 PDF의 `전체 native MVS` 패널에서 파란색·보라색 채움은 **깊이값**이고,
청록색 윤곽은 **원래 30×30m P1 평가 범위**다. 둘 다 현재 학습 사용 마스크를 뜻하지 않는다.
같은 PDF의 실제 가중치 패널도 변경 전 정책이므로 현재 가중치의 근거로 사용하지 않는다.

현재 0100_D의 감독 범위는 **수동으로 분류한 R1/R2/R3의 유효 픽셀 합집합**이다.
이 범위를 원래 30×30m 평가 범위로 자르지 않았다. 다른 97개 depth는 기존 설정을 유지한다.
다른 뷰의 제한적인 P1 지면 관측 지원은 확인했지만, 실제 학습 기여도를 분리 측정한 것은 아니다.

현재 실행에 고정된 마스크의 SHA256을 확인하고 생성한 한 장짜리 설명 자료:

- [현재 감독 범위 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/p1_single_view_weight_v1/PHD-P1-SINGLE-VIEW-WEIGHT-v1/scope_explanation.GGlNGAjv/result/0100_D_current_supervision_scope.png)
- [현재 감독 범위 PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/p1_single_view_weight_v1/PHD-P1-SINGLE-VIEW-WEIGHT-v1/scope_explanation.GGlNGAjv/result/0100_D_current_supervision_scope.pdf)

왼쪽은 깊이값과 원래 평가 경계, 오른쪽은 실제 사용 마스크다.
오른쪽 초록색은 R2/R3 가중치 1, 주황색은 R1 가중치 α=0/1/4,
회색은 제외·미분류·범위 밖·결측 가중치 0이다. α=0이면 주황색도 감독에서 제외한다.
native 사용 픽셀 305,444개 중 254,260개는 원래 30m 평가 범위 밖에 있다.
이 설명 작업은 CPU에서 기존 마스크를 표시했으며 학습 설정과 실행은 변경하지 않았다.

## 현재 적용 정책 — revision 2, 수동 판단 영역만 사용

사용자 확정 답변 **“PDF에서 수동으로 판단한 영역만 사용하고 미분류·범위 밖 0”**에
맞춰 입력 지원 마스크를 새로 고정했다. 아래의 이전 revision 1은 역사이며 새 학습에
적용하지 않는다. 기존 `mask_audit.2mlId3`, `outside_scope.oh4zEe`와 그 영수증/NPZ를
덮어쓰지 않았다. 기존 R1의 113,103 RGB 픽셀과 60,438 native 픽셀도 바꾸지 않았다.

0100_D만 `use_mask = (region_id ∈ {1,2,3}) & valid`를 적용하고,
`r1_mask = (region_id == 1) & valid`에 α를 넣는다. R2/R3는 1,
R4/R5/R6/결측은 0이다. **다른 97개 카메라의 depth 감독신호는 기존 합의대로 변경하지 않는다.**
따라서 이번 변경을 98개 카메라 모두에 수동 지원 마스크를 적용한 실험으로 해석하면 안 된다.

| 최초 의미 구분 | 저장된 region ID | 의미 | RGB 유효 픽셀 | multiplier |
|---|---|---|---:|---|
| A | R1 | 보정 시험 지면 | 113,103 | α=0/1/4 |
| B | R3 | 기타 정적 지면 | 194,717 | 1 |
| C | R2 | 현재 건물 표면 | 263,641 | 1 |
| D | R4 | 관측 제외 대상 | 55,604 | 0 |
| 미분류 | R5 | 판단 유보·경계 등 | 298,285 | 0 |
| 범위 밖 | R6 | 기존 80m 문맥 밖 | 360,939 | 0 |
| MVS 결측 | 저장상 R5에 포함 | 결측 | 131,911 | 0 |

`use_mask`는 RGB 571,461픽셀, native 305,444픽셀이다. 유효 MVS 중 사용하지 않는
픽셀은 RGB 714,828개다. `r1_mask ⊆ use_mask`, native→RGB 최근접 대응,
원 부모 R1과의 동일성, α별 지원 밖 0과 R2/R3의 1을 CPU Docker에서 확인했다.

| 조건 | weight 0 | weight 1 | weight 4 |
|---|---:|---:|---:|
| α=0 | 959,842 | 458,358 | 0 |
| α=1 | 846,739 | 571,461 | 0 |
| α=4 | 846,739 | 458,358 | 113,103 |

현재 학습 입력은 외부 payload 루트 기준 다음 파일이다.

```text
phase-payloads/phd/p1_single_view_weight_v1/PHD-P1-SINGLE-VIEW-WEIGHT-v1/
  mask_support.lrfNvP/result/r1_mask.npz
```

- SHA256: `e18bfac247d92c0985df30ed36cf7a84f7bb68831a9a068460df64177eecadfc`
- 학습 key: `r1_mask`, `use_mask`; 모두 bool `(1013,1400)`
- 감사 key: `r1_native`, `use_native`, `valid_rgb`, `valid_native`,
  `region_id`, `region_id_native`
- 부모: 같은 `attempt.boolfix.QrP8Ir`의 native/RGB `region_id`, 새 수동 polygon 없음
- 상태: `PASS_SINGLE_VIEW_MANUAL_SUPPORT_AUDIT`, `scientific_verdict: null`
- `source/`에 revision 2 소스·config·CPU Docker `run.sh`, `run.log`와 result 영수증 보존

같은 result의 `0100_D_mask_audit.pdf`는 4쪽이다. 1쪽 전체 프레임 R1 감사,
2쪽 명시된 확대, 3쪽 A/B/C/D→R1/R3/R2/R4 및 R5/R6 범례와 full native MVS,
4쪽 실제 전체 프레임 α0/1/4 가중치를 담았다. 새로운
`0100_D_manual_region_support.png`와 `0100_D_actual_manual_support_alpha0_1_4.png`
두 장을 직접 확인했다. R1 밖을 전부 1로 두었던 이전 그림 대신 이 결과가 현재 계약이다.
`audit_weight_maps.npz`는 감사용이며 학습은 위 boolean 마스크를 사용한다.
이 감사 작업에서는 GPU 학습과 GT/evaluation 자료 접근을 하지 않았다.

<details>
<summary>역사: revision 1 — R1 밖의 유효 depth를 모두 1로 둔 이전 정책과 감사</summary>

- Task: `PHD-P1-SINGLE-VIEW-WEIGHT-MASK-AUDIT-v1`
- 확인일: 2026-09-15
- 상태: `PASS_SINGLE_VIEW_R1_INPUT_AUDIT` / `scientific_verdict: null`
- 카메라: `DJI_20241217084553_0100_D.JPG`, 고정 train index 0, image ID 91

## 결론과 실제 학습 계약

기존 80×80m 학습 문맥 안에 정의한 R1 전체를 유지했다. 원 RGB, current MVS,
prior 입력 깊이를 확대해 확인한 결과, 눈에 띄는 조각상·장비·차량·나무·사람은
기존 제외 구멍 또는 R1 경계 밖에 있었으며 새로 확정할 명백한 오류는 찾지 못했다.
추가 제외 polygon은 0개다. 모든 미세 객체나 MVS의 실제 정확도를 인증한 것은 아니다.

이번에 사용하는 것은 `r1_mask` 한 장이다. 0100_D의 유효 R1만 α=0/1/4로 바꾸며,
R1 밖 유효 MVS는 원래 multiplier 1, 결측은 0을 유지한다. 다른 카메라는 변경하지
않는다. 예전 6분류의 `weight` 래스터는 학습 입력으로 사용하지 않는다. 따라서
이번에 R1에서 제외한 장비 등도 R1 밖의 원래 유효 감독신호로는 1을 유지한다.
이는 이 단계가 단일 영역 가중치에 대한 반응 비교라는 조건에 따른다.

## 사용자가 지적한 P1 밖의 미표시 영역

예전 PDF가 전체 프레임을 담았다는 설명만으로는 질문에 답할 수 없다. 전체 프레임의
MVS가 존재하더라도, 예전 분류/표시용 맵은 미분류·문맥 밖·제외 객체를 0으로 표시했다.
그 회색은 MVS 결측을 뜻하지 않았다. 이번 실제 단일 R1 학습용 맵에서는 이 픽셀들도
유효 MVS이면 1로 참여한다. R1은 기존 30×30m P1 평가 prism으로 자르지 않았다.

| 범위 | native 1024×741 | RGB 1400×1013 |
|---|---:|---:|
| 전체 픽셀 | 758,784 | 1,418,200 |
| 유효 MVS | 688,200 | 1,286,289 |
| 결측 | 70,584 | 131,911 |
| 기존 30×30m P1 prism 안 유효 | 78,835 | 147,288 |
| 기존 30×30m P1 prism 밖 유효 | 609,365 | 1,139,001 |
| 80×80m context 안 유효 | 494,999 | 925,350 |
| 80×80m context 밖 유효 | 193,201 | 360,939 |
| 학습 R1 전체 | 60,438 | 113,103 |
| R1 중 30m prism 안 | 23,118 | 43,237 |
| R1 중 30m prism 밖·80m context 안 | 37,320 | 69,866 |

RGB 기준 예전 `unknown` 유효 298,285, `outside context` 유효 360,939,
`exclusion` 유효 55,604, 합계 714,828픽셀은 예전 표시용 0에서 이번 학습용 1이 된다.

| 조건 | weight 0 픽셀 | weight 1 픽셀 | weight 4 픽셀 |
|---|---:|---:|---:|
| α=0 | 245,014 | 1,173,186 | 0 |
| α=1 | 131,911 | 1,286,289 | 0 |
| α=4 | 131,911 | 1,173,186 | 113,103 |

경계는 native MVS를 카메라 좌표에서 역투영해 얻은 XYZ가 기존 3D 범위 안에 있는지로
계산했다. 30m 범위는 x=[−23,7], y=[−21,9], z=[−44.272,−25.962],
80m 범위는 x=[−48,32], y=[−46,34], z=[−90,80]이다. 그림의 범위 윤곽은
이 조건에 해당하는 관측 픽셀의 경계여서 결측·가림 주변에서도 경계가 생긴다.

## 마스크 파일과 계보

외부 payload 루트는 `../JointBuildGS-artifacts`이며 아래 경로는 그 루트 기준이다.

```text
phase-payloads/phd/p1_single_view_weight_v1/PHD-P1-SINGLE-VIEW-WEIGHT-v1/
  mask_audit.2mlId3/result/r1_mask.npz
```

- NPZ SHA256: `a9c65e002c430bf2c7a254e7f3d6f56aa7cdbe8c2112e6c725a9d984f4aa9241`
- 학습 key: `r1_mask`, dtype `bool`, shape `(1013,1400)`
- 추가 key: `r1_native` `(741,1024)`, `valid_rgb`, `valid_native`, 모두 bool
- RGB R1 bounding box: `[506,247,945,685]`, 마지막 좌표는 exclusive
- 기존 native/RGB R1과 완전히 동일, 제거 픽셀 0
- 결측 R1, context 밖 R1, 원래 수동 building/exclusion/unknown과 겹치는 R1 모두 0
- parent: `manual_region_masks_v1/PHD-P1-MANUAL-REGIONS-v1/attempt.boolfix.QrP8Ir`
- parent receipt SHA256: `809c14181dc5afb21a5fd056c48c2d09ee9e815c943167e1d44830644dcec66a`
- binding SHA256: `c8afb896b9e6a0cdee1921b49c46e97a3d0cb0c568dd2b37ddce9f592bc1d9d8`
- current MVS SHA256: `0ac621492d71c97c1ffc788713a171a88941a1de54c4b1f547e80ec5e43b3e54`
- RGB SHA256: `b578b74e82039f801508c25b02286b67ef220d648ca5d47463ddbb3d249faca0`
- prior depth SHA256: `861f2bb9e73cd3b3bdac98028afe6e7797d9f8b68778b7fab8ec2da507a1caeb`
- audit config SHA256: `b6001ae91e6133e58e5b25a92aa343c75a4b6648b74a940618e2d4adeda38b75`

CAMERA_Z MVS는 native 정수 ray를 유지하고, RGB로 옮길 때 학습 adapter와 동일한
nearest native 조회를 사용했다. 원 prior depth는 기존 Open3D 반 픽셀 ray와 datum
계보를 유지하며 새로운 정합이나 보정을 하지 않았다. R1 native local Z 범위는
−43.0031..−41.4139m이며 그림에서 연속적인 경사로 보인다. 다른 높이의 고립된 객체층을
확인하지 못했지만 이것은 입력 관측에 대한 점검이며 높이 정확도 판정은 아니다.

## 검토 그림

`mask_audit.2mlId3/result/`:

- `0100_D_full_frame_audit.png`: 전체 RGB/MVS, R1 중 30m 안팎 분리, current MVS 파생 높이
- `0100_D_r1_zoom_audit.png`: 동일 R1 주변의 원 RGB/overlay/MVS/prior 확대
- `0100_D_mask_audit.pdf`: 1쪽은 전체 프레임, 2쪽만 명시된 확대 crop
- `receipt.json`: 입력·소스·설정·출력 hash, shape/count/invariant 점검

사용자의 P1 밖 미표시 지적에 답하는 별도 보완 artifact는
`outside_scope.oh4zEe/result/`에 보존했다. 기존 mask attempt를 덮어쓰지 않았다.

- `0100_D_full_inputs_scope_contours.png`: P1 밖도 가리지 않은 전체 RGB/native MVS,
  30m 청록·80m 자홍·R1 주황 윤곽
- `0100_D_actual_full_frame_alpha0_1_4.png`: 실제 전체 프레임 가중치 0/1/4 범례
- `0100_D_old_display_vs_training_alpha4.png`: 예전 표시용 0과 이번 학습용 1 차이
- `0100_D_outside_P1_and_actual_weights.pdf`: 위 그림 3쪽
- `actual_weight_maps.npz`: 감사용 `alpha0`, `alpha1`, `alpha4` float32 전체 맵;
  학습 연결은 이 파일이 아닌 위 boolean `r1_mask.npz` 하나다.
- `receipt.json`: 전 프레임 범위/count/weight count와 원 마스크 hash 불변 확인

## 실행과 검증 범위

고정 Docker image `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`,
Python 3.10.20, NumPy 1.26.4, CPU 2개, 메모리 4GiB, network none, GPU 미노출로 실행했다.
각 attempt의 `source/`에 실행된 소스 snapshot·config·`run.sh`, 루트에 `run.log`가 있다.
repo commit은 `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`이고 새 소스는 snapshot hash로
함께 고정했다. source input 및 parent mask는 read-only mount였다.

검증은 현재 frozen 입력 파일 hash, native↔RGB 최근접 대응, bool dtype, 전체 픽셀
분할 합계와 α별 R1 밖 유효=1/결측=0 조건으로 수행했다. 출력 PNG 5장을 직접 보아
범위·기존 제외 구멍·표시용/학습용 차이를 확인했다. 모든 학습 뷰의 semantic 정확도나
독립적인 MVS confidence를 검사한 것은 아니다. UAS·LoD2 정답·evaluation camera·최적화
결과를 읽지 않았고, 이 감사 작업은 GPU 학습을 실행하지 않았다.

</details>
