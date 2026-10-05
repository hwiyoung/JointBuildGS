"""PHD-STAGE2-R7-PROPAGATION-v1 step 2 (GeoGS runtime image, Open3D 0.19 as LoD2Depth): per-view triangle-id and depth
renders of every setting's mesh with the exact LoD2Depth ray setup; the depth must reproduce the prior map the stage-2 runs
read (M_N, M_B, L_N, L_B). For the optional M_C scene this render is its prior depth (cropped like prepare_stage2_inputs:
LoD2 to the airborne LiDAR rectangle by the XY of the hit point).

  python render.py      # mounts: /artifacts (ro), /source = GeoGS sources (ro), /p7 (rw)
Writes /p7/stage1/ids/<setting>/<view>.npz (tri int32, -1 = no hit), /p7/stage1/prior_M_C/<view>.npy (float32, NaN =
absent, full resolution) and /p7/stage1/ids/render_check.json."""
import json
import sys
import time
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, "/source/LoD2Depth")
from camera_loader import get_camera_extrinsics, get_camera_intrinsics, load_cameras, load_images  # noqa: E402
from raycasting import create_mesh_scene  # noqa: E402

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
STAGE2 = {k: S2 / f"inputs/maps/prior_{k}/raw_depth" for k in ("M_N", "M_B", "L_N", "L_B")}
OUT = Path("/p7/stage1")
RECT = np.array(json.loads((S1 / "inputs/lod2_polygons.json").read_text())["als_crop_local_xy"], float)
cams = load_cameras(str(SPARSE / "cameras.txt"))
imgs = {im.name: im for im in load_images(str(SPARSE / "images.txt")).values()}
names = sorted(x.name for x in (SCENE / "images").iterdir() if x.suffix.lower() == ".jpg")


report = {"open3d": o3d.__version__, "settings": {}}
for setting in ("M_N", "M_B", "M_C", "L_N", "L_B"):
    z = np.load(OUT / "meshes" / f"{setting}.npz")
    scene = create_mesh_scene(z["V"], [list(f) for f in z["F"]])
    (OUT / "ids" / setting).mkdir(parents=True, exist_ok=True)
    if setting == "M_C":
        (OUT / "prior_M_C").mkdir(parents=True, exist_ok=True)
    rows = []
    for n in names:
        t0 = time.time()
        im = imgs[n]; cam = cams[im.camera_id]
        rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(intrinsic_matrix=get_camera_intrinsics(cam), extrinsic_matrix=get_camera_extrinsics(im),
                                                                  width_px=cam.width, height_px=cam.height)
        res = scene.cast_rays(rays)
        prim = res["primitive_ids"].numpy(); t = res["t_hit"].numpy()
        hit = prim != o3d.t.geometry.RaycastingScene.INVALID_ID
        stem = Path(n).stem
        np.savez_compressed(OUT / "ids" / setting / f"{stem}.npz", tri=np.where(hit, prim.astype(np.int64), -1).astype(np.int32))
        r = dict(view=stem, hit_px=int(hit.sum()), seconds=None)
        if setting in STAGE2:
            s2 = np.load(STAGE2[setting] / f"{stem}.npy"); ok = np.isfinite(s2)
            r.update(stage2_px=int(ok.sum()), stage2_without_hit_px=int((ok & ~hit).sum()),
                     max_abs_depth_diff_vs_stage2_m=float(np.abs(s2[ok & hit] - t[ok & hit]).max()) if (ok & hit).any() else None)
        else:   # M_C: this render is the prior depth; crop to the rectangle like prepare_stage2_inputs.py (LoD2 sets)
            K = get_camera_intrinsics(cam); E = get_camera_extrinsics(im)
            Rm = np.asarray(E)[:3, :3]; tv = np.asarray(E)[:3, 3]; Cc = -Rm.T @ tv
            fx, fy, cx, cy = K[0][0], K[1][1], K[0][2], K[1][2]
            xn = ((np.arange(cam.width) + 0.5 - cx) / fx)[None, :]; yn = ((np.arange(cam.height) + 0.5 - cy) / fy)[:, None]
            dx = Rm[0, 0] * xn + Rm[1, 0] * yn + Rm[2, 0]; dy = Rm[0, 1] * xn + Rm[1, 1] * yn + Rm[2, 1]
            X = Cc[0] + t * dx; Y = Cc[1] + t * dy
            ok = hit & np.isfinite(t) & (X >= RECT[0, 0]) & (X <= RECT[1, 0]) & (Y >= RECT[0, 1]) & (Y <= RECT[1, 1])
            np.save(OUT / "prior_M_C" / f"{stem}.npy", np.where(ok, t, np.nan).astype(np.float32))
            r.update(prior_px=int(ok.sum()))
        r["seconds"] = round(time.time() - t0, 1)
        rows.append(r); print(setting, r, flush=True)
    report["settings"][setting] = rows
(OUT / "ids/render_check.json").write_text(json.dumps(report, indent=1))
