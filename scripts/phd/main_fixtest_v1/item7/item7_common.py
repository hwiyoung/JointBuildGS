"""PHD-MAIN-FIXTEST-v1 일 7 (곁일, 그림 unseen_1의 듬성듬성한 칸): shared paths and copied helpers (jointbuildgs:dev, CPU; run_item7.sh).
Container paths: /ph = phase-payloads/phd (ro), /item7 = this item's payload (rw), /fig and /tab = this task's figure and table folders
(rw), /repo (ro), /fonts (ro). Nothing of the fill task (SL, its repo docs) is written. Copied functions name their source.
scientific_verdict: null."""
import json
import struct
import time
from pathlib import Path

import numpy as np

PH = Path("/ph")
S0 = PH / "main_stage0_v1/PHD-MAIN-STAGE0-v1"
S1 = PH / "main_stage1_v1/PHD-MAIN-STAGE1-v1"
SL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
MF = PH / "metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1"
DR = PH / "main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
OUT = Path("/item7")
FIG = Path("/fig")
TAB = Path("/tab")
SITE = "B173nb_b10"
VW = SL / "work/virtual/metrics" / SITE            # the fill task's virtual-view wall flags and values (read only)
EXPORT = S0 / "s61/export" / SITE / "LoD2"          # the stage-0 measurement's per-view maps (locmap = location of each pixel)
BOX = S0 / "s61/box" / SITE / "LoD2"                # the stage-0 unit store (units.npz) and unit-view pairs
SCENE = S0 / "fork_inputs/s61" / SITE / "scene_LoD2/sparse/0"
GRID_W, GRID_H = 1024, 741
CELL = 0.25
# the three panels of unseen_1 (figs_fl_walls.PANELS[1] with figs_fl_common.col_res for LoD2)
PANELS = (("본 방법", "prop_LoD2_s0", "본 방법 (씨앗 0)"), ("2차원 가우시안 스플래팅", "imgonly_2dgs_s0", "2차원 가우시안 스플래팅"),
          ("GeoGS", "trust_LoD2_fix1", "GeoGS"))


def kst(fmt="%Y-%m-%d %H:%M:%S"):
    """copied from scripts/phd/main_fill_v1/figs_fl_common.py kst."""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=9))).strftime(fmt) + (" KST" if "%Y" in fmt else "")


def log(*a):
    print(kst("%H:%M:%S"), *a, flush=True)


def jdump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


def jload(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


class Timer:
    def __init__(self):
        self.t0 = self.t = time.time()
        self.marks = {}

    def mark(self, name):
        now = time.time()
        self.marks[name] = round(now - self.t, 2)
        self.t = now
        return self.marks[name]


def wall_grid(s, z, cell=CELL):
    """copied from scripts/phd/main_fill_v1/figs_fl_walls.py wall_grid (lines 25-31; itself figs_bl.wall_grid)."""
    s0, z0 = np.floor(s.min() / cell) * cell - 3 * cell, np.floor(z.min() / cell) * cell - 3 * cell
    i = np.floor((z - z0) / cell).astype(int)
    j = np.floor((s - s0) / cell).astype(int)
    H, W = i.max() + 4, j.max() + 4
    return i, j, (H, W), (s0, s0 + W * cell, z0, z0 + H * cell)


def wall_place():
    """copied from figs_fl_walls.wall_place (lines 34-38): the place (S1/defs/fig_views_v1.json 'unseen_face'), unseen.npz, face mask."""
    w = json.loads((S1 / "defs/fig_views_v1.json").read_text())["sites"][SITE]["unseen_face"]
    un = np.load(S1 / "defs" / SITE / "unseen.npz")
    face = un["surf_ext"] == w["surf_ext"]
    return w, un, face


def frame(w):
    return tuple(np.asarray(w[k], np.float64) for k in ("centre", "t", "normal"))


# ------------------------------------------------------------------------------------------------ COLMAP (copied)
def read_cameras_bin(p):
    """copied from scripts/phd/main_stage0_v1/common.py read_cameras_bin."""
    cams = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            npar = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12}[model]
            cams[cid] = dict(model=model, w=int(w), h=int(h), p=np.array(struct.unpack("<" + "d" * npar, f.read(8 * npar))))
    return cams


def qR(q):
    """copied from scripts/phd/main_stage0_v1/common.py qR."""
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def read_images_bin(p):
    """copied from scripts/phd/main_stage0_v1/common.py read_images_bin (without the 2-D points)."""
    ims = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack("<i", f.read(4))[0]
            q = np.array(struct.unpack("<dddd", f.read(32)))
            t = np.array(struct.unpack("<ddd", f.read(24)))
            cid = struct.unpack("<i", f.read(4))[0]
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            n2 = struct.unpack("<Q", f.read(8))[0]
            f.read(24 * n2)
            ims[name.decode()] = dict(id=iid, q=q, t=t, cam=cid, R=qR(q))
    return ims


class Cameras:
    """the fork scene's PINHOLE camera (the measurement grid 1024 x 741, common.Views.K) and the 937-model poses of its images; pixel
    (r, c) has its centre ray R^T ((c + 0.5 - cx) / fx, (r + 0.5 - cy) / fy, 1) as common.Views.rays."""

    def __init__(self):
        cams = read_cameras_bin(SCENE / "cameras.bin")
        self.ims = read_images_bin(SCENE / "images.bin")
        c = cams[1]
        assert c["model"] == 1 and (c["w"], c["h"]) == (GRID_W, GRID_H), c
        self.K = c["p"]

    def key(self, stem):
        return f"{stem}.jpg"

    def C(self, stem):
        im = self.ims[self.key(stem)]
        return -im["R"].T @ im["t"]

    def rays(self, stem, r, c):
        fx, fy, cx, cy = self.K
        R = self.ims[self.key(stem)]["R"]
        xn = (np.asarray(c, np.float64) + 0.5 - cx) / fx
        yn = (np.asarray(r, np.float64) + 0.5 - cy) / fy
        return np.stack([xn, yn, np.ones_like(xn)], -1) @ R          # = R^T (xn, yn, 1)

    def project(self, stem, X):
        im = self.ims[self.key(stem)]
        Xc = X @ im["R"].T + im["t"]
        fx, fy, cx, cy = self.K
        return fx * Xc[:, 0] / Xc[:, 2] + cx, fy * Xc[:, 1] / Xc[:, 2] + cy, Xc[:, 2]


# ------------------------------------------------------------------------------------------------ figures
def setup_fonts():
    """copied from scripts/phd/main_fill_v1/figs_fl_common.py setup_fonts (itself s1_common.setup_fonts)."""
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


def gt_use():
    """copied from figs_fl_common.gt_use (itself figs_bl.gt_use, lines 252-258): the evaluation GT points of the site."""
    G = np.load(S1 / "defs" / SITE / "gt_classes.npz")
    X = [G["xyz_gt_points"][G["use_gt_points"]].astype(np.float64)]
    if "xyz_gt_primary" in G.files:
        X.append(G["xyz_gt_primary"].astype(np.float64))
    return np.concatenate(X)
