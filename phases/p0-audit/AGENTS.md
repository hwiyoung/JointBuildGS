# P0 — 입력 치환 Audit 실행 가이드 (Codex·범용 에이전트용)

> Claude Code는 CLAUDE.md(동일 내용)를 읽는다. 사람 검토자: 김휘영.

## 1. 목표 (한 줄)

같은 장면·같은 footprint·같은 재구성 파이프라인에 **ALS 점군(Ref-L)** 과 **영상 유래 DIM 점군(Seq-G)** 을 각각 투입해 최종 CityJSON 건물 모델의 품질 차이와 실패 유형을 정량화한다. 상세 설계: `docs/P0_입력치환Audit_실험설계서_v1.docx`.

> **현황(2026-06-13):** P0 전체(W1–W4) 완료 — 입력준비·진단(W1) → audit 실행(W2) → 지표·통합(W3) → G1 보고 패키지·보고서(W4). 핵심: DIM 재구성 실패 8건 vs ALS 0건(McNemar p=0.0078, 전처리·튜닝 비회복), 연속 지표는 §6 임계 경계선 → **부분 지지**. G1 보고서 작성 완료(`G1_P0결과보고_판정요청_v1_20260613.docx`; v2 정리 중). **현재 G1 미팅 대기** — 임계 확정·부분지지/기각·P2 착수·Vaihingen이 안건. 선택: T7(실패 8건 원인 세분). 다음: 판정 → P1 마무리 → P2. 상세: `docs/W3_summary.md`, 레포 `docs/evidence/p0_g1_20260613/`(컨테이너 `/workspace/docs/G1_package/`).

> **표기:** W=실행 주차(W1 입력준비·진단 / W2 audit / W3 지표·통합 / W4 G1 보고, 완료) · P=연구 단계(P0 입력치환 audit·완료 / P1 Ch1·Ch2 재서술·진행중 / P2 GS-JSO 코어(A1: semantic+geom-sem) / P3 조립연결 Part B: E5 미니·MVS 대비 correction gain / P4 확장: ISPRS 외부비교·TUM2TWIN 케이스) · E=4장 실험(E1 audit결과 … E5 GS-JSO 판정) · G=판정 게이트(G1).

## 2. 판정 기준 (설계서 §6 요약)

- H1 지지: Plane F1 0.10↑ 하락, 경계 오차 1.5배↑, validity rate 10%p↑ 하락 중 2개 이상 (건물 단위 paired 중앙값)
- 기각 시: 방법론 정교화 보류, 프레임 전환 검토 — **판정은 사람이 한다. 에이전트는 수치 산출까지만.**

## 3. 디렉토리 규약

```
phases/p0-audit/
  data/raw/        # 다운로드 원본 — 절대 수정 금지
  data/work/       # 가공 산출물 (점군, footprint, 모델)
  env/             # Dockerfile, conda env, 버전 기록
  scripts/         # 번호 순 실행 스크립트 (01_, 02_, ...)
  runs/<run_id>/   # 실행별 config.yaml + 로그 + 산출물
  docs/            # 설계서, 인벤토리, 진단 리포트
```

> 이 문서의 모든 상대 경로는 `phases/p0-audit/` 기준이다. 에이전트 세션은 반드시 `phases/p0-audit/`에서 시작한다.

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
| ALS 점군 | geodaten.bayern.de 오픈데이터 (LAZ, 실측 ~21 pt/m² · 계획 ~4, CC BY 4.0) | TUM 캠퍼스 타일 |
| LoD2 reference | download1.bayernwolke.de/a/lod2/citygml/ (690_5334, 690_5336) | CityGML 2.0 |
| 보조: Vaihingen | ISPRS UrbanSemLab seafile 직링크 (16 GB, pw: secret) | 영상 표정 + ALS + roof reference |

## 6. 파이프라인 정의

