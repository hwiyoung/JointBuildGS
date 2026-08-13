#!/usr/bin/env python3
"""X4 paired analysis: ARRGS vs E2/E8 on the confirmed-93 (evaluated subset),
overall + 3-layer standard cuts (fill-dependent = E2 comp@0.25 < 0.9)."""
import csv
import json
from pathlib import Path

import numpy as np

BASE = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/"
            "phase-payloads/p2/arrgs_v1")
rows = list(csv.DictReader(open(BASE / "evaluation/rows.csv")))

by = {}
for r in rows:
    by.setdefault((r["stable_id"], r["gt"]), {})[r["arm"]] = r

METRICS = ["f1@0.5", "completeness@0.25", "precision@0.5", "acc_median",
           "z_spread", "normal_med_deg"]

def num(r, m):
    v = r.get(m, "")
    return float(v) if v not in ("", None) else None


def collect(gt):
    out = []
    for (sid, g), arms in by.items():
        if g != gt or "ARRGS" not in arms or "E2" not in arms or "E8" not in arms:
            continue
        if any(num(arms[a], "f1@0.5") is None or num(arms[a], "completeness@0.25") is None
               for a in ("E2", "E8", "ARRGS")):
            continue  # empty-metric rows (flagged buildings)
        out.append((sid, arms))
    return out

report = {}
for gt in ("e1", "lod2"):
    data = collect(gt)
    layers = {
        "all": data,
        "fill_dep(E2comp<0.9)": [d for d in data if float(d[1]["E2"]["completeness@0.25"]) < 0.9],
        "current_dom": [d for d in data if float(d[1]["E2"]["completeness@0.25"]) >= 0.9],
    }
    report[gt] = {}
    for lname, ldata in layers.items():
        if not ldata:
            continue
        med = {}
        for m in METRICS:
            for arm in ("E2", "E8", "ARRGS"):
                vals = [float(d[1][arm][m]) for d in ldata if d[1][arm][m]]
                med[f"{arm}.{m}"] = round(float(np.median(vals)), 3)
        wins = sum(1 for d in ldata
                   if float(d[1]["ARRGS"]["f1@0.5"]) > float(d[1]["E8"]["f1@0.5"]))
        report[gt][lname] = {"n": len(ldata), "medians": med,
                             "ARRGS>E8_f1_wins": wins}
json.dump(report, open(BASE / "evaluation/x4_paired_summary.json", "w"), indent=1)
for gt in report:
    for lname, r in report[gt].items():
        m = r["medians"]
        print(f"[{gt}|{lname}] n={r['n']} | f1 E2 {m['E2.f1@0.5']} E8 {m['E8.f1@0.5']} "
              f"ARRGS {m['ARRGS.f1@0.5']} | comp {m['E2.completeness@0.25']}/"
              f"{m['E8.completeness@0.25']}/{m['ARRGS.completeness@0.25']} | "
              f"acc {m['ARRGS.acc_median']} z {m['ARRGS.z_spread']} | wins {r['ARRGS>E8_f1_wins']}")
