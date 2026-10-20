"""PHD-MAIN-VISCMP-v2 places and cameras of V1-V5 from the region files, the patch stores, GT and the camera geometry only (no result file
is opened). Request 3 fixes the places; this script turns them into patch lists, frames and views:
  V2  B173 주변 LoD2 face 53: the fill task's virtual-component frame (SL/prep/figpos/virtual.json), seen from outside along the outward
      normal (orthographic, 0.05 m pixels); photo = the training camera nearest to the wall centre whose image holds the wall centre.
  V1  R1 LoD2 stepped roof: no R1 LoD2 place of figure 7.1 exists (the distance task drew 7.1 for B173 주변 LoD2 only), so the stage-3
      reinforcement-1 piece is recomputed with its rule (measure8_s3.blob: roof code-11 patches judged conflict by the r12 dry run,
      tau < |GT - prior| <= 4 tau, patch centres joined at 0.36 m, the piece with the most GT points). View = the oblique training view
      (tilt > 20 deg) holding every piece patch centre with >= 80 % visible against the prior render depth and the largest image footprint
      (p0_places.score_views 'oblique'). Zoom = the 0.5 m GT cell with the largest height spread (p95 - p5, >= 20 points) in the piece, 3 m box.
  V3  the photo-figure 4 place (B173 주변 ALS face 1, its section and vertical photo), V5 the photo-figure 5 place (B0 ALS cluster, its
      12 m section and photo): copied from configs/phd/main_photofig_v1/photofig_v1.json.
  V4  R1 LoD2 wall 19 (158 missing patches): the training views holding all of them inside with >= 80 % visible, the one whose angle to
      the outward wall normal is closest to 60 deg; photo = DJI_20241217101317_0011_D (request).
  python vp_places.py -> /vc/prep/places.json   scientific_verdict: null"""
import json

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

import vc_common  # noqa: F401  (sys.path first)
import p0_places as P0
import pf_geo as G
from vc_common import PH, ROOTS, SL, VC, jdump, jl, log, now

PFC = json.loads(open("/repo/configs/phd/main_photofig_v1/photofig_v1.json").read())["places"]


def views_holding(site, prior, P, normal=None):
    V = P0.views(); rows = []
    for v in P0.train_views(site):
        k = P0.vname(v)
        if k is None:
            continue
        u, w, z = V.project(k, P)
        inside = (z > 0) & (u >= 0) & (u < 1024) & (w >= 0) & (w < 741)
        if inside.mean() < 1.0:
            continue
        D = np.load(P0.S0 / "s61/export" / site / prior / "prior" / f"{v}.npy")
        d = D[np.clip(np.floor(w).astype(int), 0, 740), np.clip(np.floor(u).astype(int), 0, 1023)]
        vis = float((np.isfinite(d) & (np.abs(z - d) <= 0.5)).mean())
        if vis < P0.VIS_MIN:
            continue
        C = V.C(k); dirc = C - P.mean(0); dirc /= np.linalg.norm(dirc)
        r = dict(view=v, visible=vis, hull_px2=float(ConvexHull(np.column_stack([u, w])).volume), tilt_deg=round(V.tilt(k), 2),
                 distance_m=round(float(np.linalg.norm(C - P.mean(0))), 1))
        if normal is not None:
            r["view_angle_deg"] = round(float(np.degrees(np.arccos(np.clip(dirc @ normal, -1, 1)))), 2)
        rows.append(r)
    return rows


def v2():
    site, prior = "B173nb_b10", "LoD2"
    fr = jl(SL / "prep/figpos/virtual.json")["place"][site]["frame"]
    c, n, t = (np.asarray(fr[k], np.float64) for k in ("centre", "normal", "t"))
    n_out, flipped = P0.oriented_out(site, int(fr["surf_ext"]), n, c)
    right = np.cross(-n_out, [0.0, 0.0, 1.0]); right /= np.linalg.norm(right)
    # the frame's s runs along t; in the camera the wall is seen from outside: s_cam = (X - c) . right
    corners = np.array([c + a * t + (h - c[2]) * np.array([0, 0, 1.0]) for a in fr["s_range"] for h in fr["z_range"]])
    sc = (corners - c) @ right
    V = P0.views(); best = None; cand = []
    for v in P0.train_views(site):
        k = P0.vname(v)
        if k is None:
            continue
        u, w, z = V.project(k, c[None, :])
        if not (z[0] > 0 and 0 <= u[0] < 1024 and 0 <= w[0] < 741):
            continue
        dist = float(np.linalg.norm(V.C(k) - c))
        cand.append(dict(view=v, distance_m=round(dist, 2), tilt_deg=round(V.tilt(k), 2)))
    cand.sort(key=lambda r: r["distance_m"])
    best = cand[0]["view"] if cand else None
    return dict(site=site, prior=prior, face=int(fr["surf_ext"]), frame=fr, outward_normal=n_out.tolist(), normal_flipped=bool(flipped), right=right.tolist(),
                camera=dict(kind="ortho", centre=c.tolist(), right=right.tolist(), up=[0, 0, 1], toward_viewer=n_out.tolist(),
                            s_range=[float(sc.min()), float(sc.max())], h_range=[float(fr["z_range"][0] - c[2]), float(fr["z_range"][1] - c[2])], pixel=0.05),
                slab=dict(normal_half_m=1.5, pad_m=1.5, rule="the wall-flag counting region of the fill task (figs_fl_walls.cdgs_flags: |n| <= 1.5 m, s and z +- 1.5 m)"),
                photo=dict(view=best, rule="the training camera nearest to the wall centre whose 1024 x 741 image holds the wall centre", candidates=cand[:8]),
                place_rule="fill task unseen_1 frame (SL/prep/figpos/virtual.json)")


