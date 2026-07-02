# projection_gate_v2 -- A2 fix+zeta gate

> Observe only. No reconstruction/retraining. Final 합/불 판정은 김휘영.

## Method

- config: geo=EPSG:25832 opf=EPSG:32632 input_default=orthometric orthometric_geoid_m=48.125535
- measurements: 24 rows = 8 buildings x near/mid/strong 3 views
- edge alignment: wide 300px orientation-aware search, same measurement family as A1; not gradient-max and not +/-28px STEP
- columns split ALS-to-photo (projection/pose) and LoD2-to-photo (projection+model).
- overlays: clean LoD2 roof rings, not jagged silhouettes; each figure caption includes numeric offsets.

## ALS Gate Summary

| angle_bin | n | median_m | p90_m | proposed criterion |
|---|---:|---:|---:|---|
| near | 8 | 1.7652 | 4.6224 | median <= 0.3 m |
| mid | 8 | 2.6585 | 4.1721 | median <= 0.3 m |
| strong | 8 | 8.6300 | 215.2618 | median <= 0.3 m |
| overall | 24 | 3.6561 | 9.8341 | median <= 0.3 m |

- criteria_met_for_A3_instruction: **False**

## LoD2 Observation Summary

| angle_bin | n | median_m | p90_m |
|---|---:|---:|---:|
| near | 8 | 1.8501 | 4.5632 |
| mid | 8 | 1.6790 | 3.9733 |
| strong | 7 | 7.5291 | 19.0832 |
| overall | 23 | 2.3716 | 8.1330 |

## Files

- CSV: `docs/projection_gate_v2.csv`
- figures: `docs/figs/projection_gate_v2/*.png`
- residual curve: `docs/figs/projection_gate_v2/als_offset_vs_tan.png`

## Observation

- At least one ALS median value does not meet the numeric proposal. Per task instruction, A3 일괄 재계산 is not run from this state.
- Cause observation 1: ALS and LoD2 columns are both high in several rows, so the residual is not isolated to LoD2 model error.
- Cause observation 2: strong-oblique rows have the largest ALS median and p90, matching the expected vertical/edge-correspondence sensitivity growth with tan(view zenith).
- Cause observation 3: several rows have large search-derived sigma and far translations, so automated edge correspondence ambiguity remains a candidate source before any downstream recalculation.

## 판정 필요 지점

- A2 numeric proposal acceptance/rejection.
- Whether high p90 or low-confidence rows should trigger additional manual correspondence measurement.
- Whether A3 may proceed despite the A2 instruction gate.
