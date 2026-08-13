#!/usr/bin/env python3
"""X0 follow-up: isolate the gable failure factor (observation geometry vs
annealing schedule vs iteration budget). Small matrix, gable only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arrgs_train import run  # noqa: E402

OUT = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1/P2-ARRGS-X0-v1/runs")

HIGH = [[32.0, 26.0, 16]]
HIGH_MED = [[32.0, 26.0, 16], [38.0, 18.0, 8]]

RUNS = [
    ("gable_fix_highonly", {"scene": {"type": "synthetic", "kind": "gable", "rings": HIGH}}),
    ("gable_fix_highmed", {"scene": {"type": "synthetic", "kind": "gable", "rings": HIGH_MED}}),
    ("gable_fix_highmed_8k", {"scene": {"type": "synthetic", "kind": "gable", "rings": HIGH_MED},
                              "iters": 8000,
                              "snapshots": [0, 100, 500, 1000, 2000, 4000, 6000, 8000]}),
    # real-pipeline analog: occupancy init from a (noisy) prior solid, as the
    # ALS proxy does in X1-X4 — the heuristic "below any roofish plane" init is
    # artificially adversarial in the eave slivers
    ("gable_fix_proxyinit", {"scene": {"type": "synthetic", "kind": "gable", "rings": HIGH_MED},
                             "o_init": "proxy"}),
    ("box_fix_highmed", {"scene": {"type": "synthetic", "kind": "box", "rings": HIGH_MED}}),
]

BASE = {"iters": 4000, "gaussians": 6000, "holdout": True,
        "snapshots": [0, 50, 100, 250, 500, 1000, 2000, 3000, 4000]}


def main():
    summary = {}
    for name, extra in RUNS:
        cfg = dict(BASE)
        cfg.update(extra)
        cfg["out_dir"] = str(OUT / name)
        print(f"[x0fix] ===== {name} =====", flush=True)
        try:
            m = run(cfg)
            summary[name] = {k: m.get(k) for k in (
                "occupancy_accuracy", "ghost_faces", "missing_faces",
                "psnr_eval_final", "o_undecided")}
        except Exception as e:
            import traceback
            traceback.print_exc()
            summary[name] = {"error": str(e)}
        json.dump(summary, open(OUT.parent / "x0_gable_fix_summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
