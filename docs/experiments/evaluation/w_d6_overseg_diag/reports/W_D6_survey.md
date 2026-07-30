# W_D6 survey — 곡면 건물 전수 조사 (P0 재사용, 관찰만·판정 금지)

> **관찰만, 판정 = 김휘영.** 브랜치 `feat/p2-d6-curved`. EPSG:25832. Docker(p0-tools). **재구성 재실행 없음 — P0 기존 산출 재사용·집계만.**
> 모집단 = P0 통제(coverage-control) **93동**. 비교 = 참조 LoD2(CityGML) · LiDAR(ALS) · DIM(영상 MVS), Roofer 동일 하네스(P0 w3_2b run_2).
> 출처: `d6_survey.py`. 산출(gitignore): `results/tum_transfer/mob/analysis_pack_d6/{survey_per_building,survey_by_type}.csv`. 그림 `docs/figs/W_D6/survey_overseg.png`.
> 입력(재사용): 93셋 `w3_2c_canonical_closeout_.../W3_2c_canonical_paired_status.csv`(coverage_control_population=yes) · ALS/DIM CityJSON `w3_2b_roofer_repeatability_.../cityjson/run_2/{als,dim}_default.city.json` · 참조 roofType/면수 `data/raw/lod2/*.gml` · 정확도 `W3_2c_canonical_roofer_quality_metrics.csv`(height NMAD·boundary chamfer; 71 both_success).

## §0 전제 점검 — 참조 roofType는 관찰 라벨과 불일치 (중요; docs/issues.md 기록)

지붕 유형은 권위 속성 **CityGML `<bldg:roofType>`**(AdV Dachform 코드)로 분류한다. **그러나 이 속성(및 평면-only LoD2 기하)은 우리가 써온 관찰 라벨과 어긋난다.** 알려진 3동 검증:

| 동 | 관찰 라벨(D4/D5) | **참조 roofType** | 참조 기하 | class4 | ref/ALS/DIM 면수 |
|---|---|---|---|---|---|
| 4906972 | 평지붕(flat) | **3100 Satteldach(박공)** | 3면·경사 24°/35°/35° | sloped | 3 / 3 / 3 |
| 4906969 | 곡면(curved) | **1000 Flachdach(평)** | 3면·전부 수평 0° | flat | 3 / 4 / 11 |
| 42364659 | 복합(composite) | **1000 Flachdach(평)** | 2면·전부 수평 | flat | 2 / 4 / 미산출 |

→ **3동 모두 관찰 라벨과 불일치**(곡면 4906969 = 참조상 평지붕; 평지붕 4906972 = 참조상 박공). 기하 폴백도 동일(LoD2는 전부 평면 facet → 곡면 surface 없음; 4906969는 3 수평면 = 평으로 분류됨). 즉 **참조 LoD2는 4906969의 실제 곡률을 담지 않는다**(coarse 단순화). 게다가 **통제 93동 중 참조-곡면(3700 Bogendach)은 0동**(전체 690_53xx 타일쌍에도 6동뿐, 93 통제셋엔 없음).

**판단(블로커 아님)**: 데이터·산출은 모두 존재하므로 STOP하지 않고, **권위 속성으로 분류 + 과분할은 동별 분포로 답한다**(추정 없이). "곡면군 동별 표"는 참조-곡면이 0동이라 **경험적 과분할군(상위 과분할 동)**으로 대체하고 4906969를 명시 강조한다. 상세 = `phases/p2-gsjso/docs/issues.md`.

> ✔ **P0 사전 정합**: P0 T14 지시(`phases/p0-audit/CLAUDE.md` §9)는 이미 4906969를 *"plane F1 격차, ALS 4면 vs DIM 11면, 노이즈"*로, 4906972를 *"양쪽 성공 대조"*, 4907182를 *"무텍스처 실패"*로 규정했다 — 본 survey 수치(4906969 ALS 4·DIM 11)와 정확히 일치하며, **"곡면"은 P2(D4/D5) 단계 관찰 라벨**이고 P0/참조는 4906969를 곡면으로 본 적이 없음을 재확인.

## §1 지붕 유형 분류 — 코드→4분류 매핑 + 분포

