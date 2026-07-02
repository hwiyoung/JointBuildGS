#!/usr/bin/env python3
"""DECISIVE test of the vertical-datum hypothesis (김휘영): camera frame = ellipsoidal (GPS), GML/ALS =
orthometric NN, differing by the geoid N (~48.5m). Project a building's LoD2 roof outline + ALS pts at
ΔZ = 0 vs +N onto an OFF-NADIR view (where a Z error is amplified) and see which aligns with the photo.
Observe only. tools:t0."""
import sys, json, glob, math
from pathlib import Path
import numpy as np
import laspy
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from evidence_cards_v2 import (to_cam, clip_near, clip_frustum, distort, proj_ring, gml_building,
                               parse_cam_model, parse_cameras, nadir_of, DATA, IMAGE_DIR, GEOJSON, REPO, ALS_TILES)
FIG = REPO/"docs/figs/projection_gate2"


def geoid_N():
    try:
        import rasterio, pyproj
        t = pyproj.Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
        lon, lat = t.transform(690950, 5336070)
        with rasterio.open(DATA/"raw/geoid/de_bkg_gcg2016.tif") as ds:
            # geoid grid is usually in lon/lat; sample
            try:
                v = list(ds.sample([(lon, lat)]))[0][0]
            except Exception:
                tt = pyproj.Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
                xx, yy = tt.transform(lon, lat); v = list(ds.sample([(xx, yy)]))[0][0]
        return float(v), f"GCG2016 @({lon:.4f},{lat:.4f})"
    except Exception as e:
        return 48.5, f"empirical (rasterio unavailable: {e})"


def als_roof(ring, gz):
    bb = [ring[:, 0].min()-1, ring[:, 1].min()-1, ring[:, 0].max()+1, ring[:, 1].max()+1]; P = []
    for t in ALS_TILES:
        with laspy.open(t) as fh:
            h = fh.header
            if h.x_max < bb[0] or h.x_min > bb[2] or h.y_max < bb[1] or h.y_min > bb[3]: continue
        a = laspy.read(t); cl = np.asarray(a.classification); x = np.asarray(a.x); y = np.asarray(a.y); z = np.asarray(a.z)
        m = (cl == 6) & (x >= bb[0]) & (x <= bb[2]) & (y >= bb[1]) & (y <= bb[3]) & (z > gz+2)
        P.append(np.column_stack([x[m], y[m], z[m]]))
    return np.vstack(P) if P else np.zeros((0, 3))


def pick_view(roof, ring, cams, params, sr, W, H, want_nadir):
    """view whose nadir angle to the building is closest to want_nadir AND roof fully in frame."""
    allv = np.vstack(roof); ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(allv[:, 2])]); best = None
    for c in cams:
        cc = to_cam(allv, c, sr)
        if (cc[:, 2] > 1).mean() < 0.99: continue
        uv = distort(cc, params)
        if ((uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)).mean() < 0.97: continue
        nad = nadir_of(c, ctr); d = abs(nad-want_nadir)
        if best is None or d < best[0]: best = (d, nad, c)
    return best


def proj_dz(pts3, cam, params, sr, dz):
    p = pts3.copy(); p[:, 2] = p[:, 2] + dz
    cc = clip_near(to_cam(p, cam, sr))
    if len(cc): cc = clip_frustum(cc, params)
    return distort(cc, params) if len(cc) else np.zeros((0, 2))


def dz_sweep_score(roof_rings, cam, params, sr, gmag, gx, gy, x0, y0, dz):
    """orientation-aware edge energy of the dz-shifted LoD2 roof edges vs the photo (higher = better on
    the roof edge). No XY translation — pure dz sweep."""
    Hc, Wc = gmag.shape; tot = 0.0; npts = 0
    for r in roof_rings:
        r = np.asarray(r, float)
        uv = proj_dz(r, cam, params, sr, dz)
        if len(uv) < 2: continue
        for i in range(len(uv)-1):
            a = uv[i]; b = uv[i+1]; L = math.hypot(*(b-a))
            if L < 1e-6: continue
            tv = (b-a)/L; nrm = np.array([-tv[1], tv[0]])
            for s in np.arange(0, L, 3.0):
                p = a+s*tv; xi = int(round(p[0]-x0)); yi = int(round(p[1]-y0))
                if 0 <= xi < Wc and 0 <= yi < Hc:
                    tot += abs(nrm[0]*gx[yi, xi]+nrm[1]*gy[yi, xi]); npts += 1
    return tot/npts if npts else 0.0


