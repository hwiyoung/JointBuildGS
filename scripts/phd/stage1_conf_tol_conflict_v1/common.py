"""Shared helpers for PHD-STAGE1-CONF-TOL-CONFLICT-v1 (runs inside Docker only).

Container layout: /artifacts/JointBuildGS (read-only artifact root), /task (this task's
payload root, read-write), /repo (repository, read-only), /source (GeoGS pristine source,
GeoGS runtime image steps only).
"""
import datetime
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np

ART = Path(os.environ.get("JBGS_ARTIFACT_ROOT", "/artifacts/JointBuildGS"))
TASK = Path(os.environ.get("JBGS_TASK_ROOT", "/task"))
REPO = Path(os.environ.get("JBGS_REPO_ROOT", "/repo"))
CFG_PATH = Path(os.environ.get("JBGS_EXPERIMENT_CONFIG",
                               str(REPO / "configs/phd/stage1_conf_tol_conflict_v1/experiment.json")))
CFG = json.loads(CFG_PATH.read_text())
C = CFG["constants"]
SCENE = ART / CFG["scene"]["example_scene_relative"]
DIAG = ART / CFG["scene"]["diagnostic_relative"]
BIASED_SCENE = DIAG / "conditions" / CFG["scene"]["diagnostic_biased_condition"] / "scene"
SPARSE_TXT = BIASED_SCENE / "sparse_txt"
DENSE = ART / CFG["scene"]["colmap_dense_relative"]
OUT = TASK / "out"
INP = TASK / "inputs"
LOGS = TASK / "logs"
PROV = TASK / "provenance"
PRIORS = ["L", "M"]
CONDS = ["nominal", "biased"]
REGIONS = ["roof", "wall", "ground", "all"]
# region codes in the per-pixel region map
R_NONE, R_ROOF, R_WALL, R_GROUND, R_OTHER = 0, 1, 2, 3, 4


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256_file(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=_json_default))


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(str(type(o)))


class Receipt:
    """Records command, arguments, versions, timing and failures for one step."""

    def __init__(self, step, extra=None):
        self.step = step
        self.t0 = time.monotonic()
        self.started = now_iso()
        self.extra = extra or {}
        self.failures = []

    def fail(self, where, exc):
        self.failures.append({"where": where, "error": repr(exc)})

    def write(self, status="PASS"):
        import platform
        import sys
        rec = {
            "task_id": CFG["task_id"], "step": self.step, "status": status if not self.failures else "PARTIAL",
            "started_at": self.started, "finished_at": now_iso(), "seconds": time.monotonic() - self.t0,
            "argv": sys.argv, "python": sys.version, "platform": platform.platform(),
            "numpy": np.__version__, "config_sha256": sha256_file(CFG_PATH), "failures": self.failures,
            "scientific_verdict": None,
        }
        for m in ("open3d", "scipy", "laspy", "shapely", "PIL", "matplotlib"):
            try:
                rec[m] = __import__(m).__version__
            except Exception:
                pass
        rec.update(self.extra)
        LOGS.mkdir(parents=True, exist_ok=True)
        write_json(LOGS / f"receipt_{self.step}.json", rec)
        return rec


# ----------------------------------------------------------------------------- cameras
def qvec2rotmat(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w],
        [2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w],
        [2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y]])


def read_cameras_txt(path):
    cams = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        p = line.split()
        cams[int(p[0])] = {"model": p[1], "width": int(p[2]), "height": int(p[3]), "params": [float(x) for x in p[4:]]}
    return cams


