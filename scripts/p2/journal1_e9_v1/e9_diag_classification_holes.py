#!/usr/bin/env python3
"""E9 lever-1 diagnosis: classification holes in the sealed E2 lineage.

For each confirmed-93 building, completeness of the E2 scene against the E1
roof reference is computed twice from the SAME footprint-only crop of the
sealed C2_MVS classified scene: (a) raw geometry (all classes) and
(b) class-6 only. The gap is the classification hole — roof geometry that MVS
observed but SMRF/overlay failed to hand to Roofer as building. Cross-checked
against the sealed class-6 crop lineage row (footprint+3m) for reference.

CPU, no training, no new chains. Non-confirmatory; scientific_verdict null.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.affinity import translate
from shapely.geometry import shape

from scripts.p2.journal1_phase_a_v1.geometry_eval import read_ply, roof_points, subsample, pca_normals  # noqa: F401

REPO = Path("/workspace/JointBuildGS")
ART = Path("/artifacts/JointBuildGS")
A2 = ART / "phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1"
OUT = ART / "phase-payloads/p2/journal1_e9_v1/P2-JOURNAL1-E9-v1/diagnosis"
E2_SCENE = ART / ("phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
                    "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/work/C2_MVS/classified_scene.laz")
J1 = json.load(open(REPO / "configs/p2/journal1_phase_a_v1/run_v2_e7e8.json"))
ORIGIN = np.asarray(J1["origin"], dtype=np.float64)
TAUS = (0.25, 0.5)


def completeness(reference: np.ndarray, method: np.ndarray, tau: float) -> float | None:
    if not len(reference):
        return None
    if not len(method):
        return 0.0
    tree = cKDTree(method)
    d, _ = tree.query(reference, k=1, workers=-1)
    return float(np.mean(d <= tau))


def main() -> None:
    import laspy

    OUT.mkdir(parents=True, exist_ok=True)
    chosen = sorted(json.load(open(A2 / "labels/selection_confirm_v1.json"))["effective_selected_ids"])
    footprints = json.load(open(J1["footprints_geojson"]))
    polys = {}
    for feature in footprints["features"]:
        sid = str(feature["properties"]["stable_id"])
        if sid in chosen:
            polys[sid] = shape(feature["geometry"])

    print("[e9-diag] loading E2 scene ...", flush=True)
    xyz_parts, cls_parts = [], []
    with laspy.open(E2_SCENE) as reader:
        for chunk in reader.chunk_iterator(2_000_000):
            xyz_parts.append(np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z))))
            cls_parts.append(np.asarray(chunk.classification).astype(np.uint8))
    scene = np.concatenate(xyz_parts)
    cls = np.concatenate(cls_parts)
    print(f"[e9-diag] scene {len(scene):,} pts", flush=True)

    sealed_comp = {}
    for line in open(A2 / "a2/evaluation_merged/rows.jsonl", encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        if row["arm"] == "E2" and row["gt"] == "e1" and row["stable_id"] in polys:
            sealed_comp[row["stable_id"]] = {t: row.get(f"completeness@{t}") for t in TAUS}

    e1_dir = Path(J1["e1_reference_dir"])
    rows = []
    for sid in chosen:
        poly = polys[sid]
        hits = sorted(e1_dir.glob(f"*_{sid}.points.ply"))
        if not hits:
            continue
        e1_xyz, e1_cls = read_ply(hits[0])
        e1_roof, _ = roof_points(e1_xyz, e1_cls)
        if len(e1_roof) < 30:
            continue
        e1_roof, _ = subsample(e1_roof, J1["max_points_per_arm"])
        x0, y0, x1, y1 = poly.bounds
        box = (scene[:, 0] >= x0) & (scene[:, 0] <= x1) & (scene[:, 1] >= y0) & (scene[:, 1] <= y1)
        idx = np.flatnonzero(box)
        if len(idx):
            inside = shapely.contains_xy(poly, scene[idx, 0], scene[idx, 1])
            idx = idx[inside]
        crop = scene[idx] - ORIGIN
        crop_cls = cls[idx]
        raw = crop
        cls6 = crop[crop_cls == 6]
        entry = {"stable_id": sid, "n_raw": int(len(raw)), "n_cls6": int(len(cls6)),
                 "cls6_share": round(float(len(cls6) / len(raw)), 3) if len(raw) else None}
        for tau in TAUS:
            c_raw = completeness(e1_roof, raw, tau)
            c_c6 = completeness(e1_roof, cls6, tau)
            entry[f"comp_raw@{tau}"] = None if c_raw is None else round(c_raw, 3)
            entry[f"comp_cls6@{tau}"] = None if c_c6 is None else round(c_c6, 3)
            entry[f"hole@{tau}"] = None if (c_raw is None or c_c6 is None) else round(c_raw - c_c6, 3)
            sealed = sealed_comp.get(sid, {}).get(tau)
            entry[f"sealed_crop_comp@{tau}"] = None if sealed is None else round(sealed, 3)
        rows.append(entry)
        print(f"[e9-diag] {sid.split('_')[-1]}: raw@0.25 {entry['comp_raw@0.25']} cls6 {entry['comp_cls6@0.25']} hole {entry['hole@0.25']}", flush=True)

    with (OUT / "classification_holes_v1.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    holes = [r for r in rows if r["hole@0.25"] is not None]
    big = [r for r in holes if r["hole@0.25"] >= 0.10]
    summary = {
        "schema": "jointbuildgs.p2.journal1_e9_v1.classification_holes.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_buildings": len(rows),
        "hole_ge_010_count": len(big),
        "hole_ge_010_ids": [r["stable_id"] for r in sorted(big, key=lambda r: -r["hole@0.25"])],
        "hole_median": float(np.median([r["hole@0.25"] for r in holes])),
        "hole_p90": float(np.percentile([r["hole@0.25"] for r in holes], 90)),
        "raw_comp_median@0.25": float(np.median([r["comp_raw@0.25"] for r in holes])),
        "cls6_comp_median@0.25": float(np.median([r["comp_cls6@0.25"] for r in holes])),
        "note": "hole = comp_raw - comp_cls6 within the same footprint-only crop; the recoverable classification loss",
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    (OUT / "classification_holes_summary_v1.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("hole_ge_010_ids",)}, indent=1))
    print("top holes:", summary["hole_ge_010_ids"][:10])


if __name__ == "__main__":
    main()
