#!/usr/bin/env python3
"""A2 auto-OX: v22 criterion over E7/E8 + paired transitions vs sealed arms.

Evaluates the A2 E7 (ALS-only) and E8 (E2 ∪ ALS) assembled CityJSONs under the
sealed v22 reference/thresholds — the exact same code path as S3b — then builds
paired per-building O50 transitions against the sealed E1/E2/E3/E4/E5 verdicts
(v22 CSV) and the redesign E4_V2_STATIC/E5_V2_F1 verdicts (S3b CSV).

Transitions use the O_noG2 basis (G0&G1&G3&G4) for comparability with S3b;
E7/E8 additionally record the full G2-included verdict from their own val3dity
reports. NOT_OFFICIAL development read-out; NA is reference-absence only;
missing prediction is X; scientific_verdict stays null.
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
    feature_validity,
    load_config,
    parse_reference_roofs,
    plane_match_metrics,
    reference_grid_from_lod2,
    reference_triangles,
    val3dity_feature_map,
)
from scripts.p2.e4_e6_redesign_s0_v1.s0a_legacy_e3_auto_ox import no_g2_verdict

REPO = Path(__file__).resolve().parents[3]
ARTIFACTS = Path("/artifacts/JointBuildGS")
A2_ROOT = ARTIFACTS / "phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1/a2"
V22_CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/reference_auto_ox_v1.json"
V22_ROOT = ARTIFACTS / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-AUTO-OX-v22-ROBUST-PLANE-MATCH"
S3B_CSV = ARTIFACTS / "phase-payloads/p2/e4_e6_redesign_s3b_v1/P2-E4-E6-REDESIGN-S3B-v1/evaluation/s3b_building_condition_v1.csv"
NEW_CONDITIONS = ("E7", "E8")
SEALED_BASELINES = ("E1", "E2", "E3", "E4", "E5")
S3B_BASELINES = ("E4_V2_STATIC", "E5_V2_F1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    out_root = A2_ROOT / "evaluation_auto_ox"
    out_root.mkdir(parents=True, exist_ok=True)
    config = load_config(V22_CONFIG)
    viewer = json.loads((V22_ROOT / "viewer_manifest.json").read_text(encoding="utf-8"))
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
    validity = {}
    hashes = {}
    for condition in NEW_CONDITIONS:
        path = A2_ROOT / "work" / condition / "assembled.city.json"
        hashes[condition] = sha256(path)
        cityjsons[condition] = json.loads(path.read_text(encoding="utf-8"))
        report_path = A2_ROOT / "work" / condition / "val3dity_report.json"
        validity[condition] = val3dity_feature_map(json.loads(report_path.read_text(encoding="utf-8")))

    counts_nog2: dict[str, dict[str, Counter]] = {key: {c: Counter() for c in NEW_CONDITIONS} for key in SENSITIVITY}
    counts_full: dict[str, dict[str, Counter]] = {key: {c: Counter() for c in NEW_CONDITIONS} for key in SENSITIVITY}
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
            roof_reference_cells(V22_ROOT / building["lidar"]["points"], geometry["cell_size_m"], evaluation_polygon)
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
            g2, val_errors = feature_validity(validity[condition], stable_id, g0)
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
                nog2 = classify_binary(
                    g0=g0, g1=g1, g2=True, g3=g3, g4=g4,
                    reference_available=reference_available,
                    thresholds=config["acceptance_thresholds"],
                )
                full = classify_binary(
                    g0=g0, g1=g1, g2=g2, g3=g3, g4=g4,
                    reference_available=reference_available,
                    thresholds=config["acceptance_thresholds"],
                )
                counts_nog2[key][condition][nog2["verdict"]] += 1
                counts_full[key][condition][full["verdict"]] += 1
                if key == "O50":
                    verdicts[(condition, stable_id)] = nog2["verdict"]
                rows.append({
                    "population_index": building["population_index"],
                    "stable_id": stable_id,
                    "condition_id": condition,
                    "criterion": key,
                    "verdict_noG2": nog2["verdict"],
                    "verdict_withG2": full["verdict"],
                    "G0_status": nog2["gates"]["G0"],
                    "G1_status": nog2["gates"]["G1"],
                    "G2_status": "O" if g2 else "X",
                    "G3_status": nog2["gates"]["G3"],
                    "G4_status": nog2["gates"]["G4"],
                    "failure_reasons": "|".join(nog2["failure_reasons"]),
                    "g3_plane_area_recall": nog2["g3"].get("plane_area_recall"),
                    "g3_plane_area_precision": nog2["g3"].get("plane_area_precision"),
                    "g4_reference_role": geometry_role,
                    "g4_coverage": nog2["g4"].get("coverage"),
                    "g4_rmse_z_m": nog2["g4"].get("rmse_z_m"),
                    "g4_p95_abs_z_m": nog2["g4"].get("p95_abs_z_m"),
                    "g4_median_bias_z_m": nog2["g4"].get("median_bias_z_m"),
                })

    sealed_rows = [r for r in csv.DictReader((V22_ROOT / "reference_auto_ox_building_condition_v1.csv").open(encoding="utf-8")) if r["criterion"] == "O50"]
    baseline_verdicts = {(r["condition_id"], r["stable_id"]): no_g2_verdict(r) for r in sealed_rows}
    baseline_counts = {c: Counter(no_g2_verdict(r) for r in sealed_rows if r["condition_id"] == c) for c in SEALED_BASELINES}
    s3b_rows = [r for r in csv.DictReader(S3B_CSV.open(encoding="utf-8")) if r["criterion"] == "O50"]
    for r in s3b_rows:
        baseline_verdicts[(r["condition_id"], r["stable_id"])] = r["verdict_noG2"]
    for c in S3B_BASELINES:
        baseline_counts[c] = Counter(r["verdict_noG2"] for r in s3b_rows if r["condition_id"] == c)

    transitions = {}
    for new in NEW_CONDITIONS:
        for baseline in SEALED_BASELINES + S3B_BASELINES:
            table = Counter()
            rescue_ids, regress_ids = [], []
            for building in viewer["buildings"]:
                sid = building["stable_id"]
                a = baseline_verdicts.get((baseline, sid), "?")
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
    cross = Counter()
    for building in viewer["buildings"]:
        sid = building["stable_id"]
        cross[(verdicts.get(("E7", sid), "?"), verdicts.get(("E8", sid), "?"))] += 1
    transitions["E7->E8"] = {
        "e7_O_e8_O": cross[("O", "O")],
        "e7_X_e8_O": cross[("X", "O")],
        "e7_O_e8_X": cross[("O", "X")],
    }

    csv_path = out_root / "a2_auto_ox_building_condition_v1.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_auto_ox.v1",
        "task_id": "P2-JOURNAL1-PHASE-A-v1",
        "stage": "A2",
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "criterion_version": config["criterion_version"],
        "development_status": "ROOFER_REFERENCE_AUTO_OX_DEVELOPMENT_NOT_OFFICIAL",
        "basis_note": "transitions use O_noG2 (G0&G1&G3&G4) for comparability with S3b; E7/E8 also record verdict_withG2 from their own val3dity",
        "cityjson_sha256": hashes,
        "new_condition_counts_noG2": {key: {c: dict(v) for c, v in block.items()} for key, block in counts_nog2.items()},
        "new_condition_counts_withG2": {key: {c: dict(v) for c, v in block.items()} for key, block in counts_full.items()},
        "baseline_counts_O50_noG2": {c: dict(v) for c, v in baseline_counts.items()},
        "paired_transitions_O50": transitions,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    (out_root / "a2_auto_ox_summary_v1.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    brief = {
        "O50_noG2": {
            **{c: counts_nog2["O50"][c].get("O", 0) for c in NEW_CONDITIONS},
            **{c: baseline_counts[c].get("O", 0) for c in SEALED_BASELINES + S3B_BASELINES},
        },
        "transitions": {k: {kk: vv for kk, vv in v.items() if not kk.endswith("_ids")} for k, v in transitions.items()},
    }
    print(json.dumps(brief, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
