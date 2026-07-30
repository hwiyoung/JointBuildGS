"""8.2 Loop 4: Phase 1 group churning (n_groups CV, consecutive change).

Compare Phase 1 Structure/Both vs Phase 2 reported values:
  Phase 2 §14.4: n_groups CV 2.01%, consecutive change 1.17/16,773 = 0.007%
"""
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
import numpy as np
from pathlib import Path

runs = {
    "Phase 1 Structure": "results/phase1_structure/run/tb",
    "Phase 1 Both":      "results/phase1_ablation/run/tb",
}

print(f"{'run':<22} {'mean':>8} {'std':>8} {'CV':>7} {'Δstep_mean':>11} {'Δstep_max':>10}")
print("-" * 80)

for name, tb in runs.items():
    p = Path(tb)
    if not p.exists():
        print(f"{name}: tb not found"); continue
    ea = EventAccumulator(str(p), size_guidance={'scalars': 0})
    ea.Reload()
    if 'stats/n_groups' not in ea.Tags()['scalars']:
        print(f"{name}: no stats/n_groups"); continue
    events = ea.Scalars('stats/n_groups')
    vals = np.array([e.value for e in events])
    steps = np.array([e.step for e in events])
    # Skip 0 entries (warmup)
    nonzero = vals > 0
    vals = vals[nonzero]; steps = steps[nonzero]
    if vals.size < 3:
        print(f"{name}: too few non-zero")
        continue
    mean = vals.mean()
    std = vals.std()
    cv = std / mean * 100 if mean > 0 else 0
    diff = np.abs(np.diff(vals))
    print(f"{name:<22} {mean:>8.0f} {std:>8.1f} {cv:>6.2f}% {diff.mean():>11.2f} {diff.max():>10.2f}")

print("\nReference (Phase 2, CLAUDE.md §14.4):")
print("  n_groups CV: 2.01%   consecutive change: 1.17/16773 = 0.007%")
