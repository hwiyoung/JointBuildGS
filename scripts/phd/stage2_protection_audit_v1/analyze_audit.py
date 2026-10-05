"""Analysis of the 4.4 audit runs (PHD-STAGE2-PROTECTION-AUDIT-v1). Runs in Docker (jointbuildgs:dev), read-only on inputs.

  python analyze_audit.py            # /audit = audit payload, /s2 = stage-2 payload (ro), /s1 = stage-1 payload (ro)

Writes /audit/out/{results.json, csv/*.csv, figures/*.png, summary_4_4.png}. Every number quoted in the report comes
from results.json or the CSVs. Independent recomputations (E by the document's definition, E by the implementation's
definition) use numpy, the COLMAP binaries of the scene and the calibration file; they do not import the fork."""
import csv
import json
import math
import struct
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
from matplotlib.colors import Normalize
from matplotlib.path import Path as MPath

AU, S2, S1 = Path("/audit"), Path("/s2"), Path("/s1")
OUT = AU / "out"; CSV = OUT / "csv"; FIG = OUT / "figures"
for d in (OUT, CSV, FIG):
    d.mkdir(parents=True, exist_ok=True)
RUNS = ["A", "B", "C", "A_bias"]
COND = {"A": "P_M_N", "B": "P_M_N", "C": "P_M_N", "A_bias": "P_M_B"}
PRIOR_SET = {"P_M_N": "prior_M_N", "P_M_B": "prior_M_B"}
H, W = 1157, 1600
TOL, THR = 0.5, 0.5
R = {}                                                             # results.json
COL = {"A": "tab:blue", "B": "tab:red", "C": "tab:green", "A_bias": "tab:purple"}


