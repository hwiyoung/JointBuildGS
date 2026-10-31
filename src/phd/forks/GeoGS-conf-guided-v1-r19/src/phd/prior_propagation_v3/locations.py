"""Locations (= judgment units, 판정 단위) = cells of the prior surfaces, their lookup, in-surface distances and the
propagation (prior_propagation_v2, PHD-STAGE2-R8-FOUR-CASES-v1; unchanged from v1 apart from this text).
numpy/scipy (+ torch for `locate` when given tensors); no shapely: the training fork imports this module.

One flat store holds every surface of a setting (dict of arrays, saved as npz):
  sp, rect                     cell size (m) and the crop rectangle [[x0, y0], [x1, y1]]
  surf_ext [S], surf_kind [S]  external surface number (LoD2 polygon index, TIN surface number), 1 roof-like / 2 wall-like
  o, e1, e2 [S, 3]             frame of the surface's cell grid: cell (i, j) holds the points X with
                               floor((X - o).e1 / sp) = i0 + i and floor((X - o).e2 / sp) = j0 + j
                               (LoD2: the polygon's own plane, e1 = horizontal line of the plane; TIN: the XY grid of the
                               crop rectangle, e1 = x, e2 = y, shared by all TIN surfaces)
  i0, j0, ni, nj, off [S]      raster origin, shape and offset into the flat rasters
  member [sum ni*nj]           location number of a member cell, -1 otherwise
  nearest [sum ni*nj]          location number of the nearest member cell (Euclidean on the raster): a point of the
                               surface that falls in a non-member cell (surface edge) goes to the nearest cell of the same
                               surface; the 'seated location' of a Gaussian is found the same way
  loc_surface, loc_center, loc_area, loc_t1, loc_t2, loc_kind, loc_extra [L]
                               t1, t2: in-surface steps for one cell length along the raster axes (for cell samples)
Membership: LoD2 cell centre inside the polygon and inside the crop; TIN cell centre on a triangle of the surface.
A surface without any member cell gets one location at its centroid (loc_extra)."""
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from . import rule
from .conversion import KIND_ROOF, KIND_WALL, ROOF_NZ

OFFS = [(1, 0), (0, 1), (1, 1), (1, -1), (1, 2), (2, 1), (1, -2), (2, -1)]


# ------------------------------------------------------------------------------------------------ store building
def _plane_axes(n):
    n = np.asarray(n, np.float64)
    e1 = np.cross([0.0, 0.0, 1.0], n)
    e1 = e1 / np.linalg.norm(e1) if np.linalg.norm(e1) > 1e-6 else np.array([1.0, 0.0, 0.0])
    e2 = np.cross(n, e1)
    return e1, e2 / np.linalg.norm(e2)


