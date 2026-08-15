#!/usr/bin/env python3
"""Oracle backbone vs E2/E8 on the confirmed-93, stratified by change tier.

Hypotheses under test at population scale (from the B022/B036/B173 contrast):
  H-a: oracle ~ E8 on unchanged buildings (deterministic backbone is enough)
  H-b: oracle degrades specifically on change-tier buildings (stale prior),
       i.e. oracle-vs-current mismatch IS a change signal.
"""
import csv
import json
from pathlib import Path

import numpy as np

BASE = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/"
            "phase-payloads/p2/arrgs_v1")
LBL = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/"
           "phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1/labels/"
           "change_label_candidates_v1.csv")

rows = list(csv.DictReader(open(BASE / "evaluation/rows.csv")))
tier = {}
for r in csv.DictReader(open(LBL)):
    tier[r["stable_id"]] = r["tier"][0]  # A/B/C or N(A)

by = {}
for r in rows:
    if r["gt"] != "e1":
        continue
    by.setdefault(r["stable_id"], {})[r["arm"]] = r


def num(r, k):
    v = r.get(k, "")
    return float(v) if v not in ("", None) else None


data = []
for sid, arms in by.items():
    if not all(a in arms for a in ("E2", "E8", "ARRGS_ORACLE")):
        continue
    vals = {}
    ok = True
    for a in ("E2", "E8", "ARRGS_ORACLE", "ARRGS"):
        if a in arms:
            f = num(arms[a], "f1@0.5")
            c = num(arms[a], "completeness@0.25")
            acc = num(arms[a], "acc_median")
            if a != "ARRGS" and (f is None or c is None):
                ok = False
            vals[a] = (f, c, acc)
    if ok:
        data.append((sid, tier.get(sid, "N"), vals))

print(f"평가 유효 {len(data)}동 (e1-GT)")


def med(sel, arm, idx):
    v = [d[2][arm][idx] for d in sel if arm in d[2] and d[2][arm][idx] is not None]
    return float(np.median(v)) if v else float("nan")


LAYERS = [("전체", lambda t: True), ("A(변화후보)", lambda t: t == "A"),
          ("B(비변화선언)", lambda t: t == "B"), ("C(일치)", lambda t: t == "C"),
          ("N(판정불능→93내)", lambda t: t == "N")]
print(f"{'층':16s} {'n':>3s} | {'E2':>6s} {'E8':>6s} {'ORACLE':>7s} {'(opt)':>6s} | ORC acc | ORC>E8 승")
out = {}
for lname, cond in LAYERS:
    sel = [d for d in data if cond(d[1])]
    if not sel:
        continue
    wins = sum(1 for d in sel
               if d[2]["ARRGS_ORACLE"][0] is not None and d[2]["E8"][0] is not None
               and d[2]["ARRGS_ORACLE"][0] > d[2]["E8"][0])
    row = {"n": len(sel),
           "E2": round(med(sel, "E2", 0), 3), "E8": round(med(sel, "E8", 0), 3),
           "ORACLE": round(med(sel, "ARRGS_ORACLE", 0), 3),
           "opt": round(med(sel, "ARRGS", 0), 3),
           "ORACLE_acc": round(med(sel, "ARRGS_ORACLE", 2), 2),
           "wins_vs_E8": wins}
    out[lname] = row
    print(f"{lname:16s} {row['n']:3d} | {row['E2']:6.3f} {row['E8']:6.3f} "
          f"{row['ORACLE']:7.3f} {row['opt']:6.3f} | {row['ORACLE_acc']:7.2f} | {wins}/{row['n']}")

# H-b: oracle 결손(E8−oracle f1)이 티어별로 다른가 + 개별 급락 목록
gap = sorted(((d[0], d[1], d[2]["E8"][0] - d[2]["ARRGS_ORACLE"][0]) for d in data
              if d[2]["E8"][0] is not None and d[2]["ARRGS_ORACLE"][0] is not None),
             key=lambda x: -x[2])
print("\n오라클 결손 상위 10 (E8−ORACLE f1 — 변화/스테일 신호 후보):")
for sid, t, g in gap[:10]:
    print(f"  {t} {sid} Δ{g:+.3f}")
json.dump({"layers": out,
           "top_gaps": [{"sid": s, "tier": t, "gap": round(g, 3)} for s, t, g in gap[:20]],
           "scientific_verdict": None},
          open(BASE / "evaluation/oracle_paired_summary.json", "w"), indent=1)
print("\nsaved evaluation/oracle_paired_summary.json")
