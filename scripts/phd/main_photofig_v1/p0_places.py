"""PHD-MAIN-PHOTOFIG-v1 prep: the places, photos and sections of every figure, chosen from the region files, the patch store, the GT
and the camera geometry ONLY (request 2.9: no result file is opened here). (jointbuildgs:dev, CPU)

  python p0_places.py   -> /pf/prep/places.json (copied into configs/phd/main_photofig_v1/photofig_v1.json before the first figure)

Photo rule (request 4.9): training views of the site (S0/fork_inputs/s61/<site>/split.json 'train'); a view qualifies when every place
point projects inside the image in front of the camera and >= 80 % of them are visible against the prior's render depth of that view
(|camera z - prior depth| <= 0.5 m; S0/s61/export/<site>/<prior>/prior/<view>.npy, an input of training). Roofs: vertical views (optical
axis within 20 deg of the vertical) first; the qualifying view with the largest convex-hull area of the projected place is chosen.
Walls: the qualifying view with the smallest angle between the wall's outward normal and the direction to the camera.
Sections (request 4.10): 0.5 m bands; roofs = vertical section along the long axis (PCA of the place in plan) through the centroid;
walls = horizontal band at the middle height of the missing patches, along the wall; length = the place + 2 m on both sides.
scientific_verdict: null"""
import json
import sys

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
from common import Views  # noqa: E402  (the 937-image model, native 1024 x 741 grid; scripts/phd/main_stage0_v1/common.py:154-200)

from pf_common import DR, FT, PF, S0, S1, SL, in_rect, jdump, jl, log, now  # noqa: E402

VW = None
VIS_MIN = 0.8   # share of place points visible against the prior render depth (0.9 left no vertical view for figure 1: best 0.893)


def views():
    global VW
    if VW is None:
        VW = Views()
    return VW


def region(site, prior):
    return np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")


def store(site, prior):
    return np.load(S0 / "s61/box" / site / prior / "units.npz")


def patch_corners(U, idx):
    """the patch centres (the place points used for the inside and visibility tests; the hull uses them as well)."""
    return U["loc_center"][idx].astype(np.float64)


def patch_corners4(U, idx):
    h = 0.5 * float(U["sp"])
    c, t1, t2 = U["loc_center"][idx], U["loc_t1"][idx], U["loc_t2"][idx]
    return np.concatenate([c, c - h * t1 - h * t2, c + h * t1 - h * t2, c + h * t1 + h * t2, c - h * t1 + h * t2])


def train_views(site):
    return jl(S0 / "fork_inputs/s61" / site / "split.json")["train"]


def vname(n):
    """the images.bin key of a split stem (the 937-image model may store 'name.JPG')."""
    V = views()
    if n in V.ims:
        return n
    for ext in (".JPG", ".jpg"):
        if n + ext in V.ims:
            return n + ext
    return None


