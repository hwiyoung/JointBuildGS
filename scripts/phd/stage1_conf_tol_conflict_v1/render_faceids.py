"""Step 3 (GeoGS runtime image, Open3D as used by LoD2Depth): per-view LoD2 polygon-id maps
from the nominal recovered mesh, using the exact ray generation of LoD2Depth/raycasting.py.
Also verifies that this ray setup reproduces the official main.py depth of the same mesh.

Writes: inputs/faceid/{view}.npy (int32 polygon index, -1 = no building), provenance/faceid_render.json
"""
import json
import sys

import numpy as np
import open3d as o3d

import common as cm

sys.path.insert(0, "/source/LoD2Depth")
from camera_loader import get_camera_extrinsics, get_camera_intrinsics, load_cameras, load_images  # noqa: E402
from raycasting import create_mesh_scene  # noqa: E402

rc = cm.Receipt("render_faceids", {"open3d": o3d.__version__})
z = np.load(cm.INP / "lod2_polygons.npz")
V = z["vertices_local"]
F = z["faces"]
poly_of_tri = z["poly_of_tri"]
scene = create_mesh_scene(V, [list(f) for f in F])
cams = load_cameras(str(cm.SPARSE_TXT / "cameras.txt"))
imgs = load_images(str(cm.SPARSE_TXT / "images.txt"))
by_name = {im.name: im for im in imgs.values()}
out = cm.INP / "faceid"
out.mkdir(parents=True, exist_ok=True)
official = cm.INP / "prior_render/M_nominal_recovered/lod2_prior/raw_depth"
checks = []
for v in cm.load_views():
    im = by_name[v["name"]]
    cam = cams[im.camera_id]
    K = get_camera_intrinsics(cam)
    E = get_camera_extrinsics(im)
    rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(intrinsic_matrix=K, extrinsic_matrix=E,
                                                              width_px=cam.width, height_px=cam.height)
    res = scene.cast_rays(rays)
    prim = res["primitive_ids"].numpy()
    hit = prim != o3d.t.geometry.RaycastingScene.INVALID_ID
    poly = np.full(prim.shape, -1, np.int32)
    poly[hit] = poly_of_tri[prim[hit].astype(np.int64)]
    np.save(out / f"{v['stem']}.npy", poly)
    rec = {"view": v["stem"], "hit_fraction": float(hit.mean())}
    p = official / f"{v['stem']}.npy"
    if p.exists():
        d_off = np.load(p)
        d_me = res["t_hit"].numpy()
        ok_off = np.isfinite(d_off)
        rec["official_hit_fraction"] = float(ok_off.mean())
        rec["hit_mask_disagreement_px"] = int((ok_off != hit).sum())
        both = ok_off & hit
        rec["max_abs_depth_diff_m"] = float(np.abs(d_off[both] - d_me[both]).max()) if both.any() else None
    checks.append(rec)
    print(json.dumps(rec))
cm.write_json(cm.PROV / "faceid_render.json", {"open3d": o3d.__version__, "views": checks,
                                                 "note": "same create_rays_pinhole call as LoD2Depth/raycasting.py"})
rc.write()
