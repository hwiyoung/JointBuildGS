# FC-S6c-0 Lmu Design-to-Formula Audit

Status: inspection-only and analysis-only.

No training, smoke jobs, L_structure, G2, Stage3 modification, or Metric-v1 modification was performed.

Core rule used here:

`final-output target -> evidence-level precondition -> formula -> gradient path -> gate policy -> proxy readiness -> expected Stage3Algo-v1 + Metric-v1 result`

Terminology: Stage2 uses terrain evidence / terrain primitive class. `GroundSurface` is only the Stage3 final semantic face.

## Summary Decision

| Term | Formula/gate/proxy decision | Short reason |
|---|---|---|
| Lmu1 wall verticality | `FORMULA_OK_PROCEED_TO_PROXY` | Wall normal formula is valid; bidirectional gradient is a known interpretability risk. |
| Lmu2 roof non-wall prior | `FORMULA_OK_PROCEED_TO_PROXY` | Roof non-wall formula is valid with steep-roof guard. |
| Lmu3 terrain normal stability | `REJECT_TERM_FOR_NOW` | Normal formula is valid but terrain path is empirically risky under FC-S6. |
| Lmu4 terrain height compactness | `FORMULA_NEEDS_REVISION` | Current terrain height term is not robust compactness and needs revision. |
| Lmu5 split roof-height relation | `PROXY_NEEDS_REVISION` | Height-order idea is plausible, but current proxy is saturated and p_roof escape is unresolved. |
| Lmu6 semantic-geometry calibration | `TARGET_MISMATCH` | Current formula is not semantic calibration; it is semantic-weighted geometry prior. |
| Lmu7 weak roof-wall hint | `FORMULA_OK_PROCEED_TO_SINGLE_TERM_SMOKE` | Only term with target/formula/proxy chain strong enough for single-term smoke, after explicit pair/gate implementation. |
| Lmu8 weak terrain-wall hint | `GATE_BROKEN` | Target is valid but terrain-wall gate/proxy are broken or unverified. |

## Per-Term Audit

### Lmu1 wall verticality

Decision: `FORMULA_OK_PROCEED_TO_PROXY`

Target validity: Lmu1 targets semantic_faces / WallSurface by making wall primitive normals usable for Stage3 wall plane fitting.

Evidence precondition: WallSurface read-out needs wall primitives to have wall-like normals, meaning normals are approximately perpendicular to gravity.

Formula: `implemented: Lmu1 = mean_i p_wall_i * (n_i dot e_gravity)^2`

Formula validity: YES, for the wall-normal precondition.

Formula risks: In full bidirectional mode p_wall is not detached, so false wall probability can either pull non-wall geometry toward wall-like normals or reduce wall probability instead of correcting geometry.

Suggested correction: For a pure geometry-prior smoke variant, use stopgrad(p_wall). Keep bidirectional mode only when the hypothesis is explicitly semantic-geometry coupling.

Gradient path:

- semantic logits: yes through p_wall in current full mode
- normals: yes through dot(n, gravity)^2
- centers/heights: no
- confidence/gates: no confidence gate in current term
- intended: partly
- risk: Bidirectional semantics make interpretation harder; false positives can move geometry.
- stopgrad: Current implementation: no stopgrad in full mode; sem2geo mode detaches p_wall.

Gate policy: Current active term is effectively always-on for all primitives, weighted by p_wall.

Gate validity: VALID_BUT_NEEDS_CONFIDENCE_SUPPORT_GATE_FOR_NEW_SMOKE; expected gate-on rate: near 100% sample participation, soft-weighted by p_wall.

Proxy readiness: `PROXY_NOT_NEEDED_YET`. proxy not required before using current A8 candidate because Lmu1 is retained and partially tested

Expected Stage3Algo-v1 + Metric-v1 result: primary `wall_cov`, secondary `wall_support_cov, support_cov`; no-regression gates: roof_cov, ground_cov, easy/control F, open_edges, non_manifold_edges.

### Lmu2 roof non-wall prior

Decision: `FORMULA_OK_PROCEED_TO_PROXY`

Target validity: Lmu2 targets semantic_faces / RoofSurface by preventing roof primitives from collapsing into wall-like normal evidence.

Evidence precondition: RoofSurface read-out needs roof primitives to avoid wall-like horizontal normals while allowing valid sloped roof normals.

Formula: `implemented: Lmu2 = mean_i p_roof_i * relu(tau - (n_i dot e_gravity)^2)^2`

Formula validity: YES, with tau margin caveat.

Formula risks: Very steep roofs with low |n dot gravity| can be penalized; p_roof is not detached in full mode, so the term can lower roof probability instead of fixing roof normals.

