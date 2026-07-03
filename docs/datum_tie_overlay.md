# Datum Tie Overlay - 확인 오버레이

> 브랜치 `feat/p2-structure-learn`. 재구성/재학습 없음. 순수 투영·렌더 산출. 최종 판정은 김휘영.

## 0. 재현 범위

- 실행 산출: `docs/figs/datum_tie_overlay/`, `runs/20260703_datum_tie_overlay/versions.txt`.
- 지오 산출물 CRS: EPSG:25832. OPF 선언 CRS: EPSG:32632.
- 왼쪽 패널: `zeta=45.700 m` 공식 45.7.
- 오른쪽 패널: `zeta=48.126 m` 기각된 관례·LS 참고 대비값.
- 이론 이동량: `Delta zeta 2.426 m x tan(theta)`.
- A3a/A3b는 이 커밋에서 수행하지 않았다.

## 1. 대상 선정

선정 근거: zeta는 블록 상수이므로 어느 건물에도 같은 값으로 들어가야 한다. 이번 선정은 차이가 픽셀로 보이는 조건의 시연 기준이다. 서로 다른 위치·형태에서 같은 값으로 지붕 외곽과 LiDAR 지붕점이 함께 움직이면 상수성의 시각 증거가 된다.

dense 성공 그룹은 `W2_1c_paired_status.csv`에서 `als_has_lod22=True AND dim_has_lod22=True`인 114동 기준을 사용했다. 아래 3동은 모두 이 기준에 포함된다.

| building_id | 위치 | centroid E,N | 형태 | 수직/중간/강기울기 각도 deg | 선정 사유 |
|---|---|---:|---|---|---|
| DEBY_LOD2_4906966 | west/NW | 690864.6, 5336055.5 | sloped, LoD2 roofType 3100 | vertical 3.4 / middle 30.1 / strong 60.8 | 서쪽 블록, 수직/중간/강기울기 뷰 보유, 강기울기 지붕 외곽-배경 대비가 선명한 시연 조건. |
| DEBY_LOD2_4906969 | central/south | 690928.8, 5336019.1 | flat, LoD2 roofType 1000 | vertical 10.3 / middle 31.4 / strong 60.0 | 중앙 블록, flat 지붕 형태, 강기울기 뷰에서도 참조 지붕 링이 crop 안에 남는 시연 조건. |
| DEBY_LOD2_4959460 | east | 691009.1, 5336176.8 | complex/other, LoD2 roofType 9999 | vertical 7.0 / middle 31.0 / strong 63.1 | 동쪽 블록, 큰 지붕 외곽과 강기울기 링이 crop 안에 남아 AOI 동서 분산을 채우는 조건. |

## 2. 뷰별 오버레이

