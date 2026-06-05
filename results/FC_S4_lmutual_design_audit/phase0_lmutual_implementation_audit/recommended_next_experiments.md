# Recommended Next Experiments

## Immediate Recommendation
Do not start M4/M5 retraining until term-level controls and logging are available. M3 is config-only, but it should still be run with audit logging so the result is interpretable.

## Order
1. Add flag-controlled instrumentation with defaults disabled.
2. Run a smoke/cheap diagnostic for M3 (`w_mutual=0.025`) with the same Stage2 data/config except output directory and logging flags.
3. Add term masks or term weights for M4/M5, including split roof-height vs terrain-height logging.
4. Run M5 before M4 because FC-S3 B104 directly implicates ground/terrain drift.
5. Run M4 only as roof/wall class-prior ablation unless a real roof-wall relation term is implemented.

## Guardrails
- Always evaluate B104, B6, B3, B123, B126, B2, B0, B1.
- Reject diagnostics that recover roof coverage by degrading topology or hiding GroundSurface failures.
- Treat G2 as a hypothesis until a 4-way pilot beats Baseline and revised Mutual on final read-out metrics.

## Cheap Diagnostic Length
A 5k-10k diagnostic window is reasonable for first signal if initialized from an existing compatible checkpoint. If restart-only is available, keep the run short and interpret it as directional rather than final.
