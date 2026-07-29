#!/usr/bin/env python3
"""projection-gate — pixel-alignment verification of the card-v2 projection using ALS as INDEPENDENT
ground truth. Read + small compute; NO reconstruction/retrain. Observe only; PASS/FAIL verdict = 김휘영.
EPSG:25832 geo / 32632 OPF frame. Runs in jointbuildgs-p0-tools:t0 (pyproj+laspy+PIL+numpy; NO cv2/scipy).

Per texture-clear success building, on a near-nadir view, project (a) ALS class-6 building roof points and
(b) the reference LoD2 roof outline (SAME projection path as card v2). Measure the image-space translation
that best aligns each projected silhouette-boundary onto the photo roof edge (per-normal intensity STEP
detector [roof<->background] + least-squares global-translation fit; texture-robust, NOT gradient-max),
convert px->m via the local projection Jacobian, and report ALS-offset vs LoD2-offset (frame centre vs edge).
Interpretation (observe only): ALS also off => pose/coord error (apply empirical world shift, re-measure
residual; note pyproj EPSG:25832->32632 is a NULL transform so any offset is epoch/pose, not datum-formula).
ALS aligned but LoD2 off => reference-mismatch candidate.
"""
import sys, json, csv, math
from pathlib import Path
import numpy as np
import laspy
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from evidence_cards_v2 import (to_cam, clip_near, clip_frustum, distort, proj_ring, roof_mask,
                               gml_building, parse_cam_model, parse_cameras, nadir_of,
                               DATA, IMAGE_DIR, GEOJSON, REPO, ALS_TILES)

FIG = REPO / "docs/figs/projection_gate"
META = REPO / "results/tum_transfer/mob/overseg_lever/projection_gate.json"
BUILDINGS = ["4906972", "4907520", "4959327", "4906985", "4959460", "4907184", "4906966", "4906982"]
SEARCH = 70   # +-px translation search (~0.7m @ 1cm/px)


def to_gray(img_rgb):
    return img_rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114])


def outer_contour(mask, nbins=160):
    """clean outer boundary of a silhouette mask: farthest pixel per angle bin around centroid, with
    radial outward normals. Robust for star-convex single roofs (avoids interior-texture boundaries)."""
    pts = np.argwhere(mask)   # (y,x)
    if len(pts) < 20: return None, None
    c = pts.mean(0)
    ang = np.arctan2(pts[:, 0]-c[0], pts[:, 1]-c[1])
    r = np.hypot(pts[:, 0]-c[0], pts[:, 1]-c[1])
    bins = (((ang+np.pi)/(2*np.pi))*nbins).astype(int) % nbins
    P = []
    for bn in range(nbins):
        sel = np.where(bins == bn)[0]
        if len(sel): P.append(pts[sel[np.argmax(r[sel])]])
    if len(P) < 12: return None, None
    P = np.array(P, float)[:, ::-1]        # -> (x,y)
    cxy = c[::-1]
    N = P - cxy; N = N/np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    return P, N


def normal_step_offset(P, N, gray, search=28, win=6, min_step=7.0, min_pts=8):
    """signed boundary offset along each outward normal via an intensity STEP detector (mean-after minus
    mean-before), averaged over 3 parallel scan lines to suppress roof texture; then LS-fit a global image
    translation (dx,dy) from d_i = (dx,dy)·n_i. Returns the translation that puts the projected boundary on
    the photo roof edge (i.e. the misalignment)."""
    H, W = gray.shape; ds, ns = [], []
    for p, n in zip(P, N):
        tang = np.array([-n[1], n[0]])
        prof = []
        for t in range(-search, search+1):
            q = p + t*n; vals = []
            for s in (-1.5, 0, 1.5):
                qq = q + s*tang; x = int(round(qq[0])); y = int(round(qq[1]))
                if 0 <= x < W and 0 <= y < H: vals.append(gray[y, x])
            prof.append(np.mean(vals) if vals else np.nan)
        prof = np.array(prof)
        if np.isnan(prof).any(): continue
        S = np.array([prof[i+1:i+1+win].mean()-prof[i-win:i].mean() for i in range(win, len(prof)-win)])
        if not len(S): continue
        k = int(np.argmax(np.abs(S)))
        if abs(S[k]) < min_step: continue          # no clear roof/background step here
        ds.append((k+win) - search); ns.append(n)  # + = boundary lies outward of the projected point
    if len(ds) < min_pts: return None
    ns = np.array(ns); ds = np.array(ds, float)
    sol, *_ = np.linalg.lstsq(ns, ds, rcond=None)
    resid = ds - ns @ sol
    return {"dx": float(sol[0]), "dy": float(sol[1]), "n": len(ds), "rms": float(np.sqrt(np.mean(resid**2)))}


