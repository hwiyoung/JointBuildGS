"""PHD-MAIN-PREP-DISCARD-RULE-v1 5.4: the discard-rule variants against the true labels (jointbuildgs:dev, CPU; rules,
counting and regions fixed in configs discard_v1.json before any result).

  python rules_eval.py [--stage1 s52/s03] [--gt s52/gt] [--box-stage1 s52/box] [--box-gt s52/box_gt] [--out rules]

Per run (7 ranges = selection region, 4 boxes = confirmation region) and prior: the states / votes / propagated judgments of
every variant (prior_propagation_v5.rules on the pass-3 tallies and the gathered support ids; 'current' must reproduce the
stored votes and judgments exactly), then per face kind (roof, wall) and measured (support) / unmeasured (missing):
correct / wrong discard, correct / wrong keep (wrong keep by |GT - prior| / base tau in (1, 2], (2, 4], > 4), and the
unplanted points (LoD2 patches, ALS TIN vertices). Patches: in range, not excluded, true label agree or conflict; invisible
patches apart. Selection = range patches outside every box evaluation range, counted once (priority B0, R1, R2, R3E, R4, R5,
SW); confirmation = box patches inside the box's evaluation range. B0 labels = gt_clean where it has a label, else the ULS
supplement (prep v1.1 5.3). Sites (sites_v1.json): per rule the decisions on the site's patches.
Writes <out>/counts.json, counts_long.csv, sites.json, decisions/<run>_<prior>.npz (per rule discard flags). scientific_verdict: null."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from common import CFG, DCFG, OUT, PREP, REPO, inside_range, jdump, log, xy_to_uv
from src.phd.prior_propagation_v5 import locations as locs
from src.phd.prior_propagation_v5 import rule
from src.phd.prior_propagation_v5 import rules as R
from src.phd.prior_propagation_v5 import surfaces as surf

RANGES = ["B0", "R1", "R2", "R3E", "R4", "R5", "SW"]          # = the dedupe priority
BOXES = {"B0_b10": "B0", "B173nb_b10": "B173nb", "B173_b0": "B173", "R1rep_b10": "R1rep"}
RULE_NAMES = list(R.RULES)
BINS = [(1, 2), (2, 4), (4, np.inf)]


def labels_of(gt_dir, prior, rid):
    G = np.load(gt_dir / f"labels_{prior}.npz")
    lab, med, tau, ex = G["label"].astype(np.int8), G["gt_med"].astype(np.float64), G["tau"].astype(np.float64), G["excluded"]
    src = np.zeros(len(lab), np.int8)
    if rid.startswith("B0") and (gt_dir / f"labels_uls_{prior}.npz").exists():
        Gu = np.load(gt_dir / f"labels_uls_{prior}.npz")
        use = (lab < 0) & (Gu["label"] >= 0)
        lab = np.where(use, Gu["label"], lab).astype(np.int8); med = np.where(use, Gu["gt_med"], med); src[use] = 1
        ex = ex | (use & Gu["excluded"])
    return lab, med, tau, ex, src


def als_seats(run_dir, U, shift):
    summ = json.loads((run_dir / "summary.json").read_text())
    md = Path(summ["mesh_dir"]) if "mesh_dir" in summ else None
    m = dict(np.load(md / "als_mesh.npz"))
    Vv = m["V"].astype(np.float64) + shift; F = m["F"].astype(np.int64); ts = m["tri_surface"].astype(np.int64)
    tab = json.loads((md / "als_surfaces.json").read_text())["surfaces"]
    eligible = np.zeros(int(ts.max()) + 2, bool)
    for r_ in tab:
        eligible[r_["ext"]] = True
    vs = surf.vertex_surface(F, ts, eligible)
    ci = np.where(vs >= 0, locs.compact_index(U, np.maximum(vs, 0)), -1)
    seat = np.full(len(Vv), -1, np.int64); has = ci >= 0
    seat[has] = locs.locate(U, ci[has], Vv[has])
    return Vv, seat


def prepare(run_dir, gt_dir, rid, prior):
    """every variant's states / votes / judgments / discard flags of one run (rule-independent inputs loaded once)."""
    U = locs.load_store(run_dir / "units.npz")
    pairs = dict(np.load(run_dir / "unit_view_pairs.npz"))
    kn = np.load(run_dir / "knn.npz")
    summ = json.loads((run_dir / "summary.json").read_text())
    shift = np.asarray(summ["registration"]["shift_applied"], np.float64)
    jc = CFG["judgment"]; q, k, r = jc["majority"], int(jc["min_evidence"]), float(jc["max_distance_m"])
    L = len(U["state"])
    lab, med, tau, ex, src = labels_of(gt_dir, prior, rid)
    P = dict(U=U, shift=shift, lab=lab, med=med, tau=tau, ex=ex, src=src, prior=prior, J={}, disc={})
    for name in RULE_NAMES:
        st_r, vote_r, J_r, disc = R.apply(pairs, L, kn["mis"], kn["k_dist"], kn["k_id"], name, q, k, r)
        if not np.array_equal(st_r, U["state"]):
            raise RuntimeError(f"{rid} {prior} {name}: states differ from the stored ones")
        if name == "current":
            P["check"] = dict(vote_equal=bool(np.array_equal(vote_r, U["vote"])), J_equal=bool(np.array_equal(J_r, U["J"])))
            if not all(P["check"].values()):
                raise RuntimeError(f"{rid} {prior}: the offline current rule does not reproduce the stored votes / judgments {P['check']}")
        P["J"][name] = J_r; P["disc"][name] = disc
    if prior == "ALS":
        Vv, seat = als_seats(run_dir, U, shift)
        P["seat"] = seat; P["inr_v"] = inside_range(Vv[:, :2], json.loads((Path(summ["mesh_dir"]) / "range.json").read_text()))
    return P