def score_views(site, prior, P, mode, normal=None):
    """per training view: inside share, visible share, hull area (px^2), tilt; the chosen view by the photo rule."""
    V = views()
    rows = []
    for n in train_views(site):
        k = vname(n)
        if k is None:
            continue
        u, v, z = V.project(k, P)
        inside = (z > 0) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741)
        tilt = V.tilt(k)
        rec = dict(view=n, tilt_deg=round(tilt, 2), inside=float(inside.mean()))
        if inside.mean() >= (0.05 if mode == "oblique" else 0.5):
            D = np.load(S0 / "s61/export" / site / prior / "prior" / f"{n}.npy")
            ui, vi, zi = u[inside], v[inside], z[inside]
            iu = np.clip(np.floor(ui).astype(int), 0, 1023); iv = np.clip(np.floor(vi).astype(int), 0, 740)
            d = D[iv, iu]
            vis = np.isfinite(d) & (np.abs(zi - d) <= 0.5)
            rec["visible"] = float(vis.mean())
            try:
                rec["hull_px2"] = float(ConvexHull(np.column_stack([ui, vi])).volume)
            except Exception:  # noqa: BLE001
                rec["hull_px2"] = 0.0
            if normal is not None:
                C = V.C(k)
                dirc = C - P.mean(0); dirc /= np.linalg.norm(dirc)
                rec["view_angle_deg"] = round(float(np.degrees(np.arccos(np.clip(dirc @ normal, -1, 1)))), 2)
        rows.append(rec)
    def pick(pool):
        full = [r for r in pool if r["inside"] == 1.0 and r.get("visible", 0) >= VIS_MIN]
        if full:
            return full, "all place points inside, >= 80 % visible"
        vis_ok = [r for r in pool if r.get("visible", 0) >= VIS_MIN]
        top = max((r["inside"] for r in vis_ok), default=0.0)
        return [r for r in vis_ok if r["inside"] >= top - 1e-9], f"no view holds the whole place; the views with the largest inside share ({top:.3f}), >= 80 % of those visible"
    if mode == "vertical":
        pool = [r for r in rows if r["tilt_deg"] <= 20.0]
        ok, branch = pick(pool)
        if not ok:
            ok, branch = pick(rows); branch = "no vertical view qualifies; all views: " + branch
        cand = ok
        best = max(cand, key=lambda r: r["hull_px2"]) if cand else None
    elif mode == "oblique":
        ok, branch = pick([r for r in rows if r["tilt_deg"] > 20.0])
        cand = ok
        best = max(cand, key=lambda r: r["hull_px2"]) if cand else None
        if best is None:   # [결과를 보기 전에 바꿈] no oblique view sees >= 80 % of the place: the oblique view that sees the most place points
            pool = [r for r in rows if r["tilt_deg"] > 20.0 and "visible" in r]
            for r in pool:
                r["visible_points"] = r["visible"] * r["inside"]
            cand = pool
            best = max(pool, key=lambda r: (r["visible_points"], r["hull_px2"])) if pool else None
            branch = "no oblique view sees >= 80 % of the place; the oblique view (tilt > 20 deg) with the largest share of place points inside and visible"
    else:  # wall
        ok, branch = pick([r for r in rows if "view_angle_deg" in r])
        cand = ok
        best = min(cand, key=lambda r: (r["view_angle_deg"], -r["hull_px2"])) if cand else None
    vstats = sorted([r.get("visible", -1) for r in rows if r["inside"] == 1.0], reverse=True)[:5]
    return best, dict(n_views=len(rows), n_all_inside=sum(1 for r in rows if r["inside"] == 1.0), n_qualifying=len(ok), branch=branch,
                      n_candidates=len(cand), best_visible_among_all_inside=vstats, max_inside=max((r["inside"] for r in rows), default=0))


def sight_view(site, prior, P, exclude=None):
    """views other than `exclude` in which >= 80 % of the points are inside AND visible; the largest sight angle from the vertical."""
    V = views()
    c = P.mean(0)
    rows = []
    for n in train_views(site):
        if n == exclude:
            continue
        k = vname(n)
        u, v, z = V.project(k, P)
        inside = (z > 0) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741)
        if inside.mean() < VIS_MIN:
            continue
        D = np.load(S0 / "s61/export" / site / prior / "prior" / f"{n}.npy")
        d = np.full(len(z), np.nan)
        d[inside] = D[np.floor(v[inside]).astype(int), np.floor(u[inside]).astype(int)]
        vis = float(np.mean(inside & np.isfinite(d) & (np.abs(z - d) <= 0.5)))
        if vis < VIS_MIN:
            continue
        r = V.C(k) - c
        ang = float(np.degrees(np.arccos(r[2] / np.linalg.norm(r))))
        rows.append(dict(view=n, tilt_deg=round(V.tilt(k), 2), visible=vis, sight_angle_deg=round(ang, 2)))
    best = max(rows, key=lambda r: r["sight_angle_deg"]) if rows else None
    return (dict(info_view(best["view"]), score=best) if best else None), dict(n_seeing=len(rows), angles=sorted([r["sight_angle_deg"] for r in rows])[-5:])


