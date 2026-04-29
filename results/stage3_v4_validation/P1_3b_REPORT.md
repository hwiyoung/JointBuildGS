# P1-3b — backend fix + support-plane adapter (1st round)

**Mutual ckpt, 5 buildings × 4 conditions = 20 runs.** GT for evaluation only. v4 parameters P1-2-fixed.

`gravity = [0, 1, 0]` asserted in every entry.

Clean cases (Hard/Strong GO): **B1, B6, B21**. Regression watch: B2. Reference (not in GO): B0.

Conditions:

```
        Patch 1   Step 1     Step 2.5
C0        ×          ×           ×       (P1-3 baseline)
C1        ✓          ×           ×       (backend only)
C2        ✓          ✓           ×       (+ orientation)
C3        ✓          ✓           ✓       (+ d_support)
```

## Table 1 — per-(building, condition)

| bid | cond | n_planes | output_h | GT_h | \|Δh\| | output_vol | vol_ratio | coverage | val3dity | S4_max_d2p | mean_inside_ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | C0 | 25 | 9.07m | 15.97m | **6.90m** | 54 | 0.04 | 2.2% | ✓ | 0.00mm | 0.781 |
| 0 | C1 | 25 | 9.07m | 15.97m | **6.90m** | 54 | 0.04 | 2.2% | ✓ | 0.00mm | 0.781 |
| 0 | C2 | 25 | 9.07m | 15.97m | **6.90m** | 54 | 0.04 | 2.2% | ✓ | 0.00mm | 0.781 |
| 0 | C3 | 25 | 10.91m | 15.97m | **5.05m** | 113 | 0.09 | 4.7% | ✓ | 0.00mm | 0.847 |
| 1 | C0 | 23 | 4.22m | 16.61m | **12.39m** | 104 | 0.05 | 2.5% | ✓ | 0.00mm | 0.771 |
| 1 | C1 | 23 | 4.22m | 16.61m | **12.39m** | 104 | 0.05 | 2.5% | ✓ | 0.00mm | 0.771 |
| 1 | C2 | 23 | 4.22m | 16.61m | **12.39m** | 104 | 0.05 | 2.5% | ✓ | 0.00mm | 0.771 |
| 1 | C3 | 23 | 7.61m | 16.61m | **9.00m** | 287 | 0.14 | 6.8% | ✓ | 0.00mm | 0.849 |
| 2 | C0 | 13 | 13.95m | 13.63m | **0.31m** | 1652 | 1.72 | 85.2% | ✗['204'] | 11.35mm | 0.802 |
| 2 | C1 | 13 | 13.95m | 13.63m | **0.31m** | 1655 | 1.72 | 85.4% | ✗['302', '302'] | 0.00mm | 0.802 |
| 2 | C2 | 13 | 13.95m | 13.63m | **0.31m** | 1655 | 1.72 | 85.4% | ✗['302', '302'] | 0.00mm | 0.802 |
| 2 | C3 | 13 | 14.76m | 13.63m | **1.12m** | 1907 | 1.99 | 98.4% | ✗['302'] | 0.00mm | 0.895 |
| 6 | C0 | 12 | 15.56m | 19.91m | **4.35m** | 270 | 0.26 | 10.9% | ✓ | 4.72mm | 0.767 |
| 6 | C1 | 12 | 15.56m | 19.91m | **4.35m** | 270 | 0.26 | 10.9% | ✗['302'] | 0.00mm | 0.767 |
| 6 | C2 | 13 | 15.35m | 19.91m | **4.56m** | 143 | 0.14 | 5.8% | ✓ | 0.00mm | 0.780 |
| 6 | C3 | 13 | 16.05m | 19.91m | **3.86m** | 177 | 0.17 | 7.2% | ✗['302'] | 0.00mm | 0.873 |
| 21 | C0 | 17 | 3.15m | 17.42m | **14.27m** | 5 | 0.00 | 0.2% | ✓ | 0.06mm | 0.713 |
| 21 | C1 | 17 | 3.15m | 17.42m | **14.27m** | 5 | 0.00 | 0.2% | ✓ | 0.04mm | 0.713 |
| 21 | C2 | 17 | 3.15m | 17.42m | **14.27m** | 5 | 0.00 | 0.2% | ✓ | 0.04mm | 0.713 |
| 21 | C3 | 17 | 4.32m | 17.42m | **13.10m** | 10 | 0.01 | 0.4% | ✗['302', '302'] | 0.00mm | 0.784 |

## Table 2 — best condition + dominant_fix

| bid | role | best_cond | output_h | \|Δh\| | coverage | val3dity | dominant_fix |
|---|---|---|---|---|---|---|---|
| 0 | reference | **C3** | 10.91m | 5.05m | 4.7% | ✓ | **d_support** |
| 1 | clean | **C3** | 7.61m | 9.00m | 6.8% | ✓ | **d_support** |
| 2 | regression | **C0** | 13.95m | 0.31m | 85.2% | ✗['204'] | **none** |
| 6 | clean | **C0** | 15.56m | 4.35m | 10.9% | ✓ | **orientation** |
| 21 | clean | **C0** | 3.15m | 14.27m | 0.2% | ✓ | **none** |

## Table 3 — B2 regression watch

| bid | C0 height | C3 height | Δ | C0 v3d | C3 v3d | regression? |
|---|---|---|---|---|---|---|
| 2 | 13.95m | 14.76m | +0.81m | ✗ | ✗ | no |

## Table 4 — B0 reference (backend ablation)

| cond | output_h | vol_ratio | val3dity | S4_max_d2p_before | S4_max_d2p_after |
|---|---|---|---|---|---|
| C0 | 9.07m | 0.04 | ✓ | 0.00mm | 0.00mm |
| C1 | 9.07m | 0.04 | ✓ | 0.00mm | 0.00mm |
| C2 | 9.07m | 0.04 | ✓ | 0.00mm | 0.00mm |
| C3 | 10.91m | 0.09 | ✓ | 0.00mm | 0.00mm |

## Hard / Strong GO verdict (clean cases B1/B6/B21, C3)

- B1/B6/B21 hard pass (\|Δh\|<2m AND val3dity ✓): **0/3** ([])
- B2 regression: \|Δh\|=0.81m, val3dity kept=True → OK
- **Hard GO** (3/3 + B2 OK): ✗
- **Strong GO** (Hard + 3/3 coverage ≥50%): ✗ (0/3 cov ≥50%)

## Round 2 branch decision

- **전건물 NG** → adapter 설계 자체 재검토 필요
- B6 C2 > C3 → d_support 역효과, q<1.0 도입 필요
- B21 C2 > C3 → d_support 역효과, q<1.0 도입 필요

## Self-verification

- gravity = [0, 1, 0] asserted: ✓
- 5 buildings × 4 conditions = 20 runs: ✓
- C0 reproduces P1-3 v4 height: 5/5 (✓)
- dominant_fix assigned to all buildings: ✓
- Patch 1 shell closure (C1+ S4_max_d2p < 1mm): B0=0.00mm, B1=0.00mm, B2=0.00mm, B6=0.00mm, B21=0.04mm
