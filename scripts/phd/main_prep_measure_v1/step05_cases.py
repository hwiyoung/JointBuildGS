"""PHD-MAIN-PREP-MEASURE-v1 step 05 (jointbuildgs:dev, CPU): real cases of one range (order 5.4, cases 1-5 and 8).

  python step05_cases.py <range_id> [--stage1-sub step03] [--gt-sub step04] [--mesh-sub step02] [--out-sub step05]

Units = judgment units (0.25 m patches) inside the range, not excluded (step04 frozen exclusion), of each prior.
Case 1  LoD2 |GT - prior| / tau bins (<= 1, 1-2, 2-4, > 4) and automatic types (curved > wall position > eave > rooftop
        structure > other), face list
Case 2  missing units of surfaces that also hold support units: propagated judgment vs true label; missing reason from the
        undistorted images of the seeing views (brightness 5 x 5, texture std 9 x 9, angle ray / normal; config thresholds)
Case 3  case-3 views: confidence-1 pixels whose MVS depth misses the GT by more than tau (a), and confidence-0 pixels whose
        photometric depth misses it (b); (a) on true-agree prior = 'read as conflict by mistake'; 3-D blobs (0.5 m cells)
Case 4  invisible units: GT cover, true label (inheriting the prior right / wrong)
Case 5  true-conflict units: prior in front / behind; LoD2 cause by the registered ALS at the same place (representation vs
        time-change candidate); GT clusters above every prior surface ('absent structure', counted as behind)
Case 8  LoD2 units in the 1-2 tau bin (list)
Outputs: tables (csv / json) and candidate items for the figure rows. scientific_verdict: null."""
import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np
import scipy.ndimage as ndi

from common import CFG, DENSE, OUT, GRID_H, GRID_W, Views, inside_range, jdump, log, read_depth_bin
from src.phd.prior_propagation_v4 import conversion as conv
from src.phd.prior_propagation_v4 import locations as locs
from src.phd.prior_propagation_v4 import rule

CC = CFG["cases"]


def wcsv(path, rows):
    if not rows:
        Path(path).write_text("")
        return
    keys = list(rows[0].keys())
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); [w.writerow(r) for r in rows]


def boundary_distance(U):
    """in-plane distance (m) of each unit to the edge of its surface raster (distance transform of the member mask)."""
    sp = float(U["sp"]); out = np.zeros(len(U["loc_area"]))
    for s in range(len(U["surf_ext"])):
        ni, nj, off = int(U["ni"][s]), int(U["nj"][s]), int(U["off"][s])
        mem = U["member"][off:off + ni * nj].reshape(ni, nj)
        m = mem >= 0
        if not m.any():
            continue
        d = ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
        out[mem[m]] = (d[m] - 0.5) * sp
    return out