def read_images_txt(path):
    imgs = {}
    lines = [l for l in Path(path).read_text().splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        p = line.split()
        if len(p) < 10:
            continue
        imgs[p[9]] = {"id": int(p[0]), "qvec": [float(x) for x in p[1:5]], "tvec": [float(x) for x in p[5:8]],
                      "camera_id": int(p[8]), "name": p[9]}
        # skip the points2D line (may be empty)
        if i < len(lines) and not lines[i].startswith("#") and len(lines[i].split()) < 10:
            i += 1
    return imgs


def load_views():
    """Ordered view list with intrinsics/extrinsics of the exact GeoGS example poses."""
    cams = read_cameras_txt(SPARSE_TXT / "cameras.txt")
    imgs = read_images_txt(SPARSE_TXT / "images.txt")
    names = sorted(n for n in os.listdir(SCENE / "images") if n.lower().endswith(".jpg"))
    views = []
    for n in names:
        im = imgs[n]
        cam = cams[im["camera_id"]]
        assert cam["model"] == "PINHOLE"
        fx, fy, cx, cy = cam["params"]
        R = qvec2rotmat(im["qvec"])
        t = np.array(im["tvec"])
        views.append({"name": n, "stem": Path(n).stem, "W": cam["width"], "H": cam["height"],
                      "K": np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]]), "R": R, "t": t,
                      "C": -R.T @ t, "image_id": im["id"]})
    return views


def pixel_dirs(view, sub=1):
    """Unnormalised camera-frame ray directions (x, y, 1) at pixel centres (u+0.5, v+0.5)."""
    fx, fy, cx, cy = view["K"][0, 0], view["K"][1, 1], view["K"][0, 2], view["K"][1, 2]
    u = (np.arange(0, view["W"], sub) + 0.5 - cx) / fx
    v = (np.arange(0, view["H"], sub) + 0.5 - cy) / fy
    return u.astype(np.float64), v.astype(np.float64)


def world_dir_z(view):
    """World z-component of the unnormalised ray direction R^T (x, y, 1) per full-res pixel.

    Camera-Z depth difference dz along a pixel ray corresponds to a vertical difference
    dz * |world_dir_z|; used for the roof vertical residual.
    """
    u, v = pixel_dirs(view)
    R = view["R"]
    # world = R^T d ; z component = R[0,2]*x + R[1,2]*y + R[2,2]
    return (R[0, 2] * u[None, :] + R[1, 2] * v[:, None] + R[2, 2]).astype(np.float32)


def ray_dirs_world(view):
    """Unnormalised world-frame ray directions R^T (x, y, 1) per full-res pixel: (dx, dy, dz) float32."""
    u, v = pixel_dirs(view)
    R = view["R"]
    out = []
    for k in range(3):
        out.append((R[0, k] * u[None, :] + R[1, k] * v[:, None] + R[2, k]).astype(np.float32))
    return out


