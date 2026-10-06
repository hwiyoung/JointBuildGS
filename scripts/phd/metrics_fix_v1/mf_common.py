"""PHD-MAIN-METRICS-FIX-v1 shared helpers (jointbuildgs:dev). Container paths:
  /art   JointBuildGS-artifacts (ro)      /s0    the stage-0 payload PHD-MAIN-STAGE0-v1 (ro)
  /mt    the trial payload PHD-MAIN-METRICS-TRIAL-v1 (ro)
  /dr    the discard-rule payload (ro)    /prep  the prep-measure payload (ro)
  /out   this task's payload (rw)         /repo  repository (ro)
The frame, view and depth helpers are the stage-0 ones (scripts/phd/main_stage0_v1/common.py; its OUT is not used here).
FCFG = configs/phd/metrics_fix_v1/metrics_fix_v1.json. Region names are those of 2026-10-06 (order 2.3). scientific_verdict: null."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo")
import numpy as np  # noqa: E402

from common import ART, CFG, DENSE, DR, GRID_H, GRID_W, PREP, SURVEY, Views, basis, jdump, log, read_depth_bin, sha256, uv_to_xy, xy_to_uv  # noqa: E402,F401

S0 = Path("/s0")
MT = Path("/mt")
OUT = Path("/out")
FCFG = json.loads(Path("/repo/configs/phd/metrics_fix_v1/metrics_fix_v1.json").read_text())
SITES = {"B0_b10": "B0", "B173nb_b10": "B173nb", "B173_b0": "B173", "R1rep_b10": "R1rep"}
NAME = {-1: "outside", 0: "GT missing", 2: "support agreement", 3: "observation error", 4: "missing agreement", 5: "invisible agreement",
        11: "prior error", 12: "double error", 13: "missing prior error", 14: "invisible prior error"}
KO = {0: "참값 결여 영역", 2: "지지 일치 영역", 3: "관측 오류 영역", 4: "결측 일치 영역", 5: "비가시 일치 영역", 11: "사전 정보 오류 영역",
      12: "이중 오류 영역", 13: "결측 사전 정보 오류 영역", 14: "비가시 사전 정보 오류 영역"}
COL = {0: "#c8c8c8", 2: "#2ca02c", 3: "#bcbd22", 4: "#1f77b4", 5: "#9467bd", 11: "#d62728", 12: "#8c564b", 13: "#ff7f0e", 14: "#e377c2"}
ORDER = [2, 3, 4, 5, 11, 12, 13, 14, 0]
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}


class Timer:
    def __init__(self):
        self.t0 = time.time()
        self.marks = {}

    def mark(self, name):
        self.marks[name] = round(time.time() - self.t0, 1)
        return self.marks[name]


def setup_fonts():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
        try:
            font_manager.fontManager.addfont(f)
        except Exception:
            pass
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def boxes():
    return json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"]


def in_eval_uv(xy, box):
    uv = xy_to_uv(np.asarray(xy, np.float64)[:, :2])
    return (uv[:, 0] >= box["eval_u"][0]) & (uv[:, 0] <= box["eval_u"][1]) & (uv[:, 1] >= box["eval_v"][0]) & (uv[:, 1] <= box["eval_v"][1])


def label_source(site, prior, n):
    """per patch: True where the label comes from the ULS supplement (B0 sites; the stage-0 regions rule), else False."""
    D = S0 / "s61/box_gt" / site
    if site.startswith("B0") and (D / f"labels_uls_{prior}.npz").exists():
        G = np.load(D / f"labels_{prior}.npz")
        Gu = np.load(D / f"labels_uls_{prior}.npz")
        return (G["label"] < 0) & (Gu["label"] >= 0)
    return np.zeros(n, bool)


def owner_rows(site, prior, uls_patch):
    """the GT ownership rows of every patch's label source: (array name, point, patch, value, kind) lists. Non-B0 sites: one set on
    gt_points; B0: gt_owner_<prior> (gt_primary) for the gt_clean-labelled patches, gt_owner_uls_<prior> (gt_points) for the others."""
    D = S0 / "s61/box_gt" / site
    out = []
    if site.startswith("B0") and (D / f"gt_owner_uls_{prior}.npz").exists():
        o = np.load(D / f"gt_owner_{prior}.npz")
        m = ~uls_patch[o["patch"]]
        out.append(("gt_primary", o["point"][m], o["patch"][m].astype(np.int64), o["value"][m], o["kind"][m]))
        o = np.load(D / f"gt_owner_uls_{prior}.npz")
        m = uls_patch[o["patch"]]
        out.append(("gt_points", o["point"][m], o["patch"][m].astype(np.int64), o["value"][m], o["kind"][m]))
    else:
        o = np.load(D / f"gt_owner_{prior}.npz")
        out.append(("gt_points", o["point"], o["patch"].astype(np.int64), o["value"], o["kind"]))
    return out


def mvs_views(site):
    """names (with .JPG) of the geometric depth maps of the site's box MVS."""
    d = PREP / "mvs" / f"box_{site}" / "stereo/depth_maps"
    return sorted(p.name[: -len(".geometric.bin")] for p in d.glob("*.geometric.bin"))
