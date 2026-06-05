# FC-S6D Directional Decision

## Decision Label

`KEEP_A8_LEGACY` as the current live-product reference only.

This is not a claim that A8 is the final directional design. It means no directional Stage3 evidence exists yet for `A8_v2_geo` or `A8_v2_joint`.

## Evidence State

- A8 existing Stage3Algo-v1 + Metric-v1 rows were copied from FC-S6b/FC-S6 phase outputs.
- `A8_v2_geo` is config-preparable because existing `mutual_mode=sem2geo` detaches semantic probabilities.
- Runnable geo config: `configs/fc_s6d/A8_v2_geo.yaml`.
- `A8_v2_joint` is not train-ready because the explicit KL semantic calibration term is not implemented in the Stage2 training path.
- Joint stub is deliberately blocked at `configs/fc_s6d/A8_v2_joint_BLOCKED.yaml` to avoid accidentally running a geo-only substitute.
- No FC-S6D training, Stage3 evaluation, L_structure, or G2 run was launched.

## Phase 3 Recommendation

- Do not run Lmu7 yet.
- If directional screening is launched next, test `A8_v2_geo` first because it is the minimal directionality change and is supported by the existing config path.
- Add Lmu7 single-term smoke only after either A8 legacy is explicitly retained after screening or `A8_v2_geo`/`A8_v2_joint` is selected by Stage3Algo-v1 + Metric-v1.

## Blockers Before A8_v2_joint

- Implement roof/wall `L_semcal = KL(stopgrad(s_geom)||p)` behind a default-off flag.
- Re-run default-off equivalence.
- Re-run the no-training gradient-scale audit after implementation.
