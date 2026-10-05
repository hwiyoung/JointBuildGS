"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 step 8 (jointbuildgs:dev, CPU): offline checks of the fork's dry initialisations.

  python verify_dry_r10.py      # mounts: /artifacts (ro), /repo (ro), /p9 (ro), /p10 (rw)

For every dry run (runs/dry_<setting>[_cell], dry_init 2), the fork against numpy on the same product -- r9's checks
(propagation, why, seats, planting, invisible first confidence 0, the first protection with the patch judgment, g_p at every
training pixel, re-read test, direction) and the r10 changes:
  direction    file mode: the disk normal after orientation within 0.01 degree of the file normal (r9); cell mode
               (check 'ra'): a planted prior point on a patch with cells starts with the face normal of the cell numpy
               finds for it (t1 x t2 of the store, signed like its file normal), the others with the file normal
  party walls  (fix 'na', LoD2) no planted prior point lies off the r10 mesh (all within 1 cm), none lies on a cut part
               (each is farther than 1 cm from every removed r9 area: distance to the r9 mesh's replaced triangles is
               not smaller than to the r10 mesh), no training-view pixel id is a replaced r9 triangle
Writes /p10/verify/verify_dry.json."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v4 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v4 import rule  # noqa: E402

P9 = Path("/p9"); P10 = Path("/p10"); OUT = P10 / "verify"; OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads(Path("/repo/configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json").read_text())
V = CFG["values"]
res, allok = {}, True
for dry in ("M_N", "M_B", "L_N", "L_B", "L_N_cell", "L_B_cell"):
    setting = dry.replace("_cell", ""); cell_mode = dry.endswith("_cell")
    var = "poly" if setting.startswith("M") else "lod2"
    ROOT = P10 if setting.startswith("M") else P9
    st = locs.load_store(ROOT / "stage1/products" / setting / f"store_{var}_c{V['cell_m']}.npz")
    state, vote = st["state_data"], st["vote_data"]
    k, r = V["min_evidence_locations"], V["max_distance_m"]
    J_off, (mis, kd, kv) = locs.propagate(st, state, vote, V["majority"], k, r)
    Jl_off = locs.location_judgment(state, vote, J_off)
    why_off = rule.undetermined_why(state, J_off, kd, mis, k, r)
    mon = P10 / "runs" / f"dry_{dry}" / "model/monitor"
    rep = json.loads((mon / "init_report.json").read_text())
    z = np.load(mon / "init_points.npz"); g = np.load(mon / "gate_check.npz"); lz = np.load(mon / "locations.npz")
    out = dict(propagation_equal=bool(np.array_equal(g["J"], J_off)), unit_judgment_equal=bool(np.array_equal(g["J_loc"], Jl_off)),
               why_equal=bool(np.array_equal(lz["why"], why_off)))
    pr = z["origin"] == 1
    seat, loc = z["seat"], z["location"]
    has = pr & (seat >= 0)
    loc_np = np.full(len(seat), -1, np.int64)
    loc_np[has] = locs.locate(st, seat[has], z["xyz"][has].astype(np.float64))
    out["seat_agreement"] = float((loc_np[has] == loc[has]).mean()) if has.any() else 1.0
    stt = np.where(has, state[np.maximum(loc, 0)], -1); Jt = np.where(has, J_off[np.maximum(loc, 0)], -1)
    planted = z["planted"]
    conflict_pts = has & (stt == rule.ST_MISSING) & (Jt == rule.J_CONFLICT)
    out["planting"] = dict(planted_on_conflict=int((planted & conflict_pts).sum()),
                           unplanted_elsewhere=int((~planted & ~conflict_pts).sum()),
                           planted_invisible=int((planted & has & (stt == rule.ST_INVISIBLE)).sum()),
                           planted_without_unit=int((planted & pr & ~has).sum()))
    Ef = z["E_first"]
    inv = planted & has & (stt == rule.ST_INVISIBLE)
    out["invisible_first_confidence_all_zero"] = bool((Ef[inv] == 0).all())
    Jlt = np.where(has, Jl_off[np.maximum(loc, 0)], -1)
    expect_lock, _, _, _ = rule.protected(planted & pr, Ef, 0.5, np.zeros(len(Ef)), 1.0, Jlt)     # u = 0 at initialisation
    r8_rule = planted & pr & (Ef < 0.5) & (Jt != rule.J_CONFLICT)
    out["protection"] = dict(fork=rep["protection"]["n_protected"], offline=int(expect_lock.sum()),
                             equal=rep["protection"]["n_protected"] == int(expect_lock.sum()),
                             invisible_points_protected_offline=int((expect_lock & inv).sum()), invisible_planted=int(inv.sum()),
                             r8_rule_would_protect=int(r8_rule.sum()),
                             difference_support_conflict=int((r8_rule & ~expect_lock & (stt == rule.ST_SUPPORT) & (Jlt == rule.J_CONFLICT)).sum()),
                             fork_excluded_support_conflict=rep["first_E"]["excluded_support_conflict"])
    # fix 'da': direction after orientation
    fnz = z["face_normal"]; nao = z["normal_after_orientation"]
    okn = planted & pr & np.isfinite(fnz).all(1)
    a_ = fnz[okn].astype(np.float64); b_ = nao[okn].astype(np.float64)
    cosv = (a_ * b_).sum(1)
    angv = np.degrees(np.arctan2(np.linalg.norm(np.cross(a_, b_), axis=1), cosv))     # well conditioned near 0
    ori = rep["init"]["orientation"]
    # the face normal the mode asks for, offline: file normal; cell mode: t1 x t2 of the numpy cell, signed like the file normal
    ffile = z["face_normal_file"].astype(np.float64)
    want = ffile.copy()
    if cell_mode:
        cn = np.cross(st["loc_t1"], st["loc_t2"]); nn_ = np.linalg.norm(cn, axis=1)
        has_cell = has & (nn_[np.maximum(loc_np, 0)] > 1e-9)
        c = cn[loc_np[has_cell]] / nn_[loc_np[has_cell], None]
        ref = ffile[has_cell]; dot = np.where(np.isfinite(ref).all(1), (c * np.nan_to_num(ref)).sum(1), c[:, 2])
        want[has_cell] = np.where(dot[:, None] < 0, -c, c)
        out["cell_points"] = dict(n=int(has_cell.sum()), planted=int((has_cell & planted).sum()),
                                  fork_cell_normals=int(np.isfinite(z["face_normal_cell"]).all(1).sum()))
    a2 = want[okn]; c2 = (a2 * a_).sum(1)
    angw = np.degrees(np.arctan2(np.linalg.norm(np.cross(a2, a_), axis=1), c2))
    out["direction"] = dict(mode="cell" if cell_mode else "file", n_planted_prior=int((planted & pr).sum()), n_with_face_normal=int(okn.sum()),
                            max_angle_deg=float(angv.max()) if okn.any() else None,
                            min_cos=float(cosv.min()) if okn.any() else None, fork=ori,
                            offline_face_normal_max_angle_deg=float(angw.max()) if okn.any() else None,
                            passed=bool(okn.sum() == (planted & pr).sum() and okn.any() and angv.max() < 0.01
                                        and cosv.min() > 0 and ori.get("image_rows_unchanged") and angw.max() < 0.01))
    # fix 'na': party walls (and r9's bottom faces) on the r10 mesh
    if setting.startswith("M"):
        import open3d as o3d
        mesh = np.load(P10 / "stage1/meshes" / f"{setting}.npz"); m9 = np.load(P9 / "stage1/meshes" / f"{setting}.npz")
        surf_tab = json.loads((P10 / "stage1/products" / setting / "surfaces_poly.json").read_text())["surfaces"]
        types = {r["ext"]: r["type"] for r in surf_tab}
        k10 = mesh["kept_from_r9"]; repl = np.ones(len(m9["F"]), bool); repl[k10[k10 >= 0]] = False
        sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.core.Tensor(mesh["V"].astype(np.float32)), o3d.core.Tensor(mesh["F"].astype(np.uint32)))
        sr = o3d.t.geometry.RaycastingScene(); sr.add_triangles(o3d.core.Tensor(m9["V"].astype(np.float32)), o3d.core.Tensor(m9["F"][repl].astype(np.uint32)))
        P_ = z["xyz"][planted & pr].astype(np.float32)
        dd = sc.compute_distance(o3d.core.Tensor(P_)).numpy(); dr = sr.compute_distance(o3d.core.Tensor(P_)).numpy()
        # a point on a cut part: on a replaced r9 triangle (dr ~ 0) but off the r10 mesh (dd > dr)
        on_cut = (dr <= 1e-3) & (dd > dr + 1e-6)
        ext_seat = st["surf_ext"][np.maximum(seat, 0)]
        rep_px = 0
        for view in json.loads((Path("/artifacts/JointBuildGS/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1/runs/P_M_N/model/monitor/meta.json")).read_text())["train_views"]:
            tri = np.load(P10 / "stage1/ids" / setting / f"{view}.npz")["tri"]
            rep_px += int((tri >= len(mesh["F"])).sum())
        cuts = json.loads((P10 / "stage1/meshes" / f"cuts_{setting}.json").read_text())
        full_cut = {int(p) for p, r in cuts["polygons"].items() if r["fully_cut"]}
        out["party_wall"] = dict(bottom_surfaces_in_table=int(sum(t == "ground" for t in types.values())),
                                 fully_cut_polygons_in_store=int(len(full_cut & set(int(e) for e in st["surf_ext"]))),
                                 fully_cut_slivers_in_table=sorted(int(e) for e in full_cut & set(types)),
                                 planted_prior_max_distance_to_r10_mesh_m=float(dd.max()) if len(dd) else 0.0,
                                 planted_prior_on_cut_parts=int(on_cut.sum()),
                                 planted_points_seated_on_fully_cut=int(sum(int(e) in full_cut for e in ext_seat[has & planted])),
                                 train_view_ids_out_of_range=rep_px)
        out["party_wall"]["passed"] = bool(out["party_wall"]["bottom_surfaces_in_table"] == 0 and out["party_wall"]["fully_cut_polygons_in_store"] == 0
                                           and out["party_wall"]["planted_prior_max_distance_to_r10_mesh_m"] < 0.02
                                           and out["party_wall"]["planted_prior_on_cut_parts"] == 0
                                           and out["party_wall"]["planted_points_seated_on_fully_cut"] == 0 and rep_px == 0)
    g_ok, n_px, n_off = True, 0, 0
    for key in g.files:
        if not key.startswith("g_"):
            continue
        view = key[2:]
        lm = g[f"lm_{view}"].astype(np.int64); mk = g[f"mk_{view}"].astype(np.int64); A = g[f"A_{view}"].astype(np.float32)
        located = lm >= 0
        Jl = np.full(lm.shape, rule.J_NONE, np.int64); Jl[located] = Jl_off[lm[located]]
        want = ~rule.prior_term_off(located, Jl, A, mk)
        g_ok &= bool(np.array_equal(want, g[key]))
        n_px += int(want.size); n_off += int((~want).sum())
    out["g_p"] = dict(equal_at_every_pixel=g_ok, pixels=n_px, g0_pixels=n_off)
    rt = rep.get("reread_test", {})
    out["reread_test_passed"] = bool(rt.get("passed"))
    ok = (out["propagation_equal"] and out["unit_judgment_equal"] and out["why_equal"] and out["seat_agreement"] == 1.0
          and out["planting"]["planted_on_conflict"] == 0 and out["planting"]["unplanted_elsewhere"] == 0
          and out["invisible_first_confidence_all_zero"] and out["protection"]["equal"] and g_ok and out["reread_test_passed"]
          and out["direction"]["passed"] and out.get("party_wall", {}).get("passed", True))
    out["passed"] = bool(ok)
    allok &= ok
    res[dry] = out
    print(dry, json.dumps(out)[:1500], flush=True)
res["all_passed"] = bool(allok)
(OUT / "verify_dry.json").write_text(json.dumps(res, indent=1))
print("ALL PASSED" if allok else "SOME CHECKS FAILED")
sys.exit(0 if allok else 1)