def section_roof(P2, margin=2.0):
    c = P2.mean(0)
    w, vec = np.linalg.eigh(np.cov((P2 - c).T))
    a = vec[:, np.argmax(w)]
    s = (P2 - c) @ a
    return dict(kind="vertical", centre_xy=c.tolist(), axis_xy=a.tolist(), s_range_m=[float(s.min() - margin), float(s.max() + margin)], band_m=0.5)


def section_across(P2, margin=2.0):
    c = P2.mean(0)
    w, vec = np.linalg.eigh(np.cov((P2 - c).T))
    a = vec[:, np.argmin(w)]
    s = (P2 - c) @ a
    return dict(kind="vertical", centre_xy=c.tolist(), axis_xy=a.tolist(), s_range_m=[float(s.min() - margin), float(s.max() + margin)], band_m=0.5,
                rule="across the long axis (PCA minor axis) of the case region in plan, through its centroid")


def info_view(n):
    V = views(); k = vname(n)
    return dict(view=n, tilt_deg=round(V.tilt(k), 2), camera_centre=V.C(k).round(3).tolist())


def fig1_2():
    site, prior = "B173nb_b10", "ALS"
    W = np.load(SL / "work/undecidable" / f"regions_{site}_{prior}.npz")
    R = region(site, prior); U = store(site, prior)
    case = np.nonzero(W["case_skylight"])[0]; band = np.nonzero(W["case_band_skylight"] & ~W["case_skylight"])[0]
    code = R["code_ext_v3"].astype(int); ev = R["in_eval"].astype(bool)
    P = patch_corners(U, np.concatenate([case, band]))
    vert, sv = score_views(site, prior, P, "vertical")
    obl, so = score_views(site, prior, patch_corners(U, case), "oblique")   # the glass itself (case patches)
    side, sside = sight_view(site, prior, patch_corners(U, case), exclude=vert["view"])
    sec1 = section_across(R["centre"][case][:, :2].astype(np.float64))
    F4 = jl(FT / "prep/figpos.json")["figures"]["fig4"]
    mis = np.array(F4["missing"]["index"], int)
    mis_all_eval = np.nonzero(ev & np.isin(code, [4, 13]))[0]
    cc = R["centre"][case][:, :2].astype(np.float64); mc = R["centre"][mis][:, :2].astype(np.float64)
    near = cc[cKDTree(mc).query(cc)[0] <= 3.0]
    tgt = near if len(near) else cc[[int(np.argmin(cKDTree(mc).query(cc)[0]))]]
    a = tgt.mean(0) - mc.mean(0); a /= np.linalg.norm(a)
    pts = np.vstack([mc, tgt]); s = (pts - mc.mean(0)) @ a
    sec2 = dict(kind="vertical", centre_xy=mc.mean(0).tolist(), axis_xy=a.tolist(), s_range_m=[float(s.min() - 2), float(s.max() + 2)], band_m=0.5,
                rule="from the centroid of the 18 missing patches towards the case patches within 3 m of them; both + 2 m")
    P2 = patch_corners(U, mis)
    f1 = dict(site=site, prior=prior, case_patches=case.tolist(), band_patches=band.tolist(), case_area_m2=float(R["area"][case].sum()),
              place_rule="the fill task's ALS skylight case (SL/work/undecidable/regions_B173nb_b10_ALS.npz case_skylight) and its 2 m band (case_band_skylight)",
              photo_vertical=dict(info_view(vert["view"]), score=vert), photo_oblique=(dict(info_view(obl["view"]), score=obl) if obl else None),
              photo_search=dict(vertical=sv, oblique=so, side=sside), section=sec1, photo_side=side,
              photo_side_rule="[결과를 보기 전에 바꿈] every oblique training view (tilt > 20 deg) that holds the glass sees it hidden behind buildings (prior render nearer by ~22 m LoD2 / ~42 m ALS), so the second photo = the view (other than the vertical photo) in which >= 80 % of the case patches are inside and visible, with the largest angle between the line of sight to the case centroid and the vertical",
              place_xy_box=[float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max())])
    f2 = dict(site=site, prior=prior, missing_patches=mis.tolist(), missing_codes={int(i): int(code[i]) for i in mis},
              missing_in_eval_all=mis_all_eval.tolist(), missing_in_eval_codes={int(i): int(code[i]) for i in mis_all_eval},
              place_rule="the 18 missing patches in the case or its band (FT/prep/figpos.json fig4.missing.index) + 2 m",
              photo=f1["photo_vertical"]["view"], photo_inside_check=bool(all((lambda uvz: ((uvz[2] > 0) & (uvz[0] >= 0) & (uvz[0] < 1024) & (uvz[1] >= 0) & (uvz[1] < 741)).all())(views().project(vname(f1["photo_vertical"]["view"]), P2)) for _ in [0])),
              section=sec2, place_xy_box=[float(P2[:, 0].min() - 2), float(P2[:, 1].min() - 2), float(P2[:, 0].max() + 2), float(P2[:, 1].max() + 2)])
    return f1, f2


