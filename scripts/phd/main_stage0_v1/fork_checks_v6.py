"""PHD-MAIN-STAGE0-v1 5.1: checks of the fork r12 dry initialisations (jointbuildgs:dev, CPU) = the discard task's fork_checks.py
with the v6 measurement and two more checks.

  python fork_checks_v6.py --tag s61 --inputs fork_inputs/s61 --run-sub s61/box [--out fork_checks/s61.json]

check2      (rule auto = the default of the prior kind, all switches on; ALS also rule current) the fork's states, votes,
            propagated judgments and patch judgments (monitor/locations.npz) equal the measurement's (units.npz: the rule's
            state / vote / J / J_loc, or the *_tau values for rule current), and its unplanted prior points are the
            measurement's (LoD2: one point per patch -> missing patches judged conflict; ALS: the TIN vertices seated in the
            moved store on a missing patch judged conflict)
r11_equal   LoD2 (no registration shift): every array of r12's locations / init_points / unplanted / gate_check equals r11's
            run of the discard task (/dr/fork_runs/s52) element-wise
switches    for every switch run of the switch site, which outputs changed against the all-on run of the same prior, against the
            expected list of configs discard_v1.json 'switches.expected_changed_outputs', plus the per-switch items
scientific_verdict: null."""
import argparse
import json
from pathlib import Path

import numpy as np

from common import DCFG, DR, OUT, SCFG, inside_range, jdump, log
from src.phd.prior_propagation_v6 import locations as locs
from src.phd.prior_propagation_v6 import rule
from src.phd.prior_propagation_v6 import surfaces as surf

BOXES = SCFG["check_51"]["sites"]
SW_SITE = SCFG["check_51"]["switch_site"].split(" ")[0]
SW = ("confidence_mask", "judgment", "propagation", "prior_band", "protection", "init_exclusion", "prior")


def load_run(d):
    m = d / "model/monitor"
    r = dict(ok=(m / "init_report.json").exists())
    if not r["ok"]:
        return r
    r["rep"] = json.loads((m / "init_report.json").read_text())
    for k, f in (("loc", "locations.npz"), ("pts", "init_points.npz"), ("unpl", "unplanted.npz"), ("gate", "gate_check.npz")):
        if (m / f).exists():
            r[k] = np.load(m / f)
    return r


def items(r):
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
        if a is None or b is None or a.shape != b.shape:
            return False
        fl = a.dtype.kind in "fc" and b.dtype.kind in "fc"
        return bool(np.array_equal(a, b, equal_nan=fl))
    return a == b


def als_unplanted(run_dir, U, J_loc):
    """indices of the TIN vertices (inside the range) the measurement would not plant for the judgments J_loc (moved store)."""
    summ = json.loads((run_dir / "summary.json").read_text())
    md = Path(summ["mesh_dir"]); shift = np.asarray(summ["registration"]["shift_applied"], np.float64)
    m = dict(np.load(md / "als_mesh.npz"))
    Vv = m["V"].astype(np.float64) + shift; F = m["F"].astype(np.int64); ts = m["tri_surface"].astype(np.int64)
    eligible = np.zeros(int(ts.max()) + 2, bool)
    for r_ in json.loads((md / "als_surfaces.json").read_text())["surfaces"]:
        eligible[r_["ext"]] = True
    vs = surf.vertex_surface(F, ts, eligible)
    ci = np.where(vs >= 0, locs.compact_index(U, np.maximum(vs, 0)), -1)
    has = ci >= 0; seat = np.full(len(Vv), -1, np.int64)
    seat[has] = locs.locate(U, ci[has], Vv[has])
    bad = has & (J_loc[np.maximum(seat, 0)] == rule.J_CONFLICT) & (U["state"][np.maximum(seat, 0)] == rule.ST_MISSING)
    inr = inside_range(Vv[:, :2], json.loads((md / "range.json").read_text()))
    return set(np.nonzero(bad & inr)[0].tolist())


