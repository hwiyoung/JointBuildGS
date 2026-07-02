#!/usr/bin/env python3
"""Clean resolution: for ONE building, pick CENTRED views (low radial r; distortion not a confound) across
nadir angles. TOP row = current projection ΔZ=0 (roof outline, no clip_frustum, clip_near only). BOTTOM row
= ΔZ=+geoid. Clean outline only. If ΔZ=0 stays on the roof at every angle -> projection is FINE (no datum
offset; earlier oblique 'street' was an edge/bad view). tools:t0."""
import sys, json, math
import numpy as np
from PIL import Image
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from evidence_cards_v2 import (to_cam, clip_near, distort, gml_building, parse_cam_model, parse_cameras,
                               nadir_of, DATA, IMAGE_DIR, GEOJSON, REPO)
FIG = REPO/"docs/figs/projection_gate2"; N = 48.5


def proj(ring3, cam, params, sr, dz):
    p = np.asarray(ring3, float).copy(); p[:, 2] += dz
    cc = clip_near(to_cam(p, cam, sr))
    return distort(cc, params) if len(cc) >= 2 else np.zeros((0, 2))


def centred_view(roof, ring, cams, params, sr, W, H, want):
    allv = np.vstack(roof); ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(allv[:, 2])])
    cx, cy = params[2], params[3]; best = None
    for c in cams:
        cc = to_cam(allv, c, sr)
        if (cc[:, 2] > 1).mean() < 0.99: continue
        uv = distort(cc, params)
        if ((uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)).mean() < 0.99: continue
        rad = float(np.sqrt(((uv[:, 0]-cx)/(0.5*W))**2 + ((uv[:, 1]-cy)/(0.5*H))**2).max())
        if rad > 0.5: continue
        nad = nadir_of(c, ctr); sc = abs(nad-want)
        if best is None or sc < best[0]: best = (sc, nad, rad, c)
    return best


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
    gb = gml_building(b); ring = fp[b]
    wants = [3, 18, 32, 46]
    fig, ax = plt.subplots(2, len(wants), figsize=(5*len(wants), 11))
    for j, want in enumerate(wants):
        cv = centred_view(gb["roof"], ring, cams, params, sr, W, H, want)
        if not cv:
            for i in range(2): ax[i, j].text(0.5, 0.5, f"no centred ~{want}°", ha="center"); ax[i, j].axis("off")
            continue
        _, nad, rad, cam = cv
        img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))
        for i, (dz, col, lbl) in enumerate([(0.0, "red", "ΔZ=0 (CURRENT)"), (N, "lime", "ΔZ=+geoid")]):
            outs = [proj(r, cam, params, sr, dz) for r in gb["roof"]]; outs = [u for u in outs if len(u) >= 2]
            if not outs: ax[i, j].text(0.5, 0.5, "off-frame", ha="center"); ax[i, j].axis("off"); continue
            allu = np.vstack(outs); pad = 45
            x0 = int(max(0, allu[:, 0].min()-pad)); y0 = int(max(0, allu[:, 1].min()-pad))
            x1 = int(min(W, allu[:, 0].max()+pad)); y1 = int(min(H, allu[:, 1].max()+pad))
            a = ax[i, j]; a.imshow(img[y0:y1, x0:x1]); a.axis("off"); a.set_title(f"nadir={nad:.0f}° r={rad:.2f}  {lbl}", fontsize=9)
            for u in outs:
                q = np.vstack([u, u[:1]]); a.plot(q[:, 0]-x0, q[:, 1]-y0, "-", c=col, lw=1.6)
        print(f"{b} nadir={nad:.0f} r={rad:.2f} view={cam.name}")
    fig.suptitle(f"DEBY_LOD2_{b} CENTRED views — TOP=current ΔZ=0, BOTTOM=ΔZ=+geoid — does the CURRENT (red) stay on the roof as angle grows?", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(FIG/f"zmulti_{b}.png", dpi=115); plt.close(fig)
    print(f"-> zmulti_{b}.png")


if __name__ == "__main__":
    main()
