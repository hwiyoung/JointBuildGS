#!/usr/bin/env python3
"""ARRGS X1/X2/X3 orchestrator (real buildings, sealed assets, viewer-local frame).

X1  B022_DEBY_LOD2_4906965  -- sanity: B-tier unchanged, healthy E2 (comp .94/f1 .93)
X2  B173_DEBY_LOD2_4959326  -- changed: current flat roof vs sloped stale LoD2/ALS
    B036_DEBY_LOD2_4906982  -- hole: MVS/classification collapse profile
X3  3 buildings x dx {0.25,0.5,1.0} + B022 dz 0.25  (delta injected on ALS bytes)

Usage: xreal_run.py <x1|x2|x3|all> [run-name]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arrgs_train import run  # noqa: E402

OUT = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1")
E2_DIR = ("/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_roofer_ox_review_v1/"
          "P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E2")

BUILDINGS = {
    "B022": {"stable_id": "DEBY_LOD2_4906965", "bkey": "B022_DEBY_LOD2_4906965"},
    "B173": {"stable_id": "DEBY_LOD2_4959326", "bkey": "B173_DEBY_LOD2_4959326"},
    "B036": {"stable_id": "DEBY_LOD2_4906982", "bkey": "B036_DEBY_LOD2_4906982"},
}

BASE = {
    "iters": 6000,
    "gaussians": 9000,
    "snapshots": [0, 100, 250, 500, 1000, 2000, 3500, 5000, 6000],
    "holdout": True,
    "cam_batch": 3,
    "enable_delta": True,
    "domain_margin": 1.2,
}


def scene_for(bk, dx=0.0, dz=0.0):
    s = {"type": "real", "e2_dir": E2_DIR, "max_views": 40, "image_scale": 0.75}
    s.update(BUILDINGS[bk])
    if dx:
        s["inject_delta_east_m"] = dx
    if dz:
        s["inject_delta_z_m"] = dz
    return s


def grid():
    runs = []
    runs.append(("X1", "B022_clean", scene_for("B022")))
    runs.append(("X2", "B173_changed", scene_for("B173")))
    runs.append(("X2", "B036_hole", scene_for("B036")))
    for bk in ("B022", "B173", "B036"):
        for dx in (0.25, 0.5, 1.0):
            runs.append(("X3", f"{bk}_dx{int(dx*100):03d}", scene_for(bk, dx=dx)))
    runs.append(("X3", "B022_dz025", scene_for("B022", dz=0.25)))
    return runs


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    only = sys.argv[2] if len(sys.argv) > 2 else None
    summary = {}
    for exp, name, scene in grid():
        if which != "all" and exp.lower() != which:
            continue
        if only and name != only:
            continue
        cfg = dict(BASE)
        cfg["scene"] = scene
        cfg["out_dir"] = str(OUT / f"P2-ARRGS-{exp}-v1/runs/{name}")
        print(f"[xreal] ===== {exp}/{name} =====", flush=True)
        try:
            m = run(cfg)
            summary[f"{exp}/{name}"] = {k: m.get(k) for k in (
                "psnr_eval_final", "o_decision", "o_undecided", "delta_hat",
                "inject_delta", "group_counts", "cells", "gaussians", "wall_s")}
        except Exception as e:
            import traceback
            traceback.print_exc()
            summary[f"{exp}/{name}"] = {"error": str(e)}
        # append-as-you-go so a crash keeps earlier rows
        outp = OUT / f"xreal_summary_{which}.json"
        json.dump(summary, open(outp, "w"), indent=1, default=str)
    print("[xreal] done ->", json.dumps(summary, indent=1, default=str)[:2000])


if __name__ == "__main__":
    main()
