"""Reusable bounded-memory TSDF, promoted from PHD-MAIN-FILL-v1 CDGS post: the training-view TSDF of gpu_fl.depthfuse made tile by tile, with bounded host memory,
and the same mesh as the one-piece integration (same voxels in every tile core, same triangles, same triangle order).

The one-piece path (gpu_fl.depthfuse -> the fork's GaussianExtractor.extract_mesh_bounded, Open3D 0.19 legacy ScalableTSDFVolume:
voxel 0.05 m, sdf_trunc 0.25 m, depth_trunc 300 m, volume_unit_resolution 16, depth_sampling_stride 4, RGB8 with zero colour, the 243
training views, the box mask of gpu_s1.box_mask) is kept unchanged; only the depth handed to Open3D differs per tile:
  core C_t       x, y ranges on multiples of the unit length L = 0.8 m (units are anchored at the origin), z free
  extended E_t   C_t + M (M = 2 L = 1.6 m) in x and y, the box z range + M in z
  per pixel with depth d (after the box mask; d >= 300 m is no depth, as Open3D), P its point on the pixel-centre ray:
    P inside E_t                       -> d
    ray passes E_t and P lies beyond   -> camera z of the far exit point of E_t minus EPS (proxy)
    otherwise (P in front, ray misses) -> 0
Why the core is exact (Open3D 0.19 UniformTSDFVolume::IntegrateWithDepthToCameraDistanceMultiplier, ScalableTSDFVolume::Integrate,
ExtractTriangleMesh): a voxel v of C_t or of its first ring of units (>= 0.825 m inside the side faces of E_t, its z within 1.05 m of
the box) takes from pixel p: nothing if d_p <= 0 or sdf <= -trunc, else tsdf = min(1, sdf / trunc), sdf = (d_p - z_v) * multiplier.
Its pixel-centre ray passes within e_lat = 0.5 z_v sqrt(fx^-2 + fy^-2) of v (checked < 0.5 m), so inside E_t; P in the box and E_t
z-range around the box z-range make the exit (entry) of a 'beyond' ('in front') ray a side face (a camera inside E_t has no 'in front'
or missing rays); hence sdf >= 0.825 - e_lat > trunc
for both the true and the proxy depth (tsdf 1 both) and sdf < -trunc for a ray ending in front (no update both). Units are opened
from the stride-4 points within trunc of them: points within 1.05 m of C_t are kept unchanged, proxies lie >= 1.6 - EPS m from C_t,
so C_t and its first ring have the same units with the same voxels; a cube (marching cubes, Open3D's index0 = its first voxel) of a
core unit reads only that ring, so every core unit gives the same triangles in the same order, and a vertex is a function of its
edge. Each tile keeps the cubes of its core units; the tiles' unit blocks are put in the iteration order of the one-piece volume's
std::unordered_map (insertion order of its units simulated here, the map itself by umap_order.cpp on the libstdc++ Open3D loads), the
order ExtractTriangleMesh walks. Vertices are identified by their global edge (Open3D's rule: one vertex per cut edge; the edge of a
corner from its cube and the marching-cubes table), so the copies of a seam vertex in two tiles become one, and numbered as Open3D does
(first cube in the walk, edge-number order inside a cube): the file can be the same byte for byte. Where a corner cannot be settled
(only around tsdf = 0 exactly) the merge falls back to exact coordinates on the seam planes and first-use numbering, and says so.

Modes (container paths; WD = a work folder; this task: /ph/main_fill_v1/PHD-MAIN-FILL-v1/work/tsdf_tiled/<name>):
  prep <site> <result> <depth dir> <WD> [--box x0 y0 z0 x1 y1 z1]   GPU, fork image (run_gpu_fl.sh): the inputs of gpu_fl.depthfuse
        (same training cameras and order, depth files, gpu_s1.box_mask, cameras of the fork's to_cam_open3d) -> WD/inputs/
  onepiece <site> <result> <depth dir> <WD> [--box ...]              GPU: gpu_fl.depthfuse itself with BOX = --box (the fork's
        extract_mesh_bounded) -> WD/onepiece/ (validation reference)
  survey <WD> [--sub x0 y0 x1 y1 ...]                                CPU: units by tile layout and by sub-box (memory estimate)
  plan <WD> <NXxNY | auto[:GB]>                                      CPU: tiles, insertion sequences of the one-piece and every tile
  order <WD>                                                         CPU: unit iteration orders (umap_order.cpp)
  tile <WD> <k>                                                      CPU, one container per tile: -> WD/tiles/tile<k>.npz, .json
  merge <WD> <out.ply> <out.json> [<site> <result> <depth dir>]     CPU: one mesh in the one-piece triangle order
  checkorder <mesh.ply> <order.i32> <out.json>                       CPU: unit blocks of a mesh against a simulated order
  compare <a.ply> <b.ply> <out.json>                                 CPU: triangles (exact), order, vertices
Peak host memory: ru_maxrss of the process and the container's cgroup memory.peak. scientific_verdict: null."""
import argparse
import datetime
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

VOXEL, TRUNC, DTRUNC = 0.05, 0.25, 300.0      # = gpu_fl.depthfuse: extract_mesh_bounded(voxel_size=0.05, sdf_trunc=0.25, depth_trunc=300.0)
RES, STRIDE = 16, 4                             # Open3D ScalableTSDFVolume defaults (volume_unit_resolution, depth_sampling_stride)
L = VOXEL * RES                                 # = Open3D volume_unit_length_ (0.05 * 16 == 0.8 in double)
M = 2 * L                                       # margin of the extended tile E_t
EPS = 1e-3                                      # proxy: camera z this far before the far exit point of E_t (m)
SNAP = 1e-12                                    # m: a vertex coordinate this close to a voxel-centre plane is on it (Open3D
                                                # writes plane coordinates exactly; this only catches tsdf = 0 at an edge end)
ELAT_MAX = 0.5                                  # m: the bound the exactness argument needs (< 0.55)
UNIT_BYTES = 48 * RES ** 3                      # Open3D 0.19 TSDFVoxel = 48 bytes
OFF, SH = 1 << 20, 21
HERE = Path(__file__).resolve().parent


# ------------------------------------------------------------------------------------------------ small helpers
def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False))


def rss_peak_gb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 3)


def cg_peak_gb():
    try:
        return round(int(Path("/sys/fs/cgroup/memory.peak").read_text()) / 2 ** 30, 3)
    except (OSError, ValueError):
        return None


def rss_now_gb():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024 ** 2, 3)
    return None


KST = datetime.timezone(datetime.timedelta(hours=9))       # the images have no zoneinfo: local time (Asia/Seoul) by its offset


def stamp(fmt="%Y-%m-%d %H:%M:%S"):
    return datetime.datetime.now(KST).strftime(fmt)


def log(*a):
    print(stamp("%H:%M:%S"), *a, flush=True)


def enc(k):
    k = np.asarray(k, np.int64)
    return ((k[..., 0] + OFF) << (2 * SH)) | ((k[..., 1] + OFF) << SH) | (k[..., 2] + OFF)


def dec(c):
    c = np.asarray(c, np.int64)
    m = (1 << SH) - 1
    return np.stack([(c >> (2 * SH)) - OFF, ((c >> SH) & m) - OFF, (c & m) - OFF], -1)


def libstdcxx_loaded():
    try:
        return sorted({ln.split()[-1] for ln in Path("/proc/self/maps").read_text().splitlines() if "libstdc++" in ln})
    except OSError:
        return None


def load_inputs(wd):
    I = Path(wd) / "inputs"
    meta = json.loads((I / "meta.json").read_text())
    cams = dict(np.load(I / "cams.npz"))
    depth = np.load(I / "depth_masked.npy", mmap_mode="r")
    return meta, cams, depth


def cam_of(cams, i):
    fx, fy, cx, cy = (float(v) for v in cams["intr"][i])
    E = np.asarray(cams["extrinsic"][i], np.float64)
    return fx, fy, cx, cy, E, np.linalg.inv(E)