def fig4():
    site, prior = "B173nb_b10", "ALS"
    rows = np.load(FT / "prep/figpos_fig1_rows.npz")
    keys = list(rows.files)
    P = rows["xyz_gt"].astype(np.float64)                 # the GT points of the 32,932 rows (fixtest figpos_ft.py fig1)
    sub = P[:: max(1, len(P) // 4000)]
    best, sc = score_views(site, prior, sub, "vertical")
    return dict(site=site, prior=prior, rows_file="FT/prep/figpos_fig1_rows.npz", rows_keys=keys, rows=int(len(P)),
                place_rule="B173nb ALS face 1, code 2 gentle roof rows (fixtest fig 1, 32,932 rows); VIS-v1 scene 6", photo=dict(info_view(best["view"]), score=best),
                photo_search=sc, section=section_roof(P[:, :2]), place_xy_box=[float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max())],
                centre=P.mean(0).tolist())


def wall_face_pick(site, by="missing"):
    R = region(site, "LoD2"); U = store(site, "LoD2")
    code = R["code_ext_v3"].astype(int); ev = R["in_eval"].astype(bool); kind = R["kind"].astype(int)
    se = R["surf_ext"].astype(int)
    wall = ev & (kind == 2)
    exts = np.unique(se[wall])
    tab = []
    for e in exts:
        m = wall & (se == e)
        tab.append(dict(ext=int(e), patches=int(m.sum()), area_m2=float(R["area"][m].sum()), missing=int((m & np.isin(code, [4, 13])).sum()),
                        missing_agree=int((m & (code == 4)).sum()), missing_prior_error=int((m & (code == 13)).sum())))
    key = (lambda r: (r["missing"], r["area_m2"])) if by == "missing" else (lambda r: (r["area_m2"], r["missing"]))
    best = max(tab, key=key)
    return best, sorted(tab, key=lambda r: -r[("missing" if by == "missing" else "area_m2")])[:8]


def wall_normal(site, ext):
    t = {r["ext"]: r for r in jl(DR / "s02_box" / site / "lod2_surfaces.json")["surfaces"]}
    n = np.asarray(t[ext]["normal"], np.float64); n[2] = 0; n /= np.linalg.norm(n)
    return n, t[ext]


def oriented_out(site, ext, n, C):
    """outward = away from the footprint centre of the face's building (as B0REF b0_common.lod2_faces)."""
    t = {r["ext"]: r for r in jl(DR / "s02_box" / site / "lod2_surfaces.json")["surfaces"]}
    bld = t[ext]["building"]
    fp = [r for r in jl(DR / "s02_box" / site / "footprints.json")["footprints"] if r.get("building") == bld]
    if not fp:
        return n, False
    cen = np.asarray(fp[0]["ring_local"], np.float64)[:, :2].mean(0)
    if np.dot(C[:2] - cen, n[:2]) < 0:
        return -n, True
    return n, False


def wall_place(site, ext, prior="LoD2"):
    R = region(site, prior); U = store(site, prior)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
    m = np.nonzero(ev & (se == ext))[0]
    mm = m[np.isin(code[m], [4, 13])]
    C = R["centre"][m].astype(np.float64)
    n, tabrow = wall_normal(site, ext)
    n, flipped = oriented_out(site, ext, n, C.mean(0))
    P = patch_corners(U, mm if len(mm) else m)
    best, sc = score_views(site, prior, P, "wall", normal=n)
    t = np.array([-n[1], n[0], 0.0])
    s = (C - C.mean(0)) @ t
    zmid = float(np.median(R["centre"][mm][:, 2])) if len(mm) else float(np.median(C[:, 2]))
    sec = dict(kind="horizontal", z_m=zmid, band_m=0.5, centre_xy=C.mean(0)[:2].tolist(), axis_xy=t[:2].tolist(), normal_xy=n[:2].tolist(),
               s_range_m=[float(s.min() - 2), float(s.max() + 2)], rule="horizontal band at the median height of the face's missing patches, along the wall, + 2 m")
    return dict(site=site, prior=prior, ext=int(ext), patches=int(len(m)), missing=int(len(mm)), outward_normal=n.tolist(), normal_flipped=flipped,
                building=tabrow["building"], photo=(dict(info_view(best["view"]), score=best) if best else None), photo_search=sc, section=sec)


def roof_face_pick(site, prior):
    R = region(site, prior)
    code = R["code_ext_v3"].astype(int); ev = R["in_eval"].astype(bool); se = R["surf_ext"].astype(int)
    m = ev & np.isin(code, [4, 13])
    u, c = np.unique(se[m], return_counts=True)
    order = np.argsort(-c)
    return int(u[order[0]]), [dict(ext=int(a), missing=int(b)) for a, b in zip(u[order][:8], c[order][:8])]


def fig3b():
    site, prior = "R1rep_b10", "ALS"
    ext, top = roof_face_pick(site, prior)
    R = region(site, prior); U = store(site, prior)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
    m = np.nonzero(ev & (se == ext) & np.isin(code, [4, 13]))[0]
    P = patch_corners(U, m)
    best, sc = score_views(site, prior, P, "vertical")
    return dict(site=site, prior=prior, ext=ext, missing=int(len(m)), top_faces=top, photo=dict(info_view(best["view"]), score=best) if best else None,
                photo_search=sc, section=section_roof(R["centre"][m][:, :2].astype(np.float64)),
                place_rule="the R1 ALS surface with the most missing patches (code 4 or 13) in the evaluation range")


def fig5():
    site, prior = "B0_b10", "ALS"
    R = region(site, prior)
    Z = np.load(SL / "work/obs_masked" / f"region_{site}_{prior}.npz")
    ev = R["in_eval"].astype(bool)
    img = (Z["obs"].astype(bool) & ~(ev & R["premise_violation"].astype(bool))) | (ev & R["obs_within_threshold"].astype(bool))
    idx = np.nonzero(img)[0]
    C = R["centre"][idx].astype(np.float64)
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    pairs = cKDTree(C).query_pairs(0.36, output_type="ndarray")
    A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(C), len(C)))
    nc, lab = connected_components(A, directed=False)
    area = np.bincount(lab, weights=R["area"][idx].astype(np.float64), minlength=nc)
    gtp = np.bincount(lab, weights=R["gt_points"][idx].astype(np.float64), minlength=nc)
    sus = np.bincount(lab, weights=R["gt_suspect"][idx].astype(np.float64), minlength=nc)
    one = (area >= 1.0) & (sus == 0)
    big = area >= 1.0
    fallback = None
    if one.any():
        best = int(np.argmax(np.where(one, gtp, -1.0)))
    else:   # [결과를 보기 전에 바꿈] no >= 1 m2 cluster with one GT layer: the >= 1 m2 cluster with the smallest multi-layer share, then most GT points
        npa = np.bincount(lab, minlength=nc)
        share = np.where(big, sus / np.maximum(npa, 1), np.inf)
        cand = np.nonzero(big & (share <= share.min() + 1e-12))[0]
        best = int(cand[np.argmax(gtp[cand])])
        fallback = dict(rule="no cluster of area >= 1 m2 has one GT layer; chosen = the >= 1 m2 cluster with the smallest share of gt_suspect patches, then the most GT points",
                        clusters_ge_1m2=[dict(cluster=int(c), area_m2=float(area[c]), patches=int(npa[c]), gt_suspect=int(sus[c]), gt_points=int(gtp[c])) for c in np.nonzero(big)[0]])
    mem = idx[lab == best]
    U = store(site, prior)
    P = patch_corners(U, mem)
    pv, sc = score_views(site, prior, P, "vertical")
    c = R["centre"][mem][:, :2].astype(np.float64).mean(0)
    w, vec = np.linalg.eigh(np.cov((R["centre"][mem][:, :2].astype(np.float64) - c).T))
    a = vec[:, np.argmax(w)]
    return dict(site=site, prior=prior, image_error_patches=int(len(idx)), clusters=int(nc), clusters_ge_1m2=int((area >= 1).sum()), one_layer=int(one.sum()),
                cluster_patches=mem.tolist(), cluster_area_m2=float(area[best]), cluster_gt_points=int(gtp[best]),
                photo=dict(info_view(pv["view"]), score=pv) if pv else None, photo_search=sc,
                section=dict(kind="vertical", centre_xy=c.tolist(), axis_xy=a.tolist(), s_range_m=[-6.0, 6.0], band_m=0.5, rule="12 m x 0.5 m along the long axis through the centre"),
                rule="dist71 Unit.img patches joined at 0.36 m (3-D), area >= 1 m2, no gt_suspect patch (one GT layer), most GT points (fixtest fig 2 rule)",
                fallback=fallback, cluster_gt_suspect=int(sus[best]), cluster_n_patches=int(len(mem)))


