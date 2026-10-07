"""Result surfaces for the metrics (PHD-MAIN-METRICS-TRIAL-v1; configs/phd/metrics_trial_v1/metrics_trial_v1.json).

A result surface is a triangle mesh: a training's TSDF mesh, the registered prior surface put in place of the result, or the
prior fused through the same TSDF path. MeshScene wraps an Open3D ray-casting scene and gives the four readings the metrics
use along a measuring line:
  highest_z  the highest crossing of the vertical line through (x, y)            (roof height, stage-0 quick check)
  window     does the mesh cross the line within +-half of a point on it          (spread classes: near GT, near W)
  along      signed distance to the nearest crossing along +-D within a range    (edge band and walls)
  distance   unsigned 3-D distance to the mesh                                    (completeness)
An empty mesh crosses nothing and is infinitely far. Coordinates are the local frame (float32 inside Open3D).
scientific_verdict: null."""
import numpy as np

CHUNK = 4_000_000


class MeshScene:
    def __init__(self, V, F):
        import open3d as o3d
        self.o3d = o3d
        V = np.ascontiguousarray(V, np.float32)
        F = np.ascontiguousarray(F, np.uint32)
        self.n_tri = int(len(F))
        self.sc = o3d.t.geometry.RaycastingScene()
        if self.n_tri:
            self.sc.add_triangles(o3d.core.Tensor(V), o3d.core.Tensor(F))

    @classmethod
    def from_ply(cls, path):
        import open3d as o3d
        m = o3d.io.read_triangle_mesh(str(path))
        return cls(np.asarray(m.vertices), np.asarray(m.triangles))

    def cast(self, O, D):
        """first crossing distance t >= 0 of rays O + t D (D unit); inf where none."""
        O = np.asarray(O, np.float32).reshape(-1, 3)
        D = np.broadcast_to(np.asarray(D, np.float32), O.shape)
        if not self.n_tri or not len(O):
            return np.full(len(O), np.inf, np.float32)
        out = np.empty(len(O), np.float32)
        for b in range(0, len(O), CHUNK):
            r = np.concatenate([O[b:b + CHUNK], D[b:b + CHUNK]], 1)
            out[b:b + CHUNK] = self.sc.cast_rays(self.o3d.core.Tensor(np.ascontiguousarray(r)))["t_hit"].numpy()
        return out

    def highest_z(self, xy, z0=250.0):
        """z of the highest crossing of the vertical line through each (x, y); nan where the line misses the mesh."""
        xy = np.asarray(xy, np.float64).reshape(-1, 2)
        O = np.column_stack([xy, np.full(len(xy), z0)])
        t = self.cast(O, np.array([0.0, 0.0, -1.0]))
        return np.where(np.isfinite(t), z0 - t.astype(np.float64), np.nan)

    def window(self, X, D, s, half):
        """True where the mesh crosses the line X + u D within u in [s - half, s + half] (half > 0)."""
        X = np.asarray(X, np.float64).reshape(-1, 3)
        D = np.broadcast_to(np.asarray(D, np.float64), X.shape)
        s = np.broadcast_to(np.asarray(s, np.float64), (len(X),))
        half = np.broadcast_to(np.asarray(half, np.float64), (len(X),))
        ok = half > 0
        O = X + (s - half)[:, None] * D
        t = self.cast(O, D)
        return ok & np.isfinite(t) & (t <= 2.0 * half)

    def along(self, X, D, max_d):
        """signed distance u (along D) of the nearest crossing of the line X + u D with |u| <= max_d; nan where none."""
        X = np.asarray(X, np.float64).reshape(-1, 3)
        D = np.broadcast_to(np.asarray(D, np.float64), X.shape)
        tp = self.cast(X, D).astype(np.float64)
        tn = self.cast(X, -D).astype(np.float64)
        tp[tp > max_d] = np.inf
        tn[tn > max_d] = np.inf
        u = np.where(tp <= tn, tp, -tn)
        u[~np.isfinite(np.minimum(tp, tn))] = np.nan
        return u

    def distance(self, X):
        X = np.asarray(X, np.float32).reshape(-1, 3)
        if not self.n_tri or not len(X):
            return np.full(len(X), np.inf, np.float32)
        out = np.empty(len(X), np.float32)
        for b in range(0, len(X), CHUNK):
            out[b:b + CHUNK] = self.sc.compute_distance(self.o3d.core.Tensor(np.ascontiguousarray(X[b:b + CHUNK]))).numpy()
        return out