- **Ref-L**: ALS LAZ → 분류 확인 → Roofer(기본값) → CityJSON  [상한 참조]
- **Seq-G**: 영상+포즈 → COLMAP `point_triangulator`(포즈 고정) → OpenMVS densify → LAZ 변환·분류(PDAL) → 동일 Roofer → CityJSON  [audit 대상]
- 파이프라인 2안: City3D (CGAL 5.4–5.6 소스 빌드, CLI는 Qt 불필요)
- 검증 도구: val3dity (입력은 CityJSON만 — CityGML은 citygml-tools로 변환)

## 7. W1 태스크 — 입력 준비·진단 (T0–T6, 각각 별도 세션 · 한 태스크 = 한 커밋)

### T0 — 환경 구축 (도커)
프롬프트: "이 문서를 읽어. T0 작업: ① data/raw, data/work, env, scripts, runs 디렉토리 생성, 레포 루트 .gitignore에 phases/p0-audit/data/와 phases/p0-audit/runs/ 추가. ② 규칙 8·9에 따라 env/docker-compose.p0.yml 작성 — 서비스: colmap(colmap/colmap, GPU), openmvs(env/Dockerfile.openmvs로 빌드), roofer(3dgi/roofer), tools(env/Dockerfile.tools로 빌드: PDAL·GDAL·laspy·val3dity·citygml-tools). 모든 서비스에 data/·runs/ 볼륨 마운트와 사용자 매핑 적용. ③ 스모크 테스트: 각 서비스에서 버전 명령 1개씩 실행해 출력 확인, GPU 서비스는 컨테이너 내 nvidia-smi로 GPU 인식 확인. ④ 완료 기준: 이미지 태그·digest를 env/versions.md에 기록 + 한 커밋(T0)."

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

## 8. W2–W4 — 실행 완료 (G1 판정 대기)

[완료] **W2 audit**: 장면 1(TUM 캠퍼스) × 입력(ALS/DIM) × Roofer × 파라미터(기본/튜닝) → CityJSON + val3dity. City3D는 사전 선언 규칙으로 스코프 제외(대형 복합건물 입력무관 실패, SCIP 솔버). 캐노니컬 run_2(3회 재현 ±0.5pp). **W3 지표·통합**: plane F1·경계·높이·유효율 산출 → `docs/W3_summary.md`. **W4 G1 패키지**: 핵심표·McNemar·부록·그림·출처매핑 → `docs/G1_package/` → 보고서 `G1_P0결과보고_판정요청_v1` 작성.
핵심 결과: 재구성 실패 0(ALS) vs 8(DIM), McNemar p=0.0078, 전처리·튜닝 비회복(≤1건). 연속 지표 F1 −0.095 · 외곽경계 1.20× · 내부 Hausdorff 1.19×(n=35) · 높이 NMAD 1.34× · 유효율 −5.4pp — 모두 §6 임계 경계선 → **부분 지지**. 외곽경계·높이 bias는 동등(footprint·Z보정, 입력 둔감 축). G1 안건: 임계 확정 / 부분지지 vs §8-② 의미품질 프레임 / P2 착수·Vaihingen. 다음: G1 판정 → P1 마무리 → P2.

## 9. G1 보강 태스크 (T7–T14)
> audit(W2–W4) 결과를 사후 진단하는 태스크 — W1 입력 준비와 무관, 입력이 W2–W4 산출물이다.
> **결과 메모(2026-06-15):** T7~T11 실행 완료. ① T7 occlusion 라벨은 무텍스처로 정정(T9: 8건=무텍스처 6·커버리지 1·구조화 1). ② survivor 격차(F1 −0.095)는 DIM 점군 불안정과 상관(T10: r≈0.3)이나, 직접 영상 텍스처는 날카로운 지표로도 무상관(T11: r≈0) → 통합 텍스처 메커니즘 기각. ③ T12: 그림 1.1 통합 도해(4907182 전 과정). **확정 백본:** 점군 중간표현이 두 방식으로 약함 — 무텍스처에서 완전 붕괴(8동·도해), 그 외 일반 노이즈로 경미 저하(survivor, modest) — GS-JSO가 우회. 텍스처는 극단만 설명, 단일 원인 과장 금지. G1 v2 작성 중.

