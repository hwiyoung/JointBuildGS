"""PHD-STAGE2-R9-THREE-FIXES-v1 step 13 (jointbuildgs:dev, CPU): the four cases of r8 with the r9 trainings (same
definitions as four_cases.py of r8) and the checks of the three fixes, each beside r8.

  python cases_r9.py      # mounts: /artifacts (ro), /repo (ro), /r7 (ro), /r8 (ro), /p9 (rw)

Four cases (cases.json, keys as r8's cases.json): training views at the training resolution, final dump (3,500); maps
resampled nearest as the fork loads them; differences are height differences (method 3.3). LoD2 runs read the r9 prior
depth and product (bottom faces left out).
Fix 'na' (eq. 7 with the patch judgment): per re-read the protected Gaussians on support patches voted conflict (E.jsonl);
at the end the prior Gaussians on those patches (count, opacity, protected, no seeing view at the last re-read = behind the
surface the views see); the initial disks planted there and removed after the opacity reset at 3,000 (removal history);
sections across the faces of the order (LoD2 3837, 3391, 3386; TIN 3, 4, 7): prior-origin Gaussian centres of r8 and r9
and the training-view TSDF mesh of both, in the face's frame.
Fix 'da' (initial direction): the angle between a prior-origin Gaussian's disk normal and its face normal (unsigned,
atan2(|n x m|, |n . m|)) at the start and at 3,500, by initial region; r8's start = the reproduced base draw
(r8_initial_rotations.py); r8's end = its final PLY rows. Mesh: share of the aimed Gaussians within 0.25 m of the meshes
(mesh.json of r8 and r9) and the distance from the mesh to the prior surface (mesh vertices within 0.5 m of an aimed
Gaussian's initial position).
Fix 'ra' (LoD2 bottom face): Gaussians planted from bottom faces (r8 start / end), protection at the start and the end,
walls shared by two buildings (faces.party_wall_cells: cells, invisible cells, Gaussians at the end), and across the
opacity reset at 3,000 the rendered depth and accumulated opacity on the target building's pixels (r9 M_N vs the control
run of the r8 code with the bottom face); the control's protection counts up to 3,000 against r8's M_N (same code).
Writes /p9/cases/{cases.json, fixes.json, sections_na.npz}.
  R9_EXTRA=1 python cases_r9.py   # the four cases and the mesh shares of the extra runs (r9.json training.extra_runs: r8
                                  # repeated, r9 without fix 'da'); r8 repeats read r8's product and prior; -> cases_extra.json"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from plyfile import PlyData
from scipy.spatial import cKDTree

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v3 import faces as FA  # noqa: E402
from src.phd.prior_propagation_v3 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v3 import orientation as ori  # noqa: E402
from src.phd.prior_propagation_v3 import rule  # noqa: E402

P9 = Path("/p9"); R8 = Path("/r8"); R7 = Path("/r7"); OUT = P9 / "cases"; OUT.mkdir(parents=True, exist_ok=True)
S2 = Path("/artifacts/JointBuildGS/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1")
MAPS = S2 / "inputs/maps"
CFG = json.loads(Path("/repo/configs/phd/stage2_r9_three_fixes_v1/r9.json").read_text())
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
RUNS = ["M_N", "M_B", "L_N", "L_B", "M_N_noprior"]
EXTRA = os.environ.get("R9_EXTRA") == "1"
if EXTRA:
    RUNS = [k for k in CFG["training"]["extra_runs"] if k.startswith(("r8rep", "M_N_", "L_N_"))]


def product_root(run):
    """the payload whose stage-1 product, inputs and prior depth the run read (r8 repeats: r8's)."""
    return R8 if run.startswith("r8rep") else P9
ITS = int(CFG["training"]["iterations"])
H, W = 1157, 1600
CELL = CFG["values"]["cell_m"]


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


def setting_of(root, run):
    return json.loads((root / "runs" / run / "receipt.json").read_text())["setting"]


def var_of(setting):
    return "poly" if setting.startswith("M") else "lod2"


# ================================================================== A. the four cases (r8's four_cases.py, r9 paths)
def view_arrays(run, setting, stem):
    PR = product_root(run)
    dump = P9 / "runs" / run / f"model/dump/iteration_{ITS}"
    D = np.load(dump / f"{stem}_depth.npy").astype(np.float64)
    AL = np.load(dump / f"{stem}_alpha.npy").astype(np.float32)
    A = rs(np.load(MAPS / f"conf/raw_depth/{stem}.npy")) > 0.5
    M = rs(np.load(MAPS / f"mvs/raw_depth/{stem}.npy")).astype(np.float64)
    Pp = (P9 / "stage1/prior" / setting / "raw_depth" / f"{stem}.npy") if (setting.startswith("M") and PR == P9) else (MAPS / f"prior_{setting}/raw_depth/{stem}.npy")
    P = rs(np.load(Pp)).astype(np.float64)
    G = rs(np.load(MAPS / f"gt_clean/raw_depth/{stem}.npy")).astype(np.float64)
    prod = PR / "stage1/products" / setting
    f = rs(np.load(prod / "fconv" / f"{stem}.npy")).astype(np.float64)
    lm = rs(np.load(prod / "locmap" / f"{stem}.npy")).astype(np.int64)
    mk = rs(np.load(prod / "markmap" / f"{stem}.npy")).astype(np.int64)
    taup = rs(np.load(PR / "inputs" / setting / "tau" / f"{stem}.npy")).astype(np.float64)
    return dict(D=D, AL=AL, A=A, M=M, P=P, G=G, f=f, lm=lm, mk=mk, tau=taup * np.maximum(f, 1e-3))


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
    if injected:
        s_.update(within_tau_of_raised=share(np.abs(dP[rend]) <= tau[rend]),
                  within_tau_of_nominal=share(np.abs(dP[rend] - 1.0) <= tau[rend]),
                  median_dP_minus_1m_cm=100 * nmed(dP - 1.0))
    return s_


INJ = {"M_B": lambda tab: {3396}, "L_B": lambda tab: {e for e, r in tab.items() if r.get("raised_share", 0) >= 0.5 and r.get("is_building_face")}}
res = {}
for run in RUNS:
    setting = setting_of(P9, run)
    lz = np.load(P9 / "runs" / run / "model/monitor/locations.npz")
    state, vote, J, Jl, lkind, lsurf = lz["state"], lz["vote"], lz["judgment"], lz["unit_judgment"], lz["kind"], lz["surface_ext"]
    table = {r["ext"]: r for r in json.loads((product_root(run) / "stage1/products" / setting / f"surfaces_{var_of(setting)}.json").read_text())["surfaces"]}
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
    # case 4: Gaussians planted from invisible patches
    dz = np.load(P9 / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
    ip = np.load(P9 / "runs" / run / "model/monitor/init_points.npz")
    cat_init = ip["category"][ip["planted"]]
    c = dz["init_category"]; alive_inv = c == 3
    prior = dz["origin"] == 1
    removed = dz["init_removed_at"]; cat0 = dz["init_category_of_initial"]
    op = dz["opacity"]; u = dz["u"]; d3 = dz["drift_3d"]
    mesh = json.loads((P9 / "mesh" / run / "mesh.json").read_text()) if (P9 / "mesh" / run / "mesh.json").exists() else None
    inv_now = np.load(P9 / "mesh" / run / "invisible.npz") if (P9 / "mesh" / run / "invisible.npz").exists() else None
    c4 = dict(n_initial=int((cat_init == 3).sum()), n_initial_ids_removed=int(((cat0 == 3) & (removed >= 0)).sum()),
              n_end=int(alive_inv.sum()), n_end_opacity_ge_05=int((alive_inv & (op >= 0.5)).sum()),
              share_end_opacity_ge_05=float((op[alive_inv] >= 0.5).mean()) if alive_inv.any() else float("nan"),
              u_median_mm=1000 * nmed(u[alive_inv]), u_p99_mm=1000 * pct(u[alive_inv], 99), u_max_mm=1000 * float(np.nanmax(u[alive_inv])) if alive_inv.any() else float("nan"),
              drift3d_median_mm=1000 * nmed(d3[alive_inv]), drift3d_max_mm=1000 * float(np.nanmax(d3[alive_inv])) if alive_inv.any() else float("nan"),
              drift3d_p99_mm=1000 * pct(d3[alive_inv], 99), n_initial_ids_alive=int(((cat0 == 3) & (removed < 0)).sum()),
              protected_end=int((alive_inv & dz["locked"]).sum()), no_seeing_view_last_read=int((alive_inv & (dz["E_cnt"] == 0)).sum()))
    if inv_now is not None:
        iv = inv_now["invisible"]
        c4.update(n_end_invisible_final_render=int((alive_inv & iv).sum()), all_prior_invisible_final=int((prior & iv).sum()),
                  all_prior_invisible_final_opaque=int((prior & iv & (op >= 0.5)).sum()))
    if mesh is not None:
        c4["mesh"] = mesh["groups"]; c4["mesh_virtual_cameras"] = mesh["n_virtual_cameras"]
    loc_j = dz["unit_judgment"]; located = dz["located"]; lockd = dz["locked"]
    sc = lockd & located & (loc_j == rule.J_CONFLICT)
    ids = dz["init_id"].astype(np.int64)
    ext_row = np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1)
    vals, cnts = np.unique(ext_row[sc], return_counts=True)
    order = np.argsort(-cnts)[:8]
    c4["protected_on_support_conflict"] = dict(n=int(sc.sum()), no_seeing_view=int((sc & (dz["E_cnt"] == 0)).sum()),
                                               opacity_ge_05=int((sc & (op >= 0.5)).sum()),
                                               top_surfaces={str(int(vals[i])): int(cnts[i]) for i in order}, u_median_mm=1000 * nmed(u[sc]))
    c4["protected_total"] = int(lockd.sum())
    c4["protected_by_initial_category"] = {str(k): int((lockd & (c == k)).sum()) for k in range(5)}
    c4["removed_by_category"] = {str(k): int(((cat0 == k) & (removed >= 0)).sum()) for k in range(5)}
    c4["initial_by_category"] = {str(k): int((cat0 == k).sum()) for k in range(5)}
    res[run]["case4"] = c4
    rows = [json.loads(l) for l in (P9 / "runs" / run / "model/monitor/E.jsonl").read_text().splitlines() if l.strip()]
    res[run]["protection"] = [dict(iteration=r["iteration"], n_locked=r["n_locked"], newly=r["n_newly_locked"], released=r["n_released"],
                                   released_by=r["released_by"], by_category=r["locked_by_initial_category"],
                                   on_support_conflict=r["locked_on_support_conflict_unit"], no_view=r["n_prior_no_seeing_view"],
                                   differ_3d=r["would_differ_with_3d_distance"], conflict_excluded=r["n_conflict_excluded"],
                                   excluded_support_conflict=r.get("excluded_support_conflict"), excluded_propagated_conflict=r.get("excluded_propagated_conflict"),
                                   prior_on_support_conflict=r.get("prior_on_support_conflict_unit")) for r in rows]
    print(run, "cases", json.dumps({k: res[run][k] for k in ("c1", "c2", "c3_conflict")}, default=float)[:600], flush=True)
if EXTRA:   # mesh shares of the extra runs that have a mesh, by face, then stop
    for run in RUNS:
        mdir = P9 / "mesh" / run
        if not (mdir / "mesh.json").exists():
            continue
        mj = json.loads((mdir / "mesh.json").read_text())
        key = [k for k in mj["groups"] if k.startswith("target outward")][0]
        iv = np.load(mdir / "invisible.npz"); reg = iv["region"]
        dz = np.load(P9 / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
        ids = dz["init_id"].astype(np.int64)
        e = np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1)[reg]
        pf = {}
        for name in ("train", "train_virtual"):
            d = np.load(mdir / f"dist_region_{name}.npy")
            for face in np.unique(e):
                m = e == face
                pf.setdefault(str(int(face)), {})[name] = dict(n=int(m.sum()), within_025=float((d[m] <= 0.25).mean()))
        res[run]["mesh_aimed"] = dict(groups=mj["groups"], key=key, per_face=pf)
    (OUT / "cases_extra.json").write_text(json.dumps(res, indent=1, default=float))
    print("written", OUT / "cases_extra.json")
    sys.exit(0)
(OUT / "cases.json").write_text(json.dumps(res, indent=1, default=float))

# ================================================================== B. the three fixes
FX = {}
R8C = json.loads((R8 / "cases/cases.json").read_text())
Q8 = np.load(P9 / "cases/r8_initial_quaternions.npy")


def unsigned_angle(a, b):
    a = np.asarray(a, np.float64); b = np.asarray(b, np.float64)
    return np.degrees(np.arctan2(np.linalg.norm(np.cross(a, b), axis=1), np.abs((a * b).sum(1))))


def ply_normals(path):
    v = PlyData.read(str(path))["vertex"]
    q = np.stack([np.asarray(v[f"rot_{k}"], np.float64) for k in range(4)], 1)
    return ori.normal_of_quat(q)


def face_normals_r8(run):
    """face normal per initial disk of an r8 training (initial disk -> its cloud row)."""
    setting = setting_of(R8, run)
    ip = np.load(R8 / "runs" / run / "model/monitor/init_points.npz")
    rows = np.nonzero(ip["planted"])[0]
    nf = np.load(P9 / "inputs" / setting / ("prior_normal_r8cloud.npy" if setting.startswith("M") else "prior_normal.npy"))
    return nf[rows], rows, ip


def stats_deg(a):
    a = a[np.isfinite(a)]
    return dict(n=int(len(a)), p50=float(np.median(a)) if len(a) else None, p95=float(np.percentile(a, 95)) if len(a) else None)


CATN = {1: "support", 2: "missing", 3: "invisible", 4: "no_patch"}
# ---------------------------------------------------------------- fix 'da': angles
da = {}
for run in RUNS:
    out = {}
    # r9 start (the run's own init points) and end (dump)
    ip9 = np.load(P9 / "runs" / run / "model/monitor/init_points.npz")
    pl = ip9["planted"] & (ip9["origin"] == 1)
    a0 = unsigned_angle(ip9["normal_after_orientation"][pl], ip9["face_normal"][pl])
    sgn0 = (ip9["normal_after_orientation"][pl].astype(np.float64) * ip9["face_normal"][pl]).sum(1)
    cat9 = ip9["category"][pl]
    dz9 = np.load(P9 / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
    pr9 = (dz9["origin"] == 1) & (dz9["init_id"] >= 0)
    a1 = unsigned_angle(dz9["normal"][pr9], dz9["init_face_normal"][pr9]); c1 = dz9["init_category"][pr9]
    # r8 start (reproduced draw) and end (final PLY)
    nf8, rows8, ip8 = face_normals_r8(run)
    pl8 = (ip8["origin"][rows8] == 1)
    n8_0 = ori.normal_of_quat(Q8[rows8].astype(np.float64))
    b0 = unsigned_angle(n8_0[pl8], nf8[pl8]); cat8 = ip8["category"][rows8][pl8]
    dz8 = np.load(R8 / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
    n8_1 = ply_normals(R8 / "runs" / run / f"model/point_cloud/iteration_{ITS}/point_cloud.ply")
    pr8 = (dz8["origin"] == 1) & (dz8["init_id"] >= 0)
    b1 = unsigned_angle(n8_1[pr8], nf8[dz8["init_id"][pr8].astype(np.int64)]); d1 = dz8["init_category"][pr8]
    for k, nm in CATN.items():
        out[nm] = dict(r9_start=stats_deg(a0[cat9 == k]), r9_end=stats_deg(a1[c1 == k]), r8_start=stats_deg(b0[cat8 == k]), r8_end=stats_deg(b1[d1 == k]))
    out["visible"] = dict(r9_start=stats_deg(a0[np.isin(cat9, [1, 2])]), r9_end=stats_deg(a1[np.isin(c1, [1, 2])]),
                          r8_start=stats_deg(b0[np.isin(cat8, [1, 2])]), r8_end=stats_deg(b1[np.isin(d1, [1, 2])]))
    out["r9_start_sign"] = dict(min_signed_cos=float(sgn0.min()), negative=int((sgn0 < 0).sum()), n=int(len(sgn0)))
    da[run] = out
    print(run, "da", json.dumps({k: (v["r9_end"]["p50"], v["r8_end"]["p50"]) for k, v in out.items() if isinstance(v, dict) and "r9_end" in v}), flush=True)
FX["da_angles"] = da
FX["r8_initial_rotations"] = json.loads((P9 / "cases/r8_initial_quaternions.json").read_text())


# ---------------------------------------------------------------- fix 'da': meshes
def prior_mesh(setting):
    if setting.startswith("M"):
        m = np.load(P9 / "stage1/meshes" / f"{setting}.npz")
    else:
        m = np.load(R7 / "stage1/meshes" / f"{setting}.npz")
    return m["V"], m["F"]


def mesh_to_prior(root, run):
    import open3d as o3d
    setting = setting_of(root, run)
    iv = np.load(root / "mesh" / run / "invisible.npz")
    dz = np.load(root / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
    aimed0 = dz["init_position"][iv["region"]]
    aimed0 = aimed0[np.isfinite(aimed0).all(1)]
    V, F = prior_mesh(setting)
    sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(F.astype(np.uint32)))
    tree = cKDTree(aimed0) if len(aimed0) else None
    out = dict(n_aimed=int(len(aimed0)))
    for name in ("mesh_train", "mesh_train_virtual"):
        mm = o3d.io.read_triangle_mesh(str(root / "mesh" / run / f"{name}.ply"))
        Vm = np.asarray(mm.vertices)
        if tree is None or len(Vm) == 0:
            out[name] = dict(n=0); continue
        d0, _ = tree.query(Vm, k=1, distance_upper_bound=0.5)
        near = np.isfinite(d0)
        dd = sc.compute_distance(o3d.core.Tensor(Vm[near].astype(np.float32))).numpy()
        out[name] = dict(n_vertices_near=int(near.sum()), p50_m=pct(dd, 50), p95_m=pct(dd, 95), within_0_1m=share(dd <= 0.1) if len(dd) else None)
    return out


def per_face(root, run, sub=None):
    """share of the aimed Gaussians within 0.25 m of the meshes, by the face their initial disk sat on."""
    mdir = root / "mesh" / (sub or run)
    iv = np.load(mdir / "invisible.npz"); reg = iv["region"]
    dz = np.load(root / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
    ids = dz["init_id"].astype(np.int64)
    e = np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1)[reg]
    out = {}
    for name in ("train", "train_virtual"):
        f = mdir / f"dist_region_{name}.npy"
        if not f.exists():
            continue
        d = np.load(f)
        for face in np.unique(e):
            m = e == face
            out.setdefault(str(int(face)), {})[name] = dict(n=int(m.sum()), within_025=float((d[m] <= 0.25).mean()))
    return out


dm = {}
for run in RUNS:
    m9 = json.loads((P9 / "mesh" / run / "mesh.json").read_text()); m8 = json.loads((R8 / "mesh" / run / "mesh.json").read_text())
    key = [k for k in m9["groups"] if k.startswith("target outward")][0]
    dm[run] = dict(r9=m9["groups"], r8=m8["groups"], aimed_key=key, r9_cameras=m9.get("r8_cameras"),
                   mesh_to_prior=dict(r9=mesh_to_prior(P9, run), r8=mesh_to_prior(R8, run)),
                   per_face=dict(r9=per_face(P9, run), r8=per_face(R8, run)))
    vdir = P9 / "mesh" / f"{run}_r8cams"
    if (vdir / "mesh.json").exists():   # the r9 scene meshed with r8's virtual cameras
        mv = json.loads((vdir / "mesh.json").read_text())
        dm[run]["r9_with_r8_cameras"] = dict(groups=mv["groups"], per_face=per_face(P9, run, f"{run}_r8cams"),
                                            n_virtual_cameras=mv["n_virtual_cameras"],
                                            camera_centres_equal_r8=bool(np.allclose(np.array(mv["virtual_camera_centres"]), np.array(m8["virtual_camera_centres"]))))
    print(run, "mesh", m9["groups"][key]["train"]["within_0.25m"], m9["groups"][key]["train_virtual"]["within_0.25m"],
          dm[run]["mesh_to_prior"]["r9"].get("mesh_train_virtual"), flush=True)
FX["da_mesh"] = dm


# ---------------------------------------------------------------- fix 'na': support patches voted conflict
def na_stats(root, run):
    dz = np.load(root / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
    lz = np.load(root / "runs" / run / "model/monitor/locations.npz")
    ip = np.load(root / "runs" / run / "model/monitor/init_points.npz")
    state, vote = lz["state"], lz["vote"]
    loc = dz["location"].astype(np.int64); located = dz["located"]; lc = np.maximum(loc, 0)
    prior = dz["origin"] == 1
    sc = prior & located & (state[lc] == rule.ST_SUPPORT) & (vote[lc] == rule.V_CONFLICT)
    op = dz["opacity"]; lk = dz["locked"]; behind = dz["E_cnt"] == 0
    planted = ip["planted"]
    st0 = ip["state"][planted]; jl0 = ip["unit_judgment"][planted]; pr0 = ip["origin"][planted] == 1
    init_sc = pr0 & (st0 == rule.ST_SUPPORT) & (jl0 == rule.J_CONFLICT)
    rem = dz["init_removed_at"]
    ids = dz["init_id"].astype(np.int64)
    ext_row = np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1)
    by_face = {}
    for e in CFG["analysis"]["na_faces"]["M" if setting_of(root, run).startswith("M") else "L"]:
        f_ = sc & (ext_row == e)
        by_face[str(e)] = dict(n=int(f_.sum()), opaque=int((f_ & (op >= 0.5)).sum()), protected=int((f_ & lk).sum()),
                               opaque_behind=int((f_ & (op >= 0.5) & behind).sum()))
    return dict(end_on_support_conflict=int(sc.sum()), end_opacity_p50=nmed(op[sc]), end_share_opacity_ge_05=share(op[sc] >= 0.5),
                end_protected=int((sc & lk).sum()), end_opaque_behind=int((sc & (op >= 0.5) & behind).sum()),
                end_behind=int((sc & behind).sum()),
                initial_disks_on_support_conflict=int(init_sc.sum()), removed_by_3000=int((init_sc & (rem >= 0) & (rem <= 3000)).sum()),
                removed_after_3000=int((init_sc & (rem > 3000)).sum()), removed_any=int((init_sc & (rem >= 0)).sum()), by_face=by_face)


na = {}
for run in RUNS:
    r9rows = [json.loads(l) for l in (P9 / "runs" / run / "model/monitor/E.jsonl").read_text().splitlines() if l.strip()]
    r8rows = [json.loads(l) for l in (R8 / "runs" / run / "model/monitor/E.jsonl").read_text().splitlines() if l.strip()]
    na[run] = dict(r9=na_stats(P9, run), r8=na_stats(R8, run),
                   per_read=[dict(iteration=a["iteration"], r9_locked_on_support_conflict=a["locked_on_support_conflict_unit"],
                                  r8_locked_on_support_conflict=b["locked_on_support_conflict_unit"],
                                  r9_excluded_support_conflict=a.get("excluded_support_conflict"),
                                  r9_released_support_conflict=a["released_by"].get("support_conflict"),
                                  r9_prior_on_support_conflict=a.get("prior_on_support_conflict_unit"),
                                  r9_locked=a["n_locked"], r8_locked=b["n_locked"]) for a, b in zip(r9rows, r8rows)])
    print(run, "na", json.dumps(na[run]["r9"])[:300], flush=True)
FX["na"] = na


# sections across the faces of the order (figure data)
def tin_height(V, F, xy, z0=200.0):
    import open3d as o3d
    sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(F.astype(np.uint32)))
    rays = np.zeros((len(xy), 6), np.float32); rays[:, :2] = xy; rays[:, 2] = z0; rays[:, 5] = -1.0
    t = sc.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy()
    return np.where(np.isfinite(t), z0 - t, np.nan)


def mesh_cut(Vm, Fm, frame, cut_axis, c0, w):
    """segments of the mesh triangles cut by the plane (X - o).cut_axis = c0, in (x, y) of the section frame."""
    o, ex, ey, ez = frame
    T = Vm[Fm]
    d = (T - o) @ cut_axis - c0
    keep = ~((d > 0).all(1) | (d < 0).all(1))
    segs = []
    for tri, dd in zip(T[keep], d[keep]):
        pts = []
        for a_, b_ in ((0, 1), (1, 2), (2, 0)):
            if (dd[a_] > 0) != (dd[b_] > 0) and dd[a_] != dd[b_]:
                t_ = dd[a_] / (dd[a_] - dd[b_]); pts.append(tri[a_] + t_ * (tri[b_] - tri[a_]))
        if len(pts) == 2:
            segs.append(np.array(pts))
    return np.array(segs) if segs else np.zeros((0, 2, 3))


sections = {}
for setting, run in (("M_N", "M_N"), ("L_N", "L_N")):
    st = locs.load_store(P9 / "stage1/products" / setting / f"store_{var_of(setting)}_c{CELL}.npz")
    state, vote = st["state_data"], st["vote_data"]
    table = {r["ext"]: r for r in json.loads((P9 / "stage1/products" / setting / f"surfaces_{var_of(setting)}.json").read_text())["surfaces"]}
    Vp, Fp = prior_mesh(setting)
    import open3d as o3d
    meshes = {tag: o3d.io.read_triangle_mesh(str(root / "mesh" / run / "mesh_train.ply")) for tag, root in (("r9", P9), ("r8", R8))}
    dumps = {tag: np.load(root / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz") for tag, root in (("r9", P9), ("r8", R8))}
    for e in CFG["analysis"]["na_faces"]["M" if setting.startswith("M") else "L"]:
        s_idx = int(np.nonzero(st["surf_ext"] == e)[0][0])
        m = st["loc_surface"] == s_idx
        scm = m & (state == rule.ST_SUPPORT) & (vote == rule.V_CONFLICT)
        cen = st["loc_center"][scm] if scm.any() else st["loc_center"][m]
        c = np.median(cen, 0)
        if setting.startswith("M"):
            n = np.array(table[e]["normal_outward"], float)
        else:   # TIN surface: least-squares plane of its patch centres, normal up
            P_ = st["loc_center"][m]; Pc = P_ - P_.mean(0)
            n = np.linalg.svd(Pc, full_matrices=False)[2][-1]; n = n if n[2] >= 0 else -n
        e1, e2 = ori.tangent_frame(n[None])
        e1, e2 = e1[0], e2[0]
        wall = abs(n[2]) < 0.5
        cut_axis = e2 if wall else e1            # walls: horizontal cut (slab in height); roofs / TIN: cut along the slope
        xaxis = e1 if wall else e2
        frame = (c, xaxis, None, n)
        x_m = (st["loc_center"][m] - c) @ xaxis
        xr = (float(x_m.min()) - 1.0, float(x_m.max()) + 1.0)
        rec = dict(face=e, wall=bool(wall), normal=n.tolist(), centre=c.tolist(), x_range=xr, n_support_conflict_patches=int(scm.sum()),
                   n_patches=int(m.sum()))

        def yoff(X):
            if setting.startswith("M") and wall:
                return (X - c) @ n
            if setting.startswith("M"):
                return X[:, 2] - (c[2] - (n[0] * (X[:, 0] - c[0]) + n[1] * (X[:, 1] - c[1])) / n[2])
            return X[:, 2] - tin_height(Vp, Fp, X[:, :2])
        for tag in ("r9", "r8"):
            dz = dumps[tag]
            X = dz["xyz"].astype(np.float64)
            pr = dz["origin"] == 1
            sl = pr & (np.abs((X - c) @ cut_axis) <= 0.25)
            xx = (X - c) @ xaxis
            sl &= (xx >= xr[0]) & (xx <= xr[1])
            ids = dz["init_id"].astype(np.int64)
            ext_row = np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1)
            lz = np.load((P9 if tag == "r9" else R8) / "runs" / run / "model/monitor/locations.npz")
            loc = dz["location"].astype(np.int64); located = dz["located"]
            on_sc = located & (lz["state"][np.maximum(loc, 0)] == rule.ST_SUPPORT) & (lz["vote"][np.maximum(loc, 0)] == rule.V_CONFLICT)
            yy = np.full(len(X), np.nan); yy[sl] = yoff(X[sl])
            sl &= np.abs(yy) <= 1.5
            rec[tag] = dict(x=xx[sl].astype(np.float32), y=yy[sl].astype(np.float32), opacity=dz["opacity"][sl].astype(np.float32),
                            on_face=(ext_row[sl] == e), support_conflict=on_sc[sl], locked=dz["locked"][sl], behind=(dz["E_cnt"][sl] == 0))
            segs = mesh_cut(np.asarray(meshes[tag].vertices), np.asarray(meshes[tag].triangles), frame, cut_axis, 0.0, 0.25)
            if len(segs):
                sx = (segs - c) @ xaxis
                sy = np.stack([yoff(segs[:, 0]), yoff(segs[:, 1])], 1)
                k_ = (sx.min(1) >= xr[0] - 0.5) & (sx.max(1) <= xr[1] + 0.5) & (np.abs(sy).max(1) <= 1.5)
                rec[tag]["mesh"] = np.stack([sx[k_], sy[k_]], -1).astype(np.float32)
            else:
                rec[tag]["mesh"] = np.zeros((0, 2, 2), np.float32)
        sections[f"{setting}_{e}"] = rec
        print("section", setting, e, {t: int(rec[t]["on_face"].sum()) for t in ("r9", "r8")}, flush=True)
np.save(OUT / "sections_na.npy", sections, allow_pickle=True)


# ---------------------------------------------------------------- fix 'ra': bottom faces, protection, shared walls
def bottom_ext(root, setting):
    t = json.loads((root / "stage1/products" / setting / f"surfaces_{var_of(setting)}.json").read_text())["surfaces"]
    return np.array([r["ext"] for r in t if r.get("type") == "ground"], np.int64), {r["ext"]: r for r in t}


ra = {}
for run in ("M_N", "M_B", "M_N_noprior"):
    setting = setting_of(P9, run)
    bext, t8 = bottom_ext(R8, setting)
    target_bottom = [e for e in bext if t8[e].get("target")]
    out = {}
    for tag, root in (("r9", P9), ("r8", R8)):
        ip = np.load(root / "runs" / run / "model/monitor/init_points.npz")
        dz = np.load(root / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
        pl = ip["planted"] & (ip["origin"] == 1)
        onb = pl & np.isin(ip["surface"], bext); ont = pl & np.isin(ip["surface"], target_bottom)
        ids = dz["init_id"].astype(np.int64)
        ext_row = np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1)
        eb = np.isin(ext_row, bext) & (dz["origin"] == 1); et = np.isin(ext_row, target_bottom) & (dz["origin"] == 1)
        rows = [json.loads(l) for l in (root / "runs" / run / "model/monitor/E.jsonl").read_text().splitlines() if l.strip()]
        out[tag] = dict(planted_on_bottom=int(onb.sum()), planted_on_target_bottom=int(ont.sum()),
                        end_on_bottom=int(eb.sum()), end_on_target_bottom=int(et.sum()), end_on_bottom_opaque=int((eb & (dz["opacity"] >= 0.5)).sum()),
                        end_on_bottom_protected=int((eb & dz["locked"]).sum()),
                        protected_start=rows[0]["n_locked"], protected_end=rows[-1]["n_locked"],
                        protected_start_on_bottom=int((onb & (ip["E_first"] < 0.5) & (ip["unit_judgment"] != rule.J_CONFLICT)).sum()),
                        protected_end_on_bottom=int((eb & dz["locked"]).sum()))
    ra[run] = out
# shared walls (M_N; r9 product, Gaussians of r9 and r8)
st9 = locs.load_store(P9 / "stage1/products/M_N/store_poly_c0.25.npz")
tab9 = {r["ext"]: r for r in json.loads((P9 / "stage1/products/M_N/surfaces_poly.json").read_text())["surfaces"]}
mz = np.load(P9 / "stage1/meshes/M_N.npz")
fz = np.load(P9 / "stage1/meshes/faces_M_N.npz")
nout = {int(p): fz["normal_outward"][i] for i, p in enumerate(fz["ids"])}
wall_t = np.isin(mz["tri_type"], ["WallSurface"])
cells = np.nonzero(st9["loc_kind"] == 2)[0]
c_ext = st9["surf_ext"][st9["loc_surface"][cells]]
c_bld = np.array([tab9[int(e)]["building"] for e in c_ext])
c_n = np.stack([nout[int(e)] for e in c_ext])
shared, dist, partner = FA.party_wall_cells(st9["loc_center"][cells], c_bld, c_n, mz["V"], mz["F"][wall_t], mz["tri_building"][wall_t],
                                            np.stack([nout[int(p)] for p in mz["tri_poly"][wall_t]]))
pc_ = cells[shared]
lz9 = np.load(P9 / "runs/M_N/model/monitor/locations.npz")
party = dict(rule=CFG["surfaces"]["party_wall_rule"], n_wall_cells=int(len(cells)), n_shared_cells=int(len(pc_)),
             shared_area_m2=float(st9["loc_area"][pc_].sum()), polygons=sorted({int(e) for e in c_ext[shared]}),
             pairs=sorted({(int(a_), int(mz["tri_poly"][wall_t][p_])) for a_, p_ in zip(c_ext[shared], partner[shared])}),
             by_state={rule.ST_NAMES[k]: int((lz9["state"][pc_] == k).sum()) for k in rule.ST_NAMES},
             target_building_polygons=sorted({int(e) for e in c_ext[shared] if tab9[int(e)].get("target")}))
for tag, root in (("r9", P9), ("r8", R8)):
    for run in ("M_N", "M_N_noprior"):
        dz = np.load(root / "runs" / run / f"model/dump/iteration_{ITS}/gaussians.npz")
        if tag == "r9":
            on = dz["located"] & np.isin(dz["location"], pc_)
        else:   # r8 locations of the same cells (same surface, same centre)
            st8 = locs.load_store(R8 / "stage1/products/M_N/store_poly_c0.25.npz")
            key8 = {(int(st8["surf_ext"][s]), tuple(np.round(cc, 3))): i for i, (s, cc) in enumerate(zip(st8["loc_surface"], st8["loc_center"]))}
            l8 = np.array([key8.get((int(st9["surf_ext"][st9["loc_surface"][i]]), tuple(np.round(st9["loc_center"][i], 3))), -1) for i in pc_])
            on = dz["located"] & np.isin(dz["location"], l8[l8 >= 0])
        party[f"{tag}_{run}_end"] = dict(n=int(on.sum()), opaque=int((on & (dz["opacity"] >= 0.5)).sum()), protected=int((on & dz["locked"]).sum()),
                                         invisible_initial=int((on & (dz["init_category"] == 3)).sum()))
ra["shared_walls"] = party
print("shared walls", json.dumps({k: v for k, v in party.items() if k not in ("pairs",)})[:800], flush=True)

# opacity reset at 3,000: rendered depth and accumulated opacity on the target building's pixels
faces_j = json.loads((MAPS / "faces.json").read_text())
tfaces = np.array(faces_j["roof"] + faces_j["wall"], np.int64)
DUMPS = CFG["training"]["control"]["dumps"]
depth = {}
for tag, run_dir in (("r9", P9 / "runs/M_N/model/dump"), ("ctrl", P9 / "runs" / CFG["training"]["control"]["name"] / "model/dump")):
    per_view, pool = {}, {k: [] for k in ("d3001", "d3050", "a3000", "a3001", "a3050")}
    for stem in TRAIN:
        fid = rs(np.load(MAPS / f"faceid/{stem}.npy")).astype(np.int64)
        tp = np.isin(fid, tfaces)
        D = {it: np.load(run_dir / f"iteration_{it}" / f"{stem}_depth.npy").astype(np.float64) for it in DUMPS}
        AL = {it: np.load(run_dir / f"iteration_{it}" / f"{stem}_alpha.npy").astype(np.float32) for it in DUMPS}
        ok = tp & (D[3000] > 0)
        r_ = {}
        for it in (3001, 3050):
            okk = ok & (D[it] > 0)
            dd = np.abs(D[it] - D[3000])[okk]
            pool[f"d{it}"].append(dd)
            r_[f"d{it}"] = dict(p50=pct(dd, 50), p95=pct(dd, 95), share_gt_1m=share(dd > 1.0), share_gt_10m=share(dd > 10.0), n=int(okk.sum()))
        for it in DUMPS:
            pool[f"a{it}"].append(AL[it][tp])
            r_[f"alpha{it}"] = dict(p50=nmed(AL[it][tp]), share_lt_05=share(AL[it][tp] < 0.5))
        r_["target_px"] = int(tp.sum())
        per_view[stem] = r_
    tot = {}
    for it in (3001, 3050):
        dd = np.concatenate(pool[f"d{it}"])
        tot[f"d{it}"] = dict(p50=pct(dd, 50), p95=pct(dd, 95), share_gt_1m=share(dd > 1.0), share_gt_10m=share(dd > 10.0), n=int(len(dd)))
    for it in DUMPS:
        aa = np.concatenate(pool[f"a{it}"])
        tot[f"alpha{it}"] = dict(p50=nmed(aa), share_lt_05=share(aa < 0.5))
    depth[tag] = dict(total=tot, per_view=per_view)
rep_view = max(TRAIN, key=lambda s_: depth["ctrl"]["per_view"][s_]["d3001"]["p95"] if depth["ctrl"]["per_view"][s_]["d3001"]["n"] else -1)
depth["representative_view"] = rep_view
depth["rule"] = "training view with the largest 95 % of |D_3001 - D_3000| on target pixels in the control run"
# the control run reproduces r8's M_N protection counts up to 3,000 (same code, same inputs)
c_rows = [json.loads(l) for l in (P9 / "runs" / CFG["training"]["control"]["name"] / "model/monitor/E.jsonl").read_text().splitlines() if l.strip()]
r8_rows = [json.loads(l) for l in (R8 / "runs/M_N/model/monitor/E.jsonl").read_text().splitlines() if l.strip()]
depth["control_vs_r8"] = [dict(iteration=a["iteration"], control=a["n_locked"], r8=b["n_locked"]) for a, b in zip(c_rows, r8_rows)]
ra["opacity_reset"] = depth
FX["ra"] = ra
print("ra depth", json.dumps({k: v["total"] for k, v in depth.items() if isinstance(v, dict) and "total" in v})[:600], "view", rep_view, flush=True)
(OUT / "fixes.json").write_text(json.dumps(FX, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o)))
print("written", OUT / "cases.json", OUT / "fixes.json")
