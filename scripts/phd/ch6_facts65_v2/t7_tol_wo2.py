"""PHD-CH6-FACTS65-v2 task 7.5 [이 발주에서 냄]: the LoD2 tolerance of the search regions that hold the two buildings with a
building-wide offset (DEBY_LOD2_4959459, DEBY_LOD2_4906985; 6장 보조 작업 보고서 5절), recomputed with the residuals of the
two buildings left out. The procedure is the one that made the values used (the discard-rule task's search-region runs,
scripts/phd/main_prep_discard_rule_v1/s03_stage1.py with module v5; the v6 module gives the same values, 6장 보조 작업 T8):
pass 1 (render the prior at every training view, Nuth-Kaab samples), the gated horizontal shift, the vertical shift, pass 2
(re-render, residuals per surface kind, at most 20,000 per view and kind), the final all-view check (and its re-run of pass 2
when the horizontal shift is dropped) and the tolerance (2.5 NMAD after one 3-NMAD clip; LoD2 walls with >= 2,000 pixels).
The lines of run() (s03_stage1.py 110-299) for these steps are copied here with ONE change: the triangles of the left-out
buildings (tri_building of the range mesh, caps included) are not building faces (bface_tri False), so their pixels enter
neither the registration nor the tolerance. Pass 3 and the judgment are not run; nothing is trained. A run with nothing left
out must give the recorded values bit for bit (the check in the output). (jointbuildgs:dev, CPU)
  python t7_tol_wo2.py <range> [--exclude DEBY_LOD2_4959459,DEBY_LOD2_4906985 | --exclude none]
Mounts as the task runner: /dr the discard-rule payload (meshes s02/<range>, MVS mvs/<range>, the recorded s52/s03 summaries),
/prep, /art, /repo. Writes /out/t7_5/<range>_<tag>.json. scientific_verdict: null."""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo"); sys.path.insert(0, "/repo/scripts/phd/main_prep_discard_rule_v1")
import s03_stage1 as S  # noqa: E402  (imports the discard-rule common module and the v5 shared module, as the recorded runs)

DR = Path("/dr"); O = Path("/out/t7_5"); O.mkdir(parents=True, exist_ok=True)
conv, regm, tol = S.conv, S.regm, S.tol
nmad = regm.nmad


