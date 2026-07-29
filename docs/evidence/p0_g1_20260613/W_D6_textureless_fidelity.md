# W_D6 textureless-fidelity — 무텍스처 4동 충실도 (기존 산출 재사용, 관찰만·판정 금지)

> **재사용·재구성/학습 없음, 모델 비교만. 관찰만, 판정 = 김휘영.** 브랜치 `feat/p2-d6-curved`. EPSG:25832. Docker(p0-tools).
> 질문: GS-JSO가 조립한 무텍스처 4동(**42364609·4908050·4908166** 평지붕 + **4907182** 외쪽지붕 2100)이 실제 지붕과 맞나(충실) 아니면 그럴듯한 추정(평평한 슬랩)인가 — "조립됨 ≠ 맞음".
> 출처: `d6_textureless_fidelity.py`. 그림 `docs/figs/W_D6_textureless/`. CSV(gitignore) `analysis_pack_d6/textureless_fidelity.csv`. 재사용: GS=`gs_d4_dense`·ALS=`raw_lidar`·DIM=`raw_dense` 점군 + `ref_rms_{d4_gssem,raw}.csv` + `gen_status.csv` + GML.
> ⚠ **datum**: GS/ALS 점군 = 타원체고(geoid ≈ +48 m), 참조 GML = 정표고(ortho). 높이 비교는 **GS vs ALS(둘 다 타원체, 직접 차)**를 1차 지표로; 참조는 동별 geoid(=ALS−ref) 적용해 병기. mob class6=건물 외피→**지붕 top-envelope**(1 m 셀 최상단 1.5 m)만 측정.

## §1 충실도 표 (GS-JSO D4 vs ALS vs 참조)

| 동 | 유형 | roofType | 참조z(ortho) | GS z(ellip) | ALS z(ellip) | **GS−ALS 높이(m)** | GS 국소경사° | ALS 국소경사° | GS planeRMS | ALS planeRMS | GS RMS→ref | ALS RMS→ref | 면수 G/A/ref | valid G/A | DIM점 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|
| 42364609 | 평 | 1000 | 517.36 | 562.27 | 565.35 | **−3.08** | 0.0 | 57.4† | 0.0 | 0.355 | **0.12** | 0.432 | 1/1/1 | F/T | 48 |
| 4908050 | 평 | 1000 | 516.92 | 562.62 | 564.88 | **−2.25** | 0.1 | 2.6 | 0.046 | 0.015 | 0.131 | 0.071 | 1/1/1 | **T**/T | 108 |
| 4908166 | 평 | 1000 | 516.91 | 562.23 | 564.99 | **−2.76** | 0.0 | 2.4 | 0.009 | 0.065 | 0.032 | 0.112 | 1/1/1 | F/T | 13 |
| **4907182** | **외쪽(shed)** | **2100** | 520.0/520.6 | 565.83 | 568.17 | **−2.34‡** | **0.0** | **28.0‡** | 0.013 | **1.013‡** | 0.141 | **1.73‡** | **1/2/2** | F/T | 502 |

† 42364609 ALS는 희박(327점)이라 국소경사 57.4°는 노이즈 — RMS→ref(GS **0.12** < ALS 0.432)가 깨끗한 형상 지표(GS 평면이 참조에 더 맞음). geoid(ALS−ref) = 47.99·47.96·48.08·47.9 (일관) → **ALS는 참조+geoid(높이 충실), GS는 참조+~45(≈2.3~3.1 m 낮음)**.
‡ **4907182 ALS env 값(28°·planeRMS 1.013·RMS→ref 1.73)은 footprint 가장자리의 ~6 m 높은 블록(parapet/상부구조, env 셀의 19%·293점)에 오염**됨 — **roof-only(z<570) ALS = 21.4°·planeRMS 0.35**로 **참조 외쪽 facet 21.3°와 일치**(클린 pitch ≈ **21°**). 또 4907182의 GS−ALS −2.34 m는 GS가 이 경사·상부구조를 통째 놓쳐 **높이-형상 혼재값**(평 3동의 순수 수직 offset과 달리); 평 3동의 −2.25~−3.08 m는 GS class6 z-span 0.0~0.6 m=깨끗한 수직차로 확인.