def unit_normals(U):
    n = np.cross(U["loc_t1"], U["loc_t2"]); L = np.linalg.norm(n, axis=1)
    n = np.where(L[:, None] > 1e-9, n / np.maximum(L, 1e-12)[:, None], [0, 0, 1.0])
    return np.where(n[:, 2:3] < 0, -n, n)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("range_id")
    ap.add_argument("--stage1-sub", default="step03"); ap.add_argument("--gt-sub", default="step04")
    ap.add_argument("--mesh-sub", default="step02"); ap.add_argument("--out-sub", default="step05")
    ap.add_argument("--mvs", default="current")
    a = ap.parse_args()
    t0 = time.time(); rid = a.range_id
    D = OUT / a.out_sub / rid; D.mkdir(parents=True, exist_ok=True)
    rng = json.loads((OUT / a.mesh_sub / rid / "range.json").read_text())
    V = Views()
    res = dict(range=rid)
    unitsets = {}
    for prior in ("LoD2", "ALS"):
        S1 = OUT / a.stage1_sub / rid / prior
        if not (S1 / "units.npz").exists():
            continue
        U = locs.load_store(S1 / "units.npz")
        G = dict(np.load(OUT / a.gt_sub / rid / f"labels_{prior}.npz"))
        summ = json.loads((S1 / "summary.json").read_text())
        unitsets[prior] = (U, G, summ)
    # ------------------------------------------------------------------ case 1, 8 (LoD2)
    if "LoD2" in unitsets:
        U, G, summ = unitsets["LoD2"]
        tab = {r["ext"]: r for r in json.loads((OUT / a.mesh_sub / rid / "lod2_surfaces.json").read_text())["surfaces"]}
        inr = U["loc_in_range"] & ~G["excluded"]
        lab, med, tau = G["label"], G["gt_med"].astype(float), G["tau"].astype(float)
        kind = U["loc_kind"]; ext = U["surf_ext"][U["loc_surface"]]
        ratio = np.abs(med) / tau
        has = inr & (lab >= 0)
        bins = CC["c1_bins_tau"]
        def bin_of(rv):
            return np.digitize(rv, bins, right=True)       # 0: <=1, 1: 1-2, 2: 2-4, 3: >4
        bi = np.where(has, bin_of(np.nan_to_num(ratio, nan=0)), -1)
        bdist = boundary_distance(U)
        # curved faces: plane fit of the GT surface over a face with >= 50 labelled units
        curved_face = set()
        face_rows = []
        for e in np.unique(ext[has]):
            sel = has & (ext == e)
            k = int(sel.sum())
            row = dict(face=int(e), gml=tab[int(e)]["gml"], building=tab[int(e)]["building"], type=tab[int(e)]["type"], units_gt=k,
                       true_conflict_share=round(float((lab[sel] == 1).mean()), 3), median_abs_diff_m=round(float(np.median(np.abs(med[sel]))), 3),
                       median_signed_diff_m=round(float(np.median(med[sel])), 3), area_m2=round(float(U["loc_area"][sel].sum()), 1))
            if k >= 50 and tab[int(e)]["type"] == "roof":
                C = U["loc_center"][sel]; z = C[:, 2] + med[sel]
                A_ = np.column_stack([C[:, 0] - C[:, 0].mean(), C[:, 1] - C[:, 1].mean(), np.ones(k)])
                coef, *_ = np.linalg.lstsq(A_, z, rcond=None)
                rms = float(np.sqrt(np.mean((A_ @ coef - z) ** 2)))
                row["gt_plane_rms_m"] = round(rms, 3)
                if rms > 0.15:
                    curved_face.add(int(e))
            face_rows.append(row)
        typ = np.full(len(lab), "", dtype=object)
        tc = has & (lab == 1)
        typ[tc] = "other"
        roofc = tc & (kind == 1)
        typ[roofc & (med > 0) & (bdist >= 1.0)] = "rooftop structure"
        typ[roofc & (bdist < 1.0)] = "eave"
        typ[tc & (kind == 2)] = "wall position"
        typ[tc & np.isin(ext, list(curved_face))] = "curved"
        c1 = {}
        for kname, kk in (("roof", 1), ("wall", 2)):
            m = has & (kind == kk)
            c1[kname] = dict(units=int(m.sum()), bins={nm: dict(units=int((m & (bi == b)).sum()), area_m2=float(U["loc_area"][m & (bi == b)].sum()))
                                                     for b, nm in enumerate(["<=1", "1-2", "2-4", ">4"])})
        c1["types_true_conflict"] = {t: dict(units=int((typ == t).sum()), area_m2=float(U["loc_area"][typ == t].sum())) for t in
                                     ["curved", "wall position", "eave", "rooftop structure", "other"]}
        res["case1_LoD2"] = c1
        for r in face_rows:
            r["curved"] = r["face"] in curved_face
            sel = has & (ext == r["face"]) & tc
            if sel.any():
                vals, cnts = np.unique(typ[sel], return_counts=True); r["types"] = ";".join(f"{v}:{c}" for v, c in zip(vals, cnts))
        face_rows.sort(key=lambda r: -r["units_gt"] * r["true_conflict_share"])
        wcsv(D / "case1_faces_LoD2.csv", face_rows)
        # case 8: 1-2 tau bin
        c8 = has & (bi == 1)
        rows8 = []
        for e in np.unique(ext[c8]):
            sel = c8 & (ext == e)
            rows8.append(dict(face=int(e), gml=tab[int(e)]["gml"], building=tab[int(e)]["building"], type=tab[int(e)]["type"], units=int(sel.sum()),
                              median_signed_diff_m=round(float(np.median(med[sel])), 3), tau_m=round(float(tau[sel][0]), 3),
                              support_votes_conflict_share=round(float(((U["state"][sel] == rule.ST_SUPPORT) & (U["vote"][sel] == rule.V_CONFLICT)).sum() / max((U["state"][sel] == rule.ST_SUPPORT).sum(), 1)), 3)))
        rows8.sort(key=lambda r: -r["units"]); wcsv(D / "case8_boundary_LoD2.csv", rows8)
        res["case8_LoD2"] = dict(units=int(c8.sum()), faces=len(rows8))
        np.savez_compressed(D / "case1_unit_types_LoD2.npz", type=typ.astype("U20"), bin=bi.astype(np.int8), boundary_dist=bdist.astype(np.float32))
    # ------------------------------------------------------------------ cases 2, 4, 5 per prior
    for prior, (U, G, summ) in unitsets.items():
        inr = U["loc_in_range"] & ~G["excluded"]
        lab, med = G["label"], G["gt_med"].astype(float)
        st, J = U["state"], U["J"]
        ext = U["surf_ext"][U["loc_surface"]]
        # case 2: surfaces with both missing and support units
        mis = inr & (st == rule.ST_MISSING)
        sup_surf = set(np.unique(ext[inr & (st == rule.ST_SUPPORT)]).tolist())
        both = mis & np.isin(ext, list(sup_surf))
        conf = {}
        for j, jn in rule.J_NAMES.items():
            m = both & (J == j)
            conf[jn] = dict(units=int(m.sum()), true_agree=int((m & (lab == 0)).sum()), true_conflict=int((m & (lab == 1)).sum()), no_gt=int((m & (lab < 0)).sum()))
        right = int(((both & (J == rule.J_AGREE) & (lab == 0)) | (both & (J == rule.J_CONFLICT) & (lab == 1))).sum())
        wrong = int(((both & (J == rule.J_AGREE) & (lab == 1)) | (both & (J == rule.J_CONFLICT) & (lab == 0))).sum())
        # missing reasons from the images
        pairs = np.load(OUT / a.stage1_sub / rid / prior / "unit_view_pairs.npz")
        pv, pl, pn, pa = pairs["view"], pairs["loc"], pairs["npix"], pairs["na1"]
        vnames = pairs["views"]
        reg = np.asarray(summ["registration"]["shift_applied"], float)
        idx_mis = np.nonzero(both)[0]
        bright = [[] for _ in range(len(idx_mis))]; tex = [[] for _ in range(len(idx_mis))]; ang = [[] for _ in range(len(idx_mis))]
        pos = -np.ones(len(st), np.int64); pos[idx_mis] = np.arange(len(idx_mis))
        nrm = unit_normals(U) if prior == "ALS" else None
        if prior == "LoD2":
            tab = {r["ext"]: r for r in json.loads((OUT / a.mesh_sub / rid / "lod2_surfaces.json").read_text())["surfaces"]}
            nrm = np.array([tab[int(e)]["normal"] for e in ext])
        sel_pairs = pos[pl] >= 0
        fx0, fy0, cx0, cy0 = V.K0
        for vi in np.unique(pv[sel_pairs]):
            k = np.nonzero(sel_pairs & (pv == vi))[0]
            nme = str(vnames[vi])
            img = cv2.imread(str(DENSE / "images" / nme), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            imf = img.astype(np.float32)
            mean5 = cv2.blur(imf, (5, 5)); m9 = cv2.blur(imf, (9, 9)); sq9 = cv2.blur(imf * imf, (9, 9))
            std9 = np.sqrt(np.maximum(sq9 - m9 * m9, 0))
            units = pl[k]
            C = U["loc_center"][units] + reg
            R, t = V.R(nme), V.t(nme)
            Xc = C @ R.T + t
            u = fx0 * Xc[:, 0] / Xc[:, 2] + cx0; v = fy0 * Xc[:, 1] / Xc[:, 2] + cy0
            ok = (Xc[:, 2] > 0) & (u >= 0) & (u < img.shape[1]) & (v >= 0) & (v < img.shape[0])
            ui = np.clip(u.astype(int), 0, img.shape[1] - 1); vv_ = np.clip(v.astype(int), 0, img.shape[0] - 1)
            ray = C - V.C(nme); ray /= np.linalg.norm(ray, axis=1, keepdims=True)
            cosang = np.abs((ray * nrm[units]).sum(1))
            for j_, uu_, b_, s_, c_, o_ in zip(pos[units], units, mean5[vv_, ui], std9[vv_, ui], cosang, ok):
                if o_:
                    bright[j_].append(b_); tex[j_].append(s_); ang[j_].append(np.degrees(np.arccos(np.clip(c_, 0, 1))))
        th = CC["c2_missing_reason"]["thresholds"]
        reason = np.full(len(idx_mis), "other", dtype=object)
        mb = np.array([np.median(b) if b else np.nan for b in bright]); mt = np.array([np.median(x) if x else np.nan for x in tex])
        ma = np.array([np.median(x) if x else np.nan for x in ang])
        reason[ma > th["oblique_angle_gt_deg"]] = "oblique"
        reason[mt < th["textureless_std_lt"]] = "textureless"
        reason[mb < th["shadow_brightness_lt"]] = "shadow"
        reason[~np.isfinite(mb)] = "no image sample"
        reasons = {rn: dict(units=int((reason == rn).sum()), right=int(((reason == rn) & (((J[idx_mis] == rule.J_AGREE) & (lab[idx_mis] == 0)) | ((J[idx_mis] == rule.J_CONFLICT) & (lab[idx_mis] == 1)))).sum()))
                   for rn in ["shadow", "textureless", "oblique", "other", "no image sample"]}
        np.savez_compressed(D / f"case2_missing_{prior}.npz", unit=idx_mis.astype(np.int64), brightness=mb.astype(np.float32), texture=mt.astype(np.float32),
                            angle=ma.astype(np.float32), reason=reason.astype("U20"))
        # surfaces list (case 2)
        srows = []
        for e in np.unique(ext[both]):
            m = both & (ext == e)
            srows.append(dict(surface=int(e), missing=int(m.sum()), support=int((inr & (ext == e) & (st == rule.ST_SUPPORT)).sum()),
                              prop_agree=int((m & (J == rule.J_AGREE)).sum()), prop_conflict=int((m & (J == rule.J_CONFLICT)).sum()),
                              mixed=int((m & (J == rule.J_MIXED)).sum()), insufficient=int((m & (J == rule.J_INSUFF)).sum()),
                              right=int((m & (((J == rule.J_AGREE) & (lab == 0)) | ((J == rule.J_CONFLICT) & (lab == 1)))).sum()),
                              wrong=int((m & (((J == rule.J_AGREE) & (lab == 1)) | ((J == rule.J_CONFLICT) & (lab == 0)))).sum()),
                              main_reason=(lambda rr: max(set(rr), key=list(rr).count) if len(rr) else "")(reason[pos[np.nonzero(m)[0]]])))
        srows.sort(key=lambda r: -r["missing"]); wcsv(D / f"case2_surfaces_{prior}.csv", srows)
        # case 4: invisible
        inv = inr & (st == rule.ST_INVISIBLE)
        c4 = dict(units=int(inv.sum()), share=float(inv.sum() / max(inr.sum(), 1)), with_gt=int((inv & (lab >= 0)).sum()),
                  inherit_right=int((inv & (lab == 0)).sum()), inherit_wrong=int((inv & (lab == 1)).sum()), area_m2=float(U["loc_area"][inv].sum()))
        # case 5: direction (prior in front: roof GT below prior (med < 0); wall GT inside (med < 0))
        tcf = inr & (lab == 1)
        front = tcf & (med < 0); behind = tcf & (med > 0)
        c5 = dict(true_conflict=int(tcf.sum()), prior_in_front=int(front.sum()), prior_behind=int(behind.sum()),
                  front_area_m2=float(U["loc_area"][front].sum()), behind_area_m2=float(U["loc_area"][behind].sum()))
        res[f"case2_{prior}"] = dict(missing_units_on_surfaces_with_support=int(both.sum()), by_judgment=conf, right=right, wrong=wrong,
                                     reasons=reasons, surfaces=len(srows), surfaces_with_mixed=int(sum(r["mixed"] > 0 for r in srows)))
        res[f"case4_{prior}"] = c4
        res[f"case5_{prior}"] = c5
        np.savez_compressed(D / f"case5_units_{prior}.npz", front=np.nonzero(front)[0], behind=np.nonzero(behind)[0])
    # case 5 cause for LoD2: the registered ALS TIN at the same place
    if "LoD2" in unitsets and "ALS" in unitsets:
        from common import Scene
        U, G, summ = unitsets["LoD2"]
        UA, GA, sA = unitsets["ALS"]
        m = dict(np.load(OUT / a.mesh_sub / rid / "als_mesh.npz", allow_pickle=False))
        shA = np.asarray(sA["registration"]["shift_applied"], float)
        tauA = sA["tolerance"]["roof"]["tau"]
        inr = U["loc_in_range"] & ~G["excluded"]; lab = G["label"]; med = G["gt_med"].astype(float)
        tcf = np.nonzero(inr & (lab == 1) & (U["loc_kind"] == 1))[0]
        shL = np.asarray(summ["registration"]["shift_applied"], float)
        C = U["loc_center"][tcf] + shL
        zgt = C[:, 2] + med[tcf]
        sc = Scene(m["V"] + shA, m["F"])
        t, tri = sc.cast_points(np.column_stack([C[:, 0], C[:, 1], np.full(len(C), 250.0)]), np.tile([0, 0, -1.0], (len(C), 1)))
        zal = 250.0 - t
        okA = np.isfinite(zal)
        rep = okA & (np.abs(zgt - zal) <= tauA)
        chg = okA & ~rep
        res["case5_LoD2_cause"] = dict(true_conflict_roof=int(len(tcf)), als_matches_gt_representation=int(rep.sum()),
                                       als_also_off_time_change_candidate=int(chg.sum()), no_als=int((~okA).sum()))
        np.savez_compressed(D / "case5_cause_LoD2.npz", unit=tcf, als_minus_gt=(zal - zgt).astype(np.float32), representation=rep, change_candidate=chg)
    # ------------------------------------------------------------------ case 5 (absent structure, config c5_absent_structure)
    gpp = OUT / a.gt_sub / rid / "gt_primary.npz"
    if gpp.exists() and unitsets:
        from common import SURVEY, Scene
        Xg = np.load(gpp)["xyz"].astype(np.float64)
        Xg = Xg[inside_range(Xg[:, :2], rng)] if rng["kind"] != "polygon" else Xg
        exc = np.load(OUT / a.gt_sub / rid / "exclusion_cells.npz")
        Sv = np.load(SURVEY / "derived.npz")
        E = Xg[:, 0] + 690953.0; N = Xg[:, 1] + 5336071.0
        ix = np.clip(((E - 690700.0) / 0.5).astype(int), 0, Sv["dtm"].shape[1] - 1); iy = np.clip(((N - 5335820.0) / 0.5).astype(int), 0, Sv["dtm"].shape[0] - 1)
        dtm = Sv["dtm"][iy, ix].astype(np.float64) - 604.0
        absent = {}
        for prior, (U, G, summ) in unitsets.items():
            ex = exc["any"][iy, ix] | (exc["prior_side_trees"][iy, ix] if prior == "ALS" else False)
            msh = dict(np.load(OUT / a.mesh_sub / rid / ("als_mesh.npz" if prior == "ALS" else "lod2_mesh.npz"), allow_pickle=False))
            sh = np.asarray(summ["registration"]["shift_applied"], float)
            sc = Scene(msh["V"] + sh, msh["F"])
            zt = np.full(len(Xg), np.nan); trs = np.full(len(Xg), -1, np.int64)
            for b0 in range(0, len(Xg), 4_000_000):
                Q = Xg[b0:b0 + 4_000_000]
                t, tri = sc.cast_points(np.column_stack([Q[:, 0], Q[:, 1], np.full(len(Q), 250.0)]), np.tile([0, 0, -1.0], (len(Q), 1)))
                zt[b0:b0 + len(Q)] = 250.0 - t; trs[b0:b0 + len(Q)] = tri
            if prior == "ALS":   # v4: a gentle non-building ALS triangle (or nothing) below, more than 2.0 m under the GT point
                tn = msh["tri_normal"]
                gentle_ground = (trs >= 0) & (msh["tri_surface"][np.maximum(trs, 0)] < 0) & (np.abs(tn[np.maximum(trs, 0), 2]) >= 0.5)
                hgt = Xg[:, 2] - np.where(np.isfinite(zt), zt, dtm)
                cand = ~ex & ((trs < 0) | gentle_ground) & (hgt > 2.0)
            else:
                cand = ~ex & (trs < 0) & (Xg[:, 2] - dtm > 2.0)
                hgt = Xg[:, 2] - dtm
            k = np.nonzero(cand)[0]
            blobs = []
            if len(k):
                ij = np.floor(Xg[k, :2] / 0.5).astype(np.int64); ij0 = ij.min(0); ij -= ij0
                M = np.zeros(ij.max(0) + 1, np.int32); np.add.at(M, (ij[:, 0], ij[:, 1]), 1)
                lab_, nb = ndi.label(M > 0, structure=np.ones((3, 3)))
                pl_ = lab_[ij[:, 0], ij[:, 1]]
                area = ndi.sum(np.ones_like(lab_), lab_, index=np.arange(1, nb + 1)) * 0.25
                for b in np.nonzero(area >= 2.0)[0] + 1:
                    mm = pl_ == b
                    Q = Xg[k[mm]]
                    blobs.append(dict(area_m2=float(area[b - 1]), x=float(Q[:, 0].mean()), y=float(Q[:, 1].mean()), z=float(np.median(Q[:, 2])),
                                      points=int(mm.sum()), median_height_above_m=float(np.median(hgt[k[mm]]))))
            blobs.sort(key=lambda r: -r["area_m2"])
            wcsv(D / f"case5_absent_{prior}.csv", blobs)
            absent[prior] = dict(points=int(len(k)), blobs=len(blobs), area_m2=float(sum(b["area_m2"] for b in blobs)),
                                 rule=CC["revision_v4_analysis"]["case5_absent_ALS"] if prior == "ALS" else CC["c5_absent_structure"][prior])
            if f"case5_{prior}" in res:
                res[f"case5_{prior}"]["absent_structure"] = absent[prior]
    # ------------------------------------------------------------------ case 3 (image errors)
    gt_dir = OUT / a.gt_sub / rid / "gt_depth"
    mvs_dir = DENSE if a.mvs == "current" else OUT / a.mvs
    if gt_dir.exists() and "LoD2" in unitsets:
        from common import Scene
        U, G, summ = unitsets["LoD2"]
        m = dict(np.load(OUT / a.mesh_sub / rid / "lod2_mesh.npz", allow_pickle=False))
        sh = np.asarray(summ["registration"]["shift_applied"], float)
        tab = {r["ext"]: r for r in json.loads((OUT / a.mesh_sub / rid / "lod2_surfaces.json").read_text())["surfaces"]}
        n_tri = np.array([tab[int(e)]["normal"] if int(e) in tab else [0, 0, 1.0] for e in m["tri_surface"]])
        sc = Scene(m["V"] + sh, m["F"])
        tauR, tauW = summ["tolerance"]["roof"]["tau"], summ["tolerance"]["wall"]["tau"]
        A_cnt = dict(a1_px=0, a1_wrong=0, a1_wrong_prior_agree=0, a0_px=0, a0_photometric_px=0, a0_photometric_wrong=0, gt_px=0)
        R_cnt = dict(A_cnt)        # v4: roof-like faces only
        blobs_a, blobs_b = [], []
        for f in sorted(gt_dir.glob("*.npz")):
            nme = f.stem
            gt = np.load(f)["depth"].astype(np.float64)
            dg = read_depth_bin(Path(mvs_dir) / "stereo/depth_maps" / f"{nme}.geometric.bin")
            pp = Path(mvs_dir) / "stereo/depth_maps" / f"{nme}.photometric.bin"
            dp = read_depth_bin(pp) if pp.exists() else np.full_like(dg, np.nan)
            Dr = V.rays(nme); Cc = V.C(nme)
            tP, tri = sc.cast(Cc, Dr)
            hit = tri >= 0
            n = np.zeros((GRID_H, GRID_W, 3)); n[hit] = n_tri[tri[hit]]
            f_ = conv.factor(n, Dr.astype(np.float64), has_surface=hit)
            kind = conv.surface_kind(n[..., 2])
            tau_px = np.where(hit & (kind == conv.KIND_WALL), tauW, tauR)
            fin = np.isfinite(gt)
            a1 = np.isfinite(dg) & (dg > 0)
            sel = fin & hit
            e_a = np.abs(dg - gt) * f_
            wrong_a = sel & a1 & (e_a > tau_px)
            prior_ok = sel & (np.abs(tP - gt) * f_ <= tau_px)
            pv_ = np.isfinite(dp) & (dp > 0) & ~a1
            e_b = np.abs(dp - gt) * f_
            wrong_b = sel & pv_ & (e_b > tau_px)
            for cnt_, mk in ((A_cnt, np.ones_like(sel)), (R_cnt, hit & (kind == conv.KIND_ROOF))):
                cnt_["gt_px"] += int((sel & mk).sum()); cnt_["a1_px"] += int((sel & a1 & mk).sum()); cnt_["a1_wrong"] += int((wrong_a & mk).sum())
                cnt_["a1_wrong_prior_agree"] += int((wrong_a & prior_ok & mk).sum())
                cnt_["a0_px"] += int((sel & ~a1 & mk).sum()); cnt_["a0_photometric_px"] += int((sel & pv_ & mk).sum()); cnt_["a0_photometric_wrong"] += int((wrong_b & mk).sum())
            roofmask = hit & (kind == conv.KIND_ROOF)
            for msk, lst, err, dep in ((wrong_a & roofmask, blobs_a, e_a, dg), (wrong_b & roofmask, blobs_b, e_b, dp)):
                k = np.nonzero(msk.ravel())[0]
                if len(k):
                    X = Cc[None, :] + gt.ravel()[k, None] * Dr.reshape(-1, 3)[k].astype(np.float64)
                    lst.append(np.column_stack([X, err.ravel()[k], np.sign(dep.ravel()[k] - gt.ravel()[k])]))
        def cluster(lst):
            """v4: 0.5 m cells in 3-D, 26-connected; area = occupied XY cells x 0.25 m2."""
            if not lst:
                return []
            P = np.concatenate(lst)
            ijk = np.floor(P[:, :3] / 0.5).astype(np.int64)
            ijk -= ijk.min(0)
            M = np.zeros(ijk.max(0) + 1, np.int32)
            np.add.at(M, (ijk[:, 0], ijk[:, 1], ijk[:, 2]), 1)
            lab_, nb = ndi.label(M > 0, structure=np.ones((3, 3, 3)))
            pl = lab_[ijk[:, 0], ijk[:, 1], ijk[:, 2]]
            order = np.argsort(pl, kind="stable"); pls = pl[order]
            starts = np.r_[0, np.nonzero(np.diff(pls))[0] + 1]; ends = np.r_[starts[1:], len(pls)]
            out = []
            for s0, e0 in zip(starts, ends):
                if e0 - s0 < 8:          # fewer than 8 pixels cannot cover 2 m2 of 0.25 m2 cells
                    continue
                idx = order[s0:e0]
                area = float(len(np.unique(ijk[idx][:, :2], axis=0))) * 0.25
                if area < 2.0:
                    continue
                Q = P[idx]
                out.append(dict(area_m2=area, x=float(Q[:, 0].mean()), y=float(Q[:, 1].mean()), z=float(Q[:, 2].mean()), pixels=int(len(idx)),
                                median_err_m=float(np.median(Q[:, 3])), mvs_behind_share=float((Q[:, 4] > 0).mean())))
            out.sort(key=lambda r: -r["area_m2"])
            return out
        ca, cb = cluster(blobs_a), cluster(blobs_b)
        wcsv(D / "case3_blobs_a.csv", ca); wcsv(D / "case3_blobs_b.csv", cb)
        res["case3"] = dict(counts=A_cnt, counts_roof_like=R_cnt, blobs_a=len(ca), blobs_b=len(cb), views=len(list(gt_dir.glob("*.npz"))),
                            note="building-face pixels of the LoD2 render with a GT depth; tau of the face kind (LoD2); blobs from roof-like faces only (v4)")
    res["seconds"] = round(time.time() - t0, 1)
    jdump(D / "cases.json", res)
    log(rid, "cases done", res["seconds"], "s")


if __name__ == "__main__":
    main()