def v1():
    site, prior = "R1rep_b10", "LoD2"
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    R = P0.region(site, prior); U = P0.store(site, prior)
    loc = np.load(ROOTS["S2"] / "checks/dry/r12_R1rep_b10_LoD2/model/monitor/locations.npz")
    d, tau = np.abs(R["gt_med"].astype(np.float64)), R["tau"].astype(np.float64)
    m = R["in_eval"].astype(bool) & (R["kind"] == 1) & (R["code_ext_v3"] == 11) & (loc["unit_judgment"] == 0) & (d > tau) & (d <= 4.0 * tau)
    idx = np.nonzero(m)[0]
    C = R["centre"][idx]
    pairs = cKDTree(C).query_pairs(0.36, output_type="ndarray")
    A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(C), len(C)))
    k, lab = connected_components(A, directed=False)
    gt = np.bincount(lab, weights=R["gt_points"][idx].astype(np.float64), minlength=k)
    piece = idx[lab == int(np.argmax(gt))]
    P = P0.patch_corners(U, piece)
    best, sc = P0.score_views(site, prior, P, "oblique")
    # zoom: the GT cell with the largest height spread inside the piece (plan squares of the piece patches)
    xy = U["loc_center"][piece][:, :2]
    box = [float(xy[:, 0].min() - 1), float(xy[:, 1].min() - 1), float(xy[:, 0].max() + 1), float(xy[:, 1].max() + 1)]
    Xg, _, _ = G.gt_points(site, box, margin=0.0)
    own = G.in_squares(Xg, U, piece)
    Xp = Xg[own >= 0]
    # [결과를 보기 전에 바꿈] a cell's own spread caught the roof edge with the ground (10.2 m); the step = the largest jump of the cell
    # median height to an 8-neighbour cell of the piece, 0.5-5 m, cells with >= 10 points
    cell = np.floor(Xp[:, :2] / 0.5).astype(np.int64)
    keys, inv = np.unique(cell, axis=0, return_inverse=True)
    cnt = np.bincount(inv)
    med = np.array([np.median(Xp[inv == i, 2]) if cnt[i] >= 10 else np.nan for i in range(len(keys))])
    lut = {tuple(kk): i for i, kk in enumerate(keys)}
    jump = np.full(len(keys), -1.0)
    for i, kk in enumerate(keys):
        if not np.isfinite(med[i]):
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                jn = lut.get((kk[0] + dx, kk[1] + dy))
                if jn is not None and jn != i and np.isfinite(med[jn]):
                    dz = abs(med[i] - med[jn])
                    if 0.5 <= dz <= 5.0 and dz > jump[i]:
                        jump[i] = dz
    j = int(np.argmax(jump))
    zc = (keys[j] + 0.5) * 0.5
    zz = float(med[j])
    spread = jump
    return dict(site=site, prior=prior, piece_patches=[int(x) for x in piece], n_patches=int(len(piece)), area_m2=round(float(R["area"][piece].sum()), 1),
                gt_points_region=int(R["gt_points"][piece].sum()), same_as_stage3=bool(len(piece) == 2621),
                photo=dict(P0.info_view(best["view"]), score=best) if best else None, photo_search=sc,
                zoom=dict(centre=[float(zc[0]), float(zc[1]), zz], half_m=1.5, step_m=float(spread[j]), gt_points_in_cell=int(cnt[j]), rule='largest 8-neighbour jump of the 0.5 m cell median GT height, 0.5-5 m'),
                place_rule="stage-3 reinforcement-1 piece (measure8_s3.blob rule, recomputed); figure 7.1 has no R1 LoD2 version")


def v4():
    site, prior, ext = "R1rep_b10", "LoD2", 19
    R = P0.region(site, prior); U = P0.store(site, prior)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
    mp = np.nonzero(ev & (se == ext) & np.isin(code, [4, 13]))[0]
    n, _ = P0.wall_normal(site, ext)
    n, flipped = P0.oriented_out(site, ext, n, R["centre"][mp].astype(np.float64).mean(0))
    rows = views_holding(site, prior, P0.patch_corners(U, mp), normal=n)
    rows.sort(key=lambda r: abs(r["view_angle_deg"] - 60.0))
    return dict(site=site, prior=prior, ext=ext, missing=int(len(mp)), outward_normal=n.tolist(), normal_flipped=bool(flipped),
                view=rows[0]["view"] if rows else None, candidates=rows, photo="DJI_20241217101317_0011_D",
                rule="training views holding all missing patches of wall 19 with >= 80 % visible; the view angle closest to 60 deg")


def main():
    out = dict(made=now(), scientific_verdict=None, note="결과 파일을 열지 않고 고름(영역 파일, 패치 저장소, 참값, 카메라 기하)")
    out["V2"] = v2(); log("V2", out["V2"]["photo"]["view"], out["V2"]["camera"]["s_range"], out["V2"]["normal_flipped"])
    out["V1"] = v1(); log("V1", out["V1"]["n_patches"], out["V1"]["same_as_stage3"], (out["V1"]["photo"] or {}).get("view"), out["V1"]["zoom"])
    out["V3"] = dict(PFC["fig4"], source="photofig_v1.json places.fig4"); out["V5"] = dict(PFC["fig5"], source="photofig_v1.json places.fig5")
    out["V4"] = v4(); log("V4", out["V4"]["view"], out["V4"]["candidates"][:3])
    jdump(VC / "prep/places.json", out)


if __name__ == "__main__":
    main()
