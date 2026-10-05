"""Step 3 (GeoGS runtime image): polygon-id maps of the registered nominal LoD2 mesh with the exact LoD2Depth ray setup."""
import json
import sys

import numpy as np
import open3d as o3d

sys.path.insert(0, "/source/LoD2Depth")
from camera_loader import get_camera_extrinsics, get_camera_intrinsics, load_cameras, load_images  # noqa: E402
from raycasting import create_mesh_scene  # noqa: E402
from pathlib import Path  # noqa: E402

ART = Path("/artifacts/JointBuildGS")
CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
V2 = Path("/v2")
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
cams = load_cameras(str(SPARSE / "cameras.txt"))
imgs = {im.name: im for im in load_images(str(SPARSE / "images.txt")).values()}
names = sorted(x.name for x in (SCENE / "images").iterdir() if x.suffix.lower() == ".jpg")
allrec = {}
for mesh, sub, render in [("lod2_v2_nominal_local.npz", "faceid", "M_nominal"), ("lod2_v2_biased_small_local.npz", "faceid_biased_small", "M_biased_small"),
                          ("lod2_v2_biased_main_local.npz", "faceid_biased_main", "M_biased_main")]:
    z = np.load(V2 / "inputs_v2" / mesh)
    scene = create_mesh_scene(z["vertices_local"], [list(f) for f in z["faces"]])
    pot = z["poly_of_tri"]
    out = V2 / "inputs_v2" / sub
    out.mkdir(parents=True, exist_ok=True)
    official = V2 / f"inputs_v2/prior_render/{render}/lod2_prior/raw_depth"
    rec = []
    for n in names:
        im = imgs[n]
        cam = cams[im.camera_id]
        rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(intrinsic_matrix=get_camera_intrinsics(cam), extrinsic_matrix=get_camera_extrinsics(im), width_px=cam.width, height_px=cam.height)
        res = scene.cast_rays(rays)
        prim = res["primitive_ids"].numpy()
        hit = prim != o3d.t.geometry.RaycastingScene.INVALID_ID
        poly = np.full(prim.shape, -1, np.int32)
        poly[hit] = pot[prim[hit].astype(np.int64)]
        stem = Path(n).stem
        np.save(out / f"{stem}.npy", poly)
        r = {"view": stem, "hit_fraction": float(hit.mean())}
        p = official / f"{stem}.npy"
        if p.exists():
            d = np.load(p)
            both = np.isfinite(d) & hit
            r["max_abs_depth_diff_vs_official_m"] = float(np.abs(d[both] - res["t_hit"].numpy()[both]).max()) if both.any() else None
            r["hit_mask_disagreement_px"] = int((np.isfinite(d) != hit).sum())
        rec.append(r)
        print(sub, r, flush=True)
    allrec[sub] = rec
(V2 / "inputs_v2/faceid_v2.json").write_text(json.dumps({"open3d": o3d.__version__, "views": allrec["faceid"], "biased": {k: v for k, v in allrec.items() if k != "faceid"}}, indent=1))
