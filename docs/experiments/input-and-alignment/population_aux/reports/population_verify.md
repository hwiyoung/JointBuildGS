# population_verify — P0 모집단 재검증 (A) + 서브클래스 원재료 추출 (B) (읽기전용·판정 금지)

> **박사연구 GS-JSO · 모집단 검증 v2.** 브랜치 `feat/p2-structure-learn`. EPSG:25832. Docker(`--user`). **읽기전용·재구성 없음** — canonical P0 산출 재사용. 관찰만, **서브클래스 라벨 안 만듦(규칙=김휘영)**. 커밋 `population-verify-aux`.
> 재현 `population_aux.py`. 산출 `population_aux.csv`(199동, building_id 조인) · 본 문서(A 대조표·결측 요약).

## A. 검증 — building_reconstruction_status.csv 재집계

**A1 provenance**: `building_reconstruction_status.csv` = **canonical Roofer-default 런** `w2_1_roofer_default_20260612_152729` (**commit d61ff0f**, roofer **1.0.0**, config.yaml 동봉). 398행 = **199동 × 2입력(ALS·DIM)**. → **canonical 확인됨**(재생성 불요).

**A2 has_lod22 교차표 (199동, ALS × DIM):**

| 축 | 정의 | **raw w2_1(canonical)** | **W3_2c closeout** | 업로드 CSV |
|---|---|---:|---:|---:|
| 품질(quality) | ALS✓ ∧ DIM✓ | **114** | 113 | 114 |
| 생성(generation) | ALS✓ ∧ DIM✗ | **64** | 65 | 64 |
| ALS-실패 | ALS✗ | **21** | 21 | 21 |
| 합 | | 199 | 199 | 199 |

→ **업로드 114/64/21 = raw w2_1 canonical과 정확히 일치**(has_lod22 기준, commit d61ff0f). **검증 통과.**

**⚠ 단일 불일치 (canonical 산물 2종이 1동에서 엇갈림)**: **W3_2c closeout(commit 380d2f6)은 113/65/21** — **DEBY_LOD2_42364663** 1동이 다름:
- **w2_1**: DIM status=success, has_lod22=True, rf_roof_planes=3, **rf_rmse_lod22=12.05 m**(거대 오차), val3dity=True → "생성 성공"으로 셈(품질 114에 포함).
- **W3_2c**: DIM status=failure, reason=**missing_lod22_geometry**, has_lod22=False, dim_failure_bucket=**roof_matching_assembly_failure** → 12m-RMS 모델을 "조립 실패"로 재분류(생성 65에 포함).
- **해석(판정 금지)**: 42364663 DIM은 **Roofer 솔리드는 났으나 RMS 12m(사실상 쓰레기)** — "has_lod22 있음"(w2_1)이냐 "품질 미달=실패"(W3_2c)냐의 **정의 차이**. 품질/생성 경계가 이 1동에 걸림.

**reason 분해:**
- 생성축(ALS✓∧DIM✗) DIM reason: **no_points 46 · missing_lod22 16(w2_1)/17(W3_2c, +42364663) · no_planes 2**.
- ALS-실패 21 reason: **missing_roofer_output 20 · pointcloud_unusable 1**.
- (전체 status 카운트 w2_1: success 265·no_points 46·val3dity_invalid 28·missing_roofer_output 40·missing_lod22 16·no_planes 2·pointcloud_unusable 1, 199×2 기준.)

**부가 모집단 수(참고)**: `coverage_control_population=yes` **93동**(통제비교 부분집합, both-success 114의 하위) · survivor-texture(T10/T11) **71동**(추가 품질쌍 하위). → **114(both) ⊃ 93(control) ⊃ 71(survivor)**.

## B. 원재료 추출 — population_aux.csv (199동, 라벨 없음)

**컬럼별 커버리지(비결측/199)** — 기존 산출 재사용, 부분집합 결측은 그대로 보고:

| 컬럼 | 비결측 | 소스 |
|---|---:|---|
| als_has_lod22 · dim_has_lod22 | **199** | w2_1 canonical(114/64/21) |
| footprint_area_m2 · n_exterior_vertices | **199** | footprints_aoi.geojson |
| n_views_nadir · n_views_oblique | 125 | T11(71)+W4c(46) |
| n_views_total | 79 | T7 view_count |
| median_incidence_deg | 87 | T7·T11·W4c(입사각; 교차각 아님) |
| roof_area_covered_frac | 79 | T7 in-frame sample frac(근사) |
| roof_lowtex_frac | 70 | T11 sharp_low_texture_pixel_ratio |
| roof_grad_p10 | 86 | T9/T11/W4c gradient p10 |
| occlusion_frac_approx | 79 | T7 occlusion_risk_view_fraction |
| sparse/acmp/gs_{sparse,dense,acmp}_has_lod22 | 68 | v6 table(11)+gen_8way(64) |
| **median_intersection_deg** | **0** | **없음 — 뷰-쌍 교차각은 기존 산출 미존재(재투영 신규계산 필요)** |

**결측·불일치 요약(판정 금지):**
1. **has_lod22·footprint = 199 전동 완비.** 나머지 관측가능성/텍스처/arm 컬럼은 **P0-audit 부분집합(~68~125동)만** — 재사용 원칙상 그 밖 ~120동(대부분 both-success '품질' 동)은 결측.
2. **median_intersection_deg(뷰-쌍 교차각) = 0/199** — 기존 산출에 없음(T7/T9/T11은 입사각 median_incidence만). 채우려면 **199 footprint를 등록영상에 재투영하는 신규 계산**(07/09 로직 확장, 이미지 분석·재구성 아님, ~1~2h). median_incidence_deg를 근사 병기.
3. **roof_area_covered_frac = in-frame 샘플 비율 근사**(엄밀 지붕면적 커버리지 아님). occlusion = T7 근사값.
4. **arm has_lod22(sparse/acmp/GS)**: 성공 모집단은 이 arm들 미평가라 68동만 사실값 — 나머지 결측(해당 arm 미실행, 재구성 필요).
5. ⚠ **arm 상태 출처 혼재**: als/dim=w2_1 canonical, GS/sparse/acmp=v6-matched(11)+gen-8way(64) — **설정·하네스 다름**(사실값이나 동일-설정 아님, [[W_report_evidence]] §5 공정성과 동일 caveat).

## 종합 (판정 금지)
- **(A) 업로드 114/64/21 = canonical w2_1 재현 확인**; 단 **W3_2c closeout는 113/65**(42364663 DIM을 12m-RMS→실패 재분류) — 경계 1동은 "has_lod22 유무 vs 품질 미달" 정의 문제(판정=김휘영).
- **(B) population_aux.csv(199) = has_lod22·footprint 전동 + 관측가능성/텍스처/arm은 audit 부분집합(~68~125)** 재사용 추출; **median_intersection_deg는 신규 재투영 필요**(미실시). 서브클래스 규칙은 김휘영이 이 원재료로 고정.

> 재현: `docker run … jointbuildgs-p0-tools:t0 python3 scripts/evidence_and_attributes/p2_gsjso/population_aux.py`. 데이터 재사용·재구성 없음. CSV=`overseg_lever/population_aux.csv`(사본 `docs/population_aux.csv`).
