#!/usr/bin/env python3
"""One-off story demo: B022 at w=0 (free judgment, v3 inputs) with the new
per-snapshot gaussian export, so the viewer S3 timeline can play all three
variables (occupancy boxes + gaussian discs + face gates). Not an experiment
row — visualization asset only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arrgs_train import run  # noqa: E402
from xreal_run import BASE as REAL_BASE, scene_for, OUT  # noqa: E402

cfg = dict(REAL_BASE)
cfg["scene"] = scene_for("B022")
cfg["scene"]["o_init_variant"] = "top_cluster"
cfg["scene"]["tower_candidates"] = True
cfg["lambda"] = {"occ_prior": 0.0}
cfg["out_dir"] = str(OUT / "P2-ARRGS-ANCHOR-v1/runs/B022_w0_story")
run(cfg)
