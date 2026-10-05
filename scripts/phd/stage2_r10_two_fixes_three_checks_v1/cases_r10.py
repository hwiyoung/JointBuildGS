"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 step 13 (jointbuildgs:dev, CPU): the four cases of r9 with the r10 trainings (same
definitions as cases_r9.py), the checks of the two fixes and the three checks, each beside r9.

  python cases_r10.py [part ...]      # parts: cases ga na da ra ma prot (default all)
  mounts: /artifacts (ro), /repo (ro), /r7 (ro), /r8 (ro), /p9 (ro), /p10 (rw)

cases  the four cases (r9's keys) of every r10 training; LoD2 runs read the r10 prior depth and product, airborne LiDAR runs
       r9's (unchanged)
ga     the offline re-read of the two reset states (probe_<run>/monitor/reset_probe.json) beside the in-run re-read at 3,000
na     party walls: patches of the cut polygons, prior Gaussians on the cut parts at the end (r9 and r10), protection at the
       start and the end; the opacity reset at 3,000 on the target building's pixels (r10 M_N, r9 M_N, r9's control run of
       the r8 code; airborne LiDAR r10 L_N_vertex, beside nothing)
da     the two mesh layers: share of the aimed Gaussians within 0.25 m (all, per face), mesh -> prior distance, occluders,
       spread from the repeated runs
ra     vertex against cell: r9's table S-L_N rows, case 3 with the ground-truth columns, case 4, the angles of table da-1
ma     case 3 ground-truth columns of the existing trainings (r8, r8 again, r9, r9 without fix 'da'; LoD2 and airborne LiDAR
       nominal) and of the r10 trainings, with r9's definitions; pixel positions for the figure