코드→{평지붕·경사평면·곡면·복합·기타} 매핑(공개). "경사평면"=평면 facet로 구성된 경사지붕(박공/모임/...). "곡면"=호/돔(Bogendach 3700).

| AdV code | 이름 | class4 | **n in 93** | (전체 타일쌍 n) |
|---|---|---|---:|---:|
| 1000 | Flachdach(평) | 평지붕 flat | **40** | 5214 |
| 2100 | Pultdach(외쪽) | 경사평면 sloped | 3 | 1107 |
| 2200 | versetztes Pult | 경사평면 sloped | 0 | 5 |
| 3100 | Satteldach(박공) | 경사평면 sloped | **34** | 4162 |
| 3200 | Walmdach(모임) | 경사평면 sloped | 10 | 1043 |
| 3300 | Krüppelwalm | 경사평면 sloped | 0 | 23 |
| 3400 | Mansarddach | 경사평면 sloped | 0 | 249 |
| 3500 | Zeltdach(천막) | 경사평면 sloped | 1 | 67 |
| 4000 | asym. Sattel | 경사평면 sloped | 0 | 8 |
| **3700** | **Bogendach(호)** | **곡면 curved** | **0** | **6** |
| 3600 | Sheddach(톱니) | 복합 composite | 0 | 12 |
| 3900 | Mischform(혼합) | 복합 composite | 1 | 21 |
| 9999 | Sonstiges(기타) | 기타 other | 4 | 132 |

**유형별 건물 수(93)**: 평지붕 **40** · 경사평면 **48** · **곡면 0** · 복합 1 · 기타 4.
→ **곡면(참조) 지붕은 통제셋에 없다.** "곡면 지붕 유형 전반"은 참조로는 평가 불가(0 표본).

## §2 과분할·정확도 표 (93, target-only; P0 재사용)

면수 = target-only(CityObject id == full or `full-N`). 과분할 = (DIM−LiDAR)·(DIM−ref)·(DIM/ref). 미LoD2.2(면수 0)=미산출. 정확도 = height NMAD(수직, m)·boundary chamfer(수평, m), 71 both_success(NMAD 정의 69동·chamfer 71동).

### 유형별 요약
| class4 | n | DIM 재구성 | DIM>ref | ALS>ref | med(DIM−ref) | med(ALS−ref) | med(DIM−ALS) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 평지붕 flat | 40 | 33 | 21 | 22 | +1 | +1 | 0 |
| 경사평면 sloped | 48 | 47 | 32 | 29 | +2 | +1 | 0 |
| 곡면 curved | 0 | – | – | – | – | – | – |
| 복합 composite | 1 | 1 | 1 | 0 | +38 | 0 | +38 |
| 기타 other | 4 | 4 | 3 | 3 | +10 | +8 | +1.5 |
| **전체** | 93 | 85 | **57/85** | **54/92** | **+2** | **+1** | **0** |

### 곡면(4906969) + 경험적 과분할 상위군 (참조-곡면 0동 대체)
> GS(제안방법) 면수는 GS 보유 동 4906969만 병기 — **단 mob 하네스(D5)** 산출이라 위 ALS/DIM(w3_2b 하네스)과 직접 비교 불가(별도 표기).

| 동 | 참조 roofType | class4 | ref | ALS | DIM | DIM−ref | DIM−ALS | dim NMAD(m) | GS(mob) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| **4906969** (관찰=곡면) | 1000 Flach | flat | 3 | **4** | **11** | +8 | +7 | 0.149 (ALS 0.036) | **13/8** (mob ref3·LiD5·DIM17) |
| 108580336 | 3200 Walm | sloped | 14 | 28 | 56 | +42 | +28 | 0.086 | – |
| 4906968 | 3900 Mischform | composite | 8 | 8 | 46 | +38 | +38 | 0.117 | – |
| 4959326 | 3100 Sattel | sloped | 19 | 40 | 52 | +33 | +12 | – | – |
| 4906965 | 3100 Sattel | sloped | 18 | 54 | 47 | +29 | −7 | – | – |
| 4906975 | 1000 Flach | flat | 6 | 14 | 32 | +26 | +18 | – | – |
| 4907519 | 9999 Sonstiges | other | 11 | 17 | 37 | +26 | +20 | 0.038 | – |
| 60042 | 1000 Flach | flat | 20 | 23 | 44 | +24 | +21 | – | – |
| 4907183 | 3100 Sattel | sloped | 2 | 7 | 18 | +16 | +11 | 0.059 | – |

