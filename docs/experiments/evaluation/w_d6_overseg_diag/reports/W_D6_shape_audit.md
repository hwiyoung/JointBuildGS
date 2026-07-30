# W_D6 shape audit — 11 작업동 형상 눈+측정 검증 (P0 재사용, 관찰만·판정 금지)

> **관찰만, 판정 = 김휘영.** 브랜치 `feat/p2-d6-curved`. EPSG:25832. Docker(p0-tools). **학습·재구성 없음 — P0 기존 산출 재사용·렌더/집계만.**
> 배경: 지붕유형 라벨(평/곡면/복합)이 측정이 아닌 눈대중 가정이었고 survey에서 참조 roofType과 광범위 불일치가 드러남. 11 작업동 실제 형상을 눈+측정으로 바로잡고, 특히 **4906969가 곡면인지 단차 평지붕인지 ALS로 확정**한다.
> 출처: `d6_shape_audit.py`(패널·측정·4906969 y-slice) · `d6_genstatus.py`(생성표). 그림 `docs/figs/W_D6_shape/`. CSV(gitignore) `analysis_pack_d6/{shape_audit,gen_status}.csv`.
> 입력(재사용): 참조 LoD2 `data/raw/lod2/*.gml` · 점군 `mob_eval/{raw_lidar=ALS, raw_dense=DIM, gs_d4_dense=GS}/<bid>_orig_classified.las` · 정확도 `ref_rms_{raw,d4_gssem}.csv`(RMS→ref) · 생성 `eval_{d4_gssem,v6_raw}.json`.

## §0 방법 · 데이터 주의 (관찰)

- **패널**: 동마다 `[참조 LoD2(지붕면별 색) | ALS | DIM | GS] × {top, oblique}`, 점군 높이색. 캡션에 roofType·ref/ALS/DIM/GS 면수·RMS→ref·측정형상.
- **측정 형상**(ALS): mob class6 = **건물 전체 외피(지붕+벽)**라 그대로는 평면적합 무의미 → **지붕 top-envelope**(1 m 셀 최상단 1.5 m 밴드)만 추출 후 국소(2 m 셀) 경사·z-레벨·곡률(quadric vs plane) 측정. ⚠ 단차 riser·반원 가장자리가 envelope에 남아 국소경사를 부풀릴 수 있어 **측정 verdict는 보조**, 형상 확정은 **참조기하 + 눈 + (4906969) y-slice**.
- **datum**: ALS/DIM/GS LAS = **타원체고**(ortho 참조 GML 대비 ≈ +49 m geoid). z 비교는 동일 클라우드 내부에서만(절대 datum 혼용 금지).
- **권위 형상** = 참조 LoD2 기하(GML RoofSurface 수·z-레벨·경사) — 단순화 모델이나 깨끗(벽오염·datum 무관). 눈 검증이 2동(4906969·4906972)에서 참조기하와 일치 확인.

## §1 형상 패널 (docs/figs/W_D6_shape/)

우선 5동(재구성됨): [4906969](figs/W_D6_shape/4906969.png) · [4906972](figs/W_D6_shape/4906972.png) · [42364659](figs/W_D6_shape/42364659.png) · [42364663](figs/W_D6_shape/42364663.png) · [4908023](figs/W_D6_shape/4908023.png).
나머지 6동(R, raw-MVS 생성실패 → GS-JSO 5/6 회복; §4): [4907182](figs/W_D6_shape/4907182.png) · [4907510](figs/W_D6_shape/4907510.png) · [42364609](figs/W_D6_shape/42364609.png) · [4908050](figs/W_D6_shape/4908050.png) · [4908166](figs/W_D6_shape/4908166.png) · [4908176](figs/W_D6_shape/4908176.png).
+ [**4906969 ALS y-slice**](figs/W_D6_shape/4906969_yslice.png) (곡면 vs 단차 관찰).

## §2 라벨 교정표 — 관측 vs 참조 roofType vs 실제 형상 (눈+측정)

