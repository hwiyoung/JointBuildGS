"""PHD-STAGE2-R8-FOUR-CASES-v1 step 8 (jointbuildgs:dev, CPU): the four cases of the research intent after the short trainings.

  python four_cases.py      # mounts: /artifacts (ro), /repo (ro), /r7 (ro), /p8 (rw)

Pixels: the 13 training views at the training resolution (1600 x 1157); per-view maps of the stage-1 product and inputs
resampled with nearest neighbour exactly as the fork loads them (jbgs_judgment._load_set). Result = rendered expected
depth D and accumulated opacity of the final dump (iteration 3,500). Every difference is a height difference as in
method 3.3: (X - Y) x f with f the scene's own conversion map (vertical on roof-like, along the normal on wall-like
surfaces); tau in metres = the pixel's tolerance (tau map x f).
  case 1  observed, within tolerance : c_p = 1 and g_p = 1
  case 2  observed, beyond tolerance : pixels of support units voted conflict with c_p = 1 (+ pixels without a unit, c_p = 1,
                                       own mark conflict)
  case 3  not observed, in the image : c_p = 0 pixels of missing units, by propagated judgment (agree / conflict /
                                       undetermined); in the +1 m settings also the injected pixels (|P_B - P_N| x f > 0.5 m)
                                       and whether the result went to the raised prior or stayed at the nominal one;
                                       extra rows: c_p = 0 pixels of support units by vote, c_p = 0 pixels without a unit
  case 4  not in any image           : Gaussians planted from invisible units (dump records) and the mesh check
  protection over time               : monitor/E.jsonl
Writes /p8/cases/{tables.md, cases.json}."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v2 import rule  # noqa: E402

P8 = Path("/p8"); OUT = P8 / "cases"; OUT.mkdir(parents=True, exist_ok=True)
S2 = Path("/artifacts/JointBuildGS/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1")
MAPS = S2 / "inputs/maps"
CFG = json.loads(Path("/repo/configs/phd/stage2_r8_four_cases_v1/r8.json").read_text())
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
RUNS = ["M_N", "M_B", "L_N", "L_B", "M_N_noprior"]
RUN_NAME = {"M_N": "LoD2 정상", "M_B": "LoD2 주지붕 +1 m", "L_N": "항공 LiDAR 정상", "L_B": "항공 LiDAR 주지붕 +1 m",
            "M_N_noprior": "LoD2 정상, 사전 정보 깊이 항 끔"}
ITS = int(CFG["training"]["iterations"])
H, W = 1157, 1600


def rs(a, interp=cv2.INTER_NEAREST):
    return cv2.resize(a.astype(np.float32), (W, H), interpolation=interp) if a.shape != (H, W) else a.astype(np.float32)


def view_arrays(run, setting, stem):
    dump = P8 / "runs" / run / f"model/dump/iteration_{ITS}"
    D = np.load(dump / f"{stem}_depth.npy").astype(np.float64)
    AL = np.load(dump / f"{stem}_alpha.npy").astype(np.float32)
    A = rs(np.load(MAPS / f"conf/raw_depth/{stem}.npy")) > 0.5
    M = rs(np.load(MAPS / f"mvs/raw_depth/{stem}.npy")).astype(np.float64)
    P = rs(np.load(MAPS / f"prior_{setting}/raw_depth/{stem}.npy")).astype(np.float64)
    G = rs(np.load(MAPS / f"gt_clean/raw_depth/{stem}.npy")).astype(np.float64)
    prod = P8 / "stage1/products" / setting
    f = rs(np.load(prod / "fconv" / f"{stem}.npy")).astype(np.float64)
    lm = rs(np.load(prod / "locmap" / f"{stem}.npy")).astype(np.int64)
    mk = rs(np.load(prod / "markmap" / f"{stem}.npy")).astype(np.int64)
    taup = rs(np.load(P8 / "inputs" / setting / "tau" / f"{stem}.npy")).astype(np.float64)
    tau_m = taup * np.maximum(f, 1e-3)
    return dict(D=D, AL=AL, A=A, M=M, P=P, G=G, f=f, lm=lm, mk=mk, tau=tau_m)


def nmed(x):
    x = x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else float("nan")


def share(m):
    return float(m.mean()) if m.size else float("nan")


KEYS = ("D", "P", "M", "G", "f", "tau", "AL", "A")


def collect(sel, v):
    return {k: v[k][sel] for k in KEYS}


def summarise(chunks, injected=False):
    if not chunks:
        return dict(n=0)
    c = {k: np.concatenate([x[k] for x in chunks]) for k in KEYS}
    n = len(c["D"])
    if n == 0:
        return dict(n=0)
    rend = np.isfinite(c["D"]) & (c["D"] > 0)
    dP = np.where(rend, (c["D"] - c["P"]) * c["f"], np.nan)
    tau = c["tau"]
    okM = rend & c["A"] & np.isfinite(c["M"]) & (c["M"] > 0)
    dM = np.where(okM, (c["D"] - c["M"]) * c["f"], np.nan)
    okG = rend & np.isfinite(c["G"]) & (c["G"] > 0)
    dG = np.where(okG, (c["D"] - c["G"]) * c["f"], np.nan)
    gP = np.where(okG, (c["G"] - c["P"]) * c["f"], np.nan)
    s_ = dict(n=int(n), n_rendered=int(rend.sum()), median_abs_dP_cm=100 * nmed(np.abs(dP)), median_dP_cm=100 * nmed(dP),
              within_tau_of_prior=share(np.abs(dP[rend]) <= tau[rend]), built_share=share(c["AL"] >= 0.5),
              n_mvs=int(okM.sum()), median_abs_dM_cm=100 * nmed(np.abs(dM)), median_dM_cm=100 * nmed(dM),
              within_tau_of_mvs=share(np.abs(dM[okM]) <= tau[okM]),
              n_gt=int(okG.sum()), median_abs_dG_cm=100 * nmed(np.abs(dG)), within_tau_of_gt=share(np.abs(dG[okG]) <= tau[okG]),
              median_gt_minus_prior_cm=100 * nmed(gP))
    if injected:   # raised by +1 m: the nominal surface lies 1 m below the raised one (height units of roof-like pixels)
        s_.update(within_tau_of_raised=share(np.abs(dP[rend]) <= tau[rend]),
                  within_tau_of_nominal=share(np.abs(dP[rend] - 1.0) <= tau[rend]),
                  median_dP_minus_1m_cm=100 * nmed(dP - 1.0))
    return s_


INJ = {"M_B": lambda tab: {3396}, "L_B": lambda tab: {e for e, r in tab.items() if r.get("raised_share", 0) >= 0.5 and r.get("is_building_face")}}
res = {}
for run in RUNS:
    rec = json.loads((P8 / "runs" / run / "receipt.json").read_text())
    setting = rec["setting"]
    lz = np.load(P8 / "runs" / run / "model/monitor/locations.npz")
    state, vote, J, Jl, lkind, lsurf = lz["state"], lz["vote"], lz["judgment"], lz["unit_judgment"], lz["kind"], lz["surface_ext"]
    var = "poly" if setting.startswith("M") else "lod2"
    table = {r["ext"]: r for r in json.loads((P8 / "stage1/products" / setting / f"surfaces_{var}.json").read_text())["surfaces"]}
    inj_set = INJ[setting](table) if setting in INJ else set()
    inj_unit = np.isin(lsurf, list(inj_set)) & (lkind == 1)
    groups = {}
    for stem in TRAIN:
        v = view_arrays(run, setting, stem)
        prior = np.isfinite(v["P"]) & (v["P"] > 0) & np.isfinite(v["f"])
        loc = v["lm"]; located = loc >= 0
        lc = np.where(located, loc, 0)
        stt = np.where(located, state[lc], -1); vt = np.where(located, vote[lc], -1)
        jt = np.where(located, J[lc], -1); jlt = np.where(located, Jl[lc], -1)
        kd = np.where(located, lkind[lc], 0); inj = located & inj_unit[lc]
        g1 = ~rule.prior_term_off(located, jlt, v["A"].astype(np.float32), v["mk"])
        A = v["A"]
        base = {"c1": prior & A & g1,
                "c2": prior & A & located & (stt == rule.ST_SUPPORT) & (vt == rule.V_CONFLICT),
                "c2_no_patch": prior & A & ~located & (v["mk"] == rule.MARK_CONFLICT),
                "c3_agree": prior & ~A & located & (stt == rule.ST_MISSING) & (jt == rule.J_AGREE),
                "c3_conflict": prior & ~A & located & (stt == rule.ST_MISSING) & (jt == rule.J_CONFLICT),
                "c3_undetermined": prior & ~A & located & (stt == rule.ST_MISSING) & np.isin(jt, [rule.J_MIXED, rule.J_INSUFF]),
                "x_support_c0_agree": prior & ~A & located & (stt == rule.ST_SUPPORT) & (vt == rule.V_AGREE),
                "x_support_c0_conflict": prior & ~A & located & (stt == rule.ST_SUPPORT) & (vt == rule.V_CONFLICT),
                "x_no_patch_c0": prior & ~A & ~located}
        sel = {}
        for k, m in base.items():
            sel[k] = m
            if not k.endswith("no_patch") and not k.endswith("no_patch_c0"):
                sel[k + "|roof"] = m & located & (kd == 1)
                sel[k + "|wall"] = m & located & (kd == 2)
        sel["c1|no_patch"] = base["c1"] & ~located
        if inj_set:
            for k in ("c1", "c2", "c3_agree", "c3_conflict", "c3_undetermined"):
                sel[k + "|injected"] = base[k] & inj
        for k, m in sel.items():
            groups.setdefault(k, []).append(collect(m, v))
    res[run] = {k: summarise(c, injected=k.endswith("|injected")) for k, c in groups.items()}
    # case 4: Gaussians planted from invisible units
    dz = np.load(P8 / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
    ip = np.load(P8 / "runs" / run / "model/monitor/init_points.npz")
    cat_init = ip["category"][ip["planted"]]                      # rows of the initial disks after planting
    n_init_inv = int((cat_init == 3).sum())
    c = dz["init_category"]; alive_inv = c == 3
    prior = dz["origin"] == 1
    removed = dz["init_removed_at"]; cat0 = dz["init_category_of_initial"]
    op = dz["opacity"]
    u = dz["u"]; d3 = dz["drift_3d"]
    mesh = json.loads((P8 / "mesh" / run / "mesh.json").read_text()) if (P8 / "mesh" / run / "mesh.json").exists() else None
    inv_now = np.load(P8 / "mesh" / run / "invisible.npz") if (P8 / "mesh" / run / "invisible.npz").exists() else None
    c4 = dict(n_initial=n_init_inv, n_initial_ids_removed=int(((cat0 == 3) & (removed >= 0)).sum()),
              n_end=int(alive_inv.sum()), n_end_opacity_ge_05=int((alive_inv & (op >= 0.5)).sum()),
              share_end_opacity_ge_05=float((op[alive_inv] >= 0.5).mean()) if alive_inv.any() else float("nan"),
              u_median_mm=1000 * nmed(u[alive_inv]), u_p99_mm=1000 * float(np.nanpercentile(u[alive_inv], 99)) if alive_inv.any() else float("nan"),
              u_max_mm=1000 * float(np.nanmax(u[alive_inv])) if alive_inv.any() else float("nan"),
              drift3d_median_mm=1000 * nmed(d3[alive_inv]), drift3d_max_mm=1000 * float(np.nanmax(d3[alive_inv])) if alive_inv.any() else float("nan"),
              drift3d_p99_mm=1000 * float(np.nanpercentile(d3[alive_inv], 99)) if alive_inv.any() else float("nan"),
              n_initial_ids_alive=int(((cat0 == 3) & (removed < 0)).sum()),
              protected_end=int((alive_inv & dz["locked"]).sum()), no_seeing_view_last_read=int((alive_inv & (dz["E_cnt"] == 0)).sum()))
    if inv_now is not None:
        iv = inv_now["invisible"]
        c4.update(n_end_invisible_final_render=int((alive_inv & iv).sum()),
                  all_prior_invisible_final=int((prior & iv).sum()), all_prior_invisible_final_opaque=int((prior & iv & (op >= 0.5)).sum()))
    if mesh is not None:
        c4["mesh"] = mesh["groups"]
        c4["mesh_virtual_cameras"] = mesh["n_virtual_cameras"]
    # protected Gaussians on support patches voted conflict (eq. 7 excludes only the propagated conflict)
    loc_j = dz["unit_judgment"]; located = dz["located"]; lockd = dz["locked"]
    sc = lockd & located & (loc_j == rule.J_CONFLICT)
    ids = dz["init_id"].astype(np.int64)
    surf_ext_init = dz["init_surface_ext"]
    ext_row = np.where(ids >= 0, surf_ext_init[np.maximum(ids, 0)], -1)
    vals, cnts = np.unique(ext_row[sc], return_counts=True)
    order = np.argsort(-cnts)[:8]
    c4["protected_on_support_conflict"] = dict(n=int(sc.sum()), no_seeing_view=int((sc & (dz["E_cnt"] == 0)).sum()),
                                               opacity_ge_05=int((sc & (op >= 0.5)).sum()),
                                               top_surfaces={str(int(vals[i])): int(cnts[i]) for i in order},
                                               u_median_mm=1000 * nmed(u[sc]))
    c4["protected_total"] = int(lockd.sum())
    c4["protected_by_initial_category"] = {str(k): int((lockd & (c == k)).sum()) for k in range(5)}
    # opacity-floor and removal by initial category
    c4["removed_by_category"] = {str(k): int(((cat0 == k) & (removed >= 0)).sum()) for k in range(5)}
    c4["initial_by_category"] = {str(k): int((cat0 == k).sum()) for k in range(5)}
    res[run]["case4"] = c4
    # protection over time
    rows = [json.loads(l) for l in (P8 / "runs" / run / "model/monitor/E.jsonl").read_text().splitlines() if l.strip()]
    res[run]["protection"] = [dict(iteration=r["iteration"], n_locked=r["n_locked"], newly=r["n_newly_locked"], released=r["n_released"],
                                   released_by=r["released_by"], by_category=r["locked_by_initial_category"],
                                   on_support_conflict=r["locked_on_support_conflict_unit"], no_view=r["n_prior_no_seeing_view"],
                                   differ_3d=r["would_differ_with_3d_distance"], conflict_excluded=r["n_conflict_excluded"]) for r in rows]
    print(run, json.dumps({k: res[run][k] for k in ("c1", "c2", "c3_conflict", "case4")}, default=float)[:1500], flush=True)

(OUT / "cases.json").write_text(json.dumps(res, indent=1, default=float))
print("written", OUT / "cases.json")
