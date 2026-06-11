# P0 — 입력 치환 Audit 실행 가이드 (Codex·범용 에이전트용)

> Claude Code는 CLAUDE.md(동일 내용)를 읽는다. 사람 검토자: 김휘영.

## 1. 목표 (한 줄)

같은 장면·같은 footprint·같은 재구성 파이프라인에 **ALS 점군(Ref-L)** 과 **영상 유래 DIM 점군(Seq-G)** 을 각각 투입해 최종 CityJSON 건물 모델의 품질 차이와 실패 유형을 정량화한다. 상세 설계: `docs/P0_입력치환Audit_실험설계서_v1.docx`.

## 2. 판정 기준 (설계서 §6 요약)

- H1 지지: Plane F1 0.10↑ 하락, 경계 오차 1.5배↑, validity rate 10%p↑ 하락 중 2개 이상 (건물 단위 paired 중앙값)
- 기각 시: 방법론 정교화 보류, 프레임 전환 검토 — **판정은 사람이 한다. 에이전트는 수치 산출까지만.**

## 3. 디렉토리 규약

```
p0-audit/
  data/raw/        # 다운로드 원본 — 절대 수정 금지
  data/work/       # 가공 산출물 (점군, footprint, 모델)
  env/             # Dockerfile, conda env, 버전 기록
  scripts/         # 번호 순 실행 스크립트 (01_, 02_, ...)
  runs/<run_id>/   # 실행별 config.yaml + 로그 + 산출물
  docs/            # 설계서, 인벤토리, 진단 리포트
```

> 이 문서의 모든 상대 경로는 `p0-audit/` 기준이다. 에이전트 세션은 반드시 `p0-audit/`에서 시작한다.

## 4. 불변 규칙

1. `data/raw/` 수정 금지. 모든 가공은 `data/work/`에 새 파일로.
2. 손으로 실행하지 말 것 — 모든 처리는 `scripts/`의 스크립트 + config로 재현 가능해야 한다.
3. 모든 런은 `runs/<run_id>/versions.txt`에 도구 버전·커밋·파라미터 기록.
4. CRS는 **EPSG:25832** 통일. 모든 점군/벡터 산출물에 CRS 명시.
5. LAZ 분류 코드: ground=2, building=6 (Roofer 입력 요건).
6. 한 태스크 = 한 git 커밋. 커밋 메시지에 태스크 ID.
7. 실패·예외는 숨기지 말고 `docs/issues.md`에 기록 후 보고.
8. **모든 도구 실행은 도커 기반** — 호스트 직접 설치 금지. `scripts/`의 스크립트는 `docker compose -f env/docker-compose.p0.yml run --rm <service> ...` 호출로 작성한다. 컨테이너는 `--gpus all`(필요 시)과 호스트 사용자 매핑(`--user $(id -u):$(id -g)`)으로 실행해 root 소유 산출물을 만들지 않는다. 이미지 태그와 digest를 `env/versions.md`에 기록한다. 기존 레포 루트의 Dockerfile/docker-compose.yml(GS-JSO용)과 섞지 말 것.
9. 권장 이미지 구성: `colmap/colmap`(GPU, SfM/triangulator), OpenMVS는 공식 레포 Dockerfile로 `env/Dockerfile.openmvs` 빌드, `3dgi/roofer`(재구성), `tools`는 `env/Dockerfile.tools`로 빌드(PDAL, GDAL, laspy, val3dity 바이너리, citygml-tools+JRE).

## 5. 데이터 소스 (검증 완료, 2026-06-11)

| 항목 | 출처 | 비고 |
|---|---|---|
| UAV 영상 + 포즈 | Zenodo record 14548134 (`images.zip`, `opf.zip`) | Pix4D OPF — 내부·외부표정 포함 |
| OPF→COLMAP 변환 | tum2t.win/tutorials/im-gaussiannerf | `pyopf` / `opf2colmap` |
| ALS 점군 | geodaten.bayern.de 오픈데이터 (LAZ, ~4 pt/m², CC BY 4.0) | TUM 캠퍼스 타일 |
| LoD2 reference | download1.bayernwolke.de/a/lod2/citygml/ (690_5334, 690_5336) | CityGML 2.0 |
| 보조: Vaihingen | ISPRS UrbanSemLab seafile 직링크 (16 GB, pw: secret) | 영상 표정 + ALS + roof reference |

## 6. 파이프라인 정의

- **Ref-L**: ALS LAZ → 분류 확인 → Roofer(기본값) → CityJSON  [상한 참조]
- **Seq-G**: 영상+포즈 → COLMAP `point_triangulator`(포즈 고정) → OpenMVS densify → LAZ 변환·분류(PDAL) → 동일 Roofer → CityJSON  [audit 대상]
- 파이프라인 2안: City3D (CGAL 5.4–5.6 소스 빌드, CLI는 Qt 불필요)
- 검증 도구: val3dity (입력은 CityJSON만 — CityGML은 citygml-tools로 변환)

