"""PHD-MAIN-PREP-DISCARD-RULE-v1 5.1: equivalence check 2 and the switch table from the fork r11 dry initialisations
(jointbuildgs:dev, CPU).

  python fork_checks.py --tag s52 --inputs fork_inputs/s52 --run-sub s52/box [--out fork_checks/s52.json]

Check 2 (all switches on, rule current): the fork's states, votes, propagated judgments and patch judgments
(monitor/locations.npz) must equal the measurement's (units.npz), and its unplanted prior points must be the measurement's
(LoD2: one point per patch -> missing patches judged conflict; ALS: the TIN vertices of unplanted_point_index).
Switch table: for every switch run, which outputs changed against the all-on run of the same box and prior, against the
expected list of configs discard_v1.json 'switches.expected_changed_outputs', plus the order's per-switch items.
scientific_verdict: null."""
import argparse
import json
from pathlib import Path

import numpy as np

from common import DCFG, OUT, jdump, log
from src.phd.prior_propagation_v5 import rule

BOXES = ["B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"]
SW = ("confidence_mask", "judgment", "propagation", "prior_band", "protection", "init_exclusion", "prior")


def load_run(d):
    m = d / "model/monitor"
    r = dict(ok=(m / "init_report.json").exists())
    if not r["ok"]:
        return r
    r["rep"] = json.loads((m / "init_report.json").read_text())
    if (m / "locations.npz").exists():
        r["loc"] = dict(np.load(m / "locations.npz"))
    if (m / "init_points.npz").exists():
        r["pts"] = dict(np.load(m / "init_points.npz"))
    if (m / "unplanted.npz").exists():
        r["unpl"] = dict(np.load(m / "unplanted.npz"))
    return r


def items(r):
    """the compared outputs of a dry init."""
    rep = r["rep"]
    o = {}
    if "loc" in r:
        for k, nm in (("state", "states"), ("vote", "votes"), ("judgment", "propagated judgments"), ("unit_judgment", "patch judgments")):
            o[nm] = r["loc"][k]
    o["unplanted"] = int(len(r["unpl"]["xyz"])) if "unpl" in r else 0
    o["planted prior points"] = int(rep["prior_term"]["n_prior_now"])
    o["g_p"] = rep.get("prior_weight", {}).get("totals")
    o["first E"] = r["pts"]["E_first"] if "pts" in r else None
    o["protection"] = int(rep["protection"]["n_protected"]) if "protection" in rep else int((rep.get("first_E") or {}).get("n_locked", 0))
    o["A maps"] = rep["mvs_term_weight"]
    o["prior depth term"] = dict(lambda_prior=rep["prior_term"]["lambda_prior"], prior_maps=rep["prior_term"]["prior_maps"])
    return o


