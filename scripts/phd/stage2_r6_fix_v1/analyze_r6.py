"""Analysis of PHD-STAGE2-R6-FIX-v1 (jointbuildgs:dev, CPU, read-only on inputs).

  python analyze_r6.py    # mounts: /r6 (rw), /audit (r5 audit payload PHD-STAGE2-PROTECTION-AUDIT-v1, ro), /s2 (ro), /s1 (ro)

r5 numbers come from the r5 audit (runs A = P_M_N, A_bias = P_M_B); r5 is not rerun. r6 numbers from runs N and B.
Writes /r6/out/{results.json, csv/*.csv, figures/*.png, summary_r6.png}."""
import csv
import json
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
from matplotlib.colors import Normalize
from matplotlib.path import Path as MPath

R6, AU, S2, S1 = Path("/r6"), Path("/audit"), Path("/s2"), Path("/s1")
OUT = R6 / "out"; CSV = OUT / "csv"; FIG = OUT / "figures"
for d in (OUT, CSV, FIG):
    d.mkdir(parents=True, exist_ok=True)
RUN = {("r5", "N"): AU / "runs/A", ("r5", "B"): AU / "runs/A_bias", ("r6", "N"): R6 / "runs/N", ("r6", "B"): R6 / "runs/B"}
TAU_M = 0.05677034870849456
DMAX = 4 * TAU_M
N_SFM = 72028
H, W = 1157, 1600
COL = {"r5": "tab:red", "r6": "tab:blue"}
R = {}


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


def pct(x, q):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if x.size else float("nan")


