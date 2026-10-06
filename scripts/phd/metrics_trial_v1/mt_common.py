"""PHD-MAIN-METRICS-TRIAL-v1 shared helpers (jointbuildgs:dev). Container paths:
  /art   JointBuildGS-artifacts (ro)      /s0    the stage-0 payload PHD-MAIN-STAGE0-v1 (ro)
  /dr    the discard-rule payload (ro)    /prep  the prep-measure payload (ro)
  /out   this task's payload (rw)         /repo  repository (ro)
The frame, view and depth helpers are the stage-0 ones (scripts/phd/main_stage0_v1/common.py; its OUT is not used here).
MCFG = configs/phd/metrics_trial_v1/metrics_trial_v1.json. scientific_verdict: null."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo")
import numpy as np  # noqa: E402

from common import CFG, DR, GRID_H, GRID_W, PREP, SURVEY, Views, jdump, log, read_depth_bin, sha256, uv_to_xy, xy_to_uv  # noqa: E402,F401

S0 = Path("/s0")
OUT = Path("/out")
MCFG = json.loads(Path("/repo/configs/phd/metrics_trial_v1/metrics_trial_v1.json").read_text())
SITE = MCFG["site"]
B173 = "DEBY_LOD2_4959326"
NAMES = {-1: "outside", 0: "no GT", 2: "measured agreement", 3: "image wrong", 4: "unmeasured agreement (missing)",
         5: "unmeasured agreement (invisible)", 11: "prior wrong", 12: "both wrong", 13: "unmeasured wrong prior (missing)",
         14: "unmeasured wrong prior (invisible)"}
KO = {0: "참값 없음", 2: "잰 일치", 3: "영상이 틀린 곳", 4: "못 잰 일치(결측)", 5: "못 잰 일치(비가시)", 11: "사전 정보가 틀린 곳",
      12: "둘 다 틀린 곳", 13: "못 잰 곳의 틀린 사전 정보(결측)", 14: "못 잰 곳의 틀린 사전 정보(비가시)"}
COL = {0: "#c8c8c8", 2: "#2ca02c", 3: "#bcbd22", 4: "#1f77b4", 5: "#9467bd", 11: "#d62728", 12: "#8c564b", 13: "#ff7f0e", 14: "#e377c2"}
ORDER = [2, 3, 4, 5, 11, 12, 13, 14, 0]


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


def in_eval_uv(xy, box):
    uv = xy_to_uv(np.asarray(xy, np.float64)[:, :2])
    return (uv[:, 0] >= box["eval_u"][0]) & (uv[:, 0] <= box["eval_u"][1]) & (uv[:, 1] >= box["eval_v"][0]) & (uv[:, 1] <= box["eval_v"][1])


def boxes():
    return json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"]
