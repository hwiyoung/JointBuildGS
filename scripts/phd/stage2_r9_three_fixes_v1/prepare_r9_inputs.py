"""PHD-STAGE2-R9-THREE-FIXES-v1 step 4 (jointbuildgs:dev, CPU): stage-2 inputs of the fork r9 for the four training settings.

  python prepare_r9_inputs.py <setting>      # M_N | M_B | L_N | L_B ; mounts: /artifacts (ro), /repo (ro), /r7 (ro), /r8 (ro), /p9 (rw)

  tau maps       as r8 (prepare_r8_inputs.py): tau_p = tau / max(f, 1e-3) at every prior pixel of the r9 product
  initial cloud  LoD2 (fix 'ra'): the r8 cloud (S2 runs/P_M_<scene>/scene: SfM points + the LoD2 sample) without the sampled
                 points that lie on a bottom face: their closest triangle of the r8 mesh is a bottom-face triangle and the
                 mesh without the bottom faces is farther (points on a wall's lower edge, as near to the wall, stay).
                 The rest of the sample is kept as it is (same points, same order). Written as a GeoGS scene in
                 /p9/scenes/<setting> (cameras, images and calibration of the stage-2 scene). Airborne LiDAR: the r8 scene.
  seats          compact surface index of every point (-1: image points, prior points without a patch): LoD2 = polygon of the
                 closest triangle of the r9 mesh, TIN = vertex_surface (as r8)
  prior normals  fix 'da': per point of the initial cloud the outward normal of its prior face (NaN for image points):
                 LoD2 = the outward normal of the polygon of its closest triangle (meshes_r9.py faces_<setting>.npz),
                 TIN  = orientation.tin_vertex_normals (seat surface triangles; without a seat the larger kind)
                 (+ for LoD2 the same normals of the r8 cloud, bottom faces included, for the r8 comparison)
  r8 check       airborne LiDAR: products (store, unit / mark / conversion maps), tau maps and seats equal r8's
Writes /p9/inputs/<setting>/{tau/<view>.npy, seat_surface.npy, prior_normal.npy, prior_normal_rule.npy, prepare_<setting>.json}
and for LoD2 /p9/scenes/<setting>/..., /p9/inputs/<setting>/prior_normal_r8cloud.npy."""
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v3 import conversion as conv  # noqa: E402
from src.phd.prior_propagation_v3 import faces as FA  # noqa: E402
from src.phd.prior_propagation_v3 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v3 import orientation as ori  # noqa: E402
from src.phd.prior_propagation_v3 import surfaces as surf  # noqa: E402

import stage1_products_r9 as s1  # noqa: E402

setting = sys.argv[1]
P9 = Path("/p9"); R8 = Path("/r8"); OUT = P9 / "inputs" / setting; (OUT / "tau").mkdir(parents=True, exist_ok=True)
PROD = P9 / "stage1/products" / setting
COND = s1.CFG["settings"][setting]["condition"]
TAU = json.loads((P9 / "stage1/tolerance.json").read_text())["priors"][setting[0]]
tv = {conv.KIND_ROOF: TAU["roof"]["tau"], conv.KIND_WALL: TAU["wall"]["tau"]}
var = "poly" if setting.startswith("M") else "lod2"
m, ts, n_used, table = s1.surfaces_of(setting, var)
bflag = s1.building_face_flags(table)
rep = dict(setting=setting, variant=var, tolerance={"roof": tv[1], "wall": tv[2]}, views={})
tau_equal_r8 = True
for stem in s1.VIEWS:
    tri, P, A, M = s1.view_arrays(setting, stem)
    W, H = s1.CAMS[s1.IMGS[stem]["cam"]]["W"], s1.CAMS[s1.IMGS[stem]["cam"]]["H"]
    n, s_ext, hit = s1.pixel_normals(tri, ts, n_used)
    idx = np.nonzero(np.isfinite(P))[0]
    d, _ = s1.rays(stem, idx)
    f = conv.factor(n[idx], d, has_surface=hit[idx])
    f1 = np.load(PROD / "fconv" / f"{stem}.npy").reshape(-1)[idx]
    kind = conv.surface_kind(n[idx, 2])
    sx = s_ext[idx]
    bface = hit[idx].copy() if setting.startswith("M") else ((sx >= 0) & bflag[np.clip(sx, 0, len(bflag) - 1)])
    tau_m = np.where(bface, np.where(kind == conv.KIND_ROOF, tv[1], tv[2]), tv[1])
    tau = np.full(len(tri), np.nan, np.float32)
    tau[idx] = (tau_m / np.maximum(f, 1e-3)).astype(np.float32)
    np.save(OUT / "tau" / f"{stem}.npy", tau.reshape(H, W))
    t8 = np.load(R8 / "inputs" / setting / "tau" / f"{stem}.npy").reshape(-1)
    both = np.isfinite(t8) & np.isfinite(tau)
    same = bool(np.array_equal(np.isfinite(t8), np.isfinite(tau)) and (np.abs(t8[both] - tau[both]).max() == 0 if both.any() else True))
    tau_equal_r8 &= same
    rep["views"][stem] = dict(prior_px=int(len(idx)), max_abs_factor_diff_stage1_vs_stage2=float(np.nanmax(np.abs(f.astype(np.float32) - f1))) if len(idx) else 0.0,
                              nonbuilding_px=int((~bface).sum()), wall_like_px=int((kind == conv.KIND_WALL).sum()), tau_map_equal_r8=same,
                              tau_px_r8=int(np.isfinite(t8).sum()), tau_px_r9=int(np.isfinite(tau).sum()))
    print(setting, stem, rep["views"][stem], flush=True)
