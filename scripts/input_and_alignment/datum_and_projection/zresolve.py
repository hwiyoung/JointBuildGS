#!/usr/bin/env python3
"""Resolve the near-nadir vs oblique inconsistency: for ONE building, at a near-nadir AND an oblique view,
show ΔZ=0 vs ΔZ=+geoid (each panel its own crop) + print the roof-centroid pixel shift between them. If a
single ΔZ matches BOTH views -> consistent vertical-datum offset. tools:t0."""
import sys, json, math
import numpy as np, laspy
from PIL import Image
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from scripts.evidence_and_attributes.review_packages.evidence_cards_v2 import (to_cam, clip_near, distort, proj_ring, gml_building,
                               parse_cam_model, parse_cameras, nadir_of, DATA, IMAGE_DIR, GEOJSON, REPO, ALS_TILES)
from scripts.input_and_alignment.datum_and_projection.ztest import als_roof, pick_view, proj_dz
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
    b = sys.argv[1] if len(sys.argv) > 1 else "4906972"
    gb = gml_building(b); ring = fp[b]; gz = float(np.vstack(gb["roof"]+gb["wall"])[:, 2].min()); als = als_roof(ring, gz)
    ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(np.vstack(gb["roof"])[:, 2])])
    fig, ax = plt.subplots(2, 2, figsize=(15, 13))
    for row, want in enumerate([5, 40]):
        pv = pick_view(gb["roof"], ring, cams, params, sr, W, H, want)
        if not pv: continue
        _, nad, cam = pv
        c0 = proj_dz(ctr[None], cam, params, sr, 0.0); cN = proj_dz(ctr[None], cam, params, sr, N)
        shift = math.hypot(*(cN[0]-c0[0])) if len(c0) and len(cN) else float("nan")
        print(f"{b} view nadir={nad:.0f}deg : roof-centroid image shift ΔZ0->ΔZ+{N} = {shift:.0f}px")
        img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))
        for col, (dz, lbl, cc) in enumerate([(0, "ΔZ=0 (current)", "red"), (N, f"ΔZ=+{N} (+geoid)", "lime")]):
            uv_all = np.vstack([proj_dz(np.asarray(r, float), cam, params, sr, dz) for r in gb["roof"]])
            pad = 50; x0 = int(max(0, uv_all[:, 0].min()-pad)); y0 = int(max(0, uv_all[:, 1].min()-pad))
            x1 = int(min(W, uv_all[:, 0].max()+pad)); y1 = int(min(H, uv_all[:, 1].max()+pad))
            a = ax[row, col]; a.imshow(img[y0:y1, x0:x1]); a.axis("off")
            a.set_title(f"nadir={nad:.0f}deg  {lbl}  (Δ0->+geoid shift={shift:.0f}px)", fontsize=9)
            for r in gb["roof"]:
                uv = proj_dz(np.asarray(r, float), cam, params, sr, dz)
                if len(uv) >= 2:
                    q = np.vstack([uv, uv[:1]]); a.plot(q[:, 0]-x0, q[:, 1]-y0, "-", c=cc, lw=1.6)
            au = proj_dz(als, cam, params, sr, dz) if len(als) else np.zeros((0, 2))
            if len(au):
                uu = au[:, 0]-x0; vv = au[:, 1]-y0; ok = (uu >= 0) & (uu < x1-x0) & (vv >= 0) & (vv < y1-y0)
                a.scatter(uu[ok], vv[ok], s=0.6, c=cc, alpha=0.45)
    fig.suptitle(f"DEBY_LOD2_{b} — which ΔZ matches at near-nadir (top) vs oblique (bottom)? red=ΔZ0 green=ΔZ+geoid", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.97]); fig.savefig(FIG/f"zresolve_{b}.png", dpi=115); plt.close(fig)
    print(f"-> zresolve_{b}.png")


if __name__ == "__main__":
    main()
