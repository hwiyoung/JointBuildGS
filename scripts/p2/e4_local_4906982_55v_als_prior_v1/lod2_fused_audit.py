#!/usr/bin/env python3
"""Evaluation-only LoD2 metrics on fused LAZ with normalized normal aliases."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

import laspy
import numpy as np
from shapely.geometry import shape


def load_library(path: Path):
    spec = importlib.util.spec_from_file_location("jbgs_readout_metrics_e4", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--reference-gml", type=Path, required=True)
    parser.add_argument("--footprint", type=Path, required=True)
    parser.add_argument("--metric-library", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--arms", nargs="+", required=True)
    parser.add_argument("--steps", nargs="+", type=int, default=[7000, 12000, 15000, 20000])
    args = parser.parse_args()

    lib = load_library(args.metric_library)
    feature = json.loads(args.footprint.read_text())["features"][0]
    footprint = shape(feature["geometry"])
    refs = lib.parse_reference_roofs(args.reference_gml, "DEBY_LOD2_4906982")
    cfg = {
        "prediction_z_shift_to_reference_m": -45.7,
        "roof_normal_abs_nz_min": 0.7,
        "grid_size_m": 1.0,
        "center_margin_m": 3.0,
        "grid_min_points_per_cell": 3,
        "coherent_cell_median_abs_dz_max_m": 0.5,
        "coherent_cell_median_normal_angle_max_deg": 15.0,
        "distance_thresholds_m": [0.25, 0.5, 1.0],
    }
    rows = []
    with tempfile.TemporaryDirectory(prefix="jbgs-e4-lod2-alias-") as directory:
        temporary = Path(directory) / "normal_alias.laz"
        for arm in args.arms:
            for step in args.steps:
                source = args.task_root / f"arms/{arm}/R1/evaluation/step_{step:06d}/fusion/fused_surface.laz"
                cloud = laspy.read(source)
                names = {str(name) for name in cloud.point_format.dimension_names}
                aliases = (("NormalX", "normal_x"), ("NormalY", "normal_y"), ("NormalZ", "normal_z"))
                for destination, original in aliases:
                    if destination not in names:
                        cloud.add_extra_dim(laspy.ExtraBytesParams(name=destination, type=np.float32))
                        cloud[destination] = np.asarray(cloud[original], dtype=np.float32)
                cloud.write(temporary)
                row = {"arm": arm, "replica": "R1", "completed_updates": step}
                row.update(lib.point_metrics(temporary, footprint, refs, cfg, classified=False))
                row["source_fused_surface"] = str(source)
                row["normal_alias_applied_in_temporary_copy"] = True
                row["scientific_verdict"] = None
                rows.append(row)
    fields = list(rows[0])
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    body = {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.lod2_fused_evaluation.v1",
        "reference": {"path": str(args.reference_gml), "evaluation_only": True, "prediction_z_shift_to_reference_m": -45.7},
        "normal_alias_reason": "fused LAZ stores normal_x/y/z while the frozen metric library resolves NormalX/Y/Z",
        "source_artifacts_modified": False,
        "reference_used_in_training_mask_view_or_checkpoint_selection": False,
        "rows": rows,
        "scientific_verdict": None,
    }
    args.output_json.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"rows": len(rows), "output": str(args.output_json)}, indent=2))


if __name__ == "__main__":
    main()
