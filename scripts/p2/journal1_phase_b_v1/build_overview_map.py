#!/usr/bin/env python3
"""Build the journal1 Phase-B overview map: all 199 target buildings with the
first-pass (1차) triage classification and E1/E2 roof-coverage modes.

Extends the Phase-B coverage diagnostic to every census building (tiers A/B/C/
NA), classifies each one from tier + coverage signals, and emits a static map
page (map.html + map_data.json) into the viewer payload so the same 8881 server
serves it. The classification is provisional review support — B-tier rows carry
the reviewer's 2026-08-12 first-pass no-change declaration, everything else is
automatic; no scientific verdict is made and nothing here feeds training or
parameter selection.

Run inside the project container (same mounts as build_label_review_viewer.py),
after build_label_review_viewer.py (the map links into the review viewer).
"""

import argparse
import csv
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_label_review_viewer import git_commit, viewer_local_rings  # noqa: E402
import coverage_diagnostic as cd  # noqa: E402

CLASSES = [
    "A_DISPLACED", "A_DEMOLITION_SUSPECT",              # change candidates
    "A_VEG_SUSPECT", "A_ZOFFSET", "A_REVIEW",           # needs review
    "B_NOCHANGE_1ST", "C_CONSISTENT",                   # no-change / consistent
    "A_EMPTY", "NA_E2_OK", "NA_EMPTY",                  # gap / undecidable
]
GROUP_OF = {
    "A_DISPLACED": "CHANGE_CAND", "A_DEMOLITION_SUSPECT": "CHANGE_CAND",
    "A_VEG_SUSPECT": "REVIEW", "A_ZOFFSET": "REVIEW", "A_REVIEW": "REVIEW",
    "B_NOCHANGE_1ST": "NOCHANGE", "C_CONSISTENT": "NOCHANGE",
    "A_EMPTY": "GAP", "NA_E2_OK": "GAP", "NA_EMPTY": "GAP",
}


def classify(tier, e1, e2, gate_any, thr):
    """First-pass class from tier + coverage signals (priority order)."""
    if tier == "C_CONSISTENT":
        return "C_CONSISTENT"
    if tier == "B_MODERATE_MISMATCH":
        return "B_NOCHANGE_1ST"
    if tier == "NA_E1_INSUFFICIENT":
        if e2 and e2["any_xy"] >= thr["gate_min_cover"]:
            return "NA_E2_OK"
        return "NA_EMPTY"
    # A_STRONG_MISMATCH
    if not gate_any:
        mx = max(e1["n_pts"] if e1 else 0, e2["n_pts"] if e2 else 0)
        return "A_DISPLACED" if mx >= thr["displaced_min_pts"] else "A_EMPTY"
    if e1 and e1["groundonly_xy"] >= thr["ground_min"]:
        return "A_DEMOLITION_SUSPECT"
    if e1 and ((e1.get("above_ridge_share") or 0) >= thr["above_ridge_min"]
               or (e1.get("veg_cell_share") or 0) >= thr["veg_min"]):
        return "A_VEG_SUSPECT"
    if e1 and e1.get("dz_med_m") is not None and abs(e1["dz_med_m"]) >= thr["dz_min"] \
            and e1["any_xy"] >= thr["dz_cover_min"]:
        return "A_ZOFFSET"
    return "A_REVIEW"


def _num(s, cast=float):
    """CSV cell to number; NA rows carry empty strings."""
    try:
        return cast(s)
    except (TypeError, ValueError):
        return None


