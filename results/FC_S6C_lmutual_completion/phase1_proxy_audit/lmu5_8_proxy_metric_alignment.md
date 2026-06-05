# FC-S6c Lmu5-Lmu8 Proxy/Metric Alignment

Scope: no-training audit over existing FC-S6 Stage3Algo-v1 + Metric-v1 outputs for A0, A1, A4, A8, B2, and A9.

Proxy convention: higher proxy means larger predicted incompatibility / risk. A useful proxy should generally correlate negatively with F/coverage/support or positively with h_err/topology errors.

## Correlation Summary

| Proxy | Metric | Pearson | Spearman | N |
|---|---|---:|---:|---:|
| lmu5_proxy | F |  |  | 60 |
| lmu5_proxy | roof_cov |  |  | 60 |
| lmu5_proxy | wall_cov |  |  | 60 |
| lmu5_proxy | ground_cov |  |  | 60 |
| lmu5_proxy | support_cov |  |  | 60 |
| lmu5_proxy | ground_support_cov |  |  | 60 |
| lmu5_proxy | h_err |  |  | 60 |
| lmu5_proxy | vol_ratio |  |  | 60 |
| lmu5_proxy | chamfer |  |  | 60 |
| lmu5_proxy | open_edges |  |  | 60 |
| lmu5_proxy | non_manifold_edges |  |  | 60 |
| lmu6_proxy | F | 0.331486 | 0.272596 | 60 |
| lmu6_proxy | roof_cov | 0.200352 | 0.139943 | 60 |
| lmu6_proxy | wall_cov | 0.302771 | 0.126732 | 60 |
| lmu6_proxy | ground_cov | 0.230934 | 0.35056 | 60 |
| lmu6_proxy | support_cov | 0.371831 | 0.234957 | 60 |
| lmu6_proxy | ground_support_cov | 0.395638 | 0.069368 | 60 |
| lmu6_proxy | h_err | 0.17871 | -0.111587 | 60 |
| lmu6_proxy | vol_ratio | -0.407913 | -0.308475 | 60 |
| lmu6_proxy | chamfer | -0.332935 | -0.156266 | 60 |
| lmu6_proxy | open_edges |  |  | 60 |
| lmu6_proxy | non_manifold_edges |  |  | 60 |
| lmu7_proxy | F | -0.488867 | -0.613164 | 60 |
| lmu7_proxy | roof_cov | -0.304056 | -0.327406 | 60 |
| lmu7_proxy | wall_cov | -0.411487 | -0.47381 | 60 |
| lmu7_proxy | ground_cov | -0.35455 | -0.616385 | 60 |
| lmu7_proxy | support_cov | -0.473275 | -0.375109 | 60 |
| lmu7_proxy | ground_support_cov | -0.502335 | -0.428934 | 60 |
| lmu7_proxy | h_err | 0.49961 | 0.577513 | 60 |
| lmu7_proxy | vol_ratio | -0.258475 | -0.215137 | 60 |
| lmu7_proxy | chamfer | 0.475291 | 0.457148 | 60 |
| lmu7_proxy | open_edges |  |  | 60 |
| lmu7_proxy | non_manifold_edges |  |  | 60 |
| lmu8_proxy | F |  |  | 60 |
| lmu8_proxy | roof_cov |  |  | 60 |
| lmu8_proxy | wall_cov |  |  | 60 |
| lmu8_proxy | ground_cov |  |  | 60 |
| lmu8_proxy | support_cov |  |  | 60 |
| lmu8_proxy | ground_support_cov |  |  | 60 |
| lmu8_proxy | h_err |  |  | 60 |
| lmu8_proxy | vol_ratio |  |  | 60 |
| lmu8_proxy | chamfer |  |  | 60 |
| lmu8_proxy | open_edges |  |  | 60 |
| lmu8_proxy | non_manifold_edges |  |  | 60 |

## Case-Flag Means

| Proxy | B104 mean | non-B104 mean | B6 mean | non-B6 mean | roof_complex mean | non-roof_complex mean |
|---|---:|---:|---:|---:|---:|---:|
| lmu5_proxy | 0 | 0 | 0 | 0 | 0 | 0 |
| lmu6_proxy | 0.0334183 | 0.0191428 | 0.0323437 | 0.0192622 | 0.016729 | 0.0222166 |
| lmu7_proxy | 0 | 0.103623 | 0.123817 | 0.0898654 | 0.130086 | 0.0774785 |
| lmu8_proxy | 0 | 0 | 0 | 0 | 0 | 0 |

## Interpretation

- Lmu5 is intended to target roof-terrain height separation. Its proxy should be read primarily against `h_err`, `vol_ratio`, and the B6 flag.
- Lmu6 is a semantic-geometry contradiction proxy. It is most relevant if it tracks F, class coverage, or classwise support.
- Lmu7 and Lmu8 use final Stage3 graph/shell read-out as a no-training proxy for relation hints. Because Stage3 closes many shells by construction, low variation in open/non-manifold metrics weakens these proxies.
- A proxy with positive correlation to F/support is treated as a mismatch because the proxy convention is higher=worse.
- Proxy alignment is a screening tool only. A term that proceeds still requires single-term smoke training before combination.

## Proxy-Based Term Recommendation

- `Lmu5`: `DEFER` (weak_proxy_signal).
- `Lmu6`: `DEFER` (proxy_mismatch:positive_with_F,positive_with_support,positive_with_ground_cov,elevated_on_recovered_B104; useful_signal:elevated_on_B6).
- `Lmu7`: `PROCEED` (negative_with_F,positive_with_h_err,negative_with_support,elevated_on_B6,elevated_on_roof_complex).
- `Lmu8`: `DEFER` (weak_proxy_signal).