def project(view, X):
    """Project world points (N,3) -> (u_idx, v_idx, z_cam) with the +0.5 pixel-centre convention."""
    Xc = (view["R"] @ X.T).T + view["t"]
    z = Xc[:, 2]
    fx, fy, cx, cy = view["K"][0, 0], view["K"][1, 1], view["K"][0, 2], view["K"][1, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = fx * Xc[:, 0] / z + cx
        v = fy * Xc[:, 1] / z + cy
    return np.floor(u).astype(np.int64), np.floor(v).astype(np.int64), z


# ----------------------------------------------------------------------------- COLMAP dense
def read_colmap_array(path):
    """COLMAP mvs .bin: 'W&H&C&' header then float32 slice-major (C,H,W)."""
    with open(path, "rb") as fid:
        width, height, channels = np.genfromtxt(fid, delimiter="&", max_rows=1, usecols=(0, 1, 2), dtype=int)
        fid.seek(0)
        n = 0
        while True:
            b = fid.read(1)
            if b == b"&":
                n += 1
                if n >= 3:
                    break
        a = np.fromfile(fid, np.float32)
    a = a.reshape((width, height, channels), order="F")
    return np.transpose(a, (1, 0, 2)).squeeze()


# ----------------------------------------------------------------------------- statistics
def median_nmad(x):
    m = float(np.median(x))
    s = float(C["nmad_factor"] * np.median(np.abs(x - m)))
    return m, s


def two_pass(x):
    """First-pass median/NMAD, exclude |x-m| > outlier_sigma*s, recompute (m2, s2)."""
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {"n": 0, "m": None, "s": None, "m2": None, "s2": None, "out_frac": None, "n2": 0}
    m, s = median_nmad(x)
    keep = np.abs(x - m) <= C["outlier_sigma"] * s if s > 0 else np.ones(x.size, bool)
    m2, s2 = median_nmad(x[keep]) if keep.any() else (m, s)
    return {"n": int(x.size), "m": m, "s": s, "m2": m2, "s2": s2, "out_frac": float(1 - keep.mean()), "n2": int(keep.sum())}


def quantiles(x, qs=(0.05, 0.25, 0.5, 0.75, 0.95)):
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {f"p{int(q*100):02d}": None for q in qs}
    v = np.quantile(x, qs)
    return {f"p{int(q*100):02d}": float(a) for q, a in zip(qs, v)}


# ----------------------------------------------------------------------------- images
def to_png(path, rgb):
    from PIL import Image
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(str(path), compress_level=3)


def diverging_rgb(arr, vmin, vmax, nan_gray=128):
    """Fixed-range blue-white-red colouring; NaN -> gray."""
    a = np.asarray(arr, dtype=np.float32)
    ok = np.isfinite(a)
    t = np.clip((np.where(ok, a, 0) - vmin) / (vmax - vmin), 0, 1)
    rgb = np.empty(a.shape + (3,), np.uint8)
    # blue (0.13,0.40,0.85) -> white -> red (0.80,0.10,0.10)
    lo = np.array([33, 102, 217], np.float32)
    mid = np.array([255, 255, 255], np.float32)
    hi = np.array([204, 26, 26], np.float32)
    w = (t * 2)[..., None]
    c1 = lo + (mid - lo) * np.clip(w, 0, 1)
    c2 = mid + (hi - mid) * np.clip(w - 1, 0, 1)
    c = np.where(w <= 1, c1, c2)
    rgb[...] = np.clip(c, 0, 255).astype(np.uint8)
    rgb[~ok] = nan_gray
    return rgb


def depth_rgb(depth, vmin, vmax, nan_gray=0):
    """Fixed-range depth colouring (near=warm, far=cool) with matplotlib Spectral."""
    from matplotlib import cm
    a = np.asarray(depth, dtype=np.float32)
    ok = np.isfinite(a) & (a > 0)
    t = np.clip((np.where(ok, a, vmin) - vmin) / (vmax - vmin), 0, 1)
    rgb = (cm.get_cmap("Spectral")(t)[..., :3] * 255).astype(np.uint8)
    rgb[~ok] = nan_gray
    return rgb


def region_rgb(region):
    lut = np.array([[40, 40, 40], [230, 120, 30], [60, 130, 220], [90, 170, 90], [150, 150, 150]], np.uint8)
    return lut[np.clip(region, 0, 4)]


def conflict_rgb(conflict, conf, domain):
    """red = conflict, white = confidence 1 (no conflict), gray = confidence 0, dark = outside domain."""
    rgb = np.full(conflict.shape + (3,), 150, np.uint8)
    rgb[conf == 1] = 255
    rgb[conflict == 1] = (220, 30, 30)
    rgb[~domain] = 70
    return rgb


def downscale_nearest(arr, long_side):
    """Nearest sampling at block centres to a long side of `long_side` pixels."""
    H, W = arr.shape[:2]
    s = long_side / max(H, W)
    w, h = max(1, int(round(W * s))), max(1, int(round(H * s)))
    ys = np.minimum(((np.arange(h) + 0.5) / s).astype(int), H - 1)
    xs = np.minimum(((np.arange(w) + 0.5) / s).astype(int), W - 1)
    return arr[np.ix_(ys, xs)] if arr.ndim == 2 else arr[np.ix_(ys, xs)]
