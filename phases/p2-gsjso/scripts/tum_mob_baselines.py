#!/usr/bin/env python3
"""P2 make-or-break — precompute per-building baselines for the 5-way eval.

For each of the 11 make-or-break buildings:
  - reference LoD2 RoofSurface / WallSurface counts (from CityGML) and UTM xy bbox,
  - footprint polygon + area (from footprints_aoi.geojson),
  - ALS point count and roof-point density inside footprint (density-match target).

Outputs baselines.json. Runs in the P0 tools container (laspy + numpy + stdlib xml).
EPSG:25832. Engine untouched.
"""
import argparse, glob, json, math
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import laspy
from matplotlib.path import Path as MplPath

GML_NS = "http://www.opengis.net/gml"
SURF = {"RoofSurface": "roof", "WallSurface": "wall", "GroundSurface": "ground"}


def localname(t): return t.rsplit("}", 1)[-1]


def poslist(text):
    v = [float(x) for x in text.split()]
    return np.asarray(v, dtype=np.float64).reshape(-1, 3)


def parse_gml(gml_files, targets):
    info = {t: {"roof": 0, "wall": 0, "ground": 0,
                "xmin": math.inf, "ymin": math.inf, "zmin": math.inf,
                "xmax": -math.inf, "ymax": -math.inf, "zmax": -math.inf} for t in targets}
    for gml in gml_files:
        for _, elem in ET.iterparse(str(gml), events=("end",)):
            if localname(elem.tag) != "Building":
                continue
            bid = elem.get("{%s}id" % GML_NS)
            if bid in info:
                d = info[bid]
                for surf in elem.iter():
                    ln = localname(surf.tag)
                    if ln in SURF:
                        d[SURF[ln]] += 1
                        for pl in surf.iter("{%s}posList" % GML_NS):
                            if pl.text:
                                a = poslist(pl.text)
                                d["xmin"] = min(d["xmin"], a[:, 0].min()); d["xmax"] = max(d["xmax"], a[:, 0].max())
                                d["ymin"] = min(d["ymin"], a[:, 1].min()); d["ymax"] = max(d["ymax"], a[:, 1].max())
                                d["zmin"] = min(d["zmin"], a[:, 2].min()); d["zmax"] = max(d["zmax"], a[:, 2].max())
            elem.clear()
    return info


def footprint_polys(geojson, targets):
    feats = json.load(open(geojson))["features"]
    out = {}
    for f in feats:
        bid = f["properties"].get("building_id")
        if bid in targets:
            g = f["geometry"]
            ring = (g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])
            out[bid] = np.asarray(ring)[:, :2]
    return out


def poly_area(ring):
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def als_stats(als_glob, ring, buffer):
    x0, y0 = ring[:, 0].min() - buffer, ring[:, 1].min() - buffer
    x1, y1 = ring[:, 0].max() + buffer, ring[:, 1].max() + buffer
    fp = MplPath(ring)
    n_box = 0
    n_fp = 0
    zs = []
    for laz in glob.glob(als_glob):
        las = laspy.read(laz)
        X, Y, Z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
        m = (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
        if not m.any():
            continue
        Xb, Yb, Zb = X[m], Y[m], Z[m]
        n_box += len(Xb)
        infp = fp.contains_points(np.column_stack([Xb, Yb]))
        n_fp += int(infp.sum())
        if infp.any():
            zs.append(Zb[infp])
    return n_box, n_fp, (np.concatenate(zs) if zs else np.array([]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gml", nargs="+", required=True)
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--als-glob", required=True)
    ap.add_argument("--buffer", type=float, default=15.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--targets", nargs="*", default=[
        "42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
        "4908166", "4908176", "4906969", "4908023", "4906972"])
    A = ap.parse_args()
    targets = [f"DEBY_LOD2_{t}" for t in A.targets]

    gml_info = parse_gml(A.gml, set(targets))
    fps = footprint_polys(A.geojson, set(targets))

    out = {}
    for t in targets:
        gi = gml_info[t]
        ring = fps.get(t)
        area = float(poly_area(ring)) if ring is not None else None
        n_box, n_fp, zfp = als_stats(A.als_glob, ring, A.buffer) if ring is not None else (0, 0, np.array([]))
        roof_dens = (n_fp / area) if (area and area > 0) else None
        out[t] = {
            "ref_roof_surfaces": gi["roof"], "ref_wall_surfaces": gi["wall"],
            "ref_ground_surfaces": gi["ground"],
            "bbox_utm": [gi["xmin"], gi["ymin"], gi["xmax"], gi["ymax"]],
            "z_utm": [gi["zmin"], gi["zmax"]],
            "footprint_area_m2": area,
            "als_pts_in_box": int(n_box), "als_pts_in_footprint": int(n_fp),
            "als_roof_density_pps_m2": roof_dens,
        }
        print(f"{t}: ref_roof={gi['roof']} ref_wall={gi['wall']} area={area:.1f} "
              f"als_fp={n_fp} als_dens={roof_dens:.1f}" if area else f"{t}: ref_roof={gi['roof']}")
    Path(A.out).parent.mkdir(parents=True, exist_ok=True)
    Path(A.out).write_text(json.dumps(out, indent=2))
    print(f"[done] wrote {A.out}")


if __name__ == "__main__":
    main()
