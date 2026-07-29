#!/usr/bin/env python3
"""population-lock-aux v4 [1] — texture-scale (tau) anchor validation. Read + small new compute; NO
reconstruction/retrain. Observe only; verdict=김휘영. EPSG:25832 (geo) / 32632 (OPF frame).

Why: T9 confirmed 4907182 textureless (near-nadir gradient p10=0.007) but v3 roof_lowtex_frac=0.064 (average).
Validate the ruler on ground-truth anchors BEFORE trusting any threshold.
 Positive anchors = T9 cause=무텍스처 (textureless-confirmed): 4907182,42364609,4907510,4908050,4908166,4908176.
 Negative anchors = both-success, clearly textured (high v3 grad_p10): 4906972,4908023,4907028,4908354,4907520.
For each anchor, on v3's near-nadir-preferred view (deterministic re-selection), dump a PNG (roof polygon
mask + 1.5m-eroded mask overlay) and recompute low-texture 3 ways ON THE SAME VIEW+MASK:
 (i)   v3 current      : Sobel ksize3, thr 0.02   , full mask
 (ii)  v3 + eroded mask: Sobel ksize3, thr 0.02   , mask eroded 1.5 m inward (drop boundary/facade px —
       tests whether the 32632↔25832 sub-m offset pushed the mask off-roof onto textured edges)
 (iii) T11 sharp       : np.gradient, thr 0.02137 , full mask   (isolates metric-definition: Sobel vs npgrad)
Prints anchor x variant table -> observe which variant separates positives from negatives (NO verdict).
Runs in jointbuildgs:dev (cv2).
"""
import sys, math, json
from pathlib import Path
import numpy as np
import cv2
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from population_aux_v3 import (parse_cam_model, parse_cameras, project, gml_building,
                               IMAGE_DIR, DATA, REPO)

V3_THR = 0.02
T11_THR = 0.02137
ERODE_M = 1.5
FIGDIR = REPO / "docs/figs/texture_anchor_check"
OUT = REPO / "results/tum_transfer/mob/overseg_lever/texture_anchor_check.csv"

POS = ["4907182", "42364609", "4907510", "4908050", "4908166", "4908176"]
NEG = ["4906972", "4908023", "4907028", "4908354", "4907520"]


def face_normal(rings):
    best_a, best_n = 0.0, np.array([0, 0, 1.0])
    for r in rings:
        r = np.asarray(r, float)
        if len(r) < 3: continue
        n = np.cross(r[1]-r[0], r[2]-r[0]); a = np.linalg.norm(n)
        if a > best_a: best_a, best_n = a, (n/a if a > 0 else best_n)
    return best_n if best_n[2] >= 0 else -best_n


def select_view(rings, cams, W, H, params, sr):
    """deterministic near-nadir-preferred view (v3 rule): among cams seeing the roof centroid AND >=50%
    of roof vertices in-frame, near-nadir (nadir<=20) -> min nadir else min incidence. Relaxed vertex
    coverage matches v3's per-sample visibility (avoids dropping the near-nadir view on large roofs)."""
    allv = np.vstack([np.asarray(r, float) for r in rings if len(r) >= 3])
    c = allv.mean(0); nrm = face_normal(rings)
    cand = []
    for cam in cams:
        uc, frc = project(c[None], cam, W, H, params, sr)
        if not (frc[0] and 0 <= uc[0, 0] < W and 0 <= uc[0, 1] < H): continue
        uv, fr = project(allv, cam, W, H, params, sr)
        infr = fr & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
        if infr.mean() < 0.5: continue
        vd = cam.center - c; u = vd/np.linalg.norm(vd)
        nad = math.degrees(math.acos(np.clip(u[2], -1, 1)))
        inc = math.degrees(math.acos(abs(np.clip(u @ nrm, -1, 1))))
        cand.append((nad, inc, cam))
    if not cand: return None
    nn = [t for t in cand if t[0] <= 20.0]
    pick = min(nn, key=lambda t: t[0]) if nn else min(cand, key=lambda t: t[1])
    return pick  # (nad, inc, cam)


