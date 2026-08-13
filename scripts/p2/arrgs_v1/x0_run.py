#!/usr/bin/env python3
"""ARRGS X0 orchestrator: synthetic plumbing validation (the kill gate).

Runs the pre-registered grid:
  box_main / gable_main        -- P-X0-1 (photo-only occupancy convergence)
  gable_sym                    -- P-X0-2 (symmetric init must fail: no gradient)
  gable_noanneal               -- P-X0-3 (no annealing -> undecided residue)
  gable_perturb                -- plane recovery under jittered init

Writes one summary JSON with the P-X0 verdicts. scientific_verdict stays null.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arrgs_train import run  # noqa: E402

OUT_ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1/P2-ARRGS-X0-v1")

BASE = {
    "iters": 4000,
    "gaussians": 6000,
    "snapshots": [0, 50, 100, 250, 500, 1000, 2000, 3000, 4000],
    "holdout": True,
}

RUNS = [
    ("box_main", {"scene": {"type": "synthetic", "kind": "box"}}),
    ("gable_main", {"scene": {"type": "synthetic", "kind": "gable"}}),
    ("gable_sym", {"scene": {"type": "synthetic", "kind": "gable"}, "o_init": "sym"}),
    ("gable_noanneal", {"scene": {"type": "synthetic", "kind": "gable"}, "anneal": False}),
    ("gable_perturb", {"scene": {"type": "synthetic", "kind": "gable", "perturb": 3.0}}),
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    summary = {}
    for name, extra in RUNS:
        if only and name != only:
            continue
        cfg = dict(BASE)
        cfg.update(extra)
        cfg["out_dir"] = str(OUT_ROOT / "runs" / name)
        print(f"[x0] ===== {name} =====", flush=True)
        try:
            summary[name] = run(cfg)
        except Exception as e:  # keep the grid going; failures are data
            import traceback
            traceback.print_exc()
            summary[name] = {"error": str(e)}

    if not only:
        verdict = {}
        gm = summary.get("gable_main", {})
        bm = summary.get("box_main", {})
        verdict["P-X0-1_photo_only_occupancy"] = {
            "pass": (gm.get("occupancy_accuracy", 0) == 1.0
                     and bm.get("occupancy_accuracy", 0) == 1.0
                     and gm.get("ghost_faces", 99) == 0),
            "gable_acc": gm.get("occupancy_accuracy"),
            "box_acc": bm.get("occupancy_accuracy"),
            "ghost": [bm.get("ghost_faces"), gm.get("ghost_faces")],
            "missing": [bm.get("missing_faces"), gm.get("missing_faces")],
        }
        sym = summary.get("gable_sym", {})
        verdict["P-X0-2_sym_init_fails"] = {
            "pass": sym.get("occupancy_accuracy", 1.0) < 1.0
                    or sym.get("o_undecided", 0) > 0,
            "acc": sym.get("occupancy_accuracy"),
            "undecided": sym.get("o_undecided"),
        }
        na = summary.get("gable_noanneal", {})
        verdict["P-X0-3_noanneal_undecided"] = {
            "pass": na.get("o_undecided", 0) >= 1,
            "undecided": na.get("o_undecided"),
        }
        pert = summary.get("gable_perturb", {})
        rec = pert.get("plane_recovery", [])
        verdict["plane_recovery_deg_m"] = rec
        verdict["kill_gate_pass"] = bool(verdict["P-X0-1_photo_only_occupancy"]["pass"])
        summary["_verdict"] = verdict
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    out = OUT_ROOT / ("x0_summary.json" if not only else f"x0_summary_{only}.json")
    json.dump(summary, open(out, "w"), indent=1, default=str)
    print("[x0] summary ->", out)
    if not only:
        print(json.dumps(summary["_verdict"], indent=1, default=str))


if __name__ == "__main__":
    main()
