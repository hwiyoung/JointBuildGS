#!/usr/bin/env python3
"""population-lock-aux v4 [3] — flight/capture-design meta from OPF + COLMAP poses (read-only).
Optical-axis tilt-from-vertical distribution (nadir vs oblique), altitude, passes, sensor; plus a map of
the 69 buildings with v3 n_views_nadir==0 vs all AOI footprints + camera centres. Observe only.
Runs in jointbuildgs-p0-tools:t0 (matplotlib; NO cv2). EPSG:25832 geo / 32632 OPF frame."""
import json, math, csv
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/workspace/JointBuildGS/phases/p0-audit")
REPO = Path("/workspace/JointBuildGS")
DATA = ROOT / "data"
O = DATA / "work/opf/opf"
FIG = REPO / "docs/figs/texture_anchor_check"


def qrot(q):
    w, x, y, z = q
    return np.array([[1-2*y*y-2*z*z, 2*x*y-2*w*z, 2*z*x+2*w*y],
                     [2*x*y+2*w*z, 1-2*x*x-2*z*z, 2*y*z-2*w*x],
                     [2*z*x-2*w*y, 2*y*z+2*w*x, 1-2*x*x-2*y*y]], float)


def main():
    sr = json.load(open(O/"scene_reference_frame.json"))["base_to_canonical"]
    shift = np.array(sr["shift"], float)
    # COLMAP poses -> centres (UTM) + optical-axis tilt from vertical
    tilt, cz, cxy = [], [], []
    expect = True
    for ln in open(DATA/"work/colmap/sparse/0/images.txt"):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if not expect:
            expect = True; continue
        p = s.split()
        q = np.array([float(x) for x in p[1:5]]); t = np.array([float(x) for x in p[5:8]])
        R = qrot(q); C = (-R.T @ t) - shift          # canonical->base = subtract shift (scale 1)
        axis = R.T @ np.array([0, 0, 1.0])           # viewing dir in world
        tilt.append(math.degrees(math.acos(min(1, abs(axis[2]/np.linalg.norm(axis))))))
        cz.append(C[2]); cxy.append(C[:2]); expect = False
    tilt = np.array(tilt); cz = np.array(cz); cxy = np.array(cxy)
    # OPF captures: altitude, passes (time), sensor
    ic = json.load(open(O/"input_cameras.json"))
    haot = np.array([c.get("height_above_takeoff_m") for c in ic["captures"] if c.get("height_above_takeoff_m") is not None])
    times = sorted(c["time"] for c in ic["captures"] if c.get("time"))
    hhmm = Counter(t[11:16] for t in times)
    cal = json.load(open(O/"calibrated_cameras.json"))
    sens = cal.get("sensors", [{}])[0].get("internals", {})
    cs = json.load(open(O/"calibration_settings.json"))
    # tilt bands
    nad = int((tilt <= 20).sum()); mid = int(((tilt > 20) & (tilt <= 45)).sum()); obl = int((tilt > 45).sum())
    print("=== FLIGHT META ===")
    print(f"day 2024-12-17 | captures {len(ic['captures'])} | calibrated cams {len(cal['cameras'])} | COLMAP poses {len(tilt)}")
    print(f"height_above_takeoff_m: median {np.median(haot):.1f} p10 {np.percentile(haot,10):.1f} p90 {np.percentile(haot,90):.1f} (n={len(haot)})")
    print(f"COLMAP centre Z (UTM ellip.): median {np.median(cz):.1f} range {cz.min():.1f}..{cz.max():.1f}")
    print(f"optical-axis tilt-from-vertical: median {np.median(tilt):.1f} | nadir<=20:{nad} 20-45:{mid} >45:{obl}")
    for lo, hi in [(0,10),(10,20),(20,30),(30,45),(45,60),(60,90)]:
        print(f"   tilt {lo:2}-{hi:2} deg: {int(((tilt>=lo)&(tilt<hi)).sum()):4}")
    print(f"XY extent UTM: x {cxy[:,0].min():.0f}..{cxy[:,0].max():.0f}  y {cxy[:,1].min():.0f}..{cxy[:,1].max():.0f}")
    print(f"is_oblique_scene={cs.get('is_oblique_scene')} pipeline={cs.get('pipeline')} matching={cs.get('matching_algorithm')}")
    print(f"sensor internals keys: {list(sens.keys())[:8]}")
    print("passes (HH:MM buckets, count>=5):")
    blocks = {}
    for k in sorted(hhmm):
        if hhmm[k] >= 1:
            blocks.setdefault(k[:2], 0); blocks[k[:2]] += hhmm[k]
    for h in sorted(blocks): print(f"   {h}:xx  {blocks[h]} captures")

    # ---- map: AOI footprints + 69 near-nadir==0 buildings + camera centres ----
    feats = json.load(open(REPO/"results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    v3 = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in csv.DictReader(open(REPO/"docs/evidence/archive/population_aux/v3/tables/population_aux_v3.csv"))}
    nn0 = {b for b, r in v3.items() if r.get("n_views_nadir") not in ("", None) and float(r["n_views_nadir"]) == 0.0}
    print(f"\nbuildings with n_views_nadir==0: {len(nn0)}")
    # spatial correspondence: nearest near-nadir camera (tilt<=20) XY distance, nn0 vs rest
    nadir_xy = cxy[tilt <= 20]
    aoi_c = cxy.mean(0)
    d_near, d_cen, lab = {}, {}, {}
    for f in feats:
        bid = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]; ring = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        ctr = ring[:, :2].mean(0)
        d_near[bid] = float(np.min(np.linalg.norm(nadir_xy - ctr, axis=1)))
        d_cen[bid] = float(np.linalg.norm(ctr - aoi_c)); lab[bid] = bid in nn0
    import statistics as st
    a = [d_near[b] for b in d_near if lab[b]]; o = [d_near[b] for b in d_near if not lab[b]]
    ac = [d_cen[b] for b in d_cen if lab[b]]; oc = [d_cen[b] for b in d_cen if not lab[b]]
    print(f"nearest near-nadir-cam XY dist (m): nn0 median {st.median(a):.1f} vs others {st.median(o):.1f}")
    print(f"dist from AOI camera-centroid (m):  nn0 median {st.median(ac):.1f} vs others {st.median(oc):.1f} (peripheral?)")
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.scatter(cxy[:, 0], cxy[:, 1], s=6, c="#bbbbbb", alpha=0.5, label=f"camera centres ({len(cxy)})", zorder=1)
    n_hi = 0
    for f in feats:
        bid = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]; ring = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        hi = bid in nn0
        ax.plot(ring[:, 0], ring[:, 1], "-", lw=1.4 if hi else 0.5, c="#d62728" if hi else "#4477aa",
                alpha=0.95 if hi else 0.5, zorder=3 if hi else 2)
        if hi:
            ax.fill(ring[:, 0], ring[:, 1], c="#d62728", alpha=0.25, zorder=2); n_hi += 1
    ax.plot([], [], "-", c="#d62728", lw=1.6, label=f"n_views_nadir==0 ({n_hi})")
    ax.plot([], [], "-", c="#4477aa", lw=0.8, label="other AOI footprints")
    ax.set_aspect("equal"); ax.set_xlabel("E (EPSG:25832 m)"); ax.set_ylabel("N (EPSG:25832 m)")
    ax.set_title("Flight camera centres + AOI footprints; red = v3 n_views_nadir==0 (no near-nadir roof view)")
    ax.legend(loc="upper right", fontsize=8)
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(FIG/"flight_nadir0_map.png", dpi=115); print(f"[map] -> {FIG}/flight_nadir0_map.png")


if __name__ == "__main__":
    main()
