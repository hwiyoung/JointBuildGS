"""PHD-MAIN-PHOTOFIG-v1 geometry and drawing helpers (jointbuildgs:dev, CPU). scientific_verdict: null.

- meshes: the TSDF result meshes (Open3D binary PLY, double xyz + uchar rgb, uchar-count uint faces) are read by memmap and cut to a
  box before anything is kept (request 2.8); prior meshes = DR/s02_box/<site>/{lod2,als}_mesh.npz + the registration shift.
- sections: a vertical plane through c along the horizontal unit a (s = along, z up), or a horizontal plane z0 (s = along a, d = across).
- photos: the training image S0/fork_inputs/s61/<site>/images/<view>.jpg (1024 x 741, the grid of every per-view map)."""
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
from pf_common import DR, S0, S1, in_rect, jl, xy_to_uv, box  # noqa: E402

_VW = None
GT_DZ = {"B173nb_b10": -0.04224610973760058 - 0.0015611898317018646, "R1rep_b10": -0.026164426286228944 - 0.017642873283073502,
         "B0_b10": -0.0532846142990793 + 0.00947731472977685}   # raw drone LiDAR (laz - shift) -> the study's GT frame (S1/v3/box_gt/<site>/gt_summary.json)


def views():
    global _VW
    if _VW is None:
        from common import Views
        _VW = Views()
    return _VW


def vkey(n):
    V = views()
    for k in (n, n + ".JPG", n + ".jpg"):
        if k in V.ims:
            return k
    raise KeyError(n)


def image(site, n):
    from PIL import Image
    return np.asarray(Image.open(S0 / "fork_inputs/s61" / site / "images" / f"{n}.jpg").convert("RGB"))


def export(site, prior, kind, n):
    return np.load(S0 / "s61/export" / site / prior / kind / f"{n}.npy")


def fork_map(site, kind, n):
    return np.load(S0 / "fork_inputs/s61" / site / "maps" / kind / f"{n}.npy")


def backproject(n, depth, mask=None):
    """camera-Z depth map [741, 1024] -> 3-D points of the pixels (mask), and the pixel indices."""
    V = views(); k = vkey(n)
    R = V.rays(k, np.float64)
    C = V.C(k)
    m = np.isfinite(depth) & (depth > 0)
    if mask is not None:
        m &= mask
    iy, ix = np.nonzero(m)
    X = C + R[iy, ix] * depth[iy, ix][:, None]
    return X, iy, ix


def project(n, X):
    V = views()
    return V.project(vkey(n), X)


def read_ply_mesh_box(path, xy_box, margin=5.0):
    """Open3D binary PLY (double x y z, uchar r g b; faces uchar n + 3 uint) -> V, F inside xy_box + margin (all three vertices)."""
    with open(path, "rb") as f:
        hdr = b""
        while b"end_header" not in hdr:
            hdr += f.readline()
        off = len(hdr)
    lines = hdr.decode().splitlines()
    nv = int([l for l in lines if l.startswith("element vertex")][0].split()[-1])
    nf = int([l for l in lines if l.startswith("element face")][0].split()[-1])
    props = [l.split()[-1] for l in lines if l.startswith("property") and "list" not in l]
    types = [l.split()[1] for l in lines if l.startswith("property") and "list" not in l]
    tmap = {"double": "<f8", "float": "<f4", "uchar": "u1", "int": "<i4", "uint": "<u4"}
    vdt = np.dtype([(p, tmap[t]) for p, t in zip(props, types)])
    fdt = np.dtype([("n", "u1"), ("v", "<u4", (3,))])
    vm = np.memmap(path, dtype=vdt, mode="r", offset=off, shape=(nv,))
    fm = np.memmap(path, dtype=fdt, mode="r", offset=off + nv * vdt.itemsize, shape=(nf,))
    x0, y0, x1, y1 = xy_box[0] - margin, xy_box[1] - margin, xy_box[2] + margin, xy_box[3] + margin
    keep = np.zeros(nv, bool)
    CH = 4_000_000
    for b in range(0, nv, CH):
        x = np.asarray(vm["x"][b:b + CH]); y = np.asarray(vm["y"][b:b + CH])
        keep[b:b + CH] = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
    idx = np.nonzero(keep)[0]
    newid = np.full(nv, -1, np.int64); newid[idx] = np.arange(len(idx))
    V = np.column_stack([np.asarray(vm["x"][idx]), np.asarray(vm["y"][idx]), np.asarray(vm["z"][idx])])
    Fs = []
    for b in range(0, nf, CH):
        fv = np.asarray(fm["v"][b:b + CH]).astype(np.int64)
        ok = keep[fv].all(1)
        Fs.append(newid[fv[ok]])
    F = np.concatenate(Fs) if Fs else np.zeros((0, 3), np.int64)
    return V, F, dict(vertices=int(nv), faces=int(nf), kept_vertices=int(len(V)), kept_faces=int(len(F)))