def count(P, region):
    U, lab, med, tau, ex = P["U"], P["lab"], P["med"], P["tau"], P["ex"]
    base = U["loc_in_range"] & ~ex & (lab >= 0) & region
    kind = U["loc_kind"]; st = U["state"]
    ratio = np.abs(med) / np.where(tau > 0, tau, np.nan)
    out = {}
    for name in RULE_NAMES:
        disc, J_r = P["disc"][name], P["J"][name]
        c = {}
        for kn_, kv in (("roof", 1), ("wall", 2)):
            if P["prior"] == "ALS" and kv == 2:
                continue
            for mn, sv in (("measured", rule.ST_SUPPORT), ("unmeasured", rule.ST_MISSING)):
                m = base & (kind == kv) & (st == sv)
                wk = m & ~disc & (lab == 1)
                c[f"{kn_}_{mn}"] = dict(n=int(m.sum()), true_agree=int((m & (lab == 0)).sum()), true_conflict=int((m & (lab == 1)).sum()),
                                        correct_discard=int((m & disc & (lab == 1)).sum()), wrong_discard=int((m & disc & (lab == 0)).sum()),
                                        correct_keep=int((m & ~disc & (lab == 0)).sum()), wrong_keep=int(wk.sum()),
                                        wrong_keep_by_ratio={f"{a_}-{b_}": int((wk & (ratio > a_) & (ratio <= b_)).sum()) for a_, b_ in BINS})
            mi = base & (kind == kv) & (st == rule.ST_INVISIBLE)
            c[f"{kn_}_invisible"] = dict(n=int(mi.sum()), true_agree=int((mi & (lab == 0)).sum()), true_conflict=int((mi & (lab == 1)).sum()))
        up = (st == rule.ST_MISSING) & (J_r == rule.J_CONFLICT)
        if P["prior"] == "LoD2":
            upr = up & U["loc_in_range"] & region
            c["unplanted"] = dict(patches=int(upr.sum()), area_m2=round(float(U["loc_area"][upr].sum()), 2))
        else:
            seat, inr_v = P["seat"], P["inr_v"]
            vm = inr_v & (seat >= 0)
            vreg = np.zeros(len(seat), bool); vreg[vm] = region[seat[vm]]
            c["unplanted"] = dict(points=int((vm & vreg & up[np.maximum(seat, 0)]).sum()), points_in_region=int((inr_v & vreg).sum()))
        out[name] = c
    return out, dict(n_base=int(base.sum()), b0_label_source_uls=int((base & (P["src"] == 1)).sum()))