def als_silhouette(uv, shape, cell=2):
    """rasterise projected ALS pts into a filled-ish mask (density>=1 in cell) at full-image resolution."""
    H, W = shape
    m = np.zeros((H, W), bool)
    u = np.round(uv[:, 0]).astype(int); v = np.round(uv[:, 1]).astype(int)
    ok = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    u, v = u[ok], v[ok]
    for du in range(-cell, cell+1):
        for dv in range(-cell, cell+1):
            uu = np.clip(u+du, 0, W-1); vv = np.clip(v+dv, 0, H-1)
            m[vv, uu] = True
    return m


def jacobian_px_per_world(ctr3, cam, params, sr):
    """local 2x2 J = d(u,v)/d(E,N) at the roof centre (near-nadir) -> world offset = J^-1 @ image_offset."""
    def pj(p):
        cc = clip_near(to_cam(np.asarray(p)[None], cam, sr))
        return distort(cc, params)[0] if len(cc) else np.array([np.nan, np.nan])
    p0 = pj(ctr3); pe = pj(ctr3+[1, 0, 0]); pn = pj(ctr3+[0, 1, 0])
    J = np.column_stack([pe-p0, pn-p0])   # 2x2: columns = d(uv)/dE, d(uv)/dN
    return J, p0


def load_als_roof(fp_ring, ground_z, roofz):
    """ALS class-6 (building) points inside footprint bbox, above ground+2m (roof-level envelope)."""
    bb = [fp_ring[:, 0].min()-1, fp_ring[:, 1].min()-1, fp_ring[:, 0].max()+1, fp_ring[:, 1].max()+1]
    xs, ys, zs = [], [], []
    for t in ALS_TILES:
        with laspy.open(t) as fh:
            h = fh.header
            if h.x_max < bb[0] or h.x_min > bb[2] or h.y_max < bb[1] or h.y_min > bb[3]: continue
        a = laspy.read(t); cl = np.asarray(a.classification)
        x = np.asarray(a.x); y = np.asarray(a.y); z = np.asarray(a.z)
        m = (cl == 6) & (x >= bb[0]) & (x <= bb[2]) & (y >= bb[1]) & (y <= bb[3]) & (z > ground_z+2.0)
        xs.append(x[m]); ys.append(y[m]); zs.append(z[m])
    if not xs: return np.zeros((0, 3))
    return np.column_stack([np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)])


def select_nadir_views(roof, ring, cams, params, sr, W, H):
    allv = np.vstack(roof); ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(allv[:, 2])])
    cx, cy = params[2], params[3]; out = []
    for c in cams:
        cc = to_cam(allv, c, sr); front = cc[:, 2] > 1.0
        if front.mean() < 0.99: continue
        uv = distort(cc, params)
        if ((uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)).mean() < 0.98: continue
        nad = nadir_of(c, ctr)
        if nad > 25: continue
        rad = float(np.sqrt(((uv[:, 0]-cx)/(0.5*W))**2 + ((uv[:, 1]-cy)/(0.5*H))**2).max())
        out.append((rad, nad, c))
    return out, ctr


