"""Spread classes along a measuring line (PHD-MAIN-METRICS-TRIAL-v1, config 'spread').

For a GT point X, its line direction D (roof-like: +z; wall-like: the outward wall normal) and the offset s_W of the wrong data
W from X along the line, the result is near the GT point when the result mesh crosses the line within +-t of X, and near W
when it crosses within +-t of X + s_W D, with t = min(t_max, frac |s_W|) (trial: 0.5 m, 1/2), so the two windows never
overlap. Four classes:
  GT_SIDE    near GT only           WRONG_SIDE  near W only
  BOTH       near both              NEITHER     near neither (holes included)
spread share = (WRONG_SIDE + BOTH) / all; points with |s_W| < ambiguous_m (trial 0.2 m) are 'ambiguous' (reported apart).
scientific_verdict: null."""
import numpy as np

GT_SIDE, WRONG_SIDE, BOTH, NEITHER = 0, 1, 2, 3
NAMES = {GT_SIDE: "gt_side", WRONG_SIDE: "wrong_side", BOTH: "both", NEITHER: "neither"}


def threshold(s_w, t_max=0.5, frac=0.5):
    return np.minimum(t_max, frac * np.abs(np.asarray(s_w, np.float64)))


def classify(near_gt, near_w):
    near_gt = np.asarray(near_gt, bool)
    near_w = np.asarray(near_w, bool)
    c = np.full(near_gt.shape, NEITHER, np.int8)
    c[near_gt & ~near_w] = GT_SIDE
    c[~near_gt & near_w] = WRONG_SIDE
    c[near_gt & near_w] = BOTH
    return c


def four_way(scene, X, D, s_w, t_max=0.5, frac=0.5):
    """classes [N] and the thresholds t [N] of the points X with line directions D and wrong-data offsets s_w."""
    t = threshold(s_w, t_max, frac)
    near_gt = scene.window(X, D, 0.0, t)
    near_w = scene.window(X, D, s_w, t)
    return classify(near_gt, near_w), t


def shares(c, mask=None):
    """counts and shares of the four classes and the spread share (wrong side + both) over the selected points."""
    c = np.asarray(c)
    if mask is not None:
        c = c[np.asarray(mask, bool)]
    n = int(len(c))
    out = dict(points=n)
    for k, nm in NAMES.items():
        out[nm] = round(float((c == k).mean()), 4) if n else None
    out["spread"] = round(float(np.isin(c, (WRONG_SIDE, BOTH)).mean()), 4) if n else None
    return out
