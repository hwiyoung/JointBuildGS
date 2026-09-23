"""PHD-STAGE2-PROPAGATION-PREMEASURE-v1, check (c) (jointbuildgs:dev, CPU, no training): can the Gaussian confidence E
and the propagated judgment be computed for every candidate point at initialisation, with occlusion by the prior depth?

  python candidates.py      # after measure.py for all four settings; mounts as measure.py

Candidate points = the prior-origin points of the stage-2 initial cloud of P_<setting> (runs/<cond>/scene/sparse/0).
E: the r6 first computation (jbgs_judgment.compute_E, re-implemented in numpy as in stage2_r6_fix_v1/init_filter_counts.py):
   13 training views, training resolution 1600 x 1157, nearest pixel, inside, z > 0.01 m, prior depth finite and
   |z - P| < 0.5 m; E = mean A over seeing views (A resized by nearest as jbgs_judgment._load_set does).
Location: LoD2 = the polygon of the closest triangle of the scene mesh (Open3D); TIN = the building surface that most
   gentle triangles around the vertex belong to (the stage-2 airborne LiDAR points are the TIN vertices); then the cell
   of that surface (the same location builders as measure.py) and its state / vote / reference judgment.
Writes /out/candidates/candidates.json and candidates_<setting>.npz."""
import json
import struct
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
from plyfile import PlyData

import measure as ms

S2 = ms.S2
OUT = Path("/out/candidates"); OUT.mkdir(parents=True, exist_ok=True)
W, H, TOL = 1600, 1157, 0.5
COND = {"M_N": "P_M_N", "M_B": "P_M_B", "L_N": "P_L_N", "L_B": "P_L_B"}


def read_images_bin(p):
    out = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            f.read(4); q = struct.unpack("<4d", f.read(32)); t = struct.unpack("<3d", f.read(24)); f.read(4)
            name = b""
            while (ch := f.read(1)) != b"\x00":
                name += ch
            f.read(24 * struct.unpack("<Q", f.read(8))[0])
            out[Path(name.decode()).stem] = (ms.q2R(q), np.array(t))
    return out