prot   protection per re-read (r9 table 5) of every r10 training
Writes /p10/cases/<part>.json (+ npz for figures)."""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v4 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v4 import orientation as ori  # noqa: E402
from src.phd.prior_propagation_v4 import rule  # noqa: E402

P10 = Path("/p10"); P9 = Path("/p9"); R8 = Path("/r8"); R7 = Path("/r7"); OUT = P10 / "cases"; OUT.mkdir(parents=True, exist_ok=True)
S2 = Path("/artifacts/JointBuildGS/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1")
MAPS = S2 / "inputs/maps"
CFG = json.loads(Path("/repo/configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json").read_text())
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
ITS = int(CFG["training"]["iterations"])
H, W = 1157, 1600
R10RUNS = list(CFG["training"]["runs"])
PARTS = sys.argv[1:] or ["cases", "ga", "na", "da", "ra", "ma", "prot"]


def rs(a, interp=cv2.INTER_NEAREST):
    return cv2.resize(a.astype(np.float32), (W, H), interpolation=interp) if a.shape != (H, W) else a.astype(np.float32)


def nmed(x):
    x = x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else float("nan")


def pct(x, q):
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else float("nan")


def share(m):
    return float(m.mean()) if m.size else float("nan")


def jdump(name, obj):
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o)))


# ------------------------------------------------------------------ run registry: (payload root, run dir name, setting, product root)
def reg(tag):
    """'r10:M_N' / 'r9:L_N' / 'r9:r8rep_L_N' / 'r8:L_N' -> dict(root, run, setting, prod, prior_dir, tau_dir)."""
    pay, run = tag.split(":")
    root = {"r10": P10, "r9": P9, "r8": R8}[pay]
    setting = json.loads((root / "runs" / run / "receipt.json").read_text())["setting"]
    if pay == "r8" or run.startswith("r8rep"):
        prod = R8
    elif pay == "r10" and setting.startswith("M"):
        prod = P10
    else:
        prod = P9
    lod2 = setting.startswith("M")
    prior_dir = (prod / "stage1/prior" / setting / "raw_depth") if (lod2 and prod in (P9, P10)) else (MAPS / f"prior_{setting}/raw_depth")
    return dict(tag=tag, root=root, run=run, setting=setting, prod=prod, prior_dir=prior_dir, tau_dir=prod / "inputs" / setting / "tau",
                var="poly" if lod2 else "lod2")


def view_arrays(R, stem, it=ITS):
    dump = R["root"] / "runs" / R["run"] / f"model/dump/iteration_{it}"
    D = np.load(dump / f"{stem}_depth.npy").astype(np.float64)
    AL = np.load(dump / f"{stem}_alpha.npy").astype(np.float32)
    A = rs(np.load(MAPS / f"conf/raw_depth/{stem}.npy")) > 0.5
    M = rs(np.load(MAPS / f"mvs/raw_depth/{stem}.npy")).astype(np.float64)
    P = rs(np.load(R["prior_dir"] / f"{stem}.npy")).astype(np.float64)
    G = rs(np.load(MAPS / f"gt_clean/raw_depth/{stem}.npy")).astype(np.float64)
    prod = R["prod"] / "stage1/products" / R["setting"]
    f = rs(np.load(prod / "fconv" / f"{stem}.npy")).astype(np.float64)
    lm = rs(np.load(prod / "locmap" / f"{stem}.npy")).astype(np.int64)
    mk = rs(np.load(prod / "markmap" / f"{stem}.npy")).astype(np.int64)
    taup = rs(np.load(R["tau_dir"] / f"{stem}.npy")).astype(np.float64)
    return dict(D=D, AL=AL, A=A, M=M, P=P, G=G, f=f, lm=lm, mk=mk, tau=taup * np.maximum(f, 1e-3))


KEYS = ("D", "P", "M", "G", "f", "tau", "AL", "A")


def collect(sel, v):
    return {k: v[k][sel] for k in KEYS}


def summarise(chunks, injected=False):   # cases_r9.summarise
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
              median_gt_minus_prior_cm=100 * nmed(gP), median_abs_gt_minus_prior_cm=100 * nmed(np.abs(gP)),
              prior_within_tau_of_gt=share(np.abs(gP[okG]) <= tau[okG]), median_dG_cm=100 * nmed(dG))
    if injected:
        s_.update(within_tau_of_raised=share(np.abs(dP[rend]) <= tau[rend]),
                  within_tau_of_nominal=share(np.abs(dP[rend] - 1.0) <= tau[rend]),
                  median_dP_minus_1m_cm=100 * nmed(dP - 1.0))
    return s_


INJ = {"M_B": lambda tab: {3396}, "L_B": lambda tab: {e for e, r in tab.items() if r.get("raised_share", 0) >= 0.5 and r.get("is_building_face")}}


def four_cases(R, keep_pixels=None):
    """r9's four cases of one training. keep_pixels: a view name whose case-3 pixel positions are returned."""
    setting = R["setting"]
    lz = np.load(R["root"] / "runs" / R["run"] / "model/monitor/locations.npz")
    state, vote, J, Jl, lkind, lsurf = lz["state"], lz["vote"], lz["judgment"], lz["unit_judgment"], lz["kind"], lz["surface_ext"]
    table = {r["ext"]: r for r in json.loads((R["prod"] / "stage1/products" / setting / f"surfaces_{R['var']}.json").read_text())["surfaces"]}
    inj_set = INJ[setting](table) if setting in INJ else set()
    inj_unit = np.isin(lsurf, list(inj_set)) & (lkind == 1)
    groups, pix = {}, {}
    for stem in TRAIN:
        v = view_arrays(R, stem)
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
        pix[stem] = {k: int(base[k].sum()) for k in ("c3_agree", "c3_conflict", "c3_undetermined", "x_support_c0_agree")}
        if keep_pixels is not None and stem == keep_pixels:
            rend = v["D"] > 0
            pix["_maps"] = dict(view=stem, **{f"{k}_rc": np.argwhere(base[k]).astype(np.int16) for k in ("c3_agree", "c3_conflict", "c3_undetermined", "x_support_c0_agree")},
                                dP=np.where(rend & prior, (v["D"] - v["P"]) * v["f"], np.nan).astype(np.float32),
                                dG=np.where(rend & (v["G"] > 0), (v["D"] - v["G"]) * v["f"], np.nan).astype(np.float32),
                                gP=np.where(prior & (v["G"] > 0), (v["G"] - v["P"]) * v["f"], np.nan).astype(np.float32),
                                tau=v["tau"].astype(np.float32))
    res = {k: summarise(c, injected=k.endswith("|injected")) for k, c in groups.items()}
    return res, pix