### T7 — 재구성 실패 원인 진단 (8건 복구가능성 세분)

프롬프트: "이 문서(AGENTS.md)를 읽어. T7 작업: DIM에서만 발생한 재구성 실패 8건을 증거부족·구조화부족·관측부족으로 동별 분류하는 scripts/07_failure_diagnosis.py를 작성·실행해 — 'P0 실패가 영상 기반 표면 형성으로 복구 가능한 종류인가'를 수치로 가리는 것(판정은 사람, 분류·관찰까지만). 입력: 실패 8건 ID(docs/G1_package 또는 W3_summary.md), T3 DIM LAZ, T5 footprint GPKG, T2 COLMAP 포즈(EPSG:25832 확인·로컬이면 georef), 대조용 ALS LAZ. 성공 건물(동일 93동)도 같은 지표로 대조군. ① 밀도·구멍: 각 footprint에 DIM building 점(code 6)을 클립해 점밀도·구멍비율·지붕 평면적합 잔차를 대조군·ALS와 대비 — 점 충분+구멍 작은데 실패면 구조화부족. ② 가시성(8동 전체, ①과 한 스크립트에서 연속 실행 — N=8이라 게이트 불필요): T2 포즈로 footprint를 전 영상에 재투영해 뷰 수·시선각 집계 — 뷰 충분이면 증거부족, 뷰 부족·그레이징·가림이면 관측부족(가림은 근사). 분류 임계는 대조군 분포에서 정하고 채택값 공개. 완료 기준: ① 8건 동별 분류표(점밀도·구멍비율·평면잔차·뷰수·시선각·분류·복구가능여부)+대조군 요약, ② 그림 2장(8건 점 클립+ALS 대조 / 분류 건수), ③ docs/W3_failure_diagnosis.md에 표·그림·관찰('k건 복구가능 vs m건 관측부족', 판정 금지, 'E5 확증 필요' 한계)+G1_package에 추가, ④ §4 규칙대로(도커·EPSG·runs·커밋 T7)."

### T8 — 평가 모집단 분포 (W4b)
프롬프트: "이 문서(AGENTS.md)를 읽어. T8 작업: 평가 모집단의 건물 분포를 산출하는 scripts/08_population_profile.py를 작성·실행해 — '통제 93동이 평가에 적합·대표적인가'와 '재구성 실패 8동이 크기·복잡도로 군집하는가'를 수치로 보이는 것(판정 금지, 관찰까지만). 입력: T5 footprint GPKG, LoD2 reference CityGML(높이용), 캐노니컬 건물 status CSV(전체 199 / 통제 93 / 재구성 실패 8 구분; missing_lod22 8동 ID 포함). 건물별 바닥면적·둘레·외곽 꼭짓점 수(형상 복잡도)·높이를 계산하고 세 모집단(199/93/8)으로 분해. 완료 기준: ① 모집단별 분포 요약표(면적·복잡도·높이의 중앙값·IQR), ② 그림 1장(크기–복잡도 산점도, 통제 93·실패 8 강조), ③ '실패 8동의 군집 여부' 한 줄 관찰, docs/W4b_population_profile.md 기록 + G1_package에 추가, ④ §4 규칙대로(EPSG·도커·runs·커밋 T8)."

