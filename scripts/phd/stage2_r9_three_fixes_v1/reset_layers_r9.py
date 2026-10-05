"""PHD-STAGE2-R9-THREE-FIXES-v1 step 13b (jointbuildgs:dev, CPU): which layer the rendered depth of the target building's
pixels lands on right after the opacity reset (fix 'ra', qualitative check made countable).

  python reset_layers_r9.py      # mounts: /artifacts (ro), /repo (ro), /r7 (ro), /r8 (ro), /p9 (rw)

For the 13 training views at the training resolution, every ray of a target-building pixel (maps/faceid in the target
roof / wall polygons of faces.json) is cast through the r8 LoD2 mesh (bottom faces included) with its first MAXHIT
intersections (Open3D cast_rays repeated from 1 mm beyond the last hit; camera-Z distance, pixel centres of the native
intrinsics as figure_r8.rays_train). The
rendered expected depth D of a dump (r9 M_N and the control run of the r8 code; iterations 3,000, 3,001, 3,050) is put in
one class per pixel:
  front        |D - first hit| <= 0.5 m (the surface the view sees)
  bottom face  within 0.5 m of a later hit on a GroundSurface triangle (the inside of the building's bottom)
  other inner  within 0.5 m of a later hit on another LoD2 face (the inside of a far wall or roof)
  between      beyond the first hit by more than 0.5 m and not near a later hit (an average of transparent layers, or
               something that is not LoD2: ground, image-origin Gaussians)
  in front     more than 0.5 m in front of the first hit
Writes /p9/cases/reset_layers.json."""
import json
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
MAPS = S2 / "inputs/maps"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
R7 = Path("/r7"); P9 = Path("/p9")
CFG = json.loads(Path("/repo/configs/phd/stage2_r9_three_fixes_v1/r9.json").read_text())
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
H, W = 1157, 1600
TOL = 0.5
MAXHIT = 6
PZ = np.load(S1 / "inputs/lod2_polygons.npz")


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


CAMS, IMGS = {}, {}
for l in (SPARSE / "cameras.txt").read_text().splitlines():
    if l.strip() and not l.startswith("#"):
        t = l.split(); CAMS[int(t[0])] = dict(W=int(t[2]), H=int(t[3]), p=[float(x) for x in t[4:]])
for l in (SPARSE / "images.txt").read_text().splitlines():
    t = l.split()
    if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
        IMGS[Path(t[9]).stem] = dict(R=q2R([float(x) for x in t[1:5]]), t=np.array([float(x) for x in t[5:8]]), cam=int(t[8]))


def rays_train(stem):
    im = IMGS[stem]; cam = CAMS[im["cam"]]; fx, fy, cx, cy = cam["p"]
    sx, sy = W / cam["W"], H / cam["H"]
    u = (np.arange(W) + 0.5) / sx; v = (np.arange(H) + 0.5) / sy
    xn = ((u - cx) / fx)[None, :]; yn = ((v - cy) / fy)[:, None]
    R = im["R"]
    d = np.stack([R[0, k] * xn + R[1, k] * yn + R[2, k] for k in range(3)], -1)
    return d, -R.T @ im["t"]


m = np.load(R7 / "stage1/meshes/M_N.npz")
V, F = m["V"], m["F"]
bottom_tri = np.zeros(len(F), bool); bottom_tri[:len(PZ["labels"])] = np.isin(PZ["labels"].astype(str), ["GroundSurface", "ClosureSurface"])
scene = o3d.t.geometry.RaycastingScene()
scene.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(F.astype(np.uint32)))
faces_j = json.loads((MAPS / "faces.json").read_text())
tfaces = np.array(faces_j["roof"] + faces_j["wall"], np.int64)
RUNS = {"r9": P9 / "runs/M_N/model/dump", "ctrl": P9 / "runs" / CFG["training"]["control"]["name"] / "model/dump"}
ITS = (3000, 3001, 3050)
CLS = ("front", "bottom face", "other inner", "between", "in front", "no render")
count = {(r, it): np.zeros(len(CLS), np.int64) for r in RUNS for it in ITS}
per_view = {}
for stem in TRAIN:
    fid = cv2.resize(np.load(MAPS / f"faceid/{stem}.npy").astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST).astype(np.int64)
    tp = np.isin(fid, tfaces)
    d, C = rays_train(stem)
    pix = np.nonzero(tp.reshape(-1))[0]
    dd = d.reshape(-1, 3)[pix].astype(np.float64)
    T_ = np.zeros(len(pix)); alive = np.ones(len(pix), bool)
    hits_t, hits_p, hits_r, hits_k = [], [], [], []
    for k in range(MAXHIT):                       # successive hits along each ray (camera-Z distance)
        idx = np.nonzero(alive)[0]
        if len(idx) == 0:
            break
        org = C[None, :] + (T_[idx] + (1e-3 if k else 0.0))[:, None] * dd[idx]
        res = scene.cast_rays(o3d.core.Tensor(np.concatenate([org, dd[idx]], 1).astype(np.float32)))
        t = res["t_hit"].numpy().astype(np.float64); pr = res["primitive_ids"].numpy().astype(np.int64)
        ok = np.isfinite(t)
        tt = T_[idx] + (1e-3 if k else 0.0) + t
        hits_t.append(tt[ok]); hits_p.append(pr[ok]); hits_r.append(idx[ok]); hits_k.append(np.full(int(ok.sum()), k))
        T_[idx[ok]] = tt[ok]; alive[idx[~ok]] = False
    th = np.concatenate(hits_t); pid = np.concatenate(hits_p); ray_of_hit = np.concatenate(hits_r); rank = np.concatenate(hits_k)
    first = np.full(len(pix), np.nan); first[ray_of_hit[rank == 0]] = th[rank == 0]
    has = np.isfinite(first)
    pv = {}
    for r, root in RUNS.items():
        for it in ITS:
            D = np.load(root / f"iteration_{it}" / f"{stem}_depth.npy").astype(np.float64).reshape(-1)[pix]
            rend = D > 0
            near_hit = (np.abs(th - D[ray_of_hit]) <= TOL) & (rank >= 1)
            on_bottom = np.zeros(len(pix), bool); on_other = np.zeros(len(pix), bool)
            on_bottom[np.unique(ray_of_hit[near_hit & bottom_tri[pid]])] = True
            on_other[np.unique(ray_of_hit[near_hit & ~bottom_tri[pid]])] = True
            cls = np.full(len(pix), 3, np.int64)                      # between
            cls[D < first - TOL] = 4
            cls[on_other] = 2
            cls[on_bottom] = 1                                        # the bottom face wins when both are near
            cls[np.abs(D - first) <= TOL] = 0
            cls[~rend] = 5
            c = np.bincount(cls, minlength=len(CLS))
            count[(r, it)] += c
            pv[f"{r}_{it}"] = c.tolist()
    per_view[stem] = pv
    print(stem, {k: v for k, v in pv.items() if k.endswith("3001")}, flush=True)
out = dict(rule=__doc__.split("\n\n")[2], classes=list(CLS), tolerance_m=TOL,
           totals={f"{r}_{it}": dict(zip(CLS, (count[(r, it)] / max(count[(r, it)].sum(), 1)).round(4).tolist()), n=int(count[(r, it)].sum()))
                   for r in RUNS for it in ITS}, per_view=per_view)
(P9 / "cases/reset_layers.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out["totals"], indent=1))