def case4(R):
    root, run = R["root"], R["run"]
    dz = np.load(root / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
    ip = np.load(root / "runs" / run / "model/monitor/init_points.npz")
    cat_init = ip["category"][ip["planted"]]
    c = dz["init_category"]; alive_inv = c == 3
    op = dz["opacity"]; u = dz["u"]; d3 = dz["drift_3d"]
    removed = dz["init_removed_at"]; cat0 = dz["init_category_of_initial"]
    out = dict(n_initial=int((cat_init == 3).sum()), n_end=int(alive_inv.sum()), n_end_opacity_ge_05=int((alive_inv & (op >= 0.5)).sum()),
               share_end_opacity_ge_05=float((op[alive_inv] >= 0.5).mean()) if alive_inv.any() else float("nan"),
               u_median_mm=1000 * nmed(u[alive_inv]), u_p99_mm=1000 * pct(u[alive_inv], 99),
               drift3d_median_mm=1000 * nmed(d3[alive_inv]), protected_end=int((alive_inv & dz["locked"]).sum()),
               no_seeing_view_last_read=int((alive_inv & (dz["E_cnt"] == 0)).sum()),
               n_initial_ids_removed=int(((cat0 == 3) & (removed >= 0)).sum()), protected_total=int(dz["locked"].sum()))
    return out


def e_rows(R):
    return [json.loads(l) for l in (R["root"] / "runs" / R["run"] / "model/monitor/E.jsonl").read_text().splitlines() if l.strip()]


# ================================================================== cases
if "cases" in PARTS:
    res = {}
    for run in R10RUNS:
        R = reg(f"r10:{run}")
        res[run], _ = four_cases(R)
        res[run]["case4"] = case4(R)
        print(run, "cases", json.dumps({k: res[run][k] for k in ("c1", "c3_agree")}, default=float)[:400], flush=True)
    jdump("cases", res)

# ================================================================== ga: the reset probes
if "ga" in PARTS:
    ga = {}
    for run in ("M_N", "L_N_vertex"):
        pj = P10 / "runs" / f"probe_{run}" / "model/monitor/reset_probe.json"
        if not pj.exists():
            continue
        pr = json.loads(pj.read_text())
        inrun = [r for r in e_rows(reg(f"r10:{run}")) if r["iteration"] in (2500, 3000, 3500)]
        ga[run] = dict(probe=pr, in_run={r["iteration"]: dict(n_locked=r["n_locked"], newly=r["n_newly_locked"], released=r["n_released"],
                                                               released_by=r["released_by"], no_view=r["n_prior_no_seeing_view"]) for r in inrun})
        print(run, "ga", json.dumps({k: v for k, v in pr["3000"].items() if k not in ("per_view", "pre", "post")})[:600], flush=True)
    jdump("ga", ga)

# ================================================================== na: party walls
if "na" in PARTS:
    import open3d as o3d
    na = {}
    for setting in ("M_N", "M_B"):
        st9 = locs.load_store(P9 / "stage1/products" / setting / "store_poly_c0.25.npz")
        st10 = locs.load_store(P10 / "stage1/products" / setting / "store_poly_c0.25.npz")
        cells = np.load(P10 / "premeasure_v5" / f"cells_{setting}.npz")
        cut9 = np.nonzero(cells["r9_to_r10"] < 0)[0]                       # r9 patches that the cut removed
        cut_c = st9["loc_center"][cut9]
        tree = cKDTree(cut_c)
        m10 = np.load(P10 / "stage1/meshes" / f"{setting}.npz")
        sc10 = o3d.t.geometry.RaycastingScene(); sc10.add_triangles(o3d.core.Tensor(m10["V"].astype(np.float32)), o3d.core.Tensor(m10["F"].astype(np.uint32)))
        out = dict(r9_patches_cut=int(len(cut9)), by_state={rule.ST_NAMES[k]: int((st9["state_data"][cut9] == k).sum()) for k in rule.ST_NAMES})
        runs = {"M_N": [("r10", "M_N"), ("r10", "M_N_rep"), ("r10", "M_N_nodepth"), ("r9", "M_N"), ("r9", "M_N_noprior")],
                "M_B": [("r10", "M_B"), ("r9", "M_B")]}[setting]
        for pay, run in runs:
            R = reg(f"{pay}:{run}")
            dz = np.load(R["root"] / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
            X = dz["xyz"].astype(np.float64)
            dcut, _ = tree.query(X, k=1, distance_upper_bound=0.25)
            near_cut = np.isfinite(dcut)
            d10 = np.full(len(X), np.inf)
            if near_cut.any():
                d10[near_cut] = sc10.compute_distance(o3d.core.Tensor(X[near_cut].astype(np.float32))).numpy()
            on_cut = near_cut & (d10 > 0.1)                                  # near a removed patch, off the r10 prior surface
            pr = dz["origin"] == 1
            # by the initial disk: Gaussians whose initial position lies on a cut part (near a removed patch, off the r10 mesh)
            X0 = dz["init_position"].astype(np.float64); ok0 = np.isfinite(X0).all(1)
            d0c = np.full(len(X0), np.inf); d0c[ok0] = tree.query(X0[ok0], k=1, distance_upper_bound=0.25)[0]
            n0c = np.isfinite(d0c)
            d0m = np.full(len(X0), np.inf)
            if n0c.any():
                d0m[n0c] = sc10.compute_distance(o3d.core.Tensor(X0[n0c].astype(np.float32))).numpy()
            from_cut = pr & n0c & (d0m > 0.01)
            disp = np.linalg.norm(dz["displacement"], axis=1)
            cat_on = {str(int(k)): int(v) for k, v in zip(*np.unique(dz["init_category"][on_cut & pr], return_counts=True))}
            ip = np.load(R["root"] / "runs" / run / "model/monitor/init_points.npz")
            rows = e_rows(R)
            out[f"{pay}_{run}"] = dict(prior_on_cut=int((on_cut & pr).sum()), prior_on_cut_opaque=int((on_cut & pr & (dz["opacity"] >= 0.5)).sum()),
                                       prior_on_cut_protected=int((on_cut & pr & dz["locked"]).sum()), image_on_cut=int((on_cut & ~pr).sum()),
                                       image_on_cut_opaque=int((on_cut & ~pr & (dz["opacity"] >= 0.5)).sum()),
                                       planted_prior=int((ip["planted"] & (ip["origin"] == 1)).sum()),
                                       from_cut=int(from_cut.sum()), from_cut_opaque=int((from_cut & (dz["opacity"] >= 0.5)).sum()),
                                       from_cut_protected=int((from_cut & dz["locked"]).sum()),
                                       prior_on_cut_by_initial_category=cat_on,
                                       prior_on_cut_displacement_p50_m=float(np.median(disp[on_cut & pr])) if (on_cut & pr).any() else None,
                                       protected_start=rows[0]["n_locked"], protected_end=rows[-1]["n_locked"])
        na[setting] = out
        print(setting, "na", json.dumps(out)[:900], flush=True)
    # the opacity reset at 3,000 on the target building's pixels (r9 table ra-3)
    faces_j = json.loads((MAPS / "faces.json").read_text())
    tfaces = np.array(faces_j["roof"] + faces_j["wall"], np.int64)
    DUMPS = (3000, 3001, 3050)
    depth = {}
    for tag, run_dir in (("r10_M_N", P10 / "runs/M_N/model/dump"), ("r9_M_N", P9 / "runs/M_N/model/dump"),
                         ("ctrl_r8", P9 / "runs/ctrl_M_N_r8/model/dump"), ("r10_L_N_vertex", P10 / "runs/L_N_vertex/model/dump")):
        if not (run_dir / "iteration_3001").exists():
            continue
        per_view, pool = {}, {k: [] for k in ("d3001", "d3050", "a3000", "a3001", "a3050")}
        for stem in TRAIN:
            fid = rs(np.load(MAPS / f"faceid/{stem}.npy")).astype(np.int64)
            tp = np.isin(fid, tfaces)
            Dd = {it: np.load(run_dir / f"iteration_{it}" / f"{stem}_depth.npy").astype(np.float64) for it in DUMPS}
            AA = {it: np.load(run_dir / f"iteration_{it}" / f"{stem}_alpha.npy").astype(np.float32) for it in DUMPS}
            ok = tp & (Dd[3000] > 0)
            r_ = {}
            for it in (3001, 3050):
                okk = ok & (Dd[it] > 0)
                dd = np.abs(Dd[it] - Dd[3000])[okk]
                pool[f"d{it}"].append(dd)
                r_[f"d{it}"] = dict(p50=pct(dd, 50), p95=pct(dd, 95), share_gt_1m=share(dd > 1.0), share_gt_10m=share(dd > 10.0), n=int(okk.sum()))
            for it in DUMPS:
                pool[f"a{it}"].append(AA[it][tp])
                r_[f"alpha{it}"] = dict(p50=nmed(AA[it][tp]), share_lt_05=share(AA[it][tp] < 0.5))
            per_view[stem] = r_
        tot = {}
        for it in (3001, 3050):
            dd = np.concatenate(pool[f"d{it}"])
            tot[f"d{it}"] = dict(p50=pct(dd, 50), p95=pct(dd, 95), share_gt_1m=share(dd > 1.0), share_gt_10m=share(dd > 10.0), n=int(len(dd)))
        for it in DUMPS:
            aa = np.concatenate(pool[f"a{it}"])
            tot[f"alpha{it}"] = dict(p50=nmed(aa), share_lt_05=share(aa < 0.5))
        depth[tag] = dict(total=tot, per_view=per_view)
    depth["representative_view"] = "DJI_20241217101359_0032_D"
    na["opacity_reset"] = depth
    jdump("na", na)

# ================================================================== da: the two mesh layers
if "da" in PARTS:
    import open3d as o3d

    def prior_mesh(R):
        if R["setting"].startswith("M"):
            m = np.load(R["prod"] / "stage1/meshes" / f"{R['setting']}.npz")
        else:
            m = np.load(R7 / "stage1/meshes" / f"{R['setting']}.npz")
        return m["V"], m["F"]

    def mesh_to_prior(R, mdir, names):
        dz = np.load(R["root"] / "runs" / R["run"] / f"model/dump/iteration_{ITS}/gaussians.npz")
        iv = np.load(mdir / "invisible.npz")
        aimed0 = dz["init_position"][iv["region"]]; aimed0 = aimed0[np.isfinite(aimed0).all(1)]
        V, F = prior_mesh(R)
        sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(F.astype(np.uint32)))
        ntri = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]); ntri /= np.maximum(np.linalg.norm(ntri, axis=1, keepdims=True), 1e-12)
        tree = cKDTree(aimed0) if len(aimed0) else None
        out = dict(n_aimed=int(len(aimed0)))
        for name in names:
            f = mdir / f"{name}.ply"
            if not f.exists() or tree is None:
                continue
            mm = o3d.io.read_triangle_mesh(str(f)); Vm = np.asarray(mm.vertices)
            if len(Vm) == 0:
                out[name] = dict(n_vertices_near=0); continue
            d0, _ = tree.query(Vm, k=1, distance_upper_bound=0.5)
            near = np.isfinite(d0)
            if not near.any():
                out[name] = dict(n_vertices_near=0); continue
            mm.compute_vertex_normals(); Nm = np.asarray(mm.vertex_normals)[near]
            ans = sc.compute_closest_points(o3d.core.Tensor(Vm[near].astype(np.float32)))
            dd = np.linalg.norm(ans["points"].numpy().astype(np.float64) - Vm[near], axis=1)
            al = np.abs((Nm * ntri[ans["primitive_ids"].numpy()]).sum(1)) >= 0.9      # vertex normal parallel to the prior face (within ~25 deg)
            out[name] = dict(n_vertices_near=int(near.sum()), p50_m=pct(dd, 50), p95_m=pct(dd, 95), within_0_1m=share(dd <= 0.1),
                             aligned_share=share(al), aligned_p50_m=pct(dd[al], 50), not_aligned_p50_m=pct(dd[~al], 50))
        return out

    def per_face(R, mdir, layers):
        iv = np.load(mdir / "invisible.npz"); regm = iv["region"]
        dz = np.load(R["root"] / "runs" / R["run"] / f"model/dump/iteration_{ITS}/gaussians.npz")
        ids = dz["init_id"].astype(np.int64)
        e = np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1)[regm]
        out = {}
        for name in layers:
            f = mdir / f"dist_region_{name}.npy"
            if not f.exists():
                continue
            d = np.load(f)
            out["all"] = out.get("all", {}); out["all"][name] = dict(n=int(len(d)), within_025=share(d <= 0.25))
            for face in np.unique(e):
                m = e == face
                out.setdefault(str(int(face)), {})[name] = dict(n=int(m.sum()), within_025=float((d[m] <= 0.25).mean()))
        return out

    da = {}
    for tag in [f"r10:{r}" for r in R10RUNS] + ["r9:M_N", "r9:L_N", "r9:M_B", "r9:L_B", "r9:M_N_noprior"]:
        R = reg(tag)
        mdir = (P10 if tag.startswith("r10") else P9) / "mesh" / R["run"]
        if not (mdir / "mesh.json").exists():
            continue
        mj = json.loads((mdir / "mesh.json").read_text())
        layers = ["train", "train_virtual"] + (["mechanism"] if (mdir / "mesh_mechanism.ply").exists() else [])
        names = ["mesh_train", "mesh_train_virtual"] + (["mesh_mechanism"] if "mechanism" in layers else [])
        occ = json.loads((mdir / "occluders.json").read_text()) if (mdir / "occluders.json").exists() else None
        occ2 = json.loads((mdir / "occluders_v2.json").read_text()) if (mdir / "occluders_v2.json").exists() else None
        key = [k for k in mj["groups"] if k.startswith("target outward")][0]
        da[tag] = dict(groups=mj["groups"], aimed_key=key, n_region=mj["n_region"], per_face=per_face(R, mdir, layers),
                       mesh_to_prior=mesh_to_prior(R, mdir, names), occluders_first=occ["totals"] if occ else None,
                       occluders=({k: occ2[k] for k in ("hidden_share", "freed_share_of_hidden", "occluders", "totals", "group_sizes", "cameras_equal_mesh_step")} if occ2 else None),
                       occluders_per_view=occ2["per_view"] if occ2 else None, figure_cameras=mj.get("figure_cameras"), times=mj.get("times"))
        print(tag, "da", json.dumps(da[tag]["per_face"].get("all")), json.dumps(da[tag]["mesh_to_prior"])[:300], flush=True)
    jdump("da", da)

