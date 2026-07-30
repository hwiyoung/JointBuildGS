#!/usr/bin/env python3
"""projection-gate v2 (rigorous redo) — honest pixel-alignment check that CAN detect large offsets and
reports confidence. Method: project (a) clean LoD2 roof edges (outer boundary + internal hips) and (b) ALS
class-6 silhouette boundary; align each to the photo by a WIDE (+-100px) translation search maximising
ORIENTATION-AWARE edge energy (sum of |image_gradient · boundary_normal| — strong edges PERPENDICULAR to
the projected edge; suppresses periodic tile texture). Report offset(px,m) + confidence(peak z-score).
Split: als_off = projection error (ALS is model-independent truth); lod2_off = projection+model (operational
for the lowtex mask). Observe only; verdict = 김휘영. tools:t0 (numpy+laspy+PIL; NO cv2/scipy)."""
import sys, json, csv, math
from pathlib import Path
import numpy as np
import laspy
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from scripts.evidence_and_attributes.review_packages.evidence_cards_v2 import (to_cam, clip_near, clip_frustum, distort, proj_ring, gml_building,
                               parse_cam_model, parse_cameras, nadir_of, DATA, IMAGE_DIR, GEOJSON, REPO, ALS_TILES)
FIG = REPO/"docs/figs/projection_gate2"
BUILDINGS = ["4906972", "4907520", "4959327", "4906985", "4959460", "4907184", "4906966", "4906982"]
SEARCH = 100


def gate_view(roof, ring, cams, params, sr, W, H):
    allv = np.vstack(roof); ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(allv[:, 2])]); best = None
    for c in cams:
        cc = to_cam(allv, c, sr)
        if (cc[:, 2] > 1).mean() < 0.99: continue
        uv = distort(cc, params)
        if ((uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)).mean() < 0.98: continue
        nad = nadir_of(c, ctr)
        if best is None or nad < best[0]: best = (nad, c)
    return best


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


def densify_edges(rings_uv, spacing=3.0):
    pts, tan = [], []
    for r in rings_uv:
        r = np.asarray(r, float)
        for i in range(len(r)):
            a = r[i]; b = r[(i+1) % len(r)]; L = math.hypot(*(b-a))
            if L < 1e-6: continue
            tv = (b-a)/L
            for s in np.arange(0, L, spacing):
                pts.append(a+s*tv); tan.append(tv)
    return np.array(pts), np.array(tan)


def silhouette_boundary(uv, W, H, cell=2):
    m = np.zeros((H, W), bool)
    u = np.round(uv[:, 0]).astype(int); v = np.round(uv[:, 1]).astype(int)
    ok = (u >= 0) & (u < W) & (v >= 0) & (v < H); u, v = u[ok], v[ok]
    for du in range(-cell, cell+1):
        for dv in range(-cell, cell+1):
            m[np.clip(v+dv, 0, H-1), np.clip(u+du, 0, W-1)] = True
    pts = np.argwhere(m)
    if len(pts) < 30: return None, None
    c = pts.mean(0); ang = np.arctan2(pts[:, 0]-c[0], pts[:, 1]-c[1]); rr = np.hypot(pts[:, 0]-c[0], pts[:, 1]-c[1])
    nb = 160; bins = (((ang+np.pi)/(2*np.pi))*nb).astype(int) % nb; B = []
    for bn in range(nb):
        sel = np.where(bins == bn)[0]
        if len(sel): B.append(pts[sel[np.argmax(rr[sel])]])
    B = np.array(B, float)[:, ::-1]      # (x,y) ordered
    tan = np.gradient(B, axis=0); tan = tan/np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    return B, tan


def orient_align(pts, tan, gx, gy, gmag, x0, y0, search=SEARCH, step=2):
    if pts is None or len(pts) < 12: return None
    normal = np.column_stack([-tan[:, 1], tan[:, 0]])
    Hc, Wc = gmag.shape; px = pts[:, 0]-x0; py = pts[:, 1]-y0
    best = (0, 0, -1.0); scores = []
    for dy in range(-search, search+1, step):
        vy = np.round(py+dy).astype(int)
        for dx in range(-search, search+1, step):
            vx = np.round(px+dx).astype(int)
            ok = (vx >= 0) & (vx < Wc) & (vy >= 0) & (vy < Hc)
            if ok.sum() < len(pts)*0.5: continue
            al = np.abs(normal[ok, 0]*gx[vy[ok], vx[ok]] + normal[ok, 1]*gy[vy[ok], vx[ok]])
            s = float(al.mean()); scores.append(s)
            if s > best[2]: best = (dx, dy, s)
    if not scores: return None
    sc = np.array(scores)
    return {"dx": best[0], "dy": best[1], "peak": best[2], "z": float((best[2]-sc.mean())/(sc.std()+1e-9))}


