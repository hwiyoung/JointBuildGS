"""PHD-STAGE2-R8-FOUR-CASES-v1 step 2 (jointbuildgs:dev, CPU): stage-2 inputs of the fork r8 for the four training settings.

  python prepare_r8_inputs.py <setting>      # M_N | M_B | L_N | L_B ; mounts: /artifacts (ro), /repo (ro), /r7 (ro), /p8 (rw)

  tau maps    tau_p = tau / max(f, 1e-3) at every prior pixel, full resolution, NaN elsewhere (eq. 5): tau of the surface kind
              on building faces, the roof tau elsewhere (as the marks); conversion f = the stage-1 map (products/fconv),
              recomputed here with the shared function and compared pixel by pixel
  seats       compact surface index of every point of the stage-2 initial cloud (-1: image points, prior points without
              a unit): LoD2 = polygon of the closest triangle (Open3D), TIN = surface most triangles around the vertex
              belong to (the stage-2 airborne LiDAR points are the TIN vertices)
  r7 check    the seats equal r7's (same units); the tau maps equal r7's data-width maps
Writes /p8/inputs/<setting>/{tau/<view>.npy, seat_surface.npy, prepare_<setting>.json}."""
import json
import sys
from pathlib import Path

import numpy as np
from plyfile import PlyData

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v2 import conversion as conv  # noqa: E402
from src.phd.prior_propagation_v2 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v2 import surfaces as surf  # noqa: E402

import stage1_products_r8 as s1  # noqa: E402

setting = sys.argv[1]
P8 = Path("/p8"); OUT = P8 / "inputs" / setting; (OUT / "tau").mkdir(parents=True, exist_ok=True)
PROD = P8 / "stage1/products" / setting
COND = s1.CFG["settings"][setting]["condition"]
TAU = json.loads((P8 / "stage1/tolerance.json").read_text())["priors"][setting[0]]
tv = {conv.KIND_ROOF: TAU["roof"]["tau"], conv.KIND_WALL: TAU["wall"]["tau"]}
var = "poly" if setting.startswith("M") else "lod2"
m, ts, n_used, table = s1.surfaces_of(setting, var)
bflag = s1.building_face_flags(table)
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
    sx = s_ext[idx]
    bface = hit[idx].copy() if setting.startswith("M") else ((sx >= 0) & bflag[np.clip(sx, 0, len(bflag) - 1)])
    tau_m = np.where(bface, np.where(kind == conv.KIND_ROOF, tv[1], tv[2]), tv[1])
    tau = np.full(len(tri), np.nan, np.float32)
    tau[idx] = (tau_m / np.maximum(f, 1e-3)).astype(np.float32)
    np.save(OUT / "tau" / f"{stem}.npy", tau.reshape(H, W))
    r7 = np.load(Path("/r7/inputs") / setting / "tau_data" / f"{stem}.npy").reshape(-1)
    same = np.isfinite(r7) == np.isfinite(tau)
    rep["views"][stem] = dict(prior_px=int(len(idx)), max_abs_factor_diff_stage1_vs_stage2=float(np.nanmax(np.abs(f.astype(np.float32) - f1))) if len(idx) else 0.0,
                              nonbuilding_px=int((~bface).sum()), wall_like_px=int((kind == conv.KIND_WALL).sum()),
                              tau_finite_pattern_equal_r7=bool(same.all()),
                              max_abs_tau_diff_vs_r7_data=float(np.nanmax(np.abs(tau[idx] - r7[idx]))) if len(idx) else 0.0)
    print(setting, stem, rep["views"][stem], flush=True)

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
seat_r7 = np.load(Path("/r7/inputs") / setting / "seat_surface.npy")
rep["seat"] = dict(n_points=int(len(xyz)), n_prior=int(len(pr)), n_prior_with_surface=int((seat[pr] >= 0).sum()),
                   n_prior_without_surface=int((seat[pr] < 0).sum()), equal_to_r7=bool(np.array_equal(seat, seat_r7)))
tot = {k: sum(v[k] for v in rep["views"].values()) for k in ("prior_px", "nonbuilding_px", "wall_like_px")}
tot["max_abs_factor_diff_stage1_vs_stage2"] = max(v["max_abs_factor_diff_stage1_vs_stage2"] for v in rep["views"].values())
tot["tau_equal_r7_data_all_views"] = all(v["tau_finite_pattern_equal_r7"] and v["max_abs_tau_diff_vs_r7_data"] == 0.0 for v in rep["views"].values())
rep["totals"] = tot
(OUT / f"prepare_{setting}.json").write_text(json.dumps(rep, indent=1))
print(setting, "done", tot, rep["seat"], flush=True)