# ================================================================== ra: vertex against cell
if "ra" in PARTS:
    def unsigned_angle(a, b):
        a = np.asarray(a, np.float64); b = np.asarray(b, np.float64)
        return np.degrees(np.arctan2(np.linalg.norm(np.cross(a, b), axis=1), np.abs((a * b).sum(1))))

    def stats_deg(a):
        a = a[np.isfinite(a)]
        return dict(n=int(len(a)), p50=float(np.median(a)) if len(a) else None, p95=float(np.percentile(a, 95)) if len(a) else None)

    CATN = {1: "support", 2: "missing", 3: "invisible", 4: "no_patch"}
    ra = {"angles": {}}
    for tag in ["r10:L_N_vertex", "r10:L_N_cell", "r10:L_N_cell_rep", "r10:L_B_vertex", "r10:L_B_cell", "r9:L_N", "r9:L_B"]:
        R = reg(tag)
        ip = np.load(R["root"] / "runs" / R["run"] / "model/monitor/init_points.npz")
        dz = np.load(R["root"] / "runs" / R["run"] / f"model/dump/iteration_{ITS}/gaussians.npz")
        pl = ip["planted"] & (ip["origin"] == 1)
        a0 = unsigned_angle(ip["normal_after_orientation"][pl], ip["face_normal"][pl]); cat0 = ip["category"][pl]
        pr = (dz["origin"] == 1) & (dz["init_id"] >= 0)
        a1 = unsigned_angle(dz["normal"][pr], dz["init_face_normal"][pr]); c1 = dz["init_category"][pr]
        out = {}
        # the vertex normal of every initial disk (to compare the end directions of the two methods on one reference)
        if "face_normal_file" in ip.files:
            ffile = ip["face_normal_file"][ip["planted"]]
            a1v = unsigned_angle(dz["normal"][pr], ffile[dz["init_id"][pr].astype(np.int64)])
        else:
            a1v = a1
        for k, nm in CATN.items():
            out[nm] = dict(start=stats_deg(a0[cat0 == k]), end=stats_deg(a1[c1 == k]), end_vs_vertex=stats_deg(a1v[c1 == k]))
        out["visible"] = dict(start=stats_deg(a0[np.isin(cat0, [1, 2])]), end=stats_deg(a1[np.isin(c1, [1, 2])]), end_vs_vertex=stats_deg(a1v[np.isin(c1, [1, 2])]))
        ra["angles"][tag] = out
        print(tag, "angles", json.dumps({k: (v["end"]["p50"], v["end_vs_vertex"]["p50"]) for k, v in out.items()}), flush=True)
    # figure data: the view with the most support / agree c_p = 0 pixels (airborne LiDAR nominal)
    cj = json.loads((OUT / "cases.json").read_text()) if (OUT / "cases.json").exists() else {}
    _, pv = four_cases(reg("r10:L_N_vertex"))
    best = max(TRAIN, key=lambda s_: pv[s_]["x_support_c0_agree"])
    maps = {}
    for tag in ("r10:L_N_vertex", "r10:L_N_cell", "r10:L_N_cell_rep"):
        _, px = four_cases(reg(tag), keep_pixels=best)
        maps[tag] = px["_maps"]
    np.savez_compressed(OUT / "ra_maps.npz", view=best, **{f"{t.split(':')[1]}_{k}": v for t, m in maps.items() for k, v in m.items() if k != "view"})
    ra["figure_view"] = best
    ra["figure_view_pixels"] = pv[best]
    jdump("ra", ra)

