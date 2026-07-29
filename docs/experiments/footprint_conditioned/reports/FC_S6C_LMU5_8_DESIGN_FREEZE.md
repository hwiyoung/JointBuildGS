# FC-S6c Lmu5-Lmu8 Design Freeze

Status: design-frozen for no-training proxy audit and single-term smoke consideration.

This document freezes the proposed revised `L_mutual` completion terms beyond the accepted FC-S6b terrain-off candidate (`A8_no_terrain_terms`). It does not authorize training by itself. It also does not enable `L_structure`, G2, Stage3 changes, or Metric-v1 changes.

## Shared Constraints

- Stage2 loss construction must not use GT roof type, GT roof partition, GT final mesh, or GT semantic surfaces.
- Stage3Algo-v1 and Metric-v1 remain fixed evaluation-only consumers.
- `GroundSurface` is a Stage3 final semantic face; Stage2 uses terrain evidence / terrain primitive class.
- All terms are single-term smoke candidates first. Combined terms are not allowed until single-term smoke and gate review.
- All terms must be logged separately and must support default-off equivalence.
- All gates are computed from Stage2 predictions, geometry, support, confidence, and fixed domain/footprint assumptions only.
- Normalized weights are relative to the accepted A8 terrain-off Mutual scale. Gradient guard is enforced against the base loss gradient norm when gradient diagnostics are enabled.

## Lmu5 Split Roof-Height Relation

1. Final-output target: shell diagnostics first (`h_err`, `vol_ratio`), then semantic faces through stable RoofSurface/Terrain separation.
2. Formula:

```text
h_i = -dot(c_i, e_gravity)
H_t = stopgrad(weighted_quantile(h_i | terrain evidence, q=0.90))
Lmu5 = mean_i p_roof_i * relu((H_t + m_rt) - h_i)^2
```

`m_rt` is a small roof-terrain clearance margin in world units. This is roof-side only; terrain-side height compaction is not reintroduced here.

3. Stopgrad policy: stop gradient through `H_t`, terrain masks used to estimate `H_t`, and all quantile selection. Gradients flow only to roof probability/roof-supported geometry for the roof-side penalty.
4. Gate policy: enable only when terrain evidence count and confidence exceed fixed run-level gates; otherwise skip the term and log `gate=off`. No GT terrain surface is used.
5. Initial normalized weight: `0.05`.
6. Expected metric improvement: lower `h_err`, more stable `vol_ratio`, no loss of `ground_cov`; strongest expected signal on `B6` and roof/height-diagnostic cases.
7. Rejection condition: any easy/control regression, B104 `ground_cov` loss, mean support regression, or gradient ratio above guard; reject immediately if proxy improves but final Stage3 F/height metrics do not.
8. Required logs: `loss/mutual_lmu5_roof_height`, `mutual/lmu5_gate`, `mutual/lmu5_terrain_ref_height`, `mutual/lmu5_roof_margin_violation`, `grad_ratio/lmu5_base`.

Gradient ratio guard: `Lmu5` must stay `<= 5%` of base gradient norm.

## Lmu6 Semantic-Geometry Calibration

1. Final-output target: semantic faces and support-confidence. The term is intended to reduce high-confidence semantic/normal contradictions before Stage3 reads out RoofSurface, WallSurface, and terrain evidence.
2. Formula:

```text
d_roof = relu(tau - (n_i dot e_gravity)^2)^2
d_wall = (n_i dot e_gravity)^2
d_terrain = (1 - abs(n_i dot e_gravity))^2
Lmu6 = mean_i stopgrad(conf_i) * [p_roof_i d_roof + p_wall_i d_wall + p_terrain_i d_terrain]
```

This is a calibration term, not a new class prior. It penalizes contradictions only when the predicted semantic probability and geometry disagree.

