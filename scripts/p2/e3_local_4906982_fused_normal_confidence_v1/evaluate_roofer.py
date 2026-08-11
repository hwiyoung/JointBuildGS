#!/usr/bin/env python3
"""Evaluation-only roof-surface metrics for four frozen Roofer outputs."""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

from shapely.geometry import shape
import yaml


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_normal_confidence_v1/P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"
FIXED = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
COMMON = AR / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
ARMS = {
    "FUSED_VIS_CONF": ROOT,
    "FUSED_VIS_CONF_FUSED_NORMAL": FIXED,
    "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT": COMMON,
    "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE": ROOT,
}
STEPS = (7000, 12000, 15000, 20000)


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def main() -> None:
    evaluator = module("readout_surface_evaluator", REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py")
    cfg = yaml.safe_load((REPO / "configs/p2/e3_local_4906982_mvc_readout_diag_v1/config.yaml").read_text())
    footprint = shape(json.loads((ROOT / "control/shared_standard_footprint_4906982.geojson").read_text())["features"][0]["geometry"])
    references = evaluator.parse_reference_roofs(Path(cfg["reference_lod2_gml"]), cfg["building_id"])
    rows = []
    for arm, source in ARMS.items():
        for step in STEPS:
            work = source / f"arms/{arm}/R1/evaluation/step_{step:06d}/fusion"
            city = next((work / "roofer/output").glob("*.city.jsonl"))
            predicted, vertices = evaluator.load_cityjsonseq(city, cfg["building_id"], float(cfg["prediction_z_shift_to_reference_m"]))
            metrics = evaluator.surface_metrics(predicted, vertices, references, footprint, cfg)
            row = {"arm": arm, "replica": "R1", "completed_updates": step, **{f"roofer_{key}": value for key, value in metrics.items()}, "source_cityjsonseq": str(city), "evaluation_only": True, "scientific_verdict": None}
            rows.append(row)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with (ROOT / "roofer_surface_evaluation.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    body = {"schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.roofer_surface_evaluation.v1", "building_id": cfg["building_id"], "rows": rows, "reference": cfg["reference_lod2_gml"], "prediction_z_shift_to_reference_m": cfg["prediction_z_shift_to_reference_m"], "evaluation_only": True, "scientific_verdict": None}
    (ROOT / "roofer_surface_evaluation.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    final = [{"arm": row["arm"], "coverage": row["roofer_roof_xy_coverage_fraction"], "fscore_0p5": row["roofer_surface_fscore_0p5m"], "normal_median": row["roofer_surface_normal_angle_deg_median"], "roof_surfaces": row["roofer_roof_surface_count"]} for row in rows if row["completed_updates"] == 20000]
    print(json.dumps({"status": "COMPLETE", "final_20k": final, "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
