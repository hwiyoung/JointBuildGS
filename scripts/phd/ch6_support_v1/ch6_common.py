"""PHD-CH6-SUPPORT-v1 shared helpers (jointbuildgs:dev, CPU). Container paths (run_queue.sh):
  /out this task's payload (rw)   /dr discard-rule payload   /prep prep-measure payload   /s0 stage-0   /s1 stage-1   /s3 stage-3
The stage-0 helpers (frame, ranges) are imported from scripts/phd/main_stage0_v1/common.py unchanged.
CCFG = configs/phd/ch6_support_v1/ch6_support_v1.json (definitions written before any result). scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo")
from common import CFG, DR, OUT, PREP, inside_range, jdump, log, uv_to_xy, xy_to_uv  # noqa: E402,F401
from src.phd.prior_propagation_v6 import rule  # noqa: E402

S0 = Path("/s0"); S1 = Path("/s1"); S3 = Path("/s3")
CCFG = json.loads(Path("/repo/configs/phd/ch6_support_v1/ch6_support_v1.json").read_text())
RANGES = CCFG["task5_judgment"]["ranges"]
BOXES = {"B0_b10": "B0", "B173nb_b10": "B173nb", "B173_b0": "B173", "R1rep_b10": "R1rep"}
FIX = {"B0_b10": "B0", "B173nb_b10": "R2", "B173_b0": "R2", "R1rep_b10": "R1"}
PRIORS = ("LoD2", "ALS")
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "B173_b0": "B173만", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
BOXDEF = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"]
RNGDEF = json.loads((PREP / "step01/ranges.json").read_text())


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


def in_eval_rect(uv, bid):
    b = BOXDEF[bid]
    return (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1])


def labels_of(gt_dir, prior, rid):
    """the discard task's label reading: B0 boxes use gt_clean, else the ULS supplement."""
    G = np.load(gt_dir / f"labels_{prior}.npz")
    lab, med, tau, ex = G["label"].astype(np.int8), G["gt_med"].astype(np.float64), G["tau"].astype(np.float64), G["excluded"].astype(bool)
    if rid.startswith("B0") and (gt_dir / f"labels_uls_{prior}.npz").exists():
        Gu = np.load(gt_dir / f"labels_uls_{prior}.npz")
        use = (lab < 0) & (Gu["label"] >= 0)
        lab = np.where(use, Gu["label"], lab).astype(np.int8); med = np.where(use, Gu["gt_med"], med)
        ex = ex | (use & Gu["excluded"].astype(bool))
    return lab, med, tau, ex


def codes_from(lab, med, tau, ex, st, mvs, inr, prior):
    """stage-0 region rule + the stage-1 code split on the patch medians (ranges): codes 2/3/4/5 and 11/12/13/14, premise."""
    code = np.full(len(lab), -1, np.int8)
    code[inr] = 0
    g = inr & ~ex & (lab >= 0)
    off = ~(np.abs(mvs - med) <= tau)
    S, M, I = rule.ST_SUPPORT, rule.ST_MISSING, rule.ST_INVISIBLE
    for lv, base in ((0, 2), (1, 11)):
        m = g & (lab == lv)
        code[m & (st == S) & ~off] = base
        code[m & (st == S) & off] = base + 1
        code[m & (st == M)] = 4 if lv == 0 else 13
        code[m & (st == I)] = 5 if lv == 0 else 14
    thr = tau * (1.0 if prior == "LoD2" else 2.0)
    premise = (code == 3) & (np.abs(mvs) > thr)
    return code, premise


ITEMS = [("both_right", "두 자료가 모두 맞는 곳"), ("prior_wrong_1to4", "사전 정보가 조금 틀린 곳 (1~4τ)"),
         ("prior_wrong_4plus", "사전 정보가 틀린 곳 (4τ 이상)"), ("image_wrong", "영상이 틀린 곳 (판정 문턱 안)"),
         ("undecidable_passed", "판단할 수 없는 곳 (신뢰도 통과)"), ("unseen_missing_right", "보지 못한 곳: 결측, 사전 정보 맞음"),
         ("unseen_missing_wrong", "보지 못한 곳: 결측, 사전 정보 틀림"), ("unseen_invisible_right", "보지 못한 곳: 비가시, 사전 정보 맞음"),
         ("unseen_invisible_wrong", "보지 못한 곳: 비가시, 사전 정보 틀림"), ("both_wrong", "두 자료가 모두 틀린 곳 (기록)")]
ITEM_IDX = {k: i for i, (k, _) in enumerate(ITEMS)}


def items_from(code, premise, med, tau):
    it = np.full(len(code), -1, np.int8)
    ratio = np.abs(med) / np.where(tau > 0, tau, np.nan)
    it[code == 2] = ITEM_IDX["both_right"]
    it[(code == 11) & (ratio < 4)] = ITEM_IDX["prior_wrong_1to4"]
    it[(code == 11) & (ratio >= 4)] = ITEM_IDX["prior_wrong_4plus"]
    it[(code == 3) & ~premise] = ITEM_IDX["image_wrong"]
    it[(code == 3) & premise] = ITEM_IDX["undecidable_passed"]
    it[code == 4] = ITEM_IDX["unseen_missing_right"]
    it[code == 13] = ITEM_IDX["unseen_missing_wrong"]
    it[code == 5] = ITEM_IDX["unseen_invisible_right"]
    it[code == 14] = ITEM_IDX["unseen_invisible_wrong"]
    it[code == 12] = ITEM_IDX["both_wrong"]
    return it


def footprint_index(fp_json, xy, buffer_m=1.0):
    """index of the footprint containing xy (else the nearest within buffer_m), -1 outside; and the building names."""
    from shapely import STRtree, points
    from shapely.geometry import Polygon
    F = json.loads(Path(fp_json).read_text())
    F = F["footprints"] if isinstance(F, dict) else F
    polys = [Polygon(f["ring_local"]).buffer(0) for f in F]
    names = [f["building"] for f in F]
    tree = STRtree(polys)
    P = points(np.asarray(xy, np.float64))
    out = np.full(len(xy), -1, np.int64)
    pi, gi = tree.query(P, predicate="within")
    out[pi] = gi
    rest = np.where(out < 0)[0]
    if len(rest):
        ri, gi2 = tree.query_nearest(P[rest], max_distance=buffer_m, return_distance=False, all_matches=False)
        out[rest[ri]] = gi2
    return out, names
