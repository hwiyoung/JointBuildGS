"""PHD-MAIN-PREP-MEASURE-v1 step 03 (jointbuildgs:dev, CPU): stage 1 and the pre-training judgment of one range and prior.

  python step03_stage1.py <range_id> <LoD2|ALS> [--views-key train] [--views-file step01/views.json]
         [--mesh-sub step02] [--mvs current|<colmap workspace dir under /out>] [--out-sub step03] [--fig-views 8]

Pass 1  render the prior at every view (native 1024 x 741 grid), residuals of confidence-1 pixels -> Nuth-Kaab samples
Reg.    method 4.1 registration (Nuth-Kaab horizontal + conditional vertical), accepted only if the NMAD decreases;
        R1 / R4: the same estimator per 80 m tile (observation only)
Pass 2  re-render the registered prior -> tolerance per kind (2.5 NMAD after one 3-NMAD clip; wall fallback)
Pass 3  re-render -> marks, coverage tables (view / LoD2 footprint as reporting unit / surface), conflict ratios,
        judgment-unit counts (sparse location_state), gap probe counts (LoD2, before / after caps)
Then    unit states, votes, propagation (2/3, 5, 1 m), pixel judgments without a unit, unplanted points,
        ALS cell-method initial directions (5.7).
Confidence mask = r10: valid COLMAP geometric depth. scientific_verdict: null."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath

from common import (CFG, DENSE, OUT, GRID_H, GRID_W, Scene, Views, global_to_local, inside_range, jdump, log,
                    range_polygon, read_depth_bin)
from src.phd.prior_propagation_v4 import conversion as conv
from src.phd.prior_propagation_v4 import locations as locs
from src.phd.prior_propagation_v4 import orientation as ori
from src.phd.prior_propagation_v4 import rule
from src.phd.prior_propagation_v4 import surfaces as surf
from src.phd.prior_propagation_v4 import tolerance as tol

T_ROOF, T_WALL, T_CAP = 0, 1, 2
NMAD_C = 1.4826
RNG = np.random.default_rng(0)


def nmad(x):
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return np.nan, np.nan
    m = float(np.median(x))
    return m, float(NMAD_C * np.median(np.abs(x - m)))


# ------------------------------------------------------------------------------------------------ prior
class Prior:
    def __init__(self, mesh_dir, prior):
        self.prior = prior
        if prior == "LoD2":
            m = dict(np.load(mesh_dir / "lod2_mesh.npz", allow_pickle=False))
            self.V0, self.F = m["V"].astype(np.float64), m["F"].astype(np.int64)
            self.tri_surface = m["tri_surface"].astype(np.int64); self.tri_type = m["tri_type"]
            tab = json.loads((mesh_dir / "lod2_surfaces.json").read_text())["surfaces"]
            self.table = {r["ext"]: r for r in tab}
            n_tri, a_tri = surf.tri_geometry(self.V0, self.F)
            self.n_used = n_tri.copy()
            for e, r in self.table.items():
                self.n_used[self.tri_surface == e] = np.asarray(r["normal"])
            self.bface_tri = np.ones(len(self.F), bool)                 # every LoD2 polygon and cap is a building face
            self.has_unit_tri = self.tri_type != T_CAP                   # caps: building faces without judgment units
            self.PV, self.PF = m["PV"].astype(np.float64), m["PF"].astype(np.int64)
            self.n_poly = int(m["n_poly_tris"]); self.probe_overlap = m["probe_overlap"]
            self.store = locs.load_store(mesh_dir / "lod2_store.npz")
        else:
            m = dict(np.load(mesh_dir / "als_mesh.npz", allow_pickle=False))
            self.V0, self.F = m["V"].astype(np.float64), m["F"].astype(np.int64)
            self.tri_surface = m["tri_surface"].astype(np.int64)
            self.n_used = m["tri_normal"].astype(np.float64)
            self.cls, self.multi = m["cls"], m["multi"]
            self.bface_tri = self.tri_surface >= 0                         # numbered (building) surfaces
            self.has_unit_tri = self.bface_tri.copy()
            self.table = {r["ext"]: r for r in json.loads((mesh_dir / "als_surfaces.json").read_text())["surfaces"]}
            self.store = locs.load_store(mesh_dir / "als_store.npz")
        self.shift = np.zeros(3)
        self.ci_of_tri = np.full(len(self.F), -1, np.int64)
        ok = self.has_unit_tri & (self.tri_surface >= 0)
        self.ci_of_tri[ok] = locs.compact_index(self.store, self.tri_surface[ok])

    def scene(self, with_caps=True, with_probe=False):
        F = self.F if (self.prior != "LoD2" or with_caps) else self.F[:self.n_poly]
        V = self.V0 + self.shift
        if with_probe and self.prior == "LoD2" and len(self.PF):
            V2 = np.concatenate([V, self.PV + self.shift]); F2 = np.concatenate([F, self.PF + len(V)])
            return Scene(V2, F2), len(F)
        return Scene(V, F), len(F)


# ------------------------------------------------------------------------------------------------ registration
def nk_fit(dh, n, w=None):
    """dh / tan(slope) = A cos(aspect) + B sin(aspect) + C; correction applied to the prior: (dx, dy) = (B, A)."""
    nz = np.abs(n[:, 2]); nxy = np.hypot(n[:, 0], n[:, 1])
    tan = nxy / np.maximum(nz, 1e-9)
    asp = np.arctan2(n[:, 0] * np.sign(n[:, 2]), n[:, 1] * np.sign(n[:, 2]))      # azimuth of the downslope direction
    y = dh / tan
    X = np.stack([np.cos(asp), np.sin(asp), np.ones_like(asp)], 1)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return np.array([coef[1], coef[0]]), asp


def apply_shift_dh(dh, n, d):
    gx = n[:, 0] / n[:, 2]; gy = n[:, 1] / n[:, 2]
    return dh - gx * d[0] - gy * d[1]


def estimable(asp, cfg):
    q = np.floor(((asp + np.pi) % (2 * np.pi)) / (np.pi / 2)).astype(int)
    share = np.bincount(np.clip(q, 0, 3), minlength=4) / max(len(asp), 1)
    return bool((share >= 0.05).sum() >= 3 and len(asp) >= 2000), share.tolist()


def nuth_kaab(dh, n, cfg):
    """returns dict(dx, dy, iterations, accepted, nmad trace); dh, n of the fit pixels."""
    rec = dict(iterations=[], horizontal_estimable=None)
    asp = np.arctan2(n[:, 0], n[:, 1])
    est, share = estimable(asp, cfg)
    rec["horizontal_estimable"] = est; rec["aspect_quadrant_share"] = share; rec["n_fit"] = int(len(dh))
    total = np.zeros(2)
    cur = dh.copy()
    m0, s0 = nmad(cur); rec["nmad_start"] = s0; rec["median_start"] = m0
    if not est:
        rec["shift_xy"] = [0.0, 0.0]; return rec
    s_prev = s0
    for it in range(cfg["iterations_max"]):
        m, s = nmad(cur)
        inl = np.abs(cur - m) <= 3 * s
        d, _ = nk_fit(cur[inl], n[inl])
        trial = apply_shift_dh(cur, n, d)
        mt, st = nmad(trial)
        accept = st < s_prev
        rec["iterations"].append(dict(it=it, step=d.tolist(), nmad_before=s_prev, nmad_after=st, accepted=bool(accept)))
        if not accept:
            break
        cur = trial; total += d; s_prev = st
        if np.linalg.norm(d) < cfg["stop_increment_m"]:
            break
    rec["shift_xy"] = total.tolist(); rec["nmad_end"] = s_prev
    return rec


def tile_check(samples, cfg_reg, tile_m, origin_local):
    """per 80 m tile: own Nuth-Kaab shift and NMAD before / after (observation only)."""
    out = []
    X, dh, n = samples["xy"], samples["dh"], samples["n"]
    ti = np.floor((X[:, 0] - origin_local[0]) / tile_m).astype(int); tj = np.floor((X[:, 1] - origin_local[1]) / tile_m).astype(int)
    for (a, b) in sorted(set(zip(ti.tolist(), tj.tolist()))):
        m = (ti == a) & (tj == b)
        if m.sum() < 500:
            continue
        r = nuth_kaab(dh[m], n[m], cfg_reg)
        after = apply_shift_dh(dh[m], n[m], np.array(r["shift_xy"]))
        out.append(dict(tile=[a, b], centre_local=[origin_local[0] + (a + 0.5) * tile_m, origin_local[1] + (b + 0.5) * tile_m],
                        n=int(m.sum()), shift_xy=r["shift_xy"], estimable=r["horizontal_estimable"],
                        nmad_before=nmad(dh[m])[1], nmad_after_own=nmad(after)[1]))
    return out


# ------------------------------------------------------------------------------------------------ main
def run(range_id, prior_name, views, mvs_dir, mesh_dir, D, fig_n=8, tile=False, fix=None):
    t_all = time.time()
    D.mkdir(parents=True, exist_ok=True)
    rngs = json.loads((OUT / "step01/ranges.json").read_text())
    rng = rngs[range_id] if range_id in rngs else json.loads((mesh_dir / "range.json").read_text())
    V = Views()
    pr = Prior(mesh_dir, prior_name)
    st = pr.store; L = len(st["loc_area"])
    loc_in = inside_range(st["loc_center"][:, :2], rng)
    reg_cfg = CFG["registration"]
    timings = {}
    # footprint raster (reporting unit only): LoD2 GroundSurface polygons, 0.25 m
    fpj = json.loads((OUT / "step02" / "_footprints.json").read_text()) if (OUT / "step02" / "_footprints.json").exists() else None
    P = range_polygon(rng)

    have = [n for n in views if (Path(mvs_dir) / "stereo/depth_maps" / f"{n}.geometric.bin").exists()]
    dropped_views = sorted(set(views) - set(have))      # COLMAP skips images without source images: recorded, not used
    views = have

    def depth_of(n):
        p = Path(mvs_dir) / "stereo/depth_maps" / f"{n}.geometric.bin"
        d = read_depth_bin(p)
        assert d.shape == (GRID_H, GRID_W), (n, d.shape)
        return d

    def pixel_terms(scene, n, keep_maps=False):
        Dr = V.rays(n); C = V.C(n)
        t, tri = scene.cast(C, Dr)
        dm = depth_of(n)
        a1 = np.isfinite(dm) & (dm > 0)
        hit = tri >= 0
        idx = np.nonzero(hit.ravel())[0]
        trif = tri.ravel()[idx]
        d = Dr.reshape(-1, 3)[idx].astype(np.float64)
        nn = pr.n_used[trif]
        f = conv.factor(nn, d)
        r = (dm.ravel()[idx].astype(np.float64) - t.ravel()[idx]) * f
        return dict(idx=idx, tri=trif, d=d, n=nn, f=f, r=r, a1=a1.ravel()[idx], P=t.ravel()[idx], C=C, dm=dm, t=t, a1map=a1)

    # ---------------- pass 1: Nuth-Kaab samples ----------------------------------------------------
    t0 = time.time()
    sc, _ = pr.scene()
    S = dict(xy=[], dh=[], n=[], vert=[], vn=[])
    nmad_pool_before = []
    for n in views:
        q = pixel_terms(sc, n)
        bf = pr.bface_tri[q["tri"]] & q["a1"]
        nz = np.abs(q["n"][:, 2])
        X = q["C"][None, :] + q["P"][:, None] * q["d"]
        inr = inside_range(X[:, :2], rng)
        roof = bf & inr & (nz >= 0.5)
        fit = roof & (nz <= 0.9962)
        if fit.any():
            k = np.nonzero(fit)[0]
            if len(k) > 4000:
                k = RNG.choice(k, 4000, replace=False)
            # height difference h_MVS - h_prior = -r on roof-like faces seen from above (r < 0: MVS nearer the camera)
            S["xy"].append(X[k, :2]); S["dh"].append(-q["r"][k]); S["n"].append(q["n"][k] * np.sign(q["n"][k, 2:3]))
        kr = np.nonzero(roof)[0]
        if len(kr) > 4000:
            kr = RNG.choice(kr, 4000, replace=False)
        S["vert"].append(-q["r"][kr]); S["vn"].append(q["n"][kr] * np.sign(q["n"][kr, 2:3]))
        kb = np.nonzero(bf & inr)[0]
        if len(kb) > 4000:
            kb = RNG.choice(kb, 4000, replace=False)
        nmad_pool_before.append(q["r"][kb])
    S = {k: (np.concatenate(v) if v else np.zeros((0, 3) if k in ("n", "vn") else ((0, 2) if k == "xy" else 0))) for k, v in S.items()}
    timings["pass1_s"] = round(time.time() - t0, 1)
    # Nuth-Kaab steps proposed from the fit pixels (plane update); a step is accepted only when the NMAD of the
    # re-rendered height differences (roof-like confidence-1 building-face pixels, up to 40 training views) decreases
    gate_views = [views[int(i)] for i in np.unique(np.linspace(0, len(views) - 1, min(40, len(views))).round().astype(int))]

    def gate(shift, pred=None, gviews=None):
        pr.shift = np.asarray(shift, np.float64); scg, _ = pr.scene()
        vals = []
        for n in (gviews or gate_views):
            q = pixel_terms(scg, n)
            X = q["C"][None, :] + q["P"][:, None] * q["d"]
            m_ = pr.bface_tri[q["tri"]] & q["a1"] & inside_range(X[:, :2], rng) & (np.abs(q["n"][:, 2]) >= 0.5)
            if pred is not None:
                m_ &= pred(X[:, :2])
            k = np.nonzero(m_)[0]
            if len(k) > 20000:
                k = RNG.choice(k, 20000, replace=False)
            vals.append(-q["r"][k])
        v = np.concatenate(vals) if vals else np.zeros(0)
        return nmad(v)
    reg = dict(iterations=[], n_fit=int(len(S["dh"])), gate_views=len(gate_views))
    asp = np.arctan2(S["n"][:, 0], S["n"][:, 1]) if len(S["dh"]) else np.zeros(0)
    est, share = estimable(asp, reg_cfg)
    reg["horizontal_estimable"] = est; reg["aspect_quadrant_share"] = share
    cur = np.zeros(2)
    m_cur, s_cur = gate([0.0, 0.0, 0.0])
    reg["gate_start"] = dict(median=m_cur, nmad=s_cur)
    if est:
        for it in range(reg_cfg["iterations_max"]):
            dhc = apply_shift_dh(S["dh"], S["n"], cur)
            m_, s_ = nmad(dhc)
            inl = np.abs(dhc - m_) <= 3 * s_
            d, _ = nk_fit(dhc[inl], S["n"][inl])
            mt, st_ = gate([cur[0] + d[0], cur[1] + d[1], 0.0])
            acc_ = bool(st_ < s_cur)
            reg["iterations"].append(dict(it=it, step=d.tolist(), gate_nmad_before=s_cur, gate_nmad_after=st_, accepted=acc_))
            if not acc_:
                break
            cur = cur + d; m_cur, s_cur = mt, st_
            if np.linalg.norm(d) < reg_cfg["stop_increment_m"]:
                break
    dxy = cur
    reg["shift_xy"] = dxy.tolist()
    m_h, s_h = gate([dxy[0], dxy[1], 0.0])
    dz = float(m_h) if (np.isfinite(m_h) and abs(m_h) > s_h) else 0.0
    reg.update(vertical_rule="median of the re-rendered height differences (gate views, roof-like confidence-1 building-face pixels) after the horizontal shift, applied when |median| > NMAD",
               median_after_horizontal=m_h, nmad_after_horizontal=s_h, shift_z=dz)
    pool_b = np.concatenate(nmad_pool_before) if nmad_pool_before else np.zeros(0)
    reg["building_face_nmad_unregistered"] = nmad(pool_b)[1]
    if tile:   # observation only: the same gated estimator inside each 80 m tile (5 steps, 20 gate views)
        org = np.array(global_to_local(*reg_cfg["tile_check"].get("origin_epsg25832", [690700.0, 5335820.0])))
        tm = reg_cfg["tile_check"]["tile_m"]
        ti = np.floor((S["xy"][:, 0] - org[0]) / tm).astype(int); tj = np.floor((S["xy"][:, 1] - org[1]) / tm).astype(int)
        gv20 = [views[int(i)] for i in np.unique(np.linspace(0, len(views) - 1, min(20, len(views))).round().astype(int))]
        tiles = []
        for (ta, tb) in sorted(set(zip(ti.tolist(), tj.tolist()))):
            msk = (ti == ta) & (tj == tb)
            if msk.sum() < 2000:
                continue
            x0, y0 = org[0] + ta * tm, org[1] + tb * tm
            pred = lambda XY, x0=x0, y0=y0: (XY[:, 0] >= x0) & (XY[:, 0] < x0 + tm) & (XY[:, 1] >= y0) & (XY[:, 1] < y0 + tm)
            dh_t, n_t = S["dh"][msk], S["n"][msk]
            est_t, _ = estimable(np.arctan2(n_t[:, 0], n_t[:, 1]), reg_cfg)
            ct = dxy.copy()
            m0_, s0_ = gate([ct[0], ct[1], 0.0], pred, gv20)
            mz, sz = m0_, s0_
            steps = []
            if est_t:
                for it in range(5):
                    dhc = apply_shift_dh(dh_t, n_t, ct)
                    mm_, ss_ = nmad(dhc); inl = np.abs(dhc - mm_) <= 3 * ss_
                    d, _ = nk_fit(dhc[inl], n_t[inl])
                    mt, st_ = gate([ct[0] + d[0], ct[1] + d[1], 0.0], pred, gv20)
                    steps.append(dict(step=d.tolist(), nmad_after=st_, accepted=bool(st_ < sz)))
                    if st_ >= sz:
                        break
                    ct = ct + d; mz, sz = mt, st_
                    if np.linalg.norm(d) < reg_cfg["stop_increment_m"]:
                        break
            tiles.append(dict(tile=[ta, tb], centre_local=[x0 + tm / 2, y0 + tm / 2], fit_pixels=int(msk.sum()), estimable=est_t,
                              shift_xy_tile=ct.tolist(), shift_minus_range=(ct - dxy).tolist(), nmad_with_range_shift=s0_, nmad_with_tile_shift=sz,
                              median_with_tile_shift=mz, steps=steps))
        reg["tiles"] = tiles
    np.savez_compressed(D / "nk_samples.npz", **{k: v.astype(np.float32) for k, v in S.items()})
    # apply, re-render, accept only if the building-face NMAD decreases
    cand = np.array([dxy[0], dxy[1], dz])
    pr.shift = cand
    sc, _ = pr.scene()

    # ---------------- pass 2: tolerance ------------------------------------------------------------
    def pass2(sc):
        samp = {conv.KIND_ROOF: [], conv.KIND_WALL: []}; pool = []
        for n in views:
            q = pixel_terms(sc, n)
            bf = pr.bface_tri[q["tri"]] & q["a1"]
            X = q["C"][None, :] + q["P"][:, None] * q["d"]
            inr = inside_range(X[:, :2], rng)
            kind = conv.surface_kind(q["n"][:, 2])
            for k in samp:
                sel = np.nonzero(bf & inr & (kind == k))[0]
                if len(sel) > 20000:
                    sel = RNG.choice(sel, 20000, replace=False)
                samp[k].append(q["r"][sel])
            kb = np.nonzero(bf & inr)[0]
            if len(kb) > 4000:
                kb = RNG.choice(kb, 4000, replace=False)
            pool.append(q["r"][kb])
        return samp, (np.concatenate(pool) if pool else np.zeros(0))
    t0 = time.time()
    samp, pool_a = pass2(sc)
    reg["building_face_nmad_registered"] = nmad(pool_a)[1]
    # fix 4 (rev 3): final check of 4.1 'NMAD decreases' on every view and every confidence-1 building-face pixel
    # (roof-like vertical and wall normal residuals); the roof-like gate views alone barely react to horizontal shifts
    # on flat roofs (R3E LoD2: gate 0.074 -> 0.072 m while all building faces 0.100 -> 0.194 m)
    reg["final_check"] = dict(rule="horizontal shift kept only when the all-view building-face NMAD decreases",
                              nmad_before=reg["building_face_nmad_unregistered"], nmad_after=reg["building_face_nmad_registered"],
                              horizontal_proposed=dxy.tolist(), passed=True)
    if np.linalg.norm(dxy) > 0 and not (reg["building_face_nmad_registered"] < reg["building_face_nmad_unregistered"]):
        reg["final_check"]["passed"] = False
        dxy = np.zeros(2)
        m_h, s_h = gate([0.0, 0.0, 0.0])
        dz = float(m_h) if (np.isfinite(m_h) and abs(m_h) > s_h) else 0.0
        reg.update(shift_xy=dxy.tolist(), median_after_horizontal=m_h, nmad_after_horizontal=s_h, shift_z=dz)
        cand = np.array([0.0, 0.0, dz])
        pr.shift = cand
        sc, _ = pr.scene()
        samp, pool_a = pass2(sc)
        reg["building_face_nmad_registered"] = nmad(pool_a)[1]
        reg["final_check"]["nmad_after_rejection"] = reg["building_face_nmad_registered"]
    timings["pass2_s"] = round(time.time() - t0, 1)
    reg["accepted_horizontal"] = bool(np.linalg.norm(dxy) > 0)
    reg["accepted_vertical"] = bool(dz != 0.0)
    reg["accepted"] = bool(np.any(cand != 0))
    reg["acceptance_rule"] = "config v2: horizontal Nuth-Kaab steps (proposed on the fit pixels) accepted only when the NMAD of the re-rendered height differences on the gate views decreases; the final horizontal shift kept only when the all-view building-face NMAD decreases (fix 4); vertical by the median rule on the re-rendered gate views"
    reg["shift_applied"] = pr.shift.tolist()
    roof_x = np.concatenate(samp[conv.KIND_ROOF]) if samp[conv.KIND_ROOF] else np.zeros(0)
    wall_x = np.concatenate(samp[conv.KIND_WALL]) if samp[conv.KIND_WALL] else np.zeros(0)
    spec = CFG["priors"]["spec_m"][prior_name]
    roof_st = tol.robust_width(roof_x); wall_st = tol.robust_width(wall_x)
    roof_t = tol.tolerance(roof_st, spec["roof"], "agency spec (configs prep_v2 = v1)")
    if prior_name == "LoD2" and wall_st["n"] >= CFG["tolerance"]["wall_min_pixels"]:
        wall_t = tol.tolerance(wall_st, spec["wall"], "no agency wall spec")
    else:
        wall_t = tol.tolerance(dict(width=None), spec["wall"], "no agency wall spec", fallback=roof_t)
        wall_t["side"] = "roof value (walls are not TIN surfaces)" if prior_name == "ALS" else f"roof value (wall pixels {wall_st['n']} < {CFG['tolerance']['wall_min_pixels']})"
    TAU = {conv.KIND_ROOF: roof_t["tau"], conv.KIND_WALL: wall_t["tau"]}
    np.savez_compressed(D / "residual_samples.npz", roof=roof_x.astype(np.float32), wall=wall_x.astype(np.float32))
    fixed_info = None
    if fix:   # user decision 23:02 (config v3 boxes.user_decision_2302): tolerance and registration fixed from the search range
        fs = json.loads((OUT / fix / prior_name / "summary.json").read_text())
        fixed_info = dict(fixed_from=f"{fix}/{prior_name}", tolerance_box=dict(roof=roof_t, wall=wall_t), registration_box=dict(reg),
                          note="judgments use the fixed values; the box's own values on its MVS are recorded here for comparison")
        pr.shift = np.asarray(fs["registration"]["shift_applied"], np.float64)
        sc, _ = pr.scene()
        roof_t = dict(fs["tolerance"]["roof"]); wall_t = dict(fs["tolerance"]["wall"])
        TAU = {conv.KIND_ROOF: roof_t["tau"], conv.KIND_WALL: wall_t["tau"]}
        reg = dict(fixed_from=f"{fix}/{prior_name}", shift_applied=pr.shift.tolist(), horizontal_estimable=fs["registration"].get("horizontal_estimable"),
                   building_face_nmad_unregistered=reg.get("building_face_nmad_unregistered"), building_face_nmad_registered=reg.get("building_face_nmad_registered"),
                   final_check=fs["registration"].get("final_check"), accepted_horizontal=fs["registration"].get("accepted_horizontal"),
                   accepted_vertical=fs["registration"].get("accepted_vertical"))
    # ---------------- pass 3: marks, coverage, units, gaps --------------------------------------------
    t0 = time.time()
    if prior_name == "LoD2":
        sc_b, nb = pr.scene(with_caps=False, with_probe=True)
        sc_a, na_ = pr.scene(with_caps=True, with_probe=True)
    fp = json.loads((mesh_dir / "footprints.json").read_text())
    rect = np.asarray(st["rect"], np.float64); fsp = 0.25
    fni = int(np.ceil((rect[1, 0] - rect[0, 0]) / fsp)); fnj = int(np.ceil((rect[1, 1] - rect[0, 1]) / fsp))
    fras = np.full((fni, fnj), -1, np.int32)
    for k, r in enumerate(fp["footprints"]):
        ring = np.asarray(r["ring_local"]); lo = np.floor((ring.min(0) - rect[0]) / fsp).astype(int); hi = np.ceil((ring.max(0) - rect[0]) / fsp).astype(int)
        lo = np.maximum(lo, 0); hi = np.minimum(hi, [fni, fnj])
        if np.any(hi <= lo):
            continue
        gx, gy = np.meshgrid(rect[0, 0] + (np.arange(lo[0], hi[0]) + 0.5) * fsp, rect[0, 1] + (np.arange(lo[1], hi[1]) + 0.5) * fsp, indexing="ij")
        inside = MPath(ring).contains_points(np.stack([gx.ravel(), gy.ravel()], 1)).reshape(gx.shape)
        sub = fras[lo[0]:hi[0], lo[1]:hi[1]]; sub[inside] = k
    NF = len(fp["footprints"])
    fp_acc = {k: np.zeros(NF, np.int64) for k in ("px", "a1", "ag", "cf", "roof_px", "roof_a1", "roof_cf", "wall_px", "wall_a1", "wall_cf")}
    acc = dict(n_seeing=np.zeros(L, np.int32), n_supporting=np.zeros(L, np.int32), agree_views=np.zeros(L, np.int32),
               conflict_views=np.zeros(L, np.int32), pix_sum=np.zeros(L, np.int64), a1_sum=np.zeros(L, np.int64),
               agree_sum=np.zeros(L, np.int64), conflict_sum=np.zeros(L, np.int64))
    pairs_v, pairs_l, pairs_np, pairs_na = [], [], [], []
    per_view = []; per_surface = {}; gaps = []
    nofig = sorted(views, key=lambda v: V.tilt(v))
    figsel = set(nofig[:fig_n // 2] + nofig[-(fig_n - fig_n // 2):]) if fig_n else set()
    (D / "figviews").mkdir(exist_ok=True)
    nounit = dict(prior_px=0, a0_inherit=0, a1_agree=0, a1_conflict=0)
    surf_rows = {}
    for vi, n in enumerate(views):
        q = pixel_terms(sc, n)
        bf = pr.bface_tri[q["tri"]]
        kind = conv.surface_kind(q["n"][:, 2])
        tau_px = np.where(bf, np.where(kind == conv.KIND_ROOF, TAU[1], TAU[2]), TAU[1])
        a1 = q["a1"]; ar = np.abs(q["r"])
        ag = a1 & (ar <= tau_px); cf = a1 & ~(ar <= tau_px)
        X = q["C"][None, :] + q["P"][:, None] * q["d"]
        inr = inside_range(X[:, :2], rng)
        ci = pr.ci_of_tri[q["tri"]]
        okl = ci >= 0
        loc = np.full(len(ci), -1, np.int64)
        if okl.any():
            loc[okl] = locs.locate(st, ci[okl], X[okl])
        # sparse per-view unit counts
        lv = loc[okl]
        if len(lv):
            u, inv = np.unique(lv, return_inverse=True)
            npx = np.bincount(inv); na1 = np.bincount(inv, weights=a1[okl]).astype(np.int64)
            nag = np.bincount(inv, weights=ag[okl]).astype(np.int64); ncf = np.bincount(inv, weights=cf[okl]).astype(np.int64)
            supporting = 2 * na1 >= npx; mark_ag = nag >= ncf
            acc["n_seeing"][u] += 1; acc["n_supporting"][u] += supporting
            acc["agree_views"][u] += supporting & mark_ag; acc["conflict_views"][u] += supporting & ~mark_ag
            acc["pix_sum"][u] += npx; acc["a1_sum"][u] += na1; acc["agree_sum"][u] += nag; acc["conflict_sum"][u] += ncf
            pairs_v.append(np.full(len(u), vi, np.int32)); pairs_l.append(u.astype(np.int32))
            pairs_np.append(npx.astype(np.int32)); pairs_na.append(na1.astype(np.int32))
        # pixels without a unit (ground, steep TIN triangles, caps, non-building TIN): own judgment
        nl = ~okl & inr
        nounit["prior_px"] += int(nl.sum()); nounit["a0_inherit"] += int((nl & ~a1).sum())
        nounit["a1_agree"] += int((nl & ag).sum()); nounit["a1_conflict"] += int((nl & cf).sum())
        bfi = bf & inr
        rec = dict(view=n, tilt=round(V.tilt(n), 2), building_px=int(bfi.sum()), a1_px=int((bfi & a1).sum()),
                   agree_px=int((bfi & ag).sum()), conflict_px=int((bfi & cf).sum()),
                   roof_px=int((bfi & (kind == 1)).sum()), roof_a1_px=int((bfi & (kind == 1) & a1).sum()),
                   roof_agree_px=int((bfi & (kind == 1) & ag).sum()), roof_conflict_px=int((bfi & (kind == 1) & cf).sum()),
                   wall_px=int((bfi & (kind == 2)).sum()), wall_a1_px=int((bfi & (kind == 2) & a1).sum()),
                   wall_agree_px=int((bfi & (kind == 2) & ag).sum()), wall_conflict_px=int((bfi & (kind == 2) & cf).sum()))
        # per footprint (LoD2 GroundSurface as reporting unit only)
        ii = np.clip(np.floor((X[:, 0] - rect[0, 0]) / fsp).astype(int), 0, fni - 1); jj = np.clip(np.floor((X[:, 1] - rect[0, 1]) / fsp).astype(int), 0, fnj - 1)
        fid = fras[ii, jj]
        fs = bfi & (fid >= 0)
        if fs.any():
            ff = fid[fs]
            for key, arr in (("px", np.ones(fs.sum())), ("a1", a1[fs]), ("ag", ag[fs]), ("cf", cf[fs]),
                             ("roof_px", kind[fs] == 1), ("roof_a1", (kind[fs] == 1) & a1[fs]), ("roof_cf", (kind[fs] == 1) & cf[fs]),
                             ("wall_px", kind[fs] == 2), ("wall_a1", (kind[fs] == 2) & a1[fs]), ("wall_cf", (kind[fs] == 2) & cf[fs])):
                fp_acc[key] += np.bincount(ff, weights=arr, minlength=NF).astype(np.int64)
        # per surface (ext) counts
        se = pr.tri_surface[q["tri"]]
        sel = bfi & (se >= 0)
        if sel.any():
            keyv = se[sel]
            uu, iv = np.unique(keyv, return_inverse=True)
            for arr_name, arr in (("px", np.ones(sel.sum())), ("a1", a1[sel]), ("ag", ag[sel]), ("cf", cf[sel])):
                c = np.bincount(iv, weights=arr)
                for s_, v_ in zip(uu.tolist(), c.tolist()):
                    surf_rows.setdefault(s_, dict(px=0, a1=0, ag=0, cf=0))[arr_name] += int(v_)
        # gap probes (LoD2): first hit on a probe face = a ray that enters a party-wall gap
        if prior_name == "LoD2" and len(pr.PF):
            Dr = V.rays(n); C = V.C(n)
            tbt, tb = sc_b.cast(C, Dr); tat, ta = sc_a.cast(C, Dr)
            rec_g = dict(view=n, before=int((tb >= nb).sum()), after=int((ta >= na_).sum()))
            if rec_g["after"]:
                k = np.nonzero((ta >= na_).ravel())[0]
                Xh = C[None, :] + tat.ravel()[k, None] * Dr.reshape(-1, 3)[k].astype(np.float64)
                rec_g["after_points"] = Xh.round(3).tolist(); rec_g["after_overlap"] = pr.probe_overlap[ta.ravel()[k] - na_].tolist()
            gaps.append(rec_g)
        if n in figsel:
            H, W = GRID_H, GRID_W
            mk = np.full(H * W, rule.MARK_NONE, np.int8); mk[q["idx"][ag]] = rule.MARK_AGREE; mk[q["idx"][cf]] = rule.MARK_CONFLICT
            lm = np.full(H * W, -1, np.int32); lm[q["idx"]] = loc
            np.savez_compressed(D / "figviews" / f"{n}.npz", mark=mk.reshape(H, W), loc=lm.reshape(H, W), a1=q["a1map"],
                                prior_depth=q["t"].astype(np.float32), mvs_depth=q["dm"].astype(np.float32))
        per_view.append(rec)
        if vi % 100 == 0:
            log(range_id, prior_name, "pass3", vi, len(views))
    timings["pass3_s"] = round(time.time() - t0, 1)
    # ---------------- unit states and judgments -----------------------------------------------------
    t0 = time.time()
    ns, nsp = acc["n_seeing"], acc["n_supporting"]
    state = np.full(L, rule.ST_INVISIBLE, np.int8)
    state[(ns > 0) & (2 * nsp >= ns)] = rule.ST_SUPPORT
    state[(ns > 0) & (2 * nsp < ns)] = rule.ST_MISSING
    vote = np.where(acc["conflict_views"] > acc["agree_views"], rule.V_CONFLICT, rule.V_AGREE).astype(np.int8)
    vote[state != rule.ST_SUPPORT] = rule.V_NONE
    E = np.where(ns > 0, nsp / np.maximum(ns, 1), 0.0)
    jc = CFG["judgment"]
    J, (mis, kd, kv) = locs.propagate(st, state, vote, jc["majority"], jc["min_evidence"], jc["max_distance_m"])
    J_loc = locs.location_judgment(state, vote, J)
    why = rule.undetermined_why(state, J, kd, mis, jc["min_evidence"], jc["max_distance_m"])
    timings["judgment_s"] = round(time.time() - t0, 1)
    out = dict(st)
    out.update(state=state, vote=vote, E=E, J=J, J_loc=J_loc, why=why, loc_in_range=loc_in, **acc)
    locs.save_store(D / "units.npz", out)
    pv = np.concatenate(pairs_v) if pairs_v else np.zeros(0, np.int32)
    np.savez_compressed(D / "unit_view_pairs.npz", view=pv, loc=np.concatenate(pairs_l) if pairs_l else np.zeros(0, np.int32),
                        npix=np.concatenate(pairs_np) if pairs_np else np.zeros(0, np.int32),
                        na1=np.concatenate(pairs_na) if pairs_na else np.zeros(0, np.int32), views=np.array(views))
    # unplanted points
    unpl = {}
    if prior_name == "ALS":
        Vv = pr.V0 + pr.shift
        eligible = np.zeros(int(pr.tri_surface.max()) + 2, bool)
        for e in pr.table:
            eligible[e] = True
        vs = surf.vertex_surface(pr.F, pr.tri_surface, eligible)
        ci = np.where(vs >= 0, locs.compact_index(st, np.maximum(vs, 0)), -1)
        has = ci >= 0
        seat = np.full(len(Vv), -1, np.int64)
        seat[has] = locs.locate(st, ci[has], Vv[has])
        bad = has & (J_loc[np.maximum(seat, 0)] == rule.J_CONFLICT) & (state[np.maximum(seat, 0)] == rule.ST_MISSING)
        inr = inside_range(Vv[:, :2], rng)
        unpl = dict(points=int(inr.sum()), points_seated=int((has & inr).sum()), points_unseated=int((~has & inr).sum()),
                    unplanted=int((bad & inr).sum()), unplanted_ground_class2=int((bad & inr & (pr.cls == 2)).sum()))
        np.save(D / "unplanted_point_index.npy", np.nonzero(bad & inr)[0].astype(np.int32))
        # 5.7: cell-method initial directions (r10 fork orient_prior, offline): seated points with a cell take t1 x t2 of
        # their cell signed like the vertex normal; others keep the vertex normal
        vn, vn_rule = ori.tin_vertex_normals(Vv, pr.F, pr.tri_surface, vs)
        cell_n = np.cross(st["loc_t1"], st["loc_t2"]); cn = np.linalg.norm(cell_n, axis=1)
        cell_n = np.where(cn[:, None] > 1e-9, cell_n / np.maximum(cn, 1e-12)[:, None], 0)
        cok = has & (cn[np.maximum(seat, 0)] > 1e-9)
        c = cell_n[np.maximum(seat, 0)][cok]
        ref = vn[cok]
        sgn = np.where(np.isfinite(ref).all(1), (c * np.nan_to_num(ref)).sum(1), c[:, 2])
        c = np.where((sgn < 0)[:, None], -c, c)
        q4 = ori.quat_from_normal(c); nq = ori.normal_of_quat(q4)
        ang_q = np.degrees(np.arctan2(np.linalg.norm(np.cross(nq, c), axis=1), np.clip((nq * c).sum(1), -1, 1)))
        okv = np.isfinite(ref).all(1)
        ang_v = np.degrees(np.arctan2(np.linalg.norm(np.cross(c[okv], ref[okv]), axis=1), np.abs((c[okv] * ref[okv]).sum(1))))
        unpl["orientation_cell_method"] = dict(points_with_cell=int((cok & inr).sum()), points_without_patch=int((~cok & inr).sum()),
                                               angle_initial_vs_patch_face_deg=dict(p50=float(np.median(ang_q)), p99=float(np.quantile(ang_q, 0.99)), max=float(ang_q.max())),
                                               angle_vertex_vs_patch_face_deg=dict(p50=float(np.median(ang_v)), p95=float(np.quantile(ang_v, 0.95)), max=float(ang_v.max())))
        np.savez_compressed(D / "orientation_angles.npz", initial_vs_face=ang_q.astype(np.float32), vertex_vs_face=ang_v.astype(np.float32))
    else:
        bad = (state == rule.ST_MISSING) & (J_loc == rule.J_CONFLICT) & loc_in
        unpl = dict(patches=int(loc_in.sum()), unplanted_patches=int(bad.sum()), unplanted_area_m2=float(st["loc_area"][bad].sum()),
                    note="LoD2 points = one sample per patch centre")
    # summaries
    inr_l = loc_in
    def cnt(mask):
        return dict(units=int(mask.sum()), area_m2=float(st["loc_area"][mask].sum()))
    kinds = st["loc_kind"]
    summ = dict(range=range_id, prior=prior_name, views=len(views), views_without_depth_map=dropped_views, mvs=str(mvs_dir), fixed=fixed_info, tolerance=dict(roof=roof_t, wall=wall_t),
                registration=reg, timings=timings, pixels_without_unit=nounit, unplanted=unpl,
                states={nm: {k: cnt(inr_l & (state == code) & (kinds == kk)) for k, kk in (("roof", 1), ("wall", 2))}
                        for nm, code in (("support", rule.ST_SUPPORT), ("missing", rule.ST_MISSING), ("invisible", rule.ST_INVISIBLE))},
                support_vote={nm: cnt(inr_l & (state == rule.ST_SUPPORT) & (vote == v)) for nm, v in (("agree", rule.V_AGREE), ("conflict", rule.V_CONFLICT))},
                missing_judgment={nm: cnt(inr_l & (state == rule.ST_MISSING) & (J == j)) for j, nm in rule.J_NAMES.items()},
                gaps=dict(before=int(sum(g["before"] for g in gaps)), after=int(sum(g["after"] for g in gaps)), views_with_before=int(sum(g["before"] > 0 for g in gaps))) if gaps else None)
    jdump(D / "summary.json", summ)
    jdump(D / "coverage_views.json", per_view)
    jdump(D / "coverage_surfaces.json", {str(k): v for k, v in surf_rows.items()})
    jdump(D / "coverage_footprints.json", [dict(building=fp["footprints"][k]["building"], inside_range=fp["footprints"][k]["inside_share"],
                                                 **{key: int(v[k]) for key, v in fp_acc.items()}) for k in range(NF)])
    if gaps:
        jdump(D / "gaps.json", gaps)
    log(range_id, prior_name, "done", round(time.time() - t_all), "s", "tau", round(TAU[1], 4), round(TAU[2], 4), "shift", np.round(pr.shift, 3),
        "accepted", reg.get("accepted", reg.get("fixed_from")), "states", {k: v["roof"]["units"] + v["wall"]["units"] for k, v in summ["states"].items()})
    return summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("range_id"); ap.add_argument("prior", choices=["LoD2", "ALS"])
    ap.add_argument("--views-key", default="train"); ap.add_argument("--views-file", default="step01/views.json")
    ap.add_argument("--views-list", default=None, help="json file with a list of view names (overrides views-file)")
    ap.add_argument("--mesh-sub", default="step02"); ap.add_argument("--mvs", default="current")
    ap.add_argument("--out-sub", default="step03"); ap.add_argument("--fig-views", type=int, default=8)
    ap.add_argument("--tile", action="store_true")
    ap.add_argument("--fix-from", default=None, help="stage-1 dir under /out (e.g. step03/B0) whose <prior>/summary.json gives the fixed tolerance and registration")
    a = ap.parse_args()
    if a.views_list:
        views = json.loads((OUT / a.views_list).read_text())
    else:
        views = json.loads((OUT / a.views_file).read_text())["views"][a.range_id][a.views_key]
    mvs_dir = DENSE if a.mvs == "current" else OUT / a.mvs
    D = OUT / a.out_sub / a.range_id / a.prior
    run(a.range_id, a.prior, views, mvs_dir, OUT / a.mesh_sub / a.range_id, D, a.fig_views, a.tile, a.fix_from)


if __name__ == "__main__":
    main()