Suggested correction: Keep tau conservative and log roof-complex failures. For geometry-prior mode, use stopgrad(p_roof).

Gradient path:

- semantic logits: yes through p_roof in current full mode
- normals: yes when (n dot gravity)^2 < tau
- centers/heights: no
- confidence/gates: no confidence gate in current term
- intended: partly
- risk: Can obscure whether improvements come from roof logits or roof geometry; steep roof edge cases may be over-regularized.
- stopgrad: Current implementation: no stopgrad in full mode; sem2geo mode detaches p_roof.

Gate policy: Current active term is always-on, soft-weighted by p_roof.

Gate validity: VALID_WITH_STEEP_ROOF_GUARD; expected gate-on rate: near 100% sample participation, active only where roof probability and wall-like normals coincide.

Proxy readiness: `PROXY_NOT_NEEDED_YET`. roof-complex evaluator risk can mask term utility

Expected Stage3Algo-v1 + Metric-v1 result: primary `roof_cov`, secondary `roof_support_cov, roof_complex F`; no-regression gates: wall_cov, ground_cov, easy/control F, topology.

### Lmu3 terrain normal stability

Decision: `REJECT_TERM_FOR_NOW`

Target validity: Lmu3 targets semantic_faces / GroundSurface indirectly by making terrain primitive normals stable enough for Stage3 ground read-out.

Evidence precondition: GroundSurface read-out needs terrain evidence normals to be horizontal-surface-like, but this does not guarantee correct terrain height.

Formula: `implemented: Lmu3 = mean_i p_terrain_i * terrain_gate_i * (1 - abs(n_i dot e_gravity))^2`

Formula validity: YES for the normal-only precondition, NO for height or drift.

Formula risks: Can create confident wrong-height terrain evidence; p_terrain is not detached in full mode; terrain gate defaults may be none/always-on.

Suggested correction: Do not use alone as a revised terrain term. Require terrain confidence/support gates and pair with explicit height/drift diagnostics if revisited.

Gradient path:

- semantic logits: yes through p_terrain in current full mode
- normals: yes through abs(dot)
- centers/heights: no
- confidence/gates: no; gate is no_grad when configured
- intended: partly
- risk: It can improve normal appearance while worsening terrain class mass or height evidence.
- stopgrad: Current implementation detaches terrain_gate; p_terrain is live unless sem2geo mode is used.

Gate policy: none/confidence/class_mass/mass_entropy modes exist; default none is soft always-on.

Gate validity: VALID_MECHANISM_BUT_EMPIRICALLY_RISKY; expected gate-on rate: none: near 100% soft participation; configured gates: unknown until logged.

Proxy readiness: `PROXY_NOT_NEEDED_YET`. normal proxy cannot diagnose height drift

Expected Stage3Algo-v1 + Metric-v1 result: primary `ground_cov`, secondary `ground_support_cov, terrain y quantiles`; no-regression gates: B104 ground_cov, easy/control F, support_cov, topology.

### Lmu4 terrain height compactness

Decision: `FORMULA_NEEDS_REVISION`

Target validity: Lmu4 targets GroundSurface evidence and shell height by stabilizing terrain primitive height without using final GroundSurface GT.

Evidence precondition: Stage3 needs terrain primitive heights to form a stable local ground reference rather than a drifting terrain cluster.

Formula: `implemented terrain-side height: mean_i p_terrain_i * gate_i * relu(h_i - H_t)^2, with fixed H_t or terrain quantile reference`

Formula validity: PARTIAL. It is one-sided terrain-below-reference regularization, not true compactness around a robust local terrain cluster.

Formula risks: Fixed threshold can be wrong; quantile can select the wrong terrain cluster; p_terrain can escape; compaction can damage B104-like terrain evidence.

Suggested correction: Revise to robust local median/Huber compactness using predicted terrain evidence only, with strict confidence/support gates and stopgrad reference.

Gradient path:

- semantic logits: yes through p_terrain if not detached
- normals: no direct normal gradient
- centers/heights: yes through height
- confidence/gates: no through current gate/reference
- intended: partly
- risk: Can push heights or semantic mass in ways that reduce ground_cov.
- stopgrad: Quantile reference is detached; p_terrain is live unless sem2geo mode is used.

Gate policy: terrain_gate_mode plus terrain reference availability; not support-aware by default

Gate validity: NEEDS_STRICT_SUPPORT_CONFIDENCE_GATE; expected gate-on rate: unknown; can be always-on in default none mode.

Proxy readiness: `PROXY_NEEDS_REVISION`. does not distinguish stable terrain plane from wrong terrain cluster

Expected Stage3Algo-v1 + Metric-v1 result: primary `ground_cov`, secondary `ground_support_cov, h_err, vol_ratio`; no-regression gates: B104 ground_cov/support, easy/control F, open/non-manifold.

