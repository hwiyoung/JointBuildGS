"""Premise violation (PHD-MAIN-STAGE1-v1 3.2): on observation-error patches (code 3) the image evidence contradicts a prior that is
right; where |MVS - prior| exceeds the discard rule's conflict threshold (k tau) the judgment would release the right prior."""
import numpy as np
from scipy.spatial import cKDTree

OBS_ERROR, SUPPORT = 3, 2


def split(code, premise_value, tau, k, centre, radius=2.0):
    """premise violation = code 3 and |premise value| > k tau; within threshold = code 3 and not a violation;
    band = code-2 patches whose centre lies within radius (3-D) of a violation patch centre. Returns three boolean arrays."""
    code = np.asarray(code)
    pv = np.asarray(premise_value, np.float64)
    t = np.asarray(tau, np.float64)
    viol = (code == OBS_ERROR) & np.isfinite(pv) & (np.abs(pv) > k * t)
    within = (code == OBS_ERROR) & ~viol
    band = np.zeros(len(code), bool)
    if viol.any():
        sup = np.nonzero(code == SUPPORT)[0]
        if len(sup):
            d, _ = cKDTree(np.asarray(centre, np.float64)[viol]).query(np.asarray(centre, np.float64)[sup], distance_upper_bound=radius)
            band[sup[np.isfinite(d) & (d <= radius)]] = True
    return viol, within, band
