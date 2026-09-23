"""Build the per-condition GeoGS scene directories for stage 2 (run in the official GeoGS image; needs plyfile).

runs/<cond>/scene/
  images -> native example images (symlink, container path)
  sparse/0/{cameras.bin, images.bin}          copied from the native example
  sparse/0/points3D.ply + origin.npy          P/P0: prior points (crop) U SfM points; I: SfM only   (origin 1 = prior, 0 = image)
  jbgs_calibration.json                       source PINHOLE K at the training resolution (principal point restored)
  O conditions instead: sparse_lod/0 (official sampler output), lod2_prior, da3_prior, lod2_pcd.ply, no calibration file
runs/<cond>/condition.json                   everything the driver needs
inputs/maps/faces.json                        target roof / wall polygon ids for the read-outs
Symlink targets are container paths (/artifacts/JointBuildGS/..., /s2/...)."""
import json
import os
import shutil
from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement

ART = Path("/artifacts/JointBuildGS")
S2 = Path("/s2")
NATIVE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
V2 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-VERIFY-v2"
DIAG = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
RUNS = S2 / "runs"
PREP = json.loads((S2 / "inputs/prepare_report.json").read_text())
TAU_V = PREP["tau_v"]

CONDITIONS = {
    "P_L_N": dict(mode="P", prior="L", scene="N"), "P_L_B": dict(mode="P", prior="L", scene="B"),
    "P_M_N": dict(mode="P", prior="M", scene="N"), "P_M_B": dict(mode="P", prior="M", scene="B"),
    "P0_L_N": dict(mode="P0", prior="L", scene="N"), "P0_L_B": dict(mode="P0", prior="L", scene="B"),
    "P0_M_N": dict(mode="P0", prior="M", scene="N"), "P0_M_B": dict(mode="P0", prior="M", scene="B"),
    "O_M_N": dict(mode="O", prior="M", scene="N"), "O_M_B": dict(mode="O", prior="M", scene="B"),
    "I": dict(mode="I", prior=None, scene="N"),
}
PRIOR_RENDER = {("M", "N"): f"{V2}/inputs_v2/prior_render/M_nominal/lod2_prior",
                ("M", "B"): "/s2/inputs/prior_render/M_biased_main_1m/lod2_prior"}
O_SAMPLER = {"N": "M_nominal", "B": "M_biased_main_1m"}


def store_ply(path, xyz, rgb):
    dtype = [('x', 'f4'), ('y', 'f4'), ('z', 'f4'), ('nx', 'f4'), ('ny', 'f4'), ('nz', 'f4'),
             ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]
    el = np.empty(xyz.shape[0], dtype=dtype)
    attributes = np.concatenate((xyz.astype(np.float32), np.zeros_like(xyz, dtype=np.float32), rgb.astype(np.uint8)), axis=1)
    el[:] = list(map(tuple, attributes))
    PlyData([PlyElement.describe(el, 'vertex')]).write(str(path))


def symlink(target, link):
    link = Path(link)
    if link.is_symlink() or link.exists():
        if link.is_dir() and not link.is_symlink():
            shutil.rmtree(link)
        else:
            link.unlink()
    os.symlink(str(target), str(link))


# ---- faces.json (target roof faces = region code 1, target walls = code 2)
PZ = np.load(V2 / "inputs_v2/lod2_v2_nominal_local.npz")
code = PZ["poly_region_code"]
faces = {"roof": [int(i) for i in np.where(code == 1)[0]], "wall": [int(i) for i in np.where(code == 2)[0]],
         "codes": {"1": "target roof", "2": "target wall", "3": "ground", "4": "other building"}}
(S2 / "inputs/maps/faces.json").write_text(json.dumps(faces, indent=1))
print("faces", faces["roof"], "walls", len(faces["wall"]))

# ---- calibration at the training resolution (GeoGS -r -1 rescales 5644-wide images to 1600)
cams = {}
for l in (DIAG / "conditions/B+1.0/scene/sparse_txt/cameras.txt").read_text().splitlines():
    if l.strip() and not l.startswith("#"):
        t = l.split(); cams[int(t[0])] = dict(model=t[1], W=int(t[2]), H=int(t[3]), p=[float(x) for x in t[4:]])
imgs = {}
for l in (DIAG / "conditions/B+1.0/scene/sparse_txt/images.txt").read_text().splitlines():
    t = l.split()
    if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
        imgs[Path(t[9]).stem] = int(t[8])
calib = {"schema": "jointbuildgs.geogs.source_calibration.v1", "images": {}, "scientific_verdict": None,
         "policy": "Stage-2: PINHOLE K of the stage-1 maps rescaled to the GeoGS training resolution (width 1600); "
                   "adapter restores the principal point in the native rasterizer projection.",
         "source": str(DIAG / "conditions/B+1.0/scene/sparse_txt/cameras.txt")}
