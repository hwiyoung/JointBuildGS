"""PHD-STAGE2-PROPAGATION-PREMEASURE-v1 step 2 (GeoGS runtime image, Open3D 0.19 as used by LoD2Depth): per-view
triangle-id maps of each setting's prior mesh with the exact ray setup of LoD2Depth (create_rays_pinhole, the same
sparse_txt cameras), and a check that the hit depth reproduces the prior depth map the stage-2 runs read.

  python render_ids.py     # mounts: /artifacts/JointBuildGS (ro), /source = GeoGS sources (ro), /out (rw)

Writes /out/ids/<setting>/<view>.npz (tri int32, -1 = no hit) and /out/ids/render_check.json."""
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
V2 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-VERIFY-v2"
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
OFFICIAL = {"M_N": V2 / "inputs_v2/prior_render/M_nominal/lod2_prior/raw_depth",
            "M_B": S2 / "inputs/prior_render/M_biased_main_1m/lod2_prior/raw_depth",
            "L_N": V2 / "inputs_v2/prior_render/L_nominal/lod2_prior/raw_depth",
            "L_B": V2 / "inputs_v2/prior_render/L_biased_main/lod2_prior/raw_depth"}
STAGE2 = {k: S2 / f"inputs/maps/prior_{k}/raw_depth" for k in OFFICIAL}
OUT = Path("/out/ids")
cams = load_cameras(str(SPARSE / "cameras.txt"))
imgs = {im.name: im for im in load_images(str(SPARSE / "images.txt")).values()}
names = sorted(x.name for x in (SCENE / "images").iterdir() if x.suffix.lower() == ".jpg")
report = {"open3d": o3d.__version__, "settings": {}}
for setting in ("M_N", "M_B", "L_N", "L_B"):
    z = np.load(Path("/out/surfaces") / setting / "mesh.npz")
    scene = create_mesh_scene(z["V"], [list(f) for f in z["F"]])
    out = OUT / setting
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for n in names:
        t0 = time.time()
        im = imgs[n]
        cam = cams[im.camera_id]
        rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(intrinsic_matrix=get_camera_intrinsics(cam), extrinsic_matrix=get_camera_extrinsics(im),
                                                                  width_px=cam.width, height_px=cam.height)
        res = scene.cast_rays(rays)
        prim = res["primitive_ids"].numpy()
        hit = prim != o3d.t.geometry.RaycastingScene.INVALID_ID
        tri = np.where(hit, prim.astype(np.int64), -1).astype(np.int32)
        stem = Path(n).stem
        np.savez_compressed(out / f"{stem}.npz", tri=tri)
        t = res["t_hit"].numpy()
        d = np.load(OFFICIAL[setting] / f"{stem}.npy")
        ok = np.isfinite(d) & (d > 0) & (d < 1e6)
        both = ok & hit
        s2 = np.load(STAGE2[setting] / f"{stem}.npy")
        s2ok = np.isfinite(s2)
        r = dict(view=stem, hit_px=int(hit.sum()), official_px=int(ok.sum()), hit_mask_disagreement_px=int((ok != hit).sum()),
                 max_abs_depth_diff_vs_official_m=float(np.abs(d[both] - t[both]).max()) if both.any() else None,
                 stage2_px=int(s2ok.sum()), stage2_without_hit_px=int((s2ok & ~hit).sum()),
                 max_abs_depth_diff_vs_stage2_m=float(np.abs(s2[s2ok & hit] - t[s2ok & hit]).max()) if (s2ok & hit).any() else None,
                 seconds=round(time.time() - t0, 1))
        rows.append(r)
        print(setting, r, flush=True)
    report["settings"][setting] = rows
(OUT / "render_check.json").write_text(json.dumps(report, indent=1))
