"""Tolerance per surface kind (roof-like, wall-like) from the registered residuals (PHD-STAGE2-R7-PROPAGATION-v1).

  median m1 and NMAD s1 of the residuals (metres: vertical on roof-like, along the normal on wall-like surfaces)
  one clip: keep |x - m1| <= clip * s1
  median m2 and NMAD s2 of the kept residuals
  width = k * s2; tolerance = max(width, agency accuracy spec) when a spec exists for that surface kind, else width
  ('no spec'). A prior whose walls are not surfaces (airborne LiDAR TIN: steep triangles are boundaries) or whose
  wall sample is empty takes the roof value (recorded as 'roof value').
The registration shift is estimated elsewhere, on inclined (roof-like) faces only; m2 is the median after it."""
import numpy as np

NMAD_C = 1.4826


def robust_width(x, k=2.5, clip=3.0):
    x = np.asarray(x, np.float64)
    x = x[np.isfinite(x)]
    out = dict(n=int(x.size), median_before=None, nmad_before=None, n_kept=0, clipped_share=None, median_after=None,
               nmad_after=None, width=None)
    if x.size == 0:
        return out
    m1 = float(np.median(x))
    s1 = float(NMAD_C * np.median(np.abs(x - m1)))
    keep = np.abs(x - m1) <= clip * s1 if s1 > 0 else np.ones(x.size, bool)
    m2 = float(np.median(x[keep]))
    s2 = float(NMAD_C * np.median(np.abs(x[keep] - m2)))
    out.update(median_before=m1, nmad_before=s1, n_kept=int(keep.sum()), clipped_share=float(1.0 - keep.mean()),
               median_after=m2, nmad_after=s2, width=float(k * s2))
    return out


def tolerance(stats, spec=None, use_spec=True, fallback=None):
    """stats from robust_width. spec: agency accuracy for this surface kind (None = no spec in the data).
    fallback: tolerance dict of the roof when this kind has no sample. Returns dict(tau, width, spec, side)."""
    if stats.get("width") is None:
        if fallback is None:
            return dict(tau=None, width=None, spec=spec, side="no sample")
        return dict(tau=fallback["tau"], width=None, spec=spec, side="roof value (no sample or not a surface)")
    w = stats["width"]
    if spec is None:
        return dict(tau=w, width=w, spec=None, side="data (no spec)")
    if not use_spec:
        return dict(tau=w, width=w, spec=spec, side="data (spec not used)")
    return dict(tau=max(w, spec), width=w, spec=spec, side="spec" if spec > w else "data")
