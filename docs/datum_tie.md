# Datum Tie v3 - 측량 방식 높이 맞추기

> 브랜치 `feat/p2-structure-learn`. 재구성/재학습 없음. 사진 매칭/에지 매칭 없음. 관찰·수치·제안까지만, 최종 판정은 김휘영.

## 0. 재현 범위

- 실행 산출: `docs/datum_tie_patches.csv`, `docs/figs/datum_tie/`, `runs/20260703_datum_tie_v3/versions.txt`.
- 지오 산출물 CRS: EPSG:25832. OPF 선언 CRS: EPSG:32632.
- 높이 비교식: `Delta = dense_camera_height - (ALS_DHHN2016 + GCG2016_AOI)`.
- 사진 대응, 에지/코너 매칭, gradient-max, +-28px STEP는 사용하지 않았다.

## 1. 높이 기준 문서 감사

| 데이터 | 수직 기준 선언 | 원문 인용/근거 | 관찰 |
|---|---|---|---|
| 바이에른 ALS | DHHN2016 해발/Normalhöhe | LDBV Laserpunkte: `Höhenbezugssystem DHHN2016`; `Koordinatensystem UTM Zone 32`; `Geodätisches Datum ETRS 89`; `Bezugsellipsoid GRS 1980`. <https://www.ldbv.bayern.de/produkte/landschaftsinformationen/laser.html> | `als_aoi.laz`는 EPSG:25832 태그, class 2/6 사용. 원 raw ALS 일부 타일은 CRS 태그가 비어 있으나 수치 범위와 AOI 처리 산출로 EPSG:25832를 보존한다. |
| 참조 LoD2 | DHHN2016 해발/Normalhöhe | LDBV LoD2-BY: `Koordinatensystem UTM Zone 32`, `Datum ETRS89`, `Höhensystem DHHN2016`, `Abgabeformat CityGML`. <https://www.ldbv.bayern.de/produkte/liegenschaftsinformationen/gebaeudemodell.html> | footprint도 LoD2 GroundSurface에서 추출한 XY 도메인이다. 수직값을 직접 쓰지 않지만 기준은 LoD2와 같이 문서화한다. |
| footprint | LoD2 GroundSurface 파생 | `phases/p0-audit/scripts/05_footprints.py`는 `GroundSurface`의 `gml:posList`를 추출하고 `crs=EPSG:25832`로 저장한다. | 이번 측정에서는 지붕 패치의 내부 마스크로만 사용했다. |
| 카메라 포즈(OPF) | 수직 datum 미선언 | `input_cameras.json`: `coordinates=[48.14969263888889, 11.568962805555556, 636.837]`, `crs.definition=EPSG:4326`. `scene_reference_frame.json`: `WGS 84 / UTM zone 32N`, `ID[EPSG,32632]`, `CS[Cartesian,2]`, `shift=[-690953,-5336071,-604]`. | 핵심 한 줄: OPF geolocation/CRS 필드는 3번째 좌표를 갖지만 vertical CRS/geoid 모델을 선언하지 않는다. |
| TUM 동시취득 ULS | 해수면 위, 모델 미상 | Zenodo PDF: `Georeferenced data is WGS84 / UTM 32N (EPSG:32632). Elevation is given above mean sea level.` <https://zenodo.org/records/14899378> | ULS LAZ 헤더는 EPSG:32632만 반환해 vertical model은 명시하지 않는다. |
| TUM Photogrammetry 원본 LAZ | EGM96 height | `TUM_Downtown_Photogrammetry_20241217.laz` LAS header: `COMPD_CS["WGS 84 / UTM zone 32N + EGM96 height" ... AUTHORITY["EPSG","5773"]]`. | 서류상 기대 Delta 계산의 기준 후보로 EGM96을 별도 병기한다. |
| COLMAP/GS-LOCAL | shift -604 관례 | `results/tum_transfer/mob/raw/versions.txt`: `ellipsoidal UTM (GS-LOCAL+[690953,5336071,604])`. `tum_mob_raw_to_npz.py`: `dense = dim_v1.laz ... as-is`, `SHIFT=[690953,5336071,604]`. | 이번 실측 입력은 `raw_dense.npz`만 사용했다. `raw_acmp/raw_lidar`는 versions에 `+48 geoid`가 있어 제외했다. |
| 촬영 측위 | M350 RTK + SAPOS NTRIP | TUM PDF: `DJI Matrice 350 RTK ... Zenmuse L2`; `connected to the NTRIP service of SAPOS Bayern`. SAPOS HEPS: `1-2 cm (Lage) and 2-3 cm (Höhe)`. DJI M350 RTK: `1 cm + 1 ppm horizontal`, `1.5 cm + 1 ppm vertical`. | 측위 편차는 문서상 cm급으로 둔다. 실제 표면 비교 산포는 포즈/표면/모드 선택 오차를 함께 포함한다. |

참고 수치:

- GCG2016(AOI): 45.700 m (grid 직접 판독 45.663 m, 문서 표기는 45.7 m 반올림).
- EGM96(AOI): 45.544 m (`pyproj` EPSG:4326+5773 -> EPSG:4979, lon/lat=11.568963/48.149693).
- LS ζ 참고: 48.126 ± 0.429 m (`docs/projection_zeta_ls.md`).
- 서류상 기대 Delta: 카메라/원본 Photogrammetry가 EGM96 해수면 선언이면 `N_EGM96 - GCG2016 = -0.156 m`.