| building_id | angle_bin | view | zenith_deg | Delta zeta x tan(theta) m | figure | 관찰 |
|---|---|---|---:|---:|---|---|
| DEBY_LOD2_4906966 | vertical | `DJI_20241217084855_0191_D.JPG` | 3.44 | 0.146 | `docs/figs/datum_tie_overlay/4906966_vertical_pair.png` | 수직 뷰에서는 두 zeta 패널의 차이가 작고, 45.7 패널의 링/점이 지붕 외곽에 더 머물러 보인다. |
| DEBY_LOD2_4906966 | middle | `DJI_20241217084901_0194_D.JPG` | 30.14 | 1.409 | `docs/figs/datum_tie_overlay/4906966_middle_pair.png` | 중간 뷰에서는 오른쪽 48.126 패널이 같은 방향으로 이동해 차이가 보이기 시작한다. |
| DEBY_LOD2_4906966 | strong | `DJI_20241217095507_0036_D.JPG` | 60.81 | 4.342 | `docs/figs/datum_tie_overlay/4906966_strong_pair.png` | 강기울기 뷰에서는 45.7 패널의 링/점이 지붕 모서리에 더 가까워 보이고, 48.126 패널의 이동이 crop 안에서 분리되어 보인다. |
| DEBY_LOD2_4906969 | vertical | `DJI_20241217084601_0104_D.JPG` | 10.28 | 0.440 | `docs/figs/datum_tie_overlay/4906969_vertical_pair.png` | 수직 뷰에서는 두 zeta 패널의 차이가 작고, 45.7 패널의 링/점이 지붕 외곽에 더 머물러 보인다. |
| DEBY_LOD2_4906969 | middle | `DJI_20241217084719_0143_D.JPG` | 31.37 | 1.479 | `docs/figs/datum_tie_overlay/4906969_middle_pair.png` | 중간 뷰에서는 오른쪽 48.126 패널이 같은 방향으로 이동해 차이가 보이기 시작한다. |
| DEBY_LOD2_4906969 | strong | `DJI_20241217103103_0008_D.JPG` | 59.98 | 4.199 | `docs/figs/datum_tie_overlay/4906969_strong_pair.png` | 강기울기 뷰에서는 45.7 패널의 링/점이 지붕 모서리에 더 가까워 보이고, 48.126 패널의 이동이 crop 안에서 분리되어 보인다. |
| DEBY_LOD2_4959460 | vertical | `DJI_20241217091043_0084_D.JPG` | 6.99 | 0.297 | `docs/figs/datum_tie_overlay/4959460_vertical_pair.png` | 수직 뷰에서는 두 zeta 패널의 차이가 작고, 45.7 패널의 링/점이 지붕 외곽에 더 머물러 보인다. |
| DEBY_LOD2_4959460 | middle | `DJI_20241217091037_0081_D.JPG` | 31.02 | 1.459 | `docs/figs/datum_tie_overlay/4959460_middle_pair.png` | 중간 뷰에서는 오른쪽 48.126 패널이 같은 방향으로 이동해 차이가 보이기 시작한다. |
| DEBY_LOD2_4959460 | strong | `DJI_20241217100114_0043_D.JPG` | 63.09 | 4.779 | `docs/figs/datum_tie_overlay/4959460_strong_pair.png` | 강기울기 뷰에서는 45.7 패널의 링/점이 지붕 모서리에 더 가까워 보이고, 48.126 패널의 이동이 crop 안에서 분리되어 보인다. |

## 3. 강기울기 모서리 확대

| building_id | view | zenith_deg | Delta zeta x tan(theta) m | figure | 관찰 |
|---|---|---:|---:|---|---|
| DEBY_LOD2_4906966 | `DJI_20241217095507_0036_D.JPG` | 60.81 | 4.342 | `docs/figs/datum_tie_overlay/4906966_strong_corner_zoom.png` | 강기울기 1뷰의 모서리 확대 crop에서 두 zeta 투영 차이가 픽셀로 분리되어 보인다. |
| DEBY_LOD2_4906969 | `DJI_20241217103103_0008_D.JPG` | 59.98 | 4.199 | `docs/figs/datum_tie_overlay/4906969_strong_corner_zoom.png` | 강기울기 1뷰의 모서리 확대 crop에서 두 zeta 투영 차이가 픽셀로 분리되어 보인다. |
| DEBY_LOD2_4959460 | `DJI_20241217100114_0043_D.JPG` | 63.09 | 4.779 | `docs/figs/datum_tie_overlay/4959460_strong_corner_zoom.png` | 강기울기 1뷰의 모서리 확대 crop에서 두 zeta 투영 차이가 픽셀로 분리되어 보인다. |

## 4. 관찰

- 수직 뷰에서는 `Delta zeta x tan(theta)`가 작아 패널 차이가 작다.
- 중간·강기울기 뷰로 갈수록 같은 zeta 차이가 더 큰 image-plane 이동으로 보인다.
- 세 위치/형태 모두에서 `45.7` 패널의 LoD2 링과 ALS 지붕점이 지붕 외곽에 더 가까워 보인다. 이 문장은 시각 관찰이며 채택 판정이 아니다.
- `48.126` 패널은 강기울기 crop에서 같은 방향으로 더 이동해 외곽과 분리되어 보인다. 이 문장은 시각 관찰이며 채택 판정이 아니다.

## 5. 판정 필요 지점

1. `45.7` 공식값을 이후 A3a/A3b 입력 zeta로 사용할지 여부.
2. `48.126` LS 참고값을 이번 오버레이 이후 계속 대비값으로만 둘지 여부.
3. 이 확인 오버레이만으로 A3a/A3b 투입 조건이 충분한지 여부.
