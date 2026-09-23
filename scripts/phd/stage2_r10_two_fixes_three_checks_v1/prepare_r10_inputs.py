"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 step 4 (jointbuildgs:dev, CPU): stage-2 inputs of the LoD2 settings (fix 'na').

  python prepare_r10_inputs.py <setting>      # M_N | M_B ; mounts: /artifacts (ro), /repo (ro), /r7 (ro), /p9 (ro), /p10 (rw)

  tau maps       as r9 (prepare_r9_inputs.py): tau_p = tau / max(f, 1e-3) at every prior pixel of the r10 product
  initial cloud  the r9 cloud (/p9/scenes/<setting>: SfM points + the LoD2 sample without bottom-face points) without the
                 sampled points that lie on a cut part of a party wall: their closest triangle of the r9 mesh is one the cut
                 replaced and the r10 mesh is farther (a point on the edge of the remaining part, as near to it, stays).
                 The rest of the sample is kept as it is (same points, same order). Written as a GeoGS scene in /p10/scenes/<setting>.
  seats          compact surface index (r10 store) of the polygon of the closest triangle of the r10 mesh (r9's rule)
  prior normals  the outward normal of that polygon (r9's values; a cut polygon keeps its plane)
  r9 check       kept points: seat polygon and prior normal equal to r9's
The airborne LiDAR settings read r9's inputs (nothing of them changes; the cell method of fix 'ra' is computed in the fork).
Writes /p10/inputs/<setting>/{tau/<view>.npy, seat_surface.npy, prior_normal.npy, prior_normal_rule.npy, removed_party_points.npy,
prepare_<setting>.json} and /p10/scenes/<setting>/..."""
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v4 import conversion as conv  # noqa: E402
from src.phd.prior_propagation_v4 import locations as locs  # noqa: E402

import stage1_products_r10 as s1  # noqa: E402

setting = sys.argv[1]
assert setting.startswith("M"), "only the LoD2 settings change in r10"
P9 = Path("/p9"); P10 = Path("/p10"); OUT = P10 / "inputs" / setting; (OUT / "tau").mkdir(parents=True, exist_ok=True)
PROD = P10 / "stage1/products" / setting
TAU = json.loads((P10 / "stage1/tolerance.json").read_text())["priors"][setting[0]]
tv = {conv.KIND_ROOF: TAU["roof"]["tau"], conv.KIND_WALL: TAU["wall"]["tau"]}
var = "poly"
m, ts, n_used, table = s1.surfaces_of(setting, var)
rep = dict(setting=setting, variant=var, tolerance={"roof": tv[1], "wall": tv[2]}, views={})
for stem in s1.VIEWS:
    tri, P, A, M = s1.view_arrays(setting, stem)
    W, H = s1.CAMS[s1.IMGS[stem]["cam"]]["W"], s1.CAMS[s1.IMGS[stem]["cam"]]["H"]
    n, s_ext, hit = s1.pixel_normals(tri, ts, n_used)
    idx = np.nonzero(np.isfinite(P))[0]
    d, _ = s1.rays(stem, idx)
    f = conv.factor(n[idx], d, has_surface=hit[idx])
    f1 = np.load(PROD / "fconv" / f"{stem}.npy").reshape(-1)[idx]
    kind = conv.surface_kind(n[idx, 2])
    bface = hit[idx].copy()
    tau_m = np.where(bface, np.where(kind == conv.KIND_ROOF, tv[1], tv[2]), tv[1])
    tau = np.full(len(tri), np.nan, np.float32)
    tau[idx] = (tau_m / np.maximum(f, 1e-3)).astype(np.float32)
    np.save(OUT / "tau" / f"{stem}.npy", tau.reshape(H, W))
    t9 = np.load(P9 / "inputs" / setting / "tau" / f"{stem}.npy").reshape(-1)
    both = np.isfinite(t9) & np.isfinite(tau)
    rep["views"][stem] = dict(prior_px=int(len(idx)), max_abs_factor_diff_stage1_vs_stage2=float(np.nanmax(np.abs(f.astype(np.float32) - f1))) if len(idx) else 0.0,
                              tau_px_r9=int(np.isfinite(t9).sum()), tau_px_r10=int(np.isfinite(tau).sum()),
                              tau_values_differ_px=int((np.abs(t9[both] - tau[both]) > 0).sum()),
                              tau_finite_differs_px=int((np.isfinite(t9) != np.isfinite(tau)).sum()))
    print(setting, stem, rep["views"][stem], flush=True)

# ------------------------------------------------------------------ initial cloud
S9 = P9 / "scenes" / setting
ply = PlyData.read(str(S9 / "sparse/0/points3D.ply"))["vertex"]
xyz9 = np.stack([np.asarray(ply[c], np.float64) for c in "xyz"], 1)
rgb9 = np.stack([np.asarray(ply[c]) for c in ("red", "green", "blue")], 1)
origin9 = np.load(S9 / "sparse/0/origin.npy")
pr9 = np.nonzero(origin9 == 1)[0]


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


m9 = np.load(P9 / "stage1/meshes" / f"{setting}.npz")
k10 = m["kept_from_r9"]
untouched9 = np.zeros(len(m9["F"]), bool); untouched9[k10[k10 >= 0]] = True
tri9, d9 = closest(m9["V"], m9["F"], xyz9[pr9])
tri10, d10 = closest(m["V"], m["F"], xyz9[pr9])
on_cut = ~untouched9[tri9] & (d10 > d9 + 1e-6)
edge_kept = ~untouched9[tri9] & ~on_cut
keep = np.ones(len(xyz9), bool); keep[pr9[on_cut]] = False
xyz, rgb, origin = xyz9[keep], rgb9[keep], origin9[keep]
bld9 = m9["tri_building"]
rep["initial_cloud"] = dict(rule="LoD2 sample points whose closest r9 triangle was replaced by the party-wall cut and that are farther from the r10 mesh",
                            n_points_r9=int(len(xyz9)), n_prior_r9=int(len(pr9)), n_removed_on_cut=int(on_cut.sum()),
                            n_removed_target_building=int((on_cut & (bld9[tri9] == s1.TARGET)).sum()),
                            n_on_replaced_triangles_kept=int(edge_kept.sum()), n_points_r10=int(len(xyz)), n_prior_r10=int((origin == 1).sum()),
                            distance_of_removed_to_r10_mesh_m=dict(p50=float(np.median(d10[on_cut])) if on_cut.any() else None,
                                                                   min=float(d10[on_cut].min()) if on_cut.any() else None),
                            distance_to_r10_mesh_of_kept_prior_m=dict(p50=float(np.median(d10[~on_cut])), p99=float(np.percentile(d10[~on_cut], 99)),
                                                                      max=float(d10[~on_cut].max())))
sc_dir = P10 / "scenes" / setting
if sc_dir.exists():
    shutil.rmtree(sc_dir)
(sc_dir / "sparse/0").mkdir(parents=True)
for f_ in ("cameras.bin", "images.bin"):
    shutil.copy2(S9 / "sparse/0" / f_, sc_dir / "sparse/0" / f_)
shutil.copy2(S9 / "jbgs_calibration.json", sc_dir / "jbgs_calibration.json")
os.symlink(os.readlink(S9 / "images"), sc_dir / "images")        # container path of the native images
store_ply(sc_dir / "sparse/0/points3D.ply", xyz, rgb)
np.save(sc_dir / "sparse/0/origin.npy", origin.astype(np.int8))
np.save(OUT / "removed_party_points.npy", pr9[on_cut])

# ------------------------------------------------------------------ seats and prior normals
store = locs.load_store(PROD / f"store_{var}_c{s1.CFG['values']['cell_m']}.npz")
seat = np.full(len(xyz), -1, np.int64)
pr = np.nonzero(origin == 1)[0]
normal = np.full((len(xyz), 3), np.nan, np.float32)
nrule = np.full(len(xyz), -1, np.int8)
tri, dist = closest(m["V"], m["F"], xyz[pr])
ext = ts[tri]
rep["closest_triangle_distance_m"] = dict(p50=float(np.median(dist)), p99=float(np.percentile(dist, 99)), max=float(dist.max()))
fz = np.load(P10 / "stage1/meshes" / f"faces_{setting}.npz")
nout = {int(p): fz["normal_outward"][i] for i, p in enumerate(fz["ids"])}
normal[pr] = np.stack([nout[int(e)] for e in ext]).astype(np.float32)
nrule[pr] = 10
cidx = locs.compact_index(store, np.maximum(ext, 0)); cidx[ext < 0] = -1
seat[pr] = cidx
np.save(OUT / "seat_surface.npy", seat)
np.save(OUT / "prior_normal.npy", normal)
np.save(OUT / "prior_normal_rule.npy", nrule)
# r9 check: the kept rows' seat polygon and prior normal
st9 = locs.load_store(P9 / "stage1/products" / setting / f"store_{var}_c{s1.CFG['values']['cell_m']}.npz")
seat9 = np.load(P9 / "inputs" / setting / "seat_surface.npy")[keep]
nrm9 = np.load(P9 / "inputs" / setting / "prior_normal.npy")[keep]
ext9 = np.where(seat9 >= 0, st9["surf_ext"][np.maximum(seat9, 0)], -1)
ext10 = np.where(seat >= 0, store["surf_ext"][np.maximum(seat, 0)], -1)
prow = origin == 1
rep["seat"] = dict(n_points=int(len(xyz)), n_prior=int(len(pr)), n_prior_with_surface=int((seat[pr] >= 0).sum()),
                   n_prior_without_surface=int((seat[pr] < 0).sum()),
                   seat_polygon_differs_from_r9=int((ext9[prow] != ext10[prow]).sum()),
                   seat_polygon_differs_examples=[[int(a), int(b)] for a, b in zip(ext9[prow][ext9[prow] != ext10[prow]][:10], ext10[prow][ext9[prow] != ext10[prow]][:10])],
                   prior_normal_differs_from_r9=int((np.abs(nrm9[prow] - normal[prow]) > 0).any(1).sum()))
(OUT / f"prepare_{setting}.json").write_text(json.dumps(rep, indent=1))
print(setting, "done", json.dumps({k: rep[k] for k in rep if k not in ("views",)})[:2500], flush=True)
