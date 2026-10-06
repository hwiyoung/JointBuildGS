"""PHD-MAIN-PREP-DISCARD-RULE-v1 5.2: the four boxes scored with the prep v1.1 fixed values and with the new fixed values
(train-only MVS of the ranges), current rule only, inside each box's evaluation range (jointbuildgs:dev, CPU).

  python box_compare.py      -> tables/box_rescore.json, tables/box_rescore.csv

v1.1 = prep step06/box_stage1 + box_gt; new = s52/box + s52/box_gt (same box MVS, new tau / registration). Counted as in
rules_eval.py: patches in range, not excluded, true label agree or conflict; support / missing / invisible; discard = support
conflict | missing propagated conflict; unplanted LoD2 patches = missing & propagated conflict (ALS: TIN vertices seated on them).
scientific_verdict: null."""
import csv
import json

import numpy as np

from common import OUT, PREP, inside_range, jdump, log
from rules_eval import BOXES, eval_box_mask, labels_of
from src.phd.prior_propagation_v5 import locations as locs
from src.phd.prior_propagation_v5 import rule
from src.phd.prior_propagation_v5 import surfaces as surf


def seats(md, U, shift):
    """rules_eval.als_seats with the mesh folder given (the prep box summaries do not record it; prep step06/mesh = s02_box, eq1)."""
    m = dict(np.load(md / "als_mesh.npz"))
    Vv = m["V"].astype(np.float64) + shift; F = m["F"].astype(np.int64); ts = m["tri_surface"].astype(np.int64)
    eligible = np.zeros(int(ts.max()) + 2, bool)
    for r_ in json.loads((md / "als_surfaces.json").read_text())["surfaces"]:
        eligible[r_["ext"]] = True
    vs = surf.vertex_surface(F, ts, eligible)
    ci = np.where(vs >= 0, locs.compact_index(U, np.maximum(vs, 0)), -1)
    seat = np.full(len(Vv), -1, np.int64); has = ci >= 0
    seat[has] = locs.locate(U, ci[has], Vv[has])
    return seat, inside_range(Vv[:, :2], json.loads((md / "range.json").read_text()))


def score(run, gt_dir, md, box, bid, prior):
    U = locs.load_store(run / "units.npz")
    summ = json.loads((run / "summary.json").read_text())
    shift = np.asarray(summ["registration"]["shift_applied"], np.float64)
    m = eval_box_mask(U, bid, shift)
    lab, med, tau, ex, src = labels_of(gt_dir, prior, box)
    st, vote, J = U["state"], U["vote"], U["J"]
    disc = ((st == rule.ST_SUPPORT) & (vote == rule.V_CONFLICT)) | ((st == rule.ST_MISSING) & (J == rule.J_CONFLICT))
    base = U["loc_in_range"] & ~ex & (lab >= 0) & m
    vis = base & (st != rule.ST_INVISIBLE)
    up = (st == rule.ST_MISSING) & (J == rule.J_CONFLICT)
    o = dict(box=box, prior=prior, tau_roof=round(summ["tolerance"]["roof"]["tau"], 3), tau_wall=round(summ["tolerance"]["wall"]["tau"], 3),
             shift=[round(float(x), 3) for x in shift], patches=int(base.sum()),
             support=int((base & (st == rule.ST_SUPPORT)).sum()), missing=int((base & (st == rule.ST_MISSING)).sum()),
             invisible=int((base & (st == rule.ST_INVISIBLE)).sum()),
             correct_discard=int((vis & disc & (lab == 1)).sum()), wrong_discard=int((vis & disc & (lab == 0)).sum()),
             correct_keep=int((vis & ~disc & (lab == 0)).sum()), wrong_keep=int((vis & ~disc & (lab == 1)).sum()))
    if prior == "LoD2":
        o["unplanted"] = int((up & U["loc_in_range"] & m).sum())
    else:
        seat, inr_v = seats(md, U, shift); ok = inr_v & (seat >= 0)
        o["unplanted"] = int((ok & m[np.maximum(seat, 0)] & up[np.maximum(seat, 0)]).sum())
    return o


def main():
    rows = []
    for box, bid in BOXES.items():
        for prior in ("LoD2", "ALS"):
            for tag, run, gt, md in (("v1.1", PREP / "step06/box_stage1" / box / prior, PREP / "step06/box_gt" / box, PREP / "step06/mesh" / box),
                                     ("new", OUT / "s52/box" / box / prior, OUT / "s52/box_gt" / box, OUT / "s02_box" / box)):
                rows.append(dict(values=tag, **score(run, gt, md, box, bid, prior)))
    jdump(OUT / "tables/box_rescore.json", dict(rule=__doc__.split("\n\n")[1], rows=rows, scientific_verdict=None))
    keys = list(rows[0])
    with open(OUT / "tables/box_rescore.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows([{k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()} for r in rows])
    log("box_rescore", len(rows))


if __name__ == "__main__":
    main()
