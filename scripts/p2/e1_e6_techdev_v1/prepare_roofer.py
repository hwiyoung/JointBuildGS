from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from scripts.p2.c1_c2_shared_footprint_199_v3.run import combine_cityjsonseq


TASK_REL = Path("phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1")
BASELINE_REL = Path(
    "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
    "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a"
)
FOOTPRINT_REL = BASELINE_REL / "freeze/shared_footprints_199.geojson"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def reuse_baseline(artifacts: Path, condition: str) -> None:
    mapping = {"E1": "C1_L_upper", "E2": "C2_MVS"}
    source_method = mapping[condition]
    source = artifacts / BASELINE_REL / f"work/{source_method}/assembled.city.json"
    destination_root = artifacts / TASK_REL / f"runs/{condition}/roofer"
    destination = destination_root / "assembled.city.json"
    receipt = destination_root / "lineage.json"
    if destination.is_file() and receipt.is_file():
        return
    destination_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    payload = {
        "schema": "jointbuildgs.p2.e1_e6.baseline_roofer_lineage.v1",
        "condition": condition,
        "historical_condition": source_method,
        "source": {"path": str(source), "sha256": sha256(source)},
        "copy": {"path": str(destination), "sha256": sha256(destination)},
        "same_199_footprints": True,
        "same_roofer_defaults": True,
        "recomputed": False,
        "scientific_verdict": None,
    }
    receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def prepare(artifacts: Path, run_name: str) -> None:
    run = artifacts / TASK_REL / f"runs/{run_name}"
    roofer = run / "roofer"
    pipeline_path = roofer / "classification_pipeline.json"
    if pipeline_path.is_file():
        return
    cloud = run / "pointcloud/depth_fusion.ply"
    footprint = artifacts / FOOTPRINT_REL
    output = roofer / "classified_scene.laz"
    roofer.mkdir(parents=True, exist_ok=True)
    pipeline = {
        "pipeline": [
            {"type": "readers.ply", "filename": str(cloud)},
            {"type": "filters.crop", "bounds": "([690761.740,691184.650],[5335834.050,5336383.850])"},
            {"type": "filters.smrf", "cell": 1.0, "slope": 0.15, "scalar": 1.25, "threshold": 0.5, "window": 18.0, "ground_class": 2, "other_class": 1},
            {"type": "filters.hag_nn"},
            {"type": "filters.overlay", "dimension": "Classification", "datasource": str(footprint), "column": "class", "where": "HeightAboveGround > 2.0", "threads": 1},
            {"type": "writers.las", "filename": str(output), "a_srs": "EPSG:25832", "minor_version": 4, "dataformat_id": 3, "compression": "lazperf"},
        ]
    }
    pipeline_path.write_text(json.dumps(pipeline, indent=2) + "\n", encoding="utf-8")


def finalize(artifacts: Path, run_name: str) -> None:
    root = artifacts / TASK_REL / f"runs/{run_name}/roofer"
    assembled = root / "assembled.city.json"
    receipt_path = root / "receipt.json"
    if assembled.is_file() and receipt_path.is_file():
        return
    raw = sorted((root / "output").glob("*.city.jsonl"))
    if not raw:
        raise RuntimeError(f"Roofer produced no CityJSONSequence for {run_name}")
    combine_cityjsonseq(raw, assembled)
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.roofer.v1",
        "condition": run_name,
        "classified_scene": {"path": str(root / "classified_scene.laz"), "sha256": sha256(root / "classified_scene.laz")},
        "footprint": {"path": str(artifacts / FOOTPRINT_REL), "sha256": sha256(artifacts / FOOTPRINT_REL)},
        "parameters": "ROOFER_DEFAULTS",
        "invocation_count": 1,
        "quality_driven_retry": False,
        "output": {"path": str(assembled), "sha256": sha256(assembled)},
        "scientific_verdict": None,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("reuse-baseline", "prepare", "finalize"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--condition")
    parser.add_argument("--run-name")
    args = parser.parse_args()
    artifacts = args.artifact_root.resolve()
    if args.mode == "reuse-baseline":
        if args.condition not in {"E1", "E2"}:
            raise ValueError("baseline condition must be E1 or E2")
        reuse_baseline(artifacts, args.condition)
    elif args.mode == "prepare":
        prepare(artifacts, str(args.run_name))
    else:
        finalize(artifacts, str(args.run_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
