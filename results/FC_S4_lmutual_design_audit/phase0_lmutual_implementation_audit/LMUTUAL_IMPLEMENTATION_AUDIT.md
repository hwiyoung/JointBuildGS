# FC-S4 Phase 0: L_mutual Implementation Audit

## Scope
This is an inspection-only audit. No training, Stage2 behavior change, Stage3 change, G2 run, or evidence-file change was performed.

## A. Locate Implementation
- L_mutual is defined in `src/stage2/loss/mutual.py` by `l_mutual()`.
- It is imported and added to total training loss in `src/stage2/train.py`.
- `loss_total = loss_total + w_mutual * loss_mut_total` is applied only when `w_mutual > 0`, `it >= mutual_warmup`, `e_gravity is not None`, and the model has `sem_logits`.
- Phase 2 mutual is enabled by `configs/phase2_mutual.yaml` with `w_mutual=0.1`, `mutual_warmup=10000`, `mutual_tau=0.15`, `mutual_height_th=0.15`, and `mutual_mode=full`.

## B. Implemented Terms
The active implementation contains four primitive-level terms: wall verticality, roof non-wall/horizontal-enough normal prior, terrain/ground horizontality, and a combined roof/terrain height relation. It does not include roof-wall relation or ground-wall relation terms.

See `lmutual_terms_implemented.csv` for formula, sign, masks, coordinate convention, weighting, detach behavior, reduction, logging, and failure modes.

## C. Sketch vs Code
The core formula and warmup match the sketch documents found in `docs/EXPERIMENT_PLAN.md`, `docs/RESEARCH_CONTEXT.md`, and `docs/REPORT_FOR_ADVISOR.md`. The main mismatches are:
- Relation terms requested by FC-S3/FC-S4 are not implemented.
- Code comment wording for the roof term conflicts with the formula: the formula penalizes wall-like roof normals; a comment says roofs should not be flat.
- Term-level weights exist in `l_mutual()` defaults but are not exposed by `train.py` config.
- No class balancing, confidence gating, or support-aware gating exists.

See `sketch_vs_code_alignment.csv`.

## D. Config and Schedule
- Phase2 Baseline: `w_mutual=0.0`.
- Phase2 Mutual: `w_mutual=0.1`, starts at step `10000`, no ramp, no decay.
- Phase2 Both: same mutual config plus structure loss.
- No bid/scene-specific overrides were found.
- Gravity file sets `e_gravity=[0,1,0]`; the height axis is Y and implemented height is `-center_y`.

See `lmutual_config_schedule.csv`.

## E. Existing Logs
Available mutual run scalar tags include 22 tags, including base losses, `loss/mutual`, `loss/mutual_vert`, `loss/mutual_slope`, `loss/mutual_horiz`, and `loss/mutual_height`.

Missing logs include classwise gradient norms, relation-specific losses, split roof/terrain height losses, gradient cosine with base losses, and per-class evidence statistics during training. See `existing_log_tags.csv` and `missing_logging_requirements.md`.

## F. Instrumentation Plan
Add optional logging behind flags only. Recommended flags and scalar names are in `instrumentation_plan.md`. The highest-value additions before retraining are split height terms, class probability masses, classwise semantic entropy, ground/roof/wall height quantiles, and occasional gradient norm/cosine probes.

## G. Ablation Feasibility
- M3 (`w_mutual=0.25x`) is config-only.
- M4 (roof-wall only) requires code changes because current code has no roof-wall relation term and train config does not expose term masks.
- M5 (remove ground/terrain term) requires code changes for a clean ablation because terrain horizontality and terrain height cannot be independently disabled from config.
- M9 class-balanced mutual requires code changes.
- M10 late-start mutual is config-only for a hard late start.
- M11 gated ground term requires code changes.

See `ablation_feasibility_matrix.csv`.

## Highest-Risk Terms
1. Ground/terrain horizontality and terrain side of height relation: FC-S3 B104 showed ground-y distribution changes can fully recover or destroy ground coverage.
2. Combined height relation: roof and terrain height are not separately logged or separately weighted.
3. Roof term interpretation: implementation is formula-consistent but comment wording is ambiguous; this matters for M4 naming.

## Readiness
It is not clean to start M4/M5 retraining yet. It is technically safe to run a cheap M3 or M10 diagnostic because they are config-only, but it should be done only after adding flag-controlled audit logging; otherwise the result will remain hard to interpret.
