#!/usr/bin/env python3
"""D1 auto-OX: v22 criterion over every union-curve delta run.

Same code path as the A2/S3b evaluations (sealed v22 reference, thresholds,
O_noG2 basis + withG2 from each run's own val3dity report). One CSV per run
under <run>/evaluation_auto_ox/ plus a combined summary under the phase report
directory. NOT_OFFICIAL development read-out; scientific_verdict stays null.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

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

REPO = Path(__file__).resolve().parents[3]
ARTIFACTS = Path("/artifacts/JointBuildGS")
D1_CONFIG = REPO / "configs/p2/journal1_phase_d_v1/d1_union_curve_v1.json"
V22_CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/reference_auto_ox_v1.json"
V22_ROOT = ARTIFACTS / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-AUTO-OX-v22-ROBUST-PLANE-MATCH"


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    d1 = json.load(open(D1_CONFIG))
    out_root = Path(d1["out_root"])
    report_dir = out_root.parent / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    chosen = set(json.load(open(d1["population"]))["effective_selected_ids"])

    config = load_config(V22_CONFIG)
    viewer = json.loads((V22_ROOT / "viewer_manifest.json").read_text(encoding="utf-8"))
    origin = np.asarray(viewer["scene_local_origin_xyz"], dtype=np.float64)
    footprint_spec = config["shared_footprints"]
    footprint_payload = json.loads((ARTIFACTS / footprint_spec["path"]).read_text(encoding="utf-8"))
    footprints = {
        str(f["properties"][footprint_spec["id_field"]]): shape(f["geometry"])
        for f in footprint_payload["features"]
    }
    stable_ids = {b["stable_id"] for b in viewer["buildings"]}
    reference_surfaces = parse_reference_roofs(
        [ARTIFACTS / s["path"] for s in config["lod2_reference_sources"]],
        stable_ids, origin,
        float(config["structure_metric"]["lod2_reference_z_shift_to_viewer_m"]),
    )
    structure = config["structure_metric"]
    geometry = config["geometry_metric"]

    # Per-building reference context is delta-invariant: compute once.
    contexts = {}
    for building in viewer["buildings"]:
        sid = building["stable_id"]
        footprint_local = translate(footprints[sid], xoff=-origin[0], yoff=-origin[1])
        inset = footprint_local.buffer(-float(geometry["evaluation_inset_m"]))
        evaluation_polygon = inset if not inset.is_empty else footprint_local
        reference_planes = major_planes(reference_surfaces[sid], structure["minimum_plane_area_m2"])
        lod_triangles = reference_triangles(reference_surfaces[sid])
        uas_cells = (
            roof_reference_cells(V22_ROOT / building["lidar"]["points"], geometry["cell_size_m"], evaluation_polygon)
            if building["lidar"].get("point_count", 0) > 0
            else np.empty((0, 3), dtype=np.float64)
        )
        if len(uas_cells):
            cells, role = uas_cells, "CURRENT_UAS_CLASS6_ANY_SUPPORT"
        else:
            cells = reference_grid_from_lod2(lod_triangles, evaluation_polygon, geometry["cell_size_m"])
            role = "LOD2_ROOFSURFACE_FALLBACK"
        contexts[sid] = {
            "population_index": building["population_index"],
            "planes": reference_planes, "cells": cells, "role": role,
            "available": bool(reference_planes) and bool(len(cells)),
        }

    summary_counts = {}
    for run in d1["runs"]:
        label, cond = run["label"], run["condition"]
        run_root = out_root / label
        cityjson_path = run_root / "work" / cond / "assembled.city.json"
        report_path = run_root / "work" / cond / "val3dity_report.json"
        if not cityjson_path.is_file():
            print(f"[d1-ox] SKIP {label}: assembled.city.json missing")
            continue
        ox_dir = run_root / "evaluation_auto_ox"
        csv_path = ox_dir / "auto_ox_building_v1.csv"
        if csv_path.is_file():
            rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        else:
            ox_dir.mkdir(parents=True, exist_ok=True)
            cityjson = json.loads(cityjson_path.read_text(encoding="utf-8"))
            validity = val3dity_feature_map(json.loads(report_path.read_text(encoding="utf-8")))
            rows = []
            for sid, ctx in contexts.items():
                g0, g1, _ = cityjson_g0_g1(cityjson, sid)
                g2, _ = feature_validity(validity, sid, g0)
                world_triangles = lod22_triangles(cityjson, sid)
                prediction_triangles = (
                    np.asarray(world_triangles, dtype=np.float64) - origin[None, None, :]
                    if world_triangles else np.empty((0, 3, 3), dtype=np.float64)
                )
                prediction_planes = major_planes(
                    cluster_roof_planes(prediction_triangles, structure["cluster_angle_deg"], structure["cluster_height_m"]),
                    structure["minimum_plane_area_m2"],
                )
                g4 = g4_metrics(ctx["cells"], prediction_triangles)
                if len(ctx["cells"]) and g4.get("coverage") is None:
                    g4["coverage"] = 0.0
                for key in SENSITIVITY:
                    overlap = float(key[1:]) / 100.0
                    g3 = plane_match_metrics(ctx["planes"], prediction_planes, overlap,
                                             structure["normal_tolerance_deg"], structure["height_tolerance_m"])
                    nog2 = classify_binary(g0=g0, g1=g1, g2=True, g3=g3, g4=g4,
                                           reference_available=ctx["available"],
                                           thresholds=config["acceptance_thresholds"])
                    full = classify_binary(g0=g0, g1=g1, g2=g2, g3=g3, g4=g4,
                                           reference_available=ctx["available"],
                                           thresholds=config["acceptance_thresholds"])
                    rows.append({
                        "population_index": ctx["population_index"], "stable_id": sid,
                        "run_label": label, "criterion": key,
                        "verdict_noG2": nog2["verdict"], "verdict_withG2": full["verdict"],
                        "g4_reference_role": ctx["role"],
                        "g4_rmse_z_m": nog2["g4"].get("rmse_z_m"),
                        "g3_plane_area_recall": nog2["g3"].get("plane_area_recall"),
                    })
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows([{k: v for k, v in r.items()} for r in rows])
        o50 = [r for r in rows if r["criterion"] == "O50"]
        summary_counts[label] = {
            "O50_noG2_199": dict(Counter(r["verdict_noG2"] for r in o50)),
            "O50_noG2_selected93": dict(Counter(r["verdict_noG2"] for r in o50 if r["stable_id"] in chosen)),
            "O50_noG2_selected93_current_anchored_O": sum(
                1 for r in o50 if r["stable_id"] in chosen and r["verdict_noG2"] == "O"
                and r["g4_reference_role"] == "CURRENT_UAS_CLASS6_ANY_SUPPORT"),
        }
        print(f"[d1-ox] {label}: {summary_counts[label]['O50_noG2_selected93']}")

    payload = {
        "schema": "jointbuildgs.p2.journal1_phase_d_v1.d1_auto_ox.v1",
        "task_id": d1["task_id"], "stage": "D1",
        "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(),
        "criterion_version": config["criterion_version"],
        "basis_note": "O50 noG2 (S3b/A2와 동일 기준); population = confirmed 93 subset도 병기",
        "runs": summary_counts,
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    (report_dir / "d1_auto_ox_summary_v1.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(json.dumps({k: v["O50_noG2_selected93"] for k, v in summary_counts.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
