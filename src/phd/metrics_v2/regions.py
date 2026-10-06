"""Region split v2 (PHD-MAIN-METRICS-FIX-v1, config regions_v2): |MVS - GT| of a roof-like patch read at its GT points.

  patch_median   per patch: median of the values of its GT points that have one (the MVS height in the point's 0.1 m cell
                 minus the GT height), and the number of such points
  split_v2       codes 2 / 3 and 11 / 12 re-split by |d| <= tau with the same rule for both boundaries; patches with fewer
                 than `min_points` values and wall-like patches keep the v1 code (v1_kept)
scientific_verdict: null."""
import numpy as np

KIND_ROOF = 1


def patch_median(patch, value, n_patches):
    """(median [P] (nan where no value), count [P]) of the finite values grouped by patch index."""
    patch = np.asarray(patch, np.int64)
    value = np.asarray(value, np.float64)
    ok = np.isfinite(value)
    p, v = patch[ok], value[ok]
    med = np.full(n_patches, np.nan)
    cnt = np.bincount(p, minlength=n_patches).astype(np.int64)
    if len(p):
        o = np.lexsort((v, p))
        p, v = p[o], v[o]
        start = np.r_[0, np.nonzero(p[1:] != p[:-1])[0] + 1]
        c = np.diff(np.r_[start, len(p)])
        med[p[start]] = 0.5 * (v[start + (c - 1) // 2] + v[start + c // 2])
    return med, cnt


def split_v2(code_v1, kind, tau, d, n, min_points=5):
    """(code_v2, v1_kept): roof-like patches of code 2 / 3 -> 2 if |d| <= tau else 3; of code 11 / 12 -> 11 if |d| <= tau else 12;
    fewer than min_points values or wall-like -> the v1 code (v1_kept True for those of codes 2, 3, 11, 12)."""
    code_v1 = np.asarray(code_v1)
    code = code_v1.copy()
    split = np.isin(code_v1, (2, 3, 11, 12))
    usable = split & (np.asarray(kind) == KIND_ROOF) & (np.asarray(n) >= min_points) & np.isfinite(d)
    within = np.abs(np.asarray(d, np.float64)) <= np.asarray(tau, np.float64)
    agree = np.isin(code_v1, (2, 3))
    code[usable & agree] = np.where(within[usable & agree], 2, 3)
    code[usable & ~agree] = np.where(within[usable & ~agree], 11, 12)
    return code.astype(code_v1.dtype), split & ~usable