def eval_box_mask(U, box_id, shift):
    b = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"][box_id]
    uv = xy_to_uv(U["loc_center"][:, :2] + shift[:2])
    return (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage1", default="s52/s03"); ap.add_argument("--gt", default="s52/gt")
    ap.add_argument("--box-stage1", default="s52/box"); ap.add_argument("--box-gt", default="s52/box_gt"); ap.add_argument("--out", default="rules")
    a = ap.parse_args()
    O = OUT / a.out; (O / "decisions").mkdir(parents=True, exist_ok=True)
    rngs = json.loads((PREP / "step01/ranges.json").read_text())
    boxes = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"]
    res = dict(selection={}, confirmation={}, checks={})
    rows = []
    for idx, rid in enumerate(RANGES):
        for prior in ("LoD2", "ALS"):
            run = OUT / a.stage1 / rid / prior
            U = locs.load_store(run / "units.npz")
            shift = np.asarray(json.loads((run / "summary.json").read_text())["registration"]["shift_applied"], np.float64)
            uv = xy_to_uv(U["loc_center"][:, :2] + shift[:2])
            in_eval = np.zeros(len(uv), bool)
            for b in [boxes[k] for k in ("B0", "B173nb", "B173", "R1rep")]:
                in_eval |= (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1])
            earlier = np.zeros(len(uv), bool)
            for rp in RANGES[:idx]:
                earlier |= inside_range(U["loc_center"][:, :2] + shift[:2], rngs[rp])
            Pp = prepare(run, OUT / a.gt / rid, rid, prior)
            per_range, info = count(Pp, ~in_eval)
            agg, info2 = count(Pp, ~in_eval & ~earlier)
            dec, chk = Pp["disc"], Pp["check"]
            res["selection"][f"{rid}/{prior}"] = dict(per_range=per_range, aggregate_part=agg, info=info, info_aggregate=info2)
            res["checks"][f"{rid}/{prior}"] = chk
            np.savez_compressed(O / "decisions" / f"{rid}_{prior}.npz", **{n: d for n, d in dec.items()})
            for name, c in per_range.items():
                for part, v in c.items():
                    if "n" in v and "wrong_discard" in v:
                        rows.append(dict(region="selection", run=rid, prior=prior, rule=name, part=part, **{kk: vv for kk, vv in v.items() if not isinstance(vv, dict)},
                                         **{f"wrong_keep_{kk}": vv for kk, vv in v["wrong_keep_by_ratio"].items()}))
            log("selection", rid, prior, "patches", info["n_base"])
    for box, bid in BOXES.items():
        for prior in ("LoD2", "ALS"):
            run = OUT / a.box_stage1 / box / prior
            U = locs.load_store(run / "units.npz")
            shift = np.asarray(json.loads((run / "summary.json").read_text())["registration"]["shift_applied"], np.float64)
            m = eval_box_mask(U, bid, shift)
            Pp = prepare(run, OUT / a.box_gt / box, box, prior)
            c, info = count(Pp, m)
            dec, chk = Pp["disc"], Pp["check"]
            res["confirmation"][f"{box}/{prior}"] = dict(counts=c, info=info)
            res["checks"][f"{box}/{prior}"] = chk
            np.savez_compressed(O / "decisions" / f"{box}_{prior}.npz", **{n: d for n, d in dec.items()})
            for name, cc in c.items():
                for part, v in cc.items():
                    if "n" in v and "wrong_discard" in v:
                        rows.append(dict(region="confirmation", run=box, prior=prior, rule=name, part=part, **{kk: vv for kk, vv in v.items() if not isinstance(vv, dict)},
                                         **{f"wrong_keep_{kk}": vv for kk, vv in v["wrong_keep_by_ratio"].items()}))
            log("confirmation", box, prior, "patches", info["n_base"])
    # selection aggregate (deduplicated) per prior, part and rule
    aggr = {}
    for key, v in res["selection"].items():
        prior = key.split("/")[1]
        for name, c in v["aggregate_part"].items():
            for part, x in c.items():
                if "wrong_discard" not in x:
                    continue
                t = aggr.setdefault(prior, {}).setdefault(part, {}).setdefault(name, dict(n=0, true_agree=0, true_conflict=0, correct_discard=0, wrong_discard=0,
                                                                                       correct_keep=0, wrong_keep=0, wrong_keep_by_ratio={f"{a_}-{b_}": 0 for a_, b_ in BINS}))
                for kk in ("n", "true_agree", "true_conflict", "correct_discard", "wrong_discard", "correct_keep", "wrong_keep"):
                    t[kk] += x[kk]
                for kk in t["wrong_keep_by_ratio"]:
                    t["wrong_keep_by_ratio"][kk] += x["wrong_keep_by_ratio"][kk]
    res["selection_aggregate"] = aggr
    jdump(O / "counts.json", dict(rule=__doc__.split("\n\n")[1], rules=R.RULES, **res, scientific_verdict=None))
    keys = sorted({k for r_ in rows for k in r_})
    with open(O / "counts_long.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print("rules done", len(rows), "rows; current-rule checks", all(all(v.values()) for v in res["checks"].values()))


if __name__ == "__main__":
    main()
