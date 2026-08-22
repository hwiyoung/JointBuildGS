#!/usr/bin/env python3
"""Write the per-run geometry_eval config for a Phase-D union-curve run.

Every evaluator parameter is copied byte-identically from the sealed A2
template (`run_v2_e7e8.json`); only the arm set (the single delta arm), the
baseline (itself — paired contrasts happen downstream against the sealed
delta=0 rows) and the out_dir change. Non-confirmatory; scientific_verdict null.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEMPLATE = REPO / "configs/p2/journal1_phase_a_v1/run_v2_e7e8.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, help="container path of the delta run root")
    parser.add_argument("--arm", required=True, help="run label, e.g. E8_dx050")
    parser.add_argument("--condition", required=True, choices=("E7", "E8", "E9"))
    args = parser.parse_args()
    cfg = json.load(open(TEMPLATE))
    assert cfg.get("scientific_verdict") is None
    run_root = args.run_root.rstrip("/")
    cfg["stage"] = "D1"
    cfg["task_id"] = "P2-JOURNAL1-PHASE-D-v1"
    cfg["note"] = (
        f"Phase-D union-curve evaluation for {args.arm}: evaluator parameters are "
        "byte-identical to the sealed A2 template; single synthetic-delta arm."
    )
    cfg["arms"] = {args.arm: {
        "dir": f"{run_root}/assets_roofer_input/{args.condition}",
        "lineage": f"Phase-D delta run {args.arm} — {args.condition} chain with synthetic ALS shift (not a real lineage)",
    }}
    cfg["baseline_arm"] = args.arm
    cfg["out_dir"] = f"{run_root}/evaluation"
    out = Path(run_root) / "control/eval_config.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    print(out)


if __name__ == "__main__":
    main()