class _Builder:
    def __init__(self, sp, rect):
        self.sp, self.rect = float(sp), np.asarray(rect, np.float64)
        self.surf, self.rasters, self.locs = [], [], []
        self.n_loc = 0

    def add(self, ext, kind, o, e1, e2, i0, j0, member, centers, areas, t1, t2):
        """member [ni, nj] bool; centers/areas/t1/t2 per member cell in raster (C) order."""
        ni, nj = member.shape
        loc = np.full((ni, nj), -1, np.int64)
        k = int(member.sum())
        loc[member] = np.arange(self.n_loc, self.n_loc + k)
        _, idx = distance_transform_edt(~member, return_indices=True)
        nearest = loc[idx[0], idx[1]]
        s = len(self.surf)
        self.surf.append(dict(ext=int(ext), kind=int(kind), o=np.asarray(o, np.float64), e1=np.asarray(e1, np.float64),
                              e2=np.asarray(e2, np.float64), i0=int(i0), j0=int(j0), ni=ni, nj=nj))
        self.rasters.append((loc.ravel(), nearest.ravel()))
        self.locs.append(dict(surface=np.full(k, s), center=centers, area=areas, t1=t1, t2=t2, kind=np.full(k, kind),
                              extra=np.zeros(k, bool)))
        self.n_loc += k

    def add_extra(self, ext, kind, centroid, area):
        """a surface without member cells: one location at its centroid; its 1 x 1 raster points every query there."""
        s = len(self.surf)
        self.surf.append(dict(ext=int(ext), kind=int(kind), o=np.asarray(centroid, np.float64), e1=np.array([1.0, 0, 0]),
                              e2=np.array([0, 1.0, 0]), i0=0, j0=0, ni=1, nj=1))
        self.rasters.append((np.array([self.n_loc]), np.array([self.n_loc])))
        self.locs.append(dict(surface=np.array([s]), center=np.asarray(centroid, np.float64)[None], area=np.array([area]),
                              t1=np.zeros((1, 3)), t2=np.zeros((1, 3)), kind=np.array([kind]), extra=np.array([True])))
        self.n_loc += 1

    def store(self):
        S = self.surf
        ni = np.array([s["ni"] for s in S], np.int64); nj = np.array([s["nj"] for s in S], np.int64)
        off = np.concatenate([[0], np.cumsum(ni * nj)[:-1]]).astype(np.int64)
        cat = lambda key: np.concatenate([L[key] for L in self.locs]) if self.locs else np.zeros(0)
        return dict(sp=np.float64(self.sp), rect=self.rect, surf_ext=np.array([s["ext"] for s in S], np.int64),
                    surf_kind=np.array([s["kind"] for s in S], np.int8), o=np.stack([s["o"] for s in S]),
                    e1=np.stack([s["e1"] for s in S]), e2=np.stack([s["e2"] for s in S]),
                    i0=np.array([s["i0"] for s in S], np.int64), j0=np.array([s["j0"] for s in S], np.int64), ni=ni, nj=nj, off=off,
                    member=np.concatenate([r[0] for r in self.rasters]).astype(np.int64),
                    nearest=np.concatenate([r[1] for r in self.rasters]).astype(np.int64),
                    loc_surface=cat("surface").astype(np.int64), loc_center=cat("center").reshape(-1, 3).astype(np.float64),
                    loc_area=cat("area").astype(np.float64), loc_t1=cat("t1").reshape(-1, 3).astype(np.float64),
                    loc_t2=cat("t2").reshape(-1, 3).astype(np.float64), loc_kind=cat("kind").astype(np.int8),
                    loc_extra=cat("extra").astype(bool))


def build_plane_store(V, F, tri_surface, surfaces, rect, sp):
    """LoD2: surfaces = list of dict(ext, normal) for the polygons to include (their triangles: tri_surface == ext).
    Cells are squares of the polygon's plane; members have their centre inside the polygon and the crop rectangle."""
    V = np.asarray(V, np.float64); F = np.asarray(F, np.int64); ts = np.asarray(tri_surface)
    b = _Builder(sp, rect); R = b.rect
    for srf in surfaces:
        tris = F[ts == srf["ext"]]
        if len(tris) == 0:
            continue
        n = np.asarray(srf["normal"], np.float64); n = n / np.linalg.norm(n)
        kind = KIND_ROOF if abs(n[2]) >= ROOF_NZ else KIND_WALL
        e1, e2 = _plane_axes(n)
        o = V[tris[0, 0]]
        uv = np.stack([(V[tris] - o) @ e1, (V[tris] - o) @ e2], -1)
        i0 = int(np.floor(uv[..., 0].min() / sp)) - 1; j0 = int(np.floor(uv[..., 1].min() / sp)) - 1
        i1 = int(np.floor(uv[..., 0].max() / sp)) + 1; j1 = int(np.floor(uv[..., 1].max() / sp)) + 1
        ni, nj = i1 - i0 + 1, j1 - j0 + 1
        CU, CV = np.meshgrid((np.arange(i0, i1 + 1) + 0.5) * sp, (np.arange(j0, j1 + 1) + 0.5) * sp, indexing="ij")
        inside = np.zeros((ni, nj), bool)
        for t in uv:
            a_, b_, c_ = t
            den = (b_[1] - c_[1]) * (a_[0] - c_[0]) + (c_[0] - b_[0]) * (a_[1] - c_[1])
            if abs(den) < 1e-12:
                continue
            lo = np.maximum(np.floor(t.min(0) / sp).astype(int) - [i0, j0], 0)
            hi = np.minimum(np.floor(t.max(0) / sp).astype(int) - [i0, j0] + 1, [ni - 1, nj - 1])
            pu = CU[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1]; pv = CV[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1]
            l1 = ((b_[1] - c_[1]) * (pu - c_[0]) + (c_[0] - b_[0]) * (pv - c_[1])) / den
            l2 = ((c_[1] - a_[1]) * (pu - c_[0]) + (a_[0] - c_[0]) * (pv - c_[1])) / den
            inside[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1] |= (l1 >= -1e-9) & (l2 >= -1e-9) & (1 - l1 - l2 >= -1e-9)
        P3 = o[None, None, :] + CU[..., None] * e1 + CV[..., None] * e2
        incrop = (P3[..., 0] >= R[0, 0]) & (P3[..., 0] <= R[1, 0]) & (P3[..., 1] >= R[0, 1]) & (P3[..., 1] <= R[1, 1])
        member = inside & incrop
        k = int(member.sum())
        if k:
            b.add(srf["ext"], kind, o, e1, e2, i0, j0, member, P3[member], np.full(k, sp * sp),
                  np.tile(e1, (k, 1)), np.tile(e2, (k, 1)))
        else:
            cen = V[tris].mean(1); ar = 0.5 * np.linalg.norm(np.cross(V[tris[:, 1]] - V[tris[:, 0]], V[tris[:, 2]] - V[tris[:, 0]]), axis=1)
            b.add_extra(srf["ext"], kind, (cen * ar[:, None]).sum(0) / max(ar.sum(), 1e-12), min(sp * sp, float(ar.sum())))
    return b.store()


