#!/usr/bin/env python3
"""D2a same-lineage union scoring: put union(0)/union(delta)/E2 through the
exact same footprint-only crop + evaluator as the D2a GS readout, on the same
building, so Claim-B deltas compare like-for-like within one measurement
lineage. CPU only. Non-confirmatory; scientific_verdict stays null.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.p2.journal1_phase_a_v1.geometry_eval import (
    FaceSet,
    eval_building_arm,
    load_lod2_faces,
    pca_normals,
    read_ply,
    roof_points,
    subsample,
)

REPO = Path("/workspace/JointBuildGS")
ART = Path("/artifacts/JointBuildGS")
SID = "DEBY_LOD2_4906982"
J1 = json.load(open(REPO / "configs/p2/journal1_phase_a_v1/run_v2_e7e8.json"))
VIEWER_ORIGIN = np.asarray(J1["origin"], dtype=np.float64)
SOURCES = {
    "E8_delta0": ART / "phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1/a2/work/E8/fused_surface.laz",
    "E8_dx050": ART / "phase-payloads/p2/journal1_phase_d_v1/P2-JOURNAL1-PHASE-D-v1/union_curve/E8_dx050/work/E8/fused_surface.laz",
    "E2_only": ART / "phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/work/C2_MVS/classified_scene.laz",
}


def footprint_polygon():
    from shapely.affinity import translate
    from shapely.geometry import shape

    payload = json.load(open(J1["footprints_geojson"]))
    feature = next(f for f in payload["features"] if f["properties"]["stable_id"] == SID)
    world = shape(feature["geometry"])
    local = translate(world, xoff=-VIEWER_ORIGIN[0], yoff=-VIEWER_ORIGIN[1])
    return world.bounds, local


def crop_scene(path: Path, world_bounds, local_poly) -> np.ndarray:
    import laspy
    import shapely

    x0, y0, x1, y1 = world_bounds
    parts = []
    with laspy.open(path) as reader:
        for chunk in reader.chunk_iterator(2_000_000):
            x = np.asarray(chunk.x)
            y = np.asarray(chunk.y)
            keep = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
            if bool(keep.any()):
                z = np.asarray(chunk.z)[keep]
                parts.append(np.column_stack((x[keep], y[keep], z)))
    if not parts:
        return np.zeros((0, 3))
    xyz = np.concatenate(parts) - VIEWER_ORIGIN
    inside = shapely.contains_xy(local_poly, xyz[:, 0], xyz[:, 1])
    return xyz[inside]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    lod2 = load_lod2_faces(J1["gml_tiles"], {SID}, J1["origin"], J1["lod2_z_shift_to_viewer_m"])
    faceset = FaceSet(lod2[SID], J1["lod2_sample_step"]) if SID in lod2 else None
    e1_path = next(Path(J1["e1_reference_dir"]).glob(f"*_{SID}.points.ply"))
    e1_xyz, e1_cls = read_ply(e1_path)
    e1_roof, _ = roof_points(e1_xyz, e1_cls)
    e1_roof, _ = subsample(e1_roof, J1["max_points_per_arm"])
    e1_norm = pca_normals(e1_roof, J1["knn"])
    world_bounds, local_poly = footprint_polygon()

    results = {}
    for label, path in SOURCES.items():
        crop = crop_scene(path, world_bounds, local_poly)
        rows = eval_building_arm(crop, None, faceset, e1_roof, e1_norm, J1, False)
        results[label] = {"source": str(path), "crop_points": int(len(crop)), "rows": rows}
        print(f"[d2a-union] {label}: {len(crop)} pts", flush=True)
        for row in rows:
            keep = {k: row.get(k) for k in ("gt", "f1@0.5", "completeness@0.5",
                                              "precision@0.5", "acc_median", "z_spread")}
            print("  ", json.dumps(keep), flush=True)

    payload = {
        "schema": "jointbuildgs.p2.journal1_phase_d_v1.d2a_union_rows.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "building": SID,
        "lineage": "footprint-only crop of the scene surface (no ring, no class filter) — identical to the D2a GS readout crop, so GS and union deltas compare like-for-like",
        "results": results,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=1))
    print(f"[d2a-union] → {args.out}")


if __name__ == "__main__":
    main()