### Lmu5 split roof-height relation

Decision: `PROXY_NEEDS_REVISION`

Target validity: Lmu5 targets shell_diagnostics by keeping roof evidence above a predicted terrain reference so Stage3 height and volume are stable.

Evidence precondition: Roof primitive heights must sit above a reliable terrain evidence reference, without reintroducing terrain-side negative transfer.

Formula: `proposed: h_i=-dot(c_i,e_g); H_t=stopgrad(weighted_quantile(h_i | terrain evidence,q=0.90)); Lmu5=mean_i p_roof_i*relu((H_t+m_rt)-h_i)^2`

Formula validity: PARTIAL. It is roof-side only and matches the height-order precondition, but q=0.90 and p_roof live gradient create escape/saturation risks.

Formula risks: The proxy was zero because existing roof-terrain margins are already positive; p_roof can decrease instead of moving geometry; B6 should not be primary success because it is partly Stage3/evaluator height-sensitive.

Suggested correction: Use stopgrad(p_roof) for geometry-prior smoke, log roof margin distribution, and revise proxy to signed margin percentile/near-violation rather than hard relu only.

Gradient path:

- semantic logits: yes if p_roof is live in proposed formula
- normals: no
- centers/heights: yes through roof height
- confidence/gates: no; terrain reference and gates should be stopgrad
- intended: no, not if the hypothesis is roof-side geometry height correction
- risk: Can lower roof probability instead of fixing roof height; B6 may overstate success.
- stopgrad: Terrain reference must be stopgrad; p_roof should be stopgrad for a geometry-prior smoke.

Gate policy: terrain evidence count/confidence gate plus finite terrain quantile; no GT surface

Gate validity: UNVERIFIED_AND_POSSIBLY_EFFECTIVELY_OFF; expected gate-on rate: unknown; current proxy suggests hard margin violation is almost never active.

Proxy readiness: `PROXY_NEEDS_REVISION`. zero proxy likely indicates margin/proxy failure, not scientific rejection of height relation

Expected Stage3Algo-v1 + Metric-v1 result: primary `h_err`, secondary `vol_ratio, roof_cov`; no-regression gates: B104 ground_cov/support, easy/control F, topology.

### Lmu6 semantic-geometry calibration

Decision: `TARGET_MISMATCH`

Target validity: Lmu6 is intended to target semantic_faces and support_confidence by aligning semantic logits with geometry-derived class evidence.

Evidence precondition: High-confidence primitives should not carry contradictory semantic class and geometry cues into Stage3.

Formula: `proposed: d_roof=relu(tau-(n dot e_g)^2)^2; d_wall=(n dot e_g)^2; d_terrain=(1-abs(n dot e_g))^2; Lmu6=mean stopgrad(conf_i)*(p_roof d_roof+p_wall d_wall+p_terrain d_terrain)`

Formula validity: NO for semantic calibration. This is a semantic-weighted geometry prior unless geometry is teacher-side and logits are the only target.

Formula risks: Both semantic logits and geometry receive gradients, so it is unclear whether it calibrates semantics or changes geometry; proxy correlated positively with F/support, suggesting it measured structured evidence quality rather than contradiction risk.

Suggested correction: For calibration, use KL(stopgrad(s_geom_i) || p_i) or CE from stopgrad geometry pseudo-distribution to semantic logits. For geometry prior, detach p_i and rename the term.

Gradient path:

- semantic logits: yes
- normals: yes in proposed formula
- centers/heights: no
- confidence/gates: confidence is stopgrad
- intended: no for a semantic-calibration hypothesis
- risk: Interpretability risk: semantic and geometry can move together and hide mismatch.
- stopgrad: Must choose: semantic calibration = stopgrad geometry teacher; geometry prior = stopgrad p_i. Current design chooses neither.

Gate policy: confidence/support and entropy thresholds proposed

Gate validity: UNVERIFIED; expected gate-on rate: unknown; must log to avoid selecting only already-good evidence.

Proxy readiness: `PROXY_TARGET_MISMATCH`. proxy likely measures confident structured evidence rather than contradiction

Expected Stage3Algo-v1 + Metric-v1 result: primary `support_cov`, secondary `roof_cov, wall_cov, ground_cov, classwise support`; no-regression gates: all_10 F, easy/control F, roof_complex F, support_cov.

### Lmu7 weak roof-wall hint

Decision: `FORMULA_OK_PROCEED_TO_SINGLE_TERM_SMOKE`

Target validity: Lmu7 targets face_graph / roof-wall adjacency by making predicted roof and wall evidence locally compatible before Stage3 shell assembly.

Evidence precondition: Stage3 needs local roof-like evidence near wall-like evidence with compatible contact height and non-parallel normals.

