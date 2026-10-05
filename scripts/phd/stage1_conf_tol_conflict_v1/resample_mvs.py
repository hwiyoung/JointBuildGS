"""Step 4 (jointbuildgs:dev): confidence maps from the COLMAP geometric-consistency filtered
MVS depth (no prior used), resampled from the 1024x741 dense grid to the 5644x4082 view grid.
Depth: bilinear over valid neighbours; mask: nearest.  Also stores camera-Z MVS depth at full
resolution and world-frame MVS normals at native resolution.

Writes: out/conf/{view}_conf.npy|png, inputs/mvs_full/{view}_depth.npy,
        inputs/mvs_native/{view}_depth.npy|_normal_world.npy, provenance/mvs_resampling.json
"""
import json

import numpy as np

import common as cm

rc = cm.Receipt("resample_mvs")
(cm.OUT / "conf").mkdir(parents=True, exist_ok=True)
(cm.INP / "mvs_full").mkdir(parents=True, exist_ok=True)
(cm.INP / "mvs_native").mkdir(parents=True, exist_ok=True)
# undistorted dense camera (1400x1013) -> depth-map grid intrinsics as COLMAP rescales them
import struct


def read_cameras_bin(path):
    cams = {}
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            nparams = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}[model]
            params = struct.unpack("<" + "d" * nparams, f.read(8 * nparams))
            cams[cid] = {"model": model, "width": w, "height": h, "params": params}
    return cams


dense_cam = read_cameras_bin(cm.DENSE / "sparse/cameras.bin")[1]
assert dense_cam["model"] == 1  # PINHOLE
fx0, fy0, cx0, cy0 = dense_cam["params"]
W0, H0 = dense_cam["width"], dense_cam["height"]
views = cm.load_views()
records = []
supplied = cm.ART / cm.CFG["scene"]["supplied_lod2_depth_relative"]
consistency = sorted((cm.DENSE / "stereo/consistency_graphs").glob("*"))
for v in views:
    dpath = cm.DENSE / "stereo/depth_maps" / f"{v['name']}.geometric.bin"
    npath = cm.DENSE / "stereo/normal_maps" / f"{v['name']}.geometric.bin"
    d = cm.read_colmap_array(dpath)
    n = cm.read_colmap_array(npath)
    h, w = d.shape
    sx, sy = w / W0, h / H0
    fx, fy, cx, cy = fx0 * sx, fy0 * sy, cx0 * sx, cy0 * sy
    valid = (d > 0) & np.isfinite(d)
    # full-res pixel centres -> normalised coords -> depth-grid continuous coords
    u_n, v_n = cm.pixel_dirs(v)
    gu = fx * u_n + cx - 0.5
    gv = fy * v_n + cy - 0.5
    # nearest mask
    iu = np.clip(np.rint(gu).astype(int), 0, w - 1)
    iv = np.clip(np.rint(gv).astype(int), 0, h - 1)
    conf = valid[iv[:, None], iu[None, :]].astype(np.uint8)
    # bilinear depth over valid neighbours
    u0 = np.clip(np.floor(gu).astype(int), 0, w - 1)
    v0 = np.clip(np.floor(gv).astype(int), 0, h - 1)
    u1 = np.clip(u0 + 1, 0, w - 1)
    v1 = np.clip(v0 + 1, 0, h - 1)
    au = np.clip(gu - u0, 0, 1).astype(np.float32)
    av = np.clip(gv - v0, 0, 1).astype(np.float32)
    dv = np.where(valid, d, 0).astype(np.float32)
    vf = valid.astype(np.float32)
    num = np.zeros((v["H"], v["W"]), np.float32)
    den = np.zeros((v["H"], v["W"]), np.float32)
    for (vi, ui, wv, wu) in ((v0, u0, 1 - av, 1 - au), (v0, u1, 1 - av, au), (v1, u0, av, 1 - au), (v1, u1, av, au)):
        wgt = wv[:, None] * wu[None, :]
        num += wgt * dv[vi[:, None], ui[None, :]]
        den += wgt * vf[vi[:, None], ui[None, :]]
    depth = np.where((conf == 1) & (den > 0), num / np.maximum(den, 1e-12), np.nan).astype(np.float32)
    np.save(cm.OUT / "conf" / f"{v['stem']}_conf.npy", conf)
    cm.to_png(cm.OUT / "conf" / f"{v['stem']}_conf.png", np.repeat((conf * 255)[..., None], 3, axis=2))
    np.save(cm.INP / "mvs_full" / f"{v['stem']}_depth.npy", depth)
    np.save(cm.INP / "mvs_native" / f"{v['stem']}_depth.npy", np.where(valid, d, np.nan).astype(np.float32))
    nw = np.einsum("ji,hwj->hwi", v["R"], n.astype(np.float64)).astype(np.float32)  # R^T n_cam
    nw[~valid] = 0
    np.save(cm.INP / "mvs_native" / f"{v['stem']}_normal_world.npy", nw)
    rec = {"view": v["stem"], "native_wh": [w, h], "native_K": [fx, fy, cx, cy], "native_valid_fraction": float(valid.mean()),
           "full_conf_fraction": float(conf.mean()), "depth_min_max_m": [float(d[valid].min()), float(d[valid].max())]}
    # unit/scale check against the supplied LoD2 depth of the same view
    sp = supplied / f"{v['stem']}.npy"
    if sp.exists():
        ld = np.load(sp, mmap_mode="r")
        sub = (slice(None, None, 8), slice(None, None, 8))
        a, b = depth[sub], np.asarray(ld[sub], np.float32)
        ok = np.isfinite(a) & np.isfinite(b) & (b < 1e6)
        rec["scale_check_vs_supplied_lod2"] = {"n": int(ok.sum()), "median_mvs_minus_lod2_m": float(np.median(a[ok] - b[ok])) if ok.any() else None,
                                               "median_mvs_m": float(np.median(a[ok])) if ok.any() else None}
    records.append(rec)
    print(json.dumps(rec))
cm.write_json(cm.PROV / "mvs_resampling.json", {
    "source": "COLMAP patch_match_stereo geometric-consistency depth/normal maps (p0 common base)",
    "dense_camera_1400x1013": {"fx": fx0, "fy": fy0, "cx": cx0, "cy": cy0},
    "depth_convention": "camera-Z metres (COLMAP); identical to Open3D create_rays_pinhole t_hit used by LoD2Depth",
    "resampling": "depth bilinear over valid neighbours (validity-weighted), mask nearest; pixel centres at +0.5 on both grids",
    "consistent_view_count": {"available": len(consistency) > 0, "n_consistency_graph_files": len(consistency),
                              "note": "nviews arrays not produced: COLMAP consistency graphs are absent; conf = geometric filter pass"},
    "prior_used_for_confidence": False,
    "views": records})
rc.write()