def prior_mesh(site, prior):
    sh = np.asarray(jl(S0 / "s61/box" / site / prior / "summary.json")["registration"]["shift_applied"], np.float64)
    if prior == "LoD2":
        m = np.load(DR / "s02_box" / site / "lod2_mesh.npz")
        return m["V"] + sh, m["F"][m["tri_type"] != 2]
    m = np.load(DR / "s02_box" / site / "als_mesh.npz")
    return m["V"] + sh, m["F"]


def cut_vertical(V, F, c, a, s_range=None):
    """segments of the mesh on the vertical plane through c (xy) containing the horizontal direction a: list of ((s0, z0), (s1, z1))."""
    a = np.asarray(a, np.float64); a /= np.linalg.norm(a)
    nrm = np.array([-a[1], a[0]])
    d = (V[:, :2] - c) @ nrm
    s = (V[:, :2] - c) @ a
    return _cut(V, F, d, s, V[:, 2], s_range)


def cut_horizontal(V, F, z0, c, a, s_range=None):
    """segments of the mesh on the horizontal plane z = z0: ((s, d) pairs) with s along a and d across (outward = +a rotated)."""
    a = np.asarray(a, np.float64); a /= np.linalg.norm(a)
    nrm = np.array([-a[1], a[0]])
    return _cut(V, F, V[:, 2] - z0, (V[:, :2] - c) @ a, (V[:, :2] - c) @ nrm, s_range)


def _cut(V, F, d, s, h, s_range):
    if len(F) == 0:
        return np.zeros((0, 2, 2))
    df = d[F]
    cross = (df.min(1) < 0) & (df.max(1) > 0)
    Fc = F[cross]
    dd = d[Fc]; ss = s[Fc]; hh = h[Fc]
    segs = []
    for e in ((0, 1), (1, 2), (2, 0)):
        a_, b_ = e
        m = (dd[:, a_] < 0) != (dd[:, b_] < 0)
        t = np.where(m, dd[:, a_] / np.where(m, dd[:, a_] - dd[:, b_], 1.0), np.nan)
        segs.append(np.stack([ss[:, a_] + t * (ss[:, b_] - ss[:, a_]), hh[:, a_] + t * (hh[:, b_] - hh[:, a_])], -1))
    P = np.stack(segs, 1)          # [n, 3, 2], two of three are finite
    good = np.isfinite(P[:, :, 0])
    ok = good.sum(1) >= 2
    P, good = P[ok], good[ok]
    order = np.argsort(~good, axis=1, kind="stable")[:, :2]      # the first two finite edge points
    res = np.take_along_axis(P, order[:, :, None], axis=1)
    if s_range is not None:
        res = res[(res[:, :, 0].max(1) >= s_range[0]) & (res[:, :, 0].min(1) <= s_range[1])]
    return res


def band(P, c, a, s_range, half=0.25):
    a = np.asarray(a, np.float64); a /= np.linalg.norm(a)
    nrm = np.array([-a[1], a[0]])
    d = (P[:, :2] - c) @ nrm
    s = (P[:, :2] - c) @ a
    m = (np.abs(d) <= half) & (s >= s_range[0]) & (s <= s_range[1])
    return m, s


def gt_points(site, xy_box=None, margin=0.0):
    """the study's GT (S1/v3/box_gt/<site>/gt_points.npz: cleaned ULS nadir, study frame) cut to a box."""
    z = np.load(S1 / "v3/box_gt" / site / "gt_points.npz")
    X = z["xyz"]
    m = np.ones(len(X), bool)
    if xy_box is not None:
        m = (X[:, 0] >= xy_box[0] - margin) & (X[:, 0] <= xy_box[2] + margin) & (X[:, 1] >= xy_box[1] - margin) & (X[:, 1] <= xy_box[3] + margin)
    return X[m].astype(np.float64), z["multi"][m], np.nonzero(m)[0]


