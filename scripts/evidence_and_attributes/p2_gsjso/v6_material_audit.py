#!/usr/bin/env python3
"""P2 v6 analysis pack §1 — input point material per (11 buildings x 4 raw clouds).

Reuses the EXACT metric definitions from p0c_assembly_diag.py (imported, not re-derived):
pip / plane_rms / cell_zstd / coverage / metrics. Source = the raw arm's OWN classified LAS
(phases/p0-audit/runs/mob_eval/raw_*/DEBY_*_orig_classified.las) -> the building-class-6 points
each cloud actually fed Roofer (orig density, before ALS-matching). Datum = ELLIPSOIDAL UTM
(acmp/als already +48). Read-only, CPU, jointbuildgs-p0-tools:t0. Observation only.

Out: results/tum_transfer/mob/analysis_pack_v6/material_11x4.csv + material_11x4_obs.md
"""
import csv, json, sys
from pathlib import Path

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
import numpy as np, laspy
from p0c_assembly_diag import pip, plane_rms, cell_zstd, coverage, metrics  # noqa: F401 (verbatim defs)

REPO = "/workspace/JointBuildGS"
EVALROOT = f"{REPO}/phases/p0-audit/runs/mob_eval"
OUTDIR = f"{REPO}/results/tum_transfer/mob/analysis_pack_v6"
ARMS = [("sparse", "raw_sparse"), ("dense", "raw_dense"), ("acmp", "raw_acmp"), ("lidar", "raw_lidar")]
R8 = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"]
Q3 = ["4906969", "4906972", "4908023"]
TARGETS = [(t, "R") for t in R8] + [(t, "Q") for t in Q3]


def main():
    geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    rings = {}
    for f in geo:
        g = f["geometry"]
        rings[f["properties"]["building_id"]] = np.asarray(
            g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]

    rows, obs = [], []
    for short, cls in TARGETS:
        bid = f"DEBY_LOD2_{short}"
        ring = rings[bid]
        area = 0.5 * abs(np.dot(ring[:, 0], np.roll(ring[:, 1], -1)) - np.dot(ring[:, 1], np.roll(ring[:, 0], -1)))
        per = {}
        for cloud, arm in ARMS:
            las = f"{EVALROOT}/{arm}/{bid}_orig_classified.las"
            if not Path(las).exists():
                m = metrics(np.empty((0, 3)), ring, area); m["missing_las"] = True
            else:
                c = laspy.read(las)
                clp = np.asarray(c.classification)
                P = np.column_stack([np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)])
                sel = (clp == 6) & pip(P[:, :2], ring)
                m = metrics(P[sel], ring, area)
            per[cloud] = m
            rows.append({"building": short, "cls": cls, "cloud": cloud, "footprint_area_m2": round(float(area), 1),
                         "n_pts": m["n"], "density_pps_m2": m["dens"], "coverage": m["cov"],
                         "hole_frac": m["hole"], "plane_rms_m": m["rms"], "cell_zstd_m": m["zstd"],
                         "z_range_m": m["zrange"], "wall_frac": m["wall"]})
        # per-building one-line observation (no verdict)
        ns = {c: per[c]["n"] for c, _ in ARMS}
        mvs0 = [c for c in ("sparse", "dense", "acmp") if ns[c] == 0]
        tag = "[R]" if cls == "R" else "[Q]"
        obs.append(f"- **{short}** {tag} (area {area:.0f} m^2): "
                   f"n[sparse/dense/acmp/lidar]={ns['sparse']}/{ns['dense']}/{ns['acmp']}/{ns['lidar']}; "
                   + (f"MVS empty in footprint ({'/'.join(mvs0)}=0) -> textureless/out-of-range candidate; "
                      if mvs0 else "MVS has points; ")
                   + f"LiDAR n={ns['lidar']} dens={per['lidar']['dens']}.")

    Path(OUTDIR).mkdir(parents=True, exist_ok=True)
    keys = ["building", "cls", "cloud", "footprint_area_m2", "n_pts", "density_pps_m2", "coverage",
            "hole_frac", "plane_rms_m", "cell_zstd_m", "z_range_m", "wall_frac"]
    with open(f"{OUTDIR}/material_11x4.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    md = ["# §1 input material — per-building observation (orig density, building class-6 in footprint).",
          "Frame = ELLIPSOIDAL UTM (acmp/als +48 geoid, same as raw arm). Defs reused verbatim from "
          "p0c_assembly_diag.py (coverage cell=1.0m, cell_zstd cell=0.5m, plane_rms=dominant-plane SVD "
          "residual, wall_frac=pts >2m below p90 z). Observation only; verdict = 김휘영.\n"] + obs
    Path(f"{OUTDIR}/material_11x4_obs.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\n[done] {len(rows)} rows -> {OUTDIR}/material_11x4.csv + material_11x4_obs.md")


if __name__ == "__main__":
    main()