## 2. 같은 표면 3D 실측 비교

- 패치 수: 전체 60 = 지면 36 + 지붕 24.
- Delta 중앙값 ± MAD: 0.060 ± 0.050 m.
- Delta min/p10/p90/max: -3.210 / -0.060 / 0.200 / 2.340 m.
- 지면군 Delta: 0.060 ± 0.040 m.
- 지붕군 Delta: 0.050 ± 0.075 m.
- 지면군·지붕군 중앙값 차: 0.010 m.
- 유효 ζ = 45.7 + Delta = 45.760 m.

측정 입력:

- 영상 유래 점군: `results/tum_transfer/mob/raw/raw_dense.npz` (`raw_dense`, voxel 0.1 m).
- 금지/제외: `raw_acmp.npz`, `raw_lidar.npz`는 생성 이력에 `+48 geoid`가 있으므로 사용하지 않았다.
- ALS: `results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz`, class-2 지면과 class-6 지붕.
- 지붕 후보: P0 canonical w2_1의 `als_has_lod22=True AND dim_has_lod22=True` 114동에서, 실제로 ALS class-6와 raw_dense 상부 모드가 충분한 건물만 채택.

그림:

- `docs/figs/datum_tie/datum_tie_histogram.png`: Delta 히스토그램.
- `docs/figs/datum_tie/datum_tie_spatial_map.png`: 패치별 Delta 공간 지도.
- `docs/figs/datum_tie/datum_tie_group_box.png`: 지면군/지붕군 분리 분포.

## 3. 공간 경향과 보조 ICP

- Delta 공간 회귀: east -0.213 m/100m, north 0.083 m/100m, R2=0.156.
- AOI 내 회귀 예측 span: 0.801 m.
- 중앙 패치 보조 회귀(|Delta-중앙값|<=0.3m, n=53): east -0.016 m/100m, north -0.010 m/100m, span 0.096 m.
- |Delta-중앙값|>0.3m outlier: 7 / 60 patches. 전체 회귀 span은 이 outlier 후보에 민감하다.

| patch_id | surface | building_id | Delta m | 관찰 |
|---|---|---|---:|---|
| R019 | roof | DEBY_LOD2_4959320 | -3.210 | 같은 표면 모드 불확실/표면 의존 후보 |
| G004 | ground | - | 2.340 | 같은 표면 모드 불확실/표면 의존 후보 |
| R009 | roof | DEBY_LOD2_4907020 | 0.720 | 같은 표면 모드 불확실/표면 의존 후보 |
| G001 | ground | - | 0.690 | 같은 표면 모드 불확실/표면 의존 후보 |
| R006 | roof | DEBY_LOD2_4906965 | -0.370 | 같은 표면 모드 불확실/표면 의존 후보 |
| G005 | ground | - | -0.300 | 같은 표면 모드 불확실/표면 의존 후보 |

| building_id | ICP dx m | ICP dy m | 비고 |
|---|---:|---:|---|
| DEBY_LOD2_4908352 | 0.000 | 0.000 | 보조 XY 결속 확인용, 판정 도구 아님 |
| DEBY_LOD2_4908178 | 0.000 | 0.000 | 보조 XY 결속 확인용, 판정 도구 아님 |
| DEBY_LOD2_4907177 | -0.010 | 0.000 | 보조 XY 결속 확인용, 판정 도구 아님 |

## 4. 대비표와 제안

| 항목 | 값 m | 비고 |
|---|---:|---|
| GCG2016(AOI) | 45.700 | 공식 DHHN2016 변환 기준, grid 판독 45.663 m |
| 관례 | 48.000 | 기존 파이프라인 상수 |
| LS ζ 참고 | 48.126 | `docs/projection_zeta_ls.md`의 사진 대응 LS 참고값 |
| 실측 유효 ζ | 45.760 | 이번 점군 대 점군 Delta 중앙값 반영 |
| 서류상 EGM96 기대 Delta | -0.156 | EGM96 - GCG2016 |
| 실측 Delta | 0.060 | 전체 패치 중앙값 |

합격 제안 기준의 기계적 관찰: 수치 기준 중 하나 이상이 미달 방향.

- 패치 간 산포 MAD <= 0.3 m: 0.050 m.
- 지면군·지붕군 Delta 차 <= 0.3 m: 0.010 m.
- 공간 경향 span <= 0.3 m: 0.801 m.
- 문서화용 오버레이: 수치 기준이 미달 방향이므로 이 커밋에서는 as-projected 오버레이를 만들지 않았다.

제안 문장(판정 아님): 수치 기준 3개가 모두 충족 방향일 때만 ζ̂ 확정 제안을 검토한다. 미달 방향이면 공간 경향, 표면군 차이, raw_dense 상부/지면 모드 선택을 원인 후보로 남기고 A3a/A3b 투입 전 김휘영 판정을 기다린다.

## 5. 판정 필요 지점

1. 이번 점군 대 점군 실측 유효 ζ를 채택할지 여부.
2. OPF 수직 datum 미선언을 카메라 높이 기준 불확실성으로 남길지, Photogrammetry LAZ의 EGM96 선언을 촬영 자 기준으로 볼지 여부.
3. 수치 기준 미달 방향이 있을 경우 A3a/A3b를 중지하고 추가 원인 관찰을 할지 여부.
4. 수치 기준 충족 방향일 경우 as-projected 오버레이를 별도 커밋으로 만들지 여부.
