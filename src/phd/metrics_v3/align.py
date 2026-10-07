"""Common GT height shift (PHD-MAIN-STAGE1-v1 3.1): the per-box pixel selection of the gt_clean method and the pooled median."""
import numpy as np


def select_pixels(d_range, d_wide, min_px=5000):
    """one box, one pass: the bare-ground differences inside the box range, or inside range + margin when fewer than min_px
    (s04_gt_v6.align_px rule). Returns (differences, source)."""
    d_range = np.asarray(d_range, np.float64)
    if d_range.size < min_px:
        return np.asarray(d_wide, np.float64), "range + 20 m"
    return d_range, "range"


def pooled_median(parts):
    """median of the pooled differences of all boxes (each pixel once, no weighting by box). Returns (median, count)."""
    d = np.concatenate([np.asarray(p, np.float64).ravel() for p in parts]) if parts else np.zeros(0)
    return (float(np.median(d)) if d.size else 0.0), int(d.size)


def two_pass(diff_fn, boxes, min_px=5000, passes=2):
    """reference implementation for tests: diff_fn(box, shift) -> (d_range, d_wide) of that box with the GT moved by shift;
    per pass every box's selection is pooled, the median added to the shift. Returns (total shift, per-pass records)."""
    total, rec = 0.0, []
    for k in range(passes):
        parts = []
        for b in boxes:
            dr, dw = diff_fn(b, total)
            d, src = select_pixels(dr, dw, min_px)
            parts.append(d)
        med, n = pooled_median(parts)
        rec.append(dict(pass_=k + 1, pixels=n, median=med))
        total += med
    return total, rec
