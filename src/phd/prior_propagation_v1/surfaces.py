"""Surface numbers of a triangulated prior (PHD-STAGE2-R7-PROPAGATION-v1). numpy/scipy only (also used in training).

  LoD2  : one polygon = one surface; the caller numbers polygons (tri_surface = polygon index).
  TIN   : gentle triangles (|n_z| >= steep_nz) that share an edge and lie in the same outline region form one surface
          (airborne LiDAR, surface models). Steep triangles and building outlines are boundaries; steep triangles carry
          no number (STEEP). Surfaces are numbered 0, 1, ... by decreasing area."""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

STEEP = -2


def tri_geometry(V, F):
    """unit normals [T, 3] and areas [T] (float64)."""
    V = np.asarray(V, np.float64); F = np.asarray(F, np.int64)
    cr = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    a2 = np.linalg.norm(cr, axis=1)
    return cr / np.maximum(a2, 1e-300)[:, None], 0.5 * a2


def shared_edges(F, n_vertices):
    """pairs (t1, t2) of triangles that share an edge."""
    F = np.asarray(F, np.int64)
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    tri = np.tile(np.arange(len(F)), 3)
    key = e[:, 0] * (int(n_vertices) + 1) + e[:, 1]
    order = np.argsort(key, kind="stable")
    ks, ts = key[order], tri[order]
    same = ks[1:] == ks[:-1]
    return ts[:-1][same], ts[1:][same]


def tin_surfaces(V, F, steep_nz=0.5, region=None):
    """tri_surface [T] (0.. by decreasing area, STEEP for steep triangles), unit normals, areas.
    region [T] int: outline region of each triangle; triangles in different regions are not joined (None = no outline)."""
    n, a = tri_geometry(V, F)
    gentle = np.abs(n[:, 2]) >= steep_nz
    t1, t2 = shared_edges(F, len(V))
    ok = gentle[t1] & gentle[t2]
    if region is not None:
        region = np.asarray(region)
        ok &= region[t1] == region[t2]
    G = coo_matrix((np.ones(int(ok.sum())), (t1[ok], t2[ok])), shape=(len(F), len(F)))
    ncomp, lab = connected_components(G, directed=False)
    area = np.bincount(lab[gentle], weights=a[gentle], minlength=ncomp)
    present = np.nonzero(area > 0)[0]
    rank = np.full(ncomp, -1, np.int64)
    rank[present[np.argsort(-area[present], kind="stable")]] = np.arange(len(present))
    tri_surface = np.where(gentle, rank[lab], STEEP).astype(np.int32)
    return tri_surface, n, a


def vertex_surface(F, tri_surface, eligible):
    """per vertex: the eligible surface that most of its incident triangles belong to (ties: the smaller number, i.e.
    the larger surface); -1 when no incident triangle is on an eligible surface. eligible [S] bool over surface numbers."""
    F = np.asarray(F, np.int64); ts = np.asarray(tri_surface, np.int64)
    ok = ts >= 0
    ok[ok] = np.asarray(eligible)[ts[ok]]
    vv = F[ok].reshape(-1); ss = np.repeat(ts[ok], 3)
    nv = int(F.max()) + 1
    out = np.full(nv, -1, np.int64)
    if vv.size == 0:
        return out
    S = int(ts.max()) + 2
    uk, cnt = np.unique(vv * S + ss, return_counts=True)
    kv, ks = uk // S, uk % S
    order = np.lexsort((ks, -cnt, kv))
    kv, ks = kv[order], ks[order]
    first = np.r_[True, kv[1:] != kv[:-1]]
    out[kv[first]] = ks[first]
    return out