### T9 — 재구성 실패 8건의 표면 결손 원인 (무텍스처/그림자/커버리지)
프롬프트: "이 문서(AGENTS.md)를 읽어. T9 작업: 재구성 실패 8건의 DIM 결손 원인을 무텍스처·그림자·나디르 커버리지부족·구조화부족으로 가르는 scripts/09_failure_surface_cause.py를 작성·실행해 — T7의 근사 occlusion 라벨이 ALS 성공(8동 전부 holes 0.00=위에서 관측됨)과 모순되므로 'DIM이 비운 진짜 이유'를 가려 8건이 영상 기반(GS-JSO)으로 복구 가능한 종류인지 본다(판정 금지, 분류·관찰까지만). 입력: 실패 8건 ID, 원본 UAV 영상, T2 COLMAP 포즈, T5 footprint GPKG, T3 DIM LAZ, 대조 ALS LAZ, T7 산출. ① 영상 텍스처·조명: 각 footprint를 지붕을 보는 영상들에 투영해 지붕영역 텍스처(국소 gradient/분산)와 밝기·그림자 비율 집계 — 낮은 gradient=무텍스처, 어두움=그림자. ② 뷰 기하: 뷰를 near-nadir(수직~20°)/경사로 분리해 수를 세고 near-nadir 텍스처를 본다 — near-nadir 충분+무텍스처=무텍스처 확정, near-nadir 희박=커버리지. ③ DIM 4057인 42364663은 구조화부족으로 분리. 완료 기준: ① 8동 표(near-nadir/경사 뷰수·텍스처·그림자·DIM밀도·분류·복구가능여부), ② 그림(텍스처 유/무 대표 지붕 crop), ③ docs/W3_failure_surface_cause.md에 표·그림·관찰('k/8 무텍스처=복구가능, m/8 커버리지/그림자')+G1_package 추가, ④ §4 규칙대로(EPSG·도커·runs·커밋 T9)."

### T10 — survivor 구조 격차의 텍스처 기인 여부
프롬프트: "이 문서(AGENTS.md)를 읽어. T10 작업: survivor 71동의 구조 격차(plane F1 −0.095)가 8건 실패와 같은 텍스처 메커니즘에서 오는지 검정하는 scripts/10_survivor_texture_gap.py를 작성·실행해 — '텍스처 낮은 survivor가 F1도 낮은가'를 상관으로 보여 실패(극단)와 survivor 저하(경미)가 단일 메커니즘인지 본다(판정 금지, 관찰까지만). 입력: both_success 71동 ID와 건물별 paired 품질(W3-1: ALS·DIM plane F1·내부 Hausdorff·NMAD), T3 DIM LAZ, 가능하면 원본 영상. ① 각 survivor에 DIM 점을 클립해 텍스처 프록시(구멍비율·국소밀도 변동·평면 RMSE; T7과 동일 정의), 가능하면 지붕 영상 텍스처도. ② 텍스처 프록시 vs [DIM F1, paired ΔF1(ALS−DIM), 내부 Hausdorff] Spearman 상관 + 산점도. ③ survivor를 저/고텍스처로 층화해 ΔF1 비교. 완료 기준: ① 상관 표(r·p), ② 산점도(텍스처 vs ΔF1), ③ 층화 비교표, ④ docs/W3_survivor_texture_gap.md에 '격차가 텍스처와 상관 r=… → 통합 메커니즘 지지/불지지' 한 줄(판정 금지)+G1_package 추가, ⑤ §4 규칙대로(EPSG·도커·runs·커밋 T10)."

