# Missing Logging Requirements

Existing TensorBoard logs include base losses and four implemented mutual components, but they are not enough to diagnose FC-S3 failures before M3/M4/M5 retraining.

## Missing Scalars
- Classwise gradient norms for roof, wall, ground.
- Gradient norm per loss family: render/photo, depth, normal, semantic, mutual.
- Gradient cosine between L_mutual and base geometry losses: depth, normal, normal-consistency, and photo/render.
- Separate roof-wall relation and ground-wall relation losses. These are not just missing logs; the active terms are not implemented.
- Split height losses: roof-height and terrain-height are currently logged only as one combined `loss/mutual_height`.
- Per-class semantic entropy during training.
- Primitive class probability mass by class during training.
- Ground/roof/wall center height distributions during training.
- Evidence/export distribution snapshots by class after rendering/export, especially ground y quantiles.
- Support acceptance/rejection by class against the eventual Stage3 read-out surface, if feasible as an offline diagnostic.

## Why This Blocks Clean Ablation Interpretation
M3 can be run by changing `w_mutual`, but without these logs it will be unclear whether improvement came from weaker ground pressure, weaker height pressure, reduced semantic conflict, or simply less perturbation overall. M4/M5 require code changes, so their logs should be added at the same time behind flags.