for stem, cid in imgs.items():
    c = cams[cid]; assert c["model"] == "PINHOLE", c
    W0, H0 = c["W"], c["H"]
    down = W0 / 1600.0
    W1, H1 = int(W0 / down), int(H0 / down)
    sx, sy = W1 / W0, H1 / H0
    fx, fy, cx, cy = c["p"]
    calib["images"][stem] = {"width": W1, "height": H1, "K": [[fx * sx, 0.0, cx * sx], [0.0, fy * sy, cy * sy], [0.0, 0.0, 1.0]]}
calib["train_resolution"] = [W1, H1]
print("calibration", W1, H1, list(calib["images"].values())[0]["K"])

# ---- point sets
pts = {k: dict(np.load(S2 / f"inputs/points/{k}.npz")) for k in ["sfm", "prior_L_N", "prior_L_B", "prior_M_N", "prior_M_B"]}
# M mesh samples (rectangle-cropped sampler, ~292k) are subsampled to the L count (120,333) so both priors start with the
# same number of prior disks; uniform random subsampling of an area-uniform sample stays area-uniform. Seed 0, recorded below.
n_L = len(pts["prior_L_N"]["xyz"]); subsample = {}
for k in ["prior_M_N", "prior_M_B"]:
    n = len(pts[k]["xyz"]); subsample[k] = {"available": int(n), "used": int(min(n, n_L))}
    if n > n_L:
        sel = np.sort(np.random.RandomState(0).choice(n, n_L, replace=False))
        pts[k] = {kk: vv[sel] for kk, vv in pts[k].items()}
summary = {"prior_subsample": subsample}
for cond, c in CONDITIONS.items():
    scene = RUNS / cond / "scene"
    scene.mkdir(parents=True, exist_ok=True)
    symlink(f"{NATIVE}/images", scene / "images")
    sp = scene / "sparse/0"; sp.mkdir(parents=True, exist_ok=True)
    for f in ["cameras.bin", "images.bin"]:
        shutil.copy2(NATIVE / "sparse/0" / f, sp / f)
    info = dict(condition=cond, **c, tau_v=(TAU_V[c["prior"]] if c["prior"] else None), train_resolution=[W1, H1])
    if c["mode"] in ("P", "P0", "I"):
        parts, origins = [pts["sfm"]], [np.zeros(len(pts["sfm"]["xyz"]), np.int8)]
        if c["mode"] != "I":
            pk = f"prior_{c['prior']}_{c['scene']}"
            parts.append(pts[pk]); origins.append(np.ones(len(pts[pk]["xyz"]), np.int8))
            info.update(prior_set=pk, tau_set=f"tau_{c['prior']}", prior_points=int(len(pts[pk]["xyz"])), prior_subsample=subsample.get(pk))
        xyz = np.concatenate([p["xyz"] for p in parts]); rgb = np.concatenate([p["rgb"] for p in parts]); origin = np.concatenate(origins)
        store_ply(sp / "points3D.ply", xyz, rgb); np.save(sp / "origin.npy", origin)
        (scene / "jbgs_calibration.json").write_text(json.dumps(calib, indent=1))
        info.update(init_points=int(len(xyz)), sfm_points=int(len(pts["sfm"]["xyz"])), origin_path=f"/s2/runs/{cond}/scene/sparse/0/origin.npy",
                    calibration=True)
    else:  # official GeoGS, native conventions, registered prior arrays
        sl = scene / "sparse_lod/0"; sl.mkdir(parents=True, exist_ok=True)
        src = S2 / "inputs/prior_pcd" / O_SAMPLER[c["scene"]]
        shutil.copy2(DIAG / "conditions/B+1.0/scene/sparse_txt/cameras.txt", sl / "cameras.txt")
        shutil.copy2(src / "images.txt", sl / "images.txt"); shutil.copy2(src / "points3D.txt", sl / "points3D.txt")
        rows = [l.split() for l in (src / "points3D.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
        xyz = np.array([[float(r[1]), float(r[2]), float(r[3])] for r in rows], np.float32)
        rgb = np.array([[int(r[4]), int(r[5]), int(r[6])] for r in rows], np.uint8)
        store_ply(sl / "points3D.ply", xyz, rgb)
        symlink(PRIOR_RENDER[("M", c["scene"])], scene / "lod2_prior")
        symlink(f"{NATIVE}/da3_prior", scene / "da3_prior")
        symlink(f"/s2/inputs/o_prior/M_{c['scene']}/lod2_pcd.ply", scene / "lod2_pcd.ply")
        info.update(init_points=int(len(xyz)), lod2_prior=PRIOR_RENDER[("M", c["scene"])], lod2_pcd=f"/s2/inputs/o_prior/M_{c['scene']}/lod2_pcd.ply",
                    calibration=False)
    (RUNS / cond / "condition.json").write_text(json.dumps(info, indent=1))
    summary[cond] = {k: info[k] for k in info if k in ("init_points", "prior_points", "prior_set", "tau_v")}
    print(cond, summary[cond])
(RUNS / "conditions_summary.json").write_text(json.dumps(summary, indent=1))
