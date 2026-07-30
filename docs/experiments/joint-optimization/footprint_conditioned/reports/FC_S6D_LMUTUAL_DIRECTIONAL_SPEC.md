# FC-S6D L_mutual Directional Specification

## 0. Purpose

This document re-specifies `L_mutual` as a directional semantic-geometry objective.

The key correction is that **joint optimization is not merely adding a product term such as `p_class * geometry_error`**. Joint optimization must specify:

1. final-output target,
2. evidence-level precondition,
3. gradient direction,
4. formula,
5. stop-gradient policy,
6. weight / scale policy,
7. gate / reliability policy,
8. expected Stage3Algo-v1 + Metric-v1 result.

This document is intended to precede all new training, smoke tests, `L_structure`, or G2 runs.

---

## 1. Background and Current Status

### 1.1 Final output elements

The final read-out target is not the primitive field itself. The final target consists of:

| Final output area | Meaning |
|---|---|
| Semantic faces | `RoofSurface`, `WallSurface`, `GroundSurface` |
| Face graph | roof-wall, wall-ground, roof-roof adjacency |
| Shell diagnostics | closure, open edges, non-manifold edges, height, volume |
| Support / confidence | support coverage and confidence of generated semantic faces |

### 1.2 Current empirical state

- Original Mutual did not beat Baseline in final read-out.
- FC-S4 found that active `L_mutual` currently contains only primitive-level wall, roof, terrain, and combined height terms. It lacks relation terms, split height logs, class balancing, confidence gating, and support-aware gating.
- FC-S6b accepted `A8_no_terrain_terms` as the current terrain-off candidate, but not as universal or complete revised `L_mutual`.
- FC-S6c-0 design-to-formula audit found:
  - `Lμ1` and `Lμ2` are formula-valid primitive normal priors but have bidirectional-gradient interpretability risk.
  - `Lμ3` is rejected for now as a standalone terrain normal term.
  - `Lμ4` needs robust terrain height compactness redesign.
  - `Lμ5` needs proxy and gradient-path revision.
  - `Lμ6` is currently a target mismatch if described as semantic calibration.
  - `Lμ7` is the only term currently smoke-ready.
  - `Lμ8` target is valid but gate/proxy are broken or unverified.

---

## 2. Core Design Axes

Each `Lμ` term must be specified along four axes.

| Axis | Question |
|---|---|
| Target axis | Which final-output element is this term targeting? |
| Gradient axis | Is the term semantic→geometry, geometry→semantic, or explicit joint? |
| Safety axis | When should this term be active or gated off? |
| Evaluation axis | Which Stage3Algo-v1 + Metric-v1 outputs should improve or remain stable? |

The target axis and gradient axis are independent. A loss may target `WallSurface` while being semantic→geometry, geometry→semantic, or explicit joint.

---

## 3. Directional Modes

### 3.1 Legacy coupled product

The legacy sketch used:

```text
L_live = Σ_c p_c · e_c
```

This couples semantic probability and geometry error. It has the intended joint-optimization intuition, but it also has ambiguous gradient paths.

Risk:

```text
The model may reduce loss by fixing geometry, or by lowering the corresponding class probability.
```

Therefore legacy live-product terms are kept only as references, not as the formal definition of joint optimization.

---

### 3.2 Semantic→Geometry mode, S→G

Semantic probabilities are teacher weights. Geometry is updated.

```text
L_geo = Σ_c stopgrad(p_c) · e_c
```

Example:

```text
L_wall_geo = mean_i stopgrad(p_wall_i) · gate_wall_i · (n_i · g)^2
```

Use this mode when the claim is:

```text
“If a primitive is semantically wall-like, geometry should become wall-like.”
```

---

### 3.3 Geometry→Semantic mode, G→S

Geometry cue is the teacher. Semantic logits are updated.

```text
s_geom_i = geometry-derived soft class hint
L_semcal = mean_i reliability_i · KL(stopgrad(s_geom_i) || p_i)
```

Use this mode when the claim is:

```text
“If geometry is wall-like, semantic probability should not contradict it.”
```

---

### 3.4 Explicit Joint mode

Joint mutual optimization is defined as the controlled combination of S→G and G→S.

