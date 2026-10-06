"""Gaussian-level readings (PHD-MAIN-METRICS-TRIAL-v1): what the training-view mesh cannot show.
  count_near   number of selected Gaussians within r of each query point (mechanism layer, unseen walls: r = 0.25 m)
  top_raster   highest GT surface per cell with a 3 x 3 cell maximum (floaters)
  floaters     Gaussians (opacity >= 0.5) more than `above` over the highest GT surface of their cell
scientific_verdict: null."""
import numpy as np
import scipy.ndimage as ndi
from scipy.spatial import cKDTree


def count_near(points, gxyz, r=0.25):
    points = np.asarray(points, np.float64).reshape(-1, 3)
    gxyz = np.asarray(gxyz, np.float64).reshape(-1, 3)
    if not len(points) or not len(gxyz):
        return np.zeros(len(points), np.int64)
    return np.asarray(cKDTree(gxyz).query_ball_point(points, r, return_length=True, workers=-1), np.int64)


class TopRaster:
    """max GT z per `cell` (local XY), then a (2 k + 1)^2 cell maximum; cells with no GT within it read `fallback`."""

    def __init__(self, X, lo, hi, cell=1.0, k=1, fallback=None):
        X = np.asarray(X, np.float64)
        self.lo = np.asarray(lo, np.float64)[:2]
        self.cell = float(cell)
        self.nx, self.ny = (np.ceil((np.asarray(hi, np.float64)[:2] - self.lo) / cell).astype(int) + 1)
        ix, iy, ok = self.index(X[:, :2])
        g = np.full((self.ny, self.nx), -np.inf)
        np.maximum.at(g, (iy[ok], ix[ok]), X[ok, 2])
        g = ndi.maximum_filter(g, size=2 * k + 1, mode="constant", cval=-np.inf)
        self.fallback = float(X[ok, 2].max()) if fallback is None and ok.any() else fallback
        self.empty = ~np.isfinite(g)
        g[self.empty] = self.fallback
        self.grid = g

    def index(self, xy):
        q = np.floor((np.asarray(xy, np.float64) - self.lo) / self.cell).astype(np.int64)
        ok = (q[:, 0] >= 0) & (q[:, 0] < self.nx) & (q[:, 1] >= 0) & (q[:, 1] < self.ny)
        return np.clip(q[:, 0], 0, self.nx - 1), np.clip(q[:, 1], 0, self.ny - 1), ok

    def top(self, xy):
        ix, iy, ok = self.index(xy)
        return np.where(ok, self.grid[iy, ix], np.nan)


def floaters(gxyz, opacity, raster, in_range, above=3.0, opacity_min=0.5):
    """bool [N]: opacity >= opacity_min, inside the range, z > top(cell) + above."""
    gxyz = np.asarray(gxyz, np.float64)
    top = raster.top(gxyz[:, :2])
    return (np.asarray(opacity) >= opacity_min) & np.asarray(in_range, bool) & np.isfinite(top) & (gxyz[:, 2] > top + above)