### T11 — survivor 텍스처 재검정 (날카로운 지표) + 그림 1.1 재생성
프롬프트: "이 문서(AGENTS.md)를 읽어. T11 작업: ① T10의 거친 중앙값 텍스처 지표를 T9식 날카로운 지표로 바꿔 survivor 71동에 재적용하는 scripts/11_survivor_texture_refine.py를 작성·실행해 — 지붕 near-nadir 영상에서 저텍스처 픽셀 비율(국소 gradient<임계)과 p10 gradient를 건물별로 산출하고, 그 지표 vs [DIM plane F1, paired ΔF1(ALS−DIM), 내부 Hausdorff] Spearman 상관 + 저/고텍스처 층화 ΔF1 비교(T10 표 갱신). 목적: '텍스처 한 메커니즘이 8건 실패와 survivor 격차를 통합 설명하는가'를 직접 영상 텍스처로 검정(판정 금지, 관찰까지만). ② 그림 1.1 재생성: footprint 내부 지붕만 깔끔히 크롭한 near-nadir 컷으로, 텍스처 또렷한 성공 지붕 1동과 무텍스처 실패 지붕 1동(T9 confirmed, 예 4907182)을 나란히 — 창문·외벽 미포함, 텍스처 수치 캡션. 입력: both_success 71 ID·W3-1 paired 품질·T9 산출, 원본 UAV 영상, T2 포즈, T5 footprint, T3 DIM LAZ. 완료 기준: ① 갱신 상관·층화 표, ② 한 줄 관찰('날카로운 텍스처 지표로 survivor ΔF1 상관 r=… → 통합 메커니즘 지지/불지지'), ③ 깨끗한 그림 1.1(textured vs textureless near-nadir 지붕), ④ docs/W3_survivor_texture_refine.md 기록 + G1_package 갱신, ⑤ §4 규칙대로(EPSG·도커·runs·커밋 T11)."

### T12 — 그림 1.1 통합 도해 (한 무텍스처 건물의 전 과정)
프롬프트: "이 문서(AGENTS.md)를 읽어. T12 작업: 무텍스처 실패 건물 4907182 하나로 '왜 영상은 실패하고 LiDAR는 되는가'의 전 과정을 한 장에 보여주는 그림 1.1을 scripts/12_figure_failure_story.py로 만들어 — 4칸: ① near-nadir 원본 영상에 footprint 오버레이(이게 지붕·어느 건물인지 보이게), ② 지붕 내부 텍스처 클로즈업(무텍스처; T11 정의·수치 캡션), ③ DIM 점군 클립(거의 빔), ④ ALS 점군 클립(꽉 참). 대조로 텍스처 있는 survivor 1동(예 4908023)의 동일 4칸을 둘째 행에 둬도 좋음. 입력: T11 산출(crop·building ID), 원본 UAV 영상, T2 포즈, T5 footprint, T3 DIM LAZ, ALS LAZ. 완료 기준: 깨끗한 다칸 PNG(칸별 캡션·수치) + docs/figs 저장 + G1_package 갱신 + §4 규칙대로(커밋 T12)."

### T13 — val3dity 오류 유형 추출
프롬프트: "이 문서(CLAUDE.md)를 읽어. T13 작업: 캐노니컬 run_2의 val3dity 출력을 파싱해 통제 93동의 유효성 오류를 입력별·유형별로 집계하는 scripts/13_validity_error_breakdown.py를 작성·실행해 — 'ALS 무효 5동·DIM 무효 10동이 각각 어떤 기하 오류로 걸렸는가'를 수치로 보이는 것(판정 금지, 집계·관찰까지). 입력: 캐노니컬 val3dity 리포트(ALS·DIM 93동), W3_2c paired status. ① 건물별 val3dity 오류 코드(비폐합/non-watertight, 자기교차/self-intersection, 면 방향 오류, 중복·퇴화 면 등)를 입력별로 추출·분류. ② 오류 유형×입력 집계표(ALS 5·DIM 10 분해)+대표 사례. ③ 품질쌍 제외 14동 중 validity 실패의 입력별 귀속(DIM 무효 8+2, ALS 무효 4 등) 확인. 완료 기준: ① 집계표, ② docs/W3_validity_error_breakdown.md에 표·관찰('DIM 무효 주 유형은 …, ALS는 …')+G1_package 추가, ③ §4 규칙대로(도커·EPSG·runs·커밋 T13)."

### T14 — 정성 그림 2종 (그림3 텍스처→점군 / 결과 점군→모델), 한 스크립트
프롬프트: "이 문서(CLAUDE.md)를 읽어. T14 작업: 정성 그림 두 장을 한 스크립트 scripts/14_qualitative_figures.py에서 만들어·실행해(서버 한 번 실행으로 둘 다 산출). 판정 금지, 시각화만.

