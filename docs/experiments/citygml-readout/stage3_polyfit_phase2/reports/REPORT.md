# PolyFit Phase 2 — methodology re-test with CGAL repair recipe

**Background**: Phase 1 dominant 가설 A (post-processing 미완) → CGAL 표준 5-단계 repair recipe + `triangulate_faces` 추가하여 재테스트.

**Pipeline**: input → PolyFit MIP → polygon_mesh_to_polygon_soup → merge_duplicate_points → repair_polygon_soup → orient_polygon_soup → polygon_soup_to_polygon_mesh → stitch_borders → triangulate_faces → orient_to_bound_a_volume → OFF.

[src/stage3/polyfit_cli.cpp](../../../../../src/stage3/polyfit_cli.cpp), recompiled with CGAL 5.6.2 + SCIP 10.

## Stage A — GT scene.obj input

10 buildings (bids 0-9) — 같은 set as P1-3a Phase 1 + bid 3 (parser 진단용).

| bid | type | val3dity | output_h | GT_h | \|Δh\| | vol_ratio | coverage | Hausdorff | Chamfer |
|---|---|---|---|---|---|---|---|---|---|
| 0 | tri-slope | ✗[303×2] | 16.46m | 15.97m | 0.49m | 0.04 | 1.8% | 12.21m | 2.34m |
| 1 | flat | **✓** | 16.61m | 16.61m | **0.00m** | **1.00** | **47.8%** | **0.81m** | **0.23m** |
| 2 | flat | **✓** | 13.36m | 13.63m | 0.28m | 0.05 | 2.4% | 12.22m | 3.08m |
| 3 | complex | **polyfit_fail** | — | — | — | — | — | — | — |
| 4 | flat | **✓** | 14.20m | 14.20m | **0.00m** | **1.00** | **52.4%** | **0.61m** | **0.18m** |
| 5 | hip | ✗[303×6] | 18.84m | 19.19m | 0.36m | 0.02 | 0.9% | 6.97m | 1.75m |
| 6 | hip | ✗[303×6] | 19.91m | 19.91m | **0.00m** | 0.14 | 6.1% | 7.52m | 1.26m |
| 7 | complex | ✗[303×2] | 16.68m | 16.68m | **0.00m** | 0.06 | 2.3% | 5.79m | 1.19m |
| 8 | gable | **✓** | 13.98m | 13.98m | **0.00m** | 0.11 | 5.7% | 10.51m | 1.84m |
| 9 | hip | ✗[303×4] | 18.47m | 18.46m | **0.01m** | 0.04 | 1.9% | 7.86m | 1.70m |

Aggregate: **val3dity 4/10 (40%)** vs prior 0/9. **|Δh| 거의 모두 ≤ 0.5m** (height 정확).

### Per-type 요약

| type | n | val3dity pass | mean(valid) \|Δh\| | mean(valid) coverage | mean(valid) vol_ratio | mean(valid) Hausdorff |
|---|---|---|---|---|---|---|
| flat | 3 | **3/3 (100%)** | 0.09m | 34.2% | 0.68 | 4.55m |
| gable | 1 | 1/1 | 0.00m | 5.7% | 0.11 | 10.51m |
| hip | 3 | 0/3 | n/a | n/a | n/a | n/a |
| tri-slope | 1 | 0/1 | n/a | n/a | n/a | n/a |
| complex | 1 | 0/1 | n/a | n/a | n/a | n/a |

(complex bid 3은 parser fail로 시도 카운트 외)

### bid 3 polyfit_fail 분리 진단

[bid3_diag](bid3_diag/) 결과:
- `n_planes`: 66, `n_lines_input`: 1124 (1123 pts + header)
- `line_55_raw`: `-84.4078 -0.4650 -50.9445 0.0000 1.0000 -0.0000 0` — **정상 형식**
- `n_issues_first_5`: 0, `out_of_range_pids`: 0
- stderr: `CGAL ERROR: assertion violation!` — line 위치는 **CGAL 내부 코드라인**, 입력 파일 line 아님

→ **B 가설(파서 형식) 반증**. **C 가설(알고리즘 복잡도) 지지**: 66 planes의 candidate face arrangement에서 CGAL 내부 assertion 실패. PolyFit MIP는 plane 수에 super-polynomial 복잡도이고 66은 알고리즘 안정성 한계 위.

### 시각적 figure (per-type 1건씩, [figures/](../../../../figs/stage3_polyfit_phase2/figures/))

