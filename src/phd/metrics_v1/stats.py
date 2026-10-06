"""Summary statistics of the metrics (PHD-MAIN-METRICS-TRIAL-v1). scientific_verdict: null."""
import numpy as np

NMAD_C = 1.4826


def _r(x, nd=4):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def robust(x):
    """signed median, NMAD, median |x|, 68.3 % and 95 % quantiles of |x| over the finite values."""
    x = np.asarray(x, np.float64)
    x = x[np.isfinite(x)]
    if not len(x):
        return dict(n=0, median=None, nmad=None, abs_median=None, abs_q683=None, abs_q95=None)
    m = float(np.median(x))
    a = np.abs(x)
    return dict(n=int(len(x)), median=_r(m), nmad=_r(NMAD_C * np.median(np.abs(x - m))), abs_median=_r(np.median(a)),
                abs_q683=_r(np.quantile(a, 0.683)), abs_q95=_r(np.quantile(a, 0.95)))


def within(d, ts=(0.2, 0.5)):
    """shares of the distances <= each threshold (inf counts as beyond; nan is dropped)."""
    d = np.asarray(d, np.float64)
    d = d[~np.isnan(d)]
    out = dict(n=int(len(d)))
    for t in ts:
        out[f"le_{t:g}"] = round(float((d <= t).mean()), 4) if len(d) else None
    return out