def build_crop(view_cam, rings, W, H, params, sr):
    img = cv2.imread(str(IMAGE_DIR / view_cam.name), cv2.IMREAD_GRAYSCALE)
    if img is None: return None
    polys, xs, ys = [], [], []
    for r in rings:
        r = np.asarray(r, float)
        if len(r) < 3: continue
        uv, fr = project(r, view_cam, W, H, params, sr)
        if fr.sum() < 3: continue
        polys.append(uv[fr]); xs += uv[fr, 0].tolist(); ys += uv[fr, 1].tolist()
    if not polys: return None
    x0 = int(max(0, min(xs))); y0 = int(max(0, min(ys)))
    x1 = int(min(W, max(xs))); y1 = int(min(H, max(ys)))
    if x1-x0 < 8 or y1-y0 < 8: return None
    crop = img[y0:y1, x0:x1].astype(np.float32)/255.0
    mask = np.zeros(crop.shape, np.uint8)
    for p in polys:
        cv2.fillPoly(mask, [np.round(p - [x0, y0]).astype(np.int32)], 1)
    if mask.sum() < 32: return None
    # px per metre from projecting roof centroid and centroid + 1 m (x & y); bbox fallback if NaN
    all3 = np.vstack([np.asarray(r, float) for r in rings if len(r) >= 3])
    c3 = all3.mean(0)
    p0, _ = project(c3[None], view_cam, W, H, params, sr)
    px, _ = project((c3 + [1, 0, 0])[None], view_cam, W, H, params, sr)
    py, _ = project((c3 + [0, 1, 0])[None], view_cam, W, H, params, sr)
    ppm = np.nanmean([np.linalg.norm(px[0]-p0[0]), np.linalg.norm(py[0]-p0[0])])
    if not np.isfinite(ppm) or ppm <= 0:   # fallback: projected pixel diag / 3D horizontal diag
        diag_px = math.hypot(x1-x0, y1-y0)
        diag_m = math.hypot(all3[:, 0].max()-all3[:, 0].min(), all3[:, 1].max()-all3[:, 1].min())
        ppm = diag_px/diag_m if diag_m > 0 else 1.0
    # v3 downsample if >512
    scale = 1.0
    if max(crop.shape) > 512:
        scale = 512.0/max(crop.shape)
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
    ppm *= scale
    er = max(1, int(round(ERODE_M * ppm)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*er+1, 2*er+1))
    mask_er = cv2.erode(mask, k)
    return dict(crop=crop, mask=mask.astype(bool), mask_er=mask_er.astype(bool),
                ppm=float(ppm), er_px=er, area_px=int(mask.sum()), area_er=int(mask_er.sum()))


