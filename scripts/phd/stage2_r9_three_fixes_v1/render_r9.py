"""PHD-STAGE2-R9-THREE-FIXES-v1 step 2 (jointbuildgs:geogs-official-db40c95-compat-v1, Open3D 0.19 = LoD2Depth): LoD2
prior depth and triangle ids without the bottom faces (fix 'ra'), with the exact LoD2Depth ray setup of r7 render.py.

  python render_r9.py      # mounts: /artifacts (ro), /source = GeoGS sources (LoD2Depth, ro), /r7 (ro), /p9 (rw)

For M_N and M_B, two meshes per view (15 views, full resolution):
  r8 mesh (r7 stage1/meshes, bottom faces included)  -> checks: r7's triangle ids and the stage-2 prior depth the r8
     trainings read (inputs/maps/prior_<setting>/raw_depth) are reproduced (values exactly; the finite pattern up to a
     few pixels on the crop rectangle's edge, where prepare_stage2_inputs computed the hit XY in float32)
  r9 mesh (/p9/stage1/meshes, bottom faces removed)  -> the r9 prior depth and triangle ids
r9 prior depth = the r8 prior depth, except at the pixels whose ray hit a bottom face in r8: there the r9 render (the
face behind, cropped to the airborne LiDAR rectangle by the hit XY, or nothing). r9 ids = r7's ids renumbered to the r9
mesh, with the r9 render at those pixels. Every other pixel is r8's, so differences downstream come from the bottom faces.
Writes /p9/stage1/ids/<setting>/<view>.npz (tri int32 = row of the r9 mesh, -1 none), /p9/stage1/prior/<setting>/raw_depth/
<view>.npy (float32) and /p9/stage1/ids/render_check.json (per view: reproduction of r8, pixels that saw a bottom face in
r8 and what they see in r9)."""
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
R7 = Path("/r7"); P9 = Path("/p9/stage1")
RECT = np.array(json.loads((S1 / "inputs/lod2_polygons.json").read_text())["als_crop_local_xy"], float)
PZ = np.load(S1 / "inputs/lod2_polygons.npz")
cams = load_cameras(str(SPARSE / "cameras.txt"))
imgs = {im.name: im for im in load_images(str(SPARSE / "images.txt")).values()}
names = sorted(x.name for x in (SCENE / "images").iterdir() if x.suffix.lower() == ".jpg")


def cast(scene, im, cam):
    rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(intrinsic_matrix=get_camera_intrinsics(cam), extrinsic_matrix=get_camera_extrinsics(im),
                                                              width_px=cam.width, height_px=cam.height)
    res = scene.cast_rays(rays)
    prim = res["primitive_ids"].numpy(); t = res["t_hit"].numpy()
    hit = prim != o3d.t.geometry.RaycastingScene.INVALID_ID
    K = get_camera_intrinsics(cam); E = get_camera_extrinsics(im)
    Rm = np.asarray(E)[:3, :3]; tv = np.asarray(E)[:3, 3]; Cc = -Rm.T @ tv
    fx, fy, cx, cy = K[0][0], K[1][1], K[0][2], K[1][2]
    xn = ((np.arange(cam.width) + 0.5 - cx) / fx)[None, :]; yn = ((np.arange(cam.height) + 0.5 - cy) / fy)[:, None]
    dx = Rm[0, 0] * xn + Rm[1, 0] * yn + Rm[2, 0]; dy = Rm[0, 1] * xn + Rm[1, 1] * yn + Rm[2, 1]
    X = Cc[0] + t * dx; Y = Cc[1] + t * dy
    ok = hit & np.isfinite(t) & (X >= RECT[0, 0]) & (X <= RECT[1, 0]) & (Y >= RECT[0, 1]) & (Y <= RECT[1, 1])
    return np.where(hit, prim.astype(np.int64), -1), np.where(ok, t, np.nan).astype(np.float32)