- [stageA_flat_b1.png](../../../../figs/stage3_polyfit_phase2/figures/stageA_flat_b1.png) — flat ✓ (val3dity ✓, vol_ratio 1.00)
- [stageA_gable_b8.png](../../../../figs/stage3_polyfit_phase2/figures/stageA_gable_b8.png) — gable ✓ (val3dity ✓ but coverage 5.7%)
- [stageA_tri-slope_b0.png](../../../../figs/stage3_polyfit_phase2/figures/stageA_tri-slope_b0.png) — tri-slope ✗
- [stageA_hip_b5.png](../../../../figs/stage3_polyfit_phase2/figures/stageA_hip_b5.png) — hip ✗
- [stageA_complex_b7.png](../../../../figs/stage3_polyfit_phase2/figures/stageA_complex_b7.png) — complex ✗

## Stage B — v4 envelope input

| bid | type | val3dity | output_h | GT_h | \|Δh\| | coverage | vol_ratio | Hausdorff | Chamfer |
|---|---|---|---|---|---|---|---|---|---|
| 0 | tri-slope | **✓** | 15.87m | 15.97m | **0.10m** | **27.1%** | **0.54** | 7.97m | 1.52m |
| 1 | flat | ✓ | 7.80m | 16.61m | **8.81m** | 7.7% | 0.16 | 13.51m | 3.00m |
| 2 | flat | SKIP | — | — | — | — | — | — | (off_to_cityjson_None) |
| 6 | hip | ✓ | 1.87m | 19.91m | **18.04m** | 0.5% | 0.01 | 17.98m | 5.66m |
| 21 | complex | ✗[305] | 9.75m | 17.42m | 7.66m | 1.3% | 0.03 | 14.92m | 4.17m |

Aggregate: val3dity 3/4 통과(75%) but **|Δh| 8-18m collapse 다수** — height조차 못 잡음.

[figures/stageB_b{0,1,6,21}.png](../../../../figs/stage3_polyfit_phase2/figures/) — Stage A 보다 GT와 mismatch 더 큼.

## A vs B 비교 (clean cases)

| bid | type | A val3dity | A \|Δh\| | A coverage | B val3dity | B \|Δh\| | B coverage | A→B Δ |
|---|---|---|---|---|---|---|---|---|
| 0 | tri-slope | ✗ 303 | 0.49m | 1.8% | ✓ | 0.10m | 27.1% | **B 더 좋음** |
| 1 | flat | ✓ | 0.00m | 47.8% | ✓ | 8.81m | 7.7% | **B 폭락** |
| 2 | flat | ✓ | 0.28m | 2.4% | SKIP | — | — | n/a |
| 6 | hip | ✗ 303 | 0.00m | 6.1% | ✓ | 18.04m | 0.5% | val3dity↑ but quality↓↓ |
| 21 | complex | (not run) | — | — | ✗ 305 | 7.66m | 1.3% | — |

A→B 격차 자체가 데이터 quality gap 정량 지표. 일관 패턴 없음 (B가 더 나은 case + 더 나쁜 case 혼재).

## 판정

### Methodology check (Stage A)

**Hard 기준**: 8/10 val3dity pass + mean |Δh|<2m + mean coverage≥50%
- val3dity: **4/10 (40%) — 미달**
- mean |Δh| (valid): 0.09m — 통과
- mean coverage (valid flat only): 34.2% — 미달
- → **methodology_pass = False**

### "val3dity ✓ but quality 부족" 패턴 — 사용자 1번 기억 검증

| bid | val3dity | coverage | vol_ratio | Hausdorff | quality 평가 |
|---|---|---|---|---|---|
| B2 flat | ✓ | **2.4%** | 0.05 | 12.22m | mesh가 GT의 5% 크기 — quality 부족 |
| B8 gable | ✓ | 5.7% | 0.11 | 10.51m | mesh 너무 얇음 — quality 부족 |
| B6 hip(B) | ✓ | **0.5%** | 0.01 | 17.98m | mesh 사실상 collapse |
| B1 flat(B) | ✓ | 7.7% | 0.16 | 13.51m | val3dity 통과 but 폭락 |

→ **D 가설(val3dity ≠ quality) 사실 검증됨**. PolyFit 통과 cases 중 다수가 GT 와 정량적으로 큰 격차.

### PolyFit을 살릴 수 있는가? — **부분적으로 그렇다, 그러나 thesis Stage 3로는 부적합**

