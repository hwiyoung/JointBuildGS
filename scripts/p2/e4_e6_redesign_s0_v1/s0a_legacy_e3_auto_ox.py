#!/usr/bin/env python3
"""S0-a: evaluate the same-lineage legacy techdev E3 under the sealed v22 criterion.

Computes G0/G1/G3/G4 for the legacy E3 CityJSON with the exact v22 reference,
thresholds and helper code, and contrasts its O-counts against the sealed six
conditions. val3dity (G2) is unavailable in current images, so the like-for-like
statistic is O_noG2, recomputed identically for every sealed condition from the
v22 per-building CSV. Nothing is trained, extracted, or overwritten.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from shapely.affinity import translate
from shapely.geometry import shape

from scripts.p2.c1_c2_shared_footprint_199_v3.build_cloudcompare_review10 import lod22_triangles
from scripts.p2.e1_e6_roofer_ox_review_v1.add_development_g3_g4_v0 import (
    cluster_roof_planes,
    g4_metrics,
    major_planes,
    roof_reference_cells,
)
from scripts.p2.e1_e6_roofer_ox_review_v1.build_reference_auto_ox_v1 import (
    SENSITIVITY,
    cityjson_g0_g1,
    classify_binary,
    load_config,
    parse_reference_roofs,
    plane_match_metrics,
    reference_grid_from_lod2,
    reference_triangles,
)

REPO = Path(__file__).resolve().parents[3]
COMMON = REPO / "configs/p2/e4_e6_redesign_s0_v1/s0_v1.yaml"
ARTIFACTS = Path("/artifacts/JointBuildGS")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def no_g2_verdict(row: dict[str, str]) -> str:
    if row["verdict"] == "NA":
        return "NA"
    gates = [row["G0_status"], row["G1_status"], row["G3_status"], row["G4_status"]]
    return "O" if all(value == "O" for value in gates) else "X"


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    out_root = Path(common["output_root"]) / "s0a"
    out_root.mkdir(parents=True, exist_ok=True)

    config = load_config(REPO / common["v22_config"])
    v22_root = ARTIFACTS / common["v22_output_relative_root"]
    viewer = json.loads((v22_root / "viewer_manifest.json").read_text(encoding="utf-8"))
    if len(viewer["buildings"]) != 199:
        raise RuntimeError("v22 viewer population drifted")
    origin = np.asarray(viewer["scene_local_origin_xyz"], dtype=np.float64)

    legacy_path = ARTIFACTS / common["legacy_e3_cityjson"]
    legacy_hash = sha256(legacy_path)
    legacy_cityjson = json.loads(legacy_path.read_text(encoding="utf-8"))

    footprint_spec = config["shared_footprints"]
    footprint_payload = json.loads((ARTIFACTS / footprint_spec["path"]).read_text(encoding="utf-8"))
    footprints = {
        str(feature["properties"][footprint_spec["id_field"]]): shape(feature["geometry"])
        for feature in footprint_payload["features"]
    }
    stable_ids = {building["stable_id"] for building in viewer["buildings"]}
    reference_surfaces = parse_reference_roofs(
        [ARTIFACTS / source["path"] for source in config["lod2_reference_sources"]],
        stable_ids,
        origin,
        float(config["structure_metric"]["lod2_reference_z_shift_to_viewer_m"]),
    )

    structure = config["structure_metric"]
    geometry = config["geometry_metric"]
    counts: dict[str, Counter] = {key: Counter() for key in SENSITIVITY}
    rows: list[dict[str, Any]] = []
    for building in viewer["buildings"]:
        stable_id = building["stable_id"]
        footprint_local = translate(footprints[stable_id], xoff=-origin[0], yoff=-origin[1])
        inset = footprint_local.buffer(-float(geometry["evaluation_inset_m"]))
        evaluation_polygon = inset if not inset.is_empty else footprint_local
        reference_planes = major_planes(reference_surfaces[stable_id], structure["minimum_plane_area_m2"])
        lod_triangles = reference_triangles(reference_surfaces[stable_id])
        uas_path = v22_root / building["lidar"]["points"]
        uas_cells = (
            roof_reference_cells(uas_path, geometry["cell_size_m"], evaluation_polygon)
            if building["lidar"].get("point_count", 0) > 0
            else np.empty((0, 3), dtype=np.float64)
        )
        if len(uas_cells):
            geometry_cells = uas_cells
            geometry_role = "CURRENT_UAS_CLASS6_ANY_SUPPORT"
        else:
            geometry_cells = reference_grid_from_lod2(lod_triangles, evaluation_polygon, geometry["cell_size_m"])
            geometry_role = "LOD2_ROOFSURFACE_FALLBACK"
        reference_available = bool(reference_planes) and bool(len(geometry_cells))

        g0, g1, contract_reasons = cityjson_g0_g1(legacy_cityjson, stable_id)
        world_triangles = lod22_triangles(legacy_cityjson, stable_id)
        prediction_triangles = (
            np.asarray(world_triangles, dtype=np.float64) - origin[None, None, :]
            if world_triangles
            else np.empty((0, 3, 3), dtype=np.float64)
        )
        prediction_planes = major_planes(
            cluster_roof_planes(prediction_triangles, structure["cluster_angle_deg"], structure["cluster_height_m"]),
            structure["minimum_plane_area_m2"],
        )
        g4 = g4_metrics(geometry_cells, prediction_triangles)
        if len(geometry_cells) and g4.get("coverage") is None:
            g4["coverage"] = 0.0
        for key in SENSITIVITY:
            overlap = float(key[1:]) / 100.0
            g3 = plane_match_metrics(
                reference_planes,
                prediction_planes,
                overlap,
                structure["normal_tolerance_deg"],
                structure["height_tolerance_m"],
            )
            result = classify_binary(
                g0=g0,
                g1=g1,
                g2=True,
                g3=g3,
                g4=g4,
                reference_available=reference_available,
                thresholds=config["acceptance_thresholds"],
            )
            counts[key][result["verdict"]] += 1
            rows.append({
                "population_index": building["population_index"],
                "stable_id": stable_id,
                "condition_id": "E3_LEGACY_TECHDEV",
                "criterion": key,
                "verdict_noG2": result["verdict"],
                "G0_status": result["gates"]["G0"],
                "G1_status": result["gates"]["G1"],
                "G2_status": "NE",
                "G3_status": result["gates"]["G3"],
                "G4_status": result["gates"]["G4"],
                "failure_reasons": "|".join(result["failure_reasons"]),
                "g1_reasons": "|".join(contract_reasons),
                "g3_area_completeness": result["g3"].get("area_completeness"),
                "g3_plane_area_recall": result["g3"].get("plane_area_recall"),
                "g3_plane_area_precision": result["g3"].get("plane_area_precision"),
                "g4_reference_role": geometry_role,
                "g4_coverage": result["g4"].get("coverage"),
                "g4_rmse_z_m": result["g4"].get("rmse_z_m"),
                "g4_p95_abs_z_m": result["g4"].get("p95_abs_z_m"),
                "g4_median_bias_z_m": result["g4"].get("median_bias_z_m"),
            })

    sealed_csv = v22_root / "reference_auto_ox_building_condition_v1.csv"
    sealed_rows = list(csv.DictReader(sealed_csv.open(encoding="utf-8")))
    sealed_counts: dict[str, dict[str, dict[str, int]]] = {}
    for row in sealed_rows:
        key = row["criterion"]
        condition = row["condition_id"]
        block = sealed_counts.setdefault(key, {}).setdefault(condition, {"O": 0, "O_noG2": 0, "NA": 0})
        if row["verdict"] == "O":
            block["O"] += 1
        if row["verdict"] == "NA":
            block["NA"] += 1
        if no_g2_verdict(row) == "O":
            block["O_noG2"] += 1

    csv_path = out_root / "legacy_e3_building_condition_v1.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s0_v1.s0a.v1",
        "task_id": common["task_id"],
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "criterion_version": config["criterion_version"],
        "primary_threshold": config["primary_threshold"],
        "legacy_e3_cityjson": {"path": str(legacy_path), "sha256": legacy_hash},
        "v22_building_csv_sha256": sha256(sealed_csv),
        "g2_note": common["val3dity_note"],
        "legacy_e3_counts_noG2": {key: dict(value) for key, value in counts.items()},
        "sealed_condition_counts": sealed_counts,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    (out_root / "legacy_e3_summary_v1.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    brief = {
        key: {
            "E3_LEGACY_noG2": counts[key].get("O", 0),
            **{
                condition: sealed_counts.get(key, {}).get(condition, {})
                for condition in ("E3", "E4", "E5")
            },
        }
        for key in SENSITIVITY
    }
    print(json.dumps(brief, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