3. Stopgrad policy: stop gradient through confidence/support scalars and optional gate masks. Gradients may flow to semantic logits and geometry, subject to the gradient ratio guard.
4. Gate policy: only apply to samples with confidence/support above threshold and semantic entropy below threshold. Ambiguous points are logged but not forced.
5. Initial normalized weight: `0.02`.
6. Expected metric improvement: improved `roof_cov`, `wall_cov`, classwise support, and fewer semantic split errors without changing Stage3.
7. Rejection condition: support-confidence improves while final F/coverage does not, or easy/control semantic coverage regresses.
8. Required logs: `loss/mutual_lmu6_sem_geom`, `mutual/lmu6_gate_rate`, `mutual/lmu6_mismatch_roof`, `mutual/lmu6_mismatch_wall`, `mutual/lmu6_mismatch_terrain`, `grad_ratio/lmu6_base`.

Gradient ratio guard: `Lmu6` must stay `<= 5%` of base gradient norm.

## Lmu7 Weak Roof-Wall Hint

1. Final-output target: face graph, specifically roof-wall adjacency candidates that Stage3 can read into a closed shell.
2. Formula:

```text
N_r(i) = local roof-neighborhood support near wall-like evidence
Lmu7 = mean_i stopgrad(g_i) * p_roof_i * p_wall_j * compat_gap(i, j)
compat_gap(i, j) = local_distance_to_roof_wall_contact + normal_parallel_violation
```

The implementation must use local predicted evidence neighborhoods, not GT roof-wall edges.

3. Stopgrad policy: stop gradient through neighbor selection, support gates, and geometric contact targets. Gradient flows only through weak semantic compatibility and local geometry residual.
4. Gate policy: require high-confidence roof and wall evidence, local support, and finite neighborhood size. Disable for sparse/ambiguous support.
5. Initial normalized weight: `0.02`.
6. Expected metric improvement: better roof-wall adjacency consistency, lower roof-wall gap flags, no topology increase in open/non-manifold edges.
7. Rejection condition: any increase in open_edges/non_manifold_edges, roof_complex regression, or gradient ratio above guard.
8. Required logs: `loss/mutual_lmu7_roof_wall`, `mutual/lmu7_gate_rate`, `mutual/lmu7_contact_gap`, `mutual/lmu7_normal_violation`, `grad_ratio/lmu7_base`.

Gradient ratio guard: `Lmu7` must stay `<= 5%` of base gradient norm.

## Lmu8 Weak Terrain-Wall Hint

1. Final-output target: face graph and shell diagnostics, specifically wall-ground adjacency and GroundSurface closure.
2. Formula:

```text
G_t = stopgrad(local terrain height/support estimate)
Lmu8 = mean_i stopgrad(g_i) * p_wall_i * relu(abs(h_wall_bottom_i - G_t) - m_wg)^2
```

This term is not a terrain-normal or terrain-height revival. It is a weak wall-ground contact hint and must be gated more strictly than Lmu7.

3. Stopgrad policy: stop gradient through terrain reference height, terrain neighbor selection, and terrain support gates. Gradient should primarily affect wall-ground contact compatibility, not terrain class mass.
4. Gate policy: enable only with stable terrain evidence, high terrain confidence, low terrain entropy, and enough local wall support. Disable by default on terrain-ambiguous buildings.
5. Initial normalized weight: `0.01`.
6. Expected metric improvement: preserve B104 `ground_cov`, improve wall-ground closure/support, and reduce hidden GroundSurface failure without terrain drift.
7. Rejection condition: any B104 `ground_cov` or `ground_support_cov` regression, terrain y-drift increase, support regression, or gradient ratio above guard.
8. Required logs: `loss/mutual_lmu8_terrain_wall`, `mutual/lmu8_gate_rate`, `mutual/lmu8_wall_ground_gap`, `mutual/lmu8_terrain_ref_height`, `grad_ratio/lmu8_base`.

Gradient ratio guard: `Lmu8` must stay `<= 2%` of base gradient norm.

## Smoke Order Rule

The no-training proxy audit must decide which terms are eligible for single-term smoke. Recommended default order is `Lmu5`, then `Lmu6`, then `Lmu7`; `Lmu8` requires stronger terrain-safety evidence because FC-S6 showed terrain terms are the main risk path.
