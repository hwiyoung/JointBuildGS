"""PHD-MAIN-PREP-MEASURE-v1 shared helpers (jointbuildgs:dev). Paths are container paths:
  /art   JointBuildGS-artifacts (read-only)        /out  task payload (read-write)       /repo  repository (read-only)
No training. scientific_verdict: null."""
import hashlib
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
ART = Path("/art")
OUT = Path("/out")
REPO = Path("/repo")
CFG = json.loads((REPO / "configs/phd/main_prep_measure_v1/prep_v5.json").read_text())
SHIFT = np.array(CFG["frame"]["world_shift_xyz_m"], np.float64)
ZB = float(CFG["frame"]["z_bridge_als_lod2_m"])
SURVEY = ART / CFG["survey_relative"]
DENSE = ART / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
ALS_TILES = [ART / f"phase-payloads/p0-audit/data/raw/als/{t}.laz" for t in ("690_5335", "690_5336", "691_5335", "691_5336")]
ULS = ART / "phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz"
FUSED = ART / "phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply"
GRID_W, GRID_H = 1024, 741


def sha256(p, chunk=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def jdump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


# ------------------------------------------------------------------------------------------------ frame
def basis():
    a = np.deg2rad(CFG["frame"]["u_axis_angle_degrees_ccw_from_easting"])
    return np.array([[np.cos(a), np.sin(a)], [np.sin(a), -np.cos(a)]])


def xy_to_uv(xy):
    return np.asarray(xy, np.float64)[..., :2] @ basis().T


def uv_to_xy(uv):
    return np.asarray(uv, np.float64) @ basis()


def global_to_local(E, N, H=None):
    out = [np.asarray(E, np.float64) - SHIFT[0], np.asarray(N, np.float64) - SHIFT[1]]
    if H is not None:
        out.append(np.asarray(H, np.float64) - SHIFT[2])
    return out


# ------------------------------------------------------------------------------------------------ ranges
def range_polygon(r):
    """local XY polygon [4, 2] of a range dict (uv_box or xy_rect)."""
    if r["kind"] == "uv_box":
        u0, u1 = r["u_m"]; v0, v1 = r["v_m"]
        return uv_to_xy(np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1]]))
    x0, y0, x1, y1 = r["xy_rect_local"]
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


def widen(r, m):
    q = dict(r)
    if r["kind"] == "uv_box":
        q["u_m"] = [r["u_m"][0] - m, r["u_m"][1] + m]; q["v_m"] = [r["v_m"][0] - m, r["v_m"][1] + m]
    else:
        x0, y0, x1, y1 = r["xy_rect_local"]; q["xy_rect_local"] = [x0 - m, y0 - m, x1 + m, y1 + m]
    return q


def inside_range(xy, r):
    xy = np.asarray(xy, np.float64)
    if r["kind"] == "uv_box":
        uv = xy_to_uv(xy)
        return (uv[:, 0] >= r["u_m"][0]) & (uv[:, 0] < r["u_m"][1]) & (uv[:, 1] >= r["v_m"][0]) & (uv[:, 1] < r["v_m"][1])
    x0, y0, x1, y1 = r["xy_rect_local"]
    return (xy[:, 0] >= x0) & (xy[:, 0] < x1) & (xy[:, 1] >= y0) & (xy[:, 1] < y1)


def bbox_xy(r):
    P = range_polygon(r)
    return P.min(0), P.max(0)


def load_ranges():
    return json.loads((OUT / "step01" / "ranges.json").read_text())


# ------------------------------------------------------------------------------------------------ COLMAP
def read_cameras_bin(p):
    cams = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            npar = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12}[model]
            cams[cid] = dict(model=model, w=int(w), h=int(h), p=np.array(struct.unpack("<" + "d" * npar, f.read(8 * npar))))
    return cams


def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def read_images_bin(p, with_points=False):
    ims = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack("<i", f.read(4))[0]
            q = np.array(struct.unpack("<dddd", f.read(32))); t = np.array(struct.unpack("<ddd", f.read(24)))
            cid = struct.unpack("<i", f.read(4))[0]
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            n2 = struct.unpack("<Q", f.read(8))[0]
            raw = f.read(24 * n2)
            rec = dict(id=iid, q=q, t=t, cam=cid, name=name.decode(), R=qR(q))
            if with_points:
                arr = np.frombuffer(raw, dtype=np.dtype([("x", "<f8"), ("y", "<f8"), ("pid", "<i8")]))
                rec["xys"] = np.stack([arr["x"], arr["y"]], 1); rec["pids"] = arr["pid"].copy()
            ims[rec["name"]] = rec
    return ims


class Views:
    """the 937 posed images; native grid intrinsics (1024 x 741)."""

    def __init__(self, sparse=DENSE / "sparse"):
        self.cams = read_cameras_bin(Path(sparse) / "cameras.bin")
        self.ims = read_images_bin(Path(sparse) / "images.bin")
        self.names = sorted(self.ims)
        c = self.cams[self.ims[self.names[0]]["cam"]]
        assert c["model"] == 1, "PINHOLE expected"
        fx, fy, cx, cy = c["p"]
        self.W0, self.H0 = c["w"], c["h"]
        sx, sy = GRID_W / self.W0, GRID_H / self.H0
        self.K = np.array([fx * sx, fy * sy, cx * sx, cy * sy])
        self.K0 = np.array([fx, fy, cx, cy])

    def R(self, n):
        return self.ims[n]["R"]

    def t(self, n):
        return self.ims[n]["t"]

    def C(self, n):
        return -self.ims[n]["R"].T @ self.ims[n]["t"]

    def tilt(self, n):
        ax = self.ims[n]["R"].T @ np.array([0, 0, 1.0])
        return float(np.degrees(np.arccos(np.clip(-ax[2], -1, 1))))

    def rays(self, n, dtype=np.float32):
        """R^T (x_n, y_n, 1) at the native pixel centres [H, W, 3] (camera-Z convention)."""
        fx, fy, cx, cy = self.K
        R = self.R(n)
        xn = ((np.arange(GRID_W) + 0.5 - cx) / fx)[None, :]
        yn = ((np.arange(GRID_H) + 0.5 - cy) / fy)[:, None]
        return np.stack([(R[0, k] * xn + R[1, k] * yn + R[2, k]).astype(dtype) for k in range(3)], -1)

    def project(self, n, X):
        """local XYZ [N, 3] -> (u, v native pixels, z camera)."""
        Xc = X @ self.R(n).T + self.t(n)
        z = Xc[:, 2]
        fx, fy, cx, cy = self.K
        with np.errstate(divide="ignore", invalid="ignore"):
            u = fx * Xc[:, 0] / z + cx; v = fy * Xc[:, 1] / z + cy
        return u, v, z


