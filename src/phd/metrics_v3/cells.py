"""Height of a point path at GT points (PHD-MAIN-METRICS-TRIAL-v1, config 'bias_paths'): z = median of the path's points in
the GT point's cell (0.1 m, at least 3 points). Points are added in batches (one view at a time) and only those falling in a
cell that holds a query point are kept. scientific_verdict: null."""
import numpy as np


class CellMedian:
    def __init__(self, query_xy, cell=0.1):
        q = np.asarray(query_xy, np.float64).reshape(-1, 2)
        self.cell = float(cell)
        self.lo = np.floor(q.min(0) / cell) * cell - cell          # cells on multiples of `cell`
        self.nx = int(np.ceil((q[:, 0].max() - self.lo[0]) / cell)) + 2
        self.ny = int(np.ceil((q[:, 1].max() - self.lo[1]) / cell)) + 2
        self.qkey = self.key(q)
        self.ukey = np.unique(self.qkey)
        self.keys, self.zs = [], []

    def key(self, xy):
        q = np.floor((np.asarray(xy, np.float64) - self.lo) / self.cell).astype(np.int64)
        ok = (q[:, 0] >= 0) & (q[:, 0] < self.nx) & (q[:, 1] >= 0) & (q[:, 1] < self.ny)
        k = q[:, 1] * self.nx + q[:, 0]
        k[~ok] = -1
        return k

    def add(self, P):
        P = np.asarray(P, np.float64).reshape(-1, 3)
        P = P[np.isfinite(P).all(1)]
        if not len(P):
            return 0
        k = self.key(P[:, :2])
        i = np.searchsorted(self.ukey, k)
        keep = (k >= 0) & (i < len(self.ukey))
        keep[keep] &= self.ukey[i[keep]] == k[keep]
        self.keys.append(k[keep])
        self.zs.append(P[keep, 2].astype(np.float32))
        return int(keep.sum())

    def medians(self, min_n=3):
        """(z median [Q] (nan below min_n points), point count [Q]) at the query points."""
        if not self.keys or not sum(len(k) for k in self.keys):
            return np.full(len(self.qkey), np.nan), np.zeros(len(self.qkey), np.int64)
        k = np.concatenate(self.keys)
        z = np.concatenate(self.zs).astype(np.float64)
        o = np.lexsort((z, k))
        k, z = k[o], z[o]
        start = np.r_[0, np.nonzero(k[1:] != k[:-1])[0] + 1]
        cnt = np.diff(np.r_[start, len(k)])
        med = 0.5 * (z[start + (cnt - 1) // 2] + z[start + cnt // 2])
        uk = k[start]
        i = np.searchsorted(uk, self.qkey)
        hit = (i < len(uk))
        hit[hit] &= uk[i[hit]] == self.qkey[hit]
        m = np.full(len(self.qkey), np.nan)
        n = np.zeros(len(self.qkey), np.int64)
        m[hit] = med[i[hit]]
        n[hit] = cnt[i[hit]]
        m[n < min_n] = np.nan
        return m, n
