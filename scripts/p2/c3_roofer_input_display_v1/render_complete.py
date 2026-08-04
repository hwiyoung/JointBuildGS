#!/usr/bin/env python3
"""Render the complete C3 representation-to-readout lineage without recomputation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c1_c2_oracle_c3_extract_v1.render_results import (
    _c3_gaussian_panel,
    _quaternion_axes,
    _read_binary_vertex_ply,
)
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    resolve_artifact,
    write_new,
)
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import VIEWS, _sheet


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_roofer_input_display_v1/render_complete_v2.json"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c3_complete_lineage_display.v2":
        raise RuntimeError("unexpected complete-lineage schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXPERIMENT_HOST_EXECUTION":
        raise RuntimeError("complete-lineage display is not activated")
    if list(config["scope"]["condition_ids"]) != ["C3_1_SEM", "C3_2_SEM_DEPTH"]:
        raise RuntimeError("condition order drifted")
    if len(config["scope"]["building_ids"]) != 3:
        raise RuntimeError("building membership drifted")
    if config["scope"].get("c4_c5_access_allowed") is not False:
        raise RuntimeError("C4/C5 access is prohibited")
    if any(int(value) != 0 for value in config["execution_counters"].values()):
        raise RuntimeError("complete-lineage display counter must be zero")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific verdict must remain null")


def _bbox_like(reference: Any) -> Any:
    x0, y0, x1, y1 = reference.footprint.bounds

    class BBox:
        min_x = x0
        min_y = y0
        max_x = x1
        max_y = y1
        width = x1 - x0
        height = y1 - y0

    return BBox()


def _rings(reference: Any) -> list[np.ndarray]:
    polygons = [reference.footprint] if reference.footprint.geom_type == "Polygon" else list(reference.footprint.geoms)
    rings: list[np.ndarray] = []
    for polygon in polygons:
        rings.append(np.asarray(polygon.exterior.coords, dtype=np.float64))
        rings.extend(np.asarray(interior.coords, dtype=np.float64) for interior in polygon.interiors)
    return rings


def _height_colors(xyz: np.ndarray) -> np.ndarray:
    z = np.asarray(xyz[:, 2], dtype=np.float64)
    lo, hi = np.quantile(z, [0.01, 0.99])
    normalized = np.clip((z - lo) / max(float(hi - lo), 1e-9), 0.0, 1.0)
    return plt.get_cmap("viridis")(normalized)[:, :3]


def _normal_colors(quaternions: np.ndarray) -> np.ndarray:
    axis_x, axis_y = _quaternion_axes(quaternions)
    normals = np.cross(axis_x, axis_y)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    return np.abs(normals)


def _existing(paths_root: Path, pattern: str) -> list[Path]:
    paths = [paths_root / pattern.format(view=view.lower()) for view in VIEWS]
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"required inherited panel missing: {path}")
    return paths


def run(output_root: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    diagnostic_root = resolve_artifact(artifact_root, config["source"]["diagnostic_relative_root"], "diagnostic source")
    roofer_input_root = resolve_artifact(artifact_root, config["source"]["roofer_input_display_relative_root"], "Roofer-input display")
    v13_root = resolve_artifact(artifact_root, config["source"]["v13_relative_root"], "v13 source")
    lod2_path = resolve_artifact(artifact_root, config["source"]["lod2_relative_path"], "LoD2 source")
    references = load_building_references(lod2_path, config["scope"]["building_ids"])
    case_records = []
    new_panel_records = []
    for stable_id in config["scope"]["building_ids"]:
        reference = references[stable_id]
        bbox = _bbox_like(reference)
        footprint_rings = _rings(reference)
        c1_las = v13_root / f"operations/C1_L_upper_GT_FOOTPRINT_ORACLE/{stable_id}/work/input.las"
        from src.visualization.fixed_view_qualitative import load_las_points

        c1_points = load_las_points(c1_las).xyz
        footprint_z = float(np.quantile(c1_points[:, 2], 0.02))
        rows: list[tuple[str, list[Path]]] = []
        rgb_paths = [v13_root / f"qualitative/c3/comparison/{stable_id}/panels/01_rgb_roofline_{index}.png" for index in range(1, 5)]
        rows.append(("2024 RGB + 2022 roofline\nprojection context", rgb_paths))
        case_root = output_root / f"qualitative/complete_lineage/{stable_id}"
        for condition_id in config["scope"]["condition_ids"]:
            v13_support = v13_root / f"qualitative/c3/support/{condition_id}/{stable_id}/panels"
            rows.append((f"{condition_id}\nGS 3D Gaussian RGB\nellipses", _existing(v13_support, "1_{view}.png")))
            rows.append((f"{condition_id}\nGS 3D Gaussian semantic\nellipses", _existing(v13_support, "2_{view}.png")))
            proxy = _read_binary_vertex_ply(v13_root / f"c3/{condition_id}/gaussians/display_proxy_gaussian_parameters_v1.ply")
            xyz = np.column_stack((proxy["x"], proxy["y"], proxy["z"]))
            keep = (
                (xyz[:, 0] >= bbox.min_x - 5) & (xyz[:, 0] <= bbox.max_x + 5)
                & (xyz[:, 1] >= bbox.min_y - 5) & (xyz[:, 1] <= bbox.max_y + 5)
            )
            xyz = xyz[keep]
            quaternions = np.column_stack((proxy["quat_w"], proxy["quat_x"], proxy["quat_y"], proxy["quat_z"]))[keep]
            scales = np.column_stack((proxy["scale_x"], proxy["scale_y"]))[keep]
            opacity = np.asarray(proxy["opacity"], dtype=np.float64)[keep]
            for key, title, colors in (
                ("height", "GS 3D Gaussian world-Z height (depth proxy; not camera depth)", _height_colors(xyz)),
                ("normal", "GS 3D Gaussian absolute plane normal RGB", _normal_colors(quaternions)),
            ):
                paths = []
                for view in VIEWS:
                    path = case_root / f"panels/{condition_id}_gaussian_{key}_{view.lower()}.png"
                    _c3_gaussian_panel(
                        path, xyz, quaternions, scales, opacity, colors, bbox,
                        footprint_rings, footprint_z, view, f"{title} | {view}",
                    )
                    paths.append(path)
                    new_panel_records.append(file_record(path, output_root))
                label = "GS 3D Gaussian height\nworld Z; depth proxy" if key == "height" else "GS 3D Gaussian normal\nabs(nx),abs(ny),abs(nz)"
                rows.append((f"{condition_id}\n{label}", paths))
            rows.append((f"{condition_id}\nrendered-depth direct fusion\n3D points; semantic colors", _existing(v13_support, "4_{view}.png")))
            diagnostic_panels = diagnostic_root / f"qualitative/roof_first/{stable_id}/panels"
            rows.append((f"{condition_id}\nroof-only multi-view consensus\nPoisson/TSDF input", _existing(diagnostic_panels, f"{condition_id}_roof_consensus_{{view}}.png")))
            rows.append((f"{condition_id}\nroof-only Poisson mesh", _existing(diagnostic_panels, f"{condition_id}_poisson_{{view}}.png")))
            rows.append((f"{condition_id}\nroof-only TSDF mesh", _existing(diagnostic_panels, f"{condition_id}_tsdf_{{view}}.png")))
            roofer_input_panels = roofer_input_root / f"qualitative/roof_first_with_roofer_input/{stable_id}/panels"
            rows.append((f"{condition_id}\nACTUAL inherited Roofer input\nclass6 roof + class2 terrain", _existing(roofer_input_panels, f"{condition_id}_inherited_roofer_input_{{view}}.png")))
            rows.append((f"{condition_id}\ninherited Roofer output\nGT-footprint oracle diagnostic", _existing(diagnostic_panels, f"{condition_id}_roofer_{{view}}.png")))
        diagnostic_panels = diagnostic_root / f"qualitative/roof_first/{stable_id}/panels"
        rows.append(("2022 LoD2 context\n+45.7m display datum", _existing(diagnostic_panels, "lod2_context_{view}.png")))
        if len(rows) != int(config["display"]["row_count_per_sheet"]):
            raise RuntimeError(f"row count drifted for {stable_id}: {len(rows)}")
        sheet = case_root / "case_sheet_complete_c3_lineage_v2.png"
        _sheet(
            sheet,
            stable_id,
            rows,
            subtitle="complete C3 lineage | Gaussian -> direct fusion -> roof consensus/meshes | inherited Roofer branch explicit | scientific_verdict=null",
        )
        case_records.append({
            "stable_id": stable_id,
            "case_sheet": file_record(sheet, output_root),
            "row_count": len(rows),
            "visible_cell_count": len(rows) * 4,
        })
    body = {
        "schema": "jointbuildgs.c3_complete_lineage_display.v2",
        "status": "COMPLETE_EXPLICIT_REPRESENTATION_AND_READOUT_LINEAGE",
        "case_sheet_count": len(case_records),
        "rows_per_sheet": int(config["display"]["row_count_per_sheet"]),
        "visible_cell_count": sum(row["visible_cell_count"] for row in case_records),
        "new_gaussian_attribute_panel_count": len(new_panel_records),
        "case_sheets": case_records,
        "new_gaussian_attribute_panels": new_panel_records,
        "lineage_note": "Poisson/TSDF use new roof-only consensus; inherited Roofer uses separate v13 input LAS and is not downstream of TSDF.",
        "gaussian_depth_display": config["display"]["gaussian_depth_display"],
        "execution_counters": config["execution_counters"],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v2.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
