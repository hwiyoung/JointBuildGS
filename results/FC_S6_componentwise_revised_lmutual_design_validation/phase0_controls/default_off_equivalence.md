# FC-S6 Default-Off Equivalence

- Status: `PASS`
- Manual legacy formula absolute difference: `0.0`
- Explicit default controls absolute difference: `0.0`
- Scope: direct tensor check of `src/stage2/loss/mutual.py`; no training, Stage3, Metric-v1, L_structure, or G2 was invoked.
- Interpretation: FC-S6 controls are default-on/default-one for existing terms and do not change the legacy loss when left at defaults.