def read_depth_bin(p):
    data = Path(p).read_bytes(); off = 0
    for _ in range(3):
        off = data.find(b"&", off, 100) + 1
    w, h, c = map(int, data[:off].decode("ascii").split("&")[:3])
    return np.frombuffer(data, dtype="<f4", offset=off, count=w * h).reshape((w, h), order="F").T.copy()


# ------------------------------------------------------------------------------------------------ point clouds
def read_als(lo, hi, classes=(2, 6)):
    """ALS points in the local box [lo, hi] (XY, local frame): XYZ local (with the +45.7 bridge) and class."""
    import laspy
    out_xyz, out_c, out_multi = [], [], []
    for p in ALS_TILES:
        las = laspy.read(str(p))
        E = np.asarray(las.x); N = np.asarray(las.y)
        x, y = E - SHIFT[0], N - SHIFT[1]
        stem = p.stem.split("_"); te0, tn0 = float(stem[0]) * 1000, float(stem[1]) * 1000
        nominal = (E >= te0) & (E < te0 + 1000) & (N >= tn0) & (N < tn0 + 1000)
        m = nominal & (x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1])
        cls = np.asarray(las.classification)
        if classes is not None:
            m &= np.isin(cls, classes)
        z = np.asarray(las.z) + ZB - SHIFT[2]
        out_xyz.append(np.stack([x[m], y[m], z[m]], 1)); out_c.append(cls[m])
        out_multi.append(np.asarray(las.number_of_returns)[m] > 1)
        del las
    return np.concatenate(out_xyz), np.concatenate(out_c), np.concatenate(out_multi)


def read_uls(lo, hi, chunk=20_000_000):
    """ULS nadir points in the local box (XYZ local, number_of_returns > 1 flag)."""
    import laspy
    xs, ms = [], []
    with laspy.open(str(ULS)) as f:
        for pts in f.chunk_iterator(chunk):
            x = np.asarray(pts.x) - SHIFT[0]; y = np.asarray(pts.y) - SHIFT[1]
            m = (x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1])
            if m.any():
                z = np.asarray(pts.z)[m] - SHIFT[2]
                xs.append(np.stack([x[m], y[m], z], 1)); ms.append(np.asarray(pts.number_of_returns)[m] > 1)
    return np.concatenate(xs), np.concatenate(ms)


def read_fused_rows(stride=16):
    """dim_dense.ply rows 0, stride, 2 stride, ... (local frame) and their original row numbers."""
    with open(FUSED, "rb") as f:
        hdr = b""
        while b"end_header" not in hdr:
            hdr += f.readline()
        off = len(hdr)
    n = int([l for l in hdr.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
    dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    mm = np.memmap(FUSED, dtype=dt, mode="r", offset=off, shape=(n,))
    rows = np.arange(0, n, stride, dtype=np.int64)
    p = mm[::stride]
    return np.stack([p["x"], p["y"], p["z"]], 1).astype(np.float32), rows


# ------------------------------------------------------------------------------------------------ raycasting
class Scene:
    def __init__(self, V, F):
        import open3d as o3d
        self.o3d = o3d
        self.scene = o3d.t.geometry.RaycastingScene()
        self.scene.add_triangles(o3d.core.Tensor(np.asarray(V, np.float32)), o3d.core.Tensor(np.asarray(F, np.uint32)))

    def cast(self, C, D):
        """C [3] origin, D [H, W, 3] camera-Z rays -> (t camera-Z depth [H, W] (inf no hit), tri id [H, W] (-1))."""
        o3d = self.o3d
        H, W, _ = D.shape
        r = np.concatenate([np.broadcast_to(np.asarray(C, np.float32), (H, W, 3)), D.astype(np.float32)], -1).reshape(-1, 6)
        ans = self.scene.cast_rays(o3d.core.Tensor(r))
        t = ans["t_hit"].numpy().reshape(H, W)
        tri = ans["primitive_ids"].numpy().astype(np.int64).reshape(H, W)
        tri[~np.isfinite(t)] = -1
        return t, tri

    def cast_points(self, O, D):
        o3d = self.o3d
        r = np.concatenate([np.asarray(O, np.float32), np.asarray(D, np.float32)], 1)
        ans = self.scene.cast_rays(o3d.core.Tensor(r))
        t = ans["t_hit"].numpy(); tri = ans["primitive_ids"].numpy().astype(np.int64)
        tri[~np.isfinite(t)] = -1
        return t, tri

    def closest(self, X):
        o3d = self.o3d
        ans = self.scene.compute_closest_points(o3d.core.Tensor(np.asarray(X, np.float32)))
        return ans["points"].numpy(), ans["primitive_ids"].numpy().astype(np.int64)
