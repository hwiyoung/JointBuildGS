"""Export the final Gaussians (2D surfels) of every stage-2 condition with the intent labels, for the 3D viewer
(jointbuildgs:dev, CPU). scientific_verdict: null.

  python export_intent_surfels.py [--cap 200000] [--min_alpha 0.05]
Mounts: /s2 (payload, rw), /artifacts/JointBuildGS (ro).

For each prior x scene setting and each condition in it, the 30,000-iteration PLY is cropped to the target building
(XY box of the 6 roof + 12 wall faces, +2 m) and every surfel centre x is projected into the 15 cameras (training
resolution, calibrated K; the same cameras as the depth renders). A view counts when the surfel lies on the rendered
surface there (|z - D| < --vis_tol). In those views the surfel gets the same labels the per-pixel table uses:
  class    agree / conflict / unobserved of the pixel it lands on (stage-1 A, M, P, tau; I uses the setting's prior)
  followed status of the rendered surface the surfel is part of, i.e. of the table's pixel:
           agree/unobserved: |D - P| <= tau ; conflict: |D - M| <= tau      (D = rendered depth at that pixel)
  herr     surfel height minus GT height, (G - z) * f, GT min-pooled; + = surfel above GT (walls: outward)
and keeps the majority class, the majority 'followed' and the median herr. Surfels on no rendered surface are 'hidden'.
Kept (inside the height band of surface-forming surfels +-3 m, which drops sky and far surfels): every surfel off the
intent (followed = 0) and every locked surfel, then an XY-stratified sample up to --cap.
Binary: magic JBSF2D2\\0, uint32 count, uint32 floats per surfel (= 22), then float32 records:
  centre.xyz, axis0.xyz, axis1.xyz, normal.xyz, rgb, alpha, class(0 hidden,1 agree,2 conflict,3 unobserved),
  followed(1/0, -1 hidden), herr (NaN if no GT), origin(1 prior, 0 image, -1 unknown), locked(1/0), n_views.
Also writes surfels/index.json: per file counts and per-class surfel summaries, camera presets from the photo poses."""
import os
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from plyfile import PlyData
GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")   # evaluation GT maps: gt_clean (visibility + ground datum, make_gt_clean.py) or gt (raw)

S2 = Path("/s2")
MAPS = S2 / "inputs/maps"
OUT = S2 / "dashboard/surfels"
ART = Path("/artifacts/JointBuildGS")
PJ = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
SETTINGS = {"M_N": ["P_M_N", "P0_M_N", "O_M_N", "I"], "M_B": ["P_M_B", "P0_M_B", "O_M_B", "I"],
            "L_N": ["P_L_N", "P0_L_N", "I"], "L_B": ["P_L_B", "P0_L_B", "I"]}
PRESET_VIEWS = {"0009": "DJI_20241217101313_0009_D", "0024": "DJI_20241217101343_0024_D", "0005": "DJI_20241217101305_0005_D"}
SH_C0 = 0.28209479177387814
MAGIC = b"JBSF2D2\0"
FPS = 22

ap = argparse.ArgumentParser()
ap.add_argument("--cap", type=int, default=200_000)
ap.add_argument("--min_alpha", type=float, default=0.05)
ap.add_argument("--vis_tol", type=float, default=0.2)
ap.add_argument("--max_scale", type=float, default=1.5)
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]
polys = [p for p in json.loads(PJ.read_text())["polygons"] if p["poly_index"] in ROOF + WALL]
xy = np.concatenate([np.array(p["ring_local_xy"]) for p in polys])
BOX = (xy[:, 0].min() - 2, xy[:, 0].max() + 2, xy[:, 1].min() - 2, xy[:, 1].max() + 2)


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


# cameras: poses from the stage-1 sparse text, intrinsics at the training resolution (calibration used by the renders)
calib = json.loads((S2 / "runs/P_M_N/scene/jbgs_calibration.json").read_text())["images"]
CAMS = {}
for line in (SPARSE / "images.txt").read_text().splitlines():
    t = line.split()
    if len(t) >= 10 and not line.startswith("#") and t[9].lower().endswith(".jpg"):
        name = Path(t[9]).stem
        R = q2R([float(v) for v in t[1:5]]); tv = np.array([float(v) for v in t[5:8]])
        K = np.array(calib[name]["K"]); CAMS[name] = dict(R=R, t=tv, K=K, W=calib[name]["width"], H=calib[name]["height"], C=-R.T @ tv)
cache = {}


def load(setname, view, size, dtype=np.float32):
    key = (setname, view)
    if key not in cache:
        p = MAPS / setname / "raw_depth" / f"{view}.npy"
        x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy")
        cache[key] = cv2.resize(x.astype(np.float32), size, interpolation=cv2.INTER_NEAREST).astype(dtype)
    return cache[key]


