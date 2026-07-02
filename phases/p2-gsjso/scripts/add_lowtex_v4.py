#!/usr/bin/env python3
"""population-lock-aux v4 [1c] — add roof_lowtex_v4 to population_aux_v3.csv for all 199 buildings, using
the tau-validated ruler from [1]: T11 definition (np.gradient magnitude, threshold 0.02137 on [0,1] gray)
on v3's EXACT selected view + roof polygon mask (same build_crop as v3). Reason: anchor validation showed
v3's Sobel lowtex separates textureless/textured anchors by only ~0.017 (control-p90 threshold misses
5/6 textureless anchors) whereas np.gradient separates by ~0.21 (12x). Observe only; ruler=김휘영.
Runs in jointbuildgs:dev (cv2)."""
import sys, csv, json
from pathlib import Path
import numpy as np
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from population_aux_v3 import parse_cam_model, parse_cameras, gml_building, DATA, REPO
from texture_anchor_check import build_crop, lowtex, T11_THR

CSV = REPO / "docs/population_aux_v3.csv"
CSV_RESULTS = REPO / "results/tum_transfer/mob/overseg_lever/population_aux_v3.csv"
BVIEW = REPO / "results/tum_transfer/mob/overseg_lever/population_aux_v3_bestview.json"


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    cam_by = {c.name: c for c in cams}
    bview = {k.replace("DEBY_LOD2_", ""): v for k, v in json.load(open(BVIEW)).items()}
    rows = list(csv.DictReader(open(CSV)))
    n_ok = 0
    for r in rows:
        b = r["building_id"].replace("DEBY_LOD2_", "")
        vn = bview.get(b); r["roof_lowtex_v4"] = ""
        if not vn or vn not in cam_by:
            continue
        _, roof, _ = gml_building(b)
        if not roof:
            continue
        cr = build_crop(cam_by[vn], roof, W, H, params, sr)
        if cr is None:
            continue
        m = lowtex(cr["crop"], cr["mask"], "npgrad", T11_THR)
        if m:
            r["roof_lowtex_v4"] = round(m["lowtex"], 3); n_ok += 1
    cols = list(rows[0].keys())
    if "roof_lowtex_v4" not in cols:
        cols.append("roof_lowtex_v4")
    for out in (CSV, CSV_RESULTS):
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    vals = [float(r["roof_lowtex_v4"]) for r in rows if r["roof_lowtex_v4"] != ""]
    print(f"roof_lowtex_v4 computed {n_ok}/199 | min {min(vals):.3f} med {np.median(vals):.3f} max {max(vals):.3f}")
    print(f"vs v3 roof_lowtex_frac(Sobel): med {np.median([float(r['roof_lowtex_frac']) for r in rows if r['roof_lowtex_frac'] not in ('','nan')]):.3f}")


if __name__ == "__main__":
    main()