# ================================================================== ma: case 3 ground-truth columns
if "ma" in PARTS:
    ma = {"definition": CFG["analysis"]["gt"], "runs": {}}
    tags = CFG["analysis"]["ma_runs"]["L_N"] + CFG["analysis"]["ma_runs"]["M_N"]
    for tag in tags:
        R = reg(tag)
        if not (R["root"] / "runs" / R["run"] / f"model/dump/iteration_{ITS}").exists():
            continue
        res_, pv = four_cases(R)
        ma["runs"][tag] = {k: res_[k] for k in ("c3_agree", "c3_conflict", "c3_undetermined", "x_support_c0_agree", "x_support_c0_conflict",
                                               "c3_agree|roof", "c3_conflict|roof", "c3_undetermined|roof", "c3_agree|wall",
                                               "c3_conflict|wall", "c3_undetermined|wall") if k in res_}
        ma["runs"][tag]["pixels_per_view"] = pv
        print(tag, "ma", json.dumps({k: (ma["runs"][tag][k]["n"], round(ma["runs"][tag][k].get("median_abs_dG_cm", float("nan")), 1),
                                         round(ma["runs"][tag][k].get("within_tau_of_gt", float("nan")), 3))
                                     for k in ("c3_agree", "c3_conflict", "c3_undetermined")}), flush=True)
    # figure: the airborne LiDAR view with the most case-3 pixels; positions by judgment and |D - G| of r8, r9, r10
    pv = ma["runs"]["r9:L_N"]["pixels_per_view"]
    best = max(TRAIN, key=lambda s_: pv[s_]["c3_agree"] + pv[s_]["c3_conflict"] + pv[s_]["c3_undetermined"])
    fig = {}
    for tag in ("r8:L_N", "r9:r8rep_L_N", "r9:L_N", "r9:L_N_noorient", "r10:L_N_vertex", "r10:L_N_cell"):
        R = reg(tag)
        if not (R["root"] / "runs" / R["run"] / f"model/dump/iteration_{ITS}").exists():
            continue
        _, px = four_cases(R, keep_pixels=best)
        for k, v in px["_maps"].items():
            if k != "view":
                fig[f"{tag.replace(':', '_')}_{k}"] = v
    np.savez_compressed(OUT / "ma_maps.npz", view=best, **fig)
    ma["figure_view"] = best
    jdump("ma", ma)

# ================================================================== prot: protection per re-read
if "prot" in PARTS:
    prot = {}
    for tag in [f"r10:{r}" for r in R10RUNS] + ["r9:M_N", "r9:M_B", "r9:L_N", "r9:L_B", "r9:M_N_noprior"]:
        R = reg(tag)
        prot[tag] = [dict(iteration=r["iteration"], n_locked=r["n_locked"], newly=r["n_newly_locked"], released=r["n_released"],
                          released_by=r["released_by"], by_category=r["locked_by_initial_category"],
                          on_support_conflict=r["locked_on_support_conflict_unit"], no_view=r["n_prior_no_seeing_view"],
                          differ_3d=r["would_differ_with_3d_distance"], excluded_support_conflict=r.get("excluded_support_conflict"))
                     for r in e_rows(R)]
    jdump("prot", prot)
print("done", PARTS)
