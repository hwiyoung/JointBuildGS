#!/usr/bin/env python3
"""Record the conditional 0-d mono-normal reliability skip without opening data."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import e5_c001_s3b0_common as common


FIELDS = [
    "row_type",
    "scope",
    "status",
    "reason",
    "reference_opened",
    "mono_normal_inference_started",
    "learning_runs_started",
    "new_inference_runs",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=common.DEFAULT_LOCK)
    args = parser.parse_args()

    lock = common.load_lock(args.lock)
    config = lock["mono_0d"]
    if config["mode"] != "conditional_skip":
        raise RuntimeError("0-d recorder is restricted to the conditional-skip mode")
    if config["reference_opened"] is not False:
        raise RuntimeError("0-d conditional skip must not open reference data")
    if int(config["mono_normal_inference_started"]) != 0:
        raise RuntimeError("0-d conditional skip must not start mono-normal inference")

    csv_path = common.resolve(lock["outputs"]["mono_reliability_csv"])
    run_dir = common.resolve(lock["outputs"]["mono_run"])
    row = {
        "row_type": "conditional_skip",
        "scope": config["requested_scope"],
        "status": "not_started_conditional",
        "reason": config["reason"],
        "reference_opened": False,
        "mono_normal_inference_started": 0,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    common.atomic_csv(csv_path, [row], FIELDS)

    source_paths = {
        args.lock.resolve(),
        Path(__file__).resolve(),
        Path(common.__file__).resolve(),
        common.REPO / "scripts/e5_c001/s3b0/run_e5_c001_s3b0_mono_reliability.sh",
    }
    manifest = {
        "schema": "jointbuildgs.s3b0.mono_reliability.conditional_skip.v1",
        "created_utc": common.now(),
        "git": {
            "head": common.git_value("rev-parse", "HEAD"),
            "branch": common.git_value("branch", "--show-current"),
            "dirty": bool(common.git_value("status", "--porcelain")),
        },
        "mode": config["mode"],
        "scope": config["requested_scope"],
        "status": "not_started_conditional",
        "reason": config["reason"],
        "reference_opened": False,
        "mono_normal_inference_started": 0,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "counts": {
            "csv_rows": 1,
            "buildings_measured": 0,
            "figures": 0,
        },
        "runtime": {
            "python": platform.python_version(),
            "docker_image": lock["containers"]["main_image"],
            "docker_image_id": lock["containers"]["main_image_id"],
        },
        "source_sha256": common.source_hashes(source_paths),
        "output_sha256": {common.rel(csv_path): common.sha256_file(csv_path)},
    }
    common.atomic_json(run_dir / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "not_started_conditional",
                "csv_rows": 1,
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