def jac(ctr3, cam, params, sr):
    def pj(p):
        cc = clip_near(to_cam(np.asarray(p)[None], cam, sr)); return distort(cc, params)[0] if len(cc) else np.array([np.nan, np.nan])
    p0 = pj(ctr3); return np.column_stack([pj(ctr3+[1, 0, 0])-p0, pj(ctr3+[0, 1, 0])-p0])


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    fp = {}
    for f in json.load(open(GEOJSON))["features"]:
        b = f["properties"]["building_id"].replace("DEBY_LOD2_", ""); g = f["geometry"]
        r = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        if b not in fp or len(r) > len(fp[b]): fp[b] = r
    blds = [a for a in sys.argv[1:] if not a.startswith("-")] or BUILDINGS
    FIG.mkdir(parents=True, exist_ok=True); rows = []
    for b in blds:
        gb = gml_building(b); ring = fp[b]; gz = float(np.vstack(gb["roof"]+gb["wall"])[:, 2].min())
        gv = gate_view(gb["roof"], ring, cams, params, sr, W, H)
        if not gv: print(f"{b} no view"); continue
        nad, cam = gv
        ctr3 = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(np.vstack(gb["roof"])[:, 2])])
        rings_uv = [proj_ring(r, cam, params, sr) for r in gb["roof"]]; rings_uv = [u for u in rings_uv if u is not None]
        allu = np.vstack(rings_uv)
        als = als_roof(ring, gz)
        cc = clip_near(to_cam(als, cam, sr)); cc = clip_frustum(cc, params) if len(cc) else cc; aluv = distort(cc, params) if len(cc) else np.zeros((0, 2))
        # crop
        pad = SEARCH+40
        x0 = int(max(0, allu[:, 0].min()-pad)); y0 = int(max(0, allu[:, 1].min()-pad))
        x1 = int(min(W, allu[:, 0].max()+pad)); y1 = int(min(H, allu[:, 1].max()+pad))
        img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))[y0:y1, x0:x1]
        g = img.astype(np.float32) @ np.array([0.299, 0.587, 0.114]); gy, gx = np.gradient(g); gmag = np.sqrt(gx*gx+gy*gy)
        lp, lt = densify_edges(rings_uv)                       # LoD2 outer+hips
        ap, at = silhouette_boundary(aluv, W, H)               # ALS outer silhouette
        lo = orient_align(lp, lt, gx, gy, gmag, x0, y0)
        al = orient_align(ap, at, gx, gy, gmag, x0, y0) if ap is not None else None
        J = jac(ctr3, cam, params, sr); Ji = np.linalg.inv(J) if abs(np.linalg.det(J)) > 1e-9 else None

        def tom(o):
            if o is None or Ji is None: return None
            w = Ji @ np.array([o["dx"], o["dy"]])
            return {"px": round(math.hypot(o["dx"], o["dy"]), 1), "m": round(float(np.hypot(*w)), 3), "z": round(o["z"], 1)}
        LM, AM = tom(lo), tom(al)
        rows.append({"building_id": f"DEBY_LOD2_{b}", "view_nadir": round(nad, 1), "n_als": len(als),
                     "lod2_off_px": LM["px"] if LM else "", "lod2_off_m": LM["m"] if LM else "", "lod2_conf_z": LM["z"] if LM else "",
                     "als_off_px": AM["px"] if AM else "", "als_off_m": AM["m"] if AM else "", "als_conf_z": AM["z"] if AM else "",
                     "view": cam.name})
        render(b, img, x0, y0, rings_uv, aluv, lo, al, LM, AM, nad, cam.name)
        print(f"  {b} nad={nad:.0f} LoD2={LM['m'] if LM else '?'}m(z{LM['z'] if LM else '?'}) ALS={AM['m'] if AM else '?'}m(z{AM['z'] if AM else '?'})")
    cols = ["building_id", "view_nadir", "n_als", "lod2_off_px", "lod2_off_m", "lod2_conf_z", "als_off_px", "als_off_m", "als_conf_z", "view"]
    out = REPO/"results/tum_transfer/mob/overseg_lever/projection_gate2.csv"
    with open(out, "w", newline="") as fo:
        w = csv.DictWriter(fo, fieldnames=cols); w.writeheader(); w.writerows(rows)
    import shutil; shutil.copy(out, REPO/"docs/projection_gate2.csv")

    def med(k):
        v = [float(r[k]) for r in rows if r[k] != ""]; return round(float(np.median(v)), 3) if v else None
    print("\n=== SUMMARY ===  LoD2 med", med("lod2_off_m"), "m | ALS med", med("als_off_m"), "m | LoD2 conf-z med", med("lod2_conf_z"), "| ALS conf-z med", med("als_conf_z"))


def render(b, img, x0, y0, rings_uv, aluv, lo, al, LM, AM, nad, view):
    fig, ax = plt.subplots(1, 3, figsize=(19, 6.6))
    for k in range(3): ax[k].imshow(img); ax[k].axis("off")
    ax[0].set_title(f"{b} nadir={nad:.0f} — photo", fontsize=8)
    for u in rings_uv:
        q = np.vstack([u, u[:1]]); ax[1].plot(q[:, 0]-x0, q[:, 1]-y0, "-", c="lime", lw=1.0)
    if len(aluv):
        uu = aluv[:, 0]-x0; vv = aluv[:, 1]-y0; ok = (uu >= 0) & (uu < img.shape[1]) & (vv >= 0) & (vv < img.shape[0])
        ax[1].scatter(uu[ok], vv[ok], s=0.6, c="red", alpha=0.5)
    ax[1].set_title("AS-PROJECTED: green=LoD2 edges(outer+hips) red=ALS pts", fontsize=8)
    for u in rings_uv:
        q = np.vstack([u, u[:1]]); ax[2].plot(q[:, 0]-x0, q[:, 1]-y0, "-", c="lime", lw=0.6, alpha=0.4)
        if lo: ax[2].plot(q[:, 0]-x0+lo["dx"], q[:, 1]-y0+lo["dy"], "-", c="orange", lw=1.1)
    ax[2].set_title(f"orange=LoD2 shifted to best photo-edge align | LoD2 off={LM['m'] if LM else '?'}m z={LM['z'] if LM else '?'} "
                    f"| ALS off={AM['m'] if AM else '?'}m z={AM['z'] if AM else '?'}", fontsize=7.5)
    fig.suptitle(f"DEBY_LOD2_{b} projection gate v2 (wide-search orientation align; z=peak confidence) — {view}", fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(FIG/f"{b}.png", dpi=115); plt.close(fig)


if __name__ == "__main__":
    main()