```text
L_joint = L_geo + β · L_semcal
```

This is preferred over raw `p · error` when a clear joint-optimization claim is needed.

---

## 4. A8 Reference and V2 Comparisons

### 4.1 A8 legacy reference

`A8_no_terrain_terms` is the accepted terrain-off reference from FC-S6b. It is not complete revised `L_mutual`.

Approximate form:

```text
L_A8_legacy = λμ · [ αW · p_wall · e_wall + αR · p_roof · e_roof ]
```

where:

```text
e_wall = (n · g)^2

e_roof = ReLU(τ - |n · g|^2)^2
```

A8 should be renamed in the documentation as:

```text
A8_legacy_terrain_off
```

### 4.2 A8_v2_geo

This is not A8 plus an extra loss. It replaces A8’s live product by S→G directional terms.

```text
L_A8_v2_geo = λμ · κgeo · [
  αW · stopgrad(p_wall) · e_wall
+ αR · stopgrad(p_roof) · e_roof
]
```

Question:

```text
Can explicit semantic→geometry geometry priors match or improve the legacy live product?
```

### 4.3 A8_v2_joint

This adds an explicit G→S semantic-calibration channel to `A8_v2_geo`.

```text
L_A8_v2_joint = L_A8_v2_geo + λμ · β · L_semcal
```

where:

```text
L_semcal = mean_i reliability_i · KL(stopgrad(s_geom_i) || p_i)
```

Question:

```text
Does explicit geometry→semantic feedback make joint optimization better than S→G only or legacy live product?
```

---

## 5. Per-Term Directional Specification

### Lμ1. Wall verticality

| Field | Specification |
|---|---|
| Target | Semantic faces / `WallSurface` |
| Precondition | Wall primitives should have normals approximately perpendicular to gravity. |
| Legacy formula | `p_wall · (n · g)^2` |
| S→G formula | `stopgrad(p_wall) · gate_wall · (n · g)^2` |
| G→S formula | `CE(stopgrad(wall_geom_hint), p_wall)` or KL equivalent |
| Joint formula | `Lμ1_geo + βW · Lμ1_sem` |
| Gradient target | S→G: normals; G→S: semantic logits |
| Gate | confidence / entropy / optional support reliability |
| Expected result | stable or improved wall_cov, wall_support_cov; no roof/ground regression |
| Risk | false wall probability pulling non-wall geometry; probability escape in live mode |

### Lμ2. Roof non-wall prior

| Field | Specification |
|---|---|
| Target | Semantic faces / `RoofSurface` |
| Precondition | Roof primitives should not collapse into wall-like normals, while valid sloped roofs should be allowed. |
| Legacy formula | `p_roof · ReLU(τ - |n · g|^2)^2` |
| S→G formula | `stopgrad(p_roof) · gate_roof · ReLU(τ - |n · g|^2)^2` |
| G→S formula | `CE(stopgrad(roof_geom_hint), p_roof)` or KL equivalent |
| Joint formula | `Lμ2_geo + βR · Lμ2_sem` |
| Gradient target | S→G: normals; G→S: semantic logits |
| Gate | confidence / entropy / steep-roof guard |
| Expected result | stable or improved roof_cov, roof_support_cov; no roof-complex regression |
| Risk | steep roof over-penalty; probability escape in live mode |

### Lμ3. Terrain normal stability

| Field | Specification |
|---|---|
| Target | Semantic faces / final `GroundSurface` evidence candidate |
| Precondition | Terrain evidence normals should be horizontal-like, but height must also be stable. |
| Formula status | Formula-valid only for normal precondition. |
| S→G formula | `stopgrad(p_terrain) · terrain_reliable · (1 - |n · g|)^2` |
| Current decision | Reject standalone reintroduction. |
| Expected result if revisited | stable ground_cov and ground_support; no B104 regression |
| Risk | normal-only improvement can hide terrain height drift |

### Lμ4. Terrain height compactness

| Field | Specification |
|---|---|
| Target | final `GroundSurface` height and shell height |
| Precondition | Reliable terrain evidence should form a robust local height cluster. |
| Current issue | Existing terrain-side height term is not robust compactness. |
| Revised formula | `stopgrad(p_terrain) · terrain_reliable · Huber(h - stopgrad(local_terrain_median))` |
| Current decision | Formula needs revision. |
| Expected result | reduced terrain y-drift, B104 ground_cov preserved |
| Risk | wrong terrain cluster can be compacted and made more convincing |