def build_tin_store(V, F, tri_surface, tri_normal, tri_area, surfaces, rect, sp):
    """TIN: surfaces = list of dict(ext) of the building surfaces to include. One XY grid over the crop rectangle; a cell
    belongs to the surface of the triangle under its centre; area = sp^2 / |n_z|; the centre height lies on that triangle."""
    from matplotlib.tri import Triangulation   # only for building the store (offline)
    V = np.asarray(V, np.float64); F = np.asarray(F, np.int64); ts = np.asarray(tri_surface)
    b = _Builder(sp, rect); R = b.rect
    x0, y0 = R[0]
    NI = int(np.ceil((R[1, 0] - x0) / sp)); NJ = int(np.ceil((R[1, 1] - y0) / sp))
    CX, CY = np.meshgrid(x0 + (np.arange(NI) + 0.5) * sp, y0 + (np.arange(NJ) + 0.5) * sp, indexing="ij")
    tri = np.asarray(Triangulation(V[:, 0], V[:, 1], F).get_trifinder()(CX, CY), np.int64)
    wanted = {int(s["ext"]) for s in surfaces}
    owner = np.where(tri >= 0, ts[np.maximum(tri, 0)], -1).astype(np.int64)
    owner[~np.isin(owner, list(wanted))] = -1
    n = np.asarray(tri_normal, np.float64)[np.maximum(tri, 0)]
    nz = np.where(np.abs(n[..., 2]) > 1e-6, n[..., 2], 1e-6)
    p0 = V[F[np.maximum(tri, 0), 0]]
    CZ = p0[..., 2] - (n[..., 0] * (CX - p0[..., 0]) + n[..., 1] * (CY - p0[..., 1])) / nz
    area = sp * sp / np.abs(nz)
    for srf in surfaces:
        ext = int(srf["ext"])
        m = owner == ext
        if m.any():
            ii, jj = np.nonzero(m)
            a0, a1, c0, c1 = ii.min(), ii.max(), jj.min(), jj.max()
            member = m[a0:a1 + 1, c0:c1 + 1]
            sl = (slice(a0, a1 + 1), slice(c0, c1 + 1))
            cen = np.stack([CX[sl][member], CY[sl][member], CZ[sl][member]], 1)
            nn = n[sl][member]; nzz = nz[sl][member]
            t1 = np.stack([np.ones(len(nn)), np.zeros(len(nn)), -nn[:, 0] / nzz], 1)
            t2 = np.stack([np.zeros(len(nn)), np.ones(len(nn)), -nn[:, 1] / nzz], 1)
            b.add(ext, KIND_ROOF, np.array([x0, y0, 0.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), a0, c0, member, cen,
                  area[sl][member], t1, t2)
        else:
            tm = ts == ext
            ar = np.asarray(tri_area)[tm]; cen = V[F[tm]].mean(1)
            b.add_extra(ext, KIND_ROOF, (cen * ar[:, None]).sum(0) / max(ar.sum(), 1e-12), float(ar.sum()))
    return b.store()


# ------------------------------------------------------------------------------------------------ lookup
def locate(store, s_idx, X):
    """location of each point X [N, 3] on its surface s_idx [N] (compact surface index): the cell of the surface's grid
    that contains it, or the nearest member cell of the same surface. numpy arrays or torch tensors (store converted with
    the same kind, see seat.to_torch)."""
    sp = float(store["sp"])
    d = X - store["o"][s_idx]
    u = (d * store["e1"][s_idx]).sum(-1) / sp
    v = (d * store["e2"][s_idx]).sum(-1) / sp
    ni = store["ni"][s_idx]; nj = store["nj"][s_idx]
    if isinstance(u, np.ndarray):
        i = np.clip(np.floor(u).astype(np.int64) - store["i0"][s_idx], 0, ni - 1)
        j = np.clip(np.floor(v).astype(np.int64) - store["j0"][s_idx], 0, nj - 1)
    else:
        import torch
        i = torch.minimum(torch.clamp(torch.floor(u).long() - store["i0"][s_idx], min=0), ni - 1)
        j = torch.minimum(torch.clamp(torch.floor(v).long() - store["j0"][s_idx], min=0), nj - 1)
    return store["nearest"][store["off"][s_idx] + i * nj + j]


def compact_index(store, ext_ids):
    """external surface numbers -> compact index (-1 where the surface has no location)."""
    ext = np.asarray(ext_ids, np.int64)
    lut_keys = store["surf_ext"]
    order = np.argsort(lut_keys)
    pos = np.searchsorted(lut_keys[order], ext)
    pos = np.clip(pos, 0, len(order) - 1)
    hit = lut_keys[order][pos] == ext
    return np.where(hit, order[pos], -1).astype(np.int64)


# ------------------------------------------------------------------------------------------------ distances
def grid_edges(loc, P3, rows, cols, w, owner=None):
    """edges between member cells (loc >= 0) of the same surface: orthogonal, diagonal and knight steps, length = distance
    between the cell centres P3. A diagonal step needs one side cell of the same surface, a knight step both straddled
    cells, so a path does not cut across a boundary."""
    ni, nj = loc.shape
    own = owner if owner is not None else np.where(loc >= 0, 0, -1)
    for a, b in OFFS:
        i_lo, i_hi = max(0, -a), min(ni, ni - a)
        j_lo, j_hi = max(0, -b), min(nj, nj - b)
        if i_hi <= i_lo or j_hi <= j_lo:
            continue
        A = own[i_lo:i_hi, j_lo:j_hi]; B = own[i_lo + a:i_hi + a, j_lo + b:j_hi + b]
        ok = (A >= 0) & (A == B)
        if abs(a) == 1 and abs(b) == 1:
            s1 = own[i_lo + a:i_hi + a, j_lo:j_hi]; s2 = own[i_lo:i_hi, j_lo + b:j_hi + b]
            ok &= (s1 == A) | (s2 == A)
        elif (abs(a), abs(b)) in ((1, 2), (2, 1)):
            sa, sb = (int(np.sign(a)), 0) if abs(a) == 2 else (0, int(np.sign(b)))
            s1 = own[i_lo + sa:i_hi + sa, j_lo + sb:j_hi + sb]
            s2 = own[i_lo + a - sa:i_hi + a - sa, j_lo + b - sb:j_hi + b - sb]
            ok &= (s1 == A) & (s2 == A)
        la = loc[i_lo:i_hi, j_lo:j_hi][ok]; lb = loc[i_lo + a:i_hi + a, j_lo + b:j_hi + b][ok]
        pa = P3[i_lo:i_hi, j_lo:j_hi][ok]; pb = P3[i_lo + a:i_hi + a, j_lo + b:j_hi + b][ok]
        rows.append(la); cols.append(lb); w.append(np.linalg.norm(pa - pb, axis=1))


def csr(rows, cols, w, n):
    if not rows:
        return coo_matrix((n, n)).tocsr()
    r = np.concatenate(rows); c = np.concatenate(cols); ww = np.concatenate(w)
    return coo_matrix((np.concatenate([ww, ww]), (np.concatenate([r, c]), np.concatenate([c, r]))), shape=(n, n)).tocsr()


def graph(store):
    """block-diagonal graph of in-surface cell paths (no edge between surfaces)."""
    rows, cols, w = [], [], []
    L = len(store["loc_area"])
    for s in range(len(store["surf_ext"])):
        ni, nj, off = int(store["ni"][s]), int(store["nj"][s]), int(store["off"][s])
        loc = store["member"][off:off + ni * nj].reshape(ni, nj)
        if (loc >= 0).sum() < 2:
            continue
        P3 = np.zeros((ni, nj, 3)); P3[loc >= 0] = store["loc_center"][loc[loc >= 0]]
        grid_edges(loc, P3, rows, cols, w)
    return csr(rows, cols, w, L)


def nearest_support_distance(G, state):
    sup = np.nonzero(state == rule.ST_SUPPORT)[0]
    if len(sup) == 0:
        return np.full(G.shape[0], np.inf)
    return np.asarray(dijkstra(G, directed=False, indices=sup, min_only=True))


def k_nearest_support(G, loc_surface, state, vote, kmax, rmax, batch=256):
    """for every missing location: the kmax nearest support locations of the same surface within rmax
    (distances sorted, ties by location number). Returns (missing ids, k_dist [M, kmax], k_vote [M, kmax])."""
    mis = np.nonzero(state == rule.ST_MISSING)[0]
    k_dist = np.full((len(mis), kmax), np.inf); k_vote = np.full((len(mis), kmax), rule.V_NONE, np.int8)
    pos_of = {int(m): i for i, m in enumerate(mis)}
    for s in np.unique(loc_surface[mis]):
        ids = np.nonzero(loc_surface == s)[0]
        m_s = ids[state[ids] == rule.ST_MISSING]; s_s = ids[state[ids] == rule.ST_SUPPORT]
        if len(s_s) == 0:
            continue
        Gs = G[ids][:, ids]
        local = {int(g): i for i, g in enumerate(ids)}
        src = np.array([local[int(g)] for g in m_s]); tgt = np.array([local[int(g)] for g in s_s])
        for b0 in range(0, len(src), batch):
            bs = src[b0:b0 + batch]
            D = np.asarray(dijkstra(Gs, directed=False, indices=bs, limit=rmax + 1e-9))[:, tgt]
            kk = min(kmax, D.shape[1])
            part = np.argpartition(D, kk - 1, axis=1)[:, :kk] if D.shape[1] > kk else np.tile(np.arange(D.shape[1]), (len(bs), 1))
            pd = np.take_along_axis(D, part, 1)
            order = np.lexsort((s_s[part], pd), axis=1)
            part = np.take_along_axis(part, order, 1); pd = np.take_along_axis(pd, order, 1)
            rows_i = np.array([pos_of[int(g)] for g in m_s[b0:b0 + batch]])
            k_dist[rows_i, :kk] = pd
            k_vote[rows_i, :kk] = np.where(np.isfinite(pd), vote[s_s[part]], rule.V_NONE)
    return mis, k_dist, k_vote


def propagate(store, state, vote, q, k, r, G=None):
    """judgment [L]: the propagated judgment of each missing location (rule.J_*), J_NONE elsewhere; plus (mis, k_dist, k_vote)."""
    if G is None:
        G = graph(store)
    mis, kd, kv = k_nearest_support(G, store["loc_surface"], state, vote, int(k), float(r))
    J = np.full(len(state), rule.J_NONE, np.int8)
    if len(mis):
        J[mis] = rule.judge(kd, kv, q, int(k), float(r))
    return J, (mis, kd, kv)


def location_judgment(state, vote, J):
    """the judgment a location carries: its vote (support: agree/conflict), its propagated judgment (missing), none (invisible)."""
    out = np.full(len(state), rule.J_NONE, np.int8)
    out[(state == rule.ST_SUPPORT) & (vote == rule.V_AGREE)] = rule.J_AGREE
    out[(state == rule.ST_SUPPORT) & (vote == rule.V_CONFLICT)] = rule.J_CONFLICT
    out[state == rule.ST_MISSING] = J[state == rule.ST_MISSING]
    return out


def save_store(path, store, **extra):
    np.savez_compressed(path, **store, **extra)


def load_store(path):
    z = np.load(path, allow_pickle=False)
    return {k: z[k] for k in z.files}
