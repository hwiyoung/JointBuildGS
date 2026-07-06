#!/usr/bin/env python3
"""P2 impl ② — per-building seeding depth bands (GS-local frame).

Condition A (honest-range): band = [ground_local - 1, ground_local + 30], where ground_local comes
  from TUM2TWIN/Bayern LiDAR GROUND points inside the footprint (class 2; fallback lowest-5% median).
  NO reference roof height is used for A.
Condition B (oracle-ceiling, comparison only): band = [roof_local - 1, roof_local + 1], roof from
  ref_roof_heights.csv (reference; B is the ceiling, never fed to A).

LiDAR datum: determined by comparing in-footprint ground z to reference HoeheGrund (~514 m ortho).
  orthometric  -> ground_local = H_ortho + GEOID - 604   (E5 GEOID=45.7 -> H_ortho - 558.3)
  ellipsoidal  -> ground_local = z_ellip - 604
Records the determination. Runs in P0 tools container (laspy + numpy + matplotlib). EPSG:25832.
"""
import argparse, csv, glob, json
from pathlib import Path
import numpy as np
import laspy
from matplotlib.path import Path as MplPath

RECOVERY = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"]
GROUND_CLASS = 2


def ring_of(geo, bid):
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    co = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    return np.asarray(co)[:, :2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--als-glob", required=True)
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--ref-roof", required=True, help="ref_roof_heights.csv (building_id,h_ground,h_roof) ortho")
    ap.add_argument("--shift-z", type=float, default=604.0)
    ap.add_argument("--geoid", type=float, default=45.7, help="geoid undulation (ortho->ellipsoidal), E5 canonical")
    ap.add_argument("--ground-buffer", type=float, default=8.0)
    ap.add_argument("--hmax", type=float, default=30.0)
    ap.add_argument("--outdir", required=True)
    A = ap.parse_args()
    Path(A.outdir).mkdir(parents=True, exist_ok=True)

    geo = json.load(open(A.geojson))["features"]
    refh = {r["building_id"]: r for r in csv.DictReader(open(A.ref_roof))}

    # load ALS (with classification) clipped to union of recovery footprints+buffer
    rings = {b: ring_of(geo, f"DEBY_LOD2_{b}") for b in RECOVERY}
    gx0 = min(r[:, 0].min() for r in rings.values()) - 30; gx1 = max(r[:, 0].max() for r in rings.values()) + 30
    gy0 = min(r[:, 1].min() for r in rings.values()) - 30; gy1 = max(r[:, 1].max() for r in rings.values()) + 30
    XYZ, CLS = [], []
    for laz in glob.glob(A.als_glob):
        las = laspy.read(laz)
        X, Y, Z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
        cl = np.asarray(las.classification)
        m = (X >= gx0) & (X <= gx1) & (Y >= gy0) & (Y <= gy1)
        if m.any():
            XYZ.append(np.column_stack([X[m], Y[m], Z[m]])); CLS.append(cl[m])
    P = np.concatenate(XYZ); C = np.concatenate(CLS)
    has_ground_class = int((C == GROUND_CLASS).sum()) > 0
    print(f"[als] {len(P)} pts in AOI; ground-class(2) present={has_ground_class} "
          f"(n_ground={int((C==GROUND_CLASS).sum())})")

    rows = []; datum_votes = []
    for b in RECOVERY:
        bid = f"DEBY_LOD2_{b}"; r = rings[b]
        fp = MplPath(r)
        x0, y0, x1, y1 = r[:, 0].min() - A.ground_buffer, r[:, 1].min() - A.ground_buffer, \
            r[:, 0].max() + A.ground_buffer, r[:, 1].max() + A.ground_buffer
        box = (P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1)
        Pb, Cb = P[box], C[box]
        # ground estimate: ground-class median (footprint+buffer); fallback lowest-5% median
        gmask = (Cb == GROUND_CLASS)
        if gmask.sum() >= 10:
            ground_ortho = float(np.median(Pb[gmask, 2])); src = "ground-class"
        else:
            infp = fp.contains_points(Pb[:, :2]); z = Pb[infp, 2] if infp.any() else Pb[:, 2]
            lo = np.percentile(z, 5); ground_ortho = float(np.median(z[z <= lo])); src = "lowest5pct"
        ref_hg = float(refh[bid]["h_ground"])
        # datum: ground close to ref HoeheGrund(ortho ~514) => ortho; ~+45.7 => ellipsoidal
        d_ortho = abs(ground_ortho - ref_hg); d_ellip = abs(ground_ortho - (ref_hg + A.geoid))
        datum = "ortho" if d_ortho <= d_ellip else "ellipsoidal"
        datum_votes.append(datum)
        ground_local = (ground_ortho + A.geoid - A.shift_z) if datum == "ortho" else (ground_ortho - A.shift_z)
        roof_ortho = float(refh[bid]["h_roof"])
        roof_local = (roof_ortho + A.geoid - A.shift_z) if datum == "ortho" else (roof_ortho - A.shift_z)
        band_A = [round(ground_local - 1.0, 3), round(ground_local + A.hmax, 3)]
        band_B = [round(roof_local - 1.0, 3), round(roof_local + 1.0, 3)]
        rows.append(dict(bid=bid, ground_src=src, ground_ortho=round(ground_ortho, 2),
                         ref_HoeheGrund=ref_hg, datum=datum, ground_local=round(ground_local, 2),
                         roof_ortho=round(roof_ortho, 2), roof_local=round(roof_local, 2),
                         band_A=band_A, band_B=band_B))
        print(f"  {bid}: ground={ground_ortho:.2f}({src}) refHG={ref_hg} datum={datum} "
              f"-> ground_local={ground_local:.1f} roof_local={roof_local:.1f} | A={band_A} B={band_B}")

    datum_final = max(set(datum_votes), key=datum_votes.count)
    bands_A = {r["bid"]: r["band_A"] for r in rows}
    bands_B = {r["bid"]: r["band_B"] for r in rows}
    json.dump(bands_A, open(f"{A.outdir}/seed_bands_range.json", "w"), indent=2)
    json.dump(bands_B, open(f"{A.outdir}/seed_bands_oracle.json", "w"), indent=2)
    json.dump(dict(datum=datum_final, geoid=A.geoid, shift_z=A.shift_z, has_ground_class=has_ground_class,
                   hmax=A.hmax, rows=rows), open(f"{A.outdir}/seed_bands_meta.json", "w"), indent=2)
    print(f"\n[datum] LiDAR determined = {datum_final} (geoid={A.geoid}, shift_z={A.shift_z})")
    print(f"[done] -> {A.outdir}/seed_bands_{{range,oracle}}.json + seed_bands_meta.json")


if __name__ == "__main__":
    main()