def main():
    N, src = geoid_N(); print(f"geoid N = {N:.2f} m ({src})")
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    fp = {}
    for f in json.load(open(GEOJSON))["features"]:
        b = f["properties"]["building_id"].replace("DEBY_LOD2_", ""); g = f["geometry"]
        r = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        if b not in fp or len(r) > len(fp[b]): fp[b] = r
    blds = (sys.argv[1:] or ["4906972", "4907520", "4959327", "4906985", "4959460", "4907184", "4906966", "4906982"])
    # ---- quantitative ΔZ sweep (moderate-oblique view; find best-aligning ΔZ per building) ----
    print("\n=== ΔZ sweep (best-aligning vertical shift per building; expect ~geoid N if datum offset real) ===")
    bestdz = []
    for b in blds:
        gb = gml_building(b); ring = fp[b]
        pv = pick_view(gb["roof"], ring, cams, params, sr, W, H, 22)   # moderate oblique = Z-sensitive + roof visible
        if not pv: continue
        _, nad, cam = pv
        u0 = np.vstack([proj_dz(np.asarray(r, float), cam, params, sr, dz) for r in gb["roof"] for dz in (0, N)])
        pad = 70; x0 = int(max(0, u0[:, 0].min()-pad)); y0 = int(max(0, u0[:, 1].min()-pad))
        x1 = int(min(W, u0[:, 0].max()+pad)); y1 = int(min(H, u0[:, 1].max()+pad))
        img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))[y0:y1, x0:x1]
        g = img.astype(np.float32) @ np.array([0.299, 0.587, 0.114]); gyv, gxv = np.gradient(g); gm = np.sqrt(gxv*gxv+gyv*gyv)
        dzr = np.arange(-15, 66, 3.0)
        sc = [dz_sweep_score(gb["roof"], cam, params, sr, gm, gxv, gyv, x0, y0, dz) for dz in dzr]
        bd = float(dzr[int(np.argmax(sc))]); bestdz.append(bd)
        print(f"  {b} nadir={nad:.0f}  best ΔZ = {bd:+.0f} m  (score {max(sc):.1f})")
    if bestdz:
        print(f"  --> median best ΔZ = {np.median(bestdz):+.1f} m   (geoid N = {N:.1f} m)")
    # ---- visual for first building (near-nadir + oblique) ----
    for b in blds[:2]:
        gb = gml_building(b); ring = fp[b]; gz = float(np.vstack(gb["roof"]+gb["wall"])[:, 2].min())
        als = als_roof(ring, gz)
        for want, tag in [(45, "oblique45"), (5, "nearnadir")]:
            pv = pick_view(gb["roof"], ring, cams, params, sr, W, H, want)
            if not pv: continue
            _, nad, cam = pv
            img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))
            # crop around dz=0 projection
            u0 = np.vstack([proj_ring(r, cam, params, sr) for r in gb["roof"] if proj_ring(r, cam, params, sr) is not None])
            uN = np.vstack([proj_dz(np.asarray(r, float), cam, params, sr, N) for r in gb["roof"]])
            allu = np.vstack([u0, uN]); pad = 60
            x0 = int(max(0, allu[:, 0].min()-pad)); y0 = int(max(0, allu[:, 1].min()-pad))
            x1 = int(min(W, allu[:, 0].max()+pad)); y1 = int(min(H, allu[:, 1].max()+pad))
            crop = img[y0:y1, x0:x1]
            fig, ax = plt.subplots(1, 3, figsize=(19, 6.6))
            dzs = [(0, "ΔZ=0 (orthometric, current)", "red"), (N/2, f"ΔZ=+{N/2:.0f}", "yellow"), (N, f"ΔZ=+{N:.1f} (ellipsoidal=+geoid)", "lime")]
            for k, (dz, lbl, col) in enumerate(dzs):
                ax[k].imshow(crop); ax[k].axis("off"); ax[k].set_title(f"{lbl}", fontsize=9)
                for r in gb["roof"]:
                    uv = proj_dz(np.asarray(r, float), cam, params, sr, dz)
                    if len(uv) >= 2:
                        q = np.vstack([uv, uv[:1]]); ax[k].plot(q[:, 0]-x0, q[:, 1]-y0, "-", c=col, lw=1.3)
                au = proj_dz(als, cam, params, sr, dz) if len(als) else np.zeros((0, 2))
                if len(au):
                    uu = au[:, 0]-x0; vv = au[:, 1]-y0; ok = (uu >= 0) & (uu < x1-x0) & (vv >= 0) & (vv < y1-y0)
                    ax[k].scatter(uu[ok], vv[ok], s=0.5, c=col, alpha=0.4)
            fig.suptitle(f"DEBY_LOD2_{b} vertical-datum test — {tag} view nadir={nad:.0f}° — which ΔZ lands LoD2(line)+ALS(dots) on the roof? ({cam.name})", fontsize=9)
            fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(FIG/f"ztest_{b}_{tag}.png", dpi=115); plt.close(fig)
            print(f"  {b} {tag} nadir={nad:.0f} -> ztest_{b}_{tag}.png")


if __name__ == "__main__":
    main()