def run(range_id, exclude, views, mvs_dir, mesh_dir):
    """passes 1-2, registration and tolerance of s03_stage1.run (lines 110-299), with the excluded buildings' triangles off."""
    RNG = np.random.default_rng(0)                  # a fresh process seeds the module RNG at import; no draw happens before pass 1
    timings = {}
    rngs = json.loads((S.PREP / "step01/ranges.json").read_text())
    rng = rngs[range_id]
    V = S.Views()
    pr = S.Prior(mesh_dir, "LoD2")
    m = np.load(mesh_dir / "lod2_mesh.npz")
    names = [str(x) for x in m["building_names"]]; tb = m["tri_building"].astype(np.int64)
    ex_idx = {b: names.index(b) for b in exclude if b in names}
    ex_tri = np.isin(tb, list(ex_idx.values())) if ex_idx else np.zeros(len(pr.F), bool)
    bface_all = pr.bface_tri.copy()
    pr.bface_tri = pr.bface_tri & ~ex_tri                                               # THE change
    reg_cfg = S.CFG["registration"]

    have = [n for n in views if (Path(mvs_dir) / "stereo/depth_maps" / f"{n}.geometric.bin").exists()]
    dropped_views = sorted(set(views) - set(have))
    views = have

    def depth_of(n):
        d = S.read_depth_bin(Path(mvs_dir) / "stereo/depth_maps" / f"{n}.geometric.bin")
        assert d.shape == (S.GRID_H, S.GRID_W), (n, d.shape)
        return d

    def pixel_terms(scene, n):
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
        return dict(idx=idx, tri=trif, d=d, n=nn, f=f, r=r, a1=a1.ravel()[idx], P=t.ravel()[idx], C=C)

    # ---------------- pass 1: Nuth-Kaab samples (s03_stage1.py 154-177) ----------------
    t0 = time.time()
    sc, _ = pr.scene()
    Sm = dict(xy=[], dh=[], n=[], vert=[], vn=[])
    nmad_pool_before = []
    for n in views:
        q = pixel_terms(sc, n)
        bf = pr.bface_tri[q["tri"]] & q["a1"]
        nz = np.abs(q["n"][:, 2])
        X = q["C"][None, :] + q["P"][:, None] * q["d"]
        inr = S.inside_range(X[:, :2], rng)
        roof = bf & inr & (nz >= 0.5)
        fit = roof & (nz <= 0.9962)
        if fit.any():
            k = np.nonzero(fit)[0]
            if len(k) > 4000:
                k = RNG.choice(k, 4000, replace=False)
            Sm["xy"].append(X[k, :2]); Sm["dh"].append(-q["r"][k]); Sm["n"].append(q["n"][k] * np.sign(q["n"][k, 2:3]))
        kr = np.nonzero(roof)[0]
        if len(kr) > 4000:
            kr = RNG.choice(kr, 4000, replace=False)
        Sm["vert"].append(-q["r"][kr]); Sm["vn"].append(q["n"][kr] * np.sign(q["n"][kr, 2:3]))
        kb = np.nonzero(bf & inr)[0]
        if len(kb) > 4000:
            kb = RNG.choice(kb, 4000, replace=False)
        nmad_pool_before.append(q["r"][kb])
    Sm = {k: (np.concatenate(v) if v else np.zeros((0, 3) if k in ("n", "vn") else ((0, 2) if k == "xy" else 0))) for k, v in Sm.items()}
    timings["pass1_s"] = round(time.time() - t0, 1)
    gate_views = [views[int(i)] for i in np.unique(np.linspace(0, len(views) - 1, min(40, len(views))).round().astype(int))]

    def gate(shift, pred=None, gviews=None):
        pr.shift = np.asarray(shift, np.float64); scg, _ = pr.scene()
        vals = []
        for n in (gviews or gate_views):
            q = pixel_terms(scg, n)
            X = q["C"][None, :] + q["P"][:, None] * q["d"]
            m_ = pr.bface_tri[q["tri"]] & q["a1"] & S.inside_range(X[:, :2], rng) & (np.abs(q["n"][:, 2]) >= 0.5)
            if pred is not None:
                m_ &= pred(X[:, :2])
            k = np.nonzero(m_)[0]
            if len(k) > 20000:
                k = RNG.choice(k, 20000, replace=False)
            vals.append(-q["r"][k])
        v = np.concatenate(vals) if vals else np.zeros(0)
        return nmad(v)
    reg = dict(iterations=[], n_fit=int(len(Sm["dh"])), gate_views=len(gate_views))
    dxy = regm.gated_horizontal(Sm, gate, reg_cfg, reg)
    reg["shift_xy"] = dxy.tolist()
    dz, m_h, s_h = regm.vertical_shift(gate, dxy)
    reg.update(vertical_rule=regm.VERTICAL_RULE, median_after_horizontal=m_h, nmad_after_horizontal=s_h, shift_z=dz)
    pool_b = np.concatenate(nmad_pool_before) if nmad_pool_before else np.zeros(0)
    reg["building_face_nmad_unregistered"] = nmad(pool_b)[1]
    cand = np.array([dxy[0], dxy[1], dz])
    pr.shift = cand
    sc, _ = pr.scene()
    excluded_px = {}

    # ---------------- pass 2: tolerance (s03_stage1.py 244-262) ----------------
    def pass2(sc):
        samp = {conv.KIND_ROOF: [], conv.KIND_WALL: []}; pool = []
        cnt = {b: {conv.KIND_ROOF: 0, conv.KIND_WALL: 0} for b in ex_idx}
        for n in views:
            q = pixel_terms(sc, n)
            bf = pr.bface_tri[q["tri"]] & q["a1"]
            X = q["C"][None, :] + q["P"][:, None] * q["d"]
            inr = S.inside_range(X[:, :2], rng)
            kind = conv.surface_kind(q["n"][:, 2])
            for b, bi in ex_idx.items():                # counting only (no draw): confidence-1 in-range pixels of the left-out buildings
                mb = bface_all[q["tri"]] & q["a1"] & inr & (tb[q["tri"]] == bi)
                for k in cnt[b]:
                    cnt[b][k] += int((mb & (kind == k)).sum())
            for k in samp:
                sel = np.nonzero(bf & inr & (kind == k))[0]
                if len(sel) > 20000:
                    sel = RNG.choice(sel, 20000, replace=False)
                samp[k].append(q["r"][sel])
            kb = np.nonzero(bf & inr)[0]
            if len(kb) > 4000:
                kb = RNG.choice(kb, 4000, replace=False)
            pool.append(q["r"][kb])
        excluded_px.clear(); excluded_px.update({b: {("roof" if k == conv.KIND_ROOF else "wall"): v for k, v in c.items()} for b, c in cnt.items()})
        return samp, (np.concatenate(pool) if pool else np.zeros(0))
    t0 = time.time()
    samp, pool_a = pass2(sc)
    reg["building_face_nmad_registered"] = nmad(pool_a)[1]
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
    reg["shift_applied"] = pr.shift.tolist()
    roof_x = np.concatenate(samp[conv.KIND_ROOF]) if samp[conv.KIND_ROOF] else np.zeros(0)
    wall_x = np.concatenate(samp[conv.KIND_WALL]) if samp[conv.KIND_WALL] else np.zeros(0)
    spec = S.CFG["priors"]["spec_m"]["LoD2"]
    roof_st = tol.robust_width(roof_x); wall_st = tol.robust_width(wall_x)
    roof_t = tol.tolerance(roof_st, spec["roof"], "agency spec (configs prep_v2 = v1)")
    if wall_st["n"] >= S.CFG["tolerance"]["wall_min_pixels"]:
        wall_t = tol.tolerance(wall_st, spec["wall"], "no agency wall spec")
    else:
        wall_t = tol.tolerance(dict(width=None), spec["wall"], "no agency wall spec", fallback=roof_t)
    return dict(range=range_id, prior="LoD2", excluded=sorted(ex_idx), excluded_not_in_mesh=sorted(set(exclude) - set(ex_idx)),
                excluded_triangles=int(ex_tri.sum()), excluded_pixels_pass2=excluded_px, views=len(views), dropped_views=dropped_views,
                registration=reg, tolerance=dict(roof=roof_t, wall=wall_t), stats=dict(roof=roof_st, wall=wall_st), timings=timings)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("range_id")
    ap.add_argument("--exclude", default="DEBY_LOD2_4959459,DEBY_LOD2_4906985")
    a = ap.parse_args()
    exclude = [] if a.exclude == "none" else a.exclude.split(",")
    views = json.loads((S.PREP / "step01/views.json").read_text())["views"][a.range_id]["train"]
    t0 = time.time()
    res = run(a.range_id, exclude, views, DR / "mvs" / a.range_id, DR / "s02" / a.range_id)
    rec = json.loads((DR / "s52/s03" / a.range_id / "LoD2/summary.json").read_text())
    res["recorded"] = dict(tolerance={k: rec["tolerance"][k]["tau"] for k in ("roof", "wall")},
                           shift_applied=rec["registration"]["shift_applied"], views=rec["views"],
                           building_face_nmad_unregistered=rec["registration"]["building_face_nmad_unregistered"],
                           building_face_nmad_registered=rec["registration"]["building_face_nmad_registered"])
    if not exclude:                                  # the check: the copied procedure reproduces the recorded run
        res["check_equal_to_recorded"] = dict(
            tau_roof=res["tolerance"]["roof"]["tau"] == rec["tolerance"]["roof"]["tau"],
            tau_wall=res["tolerance"]["wall"]["tau"] == rec["tolerance"]["wall"]["tau"],
            shift=res["registration"]["shift_applied"] == rec["registration"]["shift_applied"],
            nmad_unregistered=res["registration"]["building_face_nmad_unregistered"] == rec["registration"]["building_face_nmad_unregistered"],
            nmad_registered=res["registration"]["building_face_nmad_registered"] == rec["registration"]["building_face_nmad_registered"])
    res["seconds"] = round(time.time() - t0, 1); res["rule"] = __doc__.split("\n\n")[0]; res["scientific_verdict"] = None
    tag = "none" if not exclude else "wo2"
    S.jdump(O / f"{a.range_id}_{tag}.json", res)
    print(a.range_id, tag, "tau", res["tolerance"]["roof"]["tau"], res["tolerance"]["wall"]["tau"], "recorded", res["recorded"]["tolerance"],
          "shift", res["registration"]["shift_applied"], "excluded px", res["excluded_pixels_pass2"], res.get("check_equal_to_recorded"), res["seconds"], "s")


if __name__ == "__main__":
    main()
