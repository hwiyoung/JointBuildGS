#!/usr/bin/env python3
"""Add the exact inherited Roofer input point cloud to the C3 case sheets."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from shapely import intersects_xy
from shapely.geometry import MultiPoint

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    resolve_artifact,
    write_new,
)
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import (
    VIEWS,
    _condition_data,
    _panel,
    _sheet,
)
from src.visualization.fixed_view_qualitative import Surface, load_las_points


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_roofer_input_display_v1/render_v1.json"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c3_roofer_input_display.v1":
        raise RuntimeError("unexpected Roofer-input display schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXPERIMENT_HOST_EXECUTION":
        raise RuntimeError("Roofer-input display is not activated")
    if list(config["scope"]["condition_ids"]) != ["C3_1_SEM", "C3_2_SEM_DEPTH"]:
        raise RuntimeError("condition order drifted")
    if len(config["scope"]["building_ids"]) != 3:
        raise RuntimeError("building membership drifted")
    if config["scope"].get("c4_c5_access_allowed") is not False:
        raise RuntimeError("C4/C5 access is prohibited")
    if any(int(value) != 0 for value in config["execution_counters"].values()):
        raise RuntimeError("display addendum execution counter must be zero")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific verdict must remain null")


def _quantiles(values: np.ndarray) -> dict[str, float] | None:
    if not len(values):
        return None
    q = np.quantile(np.asarray(values, dtype=np.float64), [0, 0.1, 0.5, 0.9, 1])
    return dict(zip(("minimum", "p10", "median", "p90", "maximum"), map(float, q)))


def _support(reference: Any, xyz: np.ndarray, radius_m: float) -> dict[str, Any]:
    if not len(xyz):
        return {
            "class6_point_count": 0,
            "buffer_coverage_fraction": 0.0,
            "convex_hull_span_fraction": 0.0,
            "z_m": None,
        }
    multipoint = MultiPoint(xyz[:, :2])
    footprint = reference.footprint
    return {
        "class6_point_count": int(len(xyz)),
        "buffer_coverage_fraction": float(multipoint.buffer(radius_m).intersection(footprint).area / footprint.area),
        "convex_hull_span_fraction": float(multipoint.convex_hull.intersection(footprint).area / footprint.area),
        "z_m": _quantiles(xyz[:, 2]),
    }


def _csv_bytes(rows: list[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _input_zlim(
    ground_display: float,
    lod2_surfaces: list[Surface],
    roof: np.ndarray,
    terrain: np.ndarray,
    terrain_quantiles: tuple[float, float],
) -> tuple[float, float]:
    values = [float(ground_display)]
    for surface in lod2_surfaces:
        values.extend([float(np.min(surface.xyz[:, 2])), float(np.max(surface.xyz[:, 2]))])
    if len(roof):
        values.extend([float(np.min(roof[:, 2])), float(np.max(roof[:, 2]))])
    if len(terrain):
        values.extend(map(float, np.quantile(terrain[:, 2], terrain_quantiles)))
    return min(values) - 2.0, max(values) + 2.0


def run(output_root: Path, artifact_root: Path, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    source_root = resolve_artifact(artifact_root, config["source"]["diagnostic_relative_root"], "diagnostic source")
    v13_root = resolve_artifact(artifact_root, config["source"]["v13_relative_root"], "v13 source")
    lod2_path = resolve_artifact(artifact_root, config["source"]["lod2_relative_path"], "LoD2 source")
    source_index = json.loads((source_root / "qualitative/index_v1.json").read_text(encoding="utf-8"))
    if source_index.get("status") != "COMPLETE" or source_index.get("case_sheet_count") != 3:
        raise RuntimeError("source qualitative artifact is incomplete")
    references = load_building_references(lod2_path, config["scope"]["building_ids"])
    geoid = 45.7
    coverage_radius = float(config["display"]["roofer_input_coverage_radius_m"])
    terrain_quantiles = tuple(map(float, config["display"].get("terrain_z_quantile_limits", [0.0, 1.0])))
    roof_point_size = float(config["display"].get("roof_point_size", 7.5))
    context_point_size = float(config["display"].get("context_point_size", 1.1))
    support_rows: list[dict[str, Any]] = []
    case_records = []
    new_panel_records = []
    for stable_id in config["scope"]["building_ids"]:
        reference = references[stable_id]
        condition_data = {
            condition: _condition_data(source_root, v13_root, condition, stable_id)
            for condition in config["scope"]["condition_ids"]
        }
        lod2_surfaces = [
            Surface(np.asarray(ring, dtype=np.float64) + np.asarray([0, 0, geoid]), semantic)
            for semantic, ring in reference.surface_rings
        ]
        ground_display = float(np.median(np.vstack(reference.ground_rings_xyz)[:, 2]) + geoid)
        z_values = [ground_display]
        for data in condition_data.values():
            if len(data["roof_xyz"]):
                z_values.extend([float(np.min(data["roof_xyz"][:, 2])), float(np.max(data["roof_xyz"][:, 2]))])
        for surface in lod2_surfaces:
            z_values.extend([float(np.min(surface.xyz[:, 2])), float(np.max(surface.xyz[:, 2]))])
        rows = []
        rgb_paths = [v13_root / f"qualitative/c3/comparison/{stable_id}/panels/01_rgb_roofline_{index}.png" for index in range(1, 5)]
        rows.append(("2024 RGB + 2022 roofline\nprojection context", rgb_paths))
        case_root = output_root / f"qualitative/roof_first_with_roofer_input/{stable_id}"
        for condition_id in config["scope"]["condition_ids"]:
            for row_key in ("semantic_context", "roof_consensus", "poisson", "tsdf"):
                paths = [
                    source_root / f"qualitative/roof_first/{stable_id}/panels/{condition_id}_{row_key}_{view.lower()}.png"
                    for view in VIEWS
                ]
                rows.append((f"{condition_id}\n{row_key.replace('_', ' ')}", paths))
            operation = v13_root / f"operations/{condition_id}_GT_FOOTPRINT_ORACLE/{stable_id}/work"
            prepared = json.loads((operation / "prepared_v1.json").read_text(encoding="utf-8"))
            point_set = load_las_points(operation / "input.las")
            classes = np.asarray(point_set.classification, dtype=np.uint8)
            roof = point_set.xyz[classes == 6]
            terrain = point_set.xyz[classes == 2]
            spatial = _support(reference, roof, coverage_radius)
            roof_inside = intersects_xy(reference.footprint, roof[:, 0], roof[:, 1]) if len(roof) else np.zeros(0, dtype=bool)
            terrain_inside = intersects_xy(reference.footprint, terrain[:, 0], terrain[:, 1]) if len(terrain) else np.zeros(0, dtype=bool)
            support_rows.append({
                "condition_id": condition_id,
                "stable_id": stable_id,
                "roofer_eligible": bool(prepared.get("roofer_eligible")),
                "class6_point_count": spatial["class6_point_count"],
                "class6_inside_footprint_count": int(np.count_nonzero(roof_inside)),
                "class2_terrain_point_count": int(len(terrain)),
                "class2_inside_footprint_count": int(np.count_nonzero(terrain_inside)),
                "footprint_area_m2": float(reference.footprint.area),
                "buffer_radius_m": coverage_radius,
                "buffer_coverage_fraction": spatial["buffer_coverage_fraction"],
                "convex_hull_span_fraction": spatial["convex_hull_span_fraction"],
                "z_minimum_m": None if spatial["z_m"] is None else spatial["z_m"]["minimum"],
                "z_median_m": None if spatial["z_m"] is None else spatial["z_m"]["median"],
                "z_maximum_m": None if spatial["z_m"] is None else spatial["z_m"]["maximum"],
                "input_las_sha256": prepared["input"]["sha256"],
            })
            xyz = np.vstack((terrain, roof)) if len(roof) else terrain
            colors = np.vstack((
                np.tile(np.asarray([0.55, 0.58, 0.62]), (len(terrain), 1)),
                np.tile(np.asarray([0.85, 0.10, 0.65]), (len(roof), 1)),
            )) if len(roof) else np.tile(np.asarray([0.55, 0.58, 0.62]), (len(terrain), 1))
            roof_mask = np.concatenate((np.zeros(len(terrain), dtype=bool), np.ones(len(roof), dtype=bool))) if len(roof) else np.zeros(len(terrain), dtype=bool)
            zlim = _input_zlim(ground_display, lod2_surfaces, roof, terrain, terrain_quantiles)
            input_paths = []
            for view in VIEWS:
                path = case_root / f"panels/{condition_id}_inherited_roofer_input_{view.lower()}.png"
                note = (
                    f"actual v13 LAS: class6 roof={len(roof):,} ({int(np.count_nonzero(roof_inside)):,} inside) magenta; "
                    f"class2 terrain={len(terrain):,} ({int(np.count_nonzero(terrain_inside)):,} inside) gray; "
                    f"coverage={spatial['buffer_coverage_fraction']:.2%}; hull={spatial['convex_hull_span_fraction']:.2%}; terrain Z 1-99% display"
                )
                _panel(
                    path,
                    reference=reference,
                    view=view,
                    zlim=zlim,
                    ground_z=ground_display,
                    title=f"{condition_id} | actual inherited Roofer input LAS | {view}",
                    points=(xyz, colors, roof_mask),
                    note=note,
                    roof_point_size=roof_point_size,
                    context_point_size=context_point_size,
                )
                input_paths.append(path)
                new_panel_records.append(file_record(path, output_root))
            rows.append((f"{condition_id}\nACTUAL ROOFER INPUT\nclass6 roof + class2 terrain", input_paths))
            roofer_paths = [
                source_root / f"qualitative/roof_first/{stable_id}/panels/{condition_id}_roofer_{view.lower()}.png"
                for view in VIEWS
            ]
            rows.append((f"{condition_id}\ninherited Roofer output", roofer_paths))
        lod2_paths = [
            source_root / f"qualitative/roof_first/{stable_id}/panels/lod2_context_{view.lower()}.png"
            for view in VIEWS
        ]
        rows.append(("2022 LoD2 context\n+45.7m display datum", lod2_paths))
        sheet = case_root / "case_sheet_with_actual_roofer_input_v1.png"
        _sheet(
            sheet,
            stable_id,
            rows,
            subtitle="roof-first C3 | ACTUAL inherited Roofer input shown before output | scientific_verdict=null",
        )
        case_records.append({"stable_id": stable_id, "case_sheet": file_record(sheet, output_root), "row_count": len(rows), "visible_cell_count": len(rows) * 4})
    write_new(output_root / "tables/roofer_input_spatial_support_v1.csv", _csv_bytes(support_rows))
    body = {
        "schema": "jointbuildgs.c3_roofer_input_display.v1",
        "status": "COMPLETE_ACTUAL_ROOFER_INPUT_EXPLICIT",
        "source_qualitative_index": file_record(source_root / "qualitative/index_v1.json", source_root),
        "case_sheet_count": len(case_records),
        "rows_per_sheet": int(config["display"]["row_count_per_sheet"]),
        "visible_cell_count": sum(row["visible_cell_count"] for row in case_records),
        "non_rgb_panel_count": int(config["display"]["total_non_rgb_panel_count"]),
        "new_roofer_input_panel_count": len(new_panel_records),
        "case_sheets": case_records,
        "new_roofer_input_panels": new_panel_records,
        "roofer_input_source": "INHERITED_V13_INPUT_LAS_CLASS6_ROOF_PLUS_CLASS2_SHARED_C2_TERRAIN",
        "roofer_input_is_tsdf_sample": False,
        "display_z_policy": "FULL_ROOF_Z_PLUS_TERRAIN_QUANTILE_RANGE",
        "execution_counters": config["execution_counters"],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v1.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.config), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
