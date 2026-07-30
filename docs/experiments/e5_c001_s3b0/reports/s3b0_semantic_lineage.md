# S3-B 0-e semantic 마스크 계보 감사

- 범위: 현행 캐시 계보의 소스 추적과 비-GT SAM ViT-B 마스크의 IoU 측정.
- 학습 실행: `learning_runs_started=0`.
- 현행 캐시의 역할: 계보 감사와 IoU 채점 전용. 비-GT SAM 프롬프트·추론 입력에는 사용하지 않음.
- 비-GT 프롬프트: 공급 footprint XY, 영상 유래 FM 평면, zero-iteration SfM+DIM 높이만 사용.

## 의존 표

| 단계 | 구현 | 읽는 항목 | 생성 항목 | 의존 전파 |
|---|---|---|---|---|
| 현행 semantic class | `phases/p2-gsjso/scripts/make_clean_labels.py` | CityGML LoD2 Roof/Wall/GroundSurface와 COLMAP pose | LoD2 mesh raycast class PNG | semantic class 전체 픽셀 |
| 현행 semantic_region ID | `phases/p2-gsjso/scripts/e5_c001_s3_semantic_regions.py` | 동일 LoD2 raycast의 building ID와 고정 class-1 PNG | region_ids, cutline_mask, region-to-building mapping | target/neighbor 영역 주소 |
| Phase-2 crop | `phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_prepare.py` | 현행 semantic PNG와 semantic_region NPZ | native-pixel crop | 학습 crop의 class와 instance 주소 |
| target-region 선택 | `src/stage2/train.py::_target_region_mask` | metadata.regions의 building_id | target_region_mask와 target_region_ids | mono-depth/mono-normal target-region 주소 |
| semantic geometry regularizer | `src/stage2/loss/semantic_guided.py` | oracle-instance-split region_ids와 cutline | region별 smooth/plane/boundary 주소 | semantic-guided geometry loss 주소 |
| S3-B 구속 영역에 현행 캐시를 재사용할 경우 | `미구현 설계 입력` | 위 region_ids와 target building ID | semantic∩footprint 구속 대상과 이웃 마스크 | LoD2 class+정답 ID 의존이 P_r 대상 선택과 photo 이웃 마스킹까지 전파 |

## 의존 항목 목록

- LoD2 표면 기하: class 레이캐스트와 building-ID 레이캐스트에 사용.
- 정답 building ID: `metadata.regions`의 target 선택과 이웃 분리에 사용.
- 공급 footprint: 현행 v3 loss 주소 자체가 아니라 과거 defect baseline과 crop QA에 사용되며, 본 0-e 비-GT 프롬프트에서는 허용된 2D 공간 입력으로 사용.
- 전파 범위: semantic class → instance region → target mask/cutline → mono target-region 및 semantic geometry regularizer. 같은 캐시를 S3-B에 연결하면 구속 스플랫 주소와 이웃 photo 마스킹까지 이어짐.

## 비-GT 대체 측정 규격

- 모델: Meta Segment Anything ViT-B, 공식 checkpoint `sam_vit_b_01ec64.pth`.
- target prompt 높이: footprint 내부 영상 대응점으로 적합한 FM 평면.
- neighbor prompt 높이: C00118 각 footprint 내부 zero-iteration COLMAP sparse + DIM dense-init z 중앙값.
- 후보 선택: `0.70 × SAM predicted IoU + 0.30 × projected-footprint IoU` 최대 후보.
- IoU 비교 대상: 현행 LoD2-raycast cache의 target/neighbor/합집합 마스크. 이 비교는 score-only.

## 소스 SHA256

- `phases/p2-gsjso/scripts/e5_c001_s3_semantic_regions.py`: `6fde6adb2df01a5411b0a4512d53fb5f0d1e1e8b1636fe5f35a827de6ca3c384`
- `phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_prepare.py`: `11e1c2e5b77c8f9e601925aa768637bf03bc968684b5c76900cdf81b013ab558`
- `phases/p2-gsjso/scripts/make_clean_labels.py`: `64bf932c2edcbdb188cf2ea13f3fcbad821b64d31317f2bcb81da8554eb8c9d9`
- `src/stage2/loss/semantic_guided.py`: `bce153583d843eb81e7a2f855d5605292729787aca627acc3b79e90d8bf3eb48`
- `src/stage2/train.py`: `e58f12fae4a30f1977ee74535facccf98fb3cb5ccb22e542f3485a642ca96dfc`
