"""PHD-STAGE2-R9-THREE-FIXES-v1 step 8 (jointbuildgs:dev, CPU): offline checks of the fork's dry initialisations (no training).

  python verify_dry_r9.py      # mounts: /artifacts (ro), /repo (ro), /r7 (ro), /r8 (ro), /p9 (rw)

For every training setting (runs/dry_<setting>, dry_init 2), the fork against numpy on the same product -- r8's checks:
  propagation, why, seats, planting, invisible (first confidence 0, protected), g_p at every training pixel, re-read test
and the r9 changes:
  protection   (fix 'na') the first protected count equals: planted prior points with first confidence < 0.5 whose PATCH
               judgment (support vote or propagated) is not conflict; the r8 rule (propagated judgment only) is counted beside
  direction    (fix 'da') every planted prior point with a face normal has the disk normal of its rotation (after orientation)
               within 0.01 degree of the face normal, same sign; image points keep the base rotation (fork report)
  bottom face  (fix 'ra', LoD2) no planted point lies on a bottom face: no seat polygon of type GroundSurface /
               ClosureSurface (none exists in the r9 surface table) and every prior point is within 1 cm of the r9 mesh;
               no prior pixel and no surface number of the r9 product belongs to a bottom face
Writes /p9/verify/verify_dry.json."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v3 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v3 import rule  # noqa: E402

P9 = Path("/p9"); OUT = P9 / "verify"; OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads(Path("/repo/configs/phd/stage2_r9_three_fixes_v1/r9.json").read_text())
V = CFG["values"]
res, allok = {}, True
for setting in ("M_N", "M_B", "L_N", "L_B"):
    var = "poly" if setting.startswith("M") else "lod2"
    st = locs.load_store(P9 / "stage1/products" / setting / f"store_{var}_c{V['cell_m']}.npz")
    state, vote = st["state_data"], st["vote_data"]
    k, r = V["min_evidence_locations"], V["max_distance_m"]
    J_off, (mis, kd, kv) = locs.propagate(st, state, vote, V["majority"], k, r)
    Jl_off = locs.location_judgment(state, vote, J_off)
    why_off = rule.undetermined_why(state, J_off, kd, mis, k, r)
    mon = P9 / "runs" / f"dry_{setting}" / "model/monitor"
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
    out["direction"] = dict(n_planted_prior=int((planted & pr).sum()), n_with_face_normal=int(okn.sum()),
                            max_angle_deg=float(angv.max()) if okn.any() else None,
                            min_cos=float(cosv.min()) if okn.any() else None, fork=ori,
                            passed=bool(okn.sum() == (planted & pr).sum() and okn.any() and angv.max() < 0.01
                                        and cosv.min() > 0 and ori.get("image_rows_unchanged")))
    # fix 'ra': bottom faces
    if setting.startswith("M"):
        import open3d as o3d
        mesh = np.load(P9 / "stage1/meshes" / f"{setting}.npz")
        surf_tab = json.loads((P9 / "stage1/products" / setting / "surfaces_poly.json").read_text())["surfaces"]
        types = {r["ext"]: r["type"] for r in surf_tab}
        sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.core.Tensor(mesh["V"].astype(np.float32)), o3d.core.Tensor(mesh["F"].astype(np.uint32)))
        dd = sc.compute_distance(o3d.core.Tensor(z["xyz"][planted & pr].astype(np.float32))).numpy()
        ext_seat = st["surf_ext"][np.maximum(seat, 0)]
        bottom_px = 0
        for view in json.loads((Path("/artifacts/JointBuildGS/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1/runs/P_M_N/model/monitor/meta.json")).read_text())["train_views"]:
            tri = np.load(P9 / "stage1/ids" / setting / f"{view}.npz")["tri"]
            bottom_px += int(np.isin(mesh["tri_type"][np.maximum(tri[tri >= 0], 0)], ["GroundSurface", "ClosureSurface"]).sum())
        out["bottom_face"] = dict(surface_types=sorted(set(types.values())), bottom_surfaces_in_table=int(sum(t == "ground" for t in types.values())),
                                  mesh_bottom_triangles=int(np.isin(mesh["tri_type"], ["GroundSurface", "ClosureSurface"]).sum()),
                                  planted_points_seated_on_bottom=int(sum(types.get(int(e)) == "ground" for e in ext_seat[has & planted])),
                                  planted_prior_max_distance_to_r9_mesh_m=float(dd.max()) if len(dd) else 0.0,
                                  train_view_pixels_on_bottom_triangles=bottom_px)
        out["bottom_face"]["passed"] = bool(out["bottom_face"]["bottom_surfaces_in_table"] == 0 and out["bottom_face"]["mesh_bottom_triangles"] == 0
                                            and out["bottom_face"]["planted_points_seated_on_bottom"] == 0 and out["bottom_face"]["planted_prior_max_distance_to_r9_mesh_m"] < 0.02
                                            and bottom_px == 0)
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
          and out["direction"]["passed"] and out.get("bottom_face", {}).get("passed", True))
    out["passed"] = bool(ok)
    allok &= ok
    res[setting] = out
    print(setting, json.dumps(out), flush=True)
res["all_passed"] = bool(allok)
(OUT / "verify_dry.json").write_text(json.dumps(res, indent=1))
print("ALL PASSED" if allok else "SOME CHECKS FAILED")
sys.exit(0 if allok else 1)