def layout(BOX, nx, ny):
    """tile cores on unit multiples (half-open unit-index ranges) covering every unit the one-piece volume can open, and E_t."""
    BOX = np.asarray(BOX, np.float64)

    def cuts(a, n):
        u0 = int(np.floor((BOX[0, a] - TRUNC) / L)) - 2
        u1 = int(np.floor((BOX[1, a] + TRUNC) / L)) + 3
        inner = [int(np.rint((BOX[0, a] + (BOX[1, a] - BOX[0, a]) * i / n) / L)) for i in range(1, n)]
        c = [u0] + inner + [u1]
        if any(c[i + 1] - c[i] < 3 for i in range(n)):
            raise SystemExit(f"tiles too narrow on axis {a}: {c}")
        return c
    xs, ys = cuts(0, nx), cuts(1, ny)
    tiles = []
    for j in range(ny):
        for i in range(nx):
            E = [[xs[i] * L - M, ys[j] * L - M, BOX[0, 2] - M], [xs[i + 1] * L + M, ys[j + 1] * L + M, BOX[1, 2] + M]]
            tiles.append(dict(k=len(tiles), ix=i, iy=j, core_units=[xs[i], xs[i + 1], ys[j], ys[j + 1]],
                              core_m=[xs[i] * L, xs[i + 1] * L, ys[j] * L, ys[j + 1] * L], E=E))
    return dict(nx=nx, ny=ny, x_cuts_units=xs, y_cuts_units=ys, L=L, M=M, EPS=EPS, tiles=tiles)


def tile_depth(d, rows, cols, cam, E):
    """per-pixel depth for the extended tile E (see the module text); elementwise, so the same at a pixel whatever else is passed.
    d: float32 depth (> 0), rows / cols: float64 pixel indices. Returns float32 depth and the class (0 none, 1 kept, 2 proxy)."""
    fx, fy, cx, cy, _, Mp = cam
    d64 = d.astype(np.float64)
    xn = (cols - cx) / fx
    yn = (rows - cy) / fy
    C = Mp[:3, 3]
    t_in = np.full(len(d), -np.inf)
    t_out = np.full(len(d), np.inf)
    for a in range(3):
        w = xn * Mp[a, 0] + yn * Mp[a, 1] + Mp[a, 2]
        lo, hi = E[0][a], E[1][a]
        with np.errstate(divide="ignore", invalid="ignore"):
            t1 = (lo - C[a]) / w
            t2 = (hi - C[a]) / w
        inside = lo <= C[a] <= hi
        zero = w == 0
        tmin = np.where(zero, -np.inf if inside else np.inf, np.minimum(t1, t2))
        tmax = np.where(zero, np.inf if inside else -np.inf, np.maximum(t1, t2))
        t_in = np.maximum(t_in, tmin)
        t_out = np.minimum(t_out, tmax)
    valid = (d64 > 0) & (d64 < DTRUNC)
    hit = t_out >= t_in
    keep = valid & hit & (d64 >= t_in) & (d64 <= t_out)
    beyond = valid & hit & (d64 > t_out) & (t_out - EPS > 0)
    out = np.zeros(len(d), np.float32)
    out[keep] = d[keep]
    out[beyond] = (t_out[beyond] - EPS).astype(np.float32)
    cls = np.zeros(len(d), np.int8)
    cls[keep] = 1
    cls[beyond] = 2
    return out, cls


def sample_pixels(depth_i):
    """Open3D's stride-4 point pixels (rows outer, columns inner) with 0 < d < depth_trunc (ConvertDepthToFloatImage zeroes d >= trunc)."""
    sub = np.asarray(depth_i[::STRIDE, ::STRIDE])
    rr, cc = np.nonzero((sub > 0) & (sub < DTRUNC))
    return (rr * STRIDE).astype(np.float64), (cc * STRIDE).astype(np.float64), sub[rr, cc]


def points_of(d, rows, cols, cam):
    """= Open3D CreatePointCloudFromFloatDepthImage: x = (j - cx) * z / fx, y = (i - cy) * z / fy, camera_pose * (x, y, z, 1)."""
    fx, fy, cx, cy, _, Mp = cam
    z = d.astype(np.float64)
    x = (cols - cx) * z / fx
    y = (rows - cy) * z / fy
    P = np.empty((len(z), 3))
    for r in range(3):
        P[:, r] = Mp[r, 0] * x + Mp[r, 1] * y + Mp[r, 2] * z + Mp[r, 3]
    return P


def unit_attempts(P):
    """= ScalableTSDFVolume::Integrate: per point, units LocateVolumeUnit(p - trunc) .. LocateVolumeUnit(p + trunc), x outer, z inner."""
    lo = np.floor((P - TRUNC) / L).astype(np.int64)
    hi = np.floor((P + TRUNC) / L).astype(np.int64)
    ks, oks = [], []
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                ks.append(lo + np.array([dx, dy, dz], np.int64))
                oks.append((lo[:, 0] + dx <= hi[:, 0]) & (lo[:, 1] + dy <= hi[:, 1]) & (lo[:, 2] + dz <= hi[:, 2]))
    return np.stack(ks, 1)[np.stack(oks, 1)]