def main():
    out = dict(made=now(), rule=__doc__.split("\n\n")[1], scientific_verdict=None)
    out["fig1"], out["fig2"] = fig1_2(); log("fig1/2", out["fig1"]["photo_vertical"]["view"], (out["fig1"]["photo_oblique"] or {}).get("view"))
    out["fig4"] = fig4(); log("fig4", out["fig4"]["photo"]["view"])
    ext3, top3 = wall_face_pick("R1rep_b10", "missing")
    out["fig3"] = dict(wall_place("R1rep_b10", ext3["ext"]), face_table=top3, place_rule="the R1 LoD2 wall face with the most missing patches (code 4 or 13) in the evaluation range")
    log("fig3", ext3, (out["fig3"]["photo"] or {}).get("view"))
    t13 = max(top3, key=lambda r: (r["missing_prior_error"], r["missing"]))
    out["fig3_extra"] = dict(wall_place("R1rep_b10", t13["ext"]), face_row=t13,
                             place_rule="[결과를 보기 전에 더함] the chosen face has no missing patch of the prior-error kind (code 13); this extra place = the R1 LoD2 wall face with the most code-13 missing patches (from the face table of the 8 faces with the most missing patches)")
    log("fig3 extra", t13)
    out["fig3b"] = fig3b(); log("fig3b", out["fig3b"]["ext"], (out["fig3b"]["photo"] or {}).get("view"))
    out["fig5"] = fig5(); log("fig5", out["fig5"]["cluster_area_m2"], (out["fig5"]["photo"] or {}).get("view"))
    f6 = {}
    for site in ("B173nb_b10", "R1rep_b10", "B0_b10"):
        a, ta = wall_face_pick(site, "area"); m, tm = wall_face_pick(site, "missing")
        faces = [a["ext"]] + ([m["ext"]] if m["ext"] != a["ext"] else [])
        f6[site] = dict(largest=a, most_missing=m, faces=[wall_place(site, e) for e in faces], area_table=ta, missing_table=tm)
        log("fig6", site, faces)
    out["fig6"] = f6
    jdump(PF / "prep/places.json", out)
    log("done")


if __name__ == "__main__":
    main()
