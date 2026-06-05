# FC-S5 Loss Design Spec v2: Loss Ledger for Final-Readout-Aligned Mutual and Structure Loss

## 0. Why this v2 exists

The previous FC-S5 design document was directionally correct but too long to quickly answer:

- What losses are in the system?
- What is each formula?
- What is each weight?
- Which final semantic surface graph / shell target does each loss serve?
- Which terms are implemented now, which are proposed, and which are deferred?

This v2 puts a compact **loss ledger** first. The ledger is the contract for future experiments.

Core rule:

> Every loss term must explicitly answer: **How does this term contribute to final semantic surface graph / shell read-out?**

A term is not accepted merely because it is geometrically plausible or semantically intuitive.

---

## 1. Final read-out target

The final model is not a primitive cloud. The target is an explicit semantic 3D building model:

```text
semantic_faces.json
  RoofSurface polygons
  WallSurface polygons
  GroundSurface polygons

face_graph.json
  RoofSurface-WallSurface adjacency
  WallSurface-GroundSurface adjacency
  RoofSurface-RoofSurface adjacency

shell_diagnostics.json
  open edges
  non-manifold edges
  face orientation
  closure
  height / volume diagnostics
```

Terminology policy:

```text
Stage2 primitive class: roof / wall / terrain
Stage3 final semantic face: RoofSurface / WallSurface / GroundSurface
```

Use **terrain evidence** for primitive-level evidence. Use **GroundSurface** only for the final Stage3 building face.

---

## 2. Loss ledger overview

### 2.1 Global total loss

Use the following hierarchy:

```text
L_total =
    λ_photo     L_photo
  + λ_depth     L_depth
  + λ_normal    L_normal
  + λ_sem       L_semantic
  + λ_reg       L_regularization
  + λ_mutual    normalize(L_mutual)
  + λ_structure normalize(L_structure)
```

Where:

```text
L_mutual = primitive evidence alignment
L_structure = soft surface graph / shell surrogate
Stage3 = hard explicit read-out, not a training loss
```

### 2.2 Recommended starting weights

These are starting points, not final values.

| Weight | Default / starting value | Notes |
|---|---:|---|
| `λ_photo` | existing baseline value | Preserve current baseline unless audit shows imbalance. |
| `λ_depth` | existing baseline value | Log grad norm and conflict with mutual/structure. |
| `λ_normal` | existing baseline value | Log classwise normal error. |
| `λ_sem` | existing baseline value | Log entropy and class mass. |
| `λ_reg` | existing baseline value | Keep stable. |
| `λ_mutual` | diagnostic grid `{0.025, 0.05, 0.1}` | Current original is `0.1`; M3 is `0.025`. |
| `λ_structure` | initially `0.0` | Do not enable until revised mutual is stable. Later grid `{0.01, 0.025, 0.05}`. |

Within `L_mutual` and `L_structure`, normalize each term before weighting:

```text
normalize(L_k) = L_k / (EMA_initial(L_k) + eps)
```

or use gradient-norm based scaling for diagnostics.

---

## 3. Base reconstruction loss ledger

| ID | Loss | Formula sketch | Updates | Final read-out contribution | Weight / schedule | Required logs | Risk / guard |
|---|---|---|---|---|---|---|---|
| B1 | Photo/render loss | `L_photo = photometric_residual(render(scene), images)` | appearance / opacity / primitive parameters | Prevents structure losses from hallucinating geometry not supported by images. | Existing baseline | `loss/photo`, `grad_norm/photo` | Can conflict with geometric priors; log grad cosine with mutual/structure. |
| B2 | Depth loss | `L_depth = ρ(z_pred - z_ref)` | primitive centers / depth | Places surface candidates at observed geometry. Supports F, chamfer, h_err. | Existing baseline | `loss/depth`, `grad_norm/depth`, `grad_cosine(mutual, depth)` | Mutual/structure may move geometry away from depth. |
| B3 | Normal loss | `L_normal = 1 - |n_pred · n_ref|` | primitive normals | Stabilizes plane fitting for RoofSurface/WallSurface/Terrain evidence. | Existing baseline | `loss/normal`, `grad_norm/normal` | Can conflict with class priors if pseudo-normal/noisy. |
| B4 | Semantic loss | `L_sem = CE(p_i, y_i)` or equivalent | semantic logits | Enables Stage3 evidence split into roof/wall/terrain. | Existing baseline | `loss/semantic`, entropy by class | Overconfidence without support can harm final read-out. |
| B5 | Regularization | project-specific | scale / opacity / stability | Prevents degenerate primitives that corrupt surface support. | Existing baseline | primitive count/scale stats | Too strong may remove useful evidence. |

