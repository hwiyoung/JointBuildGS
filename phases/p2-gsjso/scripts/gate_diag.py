#!/usr/bin/env python3
"""HONEST re-check of projection alignment: clean LoD2 roof outline (projected polygon, NOT a silhouette
contour) + ALS class-6 points as sparse dots, zoomed onto the sharpest roof edges. No automated metric —
just show the truth so alignment can be judged by eye. Observe only. tools:t0."""
import sys, json
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from evidence_cards_v2 import (to_cam, clip_near, clip_frustum, distort, proj_ring,
                               gml_building, parse_cam_model, parse_cameras, nadir_of, DATA, IMAGE_DIR, GEOJSON, REPO, ALS_TILES)
import laspy
FIG = REPO/"docs/figs/projection_gate"


def best_nadir_view(roof, ring, cams, params, sr, W, H):
    allv = np.vstack(roof); ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(allv[:, 2])])
    cx, cy = params[2], params[3]; best = None
    for c in cams:
        cc = to_cam(allv, c, sr)
        if (cc[:, 2] > 1).mean() < 0.99: continue
        uv = distort(cc, params)
        if ((uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)).mean() < 0.99: continue
        rad = float(np.sqrt(((uv[:, 0]-cx)/(0.5*W))**2 + ((uv[:, 1]-cy)/(0.5*H))**2).max())
        nad = nadir_of(c, ctr)
        if rad > 0.75: continue
        sc = nad + 40*rad
        if best is None or sc < best[0]: best = (sc, nad, rad, c)
    return best


def als_roof(ring, gz):
    bb = [ring[:, 0].min()-1, ring[:, 1].min()-1, ring[:, 0].max()+1, ring[:, 1].max()+1]
    P = []
    for t in ALS_TILES:
        with laspy.open(t) as fh:
            h = fh.header
            if h.x_max < bb[0] or h.x_min > bb[2] or h.y_max < bb[1] or h.y_min > bb[3]: continue
        a = laspy.read(t); cl = np.asarray(a.classification); x = np.asarray(a.x); y = np.asarray(a.y); z = np.asarray(a.z)
        m = (cl == 6) & (x >= bb[0]) & (x <= bb[2]) & (y >= bb[1]) & (y <= bb[3]) & (z > gz+2)
        P.append(np.column_stack([x[m], y[m], z[m]]))
    return np.vstack(P) if P else np.zeros((0, 3))


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    fp = {}
    for f in json.load(open(GEOJSON))["features"]:
        b = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]; ring = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        if b not in fp or len(ring) > len(fp[b]): fp[b] = ring
    for b in sys.argv[1:]:
        gb = gml_building(b); ring = fp[b]
        gz = float(np.vstack(gb["roof"]+gb["wall"])[:, 2].min())
        bv = best_nadir_view(gb["roof"], ring, cams, params, sr, W, H)
        if not bv: print(f"{b} no view"); continue
        _, nad, rad, cam = bv
        als = als_roof(ring, gz)
        img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))
        # clean LoD2 outlines (project each roof ring)
        rings_uv = [proj_ring(r, cam, params, sr) for r in gb["roof"]]
        rings_uv = [u for u in rings_uv if u is not None]
        allu = np.vstack(rings_uv)
        # ALS uv
        cc = clip_near(to_cam(als, cam, sr)); cc = clip_frustum(cc, params) if len(cc) else cc
        aluv = distort(cc, params) if len(cc) else np.zeros((0, 2))
        x0 = int(max(0, allu[:, 0].min()-40)); y0 = int(max(0, allu[:, 1].min()-40))
        x1 = int(min(W, allu[:, 0].max()+40)); y1 = int(min(H, allu[:, 1].max()+40))
        crop = img[y0:y1, x0:x1]
        fig, ax = plt.subplots(1, 3, figsize=(18, 6.5))
        for k in range(3):
            ax[k].imshow(crop); ax[k].axis("off")
        ax[0].set_title(f"{b} nadir={nad:.0f} r={rad:.2f} — photo only", fontsize=8)
        for u in rings_uv:
            uu = np.vstack([u, u[:1]]); ax[1].plot(uu[:, 0]-x0, uu[:, 1]-y0, "-", c="red", lw=1.0)
        ax[1].set_title("clean LoD2 roof outline (red)", fontsize=8)
        if len(aluv):
            u = aluv[:, 0]-x0; v = aluv[:, 1]-y0; ok = (u >= 0) & (u < x1-x0) & (v >= 0) & (v < y1-y0)
            ax[2].scatter(u[ok], v[ok], s=0.5, c="yellow", alpha=0.5)
        for u in rings_uv:
            uu = np.vstack([u, u[:1]]); ax[2].plot(uu[:, 0]-x0, uu[:, 1]-y0, "-", c="red", lw=0.8)
        ax[2].set_title("+ ALS roof pts (yellow dots) — do they sit on the visible roof?", fontsize=8)
        fig.suptitle(f"DEBY_LOD2_{b} HONEST alignment check — {cam.name}", fontsize=9)
        fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(FIG/f"diag_{b}.png", dpi=125); plt.close(fig)
        print(f"diag {b} nadir={nad:.0f} als={len(als)}")


if __name__ == "__main__":
    main()