def same(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return a is not None and b is not None and a.shape == b.shape and bool(np.array_equal(a, b, equal_nan=True))
    return a == b


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", required=True); ap.add_argument("--inputs", required=True)
    ap.add_argument("--run-sub", required=True); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    R = OUT / "fork_runs" / a.tag
    expected = DCFG["switches"]["expected_changed_outputs"]
    out = dict(check2={}, switches={})
    all2 = True
    for box in BOXES:
        for pr in ("LoD2", "ALS"):
            key = f"{box}_{pr}"
            base = load_run(R / key)
            if not base["ok"]:
                out["check2"][key] = dict(missing=True); all2 = False; continue
            U = np.load(OUT / a.run_sub / box / pr / "units.npz")
            L = base["loc"]
            c = {nm: bool(np.array_equal(L[fk], U[mk])) for nm, fk, mk in (("state", "state", "state"), ("vote", "vote", "vote"),
                                                                          ("J", "judgment", "J"), ("J_loc", "unit_judgment", "J_loc"))}
            P = base["pts"]; prior = P["origin"] == 1
            drop_meas = (U["state"] == rule.ST_MISSING) & (U["J_loc"] == rule.J_CONFLICT)
            if pr == "LoD2":
                loc = P["location"][prior]
                c["planted"] = bool(np.array_equal(P["planted"][prior], ~drop_meas[loc])) and bool(np.array_equal(loc, np.arange(len(loc))))
                c["n_unplanted"] = [int((~P["planted"][prior]).sum()), int(drop_meas.sum())]
            else:
                vidx = np.load(OUT / a.inputs / box / "als_vertex_index_ALS.npy")
                up_meas = set(np.load(OUT / a.run_sub / box / pr / "unplanted_point_index.npy").tolist())
                up_fork = set(vidx[~P["planted"][prior]].tolist())
                c["planted"] = up_meas == up_fork
                c["n_unplanted"] = [len(up_fork), len(up_meas)]
            c["equal"] = all(v for k, v in c.items() if isinstance(v, bool))
            all2 &= c["equal"]
            out["check2"][key] = c
            # switches
            bi = items(base)
            for s in SW:
                rs = load_run(R / f"{key}_sw-{s}")
                if not rs["ok"]:
                    out["switches"].setdefault(s, {})[key] = dict(missing=True); continue
                si = items(rs)
                na = sorted(k for k in bi if k not in si or (si[k] is None and bi[k] is not None and k not in expected[s]))   # not computed in the switch run
                changed = sorted(k for k in bi if k not in na and not same(bi[k], si.get(k)))
                unexpected = [k for k in changed if k not in expected[s] and not (s == "init_exclusion" and k == "first E")]
                row = dict(changed=changed, unexpected=unexpected, not_applicable=na)
                st_b, st_s = bi.get("states"), si.get("states")
                if st_b is not None:
                    row["states_on"] = {rule.ST_NAMES[v]: int((st_b == v).sum()) for v in rule.ST_NAMES}
                if st_s is not None:
                    row["states_off"] = {rule.ST_NAMES[v]: int((st_s == v).sum()) for v in rule.ST_NAMES}
                if s == "confidence_mask":
                    w = si["A maps"]; row["A_is_1_at_every_depth_pixel"] = bool(w["of_them_A1"] == w["pixels_with_mvs_depth"] and w["A1_without_mvs_depth"] == 0)
                if s == "judgment":
                    jl, stt = si["patch judgments"], si["states"]
                    m = (stt == rule.ST_SUPPORT) | (stt == rule.ST_MISSING)
                    row["all_agree"] = bool((jl[m] == rule.J_AGREE).all()); row["unplanted_zero"] = si["unplanted"] == 0
                    g = si["g_p"] or {}; row["g_off_pixels"] = int(sum(v for k, v in g.items() if k.endswith("_g0")))
                if s == "propagation":
                    jj, stt = si["propagated judgments"], si["states"]
                    row["missing_all_insufficient"] = bool((jj[stt == rule.ST_MISSING] == rule.J_INSUFF).all()); row["unplanted_zero"] = si["unplanted"] == 0
                if s == "protection":
                    row["protected"] = si["protection"]
                if s == "init_exclusion":
                    row["unplanted_zero"] = si["unplanted"] == 0
                    row["judgments_unchanged"] = all(same(bi[k], si[k]) for k in ("states", "votes", "propagated judgments", "patch judgments"))
                if s == "prior":
                    row["prior_points"] = si["planted prior points"]; row["lambda_prior"] = si["prior depth term"]["lambda_prior"]
                out["switches"].setdefault(s, {})[key] = row
            log(key, "check2", c["equal"], c["n_unplanted"])
    out["check2_all_equal"] = bool(all2)
    out["switches_unexpected"] = {s: {k: v.get("unexpected") for k, v in d.items() if v.get("unexpected")} for s, d in out["switches"].items()}
    jdump(OUT / (a.out or f"fork_checks/{a.tag}.json"), dict(rule=__doc__.split("\n\n")[1], **out, scientific_verdict=None))
    print("CHECK2 EQUAL" if all2 else "CHECK2 DIFFERENCES", "unexpected switch changes:", {s: len(v) for s, v in out["switches_unexpected"].items()})


if __name__ == "__main__":
    main()