---

## 4. Revised `L_mutual`: primitive evidence alignment ledger

`L_mutual` should not directly build the graph/shell. It should make primitive evidence safe and useful for Stage3 and `L_structure`.

General form:

```text
L_mutual =
    w_wall        L_wall_vertical
  + w_roof        L_roof_nonwall
  + w_terrain_n   L_terrain_normal
  + w_terrain_h   L_terrain_height_compact
  + w_hroof       L_height_roof
  + w_hterrain    L_height_terrain_optional
  + w_semcalib    L_sem_geom_calib_optional
  + w_rw_hint     L_roof_wall_local_hint_optional
  + w_tw_hint     L_terrain_wall_local_hint_optional
```

Recommended initial status for FC-S5 diagnostics:

```text
Enable existing primitive terms only.
Add logging and term-level controls first.
Do not enable new relation hints yet.
Run M3, M5, M10 before relation prototypes.
```

### 4.1 `L_mutual` term ledger

| ID | Loss term | Formula sketch | Updates | Final semantic surface graph / shell contribution | Initial weight / status | Guardrails | Required logs |
|---|---|---|---|---|---|---|---|
| M1 | Wall verticality | `Σ stopgrad(p_i^wall) gate_i^wall (n_i·g)^2 / Z_w` | normals / geometry | Makes wall evidence fit WallSurface plane estimation; supports wall_cov, wall_support, roof-wall adjacency wall side. | Existing term; keep but expose weight | Gate by wall confidence and entropy; reject if easy wall cases regress. | `loss/mutual_wall_vertical`, `mutual/mass_wall`, `grad_norm/mutual_wall` |
| M2 | Roof non-wall normal prior | `Σ stopgrad(p_i^roof) gate_i^roof ReLU(τ_min - |n_i·g|)^2 / Z_r` | normals / geometry | Prevents roof evidence from becoming wall-like; helps Stage3 split RoofSurface vs WallSurface evidence. | Existing term; verify formula/comment | Must not penalize valid sloped roofs. | `loss/mutual_roof_nonwall`, roof entropy, roof height quantiles |
| M3 | Terrain normal stability | `Σ stopgrad(p_i^terrain) gate_i^terrain (1-|n_i·g|)^2 / Z_t` | normals / geometry | Provides terrain evidence normal stability for final GroundSurface candidate. | Existing term; high risk | Gate by terrain mass, entropy, reliability. B104 is mandatory regression gate. | `loss/mutual_terrain_normal`, `mutual/mass_terrain`, terrain entropy |
| M4 | Terrain height compactness | `m_t=stopgrad(weighted_median(h_i,p_i^terrain gate_i)); Σ stopgrad(p_i^terrain) gate_i Huber(h_i-m_t)/Z_t` | centers / height | Prevents terrain evidence vertical drift, stabilizing Stage3 GroundSurface height read-out. | Proposed / replace risky mean-like behavior | Use robust median/quantile; skip if terrain mass too low. | terrain p10/median/p90, `loss/mutual_terrain_height` |
| M5 | Split roof height relation | `q_r=roof_high_quantile; q_t=terrain_med; ReLU(margin-(q_r-stopgrad(q_t)))^2` | roof height / centers | Maintains roof-over-terrain ordering without pulling terrain incorrectly. | Proposed split from current combined height | Prefer roof-side gradient first; terrain-side optional. | `loss/mutual_height_roof`, `loss/mutual_height_terrain` |
| M6 | Semantic-geometry calibration | `Σ r_i KL(stopgrad(s_geom_i) || p_i)` | semantic logits | Reduces semantic/geometry contradiction, stabilizing Stage3 roof/wall/terrain split. | Optional; disabled initially | Geometry cue can be wrong; low weight and reliability gate. | `loss/mutual_sem_geom_calib`, entropy by class |
| M7 | Roof-wall local hint | `Σ a_ij^rw [D_normal_rw(i,j)+D_height_rw(i,j)]`; `a_ij^rw=stopgrad(p_i^roof p_j^wall) spatial_gate conf_gate` | local primitive geometry | Provides weak local compatibility so roof/wall evidence can later form adjacency. Does not create hard adjacency. | Future prototype; disabled initially | False pair risk; spatial/support/confidence gate; small weight. | `loss/mutual_roof_wall_relation`, pair count |
| M8 | Terrain-wall local hint | `Σ a_ij^tw D_height_tw(i,j)`; `a_ij^tw=stopgrad(p_i^terrain p_j^wall) spatial_gate conf_gate terrain_reliability` | local primitive height / geometry | Provides weak local compatibility for future WallSurface-GroundSurface closure. | Future prototype; disabled initially | B104 terrain drift risk; terrain reliability gate mandatory. | `loss/mutual_terrain_wall_relation`, terrain reliability |
| M9 | Class balancing | `reweight terms by inverse/effective class mass` | loss weights | Prevents roof/wall/terrain imbalance from dominating mutual gradients. | Proposed; disabled until logged | Can suppress useful majority-class signal. | class mass, classwise grad norms |
| M10 | Confidence/support gating | `gate_i = f(confidence, entropy, support_proxy)` | loss masks / weights | Prevents unreliable primitives from becoming strong structure signals. | Proposed; diagnostic | Gate can collapse learning if too strict. | gate rate, skipped term counts |

