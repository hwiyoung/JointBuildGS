"""Edge band of the roof accuracy (PHD-MAIN-METRICS-TRIAL-v1, config 'edge_band').

A roof point lies in the edge band when the range (max - min) of the GT heights within `radius` (horizontal) around it
exceeds `height_range` (trial: 0.5 m, 0.3 m). Computed on a raster: per `cell` the max and min z of all GT points, then a
disk maximum / minimum filter of radius round(radius / cell) cells; a query point reads the filtered range of its cell.
Note: on a plane of slope a the range within r is about 2 r tan(a), so with the trial values every point of a face steeper
than ~17 degrees is in the band (kept as given; reported by slope). scientific_verdict: null."""
import numpy as np
import scipy.ndimage as ndi


def disk(r):
    i = np.arange(-r, r + 1)
    return (i[:, None] ** 2 + i[None, :] ** 2) <= r * r


def height_range(X_all, X_query, radius=0.5, cell=0.1):
    """range of GT z within `radius` of each query point's cell (nan where no GT point lies within)."""
    X_all = np.asarray(X_all, np.float64)
    X_query = np.asarray(X_query, np.float64)
    lo = np.floor((np.minimum(X_all[:, :2].min(0), X_query[:, :2].min(0)) - radius) / cell) * cell - cell   # cells on multiples of `cell`
    hi = np.maximum(X_all[:, :2].max(0), X_query[:, :2].max(0)) + radius + cell
    nx, ny = (np.ceil((hi - lo) / cell).astype(int) + 1)
    ia = np.floor((X_all[:, :2] - lo) / cell).astype(np.int64)
    zmax = np.full((ny, nx), -np.inf)
    zmin = np.full((ny, nx), np.inf)
    np.maximum.at(zmax, (ia[:, 1], ia[:, 0]), X_all[:, 2])
    np.minimum.at(zmin, (ia[:, 1], ia[:, 0]), X_all[:, 2])
    fp = disk(int(round(radius / cell)))
    fmax = ndi.maximum_filter(zmax, footprint=fp, mode="constant", cval=-np.inf)
    fmin = ndi.minimum_filter(zmin, footprint=fp, mode="constant", cval=np.inf)
    iq = np.floor((X_query[:, :2] - lo) / cell).astype(np.int64)
    r = fmax[iq[:, 1], iq[:, 0]] - fmin[iq[:, 1], iq[:, 0]]
    r[~np.isfinite(r)] = np.nan
    return r


def edge_band(X_all, X_query, radius=0.5, range_m=0.3, cell=0.1):
    """(in_band [N] bool, range [N]) of the query points."""
    r = height_range(X_all, X_query, radius, cell)
    return np.nan_to_num(r, nan=0.0) > range_m, r


# ---------------------------------------------------------------- v2 (PHD-MAIN-METRICS-FIX-v1, config edge_band_v2)
def edge_band_v2(X_all, X_query, slope_deg, radius=0.5, range_m=0.3, cell=0.1, cap_deg=80.0):
    """(in_band [N] bool, adjusted range [N]): the band of v1 with the height range a plane of slope theta makes within the radius
    (2 r tan(theta), theta = the owning prior face's slope, capped) taken off before the 0.3 m test. On the 0.1 m raster a plane
    still adds about cell x tan(theta) (one cell's own z span), so faces steeper than ~70 degrees reach the band again."""
    r = height_range(X_all, X_query, radius, cell)
    th = np.radians(np.minimum(np.asarray(slope_deg, np.float64), cap_deg))
    adj = np.nan_to_num(r, nan=0.0) - 2.0 * radius * np.tan(th)
    return adj > range_m, adj