def gt_min(view, size):
    key = ("gtmin", view)
    if key not in cache:
        g = np.load(MAPS / GT_SET / "raw_depth" / f"{view}.npy"); ok = np.isfinite(g) & (g > 0)
        k = int(np.ceil(g.shape[1] / size[0])) + 2
        gm = cv2.resize(cv2.erode(np.where(ok, g, np.inf).astype(np.float32), np.ones((k, k), np.uint8)), size,
                        interpolation=cv2.INTER_NEAREST)
        gm[~np.isfinite(gm)] = np.nan
        cache[key] = gm
    return cache[key]


def read_model(cond):
    v = PlyData.read(str(S2 / "runs" / cond / "model/point_cloud/iteration_30000/point_cloud.ply"))["vertex"]
    names = [p.name for p in v.properties]
    g = lambda n: np.asarray(v[n], dtype=np.float32)  # noqa: E731
    xyz = np.stack([g("x"), g("y"), g("z")], 1)
    alpha = 1 / (1 + np.exp(-g("opacity")))
    m = (xyz[:, 0] > BOX[0]) & (xyz[:, 0] < BOX[1]) & (xyz[:, 1] > BOX[2]) & (xyz[:, 1] < BOX[3]) & (alpha >= a.min_alpha)
    idx = np.flatnonzero(m)
    q = np.stack([g("rot_0"), g("rot_1"), g("rot_2"), g("rot_3")], 1)[idx]
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q.T
    ax0 = np.stack([1 - 2*(y*y + z*z), 2*(x*y + z*w), 2*(x*z - y*w)], 1)
    ax1 = np.stack([2*(x*y - z*w), 1 - 2*(x*x + z*z), 2*(y*z + x*w)], 1)
    nrm = np.stack([2*(x*z + y*w), 2*(y*z - x*w), 1 - 2*(x*x + y*y)], 1)
    sc = np.minimum(np.exp(np.stack([g("scale_0"), g("scale_1")], 1)[idx]), a.max_scale)
    rgb = np.clip(np.stack([g("f_dc_0"), g("f_dc_1"), g("f_dc_2")], 1)[idx] * SH_C0 + 0.5, 0, 1)
    origin = g("origin")[idx] if "origin" in names else np.full(idx.size, -1, np.float32)
    locked = np.zeros(idx.size, np.float32)
    dump = S2 / "runs" / cond / "model/dump/iteration_30000/gaussians.npz"
    if dump.exists():
        L = np.load(dump)["locked"]
        if L.shape[0] == len(v["x"]):
            locked = L[idx].astype(np.float32)
    return dict(xyz=xyz[idx], ax0=ax0 * sc[:, :1], ax1=ax1 * sc[:, 1:2], nrm=nrm, rgb=rgb, alpha=alpha[idx], origin=origin,
                locked=locked, n_total=len(v["x"]))


def label(model, cond, pset, tset):
    X = model["xyz"].astype(np.float64); n = X.shape[0]
    votes = np.zeros((n, 4), np.int32); fol = np.zeros(n, np.int32); nv = np.zeros(n, np.int32)
    hsum = np.full((len(CAMS), n), np.nan, np.float32)
    for vi, (name, c) in enumerate(sorted(CAMS.items())):
        size = (c["W"], c["H"])
        D = np.load(S2 / "eval" / cond / "render_30000" / f"{name}_depth.npy")
        A, M, P, T = load("conf", name, size), load("mvs", name, size), load(pset, name, size), load(tset, name, size)
        FV, G = load("fvert", name, size), gt_min(name, size)
        Xc = X @ c["R"].T + c["t"]; zc = Xc[:, 2]
        u = c["K"][0, 0] * Xc[:, 0] / zc + c["K"][0, 2]; v = c["K"][1, 1] * Xc[:, 1] / zc + c["K"][1, 2]
        ui, vi_ = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
        ins = (zc > 0.1) & (ui >= 0) & (ui < size[0]) & (vi_ >= 0) & (vi_ < size[1])
        k = np.flatnonzero(ins); pu, pv = ui[k], vi_[k]; z = zc[k].astype(np.float32)
        d = D[pv, pu]; vis = (d > 0) & (np.abs(z - d) < a.vis_tol)
        k, pu, pv, z, d = k[vis], pu[vis], pv[vis], z[vis], d[vis]
        Ap, Mp, Pp, Tp = A[pv, pu], M[pv, pu], P[pv, pu], T[pv, pu]
        base = np.isfinite(Pp) & (Pp > 0) & np.isfinite(Tp); hasM = np.isfinite(Mp) & (Mp > 0)
        cls = np.zeros(k.size, np.int32)
        cls[base & (Ap > 0) & hasM & (np.abs(Mp - Pp) <= Tp)] = 1
        cls[base & (Ap > 0) & hasM & (np.abs(Mp - Pp) > Tp)] = 2
        cls[base & (Ap <= 0)] = 3
        good = np.where(cls == 2, np.abs(d - Mp) <= Tp, np.abs(d - Pp) <= Tp)   # the surface this surfel helps render
        votes[k, cls] += 1
        lab = cls > 0
        fol[k[lab]] += good[lab].astype(np.int32)
        nv[k] += 1
        hsum[vi, k] = (G[pv, pu] - z) * FV[pv, pu]
    has = votes[:, 1:].sum(1) > 0
    cls = np.where(has, 1 + np.argmax(votes[:, 1:], 1), 0)
    followed = np.where(has, (fol / np.maximum(votes[:, 1:].sum(1), 1)) >= 0.5, False).astype(np.float32)
    followed[~has] = -1
    with np.errstate(all="ignore"):
        herr = np.nanmedian(hsum, axis=0)
    return cls.astype(np.float32), followed, herr.astype(np.float32), nv.astype(np.float32)