def first_E(xyz, cond, setting):
    imgs = read_images_bin(S2 / "runs" / cond / "scene/sparse/0/images.bin")
    calib = json.loads((S2 / "runs" / cond / "scene/jbgs_calibration.json").read_text())["images"]
    ssum = np.zeros(len(xyz)); cnt = np.zeros(len(xyz), np.int16)
    for v in ms.TRAIN:
        R, t = imgs[v]; K = np.array(calib[v]["K"])
        P = cv2.resize(np.load(ms.MAPS / f"prior_{setting}/raw_depth/{v}.npy").astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
        A = cv2.resize(np.load(ms.MAPS / f"conf/raw_depth/{v}.npy").astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
        Xc = xyz @ R.T + t; z = Xc[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = K[0, 0] * Xc[:, 0] / z + K[0, 2]; w = K[1, 1] * Xc[:, 1] / z + K[1, 2]
        ui, vi = np.round(u), np.round(w)
        ins = (z > 0.01) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        uii = np.clip(np.nan_to_num(ui), 0, W - 1).astype(np.int64); vii = np.clip(np.nan_to_num(vi), 0, H - 1).astype(np.int64)
        Pv = P[vii, uii]
        sees = ins & np.isfinite(Pv) & (np.abs(z - Pv) < TOL)
        ssum[sees] += A[vii, uii][sees]; cnt += sees.astype(np.int16)
    E = np.where(cnt > 0, ssum / np.maximum(cnt, 1), 0.0)
    return E, cnt


summary = {}
for setting, cond in COND.items():
    ply = PlyData.read(str(S2 / "runs" / cond / "scene/sparse/0/points3D.ply"))["vertex"]
    xyz_all = np.stack([np.asarray(ply[c], np.float64) for c in "xyz"], 1)
    origin = np.load(S2 / "runs" / cond / "scene/sparse/0/origin.npy")
    xyz = xyz_all[origin == 1]
    E, cnt = first_E(xyz, cond, setting)
    mesh = dict(np.load(Path("/out/surfaces") / setting / "mesh.npz"))
    rows = json.loads((Path("/out/surfaces") / setting / "surfaces.json").read_text())["surfaces"]
    kinds = {r["id"]: r["kind"] for r in rows}
    ts = mesh["tri_surface"]; F = mesh["F"].astype(np.int64)
    info = {}
    if setting.startswith("M"):
        sc = o3d.t.geometry.RaycastingScene()
        sc.add_triangles(o3d.core.Tensor(mesh["V"].astype(np.float32)), o3d.core.Tensor(mesh["F"].astype(np.uint32)))
        ans = sc.compute_closest_points(o3d.core.Tensor(xyz.astype(np.float32)))
        cp, tri = ans["points"].numpy(), ans["primitive_ids"].numpy().astype(np.int64)
        dist = np.linalg.norm(cp - xyz, axis=1)
        surf = ts[tri].astype(np.int64)
        info["closest_triangle_distance_m_p50_p99_max"] = [float(np.median(dist)), float(np.percentile(dist, 99)), float(dist.max())]
        locs = ms.Lod2Locations(mesh, rows)
    else:
        V = mesh["V"]
        dv = np.abs(V - xyz).max()
        info["max_abs_difference_to_tin_vertices_m"] = float(dv)
        building = np.array([kinds.get(int(s)) == "building" for s in range(int(ts.max()) + 1)])
        ok_t = (ts >= 0) & building[np.maximum(ts, 0)]
        vv = F[ok_t].reshape(-1); ss = np.repeat(ts[ok_t], 3).astype(np.int64)
        key = vv * (ts.max() + 2) + ss
        uk, cnt_k = np.unique(key, return_counts=True)
        kv, ks = uk // (ts.max() + 2), uk % (ts.max() + 2)
        order = np.lexsort((ks, -cnt_k, kv))          # per vertex: most triangles first, then the smaller (larger-area) surface
        kv, ks = kv[order], ks[order]
        first = np.r_[True, kv[1:] != kv[:-1]]
        surf = np.full(len(V), -1, np.int64); surf[kv[first]] = ks[first]
        locs = ms.TinLocations(mesh, rows)
    z = np.load(Path("/out/measure") / setting / "locations.npz")
    n_grid = json.loads((Path("/out/measure") / setting / "summary.json").read_text())["n_grid_locations"]
    extra_of = {int(s): n_grid + i for i, s in enumerate(z["surface"][n_grid:])}
    loc = np.full(len(xyz), -1, np.int64)
    has = surf >= 0
    if setting.startswith("M"):
        has &= np.array([kinds.get(int(s)) in ("roof", "wall", "ground", "step") for s in surf])
    lk = locs.locate(surf[has], xyz[has])
    lk = np.array([extra_of.get(int(s), -1) if l >= n_grid else l for l, s in zip(lk, surf[has])]) if (lk >= n_grid).any() else lk
    loc[has] = lk
    st = np.where(loc >= 0, z["state"][np.maximum(loc, 0)], -1)
    vote = np.where(loc >= 0, z["vote"][np.maximum(loc, 0)], -1)
    jref = np.where(loc >= 0, z["jref"][np.maximum(loc, 0)], -1)
    e_cls = np.where(cnt == 0, "unseen", np.where(E < 0.5, "E<0.5", "E>=0.5"))
    cols = {"no_location": loc < 0, "invisible": st == ms.ST_INVISIBLE,
            "support_agree": (st == ms.ST_SUPPORT) & (vote == ms.V_AGREE), "support_conflict": (st == ms.ST_SUPPORT) & (vote == ms.V_CONFLICT),
            "missing_conflict": (st == ms.ST_MISSING) & (jref == ms.J_CONFLICT), "missing_agree": (st == ms.ST_MISSING) & (jref == ms.J_AGREE),
            "missing_mixed": (st == ms.ST_MISSING) & (jref == ms.J_MIXED), "missing_insufficient": (st == ms.ST_MISSING) & (jref == ms.J_INSUFF)}
    tab = {ec: {c: int(((e_cls == ec) & m).sum()) for c, m in cols.items()} for ec in ("unseen", "E<0.5", "E>=0.5")}
    summary[setting] = dict(condition=cond, n_candidates=int(len(xyz)), n_with_location=int((loc >= 0).sum()), table=tab, **info)
    np.savez_compressed(OUT / f"candidates_{setting}.npz", xyz=xyz.astype(np.float32), E=E.astype(np.float32), cnt=cnt, surface=surf, loc=loc,
                        state=st, vote=vote, jref=jref)
    print(setting, summary[setting], flush=True)
(OUT / "candidates.json").write_text(json.dumps(dict(summary=summary, reference=ms.GRID["reference"], scientific_verdict=None), indent=1))