Formula: `audited smoke formula: select predicted roof-wall local pairs within radius r using stopgrad neighbor selection; Lmu7=mean stopgrad(g_ij)*stopgrad(p_pair_conf)*relu(d_contact(i,j)-m_rw)^2 + lambda_n*relu(abs(n_roof dot n_wall)-eta)^2`

Formula validity: YES if implemented with predicted evidence neighborhoods only and explicit contact distance.

Formula risks: False roof-wall pairs can create wrong adjacency pressure; final Stage3 graph closes many shells, so topology metrics alone may not reveal damage.

Suggested correction: Freeze the explicit pair definition above before smoke. Log valid pair count and pair confidence. Do not use GT roof-wall edges.

Gradient path:

- semantic logits: optional weak semantic gradient only if p_pair_conf is not detached; recommended first smoke detaches pair confidence
- normals: yes through normal compatibility if normals are trainable target
- centers/heights: yes through contact distance
- confidence/gates: no; gates and neighbor selection stopgrad
- intended: yes with recommended stopgrad gates/pair weights
- risk: If pair weights are live, the model can escape by lowering roof/wall confidence instead of fixing contact.
- stopgrad: Stopgrad neighbor selection, pair gate, support/confidence weights. Let only local geometry residual receive gradient in first smoke.

Gate policy: high-confidence roof and wall evidence, support threshold, finite local neighborhood, max pair distance, nonzero valid pair count

Gate validity: UNVERIFIED_BUT_SPECIFIABLE; expected gate-on rate: nonzero on roof-wall-rich cases; must be logged by bid.

Proxy readiness: `PROXY_READY`. proxy uses final Stage3 graph, so smoke must verify it maps back to train-time predicted evidence pairs

Expected Stage3Algo-v1 + Metric-v1 result: primary `roof_wall adjacency support proxy / roof_complex F`, secondary `roof_cov, wall_cov, support_cov, h_err`; no-regression gates: open_edges, non_manifold_edges, easy/control F, roof_cov, wall_cov.

### Lmu8 weak terrain-wall hint

Decision: `GATE_BROKEN`

Target validity: Lmu8 targets wall-ground adjacency and shell closure by making wall-bottom evidence compatible with predicted terrain evidence.

Evidence precondition: Stage3 wall-ground closure needs reliable terrain evidence and a well-defined wall-bottom estimate near that terrain reference.

Formula: `proposed: G_t=stopgrad(local terrain height/support estimate); Lmu8=mean_i stopgrad(g_i)*p_wall_i*relu(abs(h_wall_bottom_i-G_t)-m_wg)^2`

Formula validity: PARTIAL. The target is valid, but wall bottom and local terrain reference are not yet well-defined for train-time primitives.

Formula risks: Can reintroduce terrain negative transfer, especially B104 drift; p_wall can escape; current proxy is zero because Stage3 already reports closed wall-ground adjacency.

Suggested correction: Define wall-bottom from predicted wall primitive lower height quantile and local terrain support. Keep terrain reference and gate stopgrad. Require B104 guard before any smoke.

Gradient path:

- semantic logits: yes through p_wall if live
- normals: no unless wall-bottom depends on geometry normal
- centers/heights: yes through wall bottom height
- confidence/gates: no; terrain reliability gate should be stopgrad
- intended: partly, but terrain risk is high
- risk: Can lower wall probability or move wall bottoms toward unreliable terrain; may revive B104 terrain failure.
- stopgrad: Stopgrad local terrain reference, terrain gate, support weights. Prefer stopgrad(p_wall) for first geometry-only diagnostic if revisited.

Gate policy: stable terrain evidence, high terrain confidence, low entropy, enough local wall support, finite local pair count

Gate validity: GATE_UNVERIFIED_AND_TERRAIN_RISK_HIGH; expected gate-on rate: unknown; may be zero under strict terrain-safe gate.

Proxy readiness: `PROXY_GATE_BROKEN`. proxy uses final closed shell and cannot expose train-time terrain-wall risk

Expected Stage3Algo-v1 + Metric-v1 result: primary `ground_support_cov`, secondary `wall_ground adjacency, ground_cov, support_cov`; no-regression gates: B104 ground_cov/support, terrain y drift, easy/control F, topology.

## Boundary Record

```json
{
  "inspection_only": true,
  "training_started": false,
  "smoke_jobs_launched": false,
  "l_structure_enabled": false,
  "g2_started": false,
  "stage3_modified": false,
  "metric_v1_modified": false,
  "gt_roof_type_used_for_loss": false,
  "gt_roof_partition_used_for_loss": false,
  "gt_final_mesh_used_for_loss": false,
  "gt_semantic_surfaces_used_for_loss": false
}
```
