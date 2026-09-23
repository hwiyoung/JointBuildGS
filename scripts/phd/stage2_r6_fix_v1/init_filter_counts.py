"""Fix 4 without training (PHD-STAGE2-R6-FIX-v1, jointbuildgs:dev, CPU): which initial prior points does the r6 rule
remove, per face type, for both priors (L = ALS, M = LoD2) and both scenes (N nominal, B main roof +1 m).

  python init_filter_counts.py         # mounts: /s2 (stage-2 payload, ro), /s1 (stage-1 payload, ro), /r6 (this task, rw)

Rule (the same as jbgs_judgment.init_visible_filter, re-implemented in numpy): a prior point is kept iff at least one of
the 13 training views sees it: projection inside the image (nearest pixel of the training-resolution grid), camera depth
> 0.01 m, prior depth finite at that pixel and |z - P| < 0.5 m. Cameras: the scene's images.bin + jbgs_calibration.json.
Face type of a point: the LoD2 polygon of the nearest triangle of the registered v2 mesh (Open3D closest point); type from
the CityGML surface type where lod2_polygons.json has it, else from the triangle normal (n_z > 0.5 roof, < -0.5 ground,
otherwise wall). A point farther than 0.3 m (M) / 1.0 m (L) from every LoD2 triangle is 'other' (for L split by ALS class).
/s1 = phase-payloads/phd/stage1_conf_tol_conflict_v1 (both stage-1 task folders). Writes /r6/init_counts/{init_counts.csv, init_counts_by_polygon.csv, init_counts.json, dropped_<set>.npz}."""
import csv
import json
import struct
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
from plyfile import PlyData

S2, S1, OUT = Path("/s2"), Path("/s1"), Path("/r6/init_counts")
V2 = S1 / "PHD-STAGE1-VERIFY-v2/inputs_v2"
OUT.mkdir(parents=True, exist_ok=True)
W, H, TOL = 1600, 1157, 0.5
SETS = {"M_N": ("P_M_N", "lod2_v2_nominal_local.npz", 0.3), "M_B": ("P_M_B", "lod2_v2_biased_main_local.npz", 0.3),
        "L_N": ("P_L_N", "lod2_v2_nominal_local.npz", 1.0), "L_B": ("P_L_B", "lod2_v2_nominal_local.npz", 1.0)}
