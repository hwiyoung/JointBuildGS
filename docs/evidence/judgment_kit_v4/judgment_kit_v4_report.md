# judgment_kit_v4_report

> 재구성/재학습 없음. 판정 금지. 수치·관찰과 산출만 기록한다.

## 0. 입력과 규약

- image-projection zeta: `geo=EPSG:25832 opf=EPSG:32632 input_default=orthometric orthometric_geoid_m=45.700000`.
- 3D/씨드 경로 `-556`은 건드리지 않았다.
- 지오 산출물 CRS: EPSG:25832. OPF/COLMAP frame: EPSG:32632.
- 수동판정 대상: `docs/bucket_crosswalk_v2.csv`의 `new_class=수동판정` 44동.
- `docs/manual_review_judgments.csv`: 없음 - 배치 열은 비움.

## 1. 산출

- `docs/evidence/judgment_kit_v4/*.png`: 수동판정 4칸 카드 44장.
- 비차단 시간차 locator: 2장.
- manifest: `docs/evidence/judgment_kit_v4/manifest.csv`.
- locator neighbor rings: min=2, lt2=0.
- footprint shape flags: `docs/evidence/judgment_kit_v4/support/footprint_shape_flags.csv` (44동, small=13, elong=1).
- run versions: `runs/20260703_cards_v4_kit/versions.txt`.

## 2. 결함별 조치

| 결함 | 조치 | 관찰 |
|---|---|---|
| ① 47장 중 30장 footprint 링 부재 | locator 패널을 새로 만들고 target=굵은 빨강 roof-height footprint, neighbor=가는 회색 roof-height footprint+ID로 고정했다. | manifest에 `neighbor_rings_drawn`을 기록했다. |
| ② 초소형 동 crop이 너무 넓음 | locator와 별개로 같은 view의 roof close-up 패널을 두고, target footprint bbox 기준 tight crop을 사용했다. | `small_flag(<50m2)` 동은 shape flags에서 추적 가능하다. |
| ③ 정의 없는 빨간 채널 | v4 footer에 모든 색 규약을 명시했다. | evidence_cards_v3 렌더 코드에는 빨간 오버레이 채널이 없다. draw_card_panel은 초록 LoD2 링, 청록 LiDAR 점, 흰색 에지 화살표만 쓴다. 이전 패널의 빨강은 v2 ID/footprint 화살표 또는 진단 스크립트 산출로 보이며, v3에서 정의된 채널은 아니다. |
| ④ 구 점군 패널의 오염 투영 혼란 | `docs/evidence/evidence_cards_v1/`과 v2 사진 링을 재사용하지 않고, `configs/projection_datum.json` 기본 45.700 경로로 재투영했다. | top-view는 사진 투영 링 없이 EPSG:25832 footprint만 사용했다. |
| ⑤ ALS 34~287점 동에서 점이 작음 | ALS class-6 in-footprint <500이면 top-view 마커를 3배 키웠다. | 대상: DEBY_LOD2_104583794, DEBY_LOD2_108247350, DEBY_LOD2_42364607, DEBY_LOD2_4908053, DEBY_LOD2_4908054, DEBY_LOD2_4908159, DEBY_LOD2_4908160, DEBY_LOD2_4908165, DEBY_LOD2_4908169, DEBY_LOD2_8568392 (10동). |
| ⑥ 4906999 시간차 강기울기 산개 | v3 코드는 class-6 footprint 내부 ALS를 image에 투영하되 사진 occlusion/depth 선별은 하지 않았다. | v4 수동판정 카드에서는 사진 위 ALS 점을 제거하고, 점 증거는 DIM/ALS top-view로 분리했다. |

## 3. 빨간 채널 정체

- evidence_cards_v3 렌더 코드에는 빨간 오버레이 채널이 없다. draw_card_panel은 초록 LoD2 링, 청록 LiDAR 점, 흰색 에지 화살표만 쓴다. 이전 패널의 빨강은 v2 ID/footprint 화살표 또는 진단 스크립트 산출로 보이며, v3에서 정의된 채널은 아니다.
- v4 카드 색: locator target red, neighbor gray, close-up target red, top-view footprint red, point color viridis height. 그 외 overlay 색은 쓰지 않았다.

## 4. 시간차 locator

- 42364663, 4959320 locator 컷을 같은 roof-height footprint 규약으로 생성했다.
- 4959320 locator는 v4 수치 `recon_score_median=1.461`, 기존 v3 manifest ALS=85,951점 조건과 함께 기록했다. 큰 footprint와 조밀한 ALS 상한이 같은 위치확인 crop에 대응한다는 관찰만 남겼다.

## 5. 실패·주의

- 없음.

## 6. 판정 필요 지점

1. `docs/manual_review_judgments.csv` 부재 상태에서 `bucket_crosswalk_v2.csv`의 44동 목록을 수동판정 kit 기준으로 사용할지 여부.
2. `small_flag`와 `elong_flag`를 manual_review_judgments.csv에 병합할지 여부.
3. ALS<500점 마커 3배 확대 카드들을 동일 판독 우선순위로 둘지 여부.
4. 4959320의 낮은 관측점수와 조밀 ALS 상한 관찰을 시간차/대조군 논의에 포함할지 여부.
