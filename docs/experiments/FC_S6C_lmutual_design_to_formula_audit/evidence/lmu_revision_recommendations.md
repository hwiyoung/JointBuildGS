# Lmu Revision Recommendations

## Formula-Valid Terms

- `Lmu1` and `Lmu2` are formula-valid as primitive normal priors, but their current full-mode bidirectional gradients should be treated as an interpretability risk. They remain acceptable in the current A8 candidate because they have already been exercised by FC-S6 arms.
- `Lmu3` is formula-valid only for terrain normal stability. It is not a full GroundSurface solution and should not be reintroduced as a standalone terrain term under the current evidence.
- `Lmu7` is formula-valid only after freezing an explicit predicted-evidence roof-wall pair definition, contact-gap residual, and support/confidence gates.

## Terms Needing Revision

- `Lmu4` needs a robust local terrain compactness formula. The current one-sided threshold/quantile height term can compact the wrong terrain cluster.
- `Lmu5` needs proxy and gradient-path revision. Use `stopgrad(p_roof)` for a geometry-prior smoke, and replace the saturated hard violation proxy with continuous signed roof-terrain margin statistics.
- `Lmu6` needs a target rewrite. If it is semantic calibration, use a teacher-side geometry pseudo-distribution with KL/CE into semantic logits. If it is a geometry prior, detach semantic probabilities and rename the hypothesis.
- `Lmu8` needs gate and proxy revision before smoke. The current Stage3 graph proxy is zero because Stage3 already closes wall-ground adjacency, and the train-time terrain-wall pair definition is not verified.

## Gate Issues

- `Lmu1`/`Lmu2` are currently soft always-on. This is acceptable for existing A8 continuation but not ideal for a new claim; log class confidence/support if revisited.
- `Lmu3`/`Lmu4` terrain gates are the main risk path. Terrain terms must have confidence/support/entropy gates plus B104 terrain y-drift logs.
- `Lmu5` may be effectively always off because the hard roof-terrain margin is already satisfied.
- `Lmu7` gate is unverified but specifiable; valid pair count is the key first log.
- `Lmu8` gate is unverified and may be either always off under strict terrain reliability or unsafe if loose.

## Proxy Issues

- `Lmu5`: `PROXY_NEEDS_REVISION`; all-zero proxy means no decision can be made.
- `Lmu6`: `PROXY_TARGET_MISMATCH`; positive correlation with F/support means the current proxy is likely measuring quality rather than contradiction.
- `Lmu7`: `PROXY_READY`; it aligned with risk, but smoke must verify the train-time pair signal.
- `Lmu8`: `PROXY_GATE_BROKEN`; zero proxy and closed Stage3 shells make it unusable.
