"""Intent check of stage 2 (jointbuildgs:dev, CPU): did the result do what the stage-1 judgment says, and was that right?

  python eval_intent.py [--iteration 30000]

Every target-building pixel (6 roof faces + 12 walls, 15 views, training resolution) is put in one judgment class from the
inputs only (the condition's prior P, MVS depth M, observation map A, per-pixel width tau_p):
  agree      A=1 and |M - P| <= tau_p      photos and prior agree      -> intended: keep the prior (and the photos)
  conflict   A=1 and |M - P| >  tau_p      photos contradict the prior -> intended: follow the photos
  unobserved A=0 (prior present)           photos cannot measure       -> intended: keep the prior
For I (no prior) the classes use prior_M_N so the image-only result is read at the same places.
Per class: share of pixels; followed = % of pixels where the final render D obeys the intent (agree/unobserved: |D-P| <= tau_p,
conflict: |D-M| <= tau_p); also % within tau of P and of M; median |D-G|, |M-G|, |P-G| in metres (vertical on roofs, surface
normal on walls; GT = JBGS_GT_SET, default gt_clean from make_gt_clean.py: hidden-surface points removed and the cloud lowered
7.46 cm to the open-ground datum; evaluation only).
Output: /s2/eval/intent_<it>.csv"""
import os
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")   # evaluation GT maps: gt_clean (visibility + ground datum, make_gt_clean.py) or gt (raw)

S2 = Path("/s2")
MAPS = S2 / "inputs/maps"
ALL = ["P_M_N", "P0_M_N", "O_M_N", "I", "P_L_N", "P0_L_N", "P_M_B", "P0_M_B", "O_M_B", "P_L_B", "P0_L_B"]
ap = argparse.ArgumentParser()
ap.add_argument("--iteration", type=int, default=30000)
a = ap.parse_args()
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]
cache = {}


def load(setname, view, size, dtype=np.float32):
    key = (setname, view, size)
    if key not in cache:
        p = MAPS / setname / "raw_depth" / f"{view}.npy"
        x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy")
        cache[key] = cv2.resize(x.astype(np.float32), size, interpolation=cv2.INTER_NEAREST).astype(dtype)
    return cache[key]


rows = []
for cond in ALL:
    c = json.loads((S2 / "runs" / cond / "condition.json").read_text())
    prior = f"prior_{c['prior']}_{c['scene']}" if c["mode"] != "I" else "prior_M_N"
    tau = f"tau_{c['prior']}" if c["mode"] != "I" else "tau_M"
    rdir = S2 / "eval" / cond / f"render_{a.iteration}"
    views = sorted(json.loads((rdir / "receipt.json").read_text())["views"])
    acc = {}
    for v in views:
        D = np.load(rdir / f"{v}_depth.npy")
        size = (D.shape[1], D.shape[0])
        A, M, P, T = load("conf", v, size), load("mvs", v, size), load(prior, v, size), load(tau, v, size)
        G, FV, F = load(GT_SET, v, size), load("fvert", v, size), load("faceid", v, size, np.int32)
        base = (D > 0) & np.isfinite(P) & (P > 0) & np.isfinite(T)
        hasM = np.isfinite(M) & (M > 0)
        cls = {"agree": base & (A > 0) & hasM & (np.abs(M - P) <= T),
               "conflict": base & (A > 0) & hasM & (np.abs(M - P) > T),
               "unobserved": base & (A <= 0)}
        for region, rmask in (("roof", np.isin(F, ROOF)), ("wall", np.isin(F, WALL))):
            for k, m in cls.items():
                m = m & rmask
                r = acc.setdefault((region, k), dict(n=0, keepP=0, followM=0, nM=0, dg=[], mg=[], pg=[]))
                r["n"] += int(m.sum())
                r["keepP"] += int((m & (np.abs(D - P) <= T)).sum())
                mm = m & hasM
                r["nM"] += int(mm.sum())
                r["followM"] += int((mm & (np.abs(D - M) <= T)).sum())
                g = m & np.isfinite(G) & (G > 0)
                r["dg"].append((np.abs(D - G) * FV)[g])
                r["pg"].append((np.abs(P - G) * FV)[g])
                r["mg"].append((np.abs(M - G) * FV)[g & hasM])
    tot = {reg: sum(acc[(reg, k)]["n"] for k in ("agree", "conflict", "unobserved")) for reg in ("roof", "wall")}
    for (region, k), r in acc.items():
        med = lambda x: float(np.median(np.concatenate(x))) if sum(len(y) for y in x) else float("nan")  # noqa: E731
        followed = r["followM"] / r["nM"] if k == "conflict" else r["keepP"] / max(r["n"], 1)
        rows.append(dict(iteration=a.iteration, condition=cond, region=region, cls=k, n=r["n"],
                         share=r["n"] / max(tot[region], 1), followed=followed if r["n"] else float("nan"),
                         within_tau_P=r["keepP"] / max(r["n"], 1), within_tau_M=(r["followM"] / r["nM"]) if r["nM"] else float("nan"),
                         err_result=med(r["dg"]), err_photos=med(r["mg"]), err_prior=med(r["pg"])))
    print(cond, "done", flush=True)

with (S2 / "eval" / f"intent_{a.iteration}.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for region in ("roof", "wall"):
    print(f"\n== {region}: class share | followed% | |D-G| (|M-G|, |P-G|) m")
    for cond in ALL:
        cells = []
        for k in ("agree", "conflict", "unobserved"):
            r = next(x for x in rows if x["condition"] == cond and x["region"] == region and x["cls"] == k)
            cells.append(f"{k[:5]} {r['share']*100:4.1f}% F{r['followed']*100:5.1f}% e{r['err_result']:.3f} ({r['err_photos']:.3f},{r['err_prior']:.3f})")
        print(f"{cond:7s} | " + " | ".join(cells))
