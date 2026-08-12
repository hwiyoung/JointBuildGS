#!/usr/bin/env python3
"""S3 evaluation: v22 criterion over the S2 arms + paired transitions.

Evaluates E4_V2_STATIC and E5_V2_F1 assembled CityJSONs under the sealed v22
reference/thresholds (same code path as S0-a), then builds the same-lineage
O-count table and paired per-building transitions against the sealed E2 and
E3 verdicts (O_noG2 basis; val3dity unavailable, identical caveat to S0-a).
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
from scripts.p2.e4_e6_redesign_s0_v1.s0a_legacy_e3_auto_ox import no_g2_verdict

REPO = Path(__file__).resolve().parents[3]
ARTIFACTS = Path("/artifacts/JointBuildGS")
S3_ROOT = ARTIFACTS / "phase-payloads/p2/e4_e6_redesign_s3_v1/P2-E4-E6-REDESIGN-S3-v1"
V22_CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/reference_auto_ox_v1.json"
NEW_CONDITIONS = ("E4_V2_STATIC", "E5_V2_F1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    out_root = S3_ROOT / "evaluation"
    out_root.mkdir(parents=True, exist_ok=True)
    config = load_config(V22_CONFIG)
    v22_root = ARTIFACTS / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-AUTO-OX-v22-ROBUST-PLANE-MATCH"
    viewer = json.loads((v22_root / "viewer_manifest.json").read_text(encoding="utf-8"))
    origin = np.asarray(viewer["scene_local_origin_xyz"], dtype=np.float64)

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

    cityjsons = {}
    hashes = {}
    for condition in NEW_CONDITIONS:
        path = S3_ROOT / "work" / condition / "assembled.city.json"
        hashes[condition] = sha256(path)
        cityjsons[condition] = json.loads(path.read_text(encoding="utf-8"))

    counts: dict[str, dict[str, Counter]] = {key: {c: Counter() for c in NEW_CONDITIONS} for key in SENSITIVITY}
    verdicts: dict[tuple[str, str], str] = {}
    rows: list[dict[str, Any]] = []
    for building in viewer["buildings"]:
        stable_id = building["stable_id"]
        footprint_local = translate(footprints[stable_id], xoff=-origin[0], yoff=-origin[1])
        inset = footprint_local.buffer(-float(geometry["evaluation_inset_m"]))
        evaluation_polygon = inset if not inset.is_empty else footprint_local
        reference_planes = major_planes(reference_surfaces[stable_id], structure["minimum_plane_area_m2"])
        lod_triangles = reference_triangles(reference_surfaces[stable_id])
        uas_cells = (
            roof_reference_cells(v22_root / building["lidar"]["points"], geometry["cell_size_m"], evaluation_polygon)
            if building["lidar"].get("point_count", 0) > 0
            else np.empty((0, 3), dtype=np.float64)
        )
        if len(uas_cells):
            geometry_cells, geometry_role = uas_cells, "CURRENT_UAS_CLASS6_ANY_SUPPORT"
        else:
            geometry_cells = reference_grid_from_lod2(lod_triangles, evaluation_polygon, geometry["cell_size_m"])
            geometry_role = "LOD2_ROOFSURFACE_FALLBACK"
        reference_available = bool(reference_planes) and bool(len(geometry_cells))

        for condition in NEW_CONDITIONS:
            cityjson = cityjsons[condition]
            g0, g1, contract_reasons = cityjson_g0_g1(cityjson, stable_id)
            world_triangles = lod22_triangles(cityjson, stable_id)
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
                    reference_planes, prediction_planes, overlap,
                    structure["normal_tolerance_deg"], structure["height_tolerance_m"],
                )
                result = classify_binary(
                    g0=g0, g1=g1, g2=True, g3=g3, g4=g4,
                    reference_available=reference_available,
                    thresholds=config["acceptance_thresholds"],
                )
                counts[key][condition][result["verdict"]] += 1
                if key == "O50":
                    verdicts[(condition, stable_id)] = result["verdict"]
                rows.append({
                    "population_index": building["population_index"],
                    "stable_id": stable_id,
                    "condition_id": condition,
                    "criterion": key,
                    "verdict_noG2": result["verdict"],
                    "G0_status": result["gates"]["G0"],
                    "G1_status": result["gates"]["G1"],
                    "G3_status": result["gates"]["G3"],
                    "G4_status": result["gates"]["G4"],
                    "failure_reasons": "|".join(result["failure_reasons"]),
                    "g3_plane_area_recall": result["g3"].get("plane_area_recall"),
                    "g3_plane_area_precision": result["g3"].get("plane_area_precision"),
                    "g4_reference_role": geometry_role,
                    "g4_coverage": result["g4"].get("coverage"),
                    "g4_rmse_z_m": result["g4"].get("rmse_z_m"),
                    "g4_p95_abs_z_m": result["g4"].get("p95_abs_z_m"),
                    "g4_median_bias_z_m": result["g4"].get("median_bias_z_m"),
                })

    sealed_csv = v22_root / "reference_auto_ox_building_condition_v1.csv"
    sealed_rows = [r for r in csv.DictReader(sealed_csv.open(encoding="utf-8")) if r["criterion"] == "O50"]
    sealed_verdicts = {
        (r["condition_id"], r["stable_id"]): no_g2_verdict(r) for r in sealed_rows
    }
    sealed_counts = {c: Counter(no_g2_verdict(r) for r in sealed_rows if r["condition_id"] == c) for c in ("E1", "E2", "E3", "E4", "E5", "E6")}

    transitions = {}
    for new in NEW_CONDITIONS:
        for baseline in ("E2", "E3"):
            table = Counter()
            rescue_ids, regress_ids = [], []
            for building in viewer["buildings"]:
                sid = building["stable_id"]
                a = sealed_verdicts.get((baseline, sid), "?")
                b = verdicts.get((new, sid), "?")
                table[(a, b)] += 1
                if a == "X" and b == "O":
                    rescue_ids.append(sid)
                if a == "O" and b == "X":
                    regress_ids.append(sid)
            transitions[f"{baseline}->{new}"] = {
                "rescue_X_to_O": table[("X", "O")],
                "regress_O_to_X": table[("O", "X")],
                "both_O": table[("O", "O")],
                "net": table[("X", "O")] - table[("O", "X")],
                "rescue_ids": rescue_ids,
                "regress_ids": regress_ids,
            }
    e4e5 = Counter()
    for building in viewer["buildings"]:
        sid = building["stable_id"]
        e4e5[(verdicts.get(("E4_V2_STATIC", sid), "?"), verdicts.get(("E5_V2_F1", sid), "?"))] += 1
    transitions["E4_V2->E5_V2"] = {
        "e4_O_e5_O": e4e5[("O", "O")],
        "e4_X_e5_O": e4e5[("X", "O")],
        "e4_O_e5_X": e4e5[("O", "X")],
    }

    csv_path = out_root / "s3_building_condition_v1.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s3_v1.auto_ox.v1",
        "task_id": "P2-E4-E6-REDESIGN-S3-v1",
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "criterion_version": config["criterion_version"],
        "g2_note": "val3dity unavailable; all counts are O_noG2 (G0&G1&G3&G4), identical basis to S0-a",
        "cityjson_sha256": hashes,
        "new_condition_counts": {key: {c: dict(v) for c, v in block.items()} for key, block in counts.items()},
        "sealed_condition_counts_O50_noG2": {c: dict(v) for c, v in sealed_counts.items()},
        "paired_transitions_O50": transitions,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    (out_root / "s3_auto_ox_summary_v1.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    brief = {
        "O50": {
            **{c: counts["O50"][c].get("O", 0) for c in NEW_CONDITIONS},
            **{c: sealed_counts[c].get("O", 0) for c in ("E1", "E2", "E3")},
        },
        "transitions": {k: {kk: vv for kk, vv in v.items() if not kk.endswith("_ids")} for k, v in transitions.items()},
    }
    print(json.dumps(brief, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
