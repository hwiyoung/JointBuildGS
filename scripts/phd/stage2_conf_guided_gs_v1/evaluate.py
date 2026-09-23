"""Stage-2 evaluation (jointbuildgs:dev, CPU; ORDER_ko_v1 sections 4.5, 6.6, 9). scientific_verdict: null.

  python evaluate.py --iteration 30000 [--conds P_L_N P_M_N ...] [--render_tag render]

Per condition and face, from the calibrated renders of render_depths.py (/s2/eval/<COND>/<tag>_<it>/<view>_depth.npy,
training resolution) and the stage-2 maps (resampled nearest, exactly like the training read-out):
  d  = median((D - P) f) over face pixels with A = 1      (+ = prior above / outward of the render)
  e  = median((D - M) f) over face pixels with A = 1      (+ = MVS above / outward)
  g  = median((D - G) f) over face pixels with GT         (+ = GT above / outward)   evaluation only
  cov = sum A / |F|; labels preserve / correct / undecided / other with the condition's tau_v (ORDER 4.5)
f = vertical conversion on roof faces, surface-normal conversion on walls (inputs/prepare_report.json 'conversion').
The 15 views (13 train + 2 test) are pooled; the walls are pooled into one group.
Outputs (/s2/eval): faces_<it>.csv (all conditions), compare_conditions_<it>.csv (P-P0, P0-O, P-I per face),
appearance.csv (test PSNR/SSIM/LPIPS from each run's metric.txt, own camera model), gaussians_<it>.csv (disk records)."""
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
EVAL = S2 / "eval"
ALL = ["P_L_N", "P_L_B", "P_M_N", "P_M_B", "P0_L_N", "P0_L_B", "P0_M_N", "P0_M_B", "O_M_N", "O_M_B", "I"]
PAIRS = [("P_L_N", "P0_L_N"), ("P_L_B", "P0_L_B"), ("P_M_N", "P0_M_N"), ("P_M_B", "P0_M_B"),
         ("P0_M_N", "O_M_N"), ("P0_M_B", "O_M_B"),
         ("P_L_N", "I"), ("P_M_N", "I"), ("P_L_B", "I"), ("P_M_B", "I")]

ap = argparse.ArgumentParser()
ap.add_argument("--iteration", type=int, default=30000)
ap.add_argument("--conds", nargs="+", default=ALL)
ap.add_argument("--render_tag", default="render")
a = ap.parse_args()
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]


def load(setname, view, size, dtype=np.float32):
    p = MAPS / setname / "raw_depth" / f"{view}.npy"
    if not p.exists():
        p = MAPS / setname / f"{view}.npy"
    if not p.exists():
        return None
    x = np.load(p)
    if x.shape != (size[1], size[0]):
        x = cv2.resize(x.astype(np.float32), size, interpolation=cv2.INTER_NEAREST)
    return x.astype(dtype)


def med_nmad(chunks):
    x = np.concatenate(chunks).astype(np.float64) if chunks else np.zeros(0)
    if x.size == 0:
        return float("nan"), float("nan"), 0
    m = float(np.median(x))
    return m, float(1.4826 * np.median(np.abs(x - m))), int(x.size)


def label(cov, d, e, tau):
    if not np.isfinite(cov) or not np.isfinite(tau):
        return "n/a"
    if cov < 0.5:
        return "undecided"
    if np.isfinite(d) and abs(d) < tau:
        return "preserve"
    if np.isfinite(d) and np.isfinite(e) and abs(e) < tau:
        return "correct"
    return "other"


def prior_set(cond):
    c = json.loads((S2 / "runs" / cond / "condition.json").read_text())
    if c["mode"] == "I":
        return None, float("nan"), c
    return f"prior_{c['prior']}_{c['scene']}", float(c["tau_v"]), c


