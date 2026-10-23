"""PHD-MAIN-WIDEN0-v2 CPU registration only, copied from s03_stage1_v6.py.

Original lines 25..294, ending before adaptive tolerance or judgment. No region
codes or method decisions are generated. Original file is immutable.
"""
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
    return pr, reg, timings
