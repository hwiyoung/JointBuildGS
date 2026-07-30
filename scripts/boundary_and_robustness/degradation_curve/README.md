# Degradation-curve drivers

- `degradation_curve_v3.py`: measurement and report producer.
- `degradation_curve_v3_qa.py`: read-only bundle validation. It accepts the frozen manifest's former recovery-script path while checking the moved script bytes.
- `degradation_curve_v3_recovery.py`: recovery helper whose SHA-256 remains unchanged.
- `run_degradation_curve_20260721.sh`: reproducible container wrapper.

Canonical compact outputs are under `docs/experiments/evaluation/degradation_curve/`; figures are under `docs/figs/degradation_curve/`. The historical manifest is preserved without rewriting.
