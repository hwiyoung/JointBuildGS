"""Supplementary numbers for the verdict of PHD-STAGE2-R6-FIX-v1 (jointbuildgs:dev, CPU, no training).

  python supp_r6.py      # mounts: /s2 (ro), /s1 (ro), /r6 (rw), /audit (ro), /code (this directory)

(1) fix 4 sensitivity: kept initial prior points per face type when the depth tolerance of the initial visibility test is
    0.5 (r6), 0.3, 0.2, 0.1 or 0.05 m (M and L, nominal scene); same seeing test as init_filter_counts.py.
(2) fix 2 sensitivity: at the last E update before the reset (r6: 3000), prior disks with E < 0.5 by distance from their
    initial disk in multiples of tau; how many more would be protected at 5, 6, 8 tau.
(3) 'protected disks stay in place': disks protected at iteration 1 and still protected at 3500 (r5 and r6), distance
    from the initial disk; disks protected at 3000 and at 3500, movement between the two (unique init ids only).
Writes /r6/out/supp_r6.json and /r6/out/csv/supp_*.csv."""
import csv
import importlib.util
import json
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("ifc", "/code/init_filter_counts.py")
src = Path("/code/init_filter_counts.py").read_text()
head = src[:src.index("rows, poly_rows, summary = [], [], {}")]     # helpers only, no side effects
ns = {"__name__": "ifc"}
exec(compile(head, "init_filter_counts.py", "exec"), ns)
OUT = Path("/r6/out"); (OUT / "csv").mkdir(parents=True, exist_ok=True)
res = {}

# (1) tolerance sensitivity of the initial visibility filter
from plyfile import PlyData  # noqa: E402
import os  # noqa: E402
rows1 = []
for key in (() if os.environ.get("SUPP_SKIP_12") else ("M_N", "L_N")):
    cond, mesh_file, dmax = ns["SETS"][key]
    ply = PlyData.read(str(ns["S2"] / "runs" / cond / "scene/sparse/0/points3D.ply"))["vertex"]
    xyz = np.stack([np.asarray(ply[c], np.float64) for c in "xyz"], 1)[np.load(ns["S2"] / "runs" / cond / "scene/sparse/0/origin.npy") == 1]
    typ, poly, dist, target = ns["classify"](xyz, mesh_file, dmax)
    for tol in (0.5, 0.3, 0.2, 0.1, 0.05):
        ns["TOL"] = tol
        cnt = ns["seeing_counts"](xyz, cond, f"prior_{key}")
        keep = cnt > 0
        r = dict(set=key, tol=tol, kept=int(keep.sum()), **{f"kept_{t}": int((keep & (typ == t)).sum()) for t in ("roof", "wall", "ground", "other")},
                 kept_ground_3401=int((keep & (poly == 3401) & (typ == "ground")).sum()),
                 kept_roof_target=int((keep & (typ == "roof") & target).sum()), kept_wall_target=int((keep & (typ == "wall") & target).sum()),
                 kept_main_roof_3396=int((keep & (poly == 3396)).sum()), n_main_roof_3396=int((poly == 3396).sum()))
        rows1.append(r)
        print(r, flush=True)
    ns["TOL"] = 0.5
if rows1:
    res["init_tolerance"] = rows1
    with open(OUT / "csv/supp_init_tolerance.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows1[0].keys())); w.writeheader(); [w.writerow(r) for r in rows1]

# (2) distance of E < 0.5 prior disks at the last pre-reset E update
TAU = 0.05677034870849456
rows2 = []
for s in ("N", "B"):
    z = np.load(f"/r6/runs/{s}/audit/E/E_03000.npz")
    low = z["E"] < 0.5
    d = z["drift"][low]
    r = dict(scene=s, n_prior=int(len(z["E"])), n_E_below_05=int(low.sum()), protected=int(z["prot"].sum()))
    for m in (4, 5, 6, 8, 12):
        r[f"within_{m}tau"] = int((d <= m * TAU).sum())
    r["hidden_E_below_05"] = int((low & (z["cnt"] == 0)).sum())
    r["far_hidden"] = int((low & (z["cnt"] == 0) & (z["drift"] > 4 * TAU)).sum())
    r["far_seen"] = int((low & (z["cnt"] > 0) & (z["drift"] > 4 * TAU)).sum())
    r["far_drift_p50"] = float(np.median(d[d > 4 * TAU])) if (d > 4 * TAU).any() else float("nan")
    rows2.append(r); print(r, flush=True)
res["drift_threshold"] = rows2
with open(OUT / "csv/supp_drift_threshold.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows2[0].keys())); w.writeheader(); [w.writerow(r) for r in rows2]

# (3) do protected disks stay in place?
runs = {"r5_N": ("/audit/runs/A", 1, 3001), "r5_B": ("/audit/runs/A_bias", 1, 3001), "r6_N": ("/r6/runs/N", 1, 3000), "r6_B": ("/r6/runs/B", 1, 3000)}
rows3 = []
for tag, (root, i_first, i_pre) in runs.items():
    dmp = dict(np.load(f"{root}/model/dump/iteration_3500/gaussians.npz"))   # load once (NpzFile re-reads on every access)
    prior = dmp["origin"] == 1; lk = dmp["locked"].astype(bool)
    ids = dmp["init_id"].astype(np.int64); disp = np.linalg.norm(dmp["displacement"], axis=1)
    z1 = dict(np.load(f"{root}/audit/E/E_{i_first:05d}.npz"))
    coh = np.isin(ids, z1["init_id"][z1["prot"].astype(bool)]) & prior & lk
    zp = dict(np.load(f"{root}/audit/E/E_{i_pre:05d}.npz"))
    u, c = np.unique(ids[prior], return_counts=True)
    u2, c2 = np.unique(zp["init_id"], return_counts=True)
    pre_ids = zp["init_id"][zp["prot"].astype(bool)]
    ok_ids = np.intersect1d(u2[c2 == 1], u[c == 1])
    pre_ids = np.intersect1d(pre_ids, ok_ids)
    pre_rows = np.nonzero(np.isin(zp["init_id"], pre_ids))[0]
    pos_pre = dict(zip(zp["init_id"][pre_rows].tolist(), zp["xyz"][pre_rows]))
    sel = np.isin(ids, pre_ids) & prior & lk
    xyz_end = dmp["xyz"]
    mv = np.array([np.linalg.norm(xyz_end[k] - pos_pre[int(ids[k])]) for k in np.nonzero(sel)[0]]) if sel.any() else np.zeros(0)
    r = dict(run=tag, n_cohort_first=int(coh.sum()), cohort_first_drift_p50=float(np.median(disp[coh])) if coh.any() else float("nan"),
             cohort_first_drift_p90=float(np.percentile(disp[coh], 90)) if coh.any() else float("nan"),
             n_protected_pre_and_end=int(sel.sum()), move_pre_to_end_p50=float(np.median(mv)) if mv.size else float("nan"),
             move_pre_to_end_p90=float(np.percentile(mv, 90)) if mv.size else float("nan"),
             move_pre_to_end_max=float(mv.max()) if mv.size else float("nan"), pre_iteration=i_pre)
    rows3.append(r); print(r, flush=True)
res["stay_in_place"] = rows3
with open(OUT / "csv/supp_stay_in_place.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows3[0].keys())); w.writeheader(); [w.writerow(r) for r in rows3]
(OUT / "supp_r6.json").write_text(json.dumps(res, indent=1))