def footprint_xy(geom, origin):
    """Exterior rings of a (Multi)Polygon in viewer-local XY, rounded."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    out = []
    for poly in polys:
        if not poly:
            continue
        out.append([[round(x - origin[0], 2), round(y - origin[1], 2)]
                    for x, y, *_ in poly[0]])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/p2/journal1_phase_b_v1/run_v1.json")
    args = ap.parse_args()
    cfg_all = json.load(open(args.config))
    cov_cfg = cfg_all["coverage_diagnostic"]
    map_cfg = cfg_all["overview_map"]
    thr = dict(map_cfg["classify_thresholds"], gate_min_cover=cov_cfg["gate_min_cover"])
    origin = cfg_all["origin"]
    out_dir = Path(cfg_all["out_dir"])
    script_dir = Path(__file__).resolve().parent

    rows = list(csv.DictReader(open(cfg_all["candidates_csv"])))
    targets = {r["stable_id"] for r in rows}
    rings = viewer_local_rings(cfg_all["gml_tiles"], targets, origin,
                               cfg_all["lod2_z_shift_to_viewer_m"])
    fps = {f["properties"]["stable_id"]: f["geometry"]
           for f in json.load(open(map_cfg["footprints_geojson"]))["features"]}
    asset_maps = {}
    for arm, d in cfg_all["asset_dirs"].items():
        asset_maps[arm] = {p.name.split("_", 1)[1].removesuffix(".points.ply"): p
                           for p in sorted(Path(d).glob("B*_*.points.ply"))}
    viewer_set = {b["stable_id"] for b in json.load(
        open(out_dir / "review_manifest.json"))["buildings"]}

    buildings, cov_rows, errors = [], [], []
    for r in rows:
        sid = r["stable_id"]
        got = rings.get(sid)
        planes = cd.ring_planes(got["rings"]) if got else []
        _roof, centers = cd.roof_cells(planes, cov_cfg["cell_m"]) if planes else (None, [])
        arm_stats = {}
        for arm in ("E1", "E2"):
            src = asset_maps[arm].get(sid)
            if src is None or not centers:
                arm_stats[arm] = None
                continue
            pts = cd.read_crop(src)
            st = cd.arm_stats(pts, planes, centers, cov_cfg["cell_m"], cov_cfg)
            st["above_ridge_share"] = cd.above_ridge_share(
                pts, got["rings"], cov_cfg["above_ridge_m"])
            arm_stats[arm] = st
        if not centers:
            errors.append(sid)
        covs = [arm_stats[a]["any_xy"] for a in ("E1", "E2") if arm_stats[a]]
        gate_any = bool(covs and max(covs) >= cov_cfg["gate_min_cover"])
        cls = classify(r["tier"], arm_stats["E1"], arm_stats["E2"], gate_any, thr)
        e1_src = asset_maps["E1"].get(sid)
        bkey = e1_src.name.split("_", 1)[0] if e1_src else None
        buildings.append({
            "stable_id": sid, "bkey": bkey, "tier": r["tier"],
            "cls": cls, "group": GROUP_OF[cls], "gate_any_070": gate_any,
            "in_viewer": sid in viewer_set,
            "acc_median_m": _num(r["e1_lod2_acc_median_m"]),
            "n_e1_roof_pts": _num(r["n_e1_roof_pts"], int),
            "cov": arm_stats,
            "fp": footprint_xy(fps[sid], origin) if sid in fps else [],
        })
        cov_rows.append({"stable_id": sid, "bkey": bkey, "tier": r["tier"],
                         "cls": cls, "gate_any_070": gate_any, **{
                             a: arm_stats[a] for a in ("E1", "E2")}})

    generated_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = {c: sum(1 for b in buildings if b["cls"] == c) for c in CLASSES}
    meta = {
        "schema": "journal1_phase_b_overview_map_v1",
        "task_id": cfg_all["task_id"], "status": cfg_all["status"],
        "scientific_verdict": None, "generated_utc": generated_utc,
        "n_buildings": len(buildings), "counts": counts,
        "params": {"cell_m": cov_cfg["cell_m"], "gate_min_cover": cov_cfg["gate_min_cover"],
                    **map_cfg["classify_thresholds"]},
        "classes": CLASSES,
        "b_tier_note": ("B_NOCHANGE_1ST reflects the reviewer's 2026-08-12 first-pass "
                        "declaration that all B-tier buildings are no-change; "
                        "it is not an automatic result."),
        "frame_note": "viewer-local XY = EPSG:25832 - origin[0:2]",
    }
    (out_dir / "map_data.json").write_text(json.dumps(
        {"meta": meta, "buildings": buildings}, ensure_ascii=False, separators=(",", ":")))
    import shutil
    shutil.copy2(script_dir / "viewer" / "map.html", out_dir / "map.html")

    cov_out = Path(map_cfg["coverage_all_out"])
    cov_out.parent.mkdir(parents=True, exist_ok=True)
    cov_out.write_text(json.dumps({
        "schema": "journal1_phase_b_coverage_all199_v1", **meta,
        "buildings": cov_rows}, ensure_ascii=False, indent=1))

    receipt = {
        "task_id": cfg_all["task_id"], "status": cfg_all["status"],
        "scientific_verdict": None, "generated_utc": generated_utc,
        "tool": "scripts/p2/journal1_phase_b_v1/build_overview_map.py",
        "config": str(args.config), "git_commit": git_commit(script_dir.parents[2]),
        "python": platform.python_version(),
        "inputs": {"candidates_csv": cfg_all["candidates_csv"],
                    "gml_tiles": cfg_all["gml_tiles"],
                    "footprints_geojson": map_cfg["footprints_geojson"],
                    "asset_dirs": cfg_all["asset_dirs"]},
        "counts": counts, "no_roof_polygon": errors,
        "outputs": {"map_html": str(out_dir / "map.html"),
                     "map_data": str(out_dir / "map_data.json"),
                     "coverage_all199": str(cov_out)},
    }
    (cov_out.parent / "map_receipt_v1.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps({"buildings": len(buildings), "counts": counts,
                      "no_roof_polygon": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
