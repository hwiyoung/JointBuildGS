#!/usr/bin/env python3
"""P2 make-or-break — accuracy vs reference: RMS of GS roof points to nearest reference LoD2 roof plane.

Reference roof planes are extracted per building from CityGML RoofSurface polygons (orthometric).
GS points (classified building, in footprint) are ELLIPSOIDAL height (~+48 m geoid vs GML) so we
solve a 1-DOF vertical alignment Delta_z (search near the geoid undulation) that minimises the
point-to-nearest-plane RMS, and report the aligned RMS + Delta_z + n_points. EPSG:25832 (xy).
Runs in P0 tools container (laspy + numpy + stdlib xml).
"""
import csv, glob, json, sys
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import laspy
from matplotlib.path import Path as MplPath

REPO = "/workspace/JointBuildGS"
GML_NS = "http://www.opengis.net/gml"
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]
ARMS = ["vanilla", "baseline", "mutual", "structure", "both"]


def localname(t): return t.rsplit("}", 1)[-1]


def fit_plane(ring):
    c = ring.mean(0)
    _, _, Vt = np.linalg.svd(ring - c, full_matrices=False)
    n = Vt[-1]
    return n / (np.linalg.norm(n) + 1e-12), c


def parse_ref_roof_planes(gml_files, targets):
    planes = {t: [] for t in targets}
    for gml in gml_files:
        for _, elem in ET.iterparse(str(gml), events=("end",)):
            if localname(elem.tag) != "Building":
                continue
            bid = elem.get("{%s}id" % GML_NS)
            if bid in planes:
                for surf in elem.iter():
                    if localname(surf.tag) == "RoofSurface":
                        for pl in surf.iter("{%s}posList" % GML_NS):
                            if pl.text:
                                a = np.asarray([float(x) for x in pl.text.split()]).reshape(-1, 3)
                                if len(a) >= 3:
                                    planes[bid].append(fit_plane(a[:-1] if np.allclose(a[0], a[-1]) else a))
            elem.clear()
    return planes


def nearest_plane_dist(P, planes, dz):
    Q = P.copy(); Q[:, 2] -= dz
    d = np.full(len(Q), np.inf)
    for n, c in planes:
        d = np.minimum(d, np.abs((Q - c) @ n))
    return d


def aligned_rms(P, planes):
    best = (np.inf, None)
    for dz in np.arange(40.0, 56.0, 0.25):
        d = nearest_plane_dist(P, planes, dz)
        rms = float(np.sqrt((d ** 2).mean()))
        if rms < best[0]:
            best = (rms, float(dz))
    return best


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=ARMS,
                    help="config arm names to score (default = the 5 original ablations)")
    ap.add_argument("--out", default=f"{REPO}/results/tum_transfer/mob_analysis/ref_rms.csv")
    A = ap.parse_args()
    arms = A.arms

    gml = [f"{REPO}/phases/p0-audit/data/raw/lod2/690_5334.gml",
           f"{REPO}/phases/p0-audit/data/raw/lod2/690_5336.gml"]
    geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    targets = [f"DEBY_LOD2_{t}" for t in TARGETS]
    planes = parse_ref_roof_planes(gml, set(targets))

    def ring(bid):
        g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
        return np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]

    rows = []
    for cfg in arms:
        for t in TARGETS:
            bid = f"DEBY_LOD2_{t}"
            if not planes[bid]:
                continue
            fp = MplPath(ring(bid))
            for tag in ["orig", "matched"]:
                las = f"{REPO}/phases/p0-audit/runs/mob_eval/{cfg}/{bid}_{tag}_classified.las"
                if not Path(las).exists():
                    continue
                c = laspy.read(las)
                cl = np.asarray(c.classification)
                P = np.column_stack([np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)])
                m = (cl == 6) & fp.contains_points(P[:, :2])
                Pb = P[m]
                if len(Pb) < 10:
                    rows.append({"config": cfg, "bid": bid, "tag": tag, "n_roof_pts": int(len(Pb)),
                                 "ref_planes": len(planes[bid]), "rms_to_ref_m": None, "dz_m": None})
                    continue
                rms, dz = aligned_rms(Pb, planes[bid])
                rows.append({"config": cfg, "bid": bid, "tag": tag, "n_roof_pts": int(len(Pb)),
                             "ref_planes": len(planes[bid]), "rms_to_ref_m": round(rms, 3), "dz_m": dz})
                print(f"{cfg:9} {bid:20} {tag:8} n={len(Pb):>7} ref_planes={len(planes[bid])} "
                      f"rms_to_ref={rms:.3f}m dz={dz:.1f}")
    out = A.out
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["config", "bid", "tag", "n_roof_pts", "ref_planes", "rms_to_ref_m", "dz_m"])
        w.writeheader(); w.writerows(rows)
    print(f"[done] {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