| 동 | 관측 라벨(P2) | 참조 roofType | 참조 기하 형상(권위) | ALS 눈/측정 | 형상 관측(정정) |
|---|---|---|---|---|---|
| **4906969** | **곡면 curved** | 1000 Flach | **단차 평지붕 3레벨**(523.7/526.7/530.2) | **단차/계단 평지붕**(반원 footprint; y-slice step 0.54 ≪ arch 1.21) | **✗ 곡면 아님 → 단차 평지붕** |
| **4906972** | **평지붕 flat** | 3100 Satteldach | **박공 3면**(경사 24°/35°/35°) | **박공(경사)**(패널: 능선+양 슬로프) | **✗ 평 아님 → 박공** |
| **42364659** | **복합 composite** | 1000 Flach | **평지붕 2레벨**(516.5/517.2, sep 0.7 m) | ALS 희박(265점) 판정난; 참조=평 | **✗ 복합 아님 → 평**(‘복합’=재구성 과분할, 형상 아님) |
| **42364663** | **복합 composite** | 1000 Flach | **평지붕 1레벨**(530.5, 긴 협소동) | 참조=평; ALS class6 벽 우세(긴 협소) | **✗ 복합 아님 → 평(긴 협소)** |
| 4908023 | 대조 control | 1000 Flach | 평지붕 1레벨(518.9) | 평지붕 | ✓ 평(대조 적절) |
| 4907182 | (R) | **2100 Pultdach** | 경사 단일면(외쪽지붕) | — (무텍스처 생성실패) | (R) 경사 외쪽 |
| 4907510 | (R) | 1000 Flach | 평지붕 1레벨 | — | (R) 평 |
| 42364609 | (R) | 1000 Flach | 평지붕 1레벨 | — | (R, 무텍스처) 평 |
| 4908050 | (R) | 1000 Flach | 평지붕 1레벨 | — | (R, 무텍스처) 평 |
| 4908166 | (R) | 1000 Flach | 평지붕 1레벨 | — | (R, 무텍스처) 평 |
| 4908176 | (R) | 1000 Flach | 평지붕 1레벨 | — | (R, 무텍스처) 평 |

**관찰 (판정 금지):**
1. **형상 관측 라벨은 대부분 틀림.** 형상이 의미 있는 재구성 5동 중 **4동이 오라벨**(4906969·4906972·42364659·42364663); 4908023(대조=평)만 정확. **곡면(curved)은 11동에 0동.**
2. **‘곡면’·‘복합’ 라벨은 형상이 아니라 재구성 거동에서 왔다** — 4906969=반원 footprint+단차 평지붕(곡면 아님), 42364659/42364663=평지붕인데 GS/DIM 과분할로 ‘복합’이라 부름. 참조 roofType과 일치(survey §0 재확인).

## §3 4906969 관찰 — 둥근 호인가 단차 평지붕인가

- **참조**: 3개 **수평** RoofSurface가 **서로 다른 높이**(523.7·526.7·530.2 m) = 동심 단차(계단식) 평지붕. footprint=반원(apse). 패널 oblique에서 3개 평슬랩 확인.
- **ALS y-slice**(지붕 top-profile, 클라우드 자체 datum): **3-레벨 계단 모델 RMS 0.54 m ≪ 포물선(호) RMS 1.21 m** → top-profile이 구간별 평평(≈572.2/575.7/578.8)하고 사이에 점프 = **단차 평지붕**. 매끈한 호 아님.
- **관찰**: 4906969의 "곡면"은 **footprint(평면도)의 곡선**이고 **지붕면은 단차 평지붕**이다. 곡면 지붕 아님. (D5/D6 ‘곡면’ 라벨은 측정 미확인 가정이었음.)
- 함의(관찰만): D6 step0의 곡면 4906969 과분할(GS 14 vs LiDAR 5)은 **곡면 지붕** 때문이 아니라 **반원 가장자리 + 단차 + GS 조밀 샘플링**의 Roofer 다중평면 절단이다. 레버·판정 = 김휘영.

## §4 생성 상태표 (캐노니컬 mob 하네스, gssem 재평가; 재계산 target-only)

"assembled" = **대상 동이 지붕모델을 얻음**(target-only RoofSurface ≥ 1; Roofer `roofer_ok`은 이웃 출력 포함이라 미사용). valid-solid = eval val3dity(**클립 단위** — 이웃 포함 조합 cityjson; assembled일 때만 의미). 면수=현 디스크 재계산(`d5_target_facets.csv`는 requal 이전이라 stale).

