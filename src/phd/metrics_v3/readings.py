"""Roof readings of the geometric accuracy v2 (PHD-MAIN-METRICS-FIX-v1, config height_range): faces up to `steep_deg` are read
as the vertical height difference (highest crossing of the vertical line - z_GT), steeper faces as the signed distance along the
prior-face normal to the nearest crossing within `max_d` (MeshScene.along). scientific_verdict: null."""
import numpy as np


def roof_reading(scene, X, normal, slope_deg, steep_deg=17.0, max_d=2.0):
    """(value [N], steep [N] bool): per point the vertical difference (gentle) or the normal distance (steep); nan without a crossing."""
    X = np.asarray(X, np.float64).reshape(-1, 3)
    normal = np.asarray(normal, np.float64).reshape(-1, 3)
    steep = np.asarray(slope_deg, np.float64) > steep_deg
    out = np.full(len(X), np.nan)
    g = ~steep
    if g.any():
        out[g] = scene.highest_z(X[g, :2]) - X[g, 2]
    if steep.any():
        out[steep] = scene.along(X[steep], normal[steep], max_d)
    return out, steep
