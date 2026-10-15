"""PHD-CH6-SUPPORT-v1 task 4, a stricter reading added AFTER seeing the pre-registered classes (jointbuildgs:dev, CPU).
Why: the pre-registered 'prior_offset_case' only asked GT - prior to have the sign of MVS - prior and a median above its NMAD;
it called buildings cases whose offset was the range-wide residual left below the registration gate (R1 ALS: GT about 4 cm above
every building) or whose MVS was the wrong side (R1 42364663: MVS 1 m above, GT 5 cm). Recorded beside the pre-registered
classes, never replacing them.

  python t4_strict.py

Per range and prior: G_r = median over the range's buildings of g_b (GT - prior). A building is a strict case when
  S1 its GT offset differs from the range's common offset beyond its own spread: |g_b - G_r| > sg_b
  S2 the MVS sees the deviation in the same direction: sign(m_b - M_r) = sign(g_b - G_r), M_r = range median of m_b
     (first version: |m_b - g_b| <= max(s_b, sg_b); dropped R3E 4906985 whose MVS doubled a 0.2 m GT offset, so replaced)
  S3 not a change: not in the survey list, |g_b| <= 2 m, sg_b < |g_b - G_r| (a shift of the whole roof, not a part), and for
     LoD2 the airborne LiDAR of the same building agrees with the GT: |g_b(ALS) - G_r(ALS)| <= tau(ALS) (when the ALS row exists)
  S4 effect: |g_b - G_r| >= tau of the range and prior (also written: |g_b| / tau, the offset the judgment meets when the
     registration left the common part)
Writes /out/t4/strict.csv and strict.json. scientific_verdict: null."""
import csv
import json
from collections import defaultdict

import numpy as np

from ch6_common import OUT, jdump

CHANGE_IDS = ("4959326", "4907510", "4907508", "4907207")


def f(x):
    return float(x) if x not in ("", None) else np.nan


def main():
    rows = list(csv.DictReader(open(OUT / "t4/buildings.csv")))
    G = defaultdict(list)
    for r in rows:
        if np.isfinite(f(r["g_b"])):
            G[(r["range"], r["prior"])].append(f(r["g_b"]))
    Gr = {k: float(np.median(v)) for k, v in G.items()}
    M = defaultdict(list)
    for r in rows:
        M[(r["range"], r["prior"])].append(f(r["m_b"]))
    Mr = {k: float(np.median(v)) for k, v in M.items()}
    als = {(r["range"], r["building"]): r for r in rows if r["prior"] == "ALS"}
    out = []
    for r in rows:
        if not r["primary"] == "True":
            continue
        g, sg, m, s, tau = f(r["g_b"]), f(r["sg_b"]), f(r["m_b"]), f(r["s_b"]), f(r["tau_roof"])
        if not np.isfinite(g):
            continue
        gr = Gr[(r["range"], r["prior"])]
        d = g - gr
        s1 = abs(d) > sg
        s2 = np.sign(m - Mr[(r["range"], r["prior"])]) == np.sign(d)
        a = als.get((r["range"], r["building"]))
        als_ok = None
        if r["prior"] == "LoD2" and a is not None and np.isfinite(f(a["g_b"])):
            als_ok = abs(f(a["g_b"]) - Gr[(r["range"], "ALS")]) <= f(a["tau_roof"])
        s3 = (not any(c in r["building"] for c in CHANGE_IDS)) and abs(g) <= 2.0 and sg < abs(d) and (als_ok is not False)
        s4 = abs(d) >= tau
        out.append(dict(range=r["range"], prior=r["prior"], building=r["building"], roof_area_m2=r["roof_area_m2"], m_b=m, s_b=s, g_b=g, sg_b=sg,
                        range_common_g=round(gr, 4), g_minus_common=round(d, 4), tau=tau, ratio=round(abs(d) / tau, 3), abs_ratio=round(abs(g) / tau, 3), range_common_m=round(Mr[(r['range'], r['prior'])], 4),
                        als_g_minus_common=(round(f(a["g_b"]) - Gr[(r["range"], "ALS")], 4) if (r["prior"] == "LoD2" and a is not None and np.isfinite(f(a["g_b"]))) else ""),
                        S1=s1, S2=s2, S3=s3, S4=s4, strict_case=bool(s1 and s2 and s3), strict_case_effect=bool(s1 and s2 and s3 and s4),
                        preregistered=r["cls"]))
    keys = list(out[0])
    with open(OUT / "t4/strict.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(sorted(out, key=lambda x: (x["prior"], -x["ratio"])))
    summ = {}
    for p in ("LoD2", "ALS"):
        P = [x for x in out if x["prior"] == p]
        summ[p] = dict(buildings=len(P), strict_cases=sum(x["strict_case"] for x in P), strict_cases_effect=sum(x["strict_case_effect"] for x in P),
                       cases=[(x["range"], x["building"], x["g_minus_common"], x["ratio"]) for x in P if x["strict_case"]],
                       range_common_g={k[0]: round(v, 4) for k, v in Gr.items() if k[1] == p})
    jdump(OUT / "t4/strict.json", dict(rule=__doc__.split("\n\n")[2], summary=summ, scientific_verdict=None))
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