report = {"open3d": o3d.__version__, "settings": {}}
nl = len(PZ["labels"])
for setting in ("M_N", "M_B"):
    m8 = np.load(R7 / "stage1/meshes" / f"{setting}.npz"); m9 = np.load(P9 / "meshes" / f"{setting}.npz")
    ground8 = np.zeros(len(m8["F"]), bool); ground8[:nl] = np.isin(PZ["labels"].astype(str), ["GroundSurface", "ClosureSurface"])
    sc8 = create_mesh_scene(m8["V"], [list(f) for f in m8["F"]])
    sc9 = create_mesh_scene(m9["V"], [list(f) for f in m9["F"]])
    map89 = np.full(len(m8["F"]), -1, np.int64); map89[m9["kept_from_r8"]] = np.arange(len(m9["F"]))
    (P9 / "ids" / setting).mkdir(parents=True, exist_ok=True); (P9 / "prior" / setting / "raw_depth").mkdir(parents=True, exist_ok=True)
    rows = []
    for n in names:
        t0 = time.time()
        im = imgs[n]; cam = cams[im.camera_id]; stem = Path(n).stem
        tri8, P8_ = cast(sc8, im, cam)
        tri9, P9r = cast(sc9, im, cam)
        s2 = np.load(S2 / f"inputs/maps/prior_{setting}/raw_depth/{stem}.npy")
        ids7 = np.load(R7 / "stage1/ids" / setting / f"{stem}.npz")["tri"].astype(np.int64)
        both = np.isfinite(s2) & np.isfinite(P8_)
        bottom_ray = (tri8 >= 0) & ground8[np.maximum(tri8, 0)]          # the ray hit a bottom face in r8
        sg_prior = bottom_ray & np.isfinite(s2)
        P9_ = np.where(bottom_ray, P9r, s2).astype(np.float32)
        ids9 = np.where(bottom_ray, tri9, np.where(ids7 >= 0, map89[np.maximum(ids7, 0)], -1))
        np.savez_compressed(P9 / "ids" / setting / f"{stem}.npz", tri=ids9.astype(np.int32))
        np.save(P9 / "prior" / setting / "raw_depth" / f"{stem}.npy", P9_)
        nb = ~bottom_ray
        changed = (np.isfinite(s2) != np.isfinite(P9_)) | (np.isfinite(s2) & np.isfinite(P9_) & (s2 != P9_))
        r = dict(view=stem,
                 r8_reproduced=dict(finite_pattern_differs_px=int((np.isfinite(s2) != np.isfinite(P8_)).sum()),
                                    max_abs_depth_diff_m=float(np.abs(s2[both] - P8_[both]).max()) if both.any() else 0.0,
                                    ids_equal_r7=bool(np.array_equal(ids7, tri8))),
                 r9_render_off_bottom_rays=dict(ids_equal_renumbered_r7=bool(np.array_equal(tri9[nb], np.where(ids7[nb] >= 0, map89[np.maximum(ids7[nb], 0)], -1))),
                                                ids_differ_px=int((tri9[nb] != np.where(ids7[nb] >= 0, map89[np.maximum(ids7[nb], 0)], -1)).sum()),
                                                ids_differ_other_polygon_px=int((np.where(tri9[nb] >= 0, m9["tri_poly"][np.maximum(tri9[nb], 0)], -1)
                                                                                 != np.where(ids7[nb] >= 0, m8["tri_poly"][np.maximum(ids7[nb], 0)], -1)).sum()),
                                                finite_pattern_differs_px=int((np.isfinite(P9r[nb]) != np.isfinite(s2[nb])).sum())),
                 prior_px_r8=int(np.isfinite(s2).sum()), prior_px_r9=int(np.isfinite(P9_).sum()),
                 bottom_rays=int(bottom_ray.sum()), r8_prior_px_on_bottom_faces=int(sg_prior.sum()),
                 those_in_r9=dict(no_prior=int((sg_prior & ~np.isfinite(P9_)).sum()), other_face=int((sg_prior & np.isfinite(P9_)).sum()),
                                  new_prior_px=int((bottom_ray & ~np.isfinite(s2) & np.isfinite(P9_)).sum())),
                 changed_px=int(changed.sum()), changed_px_off_bottom_rays=int((changed & nb).sum()),
                 r9_ids_reference_no_removed_triangle=bool((ids9[ids9 >= 0] < len(m9["F"])).all()))
        r["seconds"] = round(time.time() - t0, 1)
        rows.append(r); print(setting, json.dumps(r), flush=True)
    report["settings"][setting] = rows
    report[f"{setting}_r8_values_and_ids_reproduced"] = all(r["r8_reproduced"]["max_abs_depth_diff_m"] == 0.0 and r["r8_reproduced"]["ids_equal_r7"] for r in rows)
    report[f"{setting}_r8_finite_pattern_differs_px"] = sum(r["r8_reproduced"]["finite_pattern_differs_px"] for r in rows)
    report[f"{setting}_changed_only_on_bottom_rays"] = all(r["changed_px_off_bottom_rays"] == 0 for r in rows)
(P9 / "ids/render_check.json").write_text(json.dumps(report, indent=1))
print({k: v for k, v in report.items() if k != "settings"})
