#!/usr/bin/env python3
"""Clean before/after of the vertical-datum fix on an OBLIQUE view (per-panel crops, each panel zoomed to
its own projection). Left = ΔZ=0 (orthometric, current — off the roof); right = ΔZ=+geoid (ellipsoidal —
on the roof). Observe only. tools:t0."""
import sys, json, math
import numpy as np, laspy
from PIL import Image
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from evidence_cards_v2 import (to_cam, clip_near, clip_frustum, distort, proj_ring, gml_building,
                               parse_cam_model, parse_cameras, nadir_of, DATA, IMAGE_DIR, GEOJSON, REPO, ALS_TILES)
from ztest import als_roof, pick_view, proj_dz
FIG = REPO/"docs/figs/projection_gate2"; N = 48.5


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    fp = {}
    for f in json.load(open(GEOJSON))["features"]:
        b = f["properties"]["building_id"].replace("DEBY_LOD2_", ""); g = f["geometry"]
        r = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        if b not in fp or len(r) > len(fp[b]): fp[b] = r
    for b in (sys.argv[1:] or ["4906972", "4906985"]):
        gb = gml_building(b); ring = fp[b]; gz = float(np.vstack(gb["roof"]+gb["wall"])[:, 2].min()); als = als_roof(ring, gz)
        pv = pick_view(gb["roof"], ring, cams, params, sr, W, H, 33)   # oblique ~33deg = Z-sensitive, roof still visible
        if not pv: continue
        _, nad, cam = pv
        img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))
        fig, ax = plt.subplots(1, 2, figsize=(15, 7.5))
        for k, (dz, lbl, col) in enumerate([(0, "ΔZ=0  (orthometric — CURRENT projection)", "red"),
                                            (N, f"ΔZ=+{N:.1f}  (ellipsoidal = +geoid — FIX)", "lime")]):
            uv_all = np.vstack([proj_dz(np.asarray(r, float), cam, params, sr, dz) for r in gb["roof"]])
            pad = 55; x0 = int(max(0, uv_all[:, 0].min()-pad)); y0 = int(max(0, uv_all[:, 1].min()-pad))
            x1 = int(min(W, uv_all[:, 0].max()+pad)); y1 = int(min(H, uv_all[:, 1].max()+pad))
            ax[k].imshow(img[y0:y1, x0:x1]); ax[k].axis("off"); ax[k].set_title(lbl, fontsize=10)
            for r in gb["roof"]:
                uv = proj_dz(np.asarray(r, float), cam, params, sr, dz)
                if len(uv) >= 2:
                    q = np.vstack([uv, uv[:1]]); ax[k].plot(q[:, 0]-x0, q[:, 1]-y0, "-", c=col, lw=1.6)
            au = proj_dz(als, cam, params, sr, dz) if len(als) else np.zeros((0, 2))
            if len(au):
                uu = au[:, 0]-x0; vv = au[:, 1]-y0; ok = (uu >= 0) & (uu < x1-x0) & (vv >= 0) & (vv < y1-y0)
                ax[k].scatter(uu[ok], vv[ok], s=0.6, c=col, alpha=0.45)
        fig.suptitle(f"DEBY_LOD2_{b} — oblique view nadir={nad:.0f}°: vertical-datum FIX (red=LoD2 outline, dots=ALS) — {cam.name}", fontsize=9)
        fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(FIG/f"zfix_{b}.png", dpi=120); plt.close(fig)
        print(f"  zfix {b} nadir={nad:.0f}")


if __name__ == "__main__":
    main()