## §2 관찰 (판정 금지)

1. **높이: 4동 전부 GS 지붕이 ALS(실측)보다 ~2.3~3.1 m 낮다**(−3.08·−2.25·−2.76·−2.34). geoid가 동별 ~48로 일관하므로 ALS는 참조 높이와 정합(충실)하고 **GS만 체계적으로 낮게(저-편향) 앉는다**. → **높이 충실 0/4.**
2. **형상(평 3동): GS 평면이 충실** — GS 국소경사 ≈0°·planeRMS 0.0~0.046, **RMS→ref 0.03~0.13**(ALS와 동급 또는 그 이하). 평지붕 참조와 일치(면수 1=ref). 즉 **평평한 형상은 맞다**(단 ~2.5 m 낮은 위치에서).
3. **형상(외쪽 4907182): GS가 평평하게 뭉갰다(추정-채움)** — 실제 외쪽지붕 pitch ≈ **21°**(참조 facet 21.3°·ALS roof-only 21.4°/planeRMS 0.35; ALS env 28°/RMS→ref 1.73은 ~6 m 가장자리 블록 19% 오염값 ‡)인데, **GS는 0° 평면**(planeRMS 0.013·RMS→ref 0.141·면 **1**)으로 **경사를 버리고 단일 평슬랩**으로 채움(참조·ALS 면 2). → **비-평 구조 보존 실패.**
4. **영상 증거 희박**(DIM class6 13~502점)에서 GS가 면을 만든 기전 = 소수 MVS 씨앗 + L_sem 다시점 클래스-투영 견인(`sem_detach_geometry=false`, D6-provenance §3) → 깊이-모호한 visual-hull이라 **평슬랩·저-편향**으로 귀결(곡면/경사 미복원). valid-solid도 GS 1/4(4908050)뿐 vs ALS 4/4.

## §3 그림 (docs/figs/W_D6_textureless/)
[GS-JSO(D4) | ALS | 참조 LoD2] × {top, oblique}, 높이색.
- [4907182](figs/W_D6_textureless/4907182.png) — **외쪽 추정-채움 시험**: GS oblique=평슬랩 vs ALS oblique=경사 vs 참조=경사 외쪽 → GS 경사 미보존.
- [42364609](figs/W_D6_textureless/42364609.png) · [4908050](figs/W_D6_textureless/4908050.png) · [4908166](figs/W_D6_textureless/4908166.png) — 평 3동: GS 평슬랩 ≈ ALS ≈ 참조(형상 일치, 위치만 ~2.5 m 낮음).

## §4 한 줄 관찰 (판정 금지)

**"조립됨 ≠ 충실".** GS-JSO 무텍스처 4동은 **footprint 위 평평한 슬랩을 ~2.5 m 낮은(저-편향) 높이에 채운 것**이다: 형상은 **평지붕 3동에서만 우연히 일치(3/4 형상 충실, RMS→ref 0.03~0.13)**하나 **높이는 4동 모두 ~2.3~3.1 m 낮고(0/4 높이 충실)**, **비-평 지붕(4907182 외쪽 ~21° pitch)은 경사를 버리고 평슬랩으로 뭉갰다(1/4 추정-채움, GS 0°·면 1 vs 참조/ALS ~21°·면 2)**. 즉 생성(7/8) 주장은 **조립·footprint·평탄성으로만 약하게 받쳐지고, 높이·비-평 구조 충실로는 받쳐지지 않는다** — D6-provenance(희박 MVS + L_sem visual-hull 견인)·shape-audit와 정합. (충실 판정 = 김휘영.)

## §5 재현 / 출처
- `docker run … jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/d6_textureless_fidelity.py` (read-only 재사용). 점군 GS/ALS/DIM=`mob_eval/{gs_d4_dense,raw_lidar,raw_dense}`. RMS→ref=`ref_rms_{d4_gssem,raw}.csv`(기존). 면수/valid/DIM점=`gen_status.csv`(D6 shape-audit). 참조 z=GML. roof top-envelope·국소경사=`d6_shape_audit` 함수 재사용.
- EPSG:25832 · Docker · 재구성/학습/data 무변경 · 관찰만. G1_package 사본 포함.