### Lμ5. Split roof-height relation

| Field | Specification |
|---|---|
| Target | Shell diagnostics / height and volume consistency |
| Precondition | Roof evidence should be above a reliable terrain reference. |
| Revised formula | `stopgrad(p_roof) · gate_roof · ReLU((stopgrad(H_terrain) + margin) - h_roof)^2` |
| Proxy | signed roof-terrain margin percentiles, not only hard ReLU violation |
| Gradient target | roof height / center, not terrain reference |
| Current decision | Proxy needs revision. |
| Expected result | stable h_err / vol_ratio without B104 regression |
| Risk | if p_roof live, model can reduce roof probability instead of fixing height |

### Lμ6. Semantic-geometry calibration

| Field | Specification |
|---|---|
| Target | Semantic faces and support/confidence |
| Precondition | Semantic probabilities should not strongly contradict reliable geometry cues. |
| Current issue | Previous formula was semantic-weighted geometry prior, not calibration. |
| G→S formula | `reliability · KL(stopgrad(s_geom) || p)` |
| Geometry-prior alternative | `stopgrad(p_class) · D_geom_class` but then rename as geometry prior |
| Current decision | Target mismatch until rewritten. |
| Expected result | better semantic split and support without F regression |
| Risk | geometry cue can miscalibrate semantic logits if unreliable |

### Lμ7. Weak roof-wall hint

| Field | Specification |
|---|---|
| Target | Face graph / roof-wall adjacency candidate; shell roof-wall gap candidate |
| Precondition | Local roof-like and wall-like evidence should be contact-compatible. |
| Formula | `stopgrad(pair_weight_rw) · [D_contact_rw + λn · D_normal_rw]` |
| Pair weight | predicted roof/wall probability, spatial proximity, confidence/support gate, all stopgrad in first smoke |
| Gradient target | roof-wall local relation geometry |
| Current decision | Formula OK, proceed to single-term smoke after explicit pair/gate implementation |
| Expected result | lower roof-wall risk proxy, no topology or roof/wall regression |
| Risk | false roof-wall pairs can create wrong adjacency pressure |

### Lμ8. Weak terrain-wall hint

| Field | Specification |
|---|---|
| Target | Face graph / wall-ground adjacency candidate; shell wall-ground closure candidate |
| Precondition | Wall-bottom evidence and reliable terrain evidence should be height/contact-compatible. |
| Formula | `stopgrad(pair_weight_tw) · Huber(wall_bottom_height - stopgrad(terrain_ref))` |
| Pair weight | predicted wall/terrain probability, local proximity, terrain reliability gate, all stopgrad in first smoke |
| Gradient target | terrain-wall local relation geometry, initially wall-bottom side more than terrain reference |
| Current decision | Gate broken; do not smoke yet |
| Expected result | closure support improves without B104 terrain drift |
| Risk | loose gate can reintroduce B104-like terrain failure |

---

## 6. Weight and Scale Policy

### 6.1 Definitions

```text
G_base    = median ||∇ L_base||
G_legacy  = median ||∇ L_A8_legacy||
G_geo     = median ||∇ L_A8_v2_geo||
G_semcal  = median ||∇ L_semcal||
G_lmu7    = median ||∇ normalize(Lμ7)||
```

### 6.2 Unit and residual normalization

| Loss family | Unit | Normalization policy |
|---|---|---|
| normal losses | dimensionless | keep in `[0,1]` range or EMA-normalize |
| KL/CE | dimensionless | EMA-normalize and cap gradient ratio |
| height/contact gap | world units | normalize by margin, support threshold, or EMA |
| relation proxy | mixed | normalize by initial EMA and log raw residual |

### 6.3 A8_v2_geo weight

Start with:

```text
λμ = A8-as-run
αW, αR = A8-as-run
κgeo = 1.0
```

Then run gradient-scale audit.

Optional matched-scale follow-up:

```text
κgeo = G_legacy / (G_geo + ε)
```

