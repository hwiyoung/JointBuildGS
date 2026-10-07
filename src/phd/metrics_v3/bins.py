"""Size bins of the correction rate (PHD-MAIN-METRICS-FIX-v1, config accepted_proposals.2_size_bins).

  merge_small     groups of consecutive bins: a bin with fewer than `min_points` points is merged into the next larger bin
                  (the last group into the previous one), so that every group reaches min_points where the total allows
  boundary        correction boundary = lower edge of the first group from which every larger group has a rate >= 0.5
scientific_verdict: null."""
import numpy as np


def merge_small(counts, min_points=10_000):
    """list of lists of bin indices (in order)."""
    groups, cur, tot = [], [], 0
    for i, c in enumerate(counts):
        cur.append(i)
        tot += int(c)
        if tot >= min_points:
            groups.append(cur)
            cur, tot = [], 0
    if cur:
        if groups:
            groups[-1].extend(cur)
        else:
            groups.append(cur)
    return groups


def boundary(rates, lower_edges, half=0.5):
    """lower edge of the first group from which every group (that has a rate) has rate >= half; None when there is none."""
    rates = [None if r is None or not np.isfinite(r) else float(r) for r in rates]
    for i in range(len(rates)):
        rest = [r for r in rates[i:] if r is not None]
        if rest and all(r >= half for r in rest) and rates[i] is not None:
            return lower_edges[i]
    return None
