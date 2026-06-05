# FC-S6c Lmu5-Lmu8 Smoke Recommendation

Decision scope: recommend single-term smoke eligibility only. Do not launch smoke training from this report.

## Recommended Single-Term Smoke Queue

- `Lmu7`: proceed to single-term smoke, with design-freeze gates and gradient guard.

## Deferred Terms

- `Lmu5`: defer; proxy signal is weak or terrain/topology risk is not isolated enough.
- `Lmu6`: defer; proxy signal is weak or terrain/topology risk is not isolated enough.
- `Lmu8`: defer; proxy signal is weak or terrain/topology risk is not isolated enough.

## Smoke Constraints

- One term per smoke arm only.
- Start from the accepted A8 terrain-off Mutual candidate.
- Keep `L_structure` disabled.
- Keep G2 disabled.
- Do not modify Stage3Algo-v1 or Metric-v1.
- Do not enable M7/M8-style relation hints in combination until their single-term smoke passes.
- Enforce gradient ratio guards: Lmu5-Lmu7 <= 5% of base gradient norm; Lmu8 <= 2%.

## Initial Smoke Order

1. `Lmu7`
