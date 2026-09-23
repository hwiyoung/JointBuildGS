"""PHD-STAGE2-R7-PROPAGATION-v1 step 5b (jointbuildgs:dev, CPU): offline checks of the fork's dry runs (no training).

  python verify_dry.py      # mounts: /artifacts (ro), /repo (ro), /p7 (rw)

For every training setting (runs/<setting>_spec, dry_init 2):
  propagation  the fork's propagated judgments equal the offline numpy propagation of the same product and values
  seats        the fork's location of every located prior point equals numpy locations.locate of its surface and position
  planting     no planted located prior point lies on an invisible location or (default) on a conflict-propagated one;
               every unplanted point has the reason its location implies
  protection   the first protected count equals: planted located prior points with location E < 0.5 and judgment not
               conflict, plus planted prior points without a location whose centre E < 0.5 (drift 0 at initialisation)
  prior gate   at every training pixel the fork's gate is 0 exactly where its location's propagated judgment is conflict
  re-read      the re-read test of the dry run passed
and, for the baseline runs (<setting>_spec_plant), the conflict points are planted but not protected.
Writes /p7/verify/verify_dry.json."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v1 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v1 import rule  # noqa: E402

P7 = Path("/p7"); OUT = P7 / "verify"; OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads(Path("/repo/configs/phd/stage2_r7_propagation_v1/r7.json").read_text())
V = CFG["values"]
res = {}
allok = True
for setting in ("M_N", "M_B", "L_N", "L_B"):
    var = "poly" if setting.startswith("M") else "lod2"
    st = locs.load_store(P7 / "stage1/products" / setting / f"store_{var}_c{V['cell_m']}.npz")
    J_off, _ = locs.propagate(st, st["state_spec"], st["vote_spec"], V["majority"], V["min_evidence_locations"], V["max_distance_m"])
    r = {}
    mon = P7 / "runs" / f"{setting}_spec" / "model/monitor"
    rep = json.loads((mon / "init_report.json").read_text())
    z = np.load(mon / "init_points.npz"); g = np.load(mon / "gate_check.npz")
    r["propagation_equal"] = bool(np.array_equal(g["J"], J_off))
    pr = z["origin"] == 1
    seat = z["seat"]; loc = z["location"]
    has = pr & (seat >= 0)
    loc_np = np.full(len(seat), -1, np.int64)
    loc_np[has] = locs.locate(st, seat[has], z["xyz"][has].astype(np.float64))
    r["seat_agreement"] = float((loc_np[has] == loc[has]).mean()) if has.any() else 1.0
    stt = np.where(has, st["state_spec"][np.maximum(loc, 0)], -1); Jt = np.where(has, J_off[np.maximum(loc, 0)], -1)
    planted = z["planted"]
    bad_inv = int((planted & has & (stt == rule.ST_INVISIBLE)).sum())
    bad_conf = int((planted & has & (stt == rule.ST_MISSING) & (Jt == rule.J_CONFLICT)).sum())
    reason = z["reason"]
    r["planting"] = dict(planted_on_invisible=bad_inv, planted_on_conflict=bad_conf,
                         reason_invisible_consistent=bool(np.array_equal(reason == 1, pr & has & (stt == rule.ST_INVISIBLE))),
                         reason_conflict_consistent=bool(np.array_equal(reason == 2, pr & has & (stt == rule.ST_MISSING) & (Jt == rule.J_CONFLICT))),
                         reason_unseen_consistent=bool(np.array_equal(reason == 3, pr & ~has & (z["n_seeing_centre"] == 0))))
    E0 = np.where(has, st["E_spec"][np.maximum(loc, 0)], z["E_centre_prior_depth"])
    expect_lock = int((planted & pr & (E0 < 0.5) & ~(has & (Jt == rule.J_CONFLICT))).sum())
    r["protection"] = dict(fork=rep["protection"]["n_protected"], offline=expect_lock, equal=rep["protection"]["n_protected"] == expect_lock)
    gate_ok, n_px = True, 0
    Jg = g["J"]
    for k in g.files:
        if not k.startswith("gate_"):
            continue
        view = k[5:]
        gate = g[k]; lm = g[f"lm_{view}"]
        want = np.ones(lm.shape, bool)
        ok = lm >= 0
        want[ok] = Jg[lm[ok]] != rule.J_CONFLICT
        gate_ok &= bool(np.array_equal(gate, want)); n_px += int((~want).sum())
    r["prior_gate"] = dict(equal_to_table=gate_ok, off_pixels_all=n_px, report=rep.get("prior_gate", {}))
    rt = rep.get("reread_test", {})
    r["reread_test"] = rt
    r["passed"] = bool(r["propagation_equal"] and r["seat_agreement"] == 1.0 and bad_inv == 0 and bad_conf == 0
                       and all(v for k, v in r["planting"].items() if k.startswith("reason")) and r["protection"]["equal"]
                       and gate_ok and rt.get("passed", False))
    # baseline: conflict points planted, not protected
    mb = P7 / "runs" / f"{setting}_spec_plant" / "model/monitor"
    if (mb / "init_points.npz").exists():
        zb = np.load(mb / "init_points.npz"); rb = json.loads((mb / "init_report.json").read_text())
        hb = (zb["origin"] == 1) & (zb["seat"] >= 0)
        confb = hb & (zb["state"] == rule.ST_MISSING) & (zb["judgment"] == rule.J_CONFLICT)
        r["baseline"] = dict(conflict_points=int(confb.sum()), conflict_points_planted=int((confb & zb["planted"]).sum()),
                             conflict_excluded_from_protection=rb["protection"]["n_conflict_excluded"], n_protected=rb["protection"]["n_protected"])
        r["passed"] &= r["baseline"]["conflict_points"] == r["baseline"]["conflict_points_planted"]
    allok &= r["passed"]
    res[setting] = r
    print(setting, json.dumps({k: v for k, v in r.items() if k != "reread_test"}), "reread", rt.get("passed"), flush=True)
res["all_passed"] = bool(allok)
(OUT / "verify_dry.json").write_text(json.dumps(res, indent=1, default=float))
print("ALL PASSED" if allok else "SOME CHECK FAILED")