## 7. W1 태스크 (각각 별도 세션 권장, 한 태스크 = 한 커밋 = 사람 확인 후 다음)

### T0 — 환경 구축 (도커)
프롬프트: "이 문서를 읽어. T0 작업: ① data/raw, data/work, env, scripts, runs 디렉토리 생성, 레포 루트 .gitignore에 p0-audit/data/와 p0-audit/runs/ 추가. ② 규칙 8·9에 따라 env/docker-compose.p0.yml 작성 — 서비스: colmap(colmap/colmap, GPU), openmvs(env/Dockerfile.openmvs로 빌드), roofer(3dgi/roofer), tools(env/Dockerfile.tools로 빌드: PDAL·GDAL·laspy·val3dity·citygml-tools). 모든 서비스에 data/·runs/ 볼륨 마운트와 사용자 매핑 적용. ③ 스모크 테스트: 각 서비스에서 버전 명령 1개씩 실행해 출력 확인, GPU 서비스는 컨테이너 내 nvidia-smi로 GPU 인식 확인. ④ 완료 기준: 이미지 태그·digest를 env/versions.md에 기록 + 한 커밋(T0)."

### T1 — 데이터 다운로드
프롬프트: "AGENTS.md §5의 소스에서 data/raw/로 내려받는 scripts/01_download.sh를 작성·실행해. 완료 기준: 각 파일의 SHA256·용량·라이선스를 docs/data_inventory.md 표로 기록, 실패 URL은 사유와 함께 표시."

### T2 — OPF→COLMAP 변환 + 포즈 검증
프롬프트: "opf.zip을 pyopf/opf2colmap으로 COLMAP 포맷(cameras.txt, images.txt, points3D.txt)으로 변환하는 scripts/02_opf2colmap.py를 작성·실행해. 완료 기준: 카메라 수·이미지 수 출력, 포즈 위치를 LoD2 footprint 위에 그린 overlay PNG 생성(docs/figs/), 좌표가 EPSG:25832 범위인지 assert."

### T3 — DIM 점군 생성
프롬프트: "COLMAP point_triangulator(포즈 고정)→이미지 undistort→OpenMVS DensifyPointCloud로 DIM 점군을 만들고 LAZ(EPSG:25832)로 변환하는 scripts/03_mvs.sh를 작성·실행해. 완료 기준: 점수·밀도·범위를 lasinfo로 출력해 docs/dim_v1_stats.md에 기록, ALS와 같은 영역의 단면 비교 PNG 1장."

### T4 — 점군 분류 전처리
프롬프트: "DIM LAZ에 PDAL로 ground(2)/building(6) 분류를 부여하는 scripts/04_classify.py를 작성해 (SMRF로 지면, footprint 내 비지면점을 building으로). ALS는 기존 분류 검증만. 완료 기준: 클래스별 점수 통계 + 분류 결과 평면도 PNG."

### T5 — footprint 추출
프롬프트: "LoD2 CityGML에서 ground plan을 추출해 GPKG(EPSG:25832)로 저장하는 scripts/05_footprints.py를 작성·실행해. 완료 기준: 건물 수 출력, 대상 장면 폴리곤(scene_aoi.gpkg)과 교차하는 건물 목록 CSV."

### T6 — 입력 진단 리포트
프롬프트: "ALS vs DIM 점군의 밀도, 평면 적합 잔차(지붕면 샘플), 경계부 노이즈 폭, 벽면 점 비율을 비교하는 scripts/06_diagnose.py를 작성·실행하고 docs/W1_diagnosis.md로 정리해. 완료 기준: 표 1개 + 그림 2개, 'W2 진입 가능 여부'에 대한 관찰 요약(판정은 하지 말 것)."

## 8. W2 미리보기 (참고)

장면(1–2) × 입력(ALS/DIM) × 파이프라인(Roofer/City3D) × 파라미터(기본/튜닝) → CityJSON 세트 + val3dity + plane F1/경계/높이 지표 산출. W1 완료 후 사람 go/no-go 통과 시 착수.

## 9. 알려진 함정

- Roofer는 분류된 점군 필요 (ground=2/building=6) — DIM 점군은 T4 없이 투입 불가
- OPF 좌표가 로컬일 수 있음 — T2에서 georeference 확인 필수
- val3dity는 CityGML 직접 입력 불가 (CityJSON 변환 먼저)
- OpenMVS InterfaceCOLMAP은 undistorted PINHOLE 모델만 받음
- TUM2TWIN ALS는 ~4 pt/m² — 결과 해석 시 밀도 명기 (Peters 2022의 2 m² 논거는 8 pt/m² 기준)
