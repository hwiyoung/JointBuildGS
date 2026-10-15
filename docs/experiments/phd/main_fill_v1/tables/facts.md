<!-- PHD-MAIN-FILL-v1 일 8.1 (facts) -->
# 6.3에 쓸 사실 (일 8.1)

- 작업: `PHD-MAIN-FILL-v1`, 담당 facts. 작성 10-15 23:23. scientific_verdict: null.
- 앞 작업(PHD-CH6-SUPPORT-v1)이 낸 값을 다시 쓰고, 이 발주의 꼴(값, 근거 파일과 줄, 확인한 방법)로 옮겼다. 줄 번호는 이 작업의 스크립트가 파일을 다시 읽어 찾았다 (`scripts/phd/main_fill_v1/facts/facts_v1.py`, 읽은 것은 `checks.json`).
- 등급: '확인'은 저장소 문서나 원본 자료에서 본 것이다. 앞 작업이 원본 파일로 셈한 값은 '확인한 방법'에 그렇게 적었다. 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 사본에만 있는 사실은 '확인 불가 (저장소 문서에 없음)'로 두고, 사본의 내용은 '참고'에 적었다(10월 15일 조정 결정).
- 경로 약어: `P0RAW` = `JointBuildGS-artifacts/phase-payloads/p0-audit/data/raw`, `P0` = `.../p0-audit`, `CH6P` = `.../phase-payloads/phd/ch6_support_v1/PHD-CH6-SUPPORT-v1`, `S0`, `S1`, `PREP` = 발주문의 약어, `GEOGS` = `.../phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`. 약어 없는 경로는 저장소(JointBuildGS-exp) 안이다.

## 1. 한눈에