def stratified(idx_pool, xy, quota, seed=0):
    if quota <= 0 or idx_pool.size == 0:
        return np.zeros(0, np.int64)
    if idx_pool.size <= quota:
        return idx_pool
    rng = np.random.default_rng(seed)
    cell = np.floor((xy[idx_pool] - xy[idx_pool].min(0)) / 0.5).astype(np.int64)
    key = cell[:, 0] * 100000 + cell[:, 1]
    order = rng.permutation(idx_pool.size)
    # round-robin over cells: take the i-th member of every cell before the (i+1)-th of any
    k_sorted = key[order]; o2 = np.argsort(k_sorted, kind="stable"); ks = k_sorted[o2]
    first = np.r_[0, np.flatnonzero(np.diff(ks)) + 1]
    rank = np.arange(ks.size) - np.repeat(first, np.diff(np.r_[first, ks.size]))
    pick = order[o2][np.argsort(rank, kind="stable")][:quota]
    return np.sort(idx_pool[pick])


index = {"box": [float(b) for b in BOX], "files": {}, "presets": {}}
bx, by = (BOX[0] + BOX[1]) / 2, (BOX[2] + BOX[3]) / 2
for key, name in PRESET_VIEWS.items():
    c = CAMS[name]
    index["presets"][key] = dict(center=[float(v) for v in c["C"]], view=name)
for setting, conds in SETTINGS.items():
    prior, scene = setting.split("_")
    pset, tset = f"prior_{prior}_{scene}", f"tau_{prior}"
    for cond in conds:
        m = read_model(cond)
        cls, followed, herr, nv = label(m, cond, pset, tset)
        zv = m["xyz"][cls > 0, 2]   # height band of surfels that form a rendered surface: drops sky/far surfels
        zlo, zhi = np.percentile(zv, 0.2) - 3.0, np.percentile(zv, 99.8) + 3.0
        band = (m["xyz"][:, 2] >= zlo) & (m["xyz"][:, 2] <= zhi)
        keep = np.flatnonzero(((followed == 0) | (m["locked"] > 0)) & band)
        rest = np.setdiff1d(np.flatnonzero(band), keep)
        sel = np.sort(np.concatenate([keep, stratified(rest, m["xyz"][:, :2], a.cap - keep.size)]))
        rec = np.empty((sel.size, FPS), np.float32)
        rec[:, 0:3] = m["xyz"][sel]; rec[:, 3:6] = m["ax0"][sel]; rec[:, 6:9] = m["ax1"][sel]; rec[:, 9:12] = m["nrm"][sel]
        rec[:, 12:15] = m["rgb"][sel]; rec[:, 15] = m["alpha"][sel]; rec[:, 16] = cls[sel]; rec[:, 17] = followed[sel]
        rec[:, 18] = herr[sel]; rec[:, 19] = m["origin"][sel]; rec[:, 20] = m["locked"][sel]; rec[:, 21] = nv[sel]
        fname = f"{setting}_{cond}.bin"
        with (OUT / fname).open("wb") as f:
            f.write(MAGIC); f.write(np.uint32(sel.size).tobytes()); f.write(np.uint32(FPS).tobytes()); rec.tofile(f)
        summ = {}
        for ci, cname in ((1, "agree"), (2, "conflict"), (3, "unobserved")):
            mm = cls == ci
            summ[cname] = dict(n=int(mm.sum()), followed=float((followed[mm] == 1).mean()) if mm.any() else None,
                               herr_median=float(np.nanmedian(herr[mm])) if mm.any() and np.isfinite(herr[mm]).any() else None)
        index["files"][f"{setting}/{cond}"] = dict(file=fname, exported=int(sel.size), in_box=int(cls.size), total=m["n_total"],
                                                   hidden=int((cls == 0).sum()), off_intent=int((followed == 0).sum()),
                                                   locked=int((m["locked"] > 0).sum()), classes=summ)
        print(setting, cond, index["files"][f"{setting}/{cond}"]["exported"], "exported;",
              {k: (v["n"], round(v["followed"], 3) if v["followed"] is not None else None) for k, v in summ.items()}, flush=True)
index["target_center"] = [float(bx), float(by)]
(OUT / "index.json").write_text(json.dumps(index, indent=1))
print("wrote", OUT)
