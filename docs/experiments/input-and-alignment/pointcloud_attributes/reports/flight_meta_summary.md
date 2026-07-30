# flight_meta_summary — 촬영 설계 사실 + near-nadir 결손 공간 대응 (읽기·판정 금지)

> **박사연구 GS-JSO · 모집단 잠금 보조 v4 [3].** 브랜치 `feat/p2-structure-learn`. EPSG:25832(지오)/32632(OPF 프레임).
> Docker(`--user`). **읽기 + 소규모 신규계산**(포즈 통계·지도), 재구성/재학습 없음. 관찰만, 판정=김휘영.
> 재현 `scripts/evidence_and_attributes/p2_gsjso/flight_meta.py`(tools:t0). 그림 `docs/figs/texture_anchor_check/flight_nadir0_map.png`.

## 1. 촬영 설계 사실 (OPF `input_cameras`/`calibrated_cameras`/`calibration_settings` + COLMAP 포즈)

| 항목 | 값 | 출처 |
|---|---|---|
| 촬영일 | **2024-12-17 단일일** | capture `time` |
| 캡처 수 / 보정(calibrated) 카메라 / COLMAP 포즈 | **962 / 937 / 937** | input_cameras, calibrated_cameras, images.txt |
| 이륙고 대비 고도(AGL) | **중앙 43.3 m**, p10 34.6, p90 **75.0** (다고도) | `height_above_takeoff_m` |
| COLMAP 카메라중심 Z(타원체) | 575–637 m (중앙 604.7) | 포즈 |
| **광축 천정경사(tilt-from-vertical)** | **중앙 30.5°** — nadir≤20°:**392**(0–10°:359·10–20°:33) / 20–45°:249 / **>45°:296**(45–60:153·60–90:143) | 포즈 R |
| 촬영 블록(패스) | OPF-time **09:xx 194 · 10:xx 368 · 11:xx 400**(파일명은 UTC −1h: 08:4x·09:0x–1x·09:3x–10:1x) | capture `time`/파일명 |
| AOI 범위(카메라중심 XY) | x 690795–691140(**345 m**) × y 5335867–5336336(**469 m**) | 포즈 |
| 파이프라인/매칭/오블리크플래그 | scalable_standard / standard / **is_oblique_scene=False** | calibration_settings |
| 센서 | FULL_OPENCV 5280×3956, focal ~3717 px(내부 12파라미터) | cameras.txt·calibrated sensors |

**관찰(판정 금지)**: 광축 경사가 **뚜렷한 이봉형**(near-vertical 359장 @0–10° + 강오블리크 296장 @>45°) = **나디르 격자 패스 + 오블리크 패스** 혼합
설계. 다고도(35–75 m AGL)·3블록. OPF의 `is_oblique_scene=False`는 전용 오블리크 리그가 아님을 뜻할 뿐, 실제 광축엔 오블리크 다수 존재.

## 2. v3 `n_views_nadir==0` 69동의 공간 대응 (지도 `flight_nadir0_map.png`)

v3에서 **지붕 표본에 대해 near-nadir(뷰↔수직 ≤20°) 뷰가 하나도 없는 건물 = 69동**. 지도(빨강=69동, 회색=카메라중심 937,
파랑=나머지 AOI footprint)에서:

| 지표(중앙값) | **nn0 69동** | 나머지 130동 |
|---|---:|---:|
| **가장 가까운 near-nadir 카메라 XY 거리** | **66.0 m** | 14.9 m |
| AOI 카메라중심으로부터 거리(주변부?) | **220.2 m** | 158.0 m |

**관찰(판정 금지)**: nn0 69동은 **가장 가까운 나디르 카메라가 4.4× 멀고**(66.0 vs 14.9 m) **더 주변부**(220 vs 158 m)다. 즉
`n_views_nadir==0`은 건물 속성이 아니라 **나디르 격자 패스가 머리 위를 지나지 않은 촬영-설계 커버리지 공백**과 대응한다(~40 m AGL에서
66 m 측면거리면 지붕→카메라 광선이 수직서 ~58° → near-nadir 표본뷰 0). 이 69동은 텍스처를 **최소-입사각 오블리크 뷰**에서 읽으므로
[1] 텍스처 척도의 뷰 의존성과 직접 연결된다([[texture_anchor_check]]).

> 재현: `docker run … jointbuildgs-p0-tools:t0 python3 scripts/evidence_and_attributes/p2_gsjso/flight_meta.py`. 읽기·소규모 계산·재구성 없음.