### 6.4 A8_v2_joint semantic calibration weight

Choose β by gradient ratio, not by a fixed arbitrary value.

```text
β = ρ_sem · G_base / (λμ · G_semcal + ε)
```

Recommended:

```text
ρ_sem ∈ {0.02, 0.05}
```

### 6.5 Lμ7 weight

For smoke:

```text
γ7 = 0.05 · G_base / (G_lmu7 + ε)
```

This enforces:

```text
||∇(γ7 Lμ7)|| / ||∇L_base|| ≈ 5%
```

### 6.6 Lμ8 weight if repaired

Do not set a training weight until gate/pair/reference validity is repaired.

If repaired:

```text
γ8 target gradient ratio <= 2%
```

---

## 7. Required Logging

For all directional audits and screening runs:

```text
loss/raw/*
loss/normalized/*
loss/weighted/*
grad_norm/base
grad_norm/mutual_legacy
grad_norm/mutual_geo
grad_norm/semcal
grad_cosine(mutual, semantic)
grad_cosine(mutual, normal)
grad_cosine(mutual, depth)
gate_rate/*
class_mass/*
semantic_entropy/*
height_quantiles/*
valid_pair_count/lmu7
valid_pair_count/lmu8
```

---

## 8. Experiment Plan

### Phase 0. Spec and inventory

No training.

Tasks:

1. Confirm actual A8 formula and active terms.
2. Confirm A8 weights, warmup, schedule, term masks.
3. Implement or dry-run formulas for `A8_v2_geo` and `A8_v2_joint`.
4. Define gradient audit parameter groups.

Outputs:

```text
A8_ACTIVE_LOSS_TERMS.md
LMUTUAL_DIRECTIONAL_FORMULA_TABLE.csv
```

### Phase 1. No-training gradient-scale audit

No full training.

Compare on same checkpoint/batches:

```text
A8_legacy
A8_v2_geo
A8_v2_joint candidate components
L_semcal raw
Lμ7 raw normalized
```

Outputs:

```text
gradient_scale_audit.csv
recommended_initial_weights.md
```

### Phase 2. Directionality screening

Run short diagnostic training/fine-tuning only.

Arms:

```text
A8_legacy_reference  # existing, no rerun unless needed
A8_v2_geo
A8_v2_joint
```

Evaluate with Stage3Algo-v1 + Metric-v1.

Decision:

| Decision | Meaning |
|---|---|
| GEO_BEATS_LEGACY | detach-based semantic→geometry is better than live product |
| LEGACY_REMAINS_BEST | existing A8 live-product is still best |
| JOINT_BEATS_GEO | explicit joint optimization is useful |
| JOINT_REGRESSES | semantic calibration is unstable or over-weighted |
| NO_DIRECTIONAL_GAIN | directionality change does not matter enough |

### Phase 3. Lμ7 single-term smoke

Run only after Phase 2 selects the directional base.

Arms:

```text
best_directional_base
best_directional_base + Lμ7
```

No L_structure.
No G2.
No Lμ8.
No combined relation hints.

### Phase 4. Deferred term repair

No training until formula/gate/proxy issues are fixed.

```text
Lμ5: signed margin proxy and stopgrad(p_roof)
Lμ6: rewrite as semantic calibration or rename as geometry prior
Lμ8: repair terrain-wall gate/pair/reference
```

---

## 9. Readiness for L_structure

`L_structure` remains blocked until:

1. A directional `L_mutual` candidate is selected, or A8 is explicitly retained as minimal reference.
2. Any accepted Lμ7 addition passes single-term smoke.
3. Candidate preserves B104 ground recovery.
4. Candidate does not regress easy/control, support, or topology.

Only then run:

```text
Baseline / revised L_mutual / Structure-only / revised L_mutual + Structure
```

---

## 10. No-Overclaim Policy

- Do not call A8 complete revised `L_mutual`.
- Do not claim legacy `p·error` is sufficient joint optimization without directionality comparison.
- Do not claim `Lμ7` is useful before smoke.
- Do not discard `Lμ5`, `Lμ6`, or `Lμ8` as scientifically useless; their current status is design/proxy/gate repair.
- Do not start `L_structure` or G2 until the directional `L_mutual` candidate is selected.