| 발주의 사실 | 번호 | 값 (줄임) | 등급 |
|---|---|---|---|
| 데이터셋 이름과 인용 | F1 | TUM2TWIN의 UAS 사진 묶음 `Images.zip`이다(Zenodo 기록 14548134, 5,906,891,973 B, CC BY 4.0). 묶음 안의 영상은 962장이다. 실험은 그 가운데 표정이 있는 937장을 쓴다(DEC-P1-012: 962장, 표정… | 확인 |
| 데이터셋 이름과 인용 | F2 | 확인 불가 (저장소 문서에 없음). 저장소에는 Zenodo 기록 번호(14548134, 14899378)와 내려받은 주소만 있다. 자료집의 이름과 저자, 판의 날짜는 없다. | 확인 불가 (저장소 문서에 없음) |
| 데이터셋 이름과 인용 | F3 | Pix4D 표정 묶음(OPF) `opf.zip`이다(Zenodo 기록 14899378, 1,936,493,976 B, CC BY 4.0). 처음 적힌 기록 14548134에는 이 파일이 없어 14899378의 파일을 받았다. | 확인 |
| 데이터셋 이름과 인용 | F4 | TUM2TWIN UAS 레이저 자료(2024-12-17 캠페인)의 연직 비행 파일 `TUM_Downtown_ULS_20241217_nadir.laz`다(1,277,996,022 B). 같은 캠페인의 수동 비행 파일(`..._manual.laz`)은 실험 지역 넷의 … | 확인 (Zenodo 기록 번호는 확인 불가) |
| 데이터셋 이름과 인용 | F5 | 바이에른 측량청(Bayerische Vermessungsverwaltung)의 공개 레이저 점군, 1 km 타일 넷(690_5335, 690_5336, 691_5335, 691_5336)이다. CC BY 4.0, 출처 표기 "Bayerische Vermessungs… | 확인 |
| 데이터셋 이름과 인용 | F6 | 바이에른 측량청의 LoD2 건물 모형(CityGML), 2 km 타일 둘(690_5334, 690_5336)이다. CC BY 4.0, 출처 표기는 항공 LiDAR와 같다. 파일은 CityGML 1.0(AdV LoD2 프로파일)이다. 자료 목록 문서의 'CityGML… | 확인 |
| 데이터셋 이름과 인용 | F7 | Wysocki 외, TUM2TWIN, 학술지 논문, doi:10.1016/j.isprsjprs.2025.12.013. | 확인 |
| 데이터셋 이름과 인용 | F8 | 확인 불가 (저장소 문서에 없음). | 확인 불가 (저장소 문서에 없음) |
| 데이터셋 이름과 인용 | F9 | GeoGS 공개 예제 장면(example_scene.zip)의 평가 참값 r1_b1_sub002와 그 장면의 영상 15장이다. 인용은 README의 bibtex: Zhang, Q., Wysocki, O., Jutzi, B., "GeoGS: Geometric Prio… | 확인 (권, 쪽, DOI는 확인 불가) |
| LoD2를 낸 기관과 제작 시기 | F10 | 바이에른 측량청(Bayerische Vermessungsverwaltung)이다. 건물 ID는 `DEBY_LOD2_<번호>`이고 타일 이름표는 `LoD2_32_690_5336_2_BY`다. | 확인 |
| LoD2를 낸 기관과 제작 시기 | F11 | B0 4959323: 모델 생성일(creationDate) 2025-04-04, 지적 평면과 맞춘 날(Grundrissaktualitaet) 2025-02-17. B173 4959326: 2025-01-02, 2025-02-17. R1 4906975: 2025-04… | 확인 |
| LoD2를 낸 기관과 제작 시기 | F12 | 평면의 절반 넘게 탐색 지역 일곱 곳(R3은 R3E 안이라 앞 작업의 여덟 범위 합집합과 같다)에 드는 78동: 모델 생성일 2025-04-04 34동, 2023-06-29 25동, 2021-04-20 14동, 2015-09-24 4동, 2025-01-02 1동(B… | 확인 |
| LoD2를 낸 기관과 제작 시기 | F13 | 확인 불가. GML에는 지붕을 만든 시기의 속성이 없다. creationDate는 모델을 만든 날이다. 예를 들어 B173은 creationDate가 2025-01-02인데 2022년 전의 옛 박공 지붕을 담고 있다(날개는 지금 평지붕). | 확인 불가 (GML에 속성 없음) |
| LoD2를 낸 기관과 제작 시기 | F14 | 확인 불가 (저장소 문서에 없음). 코드 값 1000은 GML에서 확인했다(F11). | 확인 불가 (저장소 문서에 없음) |
| LoD2를 낸 기관과 제작 시기 | F15 | 확인 불가 (저장소 문서에 없음). 실험 설정이 쓴 LoD2 지붕 사양은 1.0 m다. | 확인 불가 (저장소 문서에 없음) |
| 표정을 얻은 방법 | F16 | 자료집이 준 Pix4D 표정(OPF)을 받았다. 새로 구하지 않았다. opf2colmap으로 COLMAP 형식으로 옮겼고, 카메라 모형은 하나(FULL_OPENCV, 초점 거리 3,717.2 화소)다. 표정이 있는 영상은 962장 가운데 937장이다. OPF를 만든… | 확인 |
| 표정을 얻은 방법 | F17 | 표정과 내부 표정을 고정한 채 점만 삼각측량했다. SIFT(최대 2,200 화소, 특징 4,096개, 카메라 하나 고정), 순차 정합(겹침 12, quadratic, 고리 찾기 없음), point_triangulator(fix_existing_frames 1, 초점… | 확인 |
| 표정을 얻은 방법 | F18 | COLMAP 4.0.4(고정 이미지 colmap/colmap@sha256:187ca5ec…), patch_match_stereo: 기하 일관성 켬, 최대 1,024 화소(깊이 지도 1024×741), 반복 3회, 거름 켬. 거름: 일관된 시점 2장 이상, 기하 비용… | 확인 |
| 표정을 얻은 방법 | F19 | 937장 모형의 표정을 그대로 쓴다. 장면 파일에는 2차원 관측이 없다. 학습 해상도는 1024×741이다. | 확인 |
| 영상의 크기와 지상 표본 거리 | F20 | 5280×3956 화소, DJI Zenmuse L2의 RGB 카메라(EXIF Make DJI, Model L2), 기체 DJI Matrice 350 RTK. | 확인 |
| 영상의 크기와 지상 표본 거리 | F21 | 원본 5280×3956을 왜곡을 편 1400×1013으로 바꾸고, 다시 1024×741로 줄였다. 학습과 MVS 모두 1024×741이다. | 확인 |
| 영상의 크기와 지상 표본 거리 | F22 | 75 m 연직 비행 영상 341장: 원본 해상도 2.06 cm(중앙값, 2.04~2.11), 학습 해상도 11.3 cm. 실험 지역 표면에서 학습 영상의 학습 해상도 값: B0 10.3 cm, B173 주변 9.8 cm, B173만 9.7 cm, R1 11.3 cm. | 확인 |
| 영상의 크기와 지상 표본 거리 | F23 | 공개 962장 가운데 75 m 자동 연직 비행(짐벌 −90°)이 341장, 15~55 m 수동 비행이 나머지 621장이다. 공통 937장을 광축 기울기 20° 이하로 나누면 연직 392장, 경사 545장이다. | 확인 |
| 영상의 크기와 지상 표본 거리 | F24 | B0 학습 243장(연직 62, 경사 181), 평가 35장(연직 9, 경사 26); B173 주변 학습 203장(연직 86, 경사 117), 평가 29장(연직 12, 경사 17); B173만 학습 140장(연직 56, 경사 84), 평가 20장(연직 8, 경사 1… | 확인 |
| 영상의 크기와 지상 표본 거리 | F25 | 333장이 맞다. 학습에 쓴 수다. 338장은 R1 상자의 학습 후보 수다(후보 387장 가운데 여덟 장에 한 장인 49장을 평가로 떼고 남은 수). 상자 MVS가 그 338장 가운데 333장에만 기하 깊이 지도를 냈고, 깊이 지도가 없는 경사 영상 5장(DJI_2… | 확인 |
| 참값 정리 규칙의 요점 | F26 | 1) 영상과 같은 날 같은 기체로 찍은 드론 LiDAR 연직 비행 점을 쓴다. 0.5 m 칸에서 드론 LiDAR가 MVS와 항공 LiDAR보다 모두 1.5 m 넘게 높으면, 그 칸에서 두 값 가운데 큰 쪽보다 0.75 m 넘게 높은 점(굴뚝 수증기, 차량, 크레인의… | 확인 |
| 드론 LiDAR의 정확도와 밀도 | F27 | DJI Zenmuse L2, 기체 DJI Matrice 350 RTK. 영상과 같은 기체다. | 확인 |
| 드론 LiDAR의 정확도와 밀도 | F28 | 확인 불가 (저장소 문서에 없음). 저장소 문서는 정확도를 감사할 항목으로만 적었다. | 확인 불가 (저장소 문서에 없음) |
| 드론 LiDAR의 정확도와 밀도 | F29 | 평가 범위의 모든 반사 점 ÷ 평면 넓이: B0 1,028, B173 주변 1,334, B173만 1,071, R1 1,408점/m². 상자(평가 범위 + 10 m): B0 994, B173 주변 1,468, B173만 1,071, R1 1,377점/m². | 확인 |
| 드론 LiDAR의 정확도와 밀도 | F30 | 연직 비행 2024-12-17T07:42:37~08:12:54 UTC(GPS 시각). 파일은 LAS 1.2, 형식 3, 177,981,904점, 머리 작성일 2024-12-23. | 확인 |

## 2. 사실마다

### 데이터셋 이름과 인용

**F1. 현재 영상의 출처**

- 값: TUM2TWIN의 UAS 사진 묶음 `Images.zip`이다(Zenodo 기록 14548134, 5,906,891,973 B, CC BY 4.0). 묶음 안의 영상은 962장이다. 실험은 그 가운데 표정이 있는 937장을 쓴다(DEC-P1-012: 962장, 표정 있음 937장, 표정 없음 25장).
- 등급: 확인
- 근거: `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 10줄; `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 29줄; `docs/research/06_DECISION_LOG.md` 416, 425–427줄
- 확인한 방법: 문서의 줄은 이 작업의 스크립트가 다시 찾았다. 원본 `P0RAW/uav/Images.zip`의 크기(5,906,891,973 B, 자료 목록과 같음)와 묶음 안 JPEG 수(962)를 이번에 다시 셌다.

**F2. UAS 자료집의 이름과 저자**

- 값: 확인 불가 (저장소 문서에 없음). 저장소에는 Zenodo 기록 번호(14548134, 14899378)와 내려받은 주소만 있다. 자료집의 이름과 저자, 판의 날짜는 없다.
- 등급: 확인 불가 (저장소 문서에 없음)
- 근거: `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 10–11줄; `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 22줄
- 확인한 방법: 저장소 문서(docs, configs, artifacts/manifests)에서 자료집 이름 'UAV Laser Scanning and Photogrammetry'와 저자 이름을 grep으로 찾았으나 없었다.
- 참고: 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 사본에는 이름 "UAV Laser Scanning and Photogrammetry of TUM Downtown Campus", 저자 Anders, Wang, Wysocki, Huang, Liu, 판 1.0(2024-12-23, doi:10.5281/zenodo.14548134), 판 1.1.0(2025-02-24, doi:10.5281/zenodo.14899378, opf.zip을 더함), 여러 판을 묶는 DOI 10.5281/zenodo.14548133이 있다. (`CH6P/t2/web_verification.md` 22–30줄; `CH6P/t2/web_downloads/dl/z14548134.json` 1줄; `CH6P/t2/web_downloads/dl/z14899378.json` 1줄)

**F3. 표정 묶음의 출처**

- 값: Pix4D 표정 묶음(OPF) `opf.zip`이다(Zenodo 기록 14899378, 1,936,493,976 B, CC BY 4.0). 처음 적힌 기록 14548134에는 이 파일이 없어 14899378의 파일을 받았다.
- 등급: 확인
- 근거: `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 11줄; `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 22줄; `docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json` 103줄
- 확인한 방법: 줄을 다시 찾았다. 원본 `P0RAW/uav/opf.zip`의 크기(1,936,493,976 B)를 다시 셌다.

**F4. 드론 LiDAR의 출처**

- 값: TUM2TWIN UAS 레이저 자료(2024-12-17 캠페인)의 연직 비행 파일 `TUM_Downtown_ULS_20241217_nadir.laz`다(1,277,996,022 B). 같은 캠페인의 수동 비행 파일(`..._manual.laz`)은 실험 지역 넷의 평가 범위에 점이 없어(0점) 쓰지 않았다. 드론 LiDAR 파일이 든 Zenodo 기록 번호는 저장소 문서에 없다.
- 등급: 확인 (Zenodo 기록 번호는 확인 불가)
- 근거: `docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json` 138–139줄; `docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json` 138, 143줄; `docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json` 138, 149–150줄; `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 31줄; `CH6P/t2/density_uls_manual.json` 202줄
- 확인한 방법: 줄을 다시 찾았다. 원본 크기(1,277,996,022 B)와 LAS 머리(판 1.2, 형식 3, 177,981,904점, 머리 날짜 2024-12-23)를 이번에 다시 읽었다. 수동 비행 파일의 평가 범위 점 수(네 지역 모두 0, 0, 0, 0)는 앞 작업이 원본 LAZ로 센 값이다.
- 참고: 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 사본에는 연직 비행 파일이 Zenodo 판 1.0, 1.1.0, 1.2.0에 같은 바이트로 들어 있다고 적혀 있다. (`CH6P/t2/web_verification.md` 22–30줄)

**F5. 항공 LiDAR의 출처와 시기**

- 값: 바이에른 측량청(Bayerische Vermessungsverwaltung)의 공개 레이저 점군, 1 km 타일 넷(690_5335, 690_5336, 691_5335, 691_5336)이다. CC BY 4.0, 출처 표기 "Bayerische Vermessungsverwaltung – www.geodaten.bayern.de". 촬영은 GPS 시각으로 2022-02-27(17:56~18:52 UTC)이고, 파일 머리의 2022-06-16은 작성일이다. 현재 영상까지 약 2.8년이다.
- 등급: 확인
- 근거: `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 12–15줄; `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 26줄; `docs/experiments/phd/main_stage3_v1/본실험_3단계_보고서_v1.md` 1065줄; `CH6P/t2/density_als.json` 48–49, 366–367, 684–685, 1002–1003줄 (타일 넷)
- 확인한 방법: 줄을 다시 찾았다. 네 타일의 크기와 690_5336의 LAS 머리(작성일 2022-06-16, 21,428,108점)를 이번에 다시 읽었다. 촬영 시각의 분 단위는 앞 작업이 모든 점의 GPS 시각에서 셈한 값이다.

**F6. LoD2의 출처와 형식**

- 값: 바이에른 측량청의 LoD2 건물 모형(CityGML), 2 km 타일 둘(690_5334, 690_5336)이다. CC BY 4.0, 출처 표기는 항공 LiDAR와 같다. 파일은 CityGML 1.0(AdV LoD2 프로파일)이다. 자료 목록 문서의 'CityGML 2.0'은 파일과 다르다.
- 등급: 확인
- 근거: `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 16–17줄; `P0RAW/lod2/690_5336.gml` 2줄; `P0RAW/lod2/690_5334.gml` 2줄
- 확인한 방법: 자료 목록의 줄을 다시 찾았다. 두 GML 파일의 2줄(이름공간 http://www.opengis.net/citygml/1.0, 스키마 cityGMLBaseLoD2.xsd)을 이번에 다시 읽었다: 690_5336: 1.0 True, 2.0 False, 690_5334: 1.0 True, 2.0 False.

**F7. TUM2TWIN 논문 (저장소에 있는 부분)**

- 값: Wysocki 외, TUM2TWIN, 학술지 논문, doi:10.1016/j.isprsjprs.2025.12.013.
- 등급: 확인
- 근거: `docs/research/02_NOVELTY_MAP.md` 42줄; `docs/research/02_NOVELTY_MAP.md` 165–166줄
- 확인한 방법: 줄을 다시 찾았다.

**F8. TUM2TWIN 논문의 학술지, 권, 쪽, 연도, 전체 제목, 저자 목록**

- 값: 확인 불가 (저장소 문서에 없음).
- 등급: 확인 불가 (저장소 문서에 없음)
- 근거: `docs/research/02_NOVELTY_MAP.md` 165–166줄
- 확인한 방법: 저장소 문서에서 권과 쪽, 전체 제목을 grep으로 찾았으나 없었다(02_NOVELTY_MAP.md에는 DOI 연결만 있다).
- 참고: 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 사본에는 "TUM2TWIN: Introducing the large-scale multimodal urban digital twin benchmark dataset", ISPRS Journal of Photogrammetry and Remote Sensing 232 (2026) 810–830, 저자 34명(Wysocki, Schwab, Biswanath 외)이 있다. (`CH6P/t2/web_verification.md` 4–8줄; `CH6P/t2/web_downloads/dl/crossref_tum2twin.json` 1줄)

**F9. B0의 주 참값과 저자 영상 15장 (GeoGS)**

- 값: GeoGS 공개 예제 장면(example_scene.zip)의 평가 참값 r1_b1_sub002와 그 장면의 영상 15장이다. 인용은 README의 bibtex: Zhang, Q., Wysocki, O., Jutzi, B., "GeoGS: Geometric Prior-Guided Gaussian Splatting for Robust Urban Reconstruction from Sparse Views", ISPRS Journal of Photogrammetry and Remote Sensing, 2026. 실험은 이 참값을 저자 좌표에서 (2, −29, 0) m 옮기고 높이를 0.0746 m 내려 쓴다.
- 등급: 확인 (권, 쪽, DOI는 확인 불가)
- 근거: `GEOGS/sources/GeoGS/README.md` 3줄; `GEOGS/sources/GeoGS/README.md` 5줄; `GEOGS/sources/GeoGS/README.md` 152줄; `GEOGS/sources/GeoGS/README.md` 166–170줄; `scripts/phd/main_prep_measure_v1/step04_gt.py` 287–288줄; `scripts/phd/main_prep_measure_v1/step04_gt.py` 298줄
- 확인한 방법: 실험이 쓴 GeoGS 소스 사본의 README와 참값을 읽는 스크립트의 줄을 다시 찾았다. README의 bibtex에는 권, 쪽, DOI가 없고, 논문 쪽 PII S0924271626003588 연결만 있다. 논문이 이 참값을 어떻게 만들었는지는 원문이 없어 확인 불가다.
- 참고: 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 사본에는 권 240, 쪽 184–201, doi:10.1016/j.isprsjprs.2026.07.011이 있다. (`CH6P/t2/web_verification.md` 47–52줄; `CH6P/t2/web_downloads/dl/crossref_geogs.json` 1줄)

### LoD2를 낸 기관과 제작 시기

**F10. LoD2를 낸 기관**

- 값: 바이에른 측량청(Bayerische Vermessungsverwaltung)이다. 건물 ID는 `DEBY_LOD2_<번호>`이고 타일 이름표는 `LoD2_32_690_5336_2_BY`다.
- 등급: 확인
- 근거: `docs/evidence/p0-audit/w1-input-diagnostics/reports/data_inventory.md` 16–17줄; `P0RAW/lod2/690_5336.gml` 3줄; `P0RAW/lod2/690_5336.gml` 1950950줄
- 확인한 방법: 자료 목록의 출처 표기 줄과 GML의 이름표 줄, 건물 줄을 이번에 다시 읽었다.

**F11. 대상 세 동의 LoD2 날짜**

- 값: B0 4959323: 모델 생성일(creationDate) 2025-04-04, 지적 평면과 맞춘 날(Grundrissaktualitaet) 2025-02-17. B173 4959326: 2025-01-02, 2025-02-17. R1 4906975: 2025-04-04, 2025-02-17. 지붕 높이 자료의 코드(DatenquelleDachhoehe)는 세 동 모두 1000이다.
- 등급: 확인
- 근거: `P0RAW/lod2/690_5336.gml` 1950950–1950951, 1950962, 1950977, 1950983줄 (DEBY_LOD2_4959323); `P0RAW/lod2/690_5336.gml` 1953041–1953042, 1953053, 1953068, 1953074줄 (DEBY_LOD2_4959326); `P0RAW/lod2/690_5336.gml` 97766–97767, 97778, 97793, 97799줄 (DEBY_LOD2_4906975); `docs/experiments/phd/main_stage3_v1/본실험_3단계_보고서_v1.md` 1065줄
- 확인한 방법: 원본 GML을 줄 단위로 읽어 세 건물의 속성 줄을 이번에 찾았다(앞 작업의 표 CH6P/t2/lod2/lod2_buildings.csv와 같은 값).

**F12. 탐색 지역 일곱 곳 78동의 LoD2 날짜 분포**

- 값: 평면의 절반 넘게 탐색 지역 일곱 곳(R3은 R3E 안이라 앞 작업의 여덟 범위 합집합과 같다)에 드는 78동: 모델 생성일 2025-04-04 34동, 2023-06-29 25동, 2021-04-20 14동, 2015-09-24 4동, 2025-01-02 1동(B173). 지적 평면과 맞춘 날은 78동 모두 2025-02-17. 지붕 높이 자료의 코드는 1000이 69동, 5000이 6동, 3000이 2동, 6000이 1동이다.
- 등급: 확인
- 근거: `CH6P/t2/lod2/lod2_summary.json` 847줄; `CH6P/t2/lod2/lod2_summary.json` 854줄; `CH6P/t2/lod2/lod2_summary.json` 857줄
- 확인한 방법: 앞 작업이 원본 GML 두 타일을 읽어 센 값이다(scripts/phd/ch6_support_v1/task2/lod2_parse.py). 이번에 그 출력의 줄을 다시 읽었다.

**F13. LoD2 지붕을 만든 시기**

- 값: 확인 불가. GML에는 지붕을 만든 시기의 속성이 없다. creationDate는 모델을 만든 날이다. 예를 들어 B173은 creationDate가 2025-01-02인데 2022년 전의 옛 박공 지붕을 담고 있다(날개는 지금 평지붕).
- 등급: 확인 불가 (GML에 속성 없음)
- 근거: `P0RAW/lod2/690_5336.gml` 1953041–1953042, 1953053, 1953068, 1953074줄 (B173); `docs/experiments/phd/main_stage1_v1/본실험_1단계_보고서_v1.md` 131줄; `docs/experiments/phd/main_prep_measure_v1/준비측정_결정요청_v1.1.md` 97줄; `docs/experiments/phd/main_stage3_v1/본실험_3단계_보고서_v1.md` 837줄
- 확인한 방법: 대상 세 동의 일반 속성 이름을 이번에 모두 읽었다: Dachneigung, Dachorientierung, DatenquelleBodenhoehe, DatenquelleDachhoehe, DatenquelleLage, Flaeche, Gemeindeschluessel, Geometrietyp2DReferenz, Grundrissaktualitaet, HoeheDach, HoeheGrund, Methode, NiedrigsteTraufeDesGebaeudes, Z_MAX, Z_MAX_ASL, Z_MIN, Z_MIN_ASL. 지붕 제작 시기를 뜻하는 속성은 없다.

**F14. 지붕 높이 자료 코드의 뜻 (1000)**

- 값: 확인 불가 (저장소 문서에 없음). 코드 값 1000은 GML에서 확인했다(F11).
- 등급: 확인 불가 (저장소 문서에 없음)
- 확인한 방법: 저장소 문서에서 코드표를 찾았으나 없었다.
- 참고: 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 사본(기관의 LoD2 고객 안내 04/2026, 7절)에는 '1000 Aus Laserscanmessung'(레이저 측량에서), '5000 Aus Photogrammetrie – automatisch'가 있다. (`CH6P/t2/web_verification.md` 82줄)

**F15. LoD2 높이 정확도 (기관의 표현)**

- 값: 확인 불가 (저장소 문서에 없음). 실험 설정이 쓴 LoD2 지붕 사양은 1.0 m다.
- 등급: 확인 불가 (저장소 문서에 없음)
- 근거: `configs/phd/main_prep_measure_v1/prep_v5.json` 107–115줄
- 확인한 방법: 설정의 줄을 다시 찾았다. 기관의 정확도 표현은 저장소 문서에 없다.
- 참고: 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 사본에는 기관 제품 쪽 'Höhengenauigkeit ca. 1 m', 고객 안내 04/2026 '20-30 cm, 최대 1 m'가 있다. (`CH6P/t2/web_verification.md` 75줄; `CH6P/t2/web_verification.md` 76줄)

### 표정을 얻은 방법

**F16. 표정의 출처**

- 값: 자료집이 준 Pix4D 표정(OPF)을 받았다. 새로 구하지 않았다. opf2colmap으로 COLMAP 형식으로 옮겼고, 카메라 모형은 하나(FULL_OPENCV, 초점 거리 3,717.2 화소)다. 표정이 있는 영상은 962장 가운데 937장이다. OPF를 만든 소프트웨어는 Pix4Dmatic 1.58.1이다.
- 등급: 확인
- 근거: `phases/p0-audit/scripts/02_opf2colmap.py` 103, 107줄; `docs/evidence/p0-audit/w1-input-diagnostics/reports/opf2colmap_summary.md` 7–8줄; `P0/data/work/mvs/prepare_summary.txt` 1–3줄; `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 30줄; `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 32줄; `docs/research/06_DECISION_LOG.md` 425–427줄
- 확인한 방법: 스크립트와 요약 문서, 카메라 값 파일의 줄을 이번에 다시 찾았다.

**F17. COLMAP이 한 일과 설정**

- 값: 표정과 내부 표정을 고정한 채 점만 삼각측량했다. SIFT(최대 2,200 화소, 특징 4,096개, 카메라 하나 고정), 순차 정합(겹침 12, quadratic, 고리 찾기 없음), point_triangulator(fix_existing_frames 1, 초점 거리와 주점과 왜곡 다듬기 0), 왜곡 펴기(최대 1,400 화소, 1400×1013). 성긴 점은 371,808개다. COLMAP 판은 4.0.4다.
- 등급: 확인
- 근거: `phases/p0-audit/scripts/03_mvs.sh` 21–25줄; `phases/p0-audit/scripts/03_mvs.sh` 240, 250줄; `phases/p0-audit/scripts/03_mvs.sh` 257, 263줄; `phases/p0-audit/scripts/03_mvs.sh` 350, 360줄; `phases/p0-audit/scripts/03_mvs.sh` 372, 377줄; `P0/runs/t3_mvs_20260611_230138/logs/colmap_point_triangulator.log` 23–24줄; `P0/runs/t3_mvs_20260611_230138/logs/colmap_image_undistorter.log` 1줄; `configs/phd/main_prep_measure_v1/prep_v5.json` 88줄
- 확인한 방법: 스크립트와 P0 실행 기록(t3_mvs_20260611_230138)의 줄을 다시 찾았다. 성긴 점 수는 `P0/data/work/mvs/colmap_dense/sparse/points3D.bin`의 머리에서, 영상 크기는 cameras.bin에서 이번에 읽었다(모형 번호 1 = PINHOLE).

**F18. 상자 MVS의 설정과 관측 신뢰도 마스크**

- 값: COLMAP 4.0.4(고정 이미지 colmap/colmap@sha256:187ca5ec…), patch_match_stereo: 기하 일관성 켬, 최대 1,024 화소(깊이 지도 1024×741), 반복 3회, 거름 켬. 거름: 일관된 시점 2장 이상, 기하 비용 1 화소 이하, NCC 0.1 이상, 삼각 각 3° 이상. 상자마다 학습 영상만 쓴다. 관측 신뢰도 마스크는 기하 깊이가 남은 화소다.
- 등급: 확인
- 근거: `scripts/phd/main_prep_measure_v1/run_colmap.sh` 4–5줄; `scripts/phd/main_prep_measure_v1/run_colmap.sh` 11줄; `scripts/phd/main_prep_measure_v1/run_colmap.sh` 16–18줄; `configs/phd/main_prep_measure_v1/prep_v5.json` 76–87줄
- 확인한 방법: 스크립트와 설정의 줄을 다시 찾았다.

**F19. 실험 장면의 표정**

- 값: 937장 모형의 표정을 그대로 쓴다. 장면 파일에는 2차원 관측이 없다. 학습 해상도는 1024×741이다.
- 등급: 확인
- 근거: `S0/fork_inputs/s61/B0_b10/fork_inputs.json` 2줄; `S0/fork_inputs/s61/B0_b10/fork_inputs.json` 7줄
- 확인한 방법: S0의 입력 기록(fork_inputs.json)의 줄을 다시 읽었다.

### 영상의 크기와 지상 표본 거리

**F20. 원본 영상의 크기와 카메라**

- 값: 5280×3956 화소, DJI Zenmuse L2의 RGB 카메라(EXIF Make DJI, Model L2), 기체 DJI Matrice 350 RTK.
- 등급: 확인
- 근거: `docs/research/methodology/기준문서_방법론·모집단·비교설계_v1.md` 117줄; `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 31줄; `CH6P/t2/xmp_all.json` 21줄
- 확인한 방법: 묶음 안 영상 한 장(Images/DJI_20241217084239_0003_D.JPG)을 이번에 열어 크기와 EXIF를 읽었다. 기체 이름은 앞 작업이 962장의 XMP에서 센 값이다.

**F21. 학습과 MVS의 해상도**

- 값: 원본 5280×3956을 왜곡을 편 1400×1013으로 바꾸고, 다시 1024×741로 줄였다. 학습과 MVS 모두 1024×741이다.
- 등급: 확인
- 근거: `phases/p0-audit/scripts/03_mvs.sh` 25줄; `scripts/phd/main_prep_measure_v1/run_colmap.sh` 17줄; `S0/fork_inputs/s61/B0_b10/fork_inputs.json` 7줄; `S0/fork_inputs/s61/B173nb_b10/fork_inputs.json` 7줄; `S0/fork_inputs/s61/B173_b0/fork_inputs.json` 7줄; `S0/fork_inputs/s61/R1rep_b10/fork_inputs.json` 13줄
- 확인한 방법: 줄을 다시 찾았다. 왜곡을 편 영상의 크기(1400×1013)는 cameras.bin에서 이번에 읽었다.

**F22. 지상 표본 거리**

- 값: 75 m 연직 비행 영상 341장: 원본 해상도 2.06 cm(중앙값, 2.04~2.11), 학습 해상도 11.3 cm. 실험 지역 표면에서 학습 영상의 학습 해상도 값: B0 10.3 cm, B173 주변 9.8 cm, B173만 9.7 cm, R1 11.3 cm.
- 등급: 확인
- 근거: `CH6P/t2/gsd_views.json` 73줄; `CH6P/t2/gsd_views.json` 81줄; `CH6P/t2/gsd_views.json` 111줄; `CH6P/t2/facts_6_3.md` 83–85줄
- 확인한 방법: 앞 작업이 셈한 값이다. 땅 위 높이(카메라 높이 − 항공 LiDAR 맨땅)를 초점 거리(원본 3,717.2 화소, 학습 674.4 화소)로 나눴고, 표면 값은 상자 안 MVS 깊이의 중앙값을 썼다. 이번에 그 출력의 줄을 다시 읽었다.
- 참고: 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 사본에는 TUM2TWIN 논문의 '평균 지상 표본 거리 1.6 cm'가 있다. 지붕까지의 거리(약 60 m)와 맞는 값이다. (`CH6P/t2/web_verification.md` 14줄; `CH6P/t2/web_verification.md` 41줄)

**F23. 연직 영상과 경사 영상의 수**

- 값: 공개 962장 가운데 75 m 자동 연직 비행(짐벌 −90°)이 341장, 15~55 m 수동 비행이 나머지 621장이다. 공통 937장을 광축 기울기 20° 이하로 나누면 연직 392장, 경사 545장이다.
- 등급: 확인
- 근거: `CH6P/t2/xmp_all.json` 27줄; `CH6P/t2/gsd_views.json` 23줄; `configs/phd/main_prep_measure_v1/prep_v5.json` 62줄
- 확인한 방법: 앞 작업이 962장의 XMP(상대 높이, 짐벌 각)와 937장의 표정에서 센 값이다. 연직의 기준(20°)은 설정의 줄이다. 이번에 출력과 설정의 줄을 다시 읽었다.

**F24. 지역마다 학습과 평가 영상 수**

- 값: B0 학습 243장(연직 62, 경사 181), 평가 35장(연직 9, 경사 26); B173 주변 학습 203장(연직 86, 경사 117), 평가 29장(연직 12, 경사 17); B173만 학습 140장(연직 56, 경사 84), 평가 20장(연직 8, 경사 12); R1 학습 333장(연직 103, 경사 230), 평가 49장(연직 15, 경사 34). 후보 영상을 이름 순으로 놓고 여덟 장에 한 장을 평가로 뗐다.
- 등급: 확인
- 근거: `S0/fork_inputs/s61/B0_b10/fork_inputs.json` 4–5줄; `S0/fork_inputs/s61/B173nb_b10/fork_inputs.json` 4–5줄; `S0/fork_inputs/s61/B173_b0/fork_inputs.json` 4–5줄; `S0/fork_inputs/s61/R1rep_b10/fork_inputs.json` 4–5줄; `configs/phd/main_prep_measure_v1/prep_v5.json` 60줄; `PREP/step06/box_views.json` 4956줄
- 확인한 방법: S0 입력 기록의 학습과 평가 수, PREP의 상자 영상 표(box_views.json)를 이번에 다시 읽었다. 연직과 경사의 나눔(학습)은 앞 작업이 937장의 기울기로 다시 센 값(CH6P/t2/gsd_views.json의 boxes)이다.

**F25. R1의 학습 영상: 333장과 338장**

- 값: 333장이 맞다. 학습에 쓴 수다. 338장은 R1 상자의 학습 후보 수다(후보 387장 가운데 여덟 장에 한 장인 49장을 평가로 떼고 남은 수). 상자 MVS가 그 338장 가운데 333장에만 기하 깊이 지도를 냈고, 깊이 지도가 없는 경사 영상 5장(DJI_20241217093905_0026, DJI_20241217093907_0027, DJI_20241217093911_0029, DJI_20241217094010_0030, DJI_20241217094012_0031)을 학습 전에 뺐다. 상자 영상 표의 학습 경사 235장에서 5장을 빼면 230장이다. 그래서 학습은 333장(연직 103, 경사 230)이다. 338이 적힌 문서는 모두 학습에서 빼기 전의 후보 수를 적은 것이다.
- 등급: 확인
- 근거: `PREP/step06/box_views.json` 4175줄; `PREP/step06/box_views.json` 4956줄; `PREP/mvs/box_R1rep_b10/colmap_receipt.json` 1줄; `S0/fork_inputs/s61/R1rep_b10/fork_inputs.json` 4–11줄; `S0/fork_inputs/s61/R1rep_b10/fork_inputs.json` 2줄; `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.1.md` 572줄
- 확인한 방법: 세 파일(상자 영상 표, 상자 MVS 영수증, S0 입력 기록)의 값을 이번에 다시 읽었다. 338이 적힌 줄은 저장소 전체를 grep으로 찾았고, 다른 뜻의 338(가우시안 338만 개 등)은 뺐다. 목록은 아래 표.

### 참값 정리 규칙의 요점

**F26. 참값 정리 규칙의 요점 (처리 규칙 v5, 세 줄)**

- 값: 1) 영상과 같은 날 같은 기체로 찍은 드론 LiDAR 연직 비행 점을 쓴다. 0.5 m 칸에서 드론 LiDAR가 MVS와 항공 LiDAR보다 모두 1.5 m 넘게 높으면, 그 칸에서 두 값 가운데 큰 쪽보다 0.75 m 넘게 높은 점(굴뚝 수증기, 차량, 크레인의 일시 반사)을 지운다. 2) 높이는 학습 영상 최대 40장의 맨땅 화소에서 MVS 깊이와 참값 깊이의 차이 중앙값만큼 옮겨 맞춘다(1단계: 네 지역 공통 −4.38 cm). 3) 나무 칸과 일시 반사 칸은 결과 전에 평가에서 빼고, 벽의 참값은 수직면 위의 단일 반사 점만 쓴다(v5). B0의 주 참값은 GeoGS 저자의 평가 참값이고, 그것이 없는 곳은 드론 LiDAR로 채운다.
- 등급: 확인
- 근거: `configs/phd/main_prep_measure_v1/prep_v5.json` 4줄; `configs/phd/main_prep_measure_v1/prep_v5.json` 163줄; `configs/phd/main_prep_measure_v1/prep_v5.json` 164줄; `configs/phd/main_prep_measure_v1/prep_v5.json` 181–183줄; `configs/phd/main_prep_measure_v1/prep_v5.json` 186–189줄; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md` 30줄; `scripts/phd/main_prep_measure_v1/step04_gt.py` 287–288줄
- 확인한 방법: 설정과 보고서, 스크립트의 줄을 이번에 다시 찾았다. 세 줄은 앞 작업의 요약(CH6D 6장_3절_사실_v1.md 69–73줄)을 이 줄들에 맞춰 고친 것이다(1번에 +0.75 m 규칙을 더함).

### 드론 LiDAR의 정확도와 밀도

**F27. 드론 LiDAR 기기**

- 값: DJI Zenmuse L2, 기체 DJI Matrice 350 RTK. 영상과 같은 기체다.
- 등급: 확인
- 근거: `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 31줄; `CH6P/t2/xmp_all.json` 24줄
- 확인한 방법: 줄을 다시 찾았다. 영상 EXIF의 Model(L2)을 이번에 읽었다.

**F28. 드론 LiDAR 기기 정확도**

- 값: 확인 불가 (저장소 문서에 없음). 저장소 문서는 정확도를 감사할 항목으로만 적었다.
- 등급: 확인 불가 (저장소 문서에 없음)
- 근거: `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 75줄; `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 102줄; `docs/research/03_DATA_AND_BASELINE_SCOPE.md` 192줄
- 확인한 방법: 저장소 문서에서 기기 정확도를 찾았으나 없었다.
- 참고: 앞 작업(PHD-CH6-SUPPORT-v1)이 웹에서 받아 둔 제조사 사양 사본에는 'System Accuracy Horizontal: 5 cm @ 150 m, Vertical: 4 cm @ 150 m', 'Ranging Accuracy (RMS 1σ) 2 cm @ 150 m'가 있다. 자료집 논문은 GNSS 측점과의 평균 거리 0.08 m를 적었으나 다른 지역의 기록을 인용한 것이다. (`CH6P/t2/web_downloads/dji/zenmuse-l2_en.txt` 162–169줄; `CH6P/t2/web_verification.md` 56–58줄; `CH6P/t2/web_verification.md` 16줄)

**F29. 드론 LiDAR 점 밀도 (지역마다)**

- 값: 평가 범위의 모든 반사 점 ÷ 평면 넓이: B0 1,028, B173 주변 1,334, B173만 1,071, R1 1,408점/m². 상자(평가 범위 + 10 m): B0 994, B173 주변 1,468, B173만 1,071, R1 1,377점/m².
- 등급: 확인
- 근거: `CH6P/t2/density_uls_nadir.json` 204줄; `CH6P/t2/density_uls_nadir.json` 232줄; `CH6P/t2/density_uls_nadir.json` 260줄; `CH6P/t2/density_uls_nadir.json` 288줄; `CH6P/t2/density_uls_nadir.json` 190줄
- 확인한 방법: 앞 작업이 원본 LAZ를 0.1 m 칸으로 센 값이다(scripts/phd/ch6_support_v1/task2/points_density.py). 이번에 출력의 줄을 다시 읽었다.

**F30. 드론 LiDAR 촬영 시각과 파일**

- 값: 연직 비행 2024-12-17T07:42:37~08:12:54 UTC(GPS 시각). 파일은 LAS 1.2, 형식 3, 177,981,904점, 머리 작성일 2024-12-23.
- 등급: 확인
- 근거: `CH6P/t2/density_uls_nadir.json` 51줄; `CH6P/t2/density_uls_nadir.json` 52줄
- 확인한 방법: LAS 머리는 이번에 다시 읽었다. 촬영 시각은 앞 작업이 모든 점의 GPS 시각에서 셈한 값이다.

## 3. R1의 338이 적힌 곳

모두 학습에서 빼기 전의 후보 수(338장)를 적은 줄이다. 학습에 쓴 수는 333장이다.

| 파일 | 줄 | 내용 (앞부분) |
|---|---|---|
| `docs/experiments/phd/main_stage0_v1/본실험준비_0단계_보고서_v1.md` | 266 | 일치 영역이 매우 작다.** 상자의 학습 영상(140~338장)이 거의 모든 패치를 보고… |
| `docs/experiments/phd/main_stage0_v1/본실험준비_0단계_보고서_v1.md` | 319 | …보면 B173만(140장) 약 45분, B0(243장) 약 78분, R1rep(338장) 약 110분이다. 1단계의 지역 구성에… |
| `docs/experiments/phd/main_stage0_v1/본실험준비_0단계_보고서_v1.md` | 444 | …le_segments`)을 모든 학습에 둔다. 학습 영상이 가장 많은 R1rep(338장)을 1단계에서 먼저 돌려 메모리를 확인하기… |
| `docs/experiments/phd/main_stage0_v1/본실험준비_0단계_보고서_v1.md` | 483 | …없이 LoD2가 예약 21.5 GB까지 갔다. 학습 영상이 더 많은 R1rep(338장)과 B0(243장)에서는 더 클 수 있다.… |
| `docs/experiments/phd/main_stage0_v1/0단계_결정요청_v1.md` | 63 | 일치는 매우 작다.** 상자의 학습 영상(140~338장)이 거의 다 보고… |
| `docs/experiments/phd/main_stage0_v1/0단계_결정요청_v1.md` | 79 | …서도 메모리 설정 없이는 24 GB에서 멈췄다. 학습 영상이 더 많은 R1rep(338장)과 B0(243장)에서는 가우시안이 더 많… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.md` | 486 | / R1rep_b10 / LoD2 / 74 × 69 / 338 / 49 / 0.612 / 3.346 / (… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.md` | 487 | / R1rep_b10 / ALS / 74 × 69 / 338 / 49 / 0.127 / 0.127 / (… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.md` | 560 | …4906975) / 74 × 69 m = 5,156 m² (2,682 m²) / 338(깊이 지도 333) / 49 / LoD2 0… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.1.md` | 498 | / R1rep_b10 / LoD2 / 74 × 69 / 338 / 49 / 0.612 / 3.346 / (… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.1.md` | 499 | / R1rep_b10 / ALS / 74 × 69 / 338 / 49 / 0.127 / 0.127 / (… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.1.md` | 572 | …4906975) / 74 × 69 m = 5,156 m² (2,682 m²) / 338(깊이 지도 333) / 49 / LoD2 0… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_결정요청_v1.md` | 32 | …ep (부채꼴 건물 4906975) / 74 × 69 m (2,682 m²) / 338 / 49 / LoD2 0.682 / 0.73… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_결정요청_v1.md` | 119 | - **학습 비용의 눈금:** 학습 영상 243 / 203 / 140 / 338장, 상자 넓이 4,608 / 7,084 /… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_결정요청_v1.1.md` | 33 | …ep (부채꼴 건물 4906975) / 74 × 69 m (2,682 m²) / 338 / 49 / LoD2 0.682 / 0.73… |
| `docs/experiments/phd/main_prep_measure_v1/준비측정_결정요청_v1.1.md` | 120 | - **학습 비용의 눈금:** 학습 영상 243 / 203 / 140 / 338장, 상자 넓이 4,608 / 7,084 /… |
| `configs/phd/main_baselines_v1/baselines_v1.json` | 3984 | "images": 338,… |
| `configs/phd/main_baselines_v1/baselines_v1.json` | 4130 | "images": 338,… |

- 338이 있지만 다른 뜻인 줄(뺐다): `docs/experiments/phd/main_stage0_v1/본실험준비_0단계_보고서_v1.md` 289줄(가우시안 338만 개); `docs/experiments/phd/main_stage2_v1/tables/prep_tables.md` 201줄(빼낸 옛 점 수); `docs/experiments/phd/main_stage3_v1/tables/times.md` 29줄(B173 주변 학습의 기록 칸); `docs/experiments/phd/main_stage3_v1/본실험_3단계_보고서_v1.md` 376줄(같은 기록 칸).
- 1단계 뒤의 문서와 이 발주문은 333장을 쓴다(예: 이 발주문 3절의 CDGS 표 'R1 · LoD2 … 181 / 333').

## 4. 앞 작업과 다른 점

- 참값 정리 세 줄의 1번에 '+0.75 m' 규칙을 더했다(설정 `prep_v5.json`의 transient_rule 줄과 맞춤).
- 앞 작업이 '확인'으로 둔 웹 사실(자료집 이름과 저자, 논문의 권과 쪽, GeoGS의 권과 쪽과 DOI, 기기 정확도, LoD2 코드의 뜻과 높이 정확도)은 이 발주의 규칙대로 '확인 불가 (저장소 문서에 없음)'로 두고 사본의 내용을 '참고'로 옮겼다.
- LoD2 지붕을 만든 시기: 앞 작업의 '아직 모름'을 '확인 불가 (GML에 속성 없음)'로 적었다.
- 자료 목록 문서(data_inventory.md 16–17줄)의 'CityGML 2.0'은 파일(1.0)과 다르다. 앞 작업과 같은 결론이다.