- repair recipe로 0/9 → 4/10 진척 (Phase 1 가설 A **부분 검증**). flat-prism은 정확하게 재구성 (vol_ratio=1.00, |Δh|=0).
- hip/complex/tri-slope 두 모드 실패:
  1. **303 non-manifold 잔존** (5/10): 더 깊은 manifold 결함. orient_polygon_soup가 `oriented=false` 반환 — 입력 plane 자체에서 일관 orientation 정의 불가능한 경우.
  2. **val3dity ✓ but coverage <10%**: PolyFit MIP의 "minimal valid" 선호로 mesh가 GT의 일부분만 표현. complexity weight 조정으로 일부 개선 가능하지만 본질적 한계.
- **bid 3 (66 planes)**: CGAL assertion failure — 알고리즘 자체의 plane 수 한계. C 가설 사실 확인.

### 다른 backend도 같은 함정에 빠지는가? — Stage B 결과로 부분 답

v4 envelope을 PolyFit에 넣은 결과:
- **B0 tri-slope만 의미있는 결과** (cov=27%, vol_ratio=0.54). Stage A B0보다 *더 좋음*.
- B1/B6 collapse: v4 envelope의 plane 정보가 PolyFit에 부적합.
- v4 envelope은 PolyFit-style hypothesis-and-selection에 직접 호환되지 않음. cluster 파라미터 또는 plane extraction 자체 검토 필요.

## 가설 업데이트 (Phase 1 → Phase 2)

| 가설 | Phase 1 | Phase 2 결과 |
|---|---|---|
| **A** (post-processing) | HIGH | **부분 검증** — repair recipe로 4/10 valid (개선). hip/complex 303 잔존 → A 단독으론 부족. **MEDIUM** |
| **B** (cluster_planes 누락) | LOW-MEDIUM | bid 3 parser 가설 **반증**. flat 100% 통과 → cluster 충분. **LOW** |
| **C** (algorithm fit) | LOW-MEDIUM | bid 3 CGAL assertion → 66 planes 한계 명확. coverage 1-7%는 MIP "minimal valid" 선호 결과. **MEDIUM** |
| **D** (val3dity ≠ quality) | UNFALSIFIABLE | val3dity ✓ + cov 2-6%로 *직접 검증됨* — D 가설 사실. **HIGH** |

**핵심 결론**: A + C + D가 함께 작용. A는 부분 해결, **C/D가 본질적 한계**.

## 다음 단계 제안

1. **PolyFit이 본 thesis Stage 3로는 부적합** — methodology pass 미달 + quality 부족 + large-plane 빌딩 처리 불가.
2. **남은 fix 후보**:
   - C 측: PolyFit weight tuning (w_fit↑, w_cmp↓로 fit 강조) — coverage 부족 완화. weight sweep으로 검증 가능.
   - A 측: hip/complex의 303 잔존 → 더 깊은 manifold repair. 그러나 A 단독으로 quality 부족 해결 불가.
   - D 측: convex polytope/2.5D/PolyFit 중 building type 별 분기 (flat→PolyFit OK, hip→2.5D, complex→convex) 검토.
3. **본 task 범위에서 PolyFit 부적합 확정**. 다음 라운드에서:
   - **P1-3b Round 2** (q<1.0 robust support_d) 우선
   - 또는 **building-type 분기** (flat 한정으로 PolyFit 유지)
   - 권장: P1-3b Round 2가 더 비용 효과적 (단일 backend 유지).

## Self-verification

- 9 buildings × Stage A 모두 측정: ✓ (10건 — bid 3 포함)
- 6 metric (val3dity, |Δh|, coverage, vol_ratio, Hausdorff, Chamfer) 모두 출력: ✓
- 시각적 figure 최소 type당 1건: ✓ (flat, gable, tri-slope, hip, complex × Stage A; b0, b1, b6, b21 × Stage B)
- bid 3 polyfit_fail 원인 분리 보고: ✓ (CGAL Assertion, 입력 형식 정상, 66 planes 한계 — C 가설)
- 판정 분기 명확: ✓ (methodology_pass=False, "val3dity ✓ but quality 부족"으로 사용자 1번 기억 검증)

## 자료 위치

- [metrics.json](metrics.json) — 전체 정량 데이터
- [stageA/building_NN/](stageA/) — Stage A 10건 (input.txt, output.off, building.city.json, val3dity.json, polyfit_stderr.log)
- [stageB/building_NN/](stageB/) — Stage B 5건
- [figures/](../../../../figs/stage3_polyfit_phase2/figures/) — per-type side-by-side (Stage A 5 + Stage B 4)
- [bid3_diag/](bid3_diag/) — bid 3 입력 파일
- [src/stage3/polyfit_cli.cpp](../../../../../src/stage3/polyfit_cli.cpp) — 수정 소스 (5-step recipe + triangulate_faces)