### 4.2 Stop-gradient policy for `L_mutual`

Use `stopgrad` to make teacher/student direction explicit.

| Direction | Example | Why |
|---|---|---|
| Geometry cue → semantic calibration | `KL(stopgrad(s_geom_i) || p_i)` | Geometry cue is a fixed teacher; only semantic logits update. |
| Semantic confidence → geometry prior | `stopgrad(p_i^class) * D_class(n_i,c_i)` | Semantic probability selects the prior; geometry updates. |
| Avoid ambiguous two-way terms | avoid raw `KL(s_geom_i || p_i)` with both sides active | Otherwise semantic and geometry can co-adapt to lower proxy loss without improving read-out. |

---

## 5. `L_structure`: soft surface graph / shell surrogate ledger

`L_structure` is not another local primitive prior. It should optimize soft surrogates of the final graph/shell that Stage3 will harden into explicit outputs.

General form:

```text
L_structure =
    u_group      L_surface_grouping
  + u_support    L_surface_support
  + u_rw_adj     L_roof_wall_adjacency
  + u_wt_close   L_wall_terrain_closure
  + u_shell      L_shell_proxy
  + u_conf       L_low_support_confidence
  + u_roof_safe  L_roof_boundary_preservation
```

Status:

```text
Do not enable L_structure in FC-S5 diagnostics.
Implement only after revised mutual candidate recovers baseline stability.
Then run 4-way pilot: Baseline / Revised Mutual / Structure-only / Revised Mutual+Structure.
```

### 5.1 `L_structure` term ledger

| ID | Loss term | Formula sketch | Updates | Final semantic surface graph / shell contribution | Initial weight / status | Guardrails | Required logs |
|---|---|---|---|---|---|---|---|
| S1 | Soft surface grouping | `Σ_i,s q_is dist(c_i, plane_s)^2 + q_is normal_diff(n_i,n_s)^2 + q_is CE(p_i, sem_s)` | primitive geometry / soft assignment | Encourages primitives to form coherent RoofSurface/WallSurface/Terrain surface candidates. | Future; disabled | Avoid destroying ridge/valley boundaries. | group count, group residual, q entropy |
| S2 | Surface support coverage | `Σ_s area_s mean_m [1 - support_s(x_m)]` | candidate support/confidence | Directly targets support_cov and face confidence. | Future; disabled | Support proxy must match Metric-v1 support audit. | surface support, rejection proxy |
| S3 | Roof-wall adjacency proxy | `Σ_r,w A_rw gap(roof_boundary_r, wall_top_w)^2` | surface candidate geometry | Creates soft conditions for face_graph RoofSurface-WallSurface adjacency. | Future; disabled | Wrong pair risk; gate by footprint/spatial/support. | `A_rw`, roof-wall gap |
| S4 | Wall-terrain closure proxy | `Σ_w A_wt dist(wall_bottom_w, terrain_plane)^2` | wall/terrain candidate geometry | Creates soft conditions for final WallSurface-GroundSurface closure. | Future; disabled | Terrain drift risk; B104 mandatory gate. | wall-bottom terrain gap, terrain reliability |
| S5 | Shell open-boundary proxy | `Σ_w len(bottom_w)(1-max_t A_wt)+Σ_r len(boundary_r)(1-max_w A_rw)` | candidate boundary compatibility | Reduces open-edge risk before Stage3 shell diagnostics. | Future; disabled | Soft proxy may not match true topology. | unmatched boundary length |
| S6 | Low-support confidence calibration | `Σ_s C_s ReLU(τ_support - support_s)^2` | surface confidence | Prevents low-support candidate faces from becoming high-confidence final faces. | Future; disabled | Confidence collapse. | support-confidence correlation |
| S7 | Roof boundary preservation | penalize merging across strong normal/height discontinuities | grouping weights | Protects meaningful ridge/valley structure while controlling over-fragmentation. | Future; disabled | Too conservative grouping. | boundary score, merge weights |

---

## 6. Weighting and optimization policy

### 6.1 Do not guess weights from intuition alone

