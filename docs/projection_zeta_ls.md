# projection_zeta_ls -- A1 LS zeta alignment

> Observe only. No reconstruction/retraining. ALS class-6 roof points are the independent 3D evidence; final adoption is 김휘영.

## Measurement

- buildings: 8 texture-clear success buildings
- measurements: 24 views (`near` <20 deg, `mid` 20-45 deg, `strong` >45 deg)
- method: ALS roof silhouette -> wide 300px orientation-aware edge search, not gradient-max and not +/-28px STEP
- starting config zeta0: 48.000 m

## LS Result

- zeta-only: zeta_hat = **48.126 m**; 95% CI half-width = **0.429 m**; residual RMS = 167.31 px
- zeta+XY: zeta_hat = **48.054 m**, dE=+0.216 m, dN=+0.299 m; residual RMS = 166.32 px
- zeta/XY correlation: corr(zeta,dE)=+0.342, corr(zeta,dN)=-0.612; RMS improvement = 0.98 px

## Residual vs tan(view zenith)

- signed-Z residual regression: slope=-1.7422 m/tan, intercept=+3.8888 m, R2=0.033
- figure: `docs/figs/projection_zeta_ls/residual_vs_tan.png`

## zeta comparison

| source | zeta_m | delta_vs_LS_m | note |
|---|---:|---:|---|
| LS A1 | 48.126 | +0.000 | ALS-to-photo edge fit |
| GCG2016 sampled value from root-cause note | 45.700 | -2.426 | official quasigeoid comparison value |
| pipeline prior | 48.000 | -0.126 | existing GS-local/seed convention |

## Angle-bin observation at zeta0

| bin | median ALS offset at zeta0 (m) |
|---|---:|
| near | 3.0183 |
| mid | 1.9718 |
| strong | 8.5179 |

## Recommendation

- 권고: A2 재게이트에는 LS zeta_hat 48.126 m를 기본 config로 사용하고, 45.7/48.0은 sensitivity comparison 값으로만 병기한다. 채택 판정은 김휘영.

## Caveats

- This is an automated edge-silhouette alignment, so low-confidence or repeated roof texture can inflate uncertainty.
- LoD2 is not used in the LS fit; building-level scatter here is ALS/photo/pose/edge-pick scatter, while LoD2 model error remains for A2's separate LoD2 column.

## 판정 필요 지점

- LS zeta_hat 채택 여부.
- zeta+XY 개선량을 포즈/XY 보정 신호로 볼지 여부.
- residual_vs_tan 기울기를 추가 수직 잔량으로 볼지 여부.
