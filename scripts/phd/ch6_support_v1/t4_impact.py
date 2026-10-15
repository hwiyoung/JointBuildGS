"""impact of a building offset on the pre-training judgment, for a list of (range, prior, building) (scratch helper)."""
import sys, json
import numpy as np
sys.path.insert(0, "/repo/scripts/phd/ch6_support_v1")
from ch6_common import OUT, DR, footprint_index, labels_of, rule
for rid, prior, b in [("R3E", "LoD2", "4959461"), ("R5", "LoD2", "4906985"), ("B0", "LoD2", "4959459"), ("R3E", "LoD2", "4906985"), ("B0", "LoD2", "4959460"), ("R4", "LoD2", "4906989")]:
    U = np.load(OUT / "t5/s03" / rid / prior / "units.npz")
    lab, med, tau, ex = labels_of(OUT / "t5/gt" / rid, prior, rid)
    fp, names = footprint_index(DR / "s02" / rid / "footprints.json", U["loc_center"][:, :2])
    idx = [i for i, n in enumerate(names) if b in n][0]
    roof = U["loc_kind"] == 1
    m = U["loc_in_range"].astype(bool) & ~ex & (fp == idx) & (lab >= 0)
    g = float(np.median(med[m & roof]))
    rel = U["J_loc"] == rule.J_CONFLICT
    a = U["loc_area"]
    fc = m & rel & (np.abs(med - g) <= tau)
    print(rid, prior, b, "g", round(g, 3), "patches", int(m.sum()), "area", round(float(a[m].sum()), 1), "released", round(float(a[m & rel].sum()), 1),
          "false_conflict", round(float(a[fc].sum()), 1), "wrong_after", round(float(a[m & (np.abs(med - g) > tau)].sum()), 1), "share_rel", round(float(a[m & rel].sum() / a[m].sum()), 3))