def rd_csv(p):
    rows = list(csv.DictReader(open(p)))
    out = {}
    for k in rows[0]:
        try:
            out[k] = np.array([float(r[k]) if r[k] not in ("", "None") else np.nan for r in rows])
        except ValueError:
            out[k] = np.array([r[k] for r in rows])
    return out


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def nanmed(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(np.median(x)) if x.size else float("nan")


def write_csv(name, header, rows):
    with open(CSV / name, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def rmean(x, k=25):
    x = np.asarray(x, float)
    out = np.full_like(x, np.nan)
    for i in range(len(x)):
        seg = x[max(0, i - k // 2): i + k // 2 + 1]
        seg = seg[np.isfinite(seg)]
        out[i] = np.median(seg) if seg.size else np.nan
    return out


steps = {r: rd_csv(AU / "runs" / r / "audit/steps.csv") for r in RUNS}
opac = {r: rd_csv(AU / "runs" / r / "audit/opacity.csv") for r in RUNS}
Eup = {r: rd_csv(AU / "runs" / r / "audit/E_updates.csv") for r in RUNS}
dens = {r: jl(AU / "runs" / r / "audit/densify.jsonl") for r in RUNS}
final = {r: np.load(AU / "runs" / r / "audit/final.npz") for r in RUNS}
meta = {r: json.loads((AU / "runs" / r / "audit/meta.json").read_text()) for r in RUNS}
rec = {r: json.loads((AU / "runs" / r / "receipt.json").read_text()) for r in RUNS}
scal = {r: [json.loads(l) for l in open(AU / "runs" / r / "model/monitor/scalars.jsonl")] for r in RUNS}
E_iters = meta["A"]["E_iterations"]
first_E, last_E = E_iters[0], E_iters[-1]
R["runs"] = {r: dict(seconds=rec[r]["seconds"], status=rec[r]["status"], iterations=rec[r]["iterations"],
                     condition=COND[r], variant=meta[r]["variant"], lock_lr_scale=meta[r]["lock_lr_scale"],
                     lock_opacity_floor=meta[r]["lock_opacity_floor"], c_scale=meta[r]["c_scale"]) for r in RUNS}
R["optimizer"] = meta["A"]["optimizer"]
R["schedule"] = {k: meta["A"][k] for k in ("opacity_reset_interval", "densify_from_iter", "densify_until_iter",
                                         "densification_interval", "opacity_cull", "lambda_normal", "lambda_dist",
                                         "depth_ratio", "E_iterations")}

# ============================================================================== check 1: where the 0.01 acts
c1 = {}
it = steps["A"]["iteration"]
wins = {"1-500": (1, 500), "501-3000": (501, 3000), "3001-3500": (3001, 3500), "all": (1, 3500)}
rows = []
for g in ("prot", "free", "img"):
    for q in ("xyz", "rot", "scale"):
        for stat in ("med", "mean", "act_med"):
            key = f"{g}_{q}_{stat}"
            for wname, (a, b) in wins.items():
                m = (it >= a) & (it <= b)
                vals = {r: nanmed(steps[r][key][m]) for r in ("A", "B", "C")}
                with np.errstate(divide="ignore", invalid="ignore"):
                    ratAB = steps["A"][key][m] / steps["B"][key][m]
                    ratCB = steps["C"][key][m] / steps["B"][key][m]
                    ratAC = steps["A"][key][m] / steps["C"][key][m]
                rows.append([g, q, stat, wname, vals["A"], vals["B"], vals["C"], nanmed(ratAB), nanmed(ratCB), nanmed(ratAC),
                             vals["A"] / vals["B"] if vals["B"] else float("nan"), vals["C"] / vals["B"] if vals["B"] else float("nan")])
write_csv("check1_step_ratios.csv", ["group", "param", "stat", "window", "A_median_over_iters", "B_median_over_iters",
                                     "C_median_over_iters", "A_over_B_median_of_ratios", "C_over_B_median_of_ratios",
                                     "A_over_C_median_of_ratios", "A_over_B_ratio_of_medians", "C_over_B_ratio_of_medians"], rows)
c1["ratios"] = {f"{r[0]}_{r[1]}_{r[2]}_{r[3]}": dict(A=r[4], B=r[5], C=r[6], A_over_B=r[7], C_over_B=r[8], A_over_C=r[9],
                                                     A_over_B_of_medians=r[10], C_over_B_of_medians=r[11]) for r in rows}
for r in ("A", "C"):
    s = steps[r]
    c1[f"{r}_applied_over_raw_xyz"] = dict(median_over_iters=nanmed(s["prot_applied_over_raw_xyz_med"]),
                                           mean_over_iters=nanmed(s["prot_applied_over_raw_xyz_mean"]))
    c1[f"{r}_zero_frac"] = {q: {w: nanmed(s[f"prot_{q}_zero_frac"][(it >= a) & (it <= b)]) for w, (a, b) in wins.items()}
                            for q in ("xyz", "rot", "scale")}
    c1[f"{r}_zero_frac_first_iter_above_half"] = int(it[np.argmax(s["prot_xyz_zero_frac"] > 0.5)]) if (s["prot_xyz_zero_frac"] > 0.5).any() else None
c1["B_zero_frac_xyz_all"] = nanmed(steps["B"]["prot_xyz_zero_frac"])
c1["free_img_zero_frac_A"] = dict(free=nanmed(steps["A"]["free_xyz_zero_frac"]), img=nanmed(steps["A"]["img_xyz_zero_frac"]))
c1["n_prot_per_E_update"] = {r: {int(i): int(n) for i, n in zip(Eup[r]["iteration"], Eup[r]["n_prot"])} for r in RUNS}
c1["n_prot_zero_any"] = {r: bool((Eup[r]["n_prot"] == 0).any()) for r in RUNS}
c1["lr"] = dict(xyz_first=float(steps["A"]["lr_xyz"][0]), xyz_last=float(steps["A"]["lr_xyz"][-1]),
                rot=float(steps["A"]["lr_rot"][0]), scale=float(steps["A"]["lr_scale"][0]), fdc=float(steps["A"]["lr_fdc"][0]),
                frest=float(steps["A"]["lr_frest"][0]))

# end-of-run drift from the initial position (init_id -> initial disk)
e1 = {r: np.load(AU / "runs" / r / f"audit/E/E_{first_E:05d}.npz") for r in RUNS}
drift_rows = []
c1["drift_end"] = {}
for r in RUNS:
    f = final[r]
    prior = f["origin"] == 1
    prot = f["prot"].astype(bool)
    d = f["drift"]
    ids = f["init_id"]
    coh_ids = e1[r]["init_id"][e1[r]["prot"].astype(bool)]            # protected at the first E update (identical set)
    coh = np.isin(ids, coh_ids) & prior
    orig = np.zeros(len(ids), bool)                                    # rows that are the initial disk itself
    u, cnt = np.unique(ids[ids >= 0], return_counts=True)
    single = set(u[cnt == 1].tolist())
    orig = np.array([i in single for i in ids]) & coh
    vals = dict(prot_end=nanmed(d[prior & prot]), n_prot_end=int((prior & prot).sum()),
                free_end=nanmed(d[prior & ~prot]), n_free_end=int((prior & ~prot).sum()),
                img_end=nanmed(d[~prior]), cohort_first_prot=nanmed(d[coh]), n_cohort=int(coh.sum()),
                cohort_single=nanmed(d[orig]), n_cohort_single=int(orig.sum()),
                prot_end_p90=float(np.nanpercentile(d[prior & prot], 90)) if (prior & prot).any() else float("nan"),
                cohort_p90=float(np.nanpercentile(d[coh], 90)) if coh.any() else float("nan"))
    c1["drift_end"][r] = vals
    drift_rows.append([r] + [vals[k] for k in vals])
write_csv("check1_drift_end.csv", ["run"] + list(c1["drift_end"]["A"].keys()), drift_rows)
c1["drift_end_ratio"] = {k: dict(A_over_B=c1["drift_end"]["A"][k] / c1["drift_end"]["B"][k],
                                 C_over_B=c1["drift_end"]["C"][k] / c1["drift_end"]["B"][k])
                         for k in ("prot_end", "cohort_first_prot", "cohort_single")}
c1["first_E_prot_identical_ABC"] = bool(np.array_equal(np.sort(e1["A"]["init_id"][e1["A"]["prot"].astype(bool)]),
                                                     np.sort(e1["B"]["init_id"][e1["B"]["prot"].astype(bool)])) and
                                        np.array_equal(np.sort(e1["A"]["init_id"][e1["A"]["prot"].astype(bool)]),
                                                       np.sort(e1["C"]["init_id"][e1["C"]["prot"].astype(bool)])))
toy = json.loads((OUT / "toy/toy_adam_summary.json").read_text())
c1["toy"] = toy
R["check1"] = c1
per_iter = []
for i in range(len(it)):
    per_iter.append([int(it[i])] + [steps[r][f"{g}_xyz_med"][i] for r in ("A", "B", "C") for g in ("prot", "free", "img")] +
                    [steps[r][f"prot_xyz_mean"][i] for r in ("A", "B", "C")] + [steps[r]["prot_xyz_zero_frac"][i] for r in ("A", "C")])
write_csv("check1_step_per_iteration.csv", ["iteration"] + [f"{r}_{g}_xyz_med_over_lr" for r in ("A", "B", "C") for g in ("prot", "free", "img")]
          + [f"{r}_prot_xyz_mean_over_lr" for r in ("A", "B", "C")] + ["A_prot_xyz_zero_frac", "C_prot_xyz_zero_frac"], per_iter)

# ============================================================================== check 2: E, view selection
c2 = {}


def read_colmap_images(p):
    out = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack("<i", f.read(4))[0]
            q = struct.unpack("<4d", f.read(32)); t = struct.unpack("<3d", f.read(24)); cid = struct.unpack("<i", f.read(4))[0]
            name = b""
            while True:
                ch = f.read(1)
                if ch == b"\x00":
                    break
                name += ch
            npts = struct.unpack("<Q", f.read(8))[0]
            f.read(24 * npts)
            out[Path(name.decode()).stem] = (np.array(q), np.array(t), cid)
    return out


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


train_views = json.loads((AU / "runs/A/model/monitor/meta.json").read_text())["train_views"]
imgs = {c: read_colmap_images(S2 / "runs" / c / "scene/sparse/0/images.bin") for c in ("P_M_N", "P_M_B")}
calib = {c: json.loads((S2 / "runs" / c / "scene/jbgs_calibration.json").read_text())["images"] for c in ("P_M_N", "P_M_B")}
SP = Path("/artifacts/JointBuildGS/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt")
cam_full = [l.split() for l in (SP / "cameras.txt").read_text().splitlines() if l.strip() and not l.startswith("#")][0]
Wf, Hf = int(cam_full[2]), int(cam_full[3]); fxf, fyf, cxf, cyf = map(float, cam_full[4:8])
imgs_full = {}
for l in (SP / "images.txt").read_text().splitlines():
    t = l.split()
    if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
        imgs_full[Path(t[9]).stem] = (np.array([float(x) for x in t[1:5]]), np.array([float(x) for x in t[5:8]]))
pose_diff = max(float(np.abs(q2R(imgs["P_M_N"][v][0]) - q2R(imgs_full[v][0])).max() + np.abs(imgs["P_M_N"][v][1] - imgs_full[v][1]).max())
                for v in train_views)
c2["pose_max_abs_diff_scene_vs_fullres_txt"] = pose_diff


def load_map(setname, v, full=False, dtype=np.float32):
    p = S2 / "inputs/maps" / setname / "raw_depth" / f"{v}.npy"
    a = np.load(p).astype(np.float32)
    if full:
        return a
    return cv2.resize(a, (W, H), interpolation=cv2.INTER_NEAREST).astype(dtype)   # = jbgs_judgment._load_set


A_tr = {v: load_map("conf", v) for v in train_views}
A_full = {v: np.load(S2 / "inputs/maps/conf/raw_depth" / f"{v}.npy") for v in train_views}
P_tr = {c: {v: load_map(PRIOR_SET[c], v) for v in train_views} for c in ("P_M_N", "P_M_B")}


def E_numpy(xyz, cond, mode):
    """mode: 'doc' (no occlusion), 'impl' (|z - P| < 0.5 with the prior depth), 'doc_full' (no occlusion, full-res
    stage-1 A map, COLMAP pixel convention floor(u))."""
    n = len(xyz); s = np.zeros(n); c = np.zeros(n)
    for v in train_views:
        if mode == "doc_full":
            q, t = imgs_full[v]; Rm = q2R(q)
            Xc = xyz @ Rm.T + t; z = Xc[:, 2]
            u = fxf * Xc[:, 0] / z + cxf; w = fyf * Xc[:, 1] / z + cyf
            ui, vi = np.floor(u).astype(np.int64), np.floor(w).astype(np.int64)
            ins = (z > 0.01) & (ui >= 0) & (ui < Wf) & (vi >= 0) & (vi < Hf)
            Av = A_full[v][np.clip(vi, 0, Hf - 1), np.clip(ui, 0, Wf - 1)]
            sees = ins
        else:
            q, t, _ = imgs[cond][v]; Rm = q2R(q); K = np.array(calib[cond][v]["K"])
            Xc = xyz @ Rm.T + t; z = Xc[:, 2]
            u = K[0, 0] * Xc[:, 0] / z + K[0, 2]; w = K[1, 1] * Xc[:, 1] / z + K[1, 2]
            ui, vi = np.round(u).astype(np.int64), np.round(w).astype(np.int64)     # rasterizer pixel centres at integers
            ins = (z > 0.01) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
            Av = A_tr[v][np.clip(vi, 0, H - 1), np.clip(ui, 0, W - 1)]
            if mode == "doc":
                sees = ins
            else:
                Pv = P_tr[cond][v][np.clip(vi, 0, H - 1), np.clip(ui, 0, W - 1)]
                sees = ins & np.isfinite(Pv) & (np.abs(z - Pv) < TOL)
        s[sees] += Av[sees]; c[sees] += 1
    return np.where(c > 0, s / np.maximum(c, 1), 0.0), c


rng = np.random.default_rng(20260928)
samp_rows = []
c2["independent"] = {}
for r in ("A", "A_bias"):
    for iE in (first_E, last_E):
        z = np.load(AU / "runs" / r / f"audit/E/E_{iE:05d}.npz")
        n = len(z["E"]); idx = rng.choice(n, size=min(1000, n), replace=False)
        xyz = z["xyz"][idx].astype(np.float64)
        Ei = z["E"][idx].astype(np.float64); prot_i = z["prot"][idx].astype(bool); drift = z["drift"][idx]
        res, per = {}, {}
        for mode in ("impl", "doc", "doc_full"):
            Ex, cx_ = E_numpy(xyz, COND[r], mode)
            prot_x = Ex < THR
            if mode == "impl":                                   # the implementation's rule incl. the off-prior exception
                prot_x = prot_x & ~((cx_ == 0) & (drift > TOL))
            per[mode] = (Ex, cx_, prot_x)
            res[mode] = dict(match_E=float((np.abs(Ex - Ei) < 1e-6).mean()), match_prot=float((prot_x == prot_i).mean()),
                             prot_rate=float(prot_x.mean()), mean_abs_dE=float(np.abs(Ex - Ei).mean()),
                             cnt_median=float(np.median(cx_)), cnt_match=float((cx_ == z["cnt"][idx]).mean()) if mode == "impl" else None)
        res["impl_prot_rate"] = float(prot_i.mean())
        c2["independent"][f"{r}_{iE}"] = res
        for j in range(len(idx)):
            samp_rows.append([r, iE, int(z["row"][idx[j]]), float(Ei[j]), int(z["cnt"][idx[j]]), bool(prot_i[j])] +
                             [v for mode in ("impl", "doc", "doc_full") for v in (float(per[mode][0][j]), int(per[mode][1][j]), bool(per[mode][2][j]))])
write_csv("check2_independent_sample.csv", ["run", "E_iteration", "row", "E_impl", "cnt_impl", "prot_impl",
                                            "E_reimpl", "cnt_reimpl", "prot_reimpl", "E_doc_trainres", "cnt_doc_trainres",
                                            "prot_doc_trainres", "E_doc_fullres", "cnt_doc_fullres", "prot_doc_fullres"], samp_rows)

# distributions at the first and last E update (run A) and the biased-scene occlusion comparison
S1J = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
crop = np.array(S1J["als_crop_local_xy"])
ring = MPath(np.array(next(p for p in S1J["polygons"] if p["poly_index"] == 3396)["ring_local_xy"]))
dist_rows = []
c2["dist"] = {}
for r in ("A", "A_bias", "B", "C"):
    for iE in (first_E, last_E):
        z = np.load(AU / "runs" / r / f"audit/E/E_{iE:05d}.npz")
        E, cnt, prot = z["E"], z["cnt"], z["prot"].astype(bool)
        hist = np.histogram(E, bins=[0, 1e-9, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0 + 1e-9])[0]
        ch = np.bincount(np.minimum(cnt.astype(int), 13), minlength=14)
        d = dict(n_prior=int(len(E)), prot_rate=float(prot.mean()), n_prot=int(prot.sum()), n_cnt0=int((cnt == 0).sum()),
                 cnt0_rate=float((cnt == 0).mean()), E_eq0=int((E == 0).sum()), E_eq05=int((E == 0.5).sum()),
                 E_hist=hist.tolist(), cnt_hist=ch.tolist(), cnt_median=float(np.median(cnt)),
                 cnt_median_seen=float(np.median(cnt[cnt > 0])) if (cnt > 0).any() else float("nan"),
                 off_prior=int(z["off_prior"].sum()),
                 prot_doc_rate=float(z["prot_doc"].mean()), prot_rend_rate=float(z["prot_rend"].mean()),
                 cnt_doc_median=float(np.median(z["cnt_doc"])), cnt_rend0=int((z["cnt_rend"] == 0).sum()))
        c2["dist"][f"{r}_{iE}"] = d
        dist_rows.append([r, iE] + [d[k] for k in ("n_prior", "n_prot", "prot_rate", "n_cnt0", "cnt0_rate", "E_eq0", "E_eq05",
                                                    "cnt_median", "cnt_median_seen", "off_prior", "prot_doc_rate", "prot_rend_rate")]
                         + d["E_hist"] + d["cnt_hist"])
write_csv("check2_E_distributions.csv", ["run", "E_iteration", "n_prior", "n_prot", "prot_rate", "n_cnt0", "cnt0_rate", "n_E_eq0",
                                         "n_E_eq_0.5", "cnt_median", "cnt_median_seen", "n_off_prior", "prot_rate_doc_definition",
                                         "prot_rate_render_occlusion"]
          + ["E_bin_0", "E_0-0.1", "E_0.1-0.2", "E_0.2-0.3", "E_0.3-0.4", "E_0.4-0.5", "E_0.5-0.6", "E_0.6-0.7", "E_0.7-0.8",
             "E_0.8-0.9", "E_0.9-1"] + [f"cnt_{i}" for i in range(13)] + ["cnt_13"], dist_rows)

occ_rows = []
c2["occlusion"] = {}
rings = {f: MPath(np.array(next(p for p in S1J["polygons"] if p["poly_index"] == f)["ring_local_xy"]))
         for f in (3387, 3389, 3393, 3394, 3396, 3404)}
pre_reset_E = max(i for i in E_iters if i < 3000) if any(i < 3000 for i in E_iters) else last_E
c2["occlusion_iterations"] = [pre_reset_E, last_E]
for r in ("A_bias", "A"):
    for iE in (pre_reset_E, last_E):
        z = np.load(AU / "runs" / r / f"audit/E/E_{iE:05d}.npz")
        init = np.load(AU / "runs" / r / "audit/init.npz")["init_xyz"]
        ids = z["init_id"]; ixy = init[np.maximum(ids, 0), :2]
        face = {f: rings[f].contains_points(ixy) & (ids >= 0) for f in rings}
        anyroof = np.zeros(len(ids), bool)
        for f in face:
            anyroof |= face[f]
        E, Er, Ed = z["E"], z["E_rend"], z["E_doc"]
        pi, prd, pdc = z["prot"].astype(bool), z["prot_rend"].astype(bool), z["prot_doc"].astype(bool)
        out = {}
        subsets = [("all", np.ones(len(ids), bool))] + [(f"roof_{f}", face[f]) for f in (3396, 3394, 3389, 3387, 3404, 3393)] + \
                  [("not_target_roof", ~anyroof)]
        for name, m in subsets:
            dE = np.abs(E - Er)[m]
            out[name] = dict(n=int(m.sum()), n_dE_gt0=int((dE > 1e-6).sum()), n_dE_gt025=int((dE > 0.25).sum()),
                             mean_dE=float(dE.mean()) if dE.size else float("nan"),
                             prot_impl=int(pi[m].sum()), prot_rend=int(prd[m].sum()), prot_doc=int(pdc[m].sum()),
                             impl_not_rend=int((pi & ~prd)[m].sum()), rend_not_impl=int((prd & ~pi)[m].sum()),
                             impl_not_doc=int((pi & ~pdc)[m].sum()), doc_not_impl=int((pdc & ~pi)[m].sum()),
                             drift_med=nanmed(z["drift"][m]), opacity_med=nanmed(z["opacity"][m]),
                             drift_med_rend_not_impl=nanmed(z["drift"][m & prd & ~pi]),
                             drift_med_impl_not_rend=nanmed(z["drift"][m & pi & ~prd]),
                             cnt_med=nanmed(z["cnt"][m]), cnt_rend_med=nanmed(z["cnt_rend"][m]))
            occ_rows.append([r, iE, name] + [out[name][k] for k in out[name]])
        c2["occlusion"][f"{r}_{iE}"] = out
write_csv("check2_occlusion_prior_vs_render.csv", ["run", "E_iteration", "subset", "n_prior", "n_dE_gt0", "n_dE_gt0.25", "mean_abs_dE",
                                                   "prot_impl_prior_depth", "prot_render_depth", "prot_doc_no_occlusion",
                                                   "impl_not_render", "render_not_impl", "impl_not_doc", "doc_not_impl",
                                                   "drift_median", "opacity_median", "drift_med_render_not_impl",
                                                   "drift_med_impl_not_render", "cnt_median_impl", "cnt_median_render"], occ_rows)
c2["E_updates_A"] = {k: Eup["A"][k].tolist() for k in ("iteration", "n_prot", "n_prot_doc", "n_prot_rend", "flip_impl_not_doc",
                                                      "flip_doc_not_impl", "flip_impl_not_rend", "flip_rend_not_impl",
                                                      "n_prior_cnt0", "n_off_prior")}
c2["E_updates_A_bias"] = {k: Eup["A_bias"][k].tolist() for k in ("iteration", "n_prot", "n_prot_doc", "n_prot_rend",
                                                                "flip_impl_not_rend", "flip_rend_not_impl")}
R["check2"] = c2

# ============================================================================== check 3: opacity floor and reset
c3 = {}
o = opac["A"]
c3["render_nbelow_iters"] = {int(i): int(n) for i, n in zip(o["iteration"], o["render_nbelow"]) if n > 0}
c3["newly_render_min"] = {int(i): float(v) for i, v, n in zip(o["iteration"], o["newly_render_min"], o["n_newly"]) if n > 0}
c3["newly_render_med"] = {int(i): float(v) for i, v, n in zip(o["iteration"], o["newly_render_med"], o["n_newly"]) if n > 0}
c3["n_newly"] = {int(i): int(n) for i, n in zip(o["iteration"], o["n_newly"]) if n > 0}
c3["post_nbelow_total"] = int(np.nansum(o["post_nbelow"]))
c3["end_nbelow_total"] = int(np.nansum(o["end_nbelow"]))
c3["post_min_min"] = float(np.nanmin(o["post_min"]))
c3["end_min_min"] = float(np.nanmin(o["end_min"]))
c3["render_min_excl_E_updates"] = float(np.nanmin(o["render_min"][o["E_update"] == 0]))
c3["end_median_range"] = [float(np.nanmin(o["end_med"])), float(np.nanmax(o["end_med"]))]
rs = [e for e in dens["A"] if e["event"] == "opacity_reset"]
c3["reset_events"] = rs
for r in ("B", "C", "A_bias"):
    c3[f"{r}_post_nbelow_total"] = int(np.nansum(opac[r]["post_nbelow"]))
    c3[f"{r}_end_min_min"] = float(np.nanmin(opac[r]["end_min"]))
    c3[f"{r}_render_nbelow_iters"] = {int(i): int(n) for i, n in zip(opac[r]["iteration"], opac[r]["render_nbelow"]) if n > 0}
c3["B_prot_end_opacity_min_med"] = [float(np.nanmin(opac["B"]["end_min"])), nanmed(opac["B"]["end_med"])]
hist_rows = []
st = {r: np.load(AU / "runs" / r / "audit/hist/state_03500.npz") for r in ("A", "B", "C")}
bins = np.linspace(0, 1, 21)
for r in ("A", "B", "C"):
    s = st[r]; prior = s["origin"] == 1; prot = s["prot"].astype(bool)
    for gname, m in (("prot", prior & prot), ("free", prior & ~prot), ("img", ~prior)):
        h = np.histogram(s["opacity"][m], bins=bins)[0]
        hist_rows.append([r, gname, int(m.sum()), nanmed(s["opacity"][m]), float(np.min(s["opacity"][m])) if m.any() else float("nan"),
                          int((s["opacity"][m] < 0.5).sum())] + h.tolist())
write_csv("check3_opacity_hist_end.csv", ["run", "group", "n", "median", "min", "n_below_0.5"] +
          [f"{bins[i]:.2f}-{bins[i+1]:.2f}" for i in range(20)], hist_rows)
c3["end_hist"] = {f"{r[0]}_{r[1]}": dict(n=r[2], median=r[3], min=r[4], n_below=r[5]) for r in hist_rows}
write_csv("check3_opacity_per_iteration_A.csv", list(o.keys()), [[o[k][i] for k in o] for i in range(len(o["iteration"]))])
R["check3"] = c3

# ============================================================================== check 4: colour
c4 = {}
for q in ("fdc", "frest"):
    for stat in ("med", "mean", "act_med"):
        key = f"prot_{q}_{stat}"
        for wname, (a, b) in wins.items():
            m = (it >= a) & (it <= b)
            with np.errstate(divide="ignore", invalid="ignore"):
                rat = steps["A"][key][m] / steps["B"][key][m]
            c4[f"{key}_{wname}"] = dict(A=nanmed(steps["A"][key][m]), B=nanmed(steps["B"][key][m]), C=nanmed(steps["C"][key][m]),
                                       A_over_B=nanmed(rat))
for g in ("free", "img"):
    m = it >= 1
    with np.errstate(divide="ignore", invalid="ignore"):
        c4[f"{g}_fdc_med_A_over_B"] = nanmed(steps["A"][f"{g}_fdc_med"] / steps["B"][f"{g}_fdc_med"])
R["check4"] = c4
write_csv("check4_colour_per_iteration.csv", ["iteration", "A_prot_fdc_med", "B_prot_fdc_med", "C_prot_fdc_med", "A_prot_frest_med",
                                              "B_prot_frest_med", "A_free_fdc_med", "B_free_fdc_med"],
          [[int(it[i]), steps["A"]["prot_fdc_med"][i], steps["B"]["prot_fdc_med"][i], steps["C"]["prot_fdc_med"][i],
            steps["A"]["prot_frest_med"][i], steps["B"]["prot_frest_med"][i], steps["A"]["free_fdc_med"][i],
            steps["B"]["free_fdc_med"][i]] for i in range(len(it))])

# ============================================================================== section 6: 4.3 terms, 4.5/4.6 facts
s6 = {}
sa = {row["iteration"]: row for row in scal["A"]}
s6["terms"] = {i: {k: sa[i][k] for k in ("rgb", "mvs", "prior", "normal", "dist", "total", "lambda_mvs", "lambda_prior",
                                          "px_mvs_n", "px_prior_n", "px_prior_beyond", "px_mvs_hole", "px_prior_hole")
                   if k in sa[i]} for i in (1, 500, 3000) if i in sa}
s6["pixels_per_view"] = H * W
tot = {}
for r in RUNS:
    t = dict(clone={g: 0 for g in ("prot", "free", "img")}, split={g: 0 for g in ("prot", "free", "img")},
             split_parent={g: 0 for g in ("prot", "free", "img")}, prune={g: 0 for g in ("prot", "free", "img")},
             prune_low_opacity={g: 0 for g in ("prot", "free", "img")}, prune_big_screen={g: 0 for g in ("prot", "free", "img")},
             prune_big_world={g: 0 for g in ("prot", "free", "img")},
             excluded_protected=dict(clone=0, split=0, prune=0), checks=dict(clone=[], split=[], prune=[]), n_events=0)
    for e in dens[r]:
        if e["event"] == "clone":
            for g in t["clone"]: t["clone"][g] += e["selected"][g]
            t["excluded_protected"]["clone"] += e["excluded_protected"]
            t["checks"]["clone"].append(e["n_new_matches"] and e["child_origin_ok"] and e["child_init_id_ok"] and e["child_protected"] == 0)
        elif e["event"] == "split":
            for g in t["split"]: t["split"][g] += e["selected"][g]
            t["excluded_protected"]["split"] += e["excluded_protected"]
            t["checks"]["split"].append(e["n_net_matches"] and e["child_origin_ok"] and e["child_init_id_ok"] and e["child_protected"] == 0)
        elif e["event"] == "split_parent_removal":
            for g in t["split_parent"]: t["split_parent"][g] += e["removed"][g]
        elif e["event"] == "prune":
            for g in t["prune"]:
                t["prune"][g] += e["removed"][g]; t["prune_low_opacity"][g] += e["removed_low_opacity"][g]
                t["prune_big_screen"][g] += e["removed_big_screen"][g]; t["prune_big_world"][g] += e["removed_big_world"][g]
            t["excluded_protected"]["prune"] += e["excluded_protected"]
            t["checks"]["prune"].append(e["mask_equals_rule"])
        t["n_events"] += 1
    t["checks"] = {k: (all(v) if v else None) for k, v in t["checks"].items()}
    # implementation's own records: per-100 'removed' counters and per-initial-disk last_seen
    impl_removed = sum(row["removed"] for row in scal[r])
    impl_added = sum(row["added"] for row in scal[r])
    f = final[r]
    last_densify = max(e["iteration"] for e in dens[r] if e["event"] == "prune")
    mine_removed_total = sum(t["prune"].values()) + sum(t["split_parent"].values())
    mine_removed_logged = sum(e["removed"][g] for e in dens[r] if e["event"] in ("prune", "split_parent_removal")
                              for g in ("prot", "free", "img") if e["iteration"] < last_densify)
    mine_added_logged = sum(e.get("n_new", 0) for e in dens[r] if e["event"] in ("clone", "split") and e["iteration"] < last_densify)
    alive_mine = f["init_alive"].astype(bool)
    alive_impl = f["impl_last_seen"] >= f["iteration"]
    init_prior = f["init_origin"] == 1
    t["records"] = dict(impl_removed_counter_sum=int(impl_removed), impl_added_counter_sum=int(impl_added),
                        audit_removed_total=int(mine_removed_total), audit_removed_before_last_log=int(mine_removed_logged),
                        audit_added_before_last_log=int(mine_added_logged), last_densify_iteration=int(last_densify),
                        init_prior_extinct_audit=int((init_prior & ~alive_mine).sum()),
                        init_prior_extinct_impl_record=int((init_prior & ~alive_impl).sum()),
                        init_extinct_disagree=int((alive_mine != alive_impl).sum()),
                        removed_prior_rows_logged=int(len(f["removed"])))
    tot[r] = t
s6["density"] = tot
removed = final["A"]["removed"]
s6["removed_prior_A"] = dict(n=int(len(removed)), by_reason=dict(low_opacity=int(((removed[:, 3].astype(int) & 1) > 0).sum()) if len(removed) else 0,
                                                                  big_screen=int(((removed[:, 3].astype(int) & 2) > 0).sum()) if len(removed) else 0,
                                                                  big_world=int(((removed[:, 3].astype(int) & 4) > 0).sum()) if len(removed) else 0))
# PLY header fields
ply = AU / "runs/A/model/point_cloud/iteration_3500/point_cloud.ply"
hdr = []
with open(ply, "rb") as fh:
    while True:
        line = fh.readline().decode(errors="replace").strip()
        if line.startswith("property"):
            hdr.append(line.split()[-1] + ":" + line.split()[1])
        if line == "end_header":
            break
s6["ply_fields"] = hdr
dump = np.load(AU / "runs/A/model/dump/iteration_3500/gaussians.npz")
s6["dump_fields"] = list(dump.keys())
s6["dump_E_all_nan"] = bool(np.isnan(dump["E"]).all())
# protection-rule records (newly protected / released per E update and the distance of newly protected disks)
pr_rows = []
for iE in E_iters:
    z = np.load(AU / "runs/A" / f"audit/E/E_{iE:05d}.npz")
    newly = z["prot"].astype(bool) & ~z["prev_prot"].astype(bool)
    rel = z["prev_prot"].astype(bool) & ~z["prot"].astype(bool)
    d = z["drift"][newly]
    q = np.nanpercentile(d, [10, 50, 90, 99]).tolist() if d.size else [float("nan")] * 4
    pr_rows.append([iE, int(z["prot"].sum()), int(newly.sum()), int(rel.sum()), *q, float(np.nanmax(d)) if d.size else float("nan"),
                    int((d > 0.1).sum()), int((d > 0.3).sum()), int(z["off_prior"].sum())])
write_csv("sec6_protection_rule_records_A.csv", ["E_iteration", "n_protected", "n_newly_protected", "n_released",
                                                  "newly_drift_p10", "newly_drift_p50", "newly_drift_p90", "newly_drift_p99",
                                                  "newly_drift_max", "newly_drift_gt_0.1m", "newly_drift_gt_0.3m", "n_off_prior_exception"], pr_rows)
s6["protection_records"] = pr_rows
R["sec6"] = s6

# ============================================================================== instrumentation neutrality
ref = {row["iteration"]: row for row in (json.loads(l) for l in open(S2 / "runs/P_M_N/model/monitor/scalars.jsonl"))}
lam = {row["iteration"]: row for row in (json.loads(l) for l in open(S2 / "runs/P_M_N/model_lam005/monitor/scalars.jsonl"))}
neu = []
for i in sorted(sa):
    if i in ref:
        neu.append([i, sa[i]["n"], ref[i]["n"], lam.get(i, {}).get("n", float("nan")), sa[i]["n_locked"], ref[i]["n_locked"],
                    lam.get(i, {}).get("n_locked", float("nan")), sa[i]["rgb"], ref[i]["rgb"], lam.get(i, {}).get("rgb", float("nan"))])
write_csv("neutrality_A_vs_uninstrumented.csv", ["iteration", "A_n", "PMN30k_n", "lam005_n", "A_locked", "PMN30k_locked",
                                                  "lam005_locked", "A_rgb", "PMN30k_rgb", "lam005_rgb"], neu)
nv = np.array(neu, float)
m2 = nv[:, 0] <= 2000
R["neutrality"] = dict(
    A_vs_ref_rel_n_le2000=float(np.nanmedian(np.abs(nv[m2, 1] - nv[m2, 2]) / nv[m2, 2])),
    lam_vs_ref_rel_n_le2000=float(np.nanmedian(np.abs(nv[m2, 3] - nv[m2, 2]) / nv[m2, 2])),
    A_vs_ref_rel_rgb_le2000=float(np.nanmedian(np.abs(nv[m2, 7] - nv[m2, 8]) / nv[m2, 8])),
    lam_vs_ref_rel_rgb_le2000=float(np.nanmedian(np.abs(nv[m2, 9] - nv[m2, 8]) / nv[m2, 8])),
    A_vs_ref_rel_n_le3500=float(np.nanmedian(np.abs(nv[:, 1] - nv[:, 2]) / nv[:, 2])),
    A_vs_ref_locked_3500=[float(nv[-1, 4]), float(nv[-1, 5])], A_vs_ref_n_3500=[float(nv[-1, 1]), float(nv[-1, 2])],
    iteration1_identical=bool(nv[0, 1] == nv[0, 2] and nv[0, 4] == nv[0, 5] and nv[0, 7] == nv[0, 8]))

# ============================================================================== figures
def panel_steps(axs):
    names = {"prot": "protected", "free": "prior, not protected", "img": "image origin"}
    for ax, g in zip(axs, ("prot", "free", "img")):
        for r in ("A", "B", "C"):
            y = steps[r][f"{g}_xyz_mean"]
            ax.plot(it, np.where(y > 0, y, np.nan), color=COL[r], lw=0.4, alpha=0.2)
        for r, lw, ls in (("B", 1.4, "-"), ("A", 3.0, "-"), ("C", 1.3, "--")):
            y = steps[r][f"{g}_xyz_mean"]
            ax.plot(it, rmean(np.where(y > 0, y, np.nan), 51), color=COL[r], lw=lw, ls=ls, label=f"{r}")
        ax.set_yscale("log"); ax.set_title(f"{names[g]}", fontsize=8.5); ax.grid(alpha=0.3, which="major")
        ax.axvline(3000, color="0.5", lw=0.7, ls=":")
        ax.set_ylim(3e-4, 5); ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.tick_params(labelsize=7); ax.set_xlabel("iteration", fontsize=7.5); ax.set_xticks([0, 1500, 3000])
    for ax in axs[1:]:
        ax.set_yticklabels([])
    axs[0].set_ylabel("mean |dxyz| / lr_xyz per step", fontsize=7.5)
    axs[0].legend(fontsize=7, loc="lower left")


def top_extent():
    return [crop[0, 0], crop[1, 0], crop[0, 1], crop[1, 1]]


def panel_drift(axs, cax=None):
    norm = Normalize(0, 0.5)
    for ax, r in zip(axs, ("A", "B", "C")):
        f = final[r]; prior = f["origin"] == 1
        xyz, d = f["xyz"][prior], f["drift"][prior]
        o = np.argsort(d)
        sc = ax.scatter(xyz[o, 0], xyz[o, 1], c=np.clip(d[o], 0, 0.5), s=0.15, cmap="magma", norm=norm, linewidths=0, rasterized=True)
        ax.set_title(f"{r}", fontsize=8)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        ax.set_facecolor("0.85")
    return sc


def panel_view(ax, view="DJI_20241217101343_0024_D", run="A", iE=None):
    iE = iE or first_E
    z = np.load(AU / "runs" / run / f"audit/E/E_{iE:05d}.npz")
    q, t, _ = imgs[COND[run]][view]; Rm = q2R(q); K = np.array(calib[COND[run]][view]["K"])
    Xc = z["xyz"].astype(np.float64) @ Rm.T + t; zc = Xc[:, 2]
    u = K[0, 0] * Xc[:, 0] / zc + K[0, 2]; v = K[1, 1] * Xc[:, 1] / zc + K[1, 2]
    ins = (zc > 0.01) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    ax.imshow(A_tr[view], cmap="gray", vmin=-0.6, vmax=1.3, interpolation="nearest")
    idx = np.nonzero(ins)[0]
    idx = idx[np.random.default_rng(3).permutation(len(idx))[:40000]]
    sc = ax.scatter(u[idx], v[idx], c=z["E"][idx], s=0.25, cmap="viridis", vmin=0, vmax=1, linewidths=0, rasterized=True)
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.set_xticks([]); ax.set_yticks([])
    return sc


def panel_opacity(ax):
    o = opac["A"]
    ax.plot(o["iteration"], o["render_min"], color="tab:orange", lw=0.8, label="min, as rendered (start of iteration)")
    ax.plot(o["iteration"], o["end_min"], color="tab:blue", lw=1.4, label="min, end of iteration")
    ax.plot(o["iteration"], o["end_med"], color="tab:blue", lw=1.4, ls="--", label="median, end of iteration")
    ax.plot(opac["B"]["iteration"], opac["B"]["end_min"], color="tab:red", lw=0.8, alpha=0.8, label="B (no floor): min")
    ax.plot(opac["B"]["iteration"], opac["B"]["end_med"], color="tab:red", lw=0.8, ls="--", alpha=0.8, label="B (no floor): median")
    ax.axhline(0.5, color="k", lw=0.7, ls=":")
    for e in E_iters:
        ax.axvline(e, color="0.8", lw=0.5)
    ax.axvline(3000, color="tab:green", lw=1.2, ls="-.", label="opacity reset (3000)")
    ax.set_yscale("log"); ax.set_ylim(1e-3, 1.2); ax.set_xlabel("iteration", fontsize=8)
    ax.set_ylabel("opacity of protected disks", fontsize=8); ax.legend(fontsize=6.3, loc="lower left"); ax.grid(alpha=0.3)
    ax.tick_params(labelsize=7)


def panel_colour(ax):
    for r in ("A", "B"):
        y = steps[r]["prot_fdc_mean"]
        ax.plot(it, rmean(np.where(y > 0, y, np.nan), 51), color=COL[r], lw=2.0, label=f"{r}: protected, mean")
        y = steps[r]["prot_fdc_med"]
        ax.plot(it, rmean(np.where(y > 0, y, np.nan), 51), color=COL[r], lw=1.0, ls=":", label=f"{r}: protected, median")
    y = steps["A"]["free_fdc_mean"]
    ax.plot(it, rmean(np.where(y > 0, y, np.nan), 51), color="0.4", lw=1.0, ls="--", label="A: prior, not protected, mean")
    ax.set_yscale("log"); ax.set_ylim(1e-8, 1e-2); ax.set_xlabel("iteration", fontsize=8)
    ax.set_ylabel("|d f_dc| per step (SH DC colour)", fontsize=8)
    ax.legend(fontsize=7); ax.grid(alpha=0.3, which="both"); ax.tick_params(labelsize=7)


def panel_removed(ax):
    init = np.load(AU / "runs/A/audit/init.npz")
    ixyz, iorg = init["init_xyz"], init["init_origin"]
    pr = iorg == 1
    ax.scatter(ixyz[pr, 0], ixyz[pr, 1], s=0.1, color="0.75", linewidths=0, rasterized=True)
    rem = final["A"]["removed"]
    if len(rem):
        ids = rem[:, 1].astype(int); itr = rem[:, 0]
        sc = ax.scatter(ixyz[ids, 0], ixyz[ids, 1], c=itr, s=0.6, cmap="plasma", vmin=600, vmax=3500, linewidths=0, rasterized=True)
    else:
        sc = None
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    return sc


# individual workspace figures
fig, axs = plt.subplots(1, 3, figsize=(15, 4)); panel_steps(axs); fig.suptitle("Check 1: step size per group"); fig.tight_layout()
fig.savefig(FIG / "check1_step_curves_xyz.png", dpi=130); plt.close(fig)
for q in ("rot", "scale"):
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    for ax, g in zip(axs, ("prot", "free", "img")):
        for r in ("A", "B", "C"):
            y = steps[r][f"{g}_{q}_mean"]
            ax.plot(it, rmean(np.where(y > 0, y, np.nan), 51), color=COL[r], lw=1.3, label=r)
        ax.set_yscale("log"); ax.set_title(f"{g}: mean |d{q}| / lr"); ax.grid(alpha=0.3); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / f"check1_step_curves_{q}.png", dpi=120); plt.close(fig)
fig = plt.figure(figsize=(15, 5)); gsx = fig.add_gridspec(1, 4, width_ratios=[1, 1, 1, 0.05])
axs = [fig.add_subplot(gsx[0, i]) for i in range(3)]; sc = panel_drift(axs)
fig.colorbar(sc, cax=fig.add_subplot(gsx[0, 3]), label="drift from initial position (m, clipped at 0.5)")
fig.savefig(FIG / "check1_drift_maps.png", dpi=130); plt.close(fig)
for view in ("DJI_20241217101343_0024_D", "DJI_20241217101305_0005_D", "DJI_20241217101313_0009_D"):
    fig, axs = plt.subplots(1, 2, figsize=(14, 5.4))
    for ax, iE in zip(axs, (first_E, last_E)):
        sc = panel_view(ax, view, "A", iE); ax.set_title(f"A, E at iteration {iE}, view {view.split('_')[-2]} (A map: light = 1)")
    fig.colorbar(sc, ax=axs, fraction=0.02, label="E (Gaussian confidence)"); fig.savefig(FIG / f"check2_view_E_{view.split('_')[-2]}.png", dpi=120)
    plt.close(fig)
fig, axs = plt.subplots(2, 3, figsize=(16, 10.5))
for j, (r, iE) in enumerate((("A", first_E), ("A", last_E), ("A_bias", last_E))):
    z = np.load(AU / "runs" / r / f"audit/E/E_{iE:05d}.npz"); o_ = np.argsort(-z["E"])
    sc = axs[0, j].scatter(z["xyz"][o_, 0], z["xyz"][o_, 1], c=z["E"][o_], s=0.2, cmap="viridis", vmin=0, vmax=1, linewidths=0, rasterized=True)
    axs[0, j].set_title(f"{r} it {iE}: E of prior disks"); axs[0, j].set_aspect("equal")
    p = z["prot"].astype(bool)
    axs[1, j].scatter(z["xyz"][~p, 0], z["xyz"][~p, 1], s=0.15, color="0.75", linewidths=0, rasterized=True, label="not protected")
    axs[1, j].scatter(z["xyz"][p, 0], z["xyz"][p, 1], s=0.15, color="tab:red", linewidths=0, rasterized=True, label="protected")
    axs[1, j].set_title(f"{r} it {iE}: protected {p.sum()} of {len(p)} ({p.mean():.0%})"); axs[1, j].set_aspect("equal")
    axs[1, j].legend(fontsize=7, markerscale=15)
fig.colorbar(sc, ax=axs[0, :], fraction=0.015, label="E")
fig.savefig(FIG / "check2_topview_E_protection.png", dpi=110, bbox_inches="tight"); plt.close(fig)
fig, ax = plt.subplots(figsize=(8, 4.5)); panel_opacity(ax); fig.tight_layout(); fig.savefig(FIG / "check3_opacity_curves.png", dpi=130); plt.close(fig)
fig, axs = plt.subplots(1, 3, figsize=(15, 3.8))
for ax, g in zip(axs, ("prot", "free", "img")):
    for r in ("A", "B", "C"):
        s = st[r]; prior = s["origin"] == 1; prot = s["prot"].astype(bool)
        m = {"prot": prior & prot, "free": prior & ~prot, "img": ~prior}[g]
        ax.hist(s["opacity"][m], bins=bins, histtype="step", color=COL[r], lw=1.4, label=f"{r} (n={m.sum()})")
    ax.set_title(f"end opacity, {g}"); ax.legend(fontsize=7); ax.set_yscale("log")
fig.tight_layout(); fig.savefig(FIG / "check3_opacity_hist_end.png", dpi=120); plt.close(fig)
rz = np.load(AU / "runs/A/audit/maps/reset_03000.npz")
R["check3"]["reset_depth_roof"] = {}
for view in ("DJI_20241217101305_0005_D", "DJI_20241217101343_0024_D"):
    fid = cv2.resize(np.load(S2 / "inputs/maps/faceid" / f"{view}.npy").astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
    roof = np.isin(fid, [3387, 3389, 3393, 3394, 3396, 3404])
    ys, xs = np.nonzero(roof)
    y0, y1, x0, x1 = max(0, ys.min() - 30), min(H, ys.max() + 30), max(0, xs.min() - 30), min(W, xs.max() + 30)
    db, da = rz[f"depth_before_{view}"], rz[f"depth_after_{view}"]
    ab, aa = rz[f"alpha_before_{view}"], rz[f"alpha_after_{view}"]
    dd = np.where((db > 0) & (da > 0), da - db, np.nan)
    R["check3"]["reset_depth_roof"][view.split('_')[-2]] = dict(
        n_roof_px=int(roof.sum()), median_abs_change_m=nanmed(np.abs(dd[roof])),
        p90_abs_change_m=float(np.nanpercentile(np.abs(dd[roof]), 90)), frac_gt_5cm=float(np.nanmean(np.abs(dd[roof]) > 0.05)),
        frac_farther_1m=float(np.nanmean(dd[roof] > 1.0)), depth_before_med=nanmed(db[roof]), depth_after_med=nanmed(da[roof]),
        alpha_before_med=nanmed(ab[roof]), alpha_after_med=nanmed(aa[roof]))
    vals = np.r_[db[roof], da[roof]]; vals = vals[vals > 0]
    lo, hi = np.percentile(vals, [1, 99])
    fig, axs = plt.subplots(1, 3, figsize=(17, 5.2))
    for ax, im, tt in ((axs[0], db, "rendered depth right before the reset (it 3000)"), (axs[1], da, "right after the reset")):
        h = ax.imshow(np.where(im > 0, im, np.nan)[y0:y1, x0:x1], cmap="turbo", vmin=lo, vmax=hi); ax.set_title(f"{view.split('_')[-2]}: {tt}", fontsize=9)
    fig.colorbar(h, ax=axs[:2], fraction=0.02, label="camera depth (m)")
    h2 = axs[2].imshow(dd[y0:y1, x0:x1], cmap="RdBu_r", vmin=-15, vmax=15); axs[2].set_title("after - before (m); red = farther", fontsize=9)
    fig.colorbar(h2, ax=axs[2], fraction=0.04)
    for ax in axs:
        ax.contour(roof[y0:y1, x0:x1].astype(float), levels=[0.5], colors="k", linewidths=0.6); ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(FIG / f"check3_reset_depth_roof_{view.split('_')[-2]}.png", dpi=110, bbox_inches="tight"); plt.close(fig)
R["check3"]["reset_depth_roof_0005"] = R["check3"]["reset_depth_roof"]["0005"]
# occlusion flips on the biased scene, qualitative: top and side view of prior disks by category
for iE in (pre_reset_E, last_E):
    z = np.load(AU / "runs/A_bias" / f"audit/E/E_{iE:05d}.npz")
    pi, prd = z["prot"].astype(bool), z["prot_rend"].astype(bool)
    cat = np.where(pi & prd, 0, np.where(pi & ~prd, 1, np.where(~pi & prd, 2, 3)))
    names = ["protected by both", "prior-depth test only (implementation)", "render-depth test only", "neither"]
    cols = ["0.55", "tab:red", "tab:blue", "0.88"]
    fig, axs = plt.subplots(1, 2, figsize=(16, 6.5), gridspec_kw=dict(width_ratios=[1, 1.4]))
    for c in (3, 0, 1, 2):
        m = cat == c
        axs[0].scatter(z["xyz"][m, 0], z["xyz"][m, 1], s=0.3 if c in (1, 2) else 0.1, color=cols[c], linewidths=0, rasterized=True,
                       label=f"{names[c]} ({m.sum()})")
    rr = np.array(next(p for p in S1J["polygons"] if p["poly_index"] == 3396)["ring_local_xy"])
    axs[0].plot(np.r_[rr[:, 0], rr[0, 0]], np.r_[rr[:, 1], rr[0, 1]], "k-", lw=0.8)
    axs[0].set_aspect("equal"); axs[0].legend(fontsize=7, markerscale=12, loc="lower right"); axs[0].set_title(f"A_bias it {iE}: top view")
    inner = ring.contains_points(z["xyz"][:, :2])
    ctr = np.array(rr).mean(0); ax_dir = rr[1] - rr[0]; ax_dir = ax_dir / np.linalg.norm(ax_dir)
    for c in (3, 0, 1, 2):
        m = (cat == c) & inner
        t = (z["xyz"][m, :2] - ctr) @ ax_dir
        axs[1].scatter(t, z["xyz"][m, 2], s=0.5 if c in (1, 2) else 0.2, color=cols[c], linewidths=0, rasterized=True)
    axs[1].set_xlabel("position along the main-roof ridge direction (m)"); axs[1].set_ylabel("z local (m)")
    axs[1].set_title("main roof 3396 footprint, side view (prior raised +1 m in this scene)")
    fig.tight_layout(); fig.savefig(FIG / f"check2_occlusion_flips_A_bias_{iE}.png", dpi=110); plt.close(fig)
# which protected disks show through the roof after the reset: protected prior disks inside the target roof footprints
s3000 = np.load(AU / "runs/A/audit/hist/state_03000.npz")
tgt_roofs = [p for p in S1J["polygons"] if p["is_target"] and p["citygml_type"] == "RoofSurface"]
foot = np.zeros(len(s3000["xyz"]), bool)
for p in tgt_roofs:
    foot |= MPath(np.array(p["ring_local_xy"])).contains_points(s3000["xyz"][:, :2])
pm = (s3000["origin"] == 1) & s3000["prot"].astype(bool)
roof_z = float(np.mean([p["z_local_mean"] for p in tgt_roofs]))
gnd = next(p for p in S1J["polygons"] if p["is_target"] and p["citygml_type"] == "GroundSurface")
zz = s3000["xyz"][:, 2]
R["check3"]["under_roof_protected_3000"] = dict(
    n_protected=int(pm.sum()), n_inside_target_roof_footprint=int((pm & foot).sum()),
    n_below_roof_minus7m=int((pm & foot & (zz < roof_z - 7)).sum()),
    n_near_ground_surface=int((pm & foot & (np.abs(zz - gnd["z_local_mean"]) < 0.5)).sum()),
    ground_surface_poly=int(gnd["poly_index"]), ground_z_local=float(gnd["z_local_mean"]), roof_z_local_mean=roof_z,
    opacity_median_below=nanmed(s3000["opacity"][pm & foot & (zz < roof_z - 7)]))
fig, ax = plt.subplots(figsize=(8, 4)); panel_colour(ax); fig.tight_layout(); fig.savefig(FIG / "check4_colour_curves.png", dpi=130); plt.close(fig)
fig, ax = plt.subplots(figsize=(7, 6)); sc = panel_removed(ax)
if sc is not None:
    fig.colorbar(sc, ax=ax, label="removal iteration")
ax.set_title("A: initial positions of removed prior disks (grey: all prior)"); fig.tight_layout(); fig.savefig(FIG / "sec6_removed_prior_topview.png", dpi=130); plt.close(fig)
fig, axs = plt.subplots(1, 2, figsize=(12, 4))
axs[0].plot(nv[:, 0], nv[:, 1], label="A (instrumented)"); axs[0].plot(nv[:, 0], nv[:, 2], label="P_M_N 30k run (same code, no audit)")
axs[0].plot(nv[:, 0], nv[:, 3], label="P_M_N lam005 (same config, 2k)"); axs[0].set_title("number of disks"); axs[0].legend(fontsize=8)
axs[1].plot(nv[:, 0], nv[:, 4], label="A"); axs[1].plot(nv[:, 0], nv[:, 5], label="P_M_N 30k"); axs[1].plot(nv[:, 0], nv[:, 6], label="lam005")
axs[1].set_title("protected disks"); axs[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(FIG / "neutrality_trajectories.png", dpi=120); plt.close(fig)

# summary figure: six panels
fig = plt.figure(figsize=(20, 11.5))
G = fig.add_gridspec(2, 3, hspace=0.28, wspace=0.16)
g1 = G[0, 0].subgridspec(1, 3, wspace=0.35); a1 = [fig.add_subplot(g1[0, i]) for i in range(3)]
panel_steps(a1); a1[1].set_title("(1) Check 1: xyz step / lr per group (A, B, C)\nprior, not protected", fontsize=8.5)
a1[0].set_title("protected", fontsize=8.5)
g2 = G[0, 1].subgridspec(1, 4, width_ratios=[1, 1, 1, 0.06], wspace=0.05); a2 = [fig.add_subplot(g2[0, i]) for i in range(3)]
sc = panel_drift(a2); cb = fig.colorbar(sc, cax=fig.add_subplot(g2[0, 3])); cb.set_label("drift (m, clipped at 0.5)", fontsize=7)
cb.ax.tick_params(labelsize=7)
a2[1].set_title("(2) Check 1: drift from initial position, prior disks at 3500 (top view)\nB (protection off)", fontsize=8.5)
a2[0].set_title("A (current)", fontsize=8.5); a2[2].set_title("C (update x0.01)", fontsize=8.5)
a3 = fig.add_subplot(G[0, 2]); sc = panel_view(a3, "DJI_20241217101343_0024_D", "A", first_E)
fig.colorbar(sc, ax=a3, fraction=0.035).set_label("E", fontsize=8)
a3.set_title(f"(3) Check 2: prior-disk centres coloured by E (iteration {first_E}), view 0024,\n"
             "underlay = observation confidence map (light 1, dark 0)", fontsize=8.5)
a4 = fig.add_subplot(G[1, 0]); panel_opacity(a4)
a4.set_title("(4) Check 3: opacity of protected disks (A; B for reference)", fontsize=8.5)
a5 = fig.add_subplot(G[1, 1]); panel_colour(a5); a5.set_title("(5) Check 4: colour (SH DC) change of protected disks, A vs B", fontsize=8.5)
a6 = fig.add_subplot(G[1, 2]); sc = panel_removed(a6)
if sc is not None:
    fig.colorbar(sc, ax=a6, fraction=0.035).set_label("removal iteration", fontsize=8)
a6.set_title("(6) Sec. 6: initial positions of removed prior disks (A), grey = all prior", fontsize=8.5)
fig.suptitle("Method 4.4 audit (PHD-STAGE2-PROTECTION-AUDIT-v1): LoD2 prior, nominal scene P_M_N, 3,500 iterations, seed 0", fontsize=11)
fig.savefig(OUT / "summary_4_4.png", dpi=110, bbox_inches="tight"); plt.close(fig)

json.dump(R, open(OUT / "results.json", "w"), indent=1, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))
print(json.dumps({k: (v if k in ("runs", "neutrality") else "...") for k, v in R.items()}, indent=1))
