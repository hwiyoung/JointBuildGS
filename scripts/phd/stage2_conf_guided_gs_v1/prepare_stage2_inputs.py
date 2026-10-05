"""Stage-2 inputs (jointbuildgs:dev). Builds per-view map sets and per-condition scene directories from stage-1/v2 outputs.
Maps (5644x4082 float32, NaN = absent) under inputs/maps/<set>/raw_depth/{view}.npy so GeoGS load_depth_set can read them:
  conf/        A (0/1)                         mvs/      MVS camera-Z depth where A=1
  prior_L_N, prior_L_B, prior_M_N, prior_M_B   prior camera-Z depth (M cropped to the ALS rectangle)
  tau_L, tau_M                                  per-pixel width tau_p = tau_v / f_p (NaN where prior absent)
  fvert/                                       per-pixel conversion f_p of a camera-depth residual to metres:
                                               vertical |n.d|/|n_z| on roof-like faces (|n_z| >= WALL_NZ), surface normal
                                               |n.d| on wall-like faces (vertical shift of a wall is undefined), |d_z| off
                                               the LoD2 faces
  gt/                                          GT UAV cloud projected (z-buffer), evaluation only
--conversion recomputes only fvert/ and tau_*/ (reads the saved prior maps for their extent).
Point sets under inputs/points/: sfm.npz, prior_L_N.npz, prior_L_B.npz, prior_M_N.npz, prior_M_B.npz (local frame, rgb).
"""
import argparse, json, struct, sys
from pathlib import Path
import numpy as np
from shapely.geometry import Point, Polygon

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
V2 = S1.parent / "PHD-STAGE1-VERIFY-v2"
S2 = Path("/s2")
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
DIAG = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
V2CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
TAU = json.loads((V2 / "out_v2_data/checks_v2.json").read_text())["handover"]
TAU_V = {"L": TAU["tau_L"], "M": TAU["tau_M"]}
MAPS = S2 / "inputs/maps"; PTS = S2 / "inputs/points"; MAPS.mkdir(parents=True, exist_ok=True); PTS.mkdir(parents=True, exist_ok=True)
ap = argparse.ArgumentParser(); ap.add_argument("--maps", action="store_true"); ap.add_argument("--points", action="store_true")
ap.add_argument("--conversion", action="store_true"); ARGS = ap.parse_args()
if not (ARGS.maps or ARGS.points or ARGS.conversion): ARGS.maps = ARGS.points = True
WALL_NZ = 0.5  # faces with |n_z| below this are converted along their normal (data: walls n_z = 0, roofs n_z >= 0.742)
sys.path.insert(0, "/source/scene"); import colmap_loader as col  # noqa: E402 (pristine GeoGS reader)
sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v1 import conversion as conv  # noqa: E402


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w], [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


cams, imgs = {}, {}
for l in (SPARSE / "cameras.txt").read_text().splitlines():
    if l.strip() and not l.startswith("#"):
        t = l.split(); cams[int(t[0])] = dict(W=int(t[2]), H=int(t[3]), p=[float(x) for x in t[4:]])
for l in (SPARSE / "images.txt").read_text().splitlines():
    t = l.split()
    if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
        imgs[Path(t[9]).stem] = dict(q=[float(x) for x in t[1:5]], t=np.array([float(x) for x in t[5:8]]), cam=int(t[8]))
stems = sorted(imgs)
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
crop = np.array(PJ["als_crop_local_xy"])
PZ = np.load(V2 / "inputs_v2/lod2_v2_nominal_local.npz"); prc = PZ["poly_region_code"]
poly_normal = np.zeros((len(prc), 3), np.float32)
for p in PJ["polygons"]:
    poly_normal[p["poly_index"]] = p["normal"]
main_ring = Polygon(next(p for p in PJ["polygons"] if p["poly_index"] == 3396)["ring_local_xy"])


def save(setname, stem, arr):
    d = MAPS / setname / "raw_depth"; d.mkdir(parents=True, exist_ok=True)
    np.save(d / f"{stem}.npy", arr.astype(np.float32))


def conversion(poly, d):
    """f_p: metres per metre of camera depth. [PHD-STAGE2-R7-PROPAGATION-v1] one implementation for stage 1 and stage 2:
    src/phd/prior_propagation_v1/conversion.factor (roof-like vertical, wall-like along the normal, no face |d_z|). This
    r5 preparation keeps its own normal input (the nominal LoD2 polygon map); the r7 inputs use the scene's own normals."""
    return conv.factor(poly_normal[np.maximum(poly, 0)], np.stack(d, -1), has_surface=poly >= 0, roof_nz=WALL_NZ).astype(np.float32)


def view_geometry(stem):
    cam = cams[imgs[stem]["cam"]]; fx, fy, cx, cy = cam["p"]; W, H = cam["W"], cam["H"]; R = q2R(imgs[stem]["q"])
    r = conv.pixel_rays(fx, fy, cx, cy, R, W, H)   # R^T (x,y,1) at pixel centres (shared conversion module)
    return [r[..., k] for k in range(3)]


if ARGS.conversion:
    rep = {"WALL_NZ": WALL_NZ, "views": {}}
    for stem in stems:
        d = view_geometry(stem)
        poly = np.load(V2 / "inputs_v2/faceid" / f"{stem}.npy")
        f = conversion(poly, d)
        save("fvert", stem, f)
        wall = (poly >= 0) & (np.abs(poly_normal[np.maximum(poly, 0)][..., 2]) < WALL_NZ)
        r = {"wall_px": int(wall.sum()), "fvert_wall_p50": float(np.median(f[wall])) if wall.any() else None}
        for k in ("L", "M"):
            ok = np.isfinite(np.load(MAPS / f"prior_{k}_N" / "raw_depth" / f"{stem}.npy"))
            save(f"tau_{k}", stem, np.where(ok, TAU_V[k] / np.maximum(f, 1e-3), np.nan))
            r[f"tau_{k}_wall_p50"] = float(np.median(TAU_V[k] / np.maximum(f[wall & ok], 1e-3))) if (wall & ok).any() else None
        rep["views"][stem] = r
        print(stem, r, flush=True)
    rp = S2 / "inputs/prepare_report.json"; old = json.loads(rp.read_text())
    old["conversion"] = dict(rule="vertical |n.d|/|n_z| if |n_z| >= WALL_NZ else normal |n.d|; off LoD2 faces |d_z|", **rep)
    rp.write_text(json.dumps(old, indent=1))
    sys.exit(0)


# ---- GT cloud (evaluation only)
import open3d as o3d
gt = np.asarray(o3d.io.read_point_cloud(str(DIAG / "conditions/N/evaluation/gt_cropped.ply")).points)
prior_src = {"L_N": V2 / "inputs_v2/prior_render/L_nominal/lod2_prior", "L_B": V2 / "inputs_v2/prior_render/L_biased_main/lod2_prior",
             "M_N": V2 / "inputs_v2/prior_render/M_nominal/lod2_prior", "M_B": S2 / "inputs/prior_render/M_biased_main_1m/lod2_prior"}
report = {"tau_v": TAU_V, "views": {}}
for stem in (stems if ARGS.maps else []):
    cam = cams[imgs[stem]["cam"]]; fx, fy, cx, cy = cam["p"]; W, H = cam["W"], cam["H"]; R = q2R(imgs[stem]["q"]); t = imgs[stem]["t"]; C = -R.T @ t
    A = np.load(S1 / "out/conf" / f"{stem}_conf.npy").astype(np.float32); save("conf", stem, A)
    mvs = np.load(S1 / "inputs/mvs_full" / f"{stem}_depth.npy"); save("mvs", stem, np.where(A == 1, mvs, np.nan))
    d = view_geometry(stem)
    poly = np.load(V2 / "inputs_v2/faceid" / f"{stem}.npy")
    f = conversion(poly, d)
    rec = {}
    for key, src in prior_src.items():
        pdp = src / "raw_depth" / f"{stem}.npy"
        if not pdp.exists():
            rec[key] = "missing"; continue
        pdep = np.load(pdp).astype(np.float32); ok = np.isfinite(pdep) & (pdep > 0) & (pdep < 1e6)
        if key.startswith("M"):   # crop M to the ALS rectangle so L and M cover the same ground
            X = C[0] + pdep * d[0]; Y = C[1] + pdep * d[1]
            ok &= (X >= crop[0, 0]) & (X <= crop[1, 0]) & (Y >= crop[0, 1]) & (Y <= crop[1, 1])
        save(f"prior_{key}", stem, np.where(ok, pdep, np.nan))
        if key.endswith("_N"):
            save(f"tau_{key[0]}", stem, np.where(ok, TAU_V[key[0]] / np.maximum(f, 1e-3), np.nan))
        rec[key] = int(ok.sum())
    # GT z-buffer: project points, keep nearest depth per pixel
    Xc = (R @ gt.T).T + t; z = Xc[:, 2]; u = np.floor(fx * Xc[:, 0] / z + cx).astype(np.int64); v = np.floor(fy * Xc[:, 1] / z + cy).astype(np.int64)
    ins = (z > 0) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    gtd = np.full((H, W), np.inf, np.float32); idx = v[ins] * W + u[ins]
    np.minimum.at(gtd.reshape(-1), idx, z[ins].astype(np.float32))
    gtd[~np.isfinite(gtd)] = np.nan; save("gt", stem, gtd)
    save("fvert", stem, f)
    np.save(MAPS / "faceid" / f"{stem}.npy", poly) if (MAPS / "faceid").mkdir(parents=True, exist_ok=True) is None else None
    rec["gt_px"] = int(np.isfinite(gtd).sum()); rec["A_px"] = int(A.sum()); report["views"][stem] = rec
    print(stem, rec, flush=True)

# ---- point sets (local frame)
if not ARGS.points:
    stems = []
xyz, rgb, _ = col.read_points3D_binary(str(SCENE / "sparse/0/points3D.bin"))
np.savez(PTS / "sfm.npz", xyz=xyz.astype(np.float32), rgb=rgb.astype(np.uint8))
als = np.load(S1 / "inputs/als_points.npz"); dzL = V2CFG["registration"]["L_dz_m"]
P = als["xyz_local"].astype(np.float64).copy(); P[:, 2] += dzL
inside = np.array([main_ring.covers(Point(x, y)) for x, y in P[:, :2]])
gray = np.full((len(P), 3), 128, np.uint8)
np.savez(PTS / "prior_L_N.npz", xyz=P.astype(np.float32), rgb=gray)
PB = P.copy(); PB[inside, 2] += 1.0
np.savez(PTS / "prior_L_B.npz", xyz=PB.astype(np.float32), rgb=gray, raised=inside)
for key, name in [("M_N", "M_nominal"), ("M_B", "M_biased_main_1m")]:
    p = S2 / "inputs/prior_pcd_crop" / name / "points3D.txt"   # rectangle-cropped mesh sampling (dense on the block)
    if not p.exists(): p = S2 / "inputs/prior_pcd" / name / "points3D.txt"
    report[f"prior_{key}_source"] = str(p)
    if p.exists():
        rows = [l.split() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]
        X = np.array([[float(r[1]), float(r[2]), float(r[3])] for r in rows], np.float32); Cc = np.array([[int(r[4]), int(r[5]), int(r[6])] for r in rows], np.uint8)
        inc = (X[:, 0] >= crop[0, 0]) & (X[:, 0] <= crop[1, 0]) & (X[:, 1] >= crop[0, 1]) & (X[:, 1] <= crop[1, 1])
        np.savez(PTS / f"prior_{key}.npz", xyz=X[inc], rgb=Cc[inc]); report[f"prior_{key}_points"] = int(inc.sum())
    else:
        report[f"prior_{key}_points"] = "missing"
report["sfm_points"] = int(len(xyz)); report["prior_L_points"] = int(len(P)); report["L_raised_points"] = int(inside.sum())
rp = S2 / "inputs/prepare_report.json"
if rp.exists() and not ARGS.maps:
    old = json.loads(rp.read_text()); old.update({k: v for k, v in report.items() if k != "views"}); report = old
rp.write_text(json.dumps(report, indent=1))
print("done", {k: v for k, v in report.items() if k != "views"})