class Seq:
    """first insertions into volume_units_ in order (a dense 'seen' grid over the unit-index bounds)."""

    def __init__(self, lo, hi):
        self.lo, self.n = np.asarray(lo, np.int64), np.asarray(hi, np.int64) - np.asarray(lo, np.int64)
        self.seen = np.zeros(int(np.prod(self.n)), bool)
        self.parts = []
        self.attempts = 0

    def add(self, K):
        if not len(K):
            return
        q = K - self.lo
        if (q < 0).any() or (q >= self.n).any():
            raise SystemExit("unit index outside the planned bounds")
        lin = (q[:, 0] * self.n[1] + q[:, 1]) * self.n[2] + q[:, 2]
        u, first = np.unique(lin, return_index=True)
        u = u[np.argsort(first, kind="stable")]
        new = u[~self.seen[u]]
        self.seen[new] = True
        self.parts.append(new)
        self.attempts += len(K)

    def keys(self):
        lin = np.concatenate(self.parts) if self.parts else np.zeros(0, np.int64)
        z = lin % self.n[2]
        y = (lin // self.n[2]) % self.n[1]
        x = lin // (self.n[2] * self.n[1])
        return np.stack([x, y, z], 1) + self.lo


def unit_bounds(BOX):
    BOX = np.asarray(BOX, np.float64)
    lo = np.floor((BOX[0] - M - 2.0) / L).astype(np.int64) - 1
    hi = np.floor((BOX[1] + M + 2.0) / L).astype(np.int64) + 2
    return lo, hi


def e_lat(cams, BOX):
    """max over views of 0.5 z sqrt(fx^-2 + fy^-2) for the voxels that matter (the box + 1.1 m), z = camera z of its corners."""
    B = np.asarray(BOX, np.float64)
    corners = np.array([[x, y, z] for x in (B[0, 0] - 1.1, B[1, 0] + 1.1) for y in (B[0, 1] - 1.1, B[1, 1] + 1.1)
                        for z in (B[0, 2] - 1.1, B[1, 2] + 1.1)])
    worst, zmin = 0.0, np.inf
    for i in range(len(cams["intr"])):
        fx, fy, cx, cy, E, Mp = cam_of(cams, i)
        zc = corners @ E[2, :3] + E[2, 3]
        zmin = min(zmin, float(zc.min()))
        worst = max(worst, 0.5 * float(zc.max()) * float(np.sqrt(fx ** -2 + fy ** -2)))
    return worst, zmin


# ------------------------------------------------------------------------------------------------ CPU: survey, plan, order
def survey(wd, subs):
    """units the one-piece volume opens (whole box, each sub-box) and per tile for several layouts -> WD/survey.json (estimate only)."""
    t0 = time.time()
    meta, cams, depth = load_inputs(wd)
    BOX = np.asarray(meta["box"])
    lo, hi = unit_bounds(BOX)
    lays = {f"{nx}x{ny}": layout(BOX, nx, ny) for nx, ny in ((1, 2), (2, 1), (2, 2), (2, 3), (3, 2), (3, 3), (3, 4), (4, 4))}
    one = Seq(lo, hi)
    sub = {json.dumps(s): Seq(lo, hi) for s in subs}
    til = {k: [Seq(lo, hi) for _ in v["tiles"]] for k, v in lays.items()}
    for i in range(len(depth)):
        cam = cam_of(cams, i)
        rows, cols, d = sample_pixels(depth[i])
        if not len(d):
            continue
        P = points_of(d, rows, cols, cam)
        one.add(unit_attempts(P))
        for s, q in sub.items():
            b = json.loads(s)
            m = (P[:, 0] >= b[0]) & (P[:, 0] <= b[2]) & (P[:, 1] >= b[1]) & (P[:, 1] <= b[3])
            q.add(unit_attempts(P[m]))
        for k, v in lays.items():
            for t, q in zip(v["tiles"], til[k]):
                dt, cls = tile_depth(d, rows, cols, cam, t["E"])
                m = dt > 0
                q.add(unit_attempts(points_of(dt[m], rows[m], cols[m], cam)))
        if i % 40 == 0:
            log("survey view", i, "units", len(one.keys()))
    gb = lambda n: round(n * UNIT_BYTES / 2 ** 30, 2)  # noqa: E731
    n1 = len(one.keys())
    out = dict(box=meta["box"], onepiece_units=n1, onepiece_unit_gb=gb(n1),
               subs={s: dict(units=len(q.keys()), unit_gb=gb(len(q.keys()))) for s, q in sub.items()},
               layouts={k: dict(units=[len(q.keys()) for q in til[k]], unit_gb=[gb(len(q.keys())) for q in til[k]],
                                max_unit_gb=max(gb(len(q.keys())) for q in til[k]), sum_units=sum(len(q.keys()) for q in til[k]))
                        for k in lays},
               e_lat_max_m=round(e_lat(cams, BOX)[0], 4), seconds=round(time.time() - t0, 1), peak_host_gb=rss_peak_gb(), scientific_verdict=None)
    jdump(Path(wd) / "survey.json", out)
    log("survey", json.dumps(out)[:3000])


AUTO_LAYOUTS = [(1, 1), (1, 2), (2, 1), (2, 2), (2, 3), (3, 2), (3, 3), (3, 4), (4, 3), (4, 4), (4, 5), (5, 4), (5, 5), (5, 6), (6, 5),
                (6, 6)]


def tile_unit_counts(depth, cams, BOX, lay):
    """units every tile of a layout opens (simulated as in plan)."""
    lo, hi = unit_bounds(BOX)
    seqs = [Seq(lo, hi) for _ in lay["tiles"]]
    for i in range(len(depth)):
        cam = cam_of(cams, i)
        rows, cols, d = sample_pixels(depth[i])
        if not len(d):
            continue
        for t, q in zip(lay["tiles"], seqs):
            dt, _ = tile_depth(d, rows, cols, cam, t["E"])
            m = dt > 0
            q.add(unit_attempts(points_of(dt[m], rows[m], cols[m], cam)))
    return [len(q.keys()) for q in seqs]


def plan(wd, tiles):
    """tiles = 'NXxNY', or 'auto[:GB]': the layout with the fewest tiles (near-square ones first) whose largest tile opens at most GB
    of voxels (default 20 GB; the driver passes auto:22 = about 25 GB peak with the mesh, under the 32 GB limit of the heavy steps)."""
    t0 = time.time()
    meta, cams, depth = load_inputs(wd)
    BOX = np.asarray(meta["box"])
    auto = None
    if tiles.lower().startswith("auto"):
        budget = float(tiles.split(":")[1]) if ":" in tiles else 20.0
        tried = []
        for nx, ny in AUTO_LAYOUTS:
            try:
                cand = layout(BOX, nx, ny)
            except SystemExit:
                continue
            n = tile_unit_counts(depth, cams, BOX, cand)
            gbs = [round(u * UNIT_BYTES / 2 ** 30, 2) for u in n]
            tried.append(dict(layout=f"{nx}x{ny}", unit_gb=gbs))
            log("auto layout", nx, ny, gbs)
            if max(gbs) <= budget:
                break
        else:
            raise SystemExit(f"no layout up to 6x6 keeps every tile under {budget} GB of voxels (stop, report)")
        auto = dict(budget_unit_gb=budget, tried=tried)
    else:
        nx, ny = (int(v) for v in tiles.lower().split("x"))
    lay = layout(BOX, nx, ny)
    lay["auto"] = auto
    elat, zmin_cam = e_lat(cams, BOX)
    if elat >= ELAT_MAX:
        raise SystemExit(f"e_lat {elat:.3f} m >= {ELAT_MAX} m: the margin argument does not hold (stop, report)")
    # a camera inside E_t changes nothing: no pixel can lie in front of E_t or miss it, and a 'beyond' ray still leaves E_t by a side
    # face (its point is within the box z-range) -> recorded only
    centres = np.stack([cam_of(cams, i)[5][:3, 3] for i in range(len(cams["intr"]))])
    cams_in_E = [int(((centres >= np.asarray(t["E"][0])) & (centres <= np.asarray(t["E"][1]))).all(1).sum()) for t in lay["tiles"]]
    lo, hi = unit_bounds(BOX)
    one = Seq(lo, hi)
    seqs = [Seq(lo, hi) for _ in lay["tiles"]]
    cls_n = np.zeros((len(lay["tiles"]), 3), np.int64)
    for i in range(len(depth)):
        cam = cam_of(cams, i)
        rows, cols, d = sample_pixels(depth[i])
        if not len(d):
            continue
        one.add(unit_attempts(points_of(d, rows, cols, cam)))
        for t, q in zip(lay["tiles"], seqs):
            dt, cls = tile_depth(d, rows, cols, cam, t["E"])
            cls_n[t["k"]] += np.bincount(cls, minlength=3)
            m = dt > 0
            q.add(unit_attempts(points_of(dt[m], rows[m], cols[m], cam)))
    P = Path(wd) / "plan"
    P.mkdir(parents=True, exist_ok=True)
    K1 = one.keys()
    K1.astype(np.int32).tofile(P / "seq_onepiece.i32")
    rows_t = []
    for t, q in zip(lay["tiles"], seqs):
        K = q.keys()
        K.astype(np.int32).tofile(P / f"seq_tile{t['k']}.i32")
        cu = t["core_units"]
        core = (K[:, 0] >= cu[0]) & (K[:, 0] < cu[1]) & (K[:, 1] >= cu[2]) & (K[:, 1] < cu[3])
        rows_t.append(dict(k=t["k"], units=int(len(K)), core_units=int(core.sum()), unit_gb=round(len(K) * UNIT_BYTES / 2 ** 30, 2),
                           sampled_points_kept=int(cls_n[t["k"], 1]), sampled_points_proxy=int(cls_n[t["k"], 2]),
                           sampled_points_dropped=int(cls_n[t["k"], 0])))
    in_core = np.zeros(len(K1), bool)
    for t in lay["tiles"]:
        cu = t["core_units"]
        in_core |= (K1[:, 0] >= cu[0]) & (K1[:, 0] < cu[1]) & (K1[:, 1] >= cu[2]) & (K1[:, 1] < cu[3])
    if not in_core.all():
        raise SystemExit("a one-piece unit lies outside every tile core")
    out = dict(layout=lay, box=meta["box"], onepiece_units=int(len(K1)), onepiece_unit_gb=round(len(K1) * UNIT_BYTES / 2 ** 30, 2),
               tiles=rows_t, e_lat_max_m=round(elat, 4), nearest_camera_z_of_box_m=round(zmin_cam, 2),
               camera_height_above_box_top_m=[round(float(centres[:, 2].min() - BOX[1, 2]), 2), round(float(centres[:, 2].max() - BOX[1, 2]), 2)],
               cameras_inside_extended_tile=cams_in_E, cameras_inside_box=int(((centres >= BOX[0]) & (centres <= BOX[1])).all(1).sum()),
               margins=dict(first_ring_to_E_side_m=round(M - L + VOXEL / 2, 3), sdf_margin_m=round(M - L + VOXEL / 2 - elat - TRUNC, 3),
                            z_margin_m=round(M - (TRUNC + L) - elat, 3), proxy_to_core_m=round(M - EPS, 3)),
               seconds=round(time.time() - t0, 1), peak_host_gb=rss_peak_gb(), written=stamp(), scientific_verdict=None)
    jdump(P / "plan.json", out)
    jdump(P / "layout.json", lay)
    log("plan", json.dumps({k: out[k] for k in ("onepiece_units", "onepiece_unit_gb", "tiles", "e_lat_max_m", "seconds")}))


def order(wd):
    """the iteration order of every planned insertion sequence (umap_order.cpp, built here with g++, run on /opt/geogs/lib's libstdc++)."""
    W = Path(wd)
    B = W / "bin"
    B.mkdir(exist_ok=True)
    exe = B / "umap_order"
    src = HERE / "umap_order.cpp"
    env = dict(os.environ, LD_LIBRARY_PATH="/opt/geogs/lib")
    build = subprocess.run(["g++", "-O2", "-std=c++17", "-o", str(exe), str(src)], capture_output=True, text=True)
    if build.returncode:
        raise SystemExit(build.stderr)
    ldd = subprocess.run(["ldd", str(exe)], capture_output=True, text=True, env=env).stdout
    gxx = subprocess.run(["g++", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    O = W / "order"
    O.mkdir(exist_ok=True)
    res = {}
    for f in sorted((W / "plan").glob("seq_*.i32")):
        name = f.stem.replace("seq_", "")
        r = subprocess.run([str(exe), str(f), str(O / f"ord_{name}.i32")], capture_output=True, text=True, env=env)
        if r.returncode:
            raise SystemExit(f"umap_order {name}: {r.returncode} {r.stderr}")
        res[name] = json.loads(r.stdout)
    out = dict(gxx=gxx, libstdcxx=[ln.strip() for ln in ldd.splitlines() if "stdc++" in ln], runs=res, written=stamp(),
               scientific_verdict=None)
    jdump(O / "order.json", out)
    log("order", json.dumps(out))


# ------------------------------------------------------------------------------------------------ Open3D's marching cubes tables
# Open3D 0.19 MarchingCubesConst.h: tri_table (rows as hex edge digits, '-' = empty) and edge_shift. ExtractTriangleMesh emits the
# triangle k of cube ci as (edge t[3k], edge t[3k+2], edge t[3k+1]) and makes the vertices of a cube's cut edges in edge-number order
# (a vertex once, by the first cube in its walk that cuts its edge).
TRI_COMPACT = """
- 083 019 183981 12a 08312a 92a029 2832a8a98 3b2 0b28b0 19023b 1b219b98b 3a1ba3 0a108a8ba 3903b9ba9 98aa8b 478 430734 019847
419471731 12a847 34730412a 92a902847 2a9297273794 8473b2 b47b24204 90184723b 47b94b9b2921 3a13ba784 1ba14b1047b4 47890b9bab03
47b4b99ba 954 954083 054150 854835315 12a954 30812a495 52a542402 2a5325354348 95423b 0b208b495 05401523b 21525828b485 a3ba13954
4950818a18ba 54050b5bab03 54858aa8b 978579 930953573 078017157 153357 978957a12 a12950530573 802825857a52 2a5253357 7957893b2
95797292027b 23b018178157 b21b17715 958857a13a3b 5705097b010aba0 ba0b03a50807570 ba57b5 a65 0835a6 9015a6 1831985a6 165261
165126308 965906026 598582526328 23ba65 b08b20a65 01923b5a6 5a61929b298b 63b653513 08b0b50515b6 3b6036065059 65969bb98 5a6478
43047365a 1905a6847 a65197173794 612651478 125526304347 847905065026 739794329596269 3b2784a65 5a647242027b 01947823b5a6
9219b294b7b45a6 8473b53515b6 51b5b610b7b404b 059065036b63847 65969b4797b9 a4964a 4a649a083 a01a60640 83181686461a 149124264
308129249264 024426 832824426 a49a64b23 08228b49a4a6 3b201606461a 64161a48121b8b1 964936913b63 8b1810b61914641 3b6360064 648b68
7a678a89a 0730a709a67a a671a7178180 a67a71173 126168189867 269291679093739 780706602 732672 23ba68a89867 20727b09767a9a7
1801781a767a23b b21b17a61671 896867916b63136 091b67 7807063b0b60 7b6 76b 308b76 019b76 819831b76 a126b7 12a3086b7 2902a96b7
6b72a3a83a98 723627 708760620 276237019 162186198876 a76a17137 a7617a187108 03707a0a96a7 76a7a88a9 684b86 36b306046 86b846901
946963931b36 6846b82a1 12a30b06b046 4b846b0292a9 a93a32943b36463 823842462 042462 190234246438 194142246 8138618466a1 a10a06604
4634386a3039a93 a946a4 49576b 083495b76 50154076b b76834354315 954a1276b 6b712a083495 76b54a42a402 348354325a52b76 723762549
954086062687 362376150540 628687218485158 954a16176137 16a176107870954 40a4a503a6a737a 76a7a854a48a 6956b9b89 36b063056095
0b805b01556b 6b3635531 12a95b9b8b56 0b306b09656912a b85b56805a52025 6b36352a3a53 589528562382 956960062 158180568382628 156216
13616a386569896 a10a06950560 03856a a56 b5a75b b5ab75830 5b75ab190 a75ab7981831 b12b71751 08312717572b 9759279022b7
75272b592328982 25a235375 820852875a25 9015a35373a2 982921872a25752 135375 087071175 903935537 987597 5845a8ab8 5045b05abb30
01984a8aba45 ab4a45b34941314 2512852b8458 04b0b345b2b151b 0250592b5458b85 9452b3 25a352345384 5a2524420 3a235a385458019
5a2524192942 845853351 045105 845853905035 945 4b749b9ab 0834979b79ab 1ab1b414074b 3143481a474bab4 4b79b492b912 9749b791b2b1083
b74b42240 b74b42834324 29a279237749 9a7974a27870207 37a3a274a1a040a 1a2874 491417713 491417081871 403743 487 9a8ab8 30939bb9a
01a0a88ab 31ab3a 12b1b99b8 30939b1292b9 02b80b 32b 23828aa89 9a2092 23828a0181a8 1a2 138918 091 038 -
"""
TRI = [[int(c, 16) for c in t] if t != "-" else [] for t in TRI_COMPACT.split()]
EMIT = [[t[3 * k + j] for k in range(len(t) // 3) for j in (0, 2, 1)] for t in TRI]
BY_LEN = {}
for _ci, _e in enumerate(EMIT):
    BY_LEN.setdefault(len(_e), []).append(_ci)
EDGE_SHIFT = np.array([[0, 0, 0, 0], [1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [1, 0, 1, 1], [0, 1, 1, 0], [0, 0, 1, 1],
                       [0, 0, 0, 2], [1, 0, 0, 2], [1, 1, 0, 2], [0, 1, 0, 2]], np.int64)
EDGE_LUT = np.full((2, 2, 2, 3), -1, np.int64)
for _i, (_dx, _dy, _dz, _a) in enumerate(EDGE_SHIFT):
    EDGE_LUT[_dx, _dy, _dz, _a] = _i
EOFF, ESH = 1 << 15, 16


def edge_code(s, a):
    """global edge (start voxel s (n, 3), axis a (n,)) -> int64."""
    s = np.asarray(s, np.int64)
    return ((((((s[:, 0] + EOFF) << ESH) | (s[:, 1] + EOFF)) << ESH) | (s[:, 2] + EOFF)) << 2) | np.asarray(a, np.int64)


# ------------------------------------------------------------------------------------------------ cubes, units, edges of a mesh
def vertex_grid(V):
    """per vertex and axis: lower voxel-centre plane index, on a plane (within SNAP), nearest plane index. Open3D writes a vertex as
    half + voxel * edge index (+ the offset on its edge axis), so off its edge axis a vertex is exactly on a plane."""
    half = VOXEL * 0.5                                    # = Open3D half_voxel_length (voxel_length_ * 0.5)
    u = (V - half) / VOXEL
    r = np.rint(u)
    on = np.abs(V - (half + VOXEL * r)) <= SNAP
    low = np.where(on, r, np.floor(u)).astype(np.int64)
    return low, on, r.astype(np.int64)


def cube_solutions(vids, g, low, on, r, axis, limit=4):
    """edge-number sequences of Open3D's tables (one per triangle corner, mesh order) that fit a cube with first voxel g: a corner off
    one plane gives its edge, a corner on a voxel centre must be an end of its edge, equal vertices <-> equal edges."""
    n3 = len(vids)
    rows = BY_LEN.get(n3)
    if not rows or n3 == 0:
        return []
    known = np.full(n3, -1, np.int64)
    corner = {}
    for j, v in enumerate(vids):
        if axis[v] >= 0:
            d = low[v] - g
            if (d < 0).any() or (d > 1).any() or EDGE_LUT[d[0], d[1], d[2], axis[v]] < 0:
                return []
            known[j] = EDGE_LUT[d[0], d[1], d[2], axis[v]]
        else:
            c = r[v] - g
            if (c < 0).any() or (c > 1).any():
                return []
            corner[j] = c
    sols = []
    for ci in rows:
        seq = EMIT[ci]
        if any(known[j] >= 0 and known[j] != seq[j] for j in range(n3)):
            continue
        ok = True
        for j, c in corner.items():
            s0 = EDGE_SHIFT[seq[j], :3]
            s1 = s0.copy()
            s1[EDGE_SHIFT[seq[j], 3]] += 1
            if not ((c == s0).all() or (c == s1).all()):
                ok = False
                break
        if ok:
            m, back = {}, {}
            for j in range(n3):
                v = int(vids[j])
                if m.setdefault(v, seq[j]) != seq[j] or back.setdefault(seq[j], v) != v:
                    ok = False
                    break
        if ok and tuple(seq) not in sols:
            sols.append(tuple(seq))
            if len(sols) >= limit:
                break
    return sols


def cube_structure(V, F, chunk=4_000_000, max_window=30):
    """for triangles in Open3D's order: the cube (first voxel g) of every triangle and the cube-edge number of every corner (-1 = not
    settled). g = min over the corners of the lower plane index; a triangle with its three corners on one voxel-centre plane (only when a
    tsdf is exactly 0 at an edge end) may belong to the cube on either side: settled with the triangles around it, the cubes' triangles
    being consecutive and fitting the table. Returns g, e, the unsettled plane triangles {t: candidate cubes}, stats."""
    low, on, r = vertex_grid(V)
    noff = 3 - on.sum(1)
    axis = np.where(noff == 1, np.argmin(on, 1), -1)
    nt = len(F)
    st = dict(on_voxel_centre=int((noff == 0).sum()), off_two_planes=int((noff > 1).sum()))
    g = np.empty((nt, 3), np.int64)
    plane = np.zeros(nt, bool)
    for b in range(0, nt, chunk):
        f = F[b:b + chunk]
        g[b:b + len(f)] = low[f].min(1)
        plane[b:b + len(f)] = (on[f].all(1) & (r[f].min(1) == r[f].max(1))).any(1)
    P = np.nonzero(plane)[0]
    st["plane_triangles"] = int(len(P))

    def cands(t):
        if not plane[t]:
            return [tuple(int(x) for x in g[t])]
        f = F[t]
        ax = [a for a in range(3) if on[f, a].all() and r[f, a].min() == r[f, a].max()]
        out = []
        for s in range(1 << len(ax)):
            gg = g[t].copy()
            for j, a in enumerate(ax):
                if s >> j & 1:
                    gg[a] -= 1
            out.append(tuple(int(x) for x in gg))
        return out
    unsettled, fixed = {}, {}
    i = 0
    while i < len(P):
        t0 = int(P[i])
        w0 = t0
        if w0 > 0 and not plane[w0 - 1]:
            w0 -= 1
            while w0 > 0 and not plane[w0 - 1] and (g[w0 - 1] == g[t0 - 1]).all():
                w0 -= 1
        w1 = t0 + 1
        while True:
            while w1 < nt and plane[w1]:
                w1 += 1
            if w1 < nt:
                gn = g[w1].copy()
                w1 += 1
                while w1 < nt and not plane[w1] and (g[w1] == gn).all():
                    w1 += 1
            if w1 < nt and plane[w1] and w1 - w0 < max_window:
                continue
            break
        C = [cands(t) for t in range(w0, w1)]
        prev_out = tuple(int(x) for x in g[w0 - 1]) if w0 > 0 else None
        next_out = tuple(int(x) for x in g[w1]) if w1 < nt else None
        found = []

        def walk_ok(ga, gb):
            """inside one unit Open3D visits cubes in x, y, z loop order: gb must come after ga there."""
            if ga is None or gb is None:
                return True
            ua, ub = [x // RES for x in ga], [x // RES for x in gb]
            if ua != ub:
                return ga != gb
            la = [x % RES for x in ga]
            lb = [x % RES for x in gb]
            return (la[0] * RES + la[1]) * RES + la[2] < (lb[0] * RES + lb[1]) * RES + lb[2]

        def unit(gg):
            return None if gg is None else tuple(x // RES for x in gg)

        def rec(a, prev, acc, closed):
            """closed: units already left (a unit's triangles are one block in the mesh, so a left unit never comes back)."""
            if len(found) > 4:
                return
            if a == w1:
                if next_out is None or (walk_ok(prev, next_out) and (unit(next_out) == unit(prev) or unit(next_out) not in closed)):
                    found.append(list(acc))
                return
            common = None
            for b in range(a + 1, min(w1, a + 5) + 1):
                cs = set(C[b - 1 - w0])
                common = cs if common is None else (common & cs)
                if not common:
                    break
                for gg in sorted(common):
                    if gg == prev or not walk_ok(prev, gg):
                        continue
                    left = closed
                    if prev is not None and unit(gg) != unit(prev):
                        if unit(gg) in closed:
                            continue
                        left = closed | {unit(prev)}
                    sols = cube_solutions(F[a:b].ravel(), np.array(gg, np.int64), low, on, r, axis)
                    if sols:
                        acc.append((a, b, gg, sols))
                        rec(b, gg, acc, left)
                        acc.pop()
        capped = w1 < nt and plane[w1]
        if not capped:
            rec(w0, prev_out, [], frozenset())
        assign = {tuple((a, b, gg) for a, b, gg, _ in s) for s in found}
        if not capped and len(assign) == 1:
            for a, b, gg, sols in found[0]:
                g[a:b] = gg
                if len(sols) == 1:
                    fixed[(a, b)] = sols[0]
        else:
            for t in range(w0, w1):
                if plane[t]:
                    unsettled[t] = C[t - w0]
        i = int(np.searchsorted(P, w1))
    st["plane_unsettled"] = len(unsettled)
    # corner edge numbers: direct where every corner is off one plane, else the table (cube by cube)
    gs = np.r_[0, np.nonzero((g[1:] != g[:-1]).any(1))[0] + 1] if nt else np.zeros(0, np.int64)
    gl = np.diff(np.r_[gs, nt]) if nt else np.zeros(0, np.int64)
    e = np.full((nt, 3), -1, np.int8)
    for b in range(0, nt, chunk):
        f = F[b:b + chunk]
        gg = g[b:b + chunk]
        for j in range(3):
            v = f[:, j]
            d = low[v] - gg
            okv = (axis[v] >= 0) & (d >= 0).all(1) & (d <= 1).all(1)
            ee = np.full(len(f), -1, np.int64)
            ee[okv] = EDGE_LUT[d[okv, 0], d[okv, 1], d[okv, 2], axis[v][okv]]
            e[b:b + len(f), j] = ee
    gid = np.repeat(np.arange(len(gs)), gl)
    bad = np.unique(gid[(e < 0).any(1)]) if nt else np.zeros(0, np.int64)
    st["cubes"] = int(len(gs))
    st["cubes_by_table"] = int(len(bad))
    # cubes with a corner on a voxel centre: their table readings, narrowed by two exact facts of this mesh until nothing changes:
    # (a) one vertex = one global edge in every cube that uses it; (b) Open3D numbers the vertices a cube creates (first used there, in
    # this mesh's order) one after another in edge-number order, so their ids order their edge numbers.
    cub = []
    for q in bad:
        a0, a1 = int(gs[q]), int(gs[q] + gl[q])
        sols = [fixed[(a0, a1)]] if (a0, a1) in fixed else cube_solutions(F[a0:a1].ravel(), g[a0], low, on, r, axis, limit=256)
        cub.append([a0, a1, F[a0:a1].ravel(), np.array(sols, np.int64).reshape(len(sols), 3 * (a1 - a0))])
    vset = np.unique(np.concatenate([c[2] for c in cub])) if cub else np.zeros(0, np.int64)
    first = {}
    if len(vset):
        pos = np.nonzero(np.isin(F.ravel(), vset))[0]
        u, ix = np.unique(F.ravel()[pos], return_index=True)
        first = dict(zip(u.tolist(), (pos[ix] // 3).tolist()))
    for c in cub:
        a0, a1, vids, S = c
        sh = EDGE_SHIFT[S] if len(S) else np.zeros((0, len(vids), 4), np.int64)
        ge = edge_code((g[a0] + sh[..., :3]).reshape(-1, 3), sh[..., 3].ravel()).reshape(S.shape) if len(S) else np.zeros(S.shape, np.int64)
        uv, col = np.unique(vids, return_index=True)                  # one corner per vertex
        made = [j for v, j in sorted(zip(uv.tolist(), col.tolist())) if a0 <= first.get(v, -1) < a1]
        if len(S) and len(made) > 1:                                  # (b): created here -> edge numbers rise with the vertex ids
            keep = (np.diff(S[:, made], axis=1) > 0).all(1)
            S, ge = S[keep], ge[keep]
        c[3] = S
        c.append(ge)
        c.append(list(zip(uv.tolist(), col.tolist())))
    for _ in range(30):                                               # (a): one global edge per vertex, to a fixed point
        dom = {}
        for a0, a1, vids, S, ge, vc in cub:
            for v, j in vc:
                o = set(ge[:, j].tolist())
                dom[v] = dom[v] & o if v in dom else o
        changed = False
        for c in cub:
            a0, a1, vids, S, ge, vc = c
            keep = np.ones(len(S), bool)
            for v, j in vc:
                keep &= np.isin(ge[:, j], np.fromiter(dom[v], np.int64, len(dom[v])))
            if not keep.all():
                c[3], c[4] = S[keep], ge[keep]
                changed = True
        if not changed:
            break
    unres = 0
    for a0, a1, vids, S, ge, vc in cub:
        if len(S) == 1:
            e[a0:a1] = S[0].astype(np.int8).reshape(-1, 3)
        else:
            e[a0:a1] = -1
            unres += 1
    st["cubes_unsettled"] = unres
    return g, e, unsettled, st


def unit_codes(g):
    return enc(np.floor_divide(g, RES))


def settle_units(code, unsettled, rank_of=None, detail=None):
    """units of the unsettled plane triangles: the candidate unit of the triangle before / after it, else (rank_of = the simulated
    iteration order) the one whose rank lies between (or equals) the ranks of the nearest settled triangles before and after it.
    -> number still open (details appended to detail)."""
    open_ = 0
    for t, cs in sorted(unsettled.items()):
        us = sorted({int(enc(np.floor_divide(np.array(c), RES))) for c in cs})
        if len(us) == 1:
            code[t] = us[0]
            continue
        if t > 0 and int(code[t - 1]) in us:
            code[t] = code[t - 1]
            continue
        if t + 1 < len(code) and (t + 1) not in unsettled and int(code[t + 1]) in us:
            code[t] = code[t + 1]
            continue
        if rank_of is not None:
            t2 = t + 1
            while t2 < len(code) and t2 in unsettled:
                t2 += 1
            lo = rank_of(int(code[t - 1])) if t > 0 else -1
            hi = rank_of(int(code[t2])) if t2 < len(code) else np.inf
            lo = -1 if lo is None else lo
            hi = np.inf if hi is None else hi
            fit = [u for u in us if rank_of(u) is not None and lo <= rank_of(u) <= hi]
            if len(fit) == 1:
                code[t] = fit[0]
                continue
        open_ += 1
        if detail is not None and len(detail) < 50:
            rk = (lambda c: rank_of(int(c))) if rank_of is not None else (lambda c: None)
            detail.append(dict(triangle=int(t), candidates=[[int(x) for x in dec(u)] for u in us], candidate_ranks=[rk(u) for u in us],
                               before=[int(x) for x in dec(code[t - 1])] if t > 0 else None, before_rank=rk(code[t - 1]) if t > 0 else None,
                               after=[int(x) for x in dec(code[t + 1])] if t + 1 < len(code) else None,
                               after_rank=rk(code[t + 1]) if t + 1 < len(code) else None, kept=[int(x) for x in dec(code[t])]))
    return open_


def rank_lookup(order_file):
    oc = enc(np.fromfile(order_file, np.int32).reshape(-1, 3).astype(np.int64))
    srt = np.argsort(oc)
    so = oc[srt]

    def rank_of(c):
        p = int(np.searchsorted(so, c))
        return int(srt[p]) if p < len(so) and so[p] == c else None
    return oc, rank_of


def blocks(code):
    """runs of equal unit code in the mesh order -> (codes, starts, lengths, every unit in one run?)."""
    if not len(code):
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64), True
    st = np.r_[0, np.nonzero(code[1:] != code[:-1])[0] + 1]
    ln = np.diff(np.r_[st, len(code)])
    bc = code[st]
    return bc, st, ln, bool(len(np.unique(bc)) == len(bc))


def check_against(bc, order_file):
    """are the mesh's unit blocks in the simulated iteration order (a subsequence of it)?"""
    oc = enc(np.fromfile(order_file, np.int32).reshape(-1, 3).astype(np.int64))
    srt = np.argsort(oc)
    pos = np.searchsorted(oc[srt], bc)
    pos = np.clip(pos, 0, len(oc) - 1)
    found = oc[srt][pos] == bc
    rank = srt[pos]
    return dict(blocks=int(len(bc)), simulated_units=int(len(oc)), blocks_not_in_simulation=int((~found).sum()),
                increasing=bool(found.all() and (np.diff(rank) > 0).all()),
                order_breaks=int((np.diff(rank) <= 0).sum()) if len(rank) > 1 else 0)


def vertex_edges(F, g, e, nv, chunk=4_000_000):
    """global edge of every vertex from its corners (-1: unsettled or corners that disagree) and the count of disagreements."""
    lo = np.full(nv, np.iinfo(np.int64).max)
    hi = np.full(nv, -1, np.int64)
    for b in range(0, len(F), chunk):
        sl = e[b:b + chunk].ravel().astype(np.int64)
        ok = sl >= 0
        gg = np.repeat(g[b:b + chunk], 3, axis=0)[ok]
        es = EDGE_SHIFT[sl[ok]]
        codes = edge_code(gg + es[:, :3], es[:, 3])
        vids = F[b:b + chunk].ravel()[ok]
        np.minimum.at(lo, vids, codes)
        np.maximum.at(hi, vids, codes)
    vc = np.where((hi >= 0) & (lo == hi), hi, -1)
    return vc, int(((hi >= 0) & (lo != hi)).sum())


def read_mesh(path):
    import open3d as o3d
    m = o3d.io.read_triangle_mesh(str(path))
    V = np.asarray(m.vertices, np.float64).copy()
    F = np.asarray(m.triangles, np.int64).copy()
    C = np.asarray(m.vertex_colors).copy() if m.has_vertex_colors() else None
    return V, F, C


def checkorder(mesh, order_file, out):
    t0 = time.time()
    V, F, _ = read_mesh(mesh)
    g, e, unsettled, cst = cube_structure(V, F)
    code = unit_codes(g)
    oc, rank_of = rank_lookup(order_file)
    open_ = settle_units(code, unsettled, rank_of)
    bc, st, ln, uniq = blocks(code)
    res = dict(mesh=str(mesh), order=str(order_file), triangles=int(len(F)), cubes=cst, units_open=open_, every_unit_one_block=uniq,
               **check_against(bc, order_file), seconds=round(time.time() - t0, 1), scientific_verdict=None)
    jdump(out, res)
    log("checkorder", json.dumps(res))


# ------------------------------------------------------------------------------------------------ CPU: one tile
def tile(wd, k):
    import open3d as o3d
    t0 = time.time()
    W = Path(wd)
    meta, cams, depth = load_inputs(wd)
    lay = json.loads((W / "plan/layout.json").read_text())
    t = lay["tiles"][k]
    E = t["E"]
    Hh, Ww = int(meta["height"]), int(meta["width"])
    vol = o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=VOXEL, sdf_trunc=TRUNC,
                                                       color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    rgb_path = W / "inputs/rgb.npy"
    rgb = np.load(rgb_path, mmap_mode="r") if rgb_path.exists() else None
    color = o3d.geometry.Image(np.zeros((Hh, Ww, 3), np.uint8))
    rows_all, cols_all = np.mgrid[0:Hh, 0:Ww]
    rows_all, cols_all = rows_all.ravel().astype(np.float64), cols_all.ravel().astype(np.float64)
    n_cls = np.zeros(3, np.int64)
    t_depth = 0.0
    for i in range(len(depth)):
        cam = cam_of(cams, i)
        fx, fy, cx, cy, Ex, _ = cam
        t1 = time.time()
        d0 = np.asarray(depth[i]).ravel()
        nz = np.nonzero(d0 > 0)[0]
        img = np.zeros(Hh * Ww, np.float32)
        if len(nz):
            dt, cls = tile_depth(d0[nz], rows_all[nz], cols_all[nz], cam, E)
            img[nz] = dt
            n_cls += np.bincount(cls, minlength=3)
        t_depth += time.time() - t1
        if rgb is not None:
            color = o3d.geometry.Image(np.ascontiguousarray(rgb[i]))
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(color, o3d.geometry.Image(np.ascontiguousarray(img.reshape(Hh, Ww, 1))),
                                                                  depth_trunc=DTRUNC, convert_rgb_to_intensity=False, depth_scale=1.0)
        intr = o3d.camera.PinholeCameraIntrinsic(Ww, Hh, fx, fy, cx, cy)
        vol.integrate(rgbd, intr, Ex)
        if i % 30 == 0 or i == len(depth) - 1:
            log(f"tile {k} view {i + 1}/{len(depth)} rss {rss_now_gb()} GB peak {rss_peak_gb()} GB {time.time() - t0:.0f} s")
    t_int = time.time()
    mesh = vol.extract_triangle_mesh()
    t_ext = time.time()
    peak_after_extract = rss_peak_gb()
    del vol
    try:                                      # hand the freed units back to the system before the mesh work
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except OSError:
        pass
    rss_after_free = rss_now_gb()
    V = np.asarray(mesh.vertices, np.float64).copy()
    F = np.asarray(mesh.triangles, np.int64).copy()
    C = np.asarray(mesh.vertex_colors, np.float64).copy()
    del mesh
    log(f"tile {k} mesh {len(V)} vertices {len(F)} triangles; integrate {t_int - t0:.0f} s, extract {t_ext - t_int:.0f} s")
    g, e, unsettled, cst = cube_structure(V, F)
    code = unit_codes(g)
    ordf = W / f"order/ord_tile{k}.i32"
    rank_of = rank_lookup(ordf)[1] if ordf.exists() else None
    open_detail = []
    units_open = settle_units(code, unsettled, rank_of, open_detail)
    bc, st, ln, uniq = blocks(code)
    sim = check_against(bc, ordf) if ordf.exists() else None
    vc, disagree = vertex_edges(F, g, e, len(V))
    cu = t["core_units"]
    K = dec(bc)
    core = (K[:, 0] >= cu[0]) & (K[:, 0] < cu[1]) & (K[:, 1] >= cu[2]) & (K[:, 1] < cu[3])
    keep = np.repeat(core, ln)
    Fk = F[keep]
    used, inv = np.unique(Fk.ravel(), return_inverse=True)
    T = W / "tiles"
    T.mkdir(exist_ok=True)
    np.savez(T / f"tile{k}.npz", keys=K[core].astype(np.int32), lens=ln[core], F=inv.reshape(-1, 3).astype(np.int32), V=V[used],
             gcode=enc(g[keep]), e=e[keep], vcode=vc[used], C=C[used])
    res = dict(k=k, core_units=cu, E=E, views=len(depth), tile_mesh=dict(vertices=int(len(V)), triangles=int(len(F))),
               kept=dict(blocks=int(core.sum()), triangles=int(keep.sum()), vertices=int(len(used)),
                         vertices_without_edge=int((vc[used] < 0).sum()), corners_unsettled=int((e[keep] < 0).sum())),
               blocks=dict(units_with_triangles=int(len(bc)), every_unit_one_block=uniq, units_open=units_open, open_detail=open_detail,
                           against_simulated_tile_order=sim),
               cubes=dict(cst, vertex_edge_disagreements=disagree),
               pixels=dict(none=int(n_cls[0]), kept=int(n_cls[1]), proxy=int(n_cls[2])),
               seconds=dict(depth_rules=round(t_depth, 1), integrate=round(t_int - t0, 1), extract=round(t_ext - t_int, 1), all=round(time.time() - t0, 1)),
               peak_host_gb=rss_peak_gb(), peak_host_gb_after_extract=peak_after_extract, rss_gb_after_volume_freed=rss_after_free,
               cgroup_peak_gb=cg_peak_gb(),
               libstdcxx=libstdcxx_loaded(), open3d=o3d.__version__, written=stamp(), scientific_verdict=None)
    jdump(T / f"tile{k}.json", res)
    log("tile", json.dumps(res))
    if not uniq or units_open or (sim is not None and not sim["increasing"]):
        raise SystemExit(f"tile {k}: unit blocks not consistent (see tile{k}.json)")


# ------------------------------------------------------------------------------------------------ CPU: merge
def creation_order(F, gcode, e, nv, chunk=6_000_000):
    """Open3D's vertex numbering for triangles in Open3D's order: a vertex is made by the first cube (in triangle order) that cuts its
    edge, within a cube in edge-number order."""
    nt = len(F)
    gs = np.r_[0, np.nonzero(gcode[1:] != gcode[:-1])[0] + 1]
    gid = np.repeat(np.arange(len(gs)), np.diff(np.r_[gs, nt]))
    made = np.zeros(nv, bool)
    parts = []
    b = 0
    while b < nt:
        b1 = min(nt, b + chunk)
        if b1 < nt:
            p = int(np.searchsorted(gs, b1))
            b1 = int(gs[p]) if p < len(gs) else nt
        key = np.repeat(gid[b:b1] - gid[b], 3) * 16 + e[b:b1].ravel().astype(np.int64)
        vs = F[b:b1].ravel()[np.argsort(key, kind="stable")]
        u, first = np.unique(vs, return_index=True)
        keep = ~made[u]
        new = u[keep][np.argsort(first[keep], kind="stable")]
        made[new] = True
        parts.append(new)
        b = b1
    return np.concatenate(parts) if parts else np.zeros(0, np.int64)


def merge(wd, out_ply, out_json, site=None, res=None, depth_dir=None):
    import open3d as o3d
    t0 = time.time()
    W = Path(wd)
    lay = json.loads((W / "plan/layout.json").read_text())
    meta = json.loads((W / "inputs/meta.json").read_text())
    oc = enc(np.fromfile(W / "order/ord_onepiece.i32", np.int32).reshape(-1, 3).astype(np.int64))
    srt = np.argsort(oc)
    Vs, Fs, Gs, Es, VCs, ranks, lens, tile_of_v = [], [], [], [], [], [], [], []
    Cs = []
    voff = 0
    for t in lay["tiles"]:
        z = np.load(W / f"tiles/tile{t['k']}.npz")
        bc = enc(z["keys"].astype(np.int64))
        pos = np.clip(np.searchsorted(oc[srt], bc), 0, len(oc) - 1)
        if not (oc[srt][pos] == bc).all():
            raise SystemExit(f"tile {t['k']}: a core unit with triangles is not in the simulated one-piece units (stop, report)")
        ranks.append(srt[pos])
        lens.append(z["lens"].astype(np.int64))
        Fs.append(z["F"].astype(np.int64) + voff)
        Vs.append(z["V"])
        Cs.append(z["C"] if "C" in z else np.zeros_like(z["V"]))
        Gs.append(z["gcode"])
        Es.append(z["e"])
        VCs.append(z["vcode"])
        tile_of_v.append(np.full(len(z["V"]), t["k"], np.int32))
        voff += len(z["V"])
    rank = np.concatenate(ranks)
    ln = np.concatenate(lens)
    if len(np.unique(rank)) != len(rank):
        raise SystemExit("a unit is in two tiles")
    Fall, Vall, Gall, Eall, VCall, tov = (np.concatenate(x) for x in (Fs, Vs, Gs, Es, VCs, tile_of_v))
    Call = np.concatenate(Cs)
    del Fs, Vs, Gs, Es, VCs, Cs
    st = np.r_[0, np.cumsum(ln)[:-1]]
    o = np.argsort(rank, kind="stable")
    seg_st, seg_ln = st[o], ln[o]
    perm = np.repeat(seg_st - np.r_[0, np.cumsum(seg_ln)[:-1]], seg_ln) + np.arange(int(seg_ln.sum()))
    Ford, Gord, Eord = Fall[perm], Gall[perm], Eall[perm]
    del Fall, Gall, Eall, perm
    vinfo = dict(vertices_without_edge=int((VCall < 0).sum()), corners_unsettled=int((Eord < 0).sum()))
    # one vertex per global edge (the one-piece's rule): the copies of a seam vertex in two tiles share their edge
    rep = np.arange(len(Vall))
    known = np.nonzero(VCall >= 0)[0]
    _, first, inv = np.unique(VCall[known], return_index=True, return_inverse=True)
    rep[known] = known[first][inv]
    vinfo["copies_merged_by_edge"] = int(len(known) - len(first))
    vinfo["copies_with_other_coordinates"] = int((Vall[rep[known]] != Vall[known]).any(1).sum())
    vinfo["copies_with_other_colours"] = int((Call[rep[known]] != Call[known]).any(1).sum())
    if vinfo["copies_with_other_coordinates"] or vinfo["copies_with_other_colours"]:
        raise SystemExit("tile seam differs in coordinates or colours")
    unk = np.nonzero(VCall < 0)[0]
    merged = left = 0
    if len(unk):
        # a vertex whose edge is not settled (tsdf exactly 0 at an edge end): the same exact coordinates in another tile, one there
        key = np.ascontiguousarray(Vall).view(np.dtype((np.void, 24))).ravel()
        for v in unk:
            same = np.nonzero((key == key[v]) & (tov != tov[v]))[0]
            if len(same) and all((tov[same] == t).sum() == 1 for t in np.unique(tov[same])):
                rep[v] = rep[same].min() if rep[same].min() < v else v
                merged += 1
            elif len(same):
                left += 1
    vinfo["vertex_identity"] = "global edge" + ("" if not len(unk) else " (unsettled vertices: exact coordinates in other tiles)")
    vinfo["unsettled_merged_by_coordinates"] = merged
    vinfo["unsettled_left_apart"] = left
    Ford = rep[Ford]
    if vinfo["vertices_without_edge"] == 0 and vinfo["corners_unsettled"] == 0:
        new_order = creation_order(Ford, Gord, Eord, len(Vall))
        vinfo["vertex_order"] = "Open3D's numbering (first cube in triangle order, edge-number order inside a cube)"
    else:
        uq, first = np.unique(Ford.ravel(), return_index=True)
        new_order = uq[np.argsort(first, kind="stable")]
        vinfo["vertex_order"] = "first use in the triangle order (fallback: some corners unsettled)"
    newid = np.empty(len(Vall), np.int64)
    newid[new_order] = np.arange(len(new_order))
    Ffinal = newid[Ford].astype(np.int32)
    Vfinal = Vall[new_order]
    del Ford, Vall, Gord, Eord
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(Vfinal)
    mesh.triangles = o3d.utility.Vector3iVector(Ffinal)
    mesh.vertex_colors = o3d.utility.Vector3dVector(Call[new_order])
    Path(out_ply).parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_triangle_mesh(str(out_ply), mesh)
    tj = [json.loads((W / f"tiles/tile{t['k']}.json").read_text()) for t in lay["tiles"]]
    out = dict(site=site or meta["site"], result=res or meta["result"], prior_scene=meta["prior_scene"],
               source="per-view depth maps, gpu_fl.depthfuse's inputs fused tile by tile (cdgs/tsdf_tiled.py): same voxels in every tile core, "
                      "one-piece triangle and vertex order",
               depth_dir=depth_dir or meta["depth_dir"], box=meta["box"],
               tsdf=dict(voxel_m=VOXEL, sdf_trunc_m=TRUNC, depth_trunc_m=DTRUNC, views=meta["views"], views_with_depth_file=meta["views"] - len(meta["views_without_depth"]),
                         mean_share_of_pixels_in_box=meta["mean_share_of_pixels_in_box"], mean_share_of_pixels_with_depth=meta["mean_share_of_pixels_with_depth"],
                         vertices=int(len(Vfinal)), triangles=int(len(Ffinal))),
               views_without_depth=meta["views_without_depth"],
               tiled=dict(layout=f"{lay['nx']}x{lay['ny']}", L_m=L, M_m=M, EPS_m=EPS, vertices=vinfo,
                          triangle_order="one-piece (simulated unordered_map iteration order)",
                          tiles=[dict(k=x["k"], triangles_kept=x["kept"]["triangles"], seconds=x["seconds"], peak_host_gb=x["peak_host_gb"],
                                      cgroup_peak_gb=x["cgroup_peak_gb"]) for x in tj]),
               seconds=dict(prep=meta["seconds"], tiles=round(sum(x["seconds"]["all"] for x in tj), 1), merge=round(time.time() - t0, 1)),
               peak_host_gb=max([x["peak_host_gb"] for x in tj] + [rss_peak_gb()]), merge_peak_host_gb=rss_peak_gb(), merge_cgroup_peak_gb=cg_peak_gb(),
               written=stamp(), scientific_verdict=None)
    jdump(out_json, out)
    log("merge", json.dumps({k: out[k] for k in ("tsdf", "tiled", "seconds", "peak_host_gb")})[:4000])


# ------------------------------------------------------------------------------------------------ CPU: compare
def compare(a, b, out):
    """triangles as ordered vertex-coordinate triples: same multiset (exact), same order; vertices: count, set, order; colours; file."""
    t0 = time.time()
    Va, Fa, Ca = read_mesh(a)
    Vb, Fb, Cb = read_mesh(b)
    Ta = Va[Fa].reshape(-1, 9)
    Tb = Vb[Fb].reshape(-1, 9)
    res = dict(a=str(a), b=str(b), triangles=[int(len(Ta)), int(len(Tb))], vertices=[int(len(Va)), int(len(Vb))])
    res["same_triangle_order"] = bool(len(Ta) == len(Tb) and np.array_equal(Ta.view(np.uint64), Tb.view(np.uint64)))
    ka = np.ascontiguousarray(Ta).view(np.dtype((np.void, 72))).ravel()
    kb = np.ascontiguousarray(Tb).view(np.dtype((np.void, 72))).ravel()
    sa, sb = np.sort(ka), np.sort(kb)
    res["same_triangle_multiset"] = bool(len(sa) == len(sb) and np.array_equal(sa, sb))
    if not res["same_triangle_multiset"]:
        ina = np.isin(ka, kb, assume_unique=False)
        inb = np.isin(kb, ka, assume_unique=False)
        res["triangles_only_in_a"] = int((~ina).sum())
        res["triangles_only_in_b"] = int((~inb).sum())
        # nearest match by unordered coordinates for a few of them (how far apart)
        if (~ina).any() and (~inb).any():
            from scipy.spatial import cKDTree
            ca = Ta[~ina].reshape(-1, 3, 3).mean(1)
            cb = Tb[~inb].reshape(-1, 3, 3).mean(1)
            dd, jj = cKDTree(cb).query(ca)
            res["only_in_a_nearest_centroid_m"] = dict(max=float(dd.max()), median=float(np.median(dd)))
            res["max_abs_coordinate_difference_of_nearest_pairs_m"] = float(np.abs(Ta[~ina] - Tb[~inb][jj]).max())
    va = np.ascontiguousarray(Va).view(np.dtype((np.void, 24))).ravel()
    vb = np.ascontiguousarray(Vb).view(np.dtype((np.void, 24))).ravel()
    res["distinct_vertex_coordinates"] = [int(len(np.unique(va))), int(len(np.unique(vb)))]
    res["same_vertex_set"] = bool(np.array_equal(np.unique(va), np.unique(vb)))
    res["same_vertex_order"] = bool(len(Va) == len(Vb) and np.array_equal(Va.view(np.uint64), Vb.view(np.uint64)))
    res["same_triangle_colours"] = bool(Ca is not None and Cb is not None and len(Fa) == len(Fb) and np.array_equal(Ca[Fa], Cb[Fb]))
    res["colours_all_zero"] = [None if Ca is None else bool((Ca == 0).all()), None if Cb is None else bool((Cb == 0).all())]
    res["file_bytes"] = [os.path.getsize(a), os.path.getsize(b)]
    import hashlib

    def sha(f):
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for blk in iter(lambda: fh.read(1 << 24), b""):
                h.update(blk)
        return h.hexdigest()
    res["sha256"] = [sha(a), sha(b)]
    res["same_file"] = res["sha256"][0] == res["sha256"][1]
    res["seconds"] = round(time.time() - t0, 1)
    res["scientific_verdict"] = None
    jdump(out, res)
    log("compare", json.dumps(res))