| 동 | set | ref | DIM(raw) asm·면·valid | GS-JSO(D4) asm·면·valid | ALS(LiDAR) asm·면 | DIM class6점 | 무텍스처 |
|---|---|---:|---|---|---|---:|:--:|
| 4906969 | Q | 3 | Y·17·invalid | Y·14·invalid | Y·5 | 43896 | |
| 4906972 | Q | 3 | Y·3·valid | Y·3·invalid | Y·3 | 154558 | |
| 4908023 | Q | 1 | Y·1·valid | Y·2·valid | Y·1 | 7018 | |
| 42364659 | R | 2 | **N**·0 | **Y·6** | N·0 | 2870 | |
| 42364663 | R | 1 | **N**·0 | **Y·1** | Y·1 | 96621 | |
| 4907182 | R | 2 | **N**·0 | **Y·1** | Y·2 | 502 | **무텍스처** |
| 4907510 | R | 1 | **N**·0 | **Y·6** | Y·4 | 3084 | |
| 42364609 | R | 1 | **N**·0 | **Y·1** | Y·1 | 48 | **무텍스처** |
| 4908050 | R | 1 | **N**·0 | **Y·1** | Y·1 | 108 | **무텍스처** |
| 4908166 | R | 1 | **N**·0 | **Y·1** | Y·1 | 13 | **무텍스처** |
| 4908176 | R | 1 | **N**·0 | **N·0** | Y·1 | 260 | **무텍스처** |

**8 생성표적(R): raw(DIM) 0/8 → GS-JSO 7/8 → ALS 7/8.**
- **관찰**: raw MVS는 8동 전부 미조립(0/8). **GS-JSO가 7/8 회복**(ALS 7/8과 동수, 단 실패 동이 다름 — GS는 4908176만, ALS는 42364659만 미조립). 무텍스처 5동(42364609·4908050·4908166·4907182·4908176)은 영상 단독으로는 모두 증거 부재(DIM 13~502점 = raw-MVS 범위 밖)이나 **GS-JSO가 그중 4동을 조립**(4908176만 미조립). 이 회복은 D-수트 설계상 LoD2-band prior/seeding에 의한 것으로 보이나(본 audit는 조립여부·점수만 측정, 인과는 D-수트 맥락) 관찰상 영상 단독 불가 영역의 생성이다.
- **valid-solid 주의**: GS 조립분 다수 invalid(클립 단위) = 위상 잔여(D-수트 기존 관찰과 정합); 면수 0인 동의 valid는 이웃에서 온 값이라 무의미.

## §5 하네스 정합 — survey(w3_2b) vs 캐노니컬(mob) (관찰)

survey(`W_D6_survey`)는 **P0 모집단 하네스 w3_2b**(전-장면 점군 1회 Roofer, P0-SMRF 분류), 본 audit·생성표·D-수트는 **mob 하네스**(`tum_mob_eval`: 동별 bbox 클립 + gssem/smrf 분류, arm별 Roofer). 같은 동도 면수가 다르다:

| 4906969 | ALS | DIM | GS |
|---|---:|---:|---:|
| survey (w3_2b) | 4 | 11 | – |
| 캐노니컬 (mob) | 5 | 17 | 14 |

→ **차이 원인 = 하네스** (분류 P0-SMRF vs gssem · 클립 범위 · MVS 클라우드 · arm별 Roofer 실행 인스턴스; 면수 정의는 양쪽 target-only로 동일하므로 차이 원인 아님). 둘 다 P0 유래지만 호환 아님 — **수치는 하네스 내에서만 비교**. 정성 결론(과분할 광범위·LiDAR도·GS 회복 7/8)은 양 하네스에서 일관.

## §6 한 줄 관찰 (판정 금지)

**11 작업동 중 ‘곡면’ 지붕은 없다 — 형상 라벨은 측정 미확인 가정이었고 재구성 5동 중 4동이 오라벨이다.** 4906969(‘곡면’)은 **반원 footprint 위 단차 평지붕**(y-slice 계단 RMS 0.54 ≪ 호 1.21·참조 3 수평레벨), 4906972(‘평’)은 박공, 42364659·42364663(‘복합’)은 평지붕이며 ‘복합’은 재구성 과분할 거동이다. 생성에서는 raw 0/8 → **GS-JSO 7/8**(무텍스처 4동 포함, prior로 회복) → ALS 7/8. (형상·레버·판정 = 김휘영.)

## §7 재현 / 출처
- `docker run … jointbuildgs-p0-tools:t0 python3 scripts/evidence_and_attributes/p2_gsjso/d6_shape_audit.py` (패널·측정·y-slice) + `d6_genstatus.py` (생성표). read-only 재사용; data/raw·재구성 무변경.
- 면수 target-only = `d5_target_facets` 로직 현 디스크 재계산(stale CSV 대신). 참조 형상 = GML RoofSurface z-레벨·경사. 생성 valid = eval val3dity(클립). RMS→ref = `ref_rms_*.csv`. EPSG:25832 · Docker · 관찰만. G1_package 사본 포함.
