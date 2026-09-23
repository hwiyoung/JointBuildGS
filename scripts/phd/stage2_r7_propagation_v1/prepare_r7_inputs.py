"""PHD-STAGE2-R7-PROPAGATION-v1 step 4 (jointbuildgs:dev, CPU): stage-2 inputs of the fork r7 for the four training
settings, and the check that stage 1 and stage 2 now produce the same conversion maps.

  python prepare_r7_inputs.py <setting>      # M_N | M_B | L_N | L_B ; mounts: /artifacts (ro), /repo (ro), /p7 (rw)

  conversion  the stage-2 side computes its own factor map with the shared conversion (own normals, same ids) and compares
              it pixel by pixel with the stage-1 map (products/<setting>/fconv); records the maximum difference
  tau maps    tau_p = tau(surface kind) / max(f, 1e-3) at every prior pixel, full resolution, NaN elsewhere, for the two
              tolerance variants (spec, data); records the prior pixels of the +1 m scenes that had no tau in r5/r6
  seats       compact surface index of every point of the stage-2 initial cloud (-1: image points, prior points without
              a location): LoD2 = polygon of the closest triangle (Open3D), TIN = surface most triangles around the vertex
              belong to (the stage-2 airborne LiDAR points are the TIN vertices)
Writes /p7/inputs/<setting>/{tau_spec, tau_data}/<view>.npy, seat_surface.npy and prepare_<setting>.json."""
import json
import sys
from pathlib import Path

import numpy as np
from plyfile import PlyData

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v1 import conversion as conv  # noqa: E402
from src.phd.prior_propagation_v1 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v1 import surfaces as surf  # noqa: E402

import stage1_products as s1  # noqa: E402  (camera parsing, view arrays and surfaces of the stage-1 side)

setting = sys.argv[1]
P7 = Path("/p7"); OUT = P7 / "inputs" / setting; OUT.mkdir(parents=True, exist_ok=True)
PROD = P7 / "stage1/products" / setting
COND = s1.CFG["settings"][setting]["condition"]
TAU = json.loads((P7 / "stage1/tolerance.json").read_text())["priors"][setting[0]]
tv = {tag: {conv.KIND_ROOF: TAU[tag]["roof"]["tau"], conv.KIND_WALL: TAU[tag]["wall"]["tau"]} for tag in ("spec", "data")}
var = "poly" if setting.startswith("M") else "lod2"
m, ts, n_used, table = s1.surfaces_of(setting, var)
rep = dict(setting=setting, variant=var, tolerance={tag: {"roof": tv[tag][1], "wall": tv[tag][2]} for tag in tv}, views={})
for tag in tv:
    (OUT / f"tau_{tag}").mkdir(exist_ok=True)
for stem in s1.VIEWS:
    tri, P, A, M = s1.view_arrays(setting, stem)
    W, H = s1.CAMS[s1.IMGS[stem]["cam"]]["W"], s1.CAMS[s1.IMGS[stem]["cam"]]["H"]
    n, s_ext, hit = s1.pixel_normals(tri, ts, n_used)
    idx = np.nonzero(np.isfinite(P))[0]
    im = s1.IMGS[stem]; cam = s1.CAMS[im["cam"]]; fx, fy, cx, cy = cam["p"]
    d = conv.pixel_rays(fx, fy, cx, cy, im["R"], W, H, flat_idx=idx, dtype=np.float64)          # stage-2 side, own call
    f = conv.factor(n[idx], d, has_surface=hit[idx])
    f1 = np.load(PROD / "fconv" / f"{stem}.npy").reshape(-1)[idx]
    kind = conv.surface_kind(n[idx, 2])
    r = dict(prior_px=int(len(idx)), max_abs_factor_diff_stage1_vs_stage2=float(np.nanmax(np.abs(f.astype(np.float32) - f1))) if len(idx) else 0.0,
             nan_factor_px=int((~np.isfinite(f)).sum()))
    for tag in tv:
        tau = np.full(len(tri), np.nan, np.float32)
        tau[idx] = (np.where(kind == conv.KIND_ROOF, tv[tag][1], tv[tag][2]) / np.maximum(f, 1e-3)).astype(np.float32)
        np.save(OUT / f"tau_{tag}" / f"{stem}.npy", tau.reshape(H, W))
        r[f"prior_px_with_tau_{tag}"] = int(np.isfinite(tau[idx]).sum())
    old = np.load(s1.MAPS / f"tau_{setting[0]}/raw_depth/{stem}.npy").reshape(-1)
    r["prior_px_without_tau_in_r5_r6"] = int((~np.isfinite(old[idx])).sum())
    r["wall_like_px"] = int((kind == conv.KIND_WALL).sum())
    rep["views"][stem] = r
    print(setting, stem, r, flush=True)

# seats of the stage-2 initial cloud
ply = PlyData.read(str(s1.S2 / "runs" / COND / "scene/sparse/0/points3D.ply"))["vertex"]
xyz = np.stack([np.asarray(ply[c], np.float64) for c in "xyz"], 1)
origin = np.load(s1.S2 / "runs" / COND / "scene/sparse/0/origin.npy")
store = locs.load_store(PROD / f"store_{var}_c{s1.CFG['values']['cell_m']}.npz")
seat = np.full(len(xyz), -1, np.int64)
pr = np.nonzero(origin == 1)[0]
if setting.startswith("M"):
    import open3d as o3d
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(m["V"].astype(np.float32)), o3d.core.Tensor(m["F"].astype(np.uint32)))
    ans = sc.compute_closest_points(o3d.core.Tensor(xyz[pr].astype(np.float32)))
    tri = ans["primitive_ids"].numpy().astype(np.int64)
    dist = np.linalg.norm(ans["points"].numpy() - xyz[pr], axis=1)
    ext = ts[tri]
    rep["closest_triangle_distance_m"] = dict(p50=float(np.median(dist)), p99=float(np.percentile(dist, 99)), max=float(dist.max()))
else:
    V = m["V"]
    rep["max_abs_difference_to_tin_vertices_m"] = float(np.abs(V - xyz[pr]).max())
    eligible = np.zeros(int(ts.max()) + 1, bool)
    for e, row in table.items():
        eligible[e] = row["is_building_face"]
    ext = surf.vertex_surface(m["F"], ts, eligible)
    ext = ext[:len(pr)]
cidx = locs.compact_index(store, np.maximum(ext, 0)); cidx[ext < 0] = -1
seat[pr] = cidx
np.save(OUT / "seat_surface.npy", seat)
rep["seat"] = dict(n_points=int(len(xyz)), n_prior=int(len(pr)), n_prior_with_surface=int((seat[pr] >= 0).sum()),
                   n_prior_without_surface=int((seat[pr] < 0).sum()))
tot = {k: sum(v[k] for v in rep["views"].values()) for k in rep["views"][s1.VIEWS[0]] if k != "max_abs_factor_diff_stage1_vs_stage2"}
tot["max_abs_factor_diff_stage1_vs_stage2"] = max(v["max_abs_factor_diff_stage1_vs_stage2"] for v in rep["views"].values())
rep["totals"] = tot
(OUT / f"prepare_{setting}.json").write_text(json.dumps(rep, indent=1))
print(setting, "done", tot, rep["seat"], flush=True)
