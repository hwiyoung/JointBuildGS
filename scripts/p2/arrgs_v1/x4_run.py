#!/usr/bin/env python3
"""ARRGS X4: confirmed-93 population sweep (technical development, non-confirmatory).

Usage: x4_run.py <shard-idx> <shard-count>   # e.g. 0 2 / 1 2 for two GPUs
Reduced per-building budget (4000 iters, 32 views, scale 0.6) — X1/X2 carry the
qualitative depth; X4 carries the paired statistics.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arrgs_train import run  # noqa: E402

OUT = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1/P2-ARRGS-X4-v1")
LABELS = Path("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
              "P2-JOURNAL1-PHASE-A-v1/labels/selection_confirm_v1.json")
E7_DIR = Path("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
              "P2-JOURNAL1-PHASE-A-v1/a2/assets_roofer_input/E7")
E2_DIR = ("/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_roofer_ox_review_v1/"
          "P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E2")

BASE = {
    "iters": 4000,
    "gaussians": 8000,
    "snapshots": [0, 500, 1000, 2000, 3000, 4000],
    "holdout": True,
    "cam_batch": 3,
    "enable_delta": True,
    "domain_margin": 1.2,
}


def bkey_map():
    m = {}
    for p in E7_DIR.glob("B*_DEBY_LOD2_*.points.ply"):
        key = p.name.replace(".points.ply", "")
        sid = key.split("_", 1)[1]
        m[sid] = key
    return m


def main():
    shard = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    ids = json.load(open(LABELS))["effective_selected_ids"]
    keys = bkey_map()
    todo = [sid for i, sid in enumerate(sorted(ids)) if i % count == shard]
    print(f"[x4] shard {shard}/{count}: {len(todo)} buildings", flush=True)
    summary = {}
    for sid in todo:
        bkey = keys.get(sid)
        if bkey is None:
            summary[sid] = {"error": "no E7 crop"}
            continue
        out_dir = OUT / "runs" / bkey.split("_")[0]
        if (out_dir / "metrics.json").is_file():
            print(f"[x4] skip {bkey} (done)", flush=True)
            continue
        cfg = dict(BASE)
        cfg["scene"] = {"type": "real", "stable_id": sid, "bkey": bkey,
                        "e2_dir": E2_DIR, "max_views": 32, "image_scale": 0.6}
        cfg["out_dir"] = str(out_dir)
        print(f"[x4] ===== {bkey} =====", flush=True)
        try:
            m = run(cfg)
            summary[sid] = {k: m.get(k) for k in ("psnr_eval_final", "o_undecided",
                                                  "cells", "wall_s", "group_counts")}
        except Exception as e:
            import traceback
            traceback.print_exc()
            summary[sid] = {"error": str(e)}
        json.dump(summary, open(OUT / f"x4_summary_shard{shard}.json", "w"),
                  indent=1, default=str)
    print("[x4] shard complete", flush=True)


if __name__ == "__main__":
    main()