[그림 A — 텍스처→점군, 그림3] 대상 4907182(무텍스처 실패). 한 행 4칸: ① ALS 점군 top-view(꽉 참) ② DIM 점군 top-view(거의 빔) ③ 텍스처 확대 1 ④ 텍스처 확대 2. 텍스처 1 = DIM이 비어 있는 영역의 지붕 확대(무텍스처), 텍스처 2 = DIM에 점이 찍힌 영역의 확대(상대적 텍스처 있음). 두 텍스처 칸을 DIM 점군의 해당 위치에 서로 다른 색 박스로 연결해 '텍스처 없는 곳=점 없음, 있는 곳=점 있음'을 같은 건물 안에서 보이게. 원근 사진 위 footprint 오버레이는 쓰지 말 것(건물 높이 시차로 어긋남). 4907182의 DIM 243점이 텍스처 있는 자리에 안 찍혀 텍스처 2가 약하면, 둘째 행에 4908023(텍스처 건물, DIM 점군 참)을 대조로 추가.

[그림 B — 점군→모델, 입력→출력 결과] 대상 3동: ① 4907182(무텍스처 실패) ② 4906969(plane F1 격차, ALS 4면 vs DIM 11면) ③ 4906972(양쪽 성공 대조). 각 건물에 윗줄=입력 점군(ALS | DIM), 아랫줄=출력 LoD2 모델(ALS | DIM | 참조; 지붕면 인스턴스별 색). DIM 미산출(4907182)은 빈 칸+'미산출' 표시. 입력 점군은 건물 특성을 드러내는 뷰로: ① 4907182(무텍스처·빔)=top-view(구멍·비어있음이 핵심). ② 4906969(노이즈)·③ 4906972(대조)=지붕 한 패치를 비스듬히 확대한 3D 클로즈업으로 — 점을 적합 지붕면(또는 참조면)으로부터의 수직 거리로 색칠(면에 붙으면 파랑, 멀어지면 빨강)해 ALS는 얇은 파란 면, DIM은 두껍게 부푼 빨강 섞인 구름으로 거칠기가 한눈에 보이게 한다. 각 칸에 평면 적합 RMS를 숫자로(예: ALS ~2cm vs DIM ~12cm) 표기하고 점밀도는 라벨로 병기. 이 거리-색칠은 거칠기와 이상치를 함께 드러낸다. ③ control은 둘 다 얇고 파랗게 나와 '입력 좋으면 둘 다 깔끔'을 보인다. 노이즈→모델 조각의 인과는 화살표로 단정하지 말고, 노이즈 입력과 조각난 출력을 나란히 둬 독자가 추론하게 한다. 단면(cross-section)은 보조로만(또는 생략).

입력: 캐노니컬 ALS·DIM CityJSON(LoD2.2 Solid, run_2), 참조 LoD2 CityGML, T3 ALS·DIM LAZ, T5 footprint GPKG, T2 영상·COLMAP 포즈. 완료 기준: ① 그림 A·B 두 PNG(G1_package/figs), ② docs/W3_qualitative_compare.md 갱신, ③ §4 규칙대로(EPSG:25832·도커·--user 매핑·runs/versions·커밋 T14)."

## 10. 알려진 함정

- Roofer는 분류된 점군 필요 (ground=2/building=6) — DIM 점군은 T4 없이 투입 불가
- OPF 좌표가 로컬일 수 있음 — T2에서 georeference 확인 필수
- val3dity는 CityGML 직접 입력 불가 (CityJSON 변환 먼저)
- OpenMVS InterfaceCOLMAP은 undistorted PINHOLE 모델만 받음
- ALS(바이에른, TUM 캠퍼스)는 실측 ~21 pt/m²(계획 ~4) — 결과 해석 시 밀도 명기 (Peters 2022의 2 m² 논거는 8 pt/m² 기준 → 본 런 ~21로 상회)