def check2(base, U, run_dir, inputs, box, pr, tau):
    L = base["loc"]
    sx = "_tau" if tau else ""
    c = {nm: bool(np.array_equal(L[fk], U[mk + (sx if mk != "state" else "")])) for nm, fk, mk in
         (("state", "state", "state"), ("vote", "vote", "vote"), ("J", "judgment", "J"), ("J_loc", "unit_judgment", "J_loc"))}
    P = base["pts"]; prior = P["origin"] == 1
    Jl = U["J_loc" + sx]
    drop_meas = (U["state"] == rule.ST_MISSING) & (Jl == rule.J_CONFLICT)
    if pr == "LoD2":
        loc = P["location"][prior]
        c["planted"] = bool(np.array_equal(P["planted"][prior], ~drop_meas[loc])) and bool(np.array_equal(loc, np.arange(len(loc))))
        c["n_unplanted"] = [int((~P["planted"][prior]).sum()), int(drop_meas.sum())]
    else:
        vidx = np.load(OUT / inputs / box / "als_vertex_index_ALS.npy")
        up_meas = als_unplanted(run_dir, U, Jl)
        if not tau:
            up_file = set(np.load(run_dir / "unplanted_point_index.npy").tolist())
            c["measurement_file_equals_recomputed"] = up_file == up_meas
        up_fork = set(vidx[~P["planted"][prior]].tolist())
        c["planted"] = up_meas == up_fork
        c["n_unplanted"] = [len(up_fork), len(up_meas)]
    c["equal"] = all(v for k, v in c.items() if isinstance(v, bool))
    return c


def r11_equal(new, old):
    out, alleq = {}, True
    for k in ("loc", "pts", "unpl", "gate"):
        a, b = new.get(k), old.get(k)
        if a is None or b is None:
            out[k] = "missing"; alleq = False; continue
        diff = sorted(f for f in set(a.files) | set(b.files) if f not in a.files or f not in b.files or not same(a[f], b[f]))
        out[k] = dict(arrays=len(set(a.files) | set(b.files)), differing=diff)
        alleq &= not diff
    out["all_equal"] = bool(alleq)
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", required=True); ap.add_argument("--inputs", required=True)
    ap.add_argument("--run-sub", required=True); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    R = OUT / "fork_runs" / a.tag
    expected = DCFG["switches"]["expected_changed_outputs"]
    out = dict(check2={}, r11_equal={}, switches={})
    all2 = True
    for box in BOXES:
        for pr in ("LoD2", "ALS"):
            key = f"{box}_{pr}"
            run_dir = OUT / a.run_sub / box / pr
            U = np.load(run_dir / "units.npz")
            variants = [(key, False)] + ([(f"{key}_rule-current", True)] if pr == "ALS" else [])
            for name, tau in variants:
                base = load_run(R / name)
                if not base["ok"]:
                    out["check2"][name] = dict(missing=True); all2 = False; continue
                c = check2(base, U, run_dir, a.inputs, box, pr, tau)
                c["rule"] = base["rep"].get("rule"); c["rule_source"] = base["rep"].get("rule_source")
                all2 &= c["equal"]
                out["check2"][name] = c
                log(name, "check2", c["equal"], c["n_unplanted"], c["rule"])
            if pr == "LoD2":
                old = load_run(DR / "fork_runs/s52" / key)
                out["r11_equal"][key] = r11_equal(load_run(R / key), old) if old["ok"] else "r11 run missing"
            if box != SW_SITE:
                continue
            bi = items(load_run(R / key))
            for s in SW:
                rs = load_run(R / f"{key}_sw-{s}")
                if not rs["ok"]:
                    out["switches"].setdefault(s, {})[key] = dict(missing=True); continue
                si = items(rs)
                na = sorted(k for k in bi if k not in si or (si[k] is None and bi[k] is not None and k not in expected[s]))
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
    out["check2_all_equal"] = bool(all2)
    out["r11_all_equal"] = all(isinstance(v, dict) and v.get("all_equal") for v in out["r11_equal"].values())
    out["switches_unexpected"] = {s: {k: v.get("unexpected") for k, v in d.items() if v.get("unexpected")} for s, d in out["switches"].items()}
    jdump(OUT / (a.out or f"fork_checks/{a.tag}.json"), dict(rule=__doc__.split("\n\n")[1], **out, scientific_verdict=None))
    print("CHECK2 EQUAL" if all2 else "CHECK2 DIFFERENCES", "| r11 equal (LoD2):", out["r11_all_equal"],
          "| unexpected switch changes:", {s: len(v) for s, v in out["switches_unexpected"].items()})


if __name__ == "__main__":
    main()
