#!/usr/bin/env python3
"""Evaluation-only LoD2 roof metrics for existing Stage-3 outputs."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import sys


def load_readout_library(path: Path):
    spec = importlib.util.spec_from_file_location("jbgs_readout_metrics", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load metric library: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        fields.extend(key for key in row if key not in fields)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--reference-gml", type=Path, required=True)
    parser.add_argument("--footprint", type=Path, required=True)
    parser.add_argument("--metric-library", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--arm", default="GSPLAT_2DGS_REF")
    parser.add_argument("--replica", default="R1")
    parser.add_argument("--steps", nargs="+", type=int, default=[7000, 12000, 15000, 20000])
    args = parser.parse_args()

    from shapely.geometry import shape

    lib = load_readout_library(args.metric_library)
    feature = json.loads(args.footprint.read_text())["features"][0]
    footprint = shape(feature["geometry"])
    refs = lib.parse_reference_roofs(args.reference_gml, "DEBY_LOD2_4906982")
    cfg = {
        "building_id": "DEBY_LOD2_4906982",
        "prediction_z_shift_to_reference_m": -45.7,
        "roof_normal_abs_nz_min": 0.7,
        "grid_size_m": 1.0,
        "center_margin_m": 3.0,
        "grid_min_points_per_cell": 3,
        "coherent_cell_median_abs_dz_max_m": 0.5,
        "coherent_cell_median_normal_angle_max_deg": 15.0,
        "surface_sample_spacing_m": 0.5,
        "distance_thresholds_m": [0.25, 0.5, 1.0],
        "full_roof_xy_coverage_threshold": 0.95,
    }

    rows: list[dict[str, object]] = []
    for step in args.steps:
        root = (
            args.task_root / "arms" / args.arm / args.replica
            / "evaluation" / f"step_{step:06d}"
        )
        fusion = root / "fusion"
        evaluation = json.loads((root / "evaluation.json").read_text())
        terminal = json.loads((fusion / "roofer/roofer_terminal.json").read_text())
        city_paths = sorted((fusion / "roofer/output").glob("*.city.jsonl"))
        if len(city_paths) != 1:
            raise RuntimeError(f"expected one CityJSONSeq output, found {city_paths}")
        predictions, vertices = lib.load_cityjsonseq(
            city_paths[0], cfg["building_id"], cfg["prediction_z_shift_to_reference_m"]
        )
        row: dict[str, object] = {
            "arm": args.arm,
            "replica": args.replica,
            "completed_updates": step,
            "checkpoint_sha256": evaluation["checkpoint_sha256"],
            "scientific_verdict": None,
        }
        row.update(lib.prefix_fields(
            "fused",
            lib.point_metrics(fusion / "fused_surface.laz", footprint, refs, cfg, classified=False),
        ))
        row.update(lib.prefix_fields(
            "classified",
            lib.point_metrics(fusion / "classified_surface.laz", footprint, refs, cfg, classified=True),
        ))
        row.update(lib.prefix_fields(
            "roofer",
            lib.surface_metrics(predictions, vertices, refs, footprint, cfg),
        ))
        row["roofer_internal_rmse"] = (
            terminal.get("target_attributes") or {}
        ).get("rf_rmse_lod22")
        rows.append(row)

    write_csv(args.output_csv, rows)
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_reference_family_diag_v1.lod2_evaluation.v1",
        "reference": {
            "path": str(args.reference_gml),
            "building_id": "DEBY_LOD2_4906982",
            "evaluation_only": True,
            "prediction_z_shift_to_reference_m": -45.7,
        },
        "reference_used_in_training_mask_view_or_checkpoint_selection": False,
        "rows": rows,
        "scientific_verdict": None,
    }
    atomic_json(args.output_json, body)
    print(json.dumps({"rows": len(rows), "output": str(args.output_json)}, indent=2))


if __name__ == "__main__":
    main()