TRAIN = json.loads((Path("/r6/runs/N/model/monitor/meta.json") if Path("/r6/runs/N/model/monitor/meta.json").exists()
                    else S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
PJ = {p["poly_index"]: p for p in json.loads((S1 / "PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json").read_text())["polygons"]}
TYPE_OF = {"RoofSurface": "roof", "WallSurface": "wall", "GroundSurface": "ground"}


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


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
            out[Path(name.decode()).stem] = (q2R(q), np.array(t))
    return out


def seeing_counts(xyz, cond, prior_set):
    imgs = read_images_bin(S2 / "runs" / cond / "scene/sparse/0/images.bin")
    calib = json.loads((S2 / "runs" / cond / "scene/jbgs_calibration.json").read_text())["images"]
    cnt = np.zeros(len(xyz), np.int16)
    for v in TRAIN:
        R, t = imgs[v]; K = np.array(calib[v]["K"])
        P = np.load(S2 / "inputs/maps" / prior_set / "raw_depth" / f"{v}.npy").astype(np.float32)
        P = cv2.resize(P, (W, H), interpolation=cv2.INTER_NEAREST)        # = jbgs_judgment._load_set
        Xc = xyz @ R.T + t; z = Xc[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = K[0, 0] * Xc[:, 0] / z + K[0, 2]; w = K[1, 1] * Xc[:, 1] / z + K[1, 2]
        ui, vi = np.round(u), np.round(w)
        ins = (z > 0.01) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        uii = np.clip(np.nan_to_num(ui), 0, W - 1).astype(np.int64); vii = np.clip(np.nan_to_num(vi), 0, H - 1).astype(np.int64)
        Pv = P[vii, uii]
        cnt += (ins & np.isfinite(Pv) & (np.abs(z - Pv) < TOL)).astype(np.int16)
    return cnt


def classify(xyz, mesh_file, dmax):
    d = np.load(V2 / mesh_file)
    Vt, T, pot = d["vertices_local"], d["faces"], d["poly_of_tri"]
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(Vt.astype(np.float32)), o3d.core.Tensor(T.astype(np.uint32)))
    ans = scene.compute_closest_points(o3d.core.Tensor(xyz.astype(np.float32)))
    cp, tri = ans["points"].numpy(), ans["primitive_ids"].numpy().astype(np.int64)
    dist = np.linalg.norm(cp - xyz, axis=1)
    poly = pot[tri]
    e1, e2 = Vt[T[:, 1]] - Vt[T[:, 0]], Vt[T[:, 2]] - Vt[T[:, 0]]
    nrm = np.cross(e1, e2); nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    typ = np.empty(len(xyz), object)
    for i in range(len(xyz)):
        pj = PJ.get(int(poly[i]))
        if pj is not None and pj["citygml_type"] in TYPE_OF:
            typ[i] = TYPE_OF[pj["citygml_type"]]
        else:
            nz = nrm[tri[i], 2]
            typ[i] = "roof" if nz > 0.5 else ("ground" if nz < -0.5 else "wall")
    typ[dist > dmax] = "other"
    target = np.array([bool(PJ.get(int(p), {}).get("is_target", False)) for p in poly]) & (dist <= dmax)
    return typ.astype(str), poly, dist, target


rows, poly_rows, summary = [], [], {}
for key, (cond, mesh_file, dmax) in SETS.items():
    ply = PlyData.read(str(S2 / "runs" / cond / "scene/sparse/0/points3D.ply"))["vertex"]
    xyz_all = np.stack([np.asarray(ply[c], np.float64) for c in "xyz"], 1)
    origin = np.load(S2 / "runs" / cond / "scene/sparse/0/origin.npy")
    xyz = xyz_all[origin == 1]
    cnt = seeing_counts(xyz, cond, f"prior_{key}")
    drop = cnt == 0
    typ, poly, dist, target = classify(xyz, mesh_file, dmax)
    rec = dict(set=key, condition=cond, n_prior=int(len(xyz)), n_dropped=int(drop.sum()), n_kept=int((~drop).sum()),
               nearest_lod2_dist_median=float(np.median(dist)), type_cutoff_m=dmax)
    for t_ in ("roof", "wall", "ground", "other"):
        m = typ == t_
        rec[f"dropped_{t_}"] = int((drop & m).sum()); rec[f"kept_{t_}"] = int((~drop & m).sum())
        rec[f"dropped_{t_}_target"] = int((drop & m & target).sum()); rec[f"kept_{t_}_target"] = int((~drop & m & target).sum())
    if key.startswith("L"):
        cls = np.load(S1 / "PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/als_points.npz")["classification"]
        for c_ in (2, 6):
            rec[f"dropped_other_class{c_}"] = int((drop & (typ == "other") & (cls == c_)).sum())
            rec[f"dropped_class{c_}"] = int((drop & (cls == c_)).sum()); rec[f"kept_class{c_}"] = int((~drop & (cls == c_)).sum())
    # cross-check with the r6 training run's own filter (same scene and rule)
    run = {"M_N": "N", "M_B": "B"}.get(key)
    if run and (Path("/r6/runs") / run / "model/monitor/init_filter.npz").exists():
        z = np.load(Path("/r6/runs") / run / "model/monitor/init_filter.npz")
        dr = z["dropped"][z["origin"] == 1]
        rec["fork_agreement"] = float((dr == drop).mean()); rec["fork_dropped"] = int(dr.sum())
    rows.append(rec); summary[key] = rec
    for p_ in np.unique(poly[drop & (typ != "other")]):
        m = drop & (poly == p_) & (typ != "other")
        pj = PJ.get(int(p_), {})
        poly_rows.append([key, int(p_), pj.get("citygml_type", "normal:" + str(typ[m][0])), bool(pj.get("is_target", False)),
                          int(m.sum()), int(((poly == p_) & (typ != "other")).sum())])
    np.savez_compressed(OUT / f"dropped_{key}.npz", xyz=xyz.astype(np.float32), dropped=drop, type=typ, poly=poly.astype(np.int32),
                        dist=dist.astype(np.float32), cnt=cnt, target=target)
    print(key, {k: rec[k] for k in rec if k.startswith(("n_", "dropped_", "fork"))}, flush=True)
keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0].keys()).index(k) if k in rows[0] else 999)
with open(OUT / "init_counts.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); [w.writerow(r) for r in rows]
poly_rows.sort(key=lambda r: (r[0], -r[4]))
with open(OUT / "init_counts_by_polygon.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["set", "poly_index", "type", "is_target", "n_dropped", "n_points_on_polygon"]); w.writerows(poly_rows)
(OUT / "init_counts.json").write_text(json.dumps(dict(summary=summary, rule="kept iff >= 1 of 13 training views: inside, z > 0.01, |z - P| < 0.5 m",
                                                    scientific_verdict=None), indent=1))