def zbuffer_visible(n, X, tol=0.25, cell=1):
    """GT points visible in view n: per pixel the nearest camera z; a point is visible when its z is within tol of the pixel's minimum."""
    u, v, z = project(n, X)
    ins = (z > 0) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741)
    iu = np.floor(u[ins] / cell).astype(np.int64); iv = np.floor(v[ins] / cell).astype(np.int64)
    key = iv * 4096 + iu
    zmin = np.full(4096 * 4096 // (cell * cell) + 1, np.inf)
    np.minimum.at(zmin, key, z[ins])
    vis = np.zeros(len(X), bool)
    vis[np.nonzero(ins)[0]] = z[ins] <= zmin[key] + tol
    return vis, u, v, z


def locator(fig, site, xy, rect=(0.86, 0.86, 0.12, 0.12)):
    """small top-right locator: the site's evaluation range only (box axes), the figure place as a dot."""
    b = box(site)
    ax = fig.add_axes(rect)
    u0, u1 = b["eval_u"]; v0, v1 = b["eval_v"]
    ax.plot([u0, u1, u1, u0, u0], [v0, v0, v1, v1, v0], color="0.3", lw=1)
    uv = xy_to_uv(np.atleast_2d(np.asarray(xy, np.float64)))
    ax.plot(uv[:, 0], uv[:, 1], "o", color="#d62728", ms=4)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_xlim(u0 - 3, u1 + 3); ax.set_ylim(v1 + 3, v0 - 3)
    ax.set_title("평가 범위", fontsize=7, pad=1)
    for sp in ax.spines.values():
        sp.set_visible(False)
    return ax


def setup_plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
        try:
            font_manager.fontManager.addfont(f)
        except Exception:  # noqa: BLE001
            pass
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def patch_squares(U, idx):
    h = 0.5 * float(U["sp"])
    c, t1, t2 = U["loc_center"][idx].astype(np.float64), U["loc_t1"][idx].astype(np.float64), U["loc_t2"][idx].astype(np.float64)
    return np.stack([c - h * t1 - h * t2, c + h * t1 - h * t2, c + h * t1 + h * t2, c - h * t1 + h * t2], 1)


def raycast_top(V, F, xy, z0=250.0):
    """z of the first surface hit by a vertical ray from z0 down at xy (NaN = miss)."""
    import open3d as o3d
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(np.asarray(V, np.float32)), o3d.core.Tensor(np.asarray(F, np.uint32)))
    xy = np.asarray(xy, np.float64)
    rays = np.column_stack([xy, np.full(len(xy), z0), np.zeros((len(xy), 2)), -np.ones(len(xy))]).astype(np.float32)
    t = sc.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy().astype(np.float64)
    z = z0 - t
    z[~np.isfinite(t)] = np.nan
    return z


def in_squares(P, U, idx, pad=0.0):
    """points whose plan position falls in the plan squares of the patches idx (centre +- sp/2 along the plan parts of t1, t2)."""
    from scipy.spatial import cKDTree
    h = 0.5 * float(U["sp"]) + pad
    c = U["loc_center"][idx][:, :2].astype(np.float64)
    t1 = U["loc_t1"][idx][:, :2].astype(np.float64); t2 = U["loc_t2"][idx][:, :2].astype(np.float64)
    t1 /= np.maximum(np.linalg.norm(t1, axis=1, keepdims=True), 1e-9); t2 /= np.maximum(np.linalg.norm(t2, axis=1, keepdims=True), 1e-9)
    tr = cKDTree(c)
    owner = np.full(len(P), -1, np.int64)
    cand = tr.query_ball_point(P[:, :2], r=h * 1.5)
    for i, cs in enumerate(cand):
        for j in cs:
            r = P[i, :2] - c[j]
            if abs(r @ t1[j]) <= h and abs(r @ t2[j]) <= h:
                owner[i] = idx[j]
                break
    return owner