Use this sequence:

```text
1. Add term-level logging and config exposure.
2. Normalize term scales.
3. Log gradient norms and gradient cosines.
4. Run small fixed-weight diagnostics.
5. Select by final Stage3Algo-v1 + Metric-v1 read-out metrics.
6. Only then consider adaptive weighting or gradient surgery.
```

### 6.2 Diagnostic grids

For FC-S5:

```text
λ_mutual ∈ {0.025, 0.05, 0.1}
terrain terms ∈ {on, off, gated}
schedule ∈ {current warmup=10000, late-start, ramped}
```

For future L_structure:

```text
λ_structure ∈ {0.01, 0.025, 0.05}
only after revised mutual is safe
```

### 6.3 Selection gates

A candidate is accepted only if:

```text
all-10 mean F >= baseline or practically tied
B104 ground_cov recovers or terrain drift decreases
easy/control split does not regress
hard diagnostic split improves or remains interpretable
ground_support_cov improves or does not regress
topology/open/non-manifold edges do not regress
no GroundSurface failure is hidden or excluded
```

---

## 7. Required logging

### 7.1 Mutual scalar logs

```text
loss/mutual_wall_vertical
loss/mutual_roof_nonwall
loss/mutual_terrain_normal
loss/mutual_terrain_height
loss/mutual_height_roof
loss/mutual_height_terrain
loss/mutual_sem_geom_calib
loss/mutual_roof_wall_relation
loss/mutual_terrain_wall_relation
loss/mutual_total
```

Keep legacy aliases:

```text
loss/mutual_vert
loss/mutual_slope
loss/mutual_horiz
loss/mutual_height
```

### 7.2 Class stats

```text
mutual/mass_roof
mutual/mass_wall
mutual/mass_terrain
entropy/roof
entropy/wall
entropy/terrain
height/roof_p10, height/roof_median, height/roof_p90
height/wall_p10, height/wall_median, height/wall_p90
height/terrain_p10, height/terrain_median, height/terrain_p90
```

### 7.3 Gradient diagnostics

```text
grad_norm/photo
grad_norm/depth
grad_norm/normal
grad_norm/semantic
grad_norm/mutual
grad_norm/structure

grad_cosine(mutual, photo)
grad_cosine(mutual, depth)
grad_cosine(mutual, normal)
grad_cosine(mutual, semantic)
grad_cosine(structure, depth)
grad_cosine(structure, normal)
grad_cosine(mutual, structure)
```

Run gradient probes only occasionally and behind flags.

---

## 8. FC-S5 experiment sequence

### Phase 1: Instrumentation only

Add optional flag-controlled logging. Default behavior must remain unchanged.

### Phase 2: M3 cheap diagnostic

```text
M3: w_mutual = 0.025
```

Question:

```text
Was original w_mutual=0.1 too strong?
```

### Phase 3: M5 terrain-off or terrain-gated diagnostic

```text
M5: disable or gate terrain normal / terrain height / terrain-side height relation
```

Question:

```text
Does B104-like terrain drift recover?
```

### Phase 4: M10 late-start / ramp

```text
M10: later mutual start or linear ramp
```

Question:

```text
Does delaying mutual avoid early geometry disturbance?
```

### Phase 5: Relation hint prototype

Only after M3/M5/M10 identifies a safe revised mutual candidate.

```text
roof-wall weak local hint
terrain-wall weak local hint
```

### Phase 6: L_structure prototype

Only after revised mutual recovers baseline stability.

```text
soft grouping
surface support
adjacency proxy
closure proxy
shell proxy
low-support confidence
```

### Phase 7: 4-way pilot

```text
Baseline
Revised Mutual
Structure-only
Revised Mutual + Structure
```

---

## 9. No-overclaim policy

Forbidden:

```text
Original L_mutual improves final semantic building model.
```

Allowed:

```text
Original L_mutual was not aligned enough with final read-out metrics.
Revised L_mutual is tested as primitive evidence alignment.
L_structure remains a hypothesis for soft surface graph/shell alignment.
Structure contribution must be proven by 4-way ablation.
```

---

## 10. One-page summary

```text
L_base:
  keep observed geometry/semantics/rendering stable.

L_mutual:
  make primitive evidence safe for Stage3 read-out.
  Focus on terrain-safe, gated, class-balanced semantic-geometric alignment.

L_structure:
  make primitive evidence form soft surface groups, support, adjacency, closure, and shell proxies.

Stage3:
  harden the evidence into explicit RoofSurface / WallSurface / GroundSurface, face_graph, shell_diagnostics.

Every loss term must map to a final read-out target and pass guardrails on B104, B6, B3/B123/B126, and easy/control bids.
```