def lowtex(crop, mask, mode, thr):
    if mask.sum() < 16: return None
    if mode == "sobel":
        gx = cv2.Sobel(crop, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(crop, cv2.CV_32F, 0, 1, ksize=3)
    else:  # np.gradient (T11)
        gy, gx = np.gradient(crop)
    g = np.sqrt(gx*gx + gy*gy)[mask]
    return dict(lowtex=float(np.mean(g < thr)), gradp10=float(np.percentile(g, 10)))


def overlay_png(bid, tag, crop, mask, mask_er, cap):
    rgb = cv2.cvtColor((np.clip(crop, 0, 1)*255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    for m, col in [(mask, (0, 200, 0)), (mask_er, (0, 0, 230))]:
        cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(rgb, cnts, -1, col, 1)
    sc = max(1, int(360/max(rgb.shape[:2])))
    rgb = cv2.resize(rgb, None, fx=sc, fy=sc, interpolation=cv2.INTER_NEAREST)
    pad = np.zeros((rgb.shape[0]+42, max(rgb.shape[1], 380), 3), np.uint8)
    pad[:rgb.shape[0], :rgb.shape[1]] = rgb
    cv2.putText(pad, f"{bid} [{tag}]", (4, rgb.shape[0]+16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.putText(pad, cap, (4, rgb.shape[0]+34), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 255, 200), 1)
    FIGDIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(FIGDIR / f"{bid}_{tag}.png"), pad)


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    v3 = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in __import__("csv").DictReader(open(REPO/"docs/archive/population_aux/v3/tables/population_aux_v3.csv"))}
    bview = json.load(open(REPO/"results/tum_transfer/mob/overseg_lever/population_aux_v3_bestview.json"))
    bview = {k.replace("DEBY_LOD2_", ""): v for k, v in bview.items()}
    cam_by = {c.name: c for c in cams}
    rows = []
    for tag, bids in [("pos", POS), ("neg", NEG)]:
        for b in bids:
            _, roof, _ = gml_building(b)
            if not roof:
                print(f"[{tag}] {b} NO ROOF"); continue
            # use the EXACT view v3 selected (sidecar); fallback to deterministic re-selection
            vn = bview.get(b)
            if vn and vn in cam_by:
                cam = cam_by[vn]; nad = inc = -1.0
            else:
                sv = select_view(roof, cams, W, H, params, sr)
                if sv is None:
                    print(f"[{tag}] {b} NO VIEW"); continue
                nad, inc, cam = sv
            cr = build_crop(cam, roof, W, H, params, sr)
            if cr is None:
                print(f"[{tag}] {b} NO CROP"); continue
            vi = lowtex(cr["crop"], cr["mask"], "sobel", V3_THR)
            vii = lowtex(cr["crop"], cr["mask_er"], "sobel", V3_THR)
            viii = lowtex(cr["crop"], cr["mask"], "npgrad", T11_THR)
            row = dict(building_id=f"DEBY_LOD2_{b}", anchor=tag, view=cam.name, nadir_deg=round(nad, 1),
                       incidence_deg=round(inc, 1), ppm=round(cr["ppm"], 2), erode_px=cr["er_px"],
                       area_px=cr["area_px"], area_eroded=cr["area_er"],
                       v3_csv_lowtex=v3.get(b, {}).get("roof_lowtex_frac", ""),
                       lt_i_v3=round(vi["lowtex"], 3), lt_ii_eroded=round(vii["lowtex"], 3) if vii else "",
                       lt_iii_t11=round(viii["lowtex"], 3),
                       gradp10_i=round(vi["gradp10"], 4), gradp10_iii=round(viii["gradp10"], 4))
            rows.append(row)
            overlay_png(b, tag, cr["crop"], cr["mask"], cr["mask_er"],
                        f"i={row['lt_i_v3']} ii_er={row['lt_ii_eroded']} iii_t11={row['lt_iii_t11']}")
            print(f"[{tag}] {b:10} view={cam.name[:22]:22} nad={nad:4.1f} i={row['lt_i_v3']:.3f} ii_er={row['lt_ii_eroded']!s:>5} iii_t11={row['lt_iii_t11']:.3f} (csv {row['v3_csv_lowtex']})")
    import csv
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    # separation summary per variant
    print("\n=== separation (mean pos vs mean neg; higher lowtex should mark textureless positives) ===")
    for col in ["lt_i_v3", "lt_ii_eroded", "lt_iii_t11"]:
        pv = [r[col] for r in rows if r["anchor"] == "pos" and r[col] != ""]
        nv = [r[col] for r in rows if r["anchor"] == "neg" and r[col] != ""]
        pmin, nmax = min(pv), max(nv)
        sep = "SEPARATES(pos_min>neg_max)" if pmin > nmax else "overlap"
        print(f"  {col:14} pos[min {pmin:.3f} mean {np.mean(pv):.3f}]  neg[max {nmax:.3f} mean {np.mean(nv):.3f}]  gap={pmin-nmax:+.3f}  {sep}")
    print(f"\n[done] -> {OUT} ; figs -> {FIGDIR}")


if __name__ == "__main__":
    np.random.seed(0)
    main()