(전체 동별 = `survey_per_building.csv`. 4906969 **DIM−ref 과분할 순위 = 20/85**(중상위, 최상위 아님).)

**관찰 (판정 금지):**
1. **과분할은 4906969 전용 아님 — 광범위.** DIM 재구성 85동 중 **57동(67%)이 DIM>ref**; 4906969는 **20/85위**(중상위). 상위 과분할군은 모임(Walm)·혼합(Misch)·박공(Sattel)·평(Flach)·기타로 **유형 무관**.
2. **LiDAR(ALS)도 과분할.** **54/92동 ALS>ref**(med ALS−ref +1), 일부 ALS 면수 ≫ ref(예 4906965 ALS 54 vs ref 18). 즉 과분할은 영상(DIM) 전용 아님 — 조밀 점군에 Roofer가 평면을 다수 검출.
3. **참조 대비 과분할 = (영상·LiDAR 공통 성분) + (DIM 고유 초과).** 둘 다 coarse LoD2 참조보다 면수가 많다(공통). **중앙값 DIM−ALS=0은 평지붕 facet=1 동시성공 32동의 동률에 가린 값** — 불일치 52동만 보면 **DIM>ALS 37 vs ALS>DIM 15**(평균 DIM−ALS +2.79; 4906969 제외 36 vs 15, 이상치 trim 34 vs 15)로 **영상(DIM)이 LiDAR보다 모집단 전반에서 더 쪼갠다.** 4906969(DIM 11≫ALS 4)는 그 분포의 **꼬리**이지 고립 사례가 아님.
4. **4906972(관찰=평지붕)는 ref=ALS=DIM=3**으로 완전 정합(참조상 박공) — 관찰 라벨이 부정확했음을 시사.

## §3 그림
- [survey_overseg.png](figs/W_D6/survey_overseg.png) — (좌) ALS vs DIM target-only 면수 산점(84 both, 대각선=DIM=ALS; 4906969 강조): 다수 동이 대각선 위/주변에 분산, 둘 다 고-면수 도달 → 과분할은 광범위·LiDAR도; (우) 유형별 med(facets−ref): 평·경사 모두 ALS·DIM > ref.

## §4 한 줄 관찰 (판정 금지)

**곡면 과분할은 4906969만의 고립 문제가 아니다 — 참조 대비 과분할은 유형 무관으로 광범위(LiDAR 포함)하고, 그 위에 영상(DIM)이 LiDAR보다 모집단 전반에서 더 과분할한다. 단 "곡면 지붕 유형 전반"인지는 통제 93동에 참조-곡면 0동이라 검증 불가.** ① 통제 93동에 참조-곡면(Bogendach)은 0동이고 4906969 자신도 참조상 평지붕(1000)이라 "곡면 유형" 모집단 검증 불가(없음 아님 — 표본 0); ② DIM 과분할은 85동 중 57동(4906969는 20/85위)으로 광범위·유형무관; ③ ALS(LiDAR)도 54/92동 과분할 → coarse LoD2 참조 대비 면수 초과는 **영상·LiDAR 공통 성분**; ④ **그 위에 영상(DIM)은 LiDAR보다 모집단 전반에서 더 과분할**(불일치 52동 DIM>ALS 37 vs 15, 평균 +2.79; 4906969 제외 36 vs 15) — 4906969(DIM 11·GS 13 ≫ ALS/LiDAR 4~5)는 이 **영상-고유 추세의 꼬리**(=D6 step0가 분해한 입력측 GS 밀도×표면 성분)이지 고립 사례 아님. (레버·판정 = 김휘영.)

## §5 재현 / 출처
- 실행: `docker run … jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/d6_survey.py` (read-only 재사용; 재구성·data/raw 무변경).
- 면수 target-only = `d5_target_facets` 로직. 참조 면수 = GML RoofSurface 수(11 mob에서 `baselines.json`과 일치 검증). 정확도 = W3_2c height NMAD·chamfer 재사용.
- GS(4906969) = `d5_target_facets.csv`(mob 하네스, 별도 표기). G1_package 추가용. EPSG:25832 · Docker · 관찰만.
