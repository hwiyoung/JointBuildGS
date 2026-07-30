#!/usr/bin/env python3
"""B2 Phase 0 — how many of the 46 no_points footprints fall inside the TUM2TWIN Downtown bundle
coverage (Pix4D dense / ULS nadir / ULS manual)? The bundle covers only the downtown core, the
no_points are scene-wide. Read-only. footprints EPSG:25832; bundle bbox 32632 (~25832 within ~1m)."""
import csv, json
from collections import Counter
import numpy as np

W4C = "/workspace/JointBuildGS/phases/p0-audit/docs/W4c_no_points_breakdown.csv"
GEO = "/tmp/lod2.geojson"
# bundle bboxes (from pdal info, 32632; XY offset to 25832 < 1m)
PIX = (690739.9, 691189.1, 5335816.1, 5336389.8)
NAD = (690783.7, 691260.4, 5335829.5, 5336389.1)
MAN = (690788.0, 691100.8, 5335834.2, 5336052.8)


def inb(c, b):
    return b[0] <= c[0] <= b[1] and b[2] <= c[1] <= b[3]


def main():
    rows46 = list(csv.DictReader(open(W4C)))
    ids = [r["building_id"] for r in rows46 if r["building_id"].startswith("DEBY")]
    cls = {r["building_id"]: r["classification"] for r in rows46}
    feats = {f["properties"]["building_id"]: f["geometry"] for f in json.load(open(GEO))["features"]}
    nin = {"any": 0, "pix": 0, "nad": 0, "man": 0}
    inside = []
    for i in ids:
        g = feats.get(i)
        if not g:
            continue
        r = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])
        c = r[:, :2].mean(0)
        p, n, m = inb(c, PIX), inb(c, NAD), inb(c, MAN)
        if p or n or m:
            nin["any"] += 1
            inside.append((i.replace("DEBY_LOD2_", ""), cls[i], int(p), int(n), int(m)))
        nin["pix"] += p; nin["nad"] += n; nin["man"] += m
    print(f"46 no_points footprint centroid inside bundle coverage:")
    print(f"  ANY source: {nin['any']}/46 | Pix4D {nin['pix']} | ULS-nadir {nin['nad']} | ULS-manual {nin['man']}")
    print(f"  in-bundle by W4c class: {dict(Counter(r[1] for r in inside))}")
    print(f"  OUT-of-bundle (scene periphery, no co-acquired data): {46 - nin['any']}/46")
    print("  in-bundle ids (short | W4c class | pix nad man):")
    for r in sorted(inside):
        print(f"    {r[0]:10} {r[1]:18} p{r[2]} n{r[3]} m{r[4]}")


if __name__ == "__main__":
    main()
