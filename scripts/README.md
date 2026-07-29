# Reproducible repository scripts

`scripts/` contains reusable, container-executed repository drivers. Experiment-specific drivers live under [`experiments/`](experiments/README.md); repository maintenance utilities stay directly under `scripts/` when they apply across research families.

Phase-local scripts remain under `phases/<phase>/scripts/` only when their exact path or byte hash is part of a frozen run, lock, or Git-ref reproducibility contract.
