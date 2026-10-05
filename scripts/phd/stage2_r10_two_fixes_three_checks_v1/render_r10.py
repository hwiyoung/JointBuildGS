"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 step 2 (jointbuildgs:geogs-official-db40c95-compat-v1, Open3D 0.19 = LoD2Depth):
LoD2 prior depth and triangle ids without the overlapping parts of party walls (fix 'na'), with the LoD2Depth ray setup of
r7 / r9 (render_r9.py).

  python render_r10.py      # mounts: /artifacts (ro), /source = GeoGS sources (LoD2Depth, ro), /p9 (ro), /p10 (rw)

For M_N and M_B, two meshes per view (15 views, full resolution):
  r9 mesh  -> check: r9's prior depth and triangle ids are reproduced (values exactly where both are finite)
  r10 mesh -> the r10 prior depth and ids
A ray 'hits a cut part' when its r9 triangle was replaced by the cut (meshes_r10: not among the untouched rows) and the r10
render does not hit a piece of the same polygon at the same depth (|t10 - t9| <= 1e-4 m): the r9 hit point lies in the
removed overlap. r10 prior depth = the r9 prior depth, except at those rays: there the r10 render (the face behind,
cropped to the airborne LiDAR rectangle by the hit XY, or nothing). r10 ids = r9 ids renumbered to the r10 mesh; on the
remaining part of a cut wall the r10 render's piece (same polygon, same depth); at the cut rays the r10 render.
Writes /p10/stage1/ids/<setting>/<view>.npz (tri int32 = row of the r10 mesh, -1 none), /p10/stage1/prior/<setting>/raw_depth/
<view>.npy (float32) and /p10/stage1/ids/render_check.json."""
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
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
P9 = Path("/p9/stage1"); P10 = Path("/p10/stage1")
RECT = np.array(json.loads((S1 / "inputs/lod2_polygons.json").read_text())["als_crop_local_xy"], float)
cams = load_cameras(str(SPARSE / "cameras.txt"))
imgs = {im.name: im for im in load_images(str(SPARSE / "images.txt")).values()}
names = sorted(x.name for x in (SCENE / "images").iterdir() if x.suffix.lower() == ".jpg")
TOL_T = 1e-4


def cast(scene, im, cam):   # render_r9.cast
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
    return np.where(hit, prim.astype(np.int64), -1), np.where(ok, t, np.nan).astype(np.float32), np.where(hit, t, np.nan)


report = {"open3d": o3d.__version__, "t_tolerance_m": TOL_T, "settings": {}}
for setting in ("M_N", "M_B"):
    m9 = np.load(P9 / "meshes" / f"{setting}.npz"); m10 = np.load(P10 / "meshes" / f"{setting}.npz")
    sc9 = create_mesh_scene(m9["V"], [list(f) for f in m9["F"]])
    sc10 = create_mesh_scene(m10["V"], [list(f) for f in m10["F"]])
    k10 = m10["kept_from_r9"]
    map9 = np.full(len(m9["F"]), -1, np.int64); map9[k10[k10 >= 0]] = np.nonzero(k10 >= 0)[0]
    touched9 = map9 < 0                                        # r9 rows replaced by the cut
    poly9 = m9["tri_poly"].astype(np.int64); poly10 = m10["tri_poly"].astype(np.int64)
    (P10 / "ids" / setting).mkdir(parents=True, exist_ok=True); (P10 / "prior" / setting / "raw_depth").mkdir(parents=True, exist_ok=True)
    rows = []
    for n in names:
        t0 = time.time()
        im = imgs[n]; cam = cams[im.camera_id]; stem = Path(n).stem
        tri9s = np.load(P9 / "ids" / setting / f"{stem}.npz")["tri"].astype(np.int64)
        Pr9 = np.load(P9 / "prior" / setting / "raw_depth" / f"{stem}.npy")
        tri9r, P9r, t9 = cast(sc9, im, cam)
        tri10r, P10r, t10 = cast(sc10, im, cam)
        on_touched = (tri9s >= 0) & touched9[np.maximum(tri9s, 0)]
        same_piece = on_touched & (tri10r >= 0) & (poly10[np.maximum(tri10r, 0)] == poly9[np.maximum(tri9s, 0)]) & \
            np.isfinite(t9) & np.isfinite(t10) & (np.abs(t10 - t9) <= TOL_T)
        cut_ray = on_touched & ~same_piece
        Pn = np.where(cut_ray, P10r, Pr9).astype(np.float32)
        ids = np.where(tri9s >= 0, map9[np.maximum(tri9s, 0)], -1)
        ids = np.where(on_touched, tri10r, ids)
        np.savez_compressed(P10 / "ids" / setting / f"{stem}.npz", tri=ids.astype(np.int32))
        np.save(P10 / "prior" / setting / "raw_depth" / f"{stem}.npy", Pn)
        both = np.isfinite(Pr9) & np.isfinite(P9r)
        sg = cut_ray & np.isfinite(Pr9)
        oth = ~on_touched
        changed = (np.isfinite(Pr9) != np.isfinite(Pn)) | (np.isfinite(Pr9) & np.isfinite(Pn) & (Pr9 != Pn))
        r = dict(view=stem,
                 r9_reproduced=dict(finite_pattern_differs_px=int((np.isfinite(Pr9) != np.isfinite(P9r)).sum()),
                                    max_abs_depth_diff_m=float(np.abs(Pr9[both] - P9r[both]).max()) if both.any() else 0.0,
                                    ids_differ_px=int((tri9s != tri9r).sum()),
                                    ids_differ_other_polygon_px=int((np.where(tri9s >= 0, poly9[np.maximum(tri9s, 0)], -1) != np.where(tri9r >= 0, poly9[np.maximum(tri9r, 0)], -1)).sum())),
                 r10_render_off_touched=dict(ids_differ_px=int((tri10r[oth] != ids[oth]).sum()),
                                             finite_pattern_differs_px=int((np.isfinite(P10r[oth]) != np.isfinite(Pr9[oth])).sum())),
                 rays_on_touched_triangles=int(on_touched.sum()), rays_on_remaining_part=int(same_piece.sum()),
                 cut_rays=int(cut_ray.sum()), cut_rays_target=None, r9_prior_px_on_cut=int(sg.sum()),
                 those_in_r10=dict(no_prior=int((sg & ~np.isfinite(Pn)).sum()), other_face=int((sg & np.isfinite(Pn)).sum()),
                                   new_prior_px=int((cut_ray & ~np.isfinite(Pr9) & np.isfinite(Pn)).sum())),
                 prior_px_r9=int(np.isfinite(Pr9).sum()), prior_px_r10=int(np.isfinite(Pn).sum()),
                 changed_px=int(changed.sum()), changed_px_off_cut_rays=int((changed & ~cut_ray).sum()),
                 ids_reference_valid=bool((ids[ids >= 0] < len(m10["F"])).all()),
                 remaining_part_ids_same_polygon=bool((poly10[np.maximum(ids[same_piece], 0)] == poly9[np.maximum(tri9s[same_piece], 0)]).all()))
        r["seconds"] = round(time.time() - t0, 1)
        rows.append(r); print(setting, json.dumps(r), flush=True)
    report["settings"][setting] = rows
    report[f"{setting}_r9_values_reproduced"] = all(r["r9_reproduced"]["max_abs_depth_diff_m"] == 0.0 for r in rows)
    report[f"{setting}_r9_ids_differ_px"] = sum(r["r9_reproduced"]["ids_differ_px"] for r in rows)
    report[f"{setting}_r9_ids_differ_other_polygon_px"] = sum(r["r9_reproduced"]["ids_differ_other_polygon_px"] for r in rows)
    report[f"{setting}_r9_finite_pattern_differs_px"] = sum(r["r9_reproduced"]["finite_pattern_differs_px"] for r in rows)
    report[f"{setting}_cut_rays"] = sum(r["cut_rays"] for r in rows)
    report[f"{setting}_r9_prior_px_on_cut"] = sum(r["r9_prior_px_on_cut"] for r in rows)
    report[f"{setting}_changed_only_on_cut_rays"] = all(r["changed_px_off_cut_rays"] == 0 for r in rows)
(P10 / "ids/render_check.json").write_text(json.dumps(report, indent=1))
print({k: v for k, v in report.items() if k != "settings"})