def measure(b, cam, roof, ring, ground_z, als_xyz, params, sr, W, H, world_shift=(0.0, 0.0)):
    """project ALS pts + LoD2 outline (optionally with a world E/N shift on inputs), align to photo edge."""
    ds = np.array([world_shift[0], world_shift[1], 0.0])
    ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(np.vstack(roof)[:, 2])]) + ds
    lo_mask = roof_mask([r+ds for r in roof], cam, params, sr, W, H)
    ys, xs = np.where(lo_mask)
    if len(xs) < 20: return None
    pad = 45
    x0 = max(0, xs.min()-pad); y0 = max(0, ys.min()-pad); x1 = min(W, xs.max()+pad); y1 = min(H, ys.max()+pad)
    img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))[y0:y1, x0:x1]
    gray = to_gray(img)
    loP, loN = outer_contour(lo_mask[y0:y1, x0:x1])
    lo_off = normal_step_offset(loP, loN, gray) if loP is not None else None
    als_uv = None; al_off = None; alP = None
    if len(als_xyz):
        cc = clip_near(to_cam(als_xyz+ds, cam, sr))
        if len(cc): cc = clip_frustum(cc, params)
        als_uv = distort(cc, params) if len(cc) else np.zeros((0, 2))
        al_mask = als_silhouette(als_uv, (H, W))
        alP, alN = outer_contour(al_mask[y0:y1, x0:x1])
        al_off = normal_step_offset(alP, alN, gray) if alP is not None else None
    J, _ = jacobian_px_per_world(ctr, cam, params, sr)
    Jinv = np.linalg.inv(J) if abs(np.linalg.det(J)) > 1e-9 else None

    def to_m(off):
        if off is None or Jinv is None: return None
        w = Jinv @ np.array([off["dx"], off["dy"]])
        return {"px": round(math.hypot(off["dx"], off["dy"]), 1), "m": round(float(np.hypot(*w)), 3),
                "dE": round(float(w[0]), 3), "dN": round(float(w[1]), 3), "rms_px": round(off["rms"], 1), "n": off["n"]}
    return {"als": to_m(al_off), "lod2": to_m(lo_off), "crop": (x0, y0, x1, y1), "img": img,
            "als_uv": als_uv, "loP": loP, "alP": alP, "al_off": al_off, "lo_off": lo_off}


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    fp = {}
    for f in json.load(open(GEOJSON))["features"]:
        bb = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]; ring = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        if bb not in fp or len(ring) > len(fp[bb]): fp[bb] = ring
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    blds = only or BUILDINGS
    FIG.mkdir(parents=True, exist_ok=True)
    rows = []
    for b in blds:
        gb = gml_building(b); ring = fp.get(b)
        if not gb or not gb["roof"] or ring is None: print(f"  {b} skip"); continue
        allz = np.vstack(gb["roof"] + gb["wall"])[:, 2]; ground_z = float(allz.min()); roofz = float(np.median(np.vstack(gb["roof"])[:, 2]))
        als = load_als_roof(ring, ground_z, roofz)
        views, ctr = select_nadir_views(gb["roof"], ring, cams, params, sr, W, H)
        if not views: print(f"  {b} no near-nadir in-frame view"); continue
        views.sort(key=lambda t: t[0])
        picks = [("center", views[0])]
        edgev = [v for v in views if v[0] > 0.6]
        if edgev: picks.append(("edge", max(edgev, key=lambda t: t[0])))
        for pos, (rad, nad, cam) in picks:
            M = measure(b, cam, gb["roof"], ring, ground_z, als, params, sr, W, H)
            if M is None: continue
            rows.append({"building_id": f"DEBY_LOD2_{b}", "frame_pos": pos, "frame_r": round(rad, 2), "view_nadir": round(nad, 1),
                         "n_als": len(als), "view": cam.name,
                         "als_off_px": M["als"]["px"] if M["als"] else "", "als_off_m": M["als"]["m"] if M["als"] else "",
                         "lod2_off_px": M["lod2"]["px"] if M["lod2"] else "", "lod2_off_m": M["lod2"]["m"] if M["lod2"] else "",
                         "als_dE": M["als"]["dE"] if M["als"] else "", "als_dN": M["als"]["dN"] if M["als"] else "",
                         "als_rms_px": M["als"]["rms_px"] if M["als"] else "", "lod2_rms_px": M["lod2"]["rms_px"] if M["lod2"] else ""})
            # overlay PNG (center view only, to keep it readable)
            if pos == "center":
                render(b, M, cam.name, nad)
            print(f"  {b} {pos} r={rad:.2f} nad={nad:.0f} ALS={rows[-1]['als_off_m']}m LoD2={rows[-1]['lod2_off_m']}m")
    # write table
    cols = ["building_id", "frame_pos", "frame_r", "view_nadir", "n_als", "als_off_px", "als_off_m",
            "lod2_off_px", "lod2_off_m", "als_dE", "als_dN", "als_rms_px", "lod2_rms_px", "view"]
    out = REPO/"results/tum_transfer/mob/overseg_lever/projection_gate.csv"
    with open(out, "w", newline="") as fo:
        w = csv.DictWriter(fo, fieldnames=cols); w.writeheader(); w.writerows(rows)
    import shutil; shutil.copy(out, REPO/"docs/archive/projection_gate/v1/tables/projection_gate.csv")
    # summary
    def med(key, filt=lambda r: True):
        v = [float(r[key]) for r in rows if r[key] != "" and filt(r)]
        return round(float(np.median(v)), 3) if v else None
    summ = {"als_off_m_median": med("als_off_m"), "lod2_off_m_median": med("lod2_off_m"),
            "als_off_m_center": med("als_off_m", lambda r: r["frame_pos"] == "center"),
            "als_off_m_edge": med("als_off_m", lambda r: r["frame_pos"] == "edge"),
            "als_dE_median": med("als_dE"), "als_dN_median": med("als_dN"), "n": len(rows)}
    json.dump({"rows": rows, "summary": summ}, open(META, "w"), ensure_ascii=False, indent=1)
    print("\n=== SUMMARY ===")
    for k, v in summ.items(): print(f"  {k}: {v}")