def write_csv(name, header, rows):
    with open(CSV / name, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def rmed(x, k=51):
    x = np.asarray(x, float); out = np.full_like(x, np.nan)
    for i in range(len(x)):
        seg = x[max(0, i - k // 2): i + k // 2 + 1]; seg = seg[np.isfinite(seg)]
        out[i] = np.median(seg) if seg.size else np.nan
    return out


E_ITERS = {"r5": [1, 501, 1001, 1501, 2001, 2501, 3001], "r6": [1, 500, 1000, 1500, 2000, 2500, 3000, 3500]}
PRE_RESET = {"r5": 2501, "r6": 3000}
Enpz = {(v, s): {i: np.load(RUN[(v, s)] / f"audit/E/E_{i:05d}.npz") for i in E_ITERS[v]} for v in ("r5", "r6") for s in ("N", "B")}
dump = {k: np.load(p / "model/dump/iteration_3500/gaussians.npz") for k, p in RUN.items()}
steps = {k: rd_csv(p / "audit/steps.csv") for k, p in RUN.items()}
opac = {k: rd_csv(p / "audit/opacity.csv") for k, p in RUN.items()}
scal = {k: {r["iteration"]: r for r in jl(p / "model/monitor/scalars.jsonl")} for k, p in RUN.items()}
rec = {k: json.loads((p / "receipt.json").read_text()) for k, p in RUN.items()}
init = {k: np.load(p / "audit/init.npz") for k, p in RUN.items()}
R["runs"] = {f"{v}_{s}": dict(seconds=rec[(v, s)]["seconds"], status=rec[(v, s)]["status"]) for (v, s) in RUN}
S1J = json.loads((S1 / "PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json").read_text())
PJ = {p["poly_index"]: p for p in S1J["polygons"]}
ring3396 = np.array(PJ[3396]["ring_local_xy"])
crop = np.array(S1J["als_crop_local_xy"])

# ------------------------------------------------------------------------------------------ prior polygon of each initial disk
initc = json.loads((R6 / "init_counts/init_counts.json").read_text())
dropped = {s: np.load(R6 / f"init_counts/dropped_M_{s}.npz") for s in ("N", "B")}


def init_poly(v, s, init_id):
    """LoD2 polygon of the initial prior point an init_id refers to (-1 for image disks)."""
    d = dropped[s]
    poly_all = d["poly"]
    if v == "r6":
        poly_list = poly_all[~d["dropped"]]
    else:
        poly_list = poly_all
    out = np.full(len(init_id), -1, np.int64)
    ok = init_id >= N_SFM
    idx = init_id[ok] - N_SFM
    good = idx < len(poly_list)
    tmp = np.full(ok.sum(), -1, np.int64); tmp[good] = poly_list[idx[good]]
    out[ok] = tmp
    return out


# sanity: the init positions of prior init ids equal the scene prior points (kept ones for r6)
for (v, s) in RUN:
    ix = init[(v, s)]["init_xyz"]; d = dropped[s]
    pts = d["xyz"][~d["dropped"]] if v == "r6" else d["xyz"]
    R.setdefault("sanity", {})[f"{v}_{s}_init_prior_matches_scene"] = bool(np.abs(ix[N_SFM:N_SFM + len(pts)] - pts).max() < 1e-4 and len(ix) == N_SFM + len(pts))

# ============================================================================ (a)(d) protection per E update, distances
rows_upd = []
R["updates"] = {}
for v in ("r5", "r6"):
    for s in ("N", "B"):
        lst = []
        for i in E_ITERS[v]:
            z = Enpz[(v, s)][i]
            prot, prev, dr = z["prot"].astype(bool), z["prev_prot"].astype(bool), z["drift"]
            newly, rel = prot & ~prev, prev & ~prot
            far = z["far"].astype(bool) if "far" in z.files else np.zeros_like(prot)
            rel_far = rel & far
            r = dict(iteration=i, n_prior=int(len(prot)), n_prot=int(prot.sum()), prot_rate=float(prot.mean()),
                     n_newly=int(newly.sum()), n_released=int(rel.sum()), n_released_far=(int(rel_far.sum()) if v == "r6" else None),
                     n_far=(int(far.sum()) if v == "r6" else None),
                     prot_drift_p50=pct(dr[prot], 50), prot_drift_p90=pct(dr[prot], 90), prot_drift_max=float(np.nanmax(dr[prot])) if prot.any() else float("nan"),
                     newly_p10=pct(dr[newly], 10), newly_p50=pct(dr[newly], 50), newly_p90=pct(dr[newly], 90),
                     newly_max=float(np.nanmax(dr[newly])) if newly.any() else float("nan"),
                     n_cnt0=int((z["cnt"] == 0).sum()))
            lst.append(r)
            rows_upd.append([v, s] + list(r.values()))
        R["updates"][f"{v}_{s}"] = lst
write_csv("updates_protection.csv", ["rev", "scene"] + list(R["updates"]["r6_N"][0].keys()), rows_upd)

# end-of-run protected drift (dump at 3500)
R["end"] = {}
for (v, s), dmp in dump.items():
    prior = dmp["origin"] == 1; lk = dmp["locked"].astype(bool); disp = np.linalg.norm(dmp["displacement"], axis=1)
    R["end"][f"{v}_{s}"] = dict(n_prior=int(prior.sum()), n_prot=int((prior & lk).sum()), prot_rate=float((prior & lk).sum() / max(1, prior.sum())),
                                prot_drift_p50=pct(disp[prior & lk], 50), prot_drift_p90=pct(disp[prior & lk], 90),
                                prot_drift_max=float(np.nanmax(disp[prior & lk])) if (prior & lk).any() else float("nan"),
                                free_drift_p50=pct(disp[prior & ~lk], 50), img_drift_p50=pct(disp[~prior], 50),
                                n_total=int(len(prior)))

# ============================================================================ (b) biased scene: old raised main-roof disks left in place
R["raised_roof"] = {}
for v in ("r5", "r6"):
    dmp = dump[(v, "B")]
    prior = dmp["origin"] == 1
    ids = dmp["init_id"].astype(np.int64)
    poly = init_poly(v, "B", ids)
    on = prior & (poly == 3396)
    dz = dmp["displacement"][:, 2]
    stay = on & (np.abs(dz) < 0.1)
    lk = dmp["locked"].astype(bool); op = dmp["opacity"]
    R["raised_roof"][v] = dict(n_on_raised_roof=int(on.sum()), n_stayed=int(stay.sum()), prot_rate_stayed=float(lk[stay].mean()) if stay.any() else float("nan"),
                               n_prot_stayed=int((lk & stay).sum()), opacity_med_stayed=nanmed(op[stay]),
                               opacity_med_stayed_prot=nanmed(op[stay & lk]), opacity_med_stayed_free=nanmed(op[stay & ~lk]),
                               n_stayed_opacity_ge_05=int((stay & (op >= 0.5)).sum()))

# ============================================================================ (c) hidden prior disks within the threshold
R["hidden"] = {}
for s in ("N", "B"):          # r6 in-run at each E update (the implementation's own seeing counts)
    lst = []
    for i in E_ITERS["r6"]:
        z = Enpz[("r6", s)][i]
        hid = (z["cnt"] == 0) & np.isfinite(z["drift"]) & (z["drift"] <= DMAX)
        lst.append(dict(iteration=i, how=str(z["how"]), n_hidden_near=int(hid.sum()), prot_rate=float(z["prot"][hid].mean()) if hid.any() else float("nan")))
    R["hidden"][f"r6_{s}_updates"] = lst
vis = json.loads((R6 / "offline/visibility.json").read_text())["models"] if (R6 / "offline/visibility.json").exists() else {}
for (v, s), dmp in dump.items():   # like-for-like at 3500: same seeing rule on both final models
    f = R6 / f"offline/visibility_{v}_{s}.npz"
    if not f.exists():
        continue
    cnt = np.load(f)["cnt"]
    prior = dmp["origin"] == 1; lk = dmp["locked"].astype(bool); disp = np.linalg.norm(dmp["displacement"], axis=1)
    hid = prior & (cnt == 0) & (disp <= DMAX)
    R["hidden"][f"{v}_{s}_final"] = dict(n_hidden_near=int(hid.sum()), prot_rate=float(lk[hid].mean()) if hid.any() else float("nan"),
                                         n_hidden_any=int((prior & (cnt == 0)).sum()), rows_equal_dump=vis.get(f"{v}_{s}", {}).get("rows_equal_dump"))

# ============================================================================ fix 3: opacity floor
R["opacity"] = {}
for (v, s), o in opac.items():
    R["opacity"][f"{v}_{s}"] = dict(render_nbelow_total=int(np.nansum(o["render_nbelow"])), post_nbelow_total=int(np.nansum(o["post_nbelow"])),
                                    end_nbelow_total=int(np.nansum(o["end_nbelow"])), render_min=float(np.nanmin(o["render_min"])),
                                    end_min=float(np.nanmin(o["end_min"])),
                                    iters_render_below={int(i): int(n) for i, n in zip(o["iteration"], o["render_nbelow"]) if n > 0})

# ============================================================================ fix 4: initialisation and the reset show-through
R["init"] = initc["summary"]
R["init"]["ground_remaining_M_N_on_3401"] = None
pr = list(csv.DictReader(open(R6 / "init_counts/init_counts_by_polygon.csv")))
for p_ in pr:
    if p_["set"] == "M_N" and p_["poly_index"] == "3401":
        R["init"]["ground_remaining_M_N_on_3401"] = int(p_["n_points_on_polygon"]) - int(p_["n_dropped"])
    if p_["set"] == "M_N" and p_["poly_index"] == "3393":
        R["init"]["back_roof_3393_M_N"] = dict(dropped=int(p_["n_dropped"]), total=int(p_["n_points_on_polygon"]))
    if p_["set"] == "L_N" and p_["poly_index"] == "3393":
        R["init"]["back_roof_3393_L_N"] = dict(dropped=int(p_["n_dropped"]), total=int(p_["n_points_on_polygon"]))
dn = dropped["N"]
kept_ground = (~dn["dropped"]) & (dn["type"] == "ground")
R["init"]["kept_ground_M_N"] = int(kept_ground.sum())
if kept_ground.any():   # where are the remaining ground points? distance to the nearest target wall line in XY
    walls = [np.array(PJ[p]["ring_local_xy"]) for p in PJ if PJ[p]["is_target"] and PJ[p]["citygml_type"] == "WallSurface"]
    gxy = dn["xyz"][kept_ground][:, :2]
    dmin = np.full(len(gxy), np.inf)
    for wv in walls:
        for a_, b_ in zip(wv[:-1], wv[1:]):
            ab = b_ - a_; t = np.clip(((gxy - a_) @ ab) / max(ab @ ab, 1e-12), 0, 1)
            dmin = np.minimum(dmin, np.linalg.norm(gxy - (a_ + t[:, None] * ab), axis=1))
    R["init"]["kept_ground_M_N_dist_to_target_wall_p50_p90_max"] = [pct(dmin, 50), pct(dmin, 90), float(dmin.max())]
fid = {vw: cv2.resize(np.load(S2 / "inputs/maps/faceid" / f"{vw}.npy").astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
       for vw in ("DJI_20241217101305_0005_D", "DJI_20241217101343_0024_D")}
R["reset"] = {}
dd_maps = {}
for v in ("r5", "r6"):
    rz = np.load(RUN[(v, "N")] / "audit/maps/reset_03000.npz")
    for vw, f_ in fid.items():
        roof = np.isin(f_, [3387, 3389, 3393, 3394, 3396, 3404])
        db, da = rz[f"depth_before_{vw}"], rz[f"depth_after_{vw}"]
        dd = np.where((db > 0) & (da > 0), da - db, np.nan)
        dd_maps[(v, vw)] = (dd, roof)
        R["reset"][f"{v}_{vw.split('_')[-2]}"] = dict(median_abs_change_m=nanmed(np.abs(dd[roof])), p90_abs_change_m=pct(np.abs(dd[roof]), 90),
                                                     frac_farther_1m=float(np.nanmean(dd[roof] > 1.0)))
    ev = [e for e in jl(RUN[(v, "N")] / "audit/densify.jsonl") if e["event"] == "opacity_reset"]
    R["reset"][f"{v}_event"] = ev[0] if ev else None

# ============================================================================ fix 5: which term pulls harder, per E bin
g = np.load(R6 / "runs/N/audit/grad_02999.npz")
bins = np.linspace(0, 1, 11)
Eg = g["E"]
both_old = (g["norm_mvs_old"] > 0) & (g["norm_prior_old"] > 0)
both_new = (g["norm_mvs_new"] > 0) & (g["norm_prior_new"] > 0)
dom_old = g["norm_prior_old"] > g["norm_mvs_old"]; dom_new = g["norm_prior_new"] > g["norm_mvs_new"]
brow = []
R["grad"] = dict(n=int(len(Eg)), n_both=int(both_new.sum()), bins=[])
for k in range(10):
    m = (Eg >= bins[k]) & ((Eg < bins[k + 1]) if k < 9 else (Eg <= 1.0))
    mo, mn = m & both_old, m & both_new
    r = dict(E_lo=float(bins[k]), E_hi=float(bins[k + 1]), n=int(m.sum()), n_both=int(mn.sum()),
             prior_dominant_old=float(dom_old[mo].mean()) if mo.any() else float("nan"),
             prior_dominant_new=float(dom_new[mn].mean()) if mn.any() else float("nan"),
             median_ratio_old=nanmed(g["norm_prior_old"][mo] / g["norm_mvs_old"][mo]) if mo.any() else float("nan"),
             median_ratio_new=nanmed(g["norm_prior_new"][mn] / g["norm_mvs_new"][mn]) if mn.any() else float("nan"))
    R["grad"]["bins"].append(r); brow.append(list(r.values()))
lo, hi = Eg < 0.5, Eg >= 0.5
R["grad"]["below05"] = dict(old=float(dom_old[lo & both_old].mean()), new=float(dom_new[lo & both_new].mean()),
                            n=int((lo & both_new).sum()))
R["grad"]["above05"] = dict(old=float(dom_old[hi & both_old].mean()), new=float(dom_new[hi & both_new].mean()),
                            n=int((hi & both_new).sum()))
R["grad"]["per_view"] = json.loads((R6 / "runs/N/audit/grad_02999.json").read_text())["per_view"]
write_csv("fix5_prior_dominance_by_E.csv", list(R["grad"]["bins"][0].keys()), brow)

# ============================================================================ weights: losses, protected drift, read-outs
R["terms"] = {}
for (v, s), sc in scal.items():
    R["terms"][f"{v}_{s}"] = {i: {k: sc[i].get(k) for k in ("rgb", "mvs", "prior", "normal", "dist", "total", "lambda_mvs", "lambda_prior",
                                                          "px_mvs_n", "px_prior_n")} for i in (1, 500, 3000) if i in sc}
R["faces"] = {}
frows = []
for (v, s), p in RUN.items():
    for it in (3000, 3500):
        f = p / f"model/monitor/faces_{it}.json"
        if f.exists():
            for r in json.load(open(f)):
                R["faces"].setdefault(f"{v}_{s}_{it}", {})[str(r["face"])] = dict(d=r["d"], e=r["e"], g=r["g"], cov=r["cov"], label=r["label"])
                frows.append([v, s, it, r["face"], r["d"], r["e"], r["g"], r["cov"], r["label"]])
write_csv("faces_readout.csv", ["rev", "scene", "iteration", "face", "d_F", "e_F", "g_F", "cov_F", "label"], frows)

# unchanged lock: protected per-iteration xyz update (|dx|/lr), applied/raw ratio
R["lock"] = {}
for (v, s), st in steps.items():
    it_ = st["iteration"]
    R["lock"][f"{v}_{s}"] = dict(prot_xyz_mean_med=nanmed(st["prot_xyz_mean"]), prot_xyz_med_med=nanmed(st["prot_xyz_med"]),
                                 prot_xyz_act_med=nanmed(st["prot_xyz_act_med"]), applied_over_raw_med=nanmed(st["prot_applied_over_raw_xyz_med"]),
                                 free_xyz_mean_med=nanmed(st["free_xyz_mean"]), zero_frac=nanmed(st["prot_xyz_zero_frac"]),
                                 prot_fdc_mean_med=nanmed(st["prot_fdc_mean"]))

# ============================================================================ figures
# plane of the raised main roof (biased scene) fitted to its initial prior points; downslope coordinate s from its normal
_pb = dropped["B"]["xyz"][dropped["B"]["poly"] == 3396].astype(np.float64)
_A = np.c_[_pb[:, 0], _pb[:, 1], np.ones(len(_pb))]
_coef = np.linalg.lstsq(_A, _pb[:, 2], rcond=None)[0]           # z = a x + b y + c
_down = -np.array(_coef[:2]) / np.linalg.norm(_coef[:2])          # horizontal direction of steepest descent
_c0 = _pb[:, :2].mean(0)
_slope = float(np.linalg.norm(_coef[:2]))
R["raised_roof_plane"] = dict(a=float(_coef[0]), b=float(_coef[1]), c=float(_coef[2]), slope=_slope,
                              fit_rms=float(np.sqrt(np.mean((_A @ _coef - _pb[:, 2]) ** 2))))


def panel_side(ax, v):
    dmp = dump[(v, "B")]
    prior = dmp["origin"] == 1
    poly = init_poly(v, "B", dmp["init_id"].astype(np.int64))
    on = prior & (poly == 3396)
    xyz = dmp["xyz"]; lk = dmp["locked"].astype(bool); op = np.clip(dmp["opacity"], 0, 1)
    sd = (xyz[:, :2] - _c0) @ _down
    zr = (np.c_[xyz[:, 0], xyz[:, 1], np.ones(len(xyz))] @ _coef)      # raised plane height under each disk
    for m, c in ((on & ~lk, (0.12, 0.47, 0.71)), (on & lk, (0.84, 0.15, 0.16))):
        rgba = np.zeros((m.sum(), 4)); rgba[:, :3] = c; rgba[:, 3] = 0.12 + 0.88 * op[m]
        ax.scatter(sd[m], xyz[m, 2] - zr[m], s=3, c=rgba, linewidths=0, rasterized=True)
    ax.axhline(0.0, color="tab:orange", lw=1.0, ls="--", label="raised prior surface (+1 m)")
    ax.axhline(-1.0, color="k", lw=1.0, ls="-", label="nominal roof (photos)")
    ax.set_ylim(-1.8, 0.6)
    ax.set_xlabel("downslope position on roof 3396 (m)", fontsize=7.5); ax.set_ylabel("height above raised prior (m)", fontsize=7.5)
    ax.tick_params(labelsize=7)
    n_st = R["raised_roof"][v]
    ax.text(0.01, 0.04, f"{v}: {int(on.sum())} prior disks from 3396, stayed (|dz|<0.1 m) {n_st['n_stayed']}, "
            f"of those protected {n_st['n_prot_stayed']}", transform=ax.transAxes, fontsize=7)


def panel_newly(ax):
    pos, data, cols, labels = [], [], [], []
    k = 0
    for v in ("r5", "r6"):
        for i in E_ITERS[v][1:]:
            z = Enpz[(v, "N")][i]
            nw = z["prot"].astype(bool) & ~z["prev_prot"].astype(bool)
            x = z["drift"][nw]; x = x[np.isfinite(x)]
            data.append(np.maximum(x, 1e-4) if x.size else np.array([np.nan])); pos.append(k); cols.append(COL[v]); labels.append(f"{v}\n{i}")
            k += 1
        k += 1
    bp = ax.boxplot(data, positions=pos, widths=0.6, whis=(10, 90), showfliers=False, patch_artist=True)
    for b, c in zip(bp["boxes"], cols):
        b.set_facecolor(c); b.set_alpha(0.5)
    for p_, d_ in zip(pos, data):
        if np.isfinite(d_).any():
            ax.plot(p_, np.nanmax(d_), marker="v", color="k", ms=3)
    ax.axhline(DMAX, color="k", ls="--", lw=0.9); ax.text(pos[-1] + 0.5, DMAX, "4 tau = 0.227 m", fontsize=7, va="bottom", ha="right")
    ax.set_yscale("log"); ax.set_ylim(1e-3, 20)
    ax.set_xticks(pos); ax.set_xticklabels(labels, fontsize=6)
    ax.set_ylabel("distance from initial position (m)", fontsize=7.5)
    ax.set_title("newly protected disks per E update (nominal scene); box p25-p75, whiskers p10-p90, marker max", fontsize=7.5)


def panel_opacity(ax):
    for (v, s), ls in ((("r6", "N"), "-"), (("r6", "B"), "--")):
        o = opac[(v, s)]
        ax.plot(o["iteration"], o["render_min"], color="tab:blue", lw=1.3, ls=ls, label=f"r6 {s}: min as rendered")
        ax.plot(o["iteration"], o["end_min"], color="tab:green", lw=1.0, ls=ls, label=f"r6 {s}: min end of iteration")
    o = opac[("r5", "N")]
    ax.plot(o["iteration"], o["render_min"], color="tab:red", lw=0.7, alpha=0.8, label="r5 N: min as rendered")
    ax.axhline(0.5, color="k", ls=":", lw=0.8); ax.axvline(3000, color="tab:purple", ls="-.", lw=1.0, label="opacity reset 3000")
    ax.set_yscale("log"); ax.set_ylim(1e-3, 1.2); ax.set_xlabel("iteration", fontsize=7.5); ax.set_ylabel("protected-disk opacity", fontsize=7.5)
    ax.legend(fontsize=6, loc="lower left"); ax.grid(alpha=0.3); ax.tick_params(labelsize=7)


TYPE_COL = {"roof": "tab:red", "wall": "tab:orange", "ground": "tab:purple", "other": "0.5"}


def panel_dropped(ax):
    d = dropped["N"]
    ax.scatter(d["xyz"][~d["dropped"], 0], d["xyz"][~d["dropped"], 1], s=0.1, color="0.85", linewidths=0, rasterized=True)
    for t_ in ("wall", "roof", "ground"):
        m = d["dropped"] & (d["type"] == t_)
        ax.scatter(d["xyz"][m, 0], d["xyz"][m, 1], s=0.2, color=TYPE_COL[t_], linewidths=0, rasterized=True, label=f"{t_} {m.sum()}")
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.legend(fontsize=6, markerscale=15, loc="lower right")
    ax.set_title("dropped prior points (M nominal), grey = kept", fontsize=7.5)


def panel_depth_change(ax, v, vw="DJI_20241217101343_0024_D"):
    dd, roof = dd_maps[(v, vw)]
    ys, xs = np.nonzero(roof)
    y0, y1, x0, x1 = max(0, ys.min() - 30), min(H, ys.max() + 30), max(0, xs.min() - 30), min(W, xs.max() + 30)
    h = ax.imshow(dd[y0:y1, x0:x1], cmap="RdBu_r", vmin=-15, vmax=15)
    ax.contour(roof[y0:y1, x0:x1].astype(float), levels=[0.5], colors="k", linewidths=0.5)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{v}: depth after - before reset (m), view 0024", fontsize=7.5)
    return h


def panel_grad(ax):
    x = [(b["E_lo"] + b["E_hi"]) / 2 for b in R["grad"]["bins"]]
    ax.plot(x, [b["prior_dominant_old"] for b in R["grad"]["bins"]], "o-", color="tab:red", label="old normalisation (r5: own weight sums)")
    ax.plot(x, [b["prior_dominant_new"] for b in R["grad"]["bins"]], "o-", color="tab:blue", label="new normalisation (r6: pixel count)")
    ax.axvline(0.5, color="k", ls=":", lw=0.8)
    ax.set_xlabel("Gaussian confidence E (bin centre)", fontsize=7.5)
    ax.set_ylabel("share where prior-depth pull > MVS pull", fontsize=7.5)
    ax.set_ylim(-0.02, 1.02); ax.legend(fontsize=6.5); ax.grid(alpha=0.3); ax.tick_params(labelsize=7)
    ax.set_title("disks pulled by both depth terms, checkpoint 2999 (nominal scene)", fontsize=7.5)


def panel_drift_map(axs):
    norm = Normalize(0, 0.5)
    sc = None
    for ax, v in zip(axs, ("r5", "r6")):
        dmp = dump[(v, "N")]; prior = dmp["origin"] == 1
        xyz, dsp = dmp["xyz"][prior], np.linalg.norm(dmp["displacement"][prior], axis=1)
        o = np.argsort(dsp)
        sc = ax.scatter(xyz[o, 0], xyz[o, 1], c=np.clip(dsp[o], 0, 0.5), s=0.15, cmap="magma", norm=norm, linewidths=0, rasterized=True)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.set_facecolor("0.85")
        ax.set_xlim(crop[0, 0], crop[1, 0]); ax.set_ylim(crop[0, 1], crop[1, 1])
        ax.set_title(f"{v}: prior disks at 3500, drift from initial", fontsize=7.5)
    return sc


# workspace figures
fig, axs = plt.subplots(1, 2, figsize=(16, 5)); panel_side(axs[0], "r5"); panel_side(axs[1], "r6"); axs[0].legend(fontsize=7)
fig.tight_layout(); fig.savefig(FIG / "fig1_raised_roof_side.png", dpi=120); plt.close(fig)
fig, ax = plt.subplots(figsize=(12, 4.5)); panel_newly(ax); fig.tight_layout(); fig.savefig(FIG / "fig2_newly_protected_distance.png", dpi=120); plt.close(fig)
fig, ax = plt.subplots(figsize=(9, 4.5)); panel_opacity(ax); fig.tight_layout(); fig.savefig(FIG / "fig3_opacity_min.png", dpi=120); plt.close(fig)
fig, axs = plt.subplots(1, 3, figsize=(18, 5)); panel_dropped(axs[0]); panel_depth_change(axs[1], "r5"); h = panel_depth_change(axs[2], "r6")
fig.colorbar(h, ax=axs[1:], fraction=0.02); fig.savefig(FIG / "fig4_init_and_reset.png", dpi=120, bbox_inches="tight"); plt.close(fig)
for vw in fid:
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.5)); panel_depth_change(axs[0], "r5", vw); h = panel_depth_change(axs[1], "r6", vw)
    fig.colorbar(h, ax=axs, fraction=0.02); fig.savefig(FIG / f"fig4b_reset_depth_{vw.split('_')[-2]}.png", dpi=110, bbox_inches="tight"); plt.close(fig)
fig, ax = plt.subplots(figsize=(8, 4.5)); panel_grad(ax); fig.tight_layout(); fig.savefig(FIG / "fig5_prior_dominance.png", dpi=120); plt.close(fig)
fig, axs = plt.subplots(1, 2, figsize=(12, 5.5)); sc = panel_drift_map(axs); fig.colorbar(sc, ax=axs, fraction=0.03, label="m (clip 0.5)")
fig.savefig(FIG / "fig6_drift_map.png", dpi=120, bbox_inches="tight"); plt.close(fig)

# summary figure
fig = plt.figure(figsize=(21, 12))
G = fig.add_gridspec(2, 3, hspace=0.30, wspace=0.18)
g1 = G[0, 0].subgridspec(2, 1, hspace=0.45); a1 = [fig.add_subplot(g1[i, 0]) for i in range(2)]
panel_side(a1[0], "r5"); panel_side(a1[1], "r6")
a1[0].set_title("(1) Fix 1-2, biased scene: prior disks of raised roof 3396 at 3500, side view\nr5 (red = protected, blue = not; alpha = opacity)", fontsize=8)
a1[1].set_title("r6", fontsize=8); a1[0].legend(fontsize=6, loc="upper right")
a2 = fig.add_subplot(G[0, 1]); panel_newly(a2)
a2.set_title("(2) Fix 2: distance of newly protected disks from their initial position per E update\n(nominal scene, r5 red, r6 blue; line = 4 tau)", fontsize=8)
a3 = fig.add_subplot(G[0, 2]); panel_opacity(a3); a3.set_title("(3) Fix 3: minimum opacity of protected disks", fontsize=8)
g4 = G[1, 0].subgridspec(1, 3, wspace=0.08, width_ratios=[1.1, 1, 1]); a4 = [fig.add_subplot(g4[0, i]) for i in range(3)]
panel_dropped(a4[0]); panel_depth_change(a4[1], "r5"); h = panel_depth_change(a4[2], "r6")
a4[0].set_title("(4) Fix 4: dropped prior points (M nominal)", fontsize=8)
a4[1].set_title("reset: depth after-before\nr5, view 0024", fontsize=8); a4[2].set_title("r6 (both -15..15 m)", fontsize=8)
cb4 = fig.colorbar(h, ax=a4[1:], fraction=0.05, shrink=0.8); cb4.ax.tick_params(labelsize=6)
a5 = fig.add_subplot(G[1, 1]); panel_grad(a5); a5.set_title("(5) Fix 5: share of disks where the prior-depth pull is stronger, by E\n(same checkpoint 2999, only the denominators differ)", fontsize=8)
g6 = G[1, 2].subgridspec(1, 3, width_ratios=[1, 1, 0.05], wspace=0.05); a6 = [fig.add_subplot(g6[0, i]) for i in range(2)]
sc = panel_drift_map(a6); cb = fig.colorbar(sc, cax=fig.add_subplot(g6[0, 2])); cb.set_label("drift (m, clip 0.5)", fontsize=7)
a6[0].set_title("(6) Weights: prior-disk drift at 3500, nominal\nr5", fontsize=8); a6[1].set_title("r6", fontsize=8)
fig.suptitle("PHD-STAGE2-R6-FIX-v1: stage-2 fork r6 vs r5, LoD2 prior, nominal (P_M_N) and main-roof +1 m (P_M_B), 3,500 iterations, seed 0", fontsize=11)
fig.savefig(OUT / "summary_r6.png", dpi=105, bbox_inches="tight"); plt.close(fig)

json.dump(R, open(OUT / "results.json", "w"), indent=1, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))
print(json.dumps({k: R[k] for k in ("runs", "raised_roof", "hidden", "opacity", "reset", "lock")}, indent=1, default=str)[:6000])
