"""Point-cloud summary numbers (PHD-MAIN-METRICS-TRIAL-v1, config 'summary_numbers'): records for comparison with other
studies, not used for the research questions.
  sample_mesh   area-weighted random points of a mesh (density per m2, fixed seed)
  voxel_thin    one point per voxel (the point nearest the voxel centre)
  chamfer_pcf   Chamfer distance both ways and their mean; precision, completeness and F1 at thresholds
  pca_normals   normals of query points from the cloud's points within a radius (smallest-variance direction)
  m3c2          M3C2 (Lague et al. 2013): per core point the mean position of each cloud inside a cylinder along the normal;
                distance = compared - reference
scientific_verdict: null."""
import numpy as np
from scipy.spatial import cKDTree


def tri_areas(V, F):
    V = np.asarray(V, np.float64)
    F = np.asarray(F, np.int64)
    return 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)


def sample_mesh(V, F, density, seed=0):
    """round(area x density) points, triangles drawn by area, uniform inside the triangle."""
    V = np.asarray(V, np.float64)
    F = np.asarray(F, np.int64)
    if not len(F):
        return np.zeros((0, 3))
    A = tri_areas(V, F)
    n = int(round(A.sum() * density))
    rng = np.random.default_rng(seed)
    cs = np.cumsum(A)
    tri = np.minimum(np.searchsorted(cs, rng.random(n) * cs[-1], side="right"), len(F) - 1)
    r1 = np.sqrt(rng.random(n))[:, None]
    r2 = rng.random(n)[:, None]
    f = F[tri]
    return (1 - r1) * V[f[:, 0]] + r1 * (1 - r2) * V[f[:, 1]] + r1 * r2 * V[f[:, 2]]


def voxel_thin(X, size):
    """indices of one point per voxel of edge `size`: the point nearest the voxel centre."""
    X = np.asarray(X, np.float64)
    if not len(X):
        return np.zeros(0, np.int64)
    q = np.floor(X / size)
    d = np.linalg.norm(X - (q + 0.5) * size, axis=1)
    q = q.astype(np.int64)
    q -= q.min(0)
    dims = q.max(0) + 1
    key = (q[:, 0] * dims[1] + q[:, 1]) * dims[2] + q[:, 2]
    o = np.lexsort((d, key))
    first = np.r_[True, key[o][1:] != key[o][:-1]]
    return np.sort(o[first])


def chamfer_pcf(R, G, ts=(0.2, 0.5)):
    R = np.asarray(R, np.float64)
    G = np.asarray(G, np.float64)
    out = dict(n_result=int(len(R)), n_gt=int(len(G)))
    dRG = cKDTree(G).query(R, workers=-1)[0] if len(R) and len(G) else np.full(len(R), np.inf)
    dGR = cKDTree(R).query(G, workers=-1)[0] if len(R) and len(G) else np.full(len(G), np.inf)
    a = float(dRG.mean()) if len(dRG) else None
    b = float(dGR.mean()) if len(dGR) else None
    out.update(chamfer_result_to_gt=None if a is None else round(a, 4), chamfer_gt_to_result=None if b is None else round(b, 4),
               chamfer_mean=None if a is None or b is None else round(0.5 * (a + b), 4))
    for t in ts:
        p = float((dRG <= t).mean()) if len(dRG) else None
        c = float((dGR <= t).mean()) if len(dGR) else None
        f = 2 * p * c / (p + c) if p is not None and c is not None and p + c > 0 else (0.0 if p is not None and c is not None else None)
        out[f"precision_{t:g}"] = None if p is None else round(p, 4)
        out[f"completeness_{t:g}"] = None if c is None else round(c, 4)
        out[f"f1_{t:g}"] = None if f is None else round(f, 4)
    return out, dRG, dGR


def _neighbours(tree, C, r, P):
    L = tree.query_ball_point(C, r, workers=-1)
    lens = np.fromiter((len(x) for x in L), np.int64, len(L))
    idx = np.fromiter((i for x in L for i in x), np.int64, int(lens.sum()))
    owner = np.repeat(np.arange(len(C)), lens)
    return owner, idx


def pca_normals(Q, cloud, radius, min_n=10, chunk=20000, tree=None):
    """unit normals [N, 3] (nan where fewer than min_n cloud points lie within radius)."""
    Q = np.asarray(Q, np.float64)
    P = np.asarray(cloud, np.float64)
    tree = tree or cKDTree(P)
    out = np.full((len(Q), 3), np.nan)
    for b in range(0, len(Q), chunk):
        C = Q[b:b + chunk]
        owner, idx = _neighbours(tree, C, radius, P)
        cnt = np.bincount(owner, minlength=len(C)).astype(np.float64)
        v = P[idx] - C[owner]
        mu = np.stack([np.bincount(owner, v[:, k], len(C)) for k in range(3)], 1) / np.maximum(cnt, 1)[:, None]
        cov = np.zeros((len(C), 3, 3))
        for i in range(3):
            for j in range(i, 3):
                cov[:, i, j] = np.bincount(owner, v[:, i] * v[:, j], len(C)) / np.maximum(cnt, 1) - mu[:, i] * mu[:, j]
                cov[:, j, i] = cov[:, i, j]
        ok = cnt >= min_n
        if ok.any():
            w, vec = np.linalg.eigh(cov[ok])
            out[b:b + chunk][ok] = vec[:, :, 0]
    return out


def m3c2(core, normals, ref, cmp, radius=0.25, half_len=1.0, min_n=5, chunk=5000):
    """M3C2 distance [N] (nan where either cloud has fewer than min_n points in the cylinder) and the point counts."""
    core = np.asarray(core, np.float64)
    N = np.asarray(normals, np.float64)
    R = np.sqrt(radius ** 2 + half_len ** 2)
    means, counts = [], []
    for P in (np.asarray(ref, np.float64), np.asarray(cmp, np.float64)):
        tree = cKDTree(P) if len(P) else None
        m = np.full(len(core), np.nan)
        c = np.zeros(len(core), np.int64)
        if tree is not None:
            for b in range(0, len(core), chunk):
                C = core[b:b + chunk]
                Nb = N[b:b + chunk]
                owner, idx = _neighbours(tree, C, R, P)
                v = P[idx] - C[owner]
                a = (v * Nb[owner]).sum(1)
                rad2 = (v * v).sum(1) - a * a
                ok = (np.abs(a) <= half_len) & (rad2 <= radius ** 2) & np.isfinite(a)
                cnt = np.bincount(owner[ok], minlength=len(C))
                s = np.bincount(owner[ok], a[ok], minlength=len(C))
                with np.errstate(invalid="ignore", divide="ignore"):
                    m[b:b + chunk] = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
                c[b:b + chunk] = cnt
        means.append(m)
        counts.append(c)
    d = means[1] - means[0]
    d[(counts[0] < min_n) | (counts[1] < min_n)] = np.nan
    return d, counts[0], counts[1]