def render(b, M, view, nad):
    x0, y0, x1, y1 = M["crop"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 6))
    ax[0].imshow(M["img"])
    if M["als_uv"] is not None and len(M["als_uv"]):
        u = M["als_uv"][:, 0]-x0; v = M["als_uv"][:, 1]-y0
        ok = (u >= 0) & (u < x1-x0) & (v >= 0) & (v < y1-y0)
        ax[0].scatter(u[ok], v[ok], s=1, c="cyan", alpha=0.3)
    if M["loP"] is not None:
        ax[0].plot(np.append(M["loP"][:, 0], M["loP"][0, 0]), np.append(M["loP"][:, 1], M["loP"][0, 1]), "-", c="red", lw=1.3)
    ax[0].set_title(f"{b} nadir={nad:.0f}  cyan=ALS roof pts  red=LoD2 outline (AS-PROJECTED)", fontsize=8); ax[0].axis("off")
    # right: zoom with measured offset arrows (as-projected boundary + step-detected edge shift)
    ax[1].imshow(M["img"])
    if M["loP"] is not None:
        ax[1].plot(np.append(M["loP"][:, 0], M["loP"][0, 0]), np.append(M["loP"][:, 1], M["loP"][0, 1]), "-", c="red", lw=1.0, alpha=0.6)
        lo = M["lo_off"]
        if lo:
            ax[1].plot(np.append(M["loP"][:, 0]+lo["dx"], M["loP"][0, 0]+lo["dx"]),
                       np.append(M["loP"][:, 1]+lo["dy"], M["loP"][0, 1]+lo["dy"]), "-", c="orange", lw=1.3)
    am = M["als"]; lm = M["lod2"]
    ax[1].set_title(f"ALS off={am['m'] if am else '?'}m ({am['px'] if am else '?'}px) | LoD2 off={lm['m'] if lm else '?'}m "
                    f"(orange=LoD2 shifted to photo edge)", fontsize=8); ax[1].axis("off")
    fig.suptitle(f"DEBY_LOD2_{b} projection gate (observe only) — {view}", fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(FIG/f"{b}.png", dpi=110); plt.close(fig)


if __name__ == "__main__":
    main()
