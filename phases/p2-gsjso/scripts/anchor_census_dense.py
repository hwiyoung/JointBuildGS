#!/usr/bin/env python3
"""Census-scoped entry point for the locked R1-prime-3 dense worker."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE = SCRIPT_DIR / "boundary_map_v3_dense.py"
REPO = SCRIPT_DIR.parents[2]
RUN_ID = "20260720_anchor_census"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
ALLOWLIST = "census_FM_dense_dial_2px_only"


def load_worker() -> Any:
    spec = importlib.util.spec_from_file_location(
        "anchor_census_locked_dense_worker", SOURCE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    worker = load_worker()
    worker.RUN_ID = RUN_ID
    worker.RUN_DIR = RUN_DIR
    worker.JOBS = RUN_DIR / "anchor_census_jobs.json"
    worker.BUILDING_CSV = (
        RUN_DIR / "anchor_census_inference_measurements.csv"
    )
    worker.PAIR_CSV = RUN_DIR / "anchor_census_pairs.csv"
    worker.PROGRESS = RUN_DIR / "anchor_census_progress.json"
    worker.MANIFEST = RUN_DIR / "anchor_census_inference_manifest.json"
    worker.RUN_LOG = RUN_DIR / "anchor_census_inference.log"
    worker.RAW_DIR = RUN_DIR / "anchor_census_raw"
    worker.JOB_PRODUCER = SCRIPT_DIR / "anchor_census.py"
    worker.NEW_INFERENCE_TYPE = ALLOWLIST
    worker.LOCKED_PRIORITY_PREFIX = []
    worker.REPRODUCTION_EXPECTED = {}
    worker.main()


if __name__ == "__main__":
    main()
