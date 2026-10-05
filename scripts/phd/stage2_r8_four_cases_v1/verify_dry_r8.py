"""PHD-STAGE2-R8-FOUR-CASES-v1 step 5b (jointbuildgs:dev, CPU): offline checks of the fork's dry initialisations (no training).

  python verify_dry_r8.py      # mounts: /artifacts (ro), /repo (ro), /r7 (ro), /p8 (rw)

For every training setting (runs/dry_<setting>, dry_init 2), the fork against numpy on the same product:
  propagation  the fork's propagated judgments and unit judgments equal locations.propagate / location_judgment
  why          the reasons of the undetermined units equal rule.undetermined_why
  seats        the fork's unit of every prior point with a unit equals numpy locations.locate
  planting     no planted point lies on a missing unit with a propagated conflict; every other point is planted
               (support units of either vote, invisible units, points without a unit)
  invisible    every planted point of an invisible unit has first confidence 0 and is protected (u = 0 at initialisation)
  protection   the first protected count equals: planted prior points with first confidence < 0.5 and propagated
               judgment not conflict
  g_p          at every training pixel the fork's g_p equals rule.prior_term_off computed with numpy from the unit map,
               the unit judgments, c_p and the mark map at the training resolution
  re-read      the re-read test of the dry run passed
Writes /p8/verify/verify_dry.json."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v2 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v2 import rule  # noqa: E402

P8 = Path("/p8"); OUT = P8 / "verify"; OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads(Path("/repo/configs/phd/stage2_r8_four_cases_v1/r8.json").read_text())
V = CFG["values"]
res, allok = {}, True
for setting in ("M_N", "M_B", "L_N", "L_B"):
    var = "poly" if setting.startswith("M") else "lod2"
    st = locs.load_store(P8 / "stage1/products" / setting / f"store_{var}_c{V['cell_m']}.npz")
    state, vote = st["state_data"], st["vote_data"]
    k, r = V["min_evidence_locations"], V["max_distance_m"]
    J_off, (mis, kd, kv) = locs.propagate(st, state, vote, V["majority"], k, r)
    Jl_off = locs.location_judgment(state, vote, J_off)
    why_off = rule.undetermined_why(state, J_off, kd, mis, k, r)
    mon = P8 / "runs" / f"dry_{setting}" / "model/monitor"
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
    expect_lock = planted & pr & (Ef < 0.5) & (Jt != rule.J_CONFLICT)
    out["protection"] = dict(fork=rep["protection"]["n_protected"], offline=int(expect_lock.sum()),
                             equal=rep["protection"]["n_protected"] == int(expect_lock.sum()),
                             invisible_points_protected_offline=int((expect_lock & inv).sum()), invisible_planted=int(inv.sum()))
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
          and out["invisible_first_confidence_all_zero"] and out["protection"]["equal"] and g_ok and out["reread_test_passed"])
    out["passed"] = bool(ok)
    allok &= ok
    res[setting] = out
    print(setting, json.dumps(out), flush=True)
res["all_passed"] = bool(allok)
(OUT / "verify_dry.json").write_text(json.dumps(res, indent=1))
print("ALL PASSED" if allok else "SOME CHECKS FAILED")
sys.exit(0 if allok else 1)
