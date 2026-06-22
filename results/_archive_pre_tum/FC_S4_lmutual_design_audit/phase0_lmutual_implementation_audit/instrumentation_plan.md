# Instrumentation Plan

All instrumentation should be optional and flag-controlled. Default training behavior must remain unchanged.

## Proposed Config Flags
- `mutual_audit_logging: false` default.
- `mutual_grad_audit_every: 0` default disabled; positive integer enables occasional extra backward/grad probes.
- `mutual_log_class_stats_every: 0` default disabled.
- `mutual_log_evidence_snapshot_every: 0` default disabled, preferably offline/export-side rather than inside training.

## Minimal Scalar Additions
- Per-term L_mutual scalars already present: keep `loss/mutual_vert`, `loss/mutual_slope`, `loss/mutual_horiz`, `loss/mutual_height`.
- Add split height scalars: `loss/mutual_height_roof`, `loss/mutual_height_terrain`.
- If relation terms are added, log `loss/mutual_roof_wall_relation` and `loss/mutual_ground_wall_relation` separately.
- Log class probability mass: `mutual/mass_roof`, `mutual/mass_wall`, `mutual/mass_ground`.
- Log per-class center-height quantiles: ground/roof/wall p10, median, p90 along the gravity height axis.
- Log semantic entropy by class from primitive probabilities.

## Gradient Diagnostics
Run only every N steps and behind `mutual_grad_audit_every`:
- Gradient norm per loss family: render/photo, depth, normal, semantic, mutual.
- Classwise mutual gradient norms for roof/wall/ground masks.
- Gradient cosine between `L_mutual` and `L_depth`, `L_normal`, `L_semantic`, and `L_photo` on shared parameters: normals/quats, centers/means, semantic logits.
- Record skipped diagnostics when gradients are unavailable rather than silently omitting tags.

## Evidence/Export Diagnostics
Prefer offline diagnostics after checkpoint export:
- Rendered evidence class counts, semantic entropy, confidence, normal consistency.
- Ground y quantiles and distance to predicted/GT reference ground plane for audit only.
- Support accepted/rejected distribution by class after Stage3 read-out.

## Safety Rules
- No default behavior change.
- No extra backward pass unless explicitly enabled.
- No GT semantic surfaces or GT roof partitions for Stage2-derived outputs.
- Logs may use GT/reference only in evaluation/audit contexts, never in training loss construction.