rows = []
for cond in a.conds:
    rdir = EVAL / cond / f"{a.render_tag}_{a.iteration}"
    rec_path = rdir / "receipt.json"
    if not rec_path.exists():
        print("skip (no render)", cond)
        continue
    pset, tau, cinfo = prior_set(cond)
    views = sorted(json.loads(rec_path.read_text())["views"])
    acc = {f: dict(d=[], e=[], g=[], d_all=[], n_pixels=0, n_A=0) for f in ROOF + ["wall"]}
    for v in views:
        D = np.load(rdir / f"{v}_depth.npy").astype(np.float32)
        size = (D.shape[1], D.shape[0])
        rendered = np.isfinite(D) & (D > 0)
        A = load("conf", v, size); M = load("mvs", v, size); G = load(GT_SET, v, size); FV = load("fvert", v, size)
        F = load("faceid", v, size, np.int32)
        P = load(pset, v, size) if pset else None
        a1 = A > 0
        for name, members in [(f, [f]) for f in ROOF] + [("wall", WALL)]:
            fm = np.isin(F, members)
            if not fm.any():
                continue
            r = acc[name]
            r["n_pixels"] += int(fm.sum()); r["n_A"] += int((fm & a1).sum())
            if P is not None:
                pm = fm & rendered & np.isfinite(P) & (P > 0)
                r["d_all"].append(((D - P) * FV)[pm]); r["d"].append(((D - P) * FV)[pm & a1])
            em = fm & a1 & rendered & np.isfinite(M) & (M > 0)
            r["e"].append(((D - M) * FV)[em])
            gm = fm & rendered & np.isfinite(G) & (G > 0)
            r["g"].append(((D - G) * FV)[gm])
    for name in ROOF + ["wall"]:
        r = acc[name]
        d, dn, nd = med_nmad(r["d"]); e, en, ne = med_nmad(r["e"]); g, gn, ng = med_nmad(r["g"]); da, dan, nda = med_nmad(r["d_all"])
        cov = r["n_A"] / r["n_pixels"] if r["n_pixels"] else float("nan")
        rows.append(dict(iteration=a.iteration, condition=cond, mode=cinfo["mode"], prior=cinfo.get("prior"), scene=cinfo["scene"],
                         face=name, axis="normal" if name == "wall" else "vertical", n_pixels=r["n_pixels"], n_A=r["n_A"], cov=cov,
                         d=d, d_nmad=dn, n_d=nd, d_all=da, d_all_nmad=dan, e=e, e_nmad=en, n_e=ne, g=g, g_nmad=gn, n_g=ng,
                         tau_v=tau, label=label(cov, d, e, tau)))
    print(cond, {r["face"]: (round(r["g"], 3), r["label"]) for r in rows if r["condition"] == cond})

EVAL.mkdir(parents=True, exist_ok=True)
if rows:
    with (EVAL / f"faces_{a.iteration}.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

# ---- condition differences (a - b): negative d|g| = a closer to GT
by = {(r["condition"], r["face"]): r for r in rows}
comp = []
for ca, cb in PAIRS:
    for face in ROOF + ["wall"]:
        ra, rb = by.get((ca, face)), by.get((cb, face))
        if ra is None or rb is None:
            continue
        same_prior = (ra["prior"], ra["scene"]) == (rb["prior"], rb["scene"])
        comp.append(dict(iteration=a.iteration, a=ca, b=cb, face=face, abs_g_a=abs(ra["g"]), abs_g_b=abs(rb["g"]),
                         delta_abs_g=abs(ra["g"]) - abs(rb["g"]), delta_g_nmad=ra["g_nmad"] - rb["g_nmad"],
                         delta_d=(ra["d"] - rb["d"]) if same_prior else float("nan"), delta_e=ra["e"] - rb["e"],
                         label_a=ra["label"], label_b=rb["label"]))
if comp:
    with (EVAL / f"compare_conditions_{a.iteration}.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(comp[0])); w.writeheader(); w.writerows(comp)

# ---- appearance: each run's own training_report (test views, own camera model)
app = []
for cond in ALL:
    mt = S2 / "runs" / cond / "model" / "metric.txt"
    if mt.exists():
        for line in mt.read_text().split():
            it, psnr, ssim, lp = line.split("_")
            app.append(dict(condition=cond, iteration=int(it), psnr=float(psnr), ssim=float(ssim), lpips=float(lp)))
if app:
    with (EVAL / "appearance.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(app[0])); w.writeheader(); w.writerows(app)

# ---- disk records from the in-training dump (P/P0/I)
grows = []
for cond in a.conds:
    npz = S2 / "runs" / cond / "model" / "dump" / f"iteration_{a.iteration}" / "gaussians.npz"
    if not npz.exists():
        continue
    z = np.load(npz)
    o, lk, op = z["origin"], z["locked"].astype(bool), z["opacity"]
    disp = np.linalg.norm(z["displacement"], axis=1)
    pr = o == 1
    init_prior = z["init_origin"] == 1
    removed = init_prior & (z["init_last_seen"] < a.iteration)
    q = lambda x, p: float(np.nanpercentile(x, p)) if x.size else float("nan")  # noqa: E731
    grows.append(dict(condition=cond, iteration=a.iteration, n=int(o.size), n_prior=int(pr.sum()), n_image=int((~pr).sum()),
                      n_locked=int(lk.sum()), n_prior_free=int((pr & ~lk).sum()),
                      init_prior=int(init_prior.sum()), init_prior_removed=int(removed.sum()),
                      E_prior_lt05=int((pr & (z["E"] < 0.5)).sum()), E_prior_ge05=int((pr & (z["E"] >= 0.5)).sum()),
                      opacity_p50_locked=q(op[lk], 50), opacity_p50_prior_free=q(op[pr & ~lk], 50), opacity_p50_image=q(op[~pr], 50),
                      disp_p50_locked=q(disp[lk], 50), disp_p90_locked=q(disp[lk], 90),
                      disp_p50_prior_free=q(disp[pr & ~lk], 50), disp_p90_prior_free=q(disp[pr & ~lk], 90)))
if grows:
    with (EVAL / f"gaussians_{a.iteration}.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(grows[0])); w.writeheader(); w.writerows(grows)
print("wrote", len(rows), "face rows,", len(comp), "comparisons,", len(app), "appearance rows,", len(grows), "disk rows")
