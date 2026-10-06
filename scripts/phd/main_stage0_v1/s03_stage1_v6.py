"""PHD-MAIN-STAGE0-v1 s03 v6 (jointbuildgs:dev, CPU): stage 1 and the pre-training judgment of one range / box and prior =
the discard task's s03_stage1.py (module v5) with the shared module prior_propagation_v6 and its two changes:
  store fix     after the registration the patch store is moved with the prior (locations.move_store): every lookup of a
                point of the registered prior (pass-3 ray hits, unplanted points) uses the moved store; v5 used the store
                of the unmoved prior (v5's diagnostic option that took the shift back = this rule; the option is gone).
                loc_in_range uses the moved centres; the footprint raster (reporting only) keeps the unmoved crop rectangle
  rule default  --rule auto (default) = rules.default_rule(prior): LoD2 current, ALS margin_all_2. state / vote / J / J_loc /
                why / unplanted points of units.npz follow the rule; the current rule's votes and judgments are kept as
                vote_tau / J_tau / J_loc_tau (the fork store reads them, the comparisons too)
New output (agreement regions, 5.3): per patch the median of the signed residual r over its confidence-1 pixels in its
supporting views (mvs_r_med, count mvs_r_n); MVS - prior along the outward normal / up = -mvs_r_med.

  python s03_stage1_v6.py <range_id> <LoD2|ALS> [--views-file /prep/step01/views.json] [--views-list f] [--mesh-sub s02]
         [--mvs current|<workspace>] [--out-sub s03] [--fig-views 8] [--tile] [--fix-from <stage-1 dir>]
         [--conf geometric|photometric] [--export-fork <dir>] [--rule auto|<name>]

Pass 1  render the prior at every view (native 1024 x 741 grid), residuals of confidence-1 pixels -> Nuth-Kaab samples
Reg.    registration.gated_horizontal / vertical_shift / final_check_fails (prep config v2 rules)
Pass 2  re-render the registered prior -> tolerance per kind (2.5 NMAD after one 3-NMAD clip; wall fallback)
Pass 3  re-render -> marks, coverage tables, judgment-unit counts (tallies.view_counts), gap probe counts (LoD2), the
        per-patch residual samples of the supporting views
Then    unit states, votes, propagation (2/3, 5, 1 m), the gathered support ids (knn.npz), the rule, unplanted points,
        ALS cell-method initial directions. Confidence mask = r10: valid COLMAP geometric depth (--conf photometric =
        the confidence-mask switch off). scientific_verdict: null."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath

from common import (CFG, DENSE, OUT, PREP, GRID_H, GRID_W, Scene, Views, global_to_local, inside_range, jdump, log,
                    range_polygon, read_depth_bin)
from src.phd.prior_propagation_v6 import conversion as conv
from src.phd.prior_propagation_v6 import locations as locs
from src.phd.prior_propagation_v6 import orientation as ori
from src.phd.prior_propagation_v6 import registration as regm
from src.phd.prior_propagation_v6 import rule
from src.phd.prior_propagation_v6 import rules as rls
from src.phd.prior_propagation_v6 import surfaces as surf
from src.phd.prior_propagation_v6 import tallies as tly
from src.phd.prior_propagation_v6 import tolerance as tol

T_ROOF, T_WALL, T_CAP = 0, 1, 2
RNG = np.random.default_rng(0)


nmad = regm.nmad


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


# ------------------------------------------------------------------------------------------------ registration (prior_propagation_v5)
nk_fit, apply_shift_dh, estimable, nuth_kaab = regm.nk_fit, regm.apply_shift_dh, regm.estimable, regm.nuth_kaab


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
def run(range_id, prior_name, views, mvs_dir, mesh_dir, D, fig_n=8, tile=False, fix=None, conf="geometric", export=None, rule_arg="auto"):
    t_all = time.time()
    D.mkdir(parents=True, exist_ok=True)
    rngs = json.loads((PREP / "step01/ranges.json").read_text())
    rng = rngs[range_id] if range_id in rngs else json.loads((mesh_dir / "range.json").read_text())
    V = Views()
    pr = Prior(mesh_dir, prior_name)
    st0 = pr.store; L = len(st0["loc_area"])          # v6: the store of the unmoved prior; moved after the registration
    rule_name = rls.resolve(rule_arg, prior_name)
    reg_cfg = CFG["registration"]
    timings = {}
    # footprint raster (reporting unit only): LoD2 GroundSurface polygons, 0.25 m
    P = range_polygon(rng)

    have = [n for n in views if (Path(mvs_dir) / "stereo/depth_maps" / f"{n}.geometric.bin").exists()]   # (both confidence modes: the geometric list)
    dropped_views = sorted(set(views) - set(have))      # COLMAP skips images without source images: recorded, not used
    views = have

    def depth_of(n):
        p = Path(mvs_dir) / "stereo/depth_maps" / f"{n}.{'photometric' if conf == 'photometric' else 'geometric'}.bin"
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
    dxy = regm.gated_horizontal(S, gate, reg_cfg, reg)
    reg["shift_xy"] = dxy.tolist()
    dz, m_h, s_h = regm.vertical_shift(gate, dxy)
    reg.update(vertical_rule=regm.VERTICAL_RULE, median_after_horizontal=m_h, nmad_after_horizontal=s_h, shift_z=dz)
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
    if regm.final_check_fails(dxy, reg["building_face_nmad_unregistered"], reg["building_face_nmad_registered"]):
        reg["final_check"]["passed"] = False
        dxy = np.zeros(2)
        dz, m_h, s_h = regm.vertical_shift(gate, dxy)
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
    reg["acceptance_rule"] = regm.ACCEPTANCE_RULE
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
    if fix:   # fixed tolerance and registration of another stage-1 run (prep user decision 23:02; this task 5.2)
        fdir = Path(fix) if str(fix).startswith("/") else OUT / fix
        fs = json.loads((fdir / prior_name / "summary.json").read_text())
        shift_f, roof_t, wall_t, reg, fixed_info = regm.fixed_from_summary(fs, prior_name, reg, roof_t, wall_t, str(fix))
        pr.shift = shift_f
        sc, _ = pr.scene()
        TAU = {conv.KIND_ROOF: roof_t["tau"], conv.KIND_WALL: wall_t["tau"]}
    # ---------------- pass 3: marks, coverage, units, gaps --------------------------------------------
    t0 = time.time()
    st = locs.move_store(st0, pr.shift)                # v6 store fix: the store moved with the registered prior
    loc_in = inside_range(st["loc_center"][:, :2], rng)
    if prior_name == "LoD2":
        sc_b, nb = pr.scene(with_caps=False, with_probe=True)
        sc_a, na_ = pr.scene(with_caps=True, with_probe=True)
    fp = json.loads((mesh_dir / "footprints.json").read_text())
    rect = np.asarray(st0["rect"], np.float64); fsp = 0.25          # reporting raster: the unmoved crop rectangle (as v5)
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
    acc = tly.new_acc(L)
    pairs_v, pairs_l, pairs_np, pairs_na, pairs_le = [], [], [], [], []
    rs_l, rs_r = [], []                                 # v6: signed residuals of the patches in their supporting views
    if export:
        EX = Path(export)
        for sub in ("conf", "mvs", "prior", "tau", "locmap", "markmap", "markcode"):
            (EX / sub).mkdir(parents=True, exist_ok=True)
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
        if okl.any():   # v6: the registered hit in the moved store
            loc[okl] = locs.locate(st, ci[okl], X[okl])
        # sparse per-view unit counts
        vc = tly.view_counts(loc, okl, a1, ag, cf, ar, tau_px)
        if vc is not None:
            u, npx, na1, nag, ncf, le = vc
            tly.accumulate(acc, u, npx, na1, nag, ncf)
            pairs_v.append(np.full(len(u), vi, np.int32)); pairs_l.append(u.astype(np.int32))
            pairs_np.append(npx.astype(np.int32)); pairs_na.append(na1.astype(np.int32)); pairs_le.append(le.astype(np.int32))
            sup_u = u[2 * na1 >= npx]                   # v6: units this view supports
            if len(sup_u):
                ks = np.nonzero(okl & a1)[0]
                ks = ks[np.isin(loc[ks], sup_u)]
                rs_l.append(loc[ks].astype(np.int32)); rs_r.append(q["r"][ks].astype(np.float32))
        if export:   # per-view maps of the training view for the fork (training resolution = this grid)
            H, W = GRID_H, GRID_W; stem = n.rsplit(".", 1)[0]
            np.save(EX / "conf" / f"{stem}.npy", q["a1map"].astype(np.float32))
            mv = np.where(q["a1map"], q["dm"], np.nan).astype(np.float32); np.save(EX / "mvs" / f"{stem}.npy", mv)
            pdp = np.where(np.isfinite(q["t"]), q["t"], np.nan).astype(np.float32); np.save(EX / "prior" / f"{stem}.npy", pdp)
            tm = np.full(H * W, np.nan, np.float32); tm[q["idx"]] = (tau_px / np.maximum(q["f"], 1e-3)).astype(np.float32)
            np.save(EX / "tau" / f"{stem}.npy", tm.reshape(H, W))
            lm_ = np.full(H * W, -1, np.int32); lm_[q["idx"]] = loc; np.save(EX / "locmap" / f"{stem}.npy", lm_.reshape(H, W))
            mk_ = np.full(H * W, rule.MARK_NONE, np.int32); mk_[q["idx"][ag]] = rule.MARK_AGREE; mk_[q["idx"][cf]] = rule.MARK_CONFLICT
            np.save(EX / "markmap" / f"{stem}.npy", mk_.reshape(H, W))
            code = np.full(len(a1), -1, np.int32)
            rr = ar / np.where(tau_px > 0, tau_px, np.nan)
            code[a1] = np.searchsorted(np.asarray(tly.THRESHOLDS), rr[a1], side="left")
            mc_ = np.full(H * W, -1, np.int32); mc_[q["idx"]] = code; np.save(EX / "markcode" / f"{stem}.npy", mc_.reshape(H, W))
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
    state, vote_tau, E = tly.unit_states(acc)
    jc = CFG["judgment"]
    G0 = locs.graph(st0)      # in-surface distances of the unmoved store (= v5's graph, bit for bit; the moved one differs by rounding only)
    J_tau, (mis, kd, kv) = locs.propagate(st, state, vote_tau, jc["majority"], jc["min_evidence"], jc["max_distance_m"], G=G0)
    J_loc_tau = locs.location_judgment(state, vote_tau, J_tau)
    mis2, kd2, kid2 = locs.k_nearest_support_ids(G0, st["loc_surface"], state, int(jc["min_evidence"]), float(jc["max_distance_m"]))
    np.savez_compressed(D / "knn.npz", mis=mis2.astype(np.int64), k_dist=kd2, k_id=kid2.astype(np.int64))
    kv2 = np.where(kid2 >= 0, vote_tau[np.maximum(kid2, 0)], rule.V_NONE)
    knn_check = dict(same_missing=bool(np.array_equal(mis, mis2)), same_dist=bool(np.array_equal(kd, kd2)), same_vote=bool(np.array_equal(kv, kv2)))
    pv = np.concatenate(pairs_v) if pairs_v else np.zeros(0, np.int32)
    pairs = dict(view=pv, loc=np.concatenate(pairs_l) if pairs_l else np.zeros(0, np.int32),
                 npix=np.concatenate(pairs_np) if pairs_np else np.zeros(0, np.int32),
                 na1=np.concatenate(pairs_na) if pairs_na else np.zeros(0, np.int32),
                 le=np.concatenate(pairs_le) if pairs_le else np.zeros((0, len(tly.THRESHOLDS)), np.int32))
    np.savez_compressed(D / "unit_view_pairs.npz", **pairs, views=np.array(views), thresholds=np.array(tly.THRESHOLDS))
    # v6: the rule of the run (default by the prior kind); the current rule's values are kept as *_tau
    q_, k_, r_ = jc["majority"], int(jc["min_evidence"]), float(jc["max_distance_m"])
    st_c, vote_c, J_c, _ = rls.apply(pairs, L, mis2, kd2, kid2, "current", q_, k_, r_)
    rule_check = dict(rule=rule_name, offline_current_equals_pass3=bool(np.array_equal(st_c, state) and np.array_equal(vote_c, vote_tau) and np.array_equal(J_c, J_tau)))
    if not rule_check["offline_current_equals_pass3"]:
        raise RuntimeError("the offline current rule does not reproduce the pass-3 states / votes / judgments")
    if rule_name == "current":
        vote, J = vote_tau, J_tau
    else:
        st_r, vote, J, _ = rls.apply(pairs, L, mis2, kd2, kid2, rule_name, q_, k_, r_)
        if not np.array_equal(st_r, state):
            raise RuntimeError("rule tallies give other states than the pass-3 counts")
    J_loc = locs.location_judgment(state, vote, J)
    why = rule.undetermined_why(state, J, kd, mis, jc["min_evidence"], jc["max_distance_m"])
    # v6: per patch the median signed residual of its confidence-1 pixels in its supporting views (agreement regions)
    rl = np.concatenate(rs_l) if rs_l else np.zeros(0, np.int32); rr = np.concatenate(rs_r) if rs_r else np.zeros(0, np.float32)
    del rs_l, rs_r
    mvs_n = np.bincount(rl, minlength=L).astype(np.int32); mvs_med = np.full(L, np.nan, np.float32)
    if len(rl):
        o2 = np.lexsort((rr, rl)); rs = rr[o2]; starts = np.r_[0, np.cumsum(mvs_n)[:-1]]; has = mvs_n > 0
        mvs_med[has] = 0.5 * (rs[starts[has] + (mvs_n[has] - 1) // 2] + rs[starts[has] + mvs_n[has] // 2])
        del o2, rs
    del rl, rr
    timings["judgment_s"] = round(time.time() - t0, 1)
    out = dict(st)
    out.update(state=state, vote=vote, E=E, J=J, J_loc=J_loc, why=why, loc_in_range=loc_in, vote_tau=vote_tau, J_tau=J_tau,
               J_loc_tau=J_loc_tau, mvs_r_med=mvs_med, mvs_r_n=mvs_n, prior_kind=np.array(prior_name), rule=np.array(rule_name), **acc)
    locs.save_store(D / "units.npz", out)
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
        seat[has] = locs.locate(st, ci[has], Vv[has])          # v6: registered vertices in the moved store
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
                confidence=conf, knn_check=knn_check, module="src/phd/prior_propagation_v6", mesh_dir=str(mesh_dir), rule=rule_name, rule_check=rule_check,
                store_frame_shift=locs.frame_shift(st).tolist(),
                registration=reg, timings=timings, pixels_without_unit=nounit, unplanted=unpl,
                states={nm: {k: cnt(inr_l & (state == code) & (kinds == kk)) for k, kk in (("roof", 1), ("wall", 2))}
                        for nm, code in (("support", rule.ST_SUPPORT), ("missing", rule.ST_MISSING), ("invisible", rule.ST_INVISIBLE))},
                support_vote={nm: cnt(inr_l & (state == rule.ST_SUPPORT) & (vote == v)) for nm, v in (("agree", rule.V_AGREE), ("conflict", rule.V_CONFLICT))},
                missing_judgment={nm: cnt(inr_l & (state == rule.ST_MISSING) & (J == j)) for j, nm in rule.J_NAMES.items()},
                support_vote_tau={nm: cnt(inr_l & (state == rule.ST_SUPPORT) & (vote_tau == v)) for nm, v in (("agree", rule.V_AGREE), ("conflict", rule.V_CONFLICT))},
                missing_judgment_tau={nm: cnt(inr_l & (state == rule.ST_MISSING) & (J_tau == j)) for j, nm in rule.J_NAMES.items()},
                mvs_residual=dict(patches_with_samples=int((mvs_n > 0).sum()), samples=int(mvs_n.sum())),
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
    ap.add_argument("--views-key", default="train"); ap.add_argument("--views-file", default="/prep/step01/views.json")
    ap.add_argument("--views-list", default=None, help="json file with a list of view names (overrides views-file)")
    ap.add_argument("--mesh-sub", default="s02"); ap.add_argument("--mvs", default="current")
    ap.add_argument("--out-sub", default="s03"); ap.add_argument("--fig-views", type=int, default=8)
    ap.add_argument("--conf", default="geometric", choices=["geometric", "photometric"], help="photometric = the confidence-mask switch off")
    ap.add_argument("--export-fork", default=None, help="directory (under /out) for the per-view maps of the fork")
    ap.add_argument("--rule", default="auto", help="discard rule: auto (default of the prior kind: LoD2 current, ALS margin_all_2) or a rules.RULES name")
    ap.add_argument("--tile", action="store_true")
    ap.add_argument("--fix-from", default=None, help="stage-1 dir (absolute, e.g. /prep/step03/B0, or under /out) whose <prior>/summary.json gives the fixed values")
    a = ap.parse_args()
    P_ = lambda p: Path(p) if str(p).startswith("/") else OUT / p
    if a.views_list:
        views = json.loads(P_(a.views_list).read_text())
        views = views if isinstance(views, list) else views["train"]
    else:
        views = json.loads(P_(a.views_file).read_text())["views"][a.range_id][a.views_key]
    mvs_dir = DENSE if a.mvs == "current" else P_(a.mvs)
    D = OUT / a.out_sub / a.range_id / a.prior
    run(a.range_id, a.prior, views, mvs_dir, P_(a.mesh_sub) / a.range_id, D, a.fig_views, a.tile, a.fix_from, a.conf,
        P_(a.export_fork) if a.export_fork else None, a.rule)


if __name__ == "__main__":
    main()