rep["tau_maps_equal_r8_all_views"] = bool(tau_equal_r8)

# ------------------------------------------------------------------ initial cloud
S2RUN = s1.S2 / "runs" / COND / "scene"
ply = PlyData.read(str(S2RUN / "sparse/0/points3D.ply"))["vertex"]
xyz8 = np.stack([np.asarray(ply[c], np.float64) for c in "xyz"], 1)
rgb8 = np.stack([np.asarray(ply[c]) for c in ("red", "green", "blue")], 1)
origin8 = np.load(S2RUN / "sparse/0/origin.npy")
pr8 = np.nonzero(origin8 == 1)[0]


def store_ply(path, xyz, rgb):   # make_scenes.store_ply
    dtype = [('x', 'f4'), ('y', 'f4'), ('z', 'f4'), ('nx', 'f4'), ('ny', 'f4'), ('nz', 'f4'), ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]
    el = np.empty(xyz.shape[0], dtype=dtype)
    attributes = np.concatenate((xyz.astype(np.float32), np.zeros_like(xyz, dtype=np.float32), rgb.astype(np.uint8)), axis=1)
    el[:] = list(map(tuple, attributes))
    PlyData([PlyElement.describe(el, 'vertex')]).write(str(path))


def closest(Vm, Fm, pts):
    import open3d as o3d
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(np.asarray(Vm, np.float32)), o3d.core.Tensor(np.asarray(Fm, np.uint32)))
    ans = sc.compute_closest_points(o3d.core.Tensor(np.asarray(pts, np.float32)))
    return ans["primitive_ids"].numpy().astype(np.int64), np.linalg.norm(ans["points"].numpy().astype(np.float64) - pts, axis=1)


if setting.startswith("M"):
    m8 = np.load(s1.R7 / "stage1/meshes" / f"{setting}.npz")
    nl = len(s1.PZ["labels"])
    ground8 = np.zeros(len(m8["F"]), bool); ground8[:nl] = FA.excluded_by_type(s1.PZ["labels"].astype(str))
    tri8, d8 = closest(m8["V"], m8["F"], xyz8[pr8])
    tri9, d9 = closest(m["V"], m["F"], xyz8[pr8])
    on_bottom = ground8[tri8] & (d9 > d8 + 1e-6)
    edge_kept = ground8[tri8] & ~on_bottom
    keep = np.ones(len(xyz8), bool); keep[pr8[on_bottom]] = False
    xyz, rgb, origin = xyz8[keep], rgb8[keep], origin8[keep]
    bld8 = np.where(np.arange(len(m8["F"])) < nl, np.r_[s1.PZ["building_ids"].astype(str), np.array([s1.TARGET] * (len(m8["F"]) - nl))], s1.TARGET)
    rep["initial_cloud"] = dict(rule="LoD2 sample points whose closest r8 triangle is a bottom face and that are farther from the mesh without bottom faces",
                                n_points_r8=int(len(xyz8)), n_prior_r8=int(len(pr8)), n_removed_on_bottom=int(on_bottom.sum()),
                                n_removed_target_building=int((on_bottom & (bld8[tri8] == s1.TARGET)).sum()),
                                n_edge_points_kept=int(edge_kept.sum()), n_points_r9=int(len(xyz)), n_prior_r9=int((origin == 1).sum()),
                                distance_to_r9_mesh_of_kept_prior_m=dict(p50=float(np.median(d9[~on_bottom])), p99=float(np.percentile(d9[~on_bottom], 99)),
                                                                         max=float(d9[~on_bottom].max())))
    sc_dir = P9 / "scenes" / setting
    if sc_dir.exists():
        shutil.rmtree(sc_dir)
    (sc_dir / "sparse/0").mkdir(parents=True)
    for f_ in ("cameras.bin", "images.bin"):
        shutil.copy2(S2RUN / "sparse/0" / f_, sc_dir / "sparse/0" / f_)
    shutil.copy2(S2RUN / "jbgs_calibration.json", sc_dir / "jbgs_calibration.json")
    os.symlink(os.readlink(S2RUN / "images"), sc_dir / "images")        # container path of the native images
    store_ply(sc_dir / "sparse/0/points3D.ply", xyz, rgb)
    np.save(sc_dir / "sparse/0/origin.npy", origin.astype(np.int8))
    np.save(OUT / "removed_bottom_points.npy", pr8[on_bottom])
    # r8 cloud normals (bottom faces included; for the r8 comparison of fix 'da')
    T8 = FA.polygon_table(m8["V"], m8["F"], m8["tri_poly"])
    fz = np.load(P9 / "stage1/meshes" / f"faces_{setting}.npz")
    nout = {int(p): fz["normal_outward"][i] for i, p in enumerate(fz["ids"])}
    nr8 = np.full((len(xyz8), 3), np.nan, np.float32)
    pol8 = m8["tri_poly"][tri8]
    for i, p in enumerate(T8["ids"]):
        sel = pol8 == p
        if sel.any():
            nr8[pr8[sel]] = nout.get(int(p), T8["normal"][i])               # bottom faces: their (downward) winding normal
    np.save(OUT / "prior_normal_r8cloud.npy", nr8)
