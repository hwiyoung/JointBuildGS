# P0 조립실패 원인 진단 — 입력(ACMP) 탓인가 Roofer 백엔드 탓인가

> 작성 2026-06-22. 관찰만, **판정 금지(사람=김휘영)**. EPSG:25832 · Docker · P0 동일 04_classify/Roofer config.
> 발단: [P0 완전성 재검증](p0_completeness_reverification.md)에서 생성-실패 64동 중 ACMP로도 미회복 43동이
> 조립실패, 다수가 "평면 찾고도 solid 실패". 그 원인을 입력/백엔드로 가른다.
> 스크립트 `phases/p2-gsjso/scripts/p0c_{assembly_diag,assembly_fig,acmp_forcebuild}*`; 산출 `…/p0c_step2/eval/`.

## 대상 (Part 1)
43 assembly-limited을 ACMP-canonical Roofer reason으로 분해: **missing_lod22 17**(평면≥1·solid 없음) +
no_points 15 + no_planes 11. **17동 전부 ALS-success/lod22=True**(입력무관 후보 0). 점충분(dens≥40) 7 ·
저밀도 10. 단, 여기서 dens는 **SMRF 분류 후 building(6) 밀도** — 아래에서 이게 핵심.

## 백엔드는 무죄 (Part 4, 결정적)
**ALS 점군을 동일 Roofer·동일 config·이 런에서 직접 재실행 → 64/64 LoD2.2 생성**(deep-3: 104586480 planes1→solid,
4907182 planes12→solid, 4908050 planes1→solid). 같은 harness가 ALS로는 64동 전부 솔리드 → **Roofer 백엔드가
한계가 아니다. 실패는 입력측.** (`eval/als_canon_status.csv`)

## ACMP vs ALS 결손 (Part 2/3) — building 클래스(footprint 내, class 6)
| | ACMP | ALS | 관찰 |
|---|---|---|---|
| 노이즈(0.5m 셀 z-std) | 0.04–0.65 m | 0.008–0.12 m | ACMP 지붕 **3–10× 더 두껍/노이즈** |
| 수직 outlier | class6 z가 지붕+20~100 m까지 smear | 없음 | MVS sky/volume 인공물 |
| **grdfrac**(footprint 내 SMRF=ground 비율) | **0.40–0.98** | (해당없음, ALS native class) | **SMRF가 ACMP 지붕을 ground로 오분류** |
| Roofer가 본 building 밀도 | **0–4 pt/m²**(원시 90–370인데) | 10–21 pt/m² | 오분류로 building 굶음 |
| coverage | 0.13–0.66 | 1.00 | ACMP building 패치 |

deep-3 z-분포 확인: 4907182는 SMRF-ground의 **47%가 지붕 높이(±2 m)** → 지붕 절반을 ground로 먹음.
104586480·4908050은 **지붕≈지면(Δ0.1 m, 저기복)** + ACMP 지붕점 희소·수직 smear → ground/roof 분리 불가.

## 결정적 sub-test — SMRF 정책 vs 원시 노이즈
footprint 내부 점을 **전부 building=6으로 강제**(SMRF 지붕-먹기 우회) 후 동일 Roofer:

| 입력 × 분류 (동일 Roofer canonical) | LoD2.2 회복 |
|---|---|
| ALS (native class) | **64/64** |
| ACMP @ SMRF-classified (Step2 canonical) | 17/64 |
| **ACMP @ force-build(지붕 유지)** | **42/64** |

→ **+25동이 "지붕만 안 먹으면" 그대로 조립**(missing_lod22 9·no_points 15·no_planes 1). 점은 **이미 ACMP에 있었고**
SMRF 전처리가 버린 것. deep-3 전부 force-build로 solid. 남는 **~19–22동만 force-build로도 실패 = 진짜 cloud-limited**
(ACMP dens~4·no_planes/no_points; 그중 3동은 loose 파라미터로는 회복). `eval/p0c_forcebuild_breakdown.json`.

## 동별 한 줄 관찰 (판정 금지)
- `104586480`(dens371·1plane→solid없음): 지붕≈지면 저기복 + 수직 smear(z→536) → SMRF 분리실패·plane 1개. 지붕 유지 시 2plane solid. → **분류·노이즈 탓**.
- `4907182`(real 4 m): SMRF가 지붕 47%를 ground로 → building 1236점 → solid 실패. 지붕 유지 시 6plane solid. → **SMRF 오분류 탓**.
- `4908050`(저기복): ACMP 지붕점 159+수직smear, 지붕≈지면 → 분리불가. 지붕 유지 시 solid. → **분류+저기복 탓**.
- 저밀도 12동(dens~4, 예 4908044/4908051/8573617): force-build로도 no_planes/no_points → **원시 cloud 희소·노이즈 탓**(입력 자체 부족).

## 함의 (증거 기반 관찰, 결정은 사람)
- **조립실패는 백엔드(Roofer) 탓 아님** — ALS 64/64. **입력측**이고, 두 갈래:
  1) **전처리(SMRF 분류) artifact ≈ 25/44** — ACMP 지붕점은 있으나 generic SMRF(P0 DIM용)가 노이즈·저기복 지붕을
     ground로 먹어 Roofer를 굶김. footprint-aware 분류로 지붕만 보존하면 17→42 회복. **점군 부재 아님**.
  2) **진짜 cloud 결손 ≈ 19–22/44** — ACMP가 dens~4로 너무 희소·노이즈 → 지붕 유지해도 평면 없음.
- **GS가 충족해야 할 점 사양(관찰):** ① 지붕점이 ground와 분리 가능(지면 위로 충분히·저기복도)·수직 volume smear 없음
  → 분류가 안 먹게; ② 지붕 노이즈 두께 z-std ≲ 0.1 m(ALS급) → 평면 분리; ③ 지붕 커버리지 충분(hole 적음·dens ≫ 4 pt/m²).
  ACMP는 ①(노이즈·smear)·③(저밀도 일부)에서 미달.

## 산출물
- `eval/p0c_assembly_diag.json`(17동 ACMP-vs-ALS 결손) · `eval/acmp_forcebuild_status.csv` · `eval/als_canon_status.csv`
  · `eval/p0c_forcebuild_breakdown.json`(victim/cloud-limited 분리)
- 그림 `docs/figs/tum_transfer/p0c_assembly_recovery.png`(회복 사다리 ACMP-SMRF/force-build/ALS × 버킷)
- 점군 `…/p0c_step2/{als_aoi,acmp_forcebuild}.laz`(EPSG:25832)