else:
    xyz, rgb, origin = xyz8, rgb8, origin8
    rep["initial_cloud"] = dict(rule="the r8 cloud (airborne LiDAR has no bottom faces)", n_points=int(len(xyz)), n_prior=int((origin == 1).sum()))

# ------------------------------------------------------------------ seats and prior normals
store = locs.load_store(PROD / f"store_{var}_c{s1.CFG['values']['cell_m']}.npz")
seat = np.full(len(xyz), -1, np.int64)
pr = np.nonzero(origin == 1)[0]
normal = np.full((len(xyz), 3), np.nan, np.float32)
nrule = np.full(len(xyz), -1, np.int8)
if setting.startswith("M"):
    tri, dist = closest(m["V"], m["F"], xyz[pr])
    ext = ts[tri]
    rep["closest_triangle_distance_m"] = dict(p50=float(np.median(dist)), p99=float(np.percentile(dist, 99)), max=float(dist.max()))
    fz = np.load(P9 / "stage1/meshes" / f"faces_{setting}.npz")
    nout = {int(p): fz["normal_outward"][i] for i, p in enumerate(fz["ids"])}
    normal[pr] = np.stack([nout[int(e)] for e in ext]).astype(np.float32)
    nrule[pr] = 10
    flip = {int(p): bool((fz["normal_outward"][i] * fz["normal_winding"][i]).sum() < 0) for i, p in enumerate(fz["ids"])}
    rep["prior_normal"] = dict(rule="outward normal of the polygon of the closest triangle (r9 mesh)",
                               points_on_flipped_polygons=int(sum(flip[int(e)] for e in ext)))
else:
    V = m["V"]
    rep["max_abs_difference_to_tin_vertices_m"] = float(np.abs(V - xyz[pr]).max())
    eligible = np.zeros(int(ts.max()) + 1, bool)
    for e, row in table.items():
        eligible[e] = row["is_building_face"]
    ext_all = surf.vertex_surface(m["F"], ts, eligible)
    ext = ext_all[:len(pr)]
    nv, rv = ori.tin_vertex_normals(V, m["F"], ts, ext_all)
    normal[pr] = nv[:len(pr)].astype(np.float32); nrule[pr] = rv[:len(pr)]
    rep["prior_normal"] = dict(rule="TIN vertex normal: seat surface triangles; without a seat the larger kind (gentle / steep)",
                               by_rule={str(k): int((rv[:len(pr)] == k).sum()) for k in (0, 1, 2, 3)},
                               n_z_below_0=int((nv[:len(pr), 2] < 0).sum()))
cidx = locs.compact_index(store, np.maximum(ext, 0)); cidx[ext < 0] = -1
seat[pr] = cidx
np.save(OUT / "seat_surface.npy", seat)
np.save(OUT / "prior_normal.npy", normal)
np.save(OUT / "prior_normal_rule.npy", nrule)
rep["seat"] = dict(n_points=int(len(xyz)), n_prior=int(len(pr)), n_prior_with_surface=int((seat[pr] >= 0).sum()),
                   n_prior_without_surface=int((seat[pr] < 0).sum()))
if not setting.startswith("M"):   # r8 check: products, seats
    seat8 = np.load(R8 / "inputs" / setting / "seat_surface.npy")
    rep["seat"]["equal_to_r8"] = bool(np.array_equal(seat, seat8))
    eq = {}
    for var_ in ("lod2", "cls2"):
        a = np.load(PROD / f"store_{var_}_c0.25.npz"); b = np.load(R8 / "stage1/products" / setting / f"store_{var_}_c0.25.npz")
        eq[f"store_{var_}"] = bool(set(a.files) == set(b.files) and all(np.array_equal(a[k], b[k]) for k in a.files))
    for sub in ("locmap", "markmap", "fconv"):
        eq[sub] = all(np.array_equal(np.load(PROD / sub / f"{v}.npy"), np.load(R8 / "stage1/products" / setting / sub / f"{v}.npy"), equal_nan=(sub == "fconv"))
                      for v in s1.VIEWS)
    eq["tau_maps"] = rep["tau_maps_equal_r8_all_views"]
    rep["r8_products_equal"] = eq
    rep["r8_products_all_equal"] = bool(all(eq.values()) and rep["seat"]["equal_to_r8"])
(OUT / f"prepare_{setting}.json").write_text(json.dumps(rep, indent=1))
print(setting, "done", json.dumps({k: rep[k] for k in rep if k not in ("views",)})[:2500], flush=True)
