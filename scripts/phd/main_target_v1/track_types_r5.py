"""Exact selected Track-A/MESHPATCH input-only functions; see extraction binding."""
import os,sys
sys.path.insert(0,"/ph/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1/cache/python")
os.environ['NUMBA_CACHE_DIR']='/out/tmp/r5numba'
import numpy as np
from scipy.spatial import cKDTree
from numba import njit
from pathlib import Path
from types import SimpleNamespace
CACHE=Path('/out/r5/types_cache')
def log(prior,stage,**kw): print('TYPES',prior,stage,kw,flush=True)
@njit(cache=True)
def find(p, x):
    r = x
    while p[r] != r:
        r = p[r]
    while p[x] != r:
        nx = p[x]
        p[x] = r
        x = nx
    return r

@njit(cache=True)
def union_mask(n, E, mask):
    p = np.arange(n)
    for k in range(E.shape[0]):
        if mask[k]:
            a = find(p, E[k, 0])
            b = find(p, E[k, 1])
            if a != b:
                p[b] = a
    for x in range(n):
        p[x] = find(p, x)
    return p

@njit(cache=True)
def plane_from_sums(S1, S2, m):
    c = S1 / m
    C = S2 / m - np.outer(c, c)
    w, v = np.linalg.eigh(C)
    return (c, v[:, 0].copy())

@njit(cache=True)
def rg_plane(n, indptr, indices, P, N, curv, order, cth, cos_th, eps, minsize):
    lab = np.full(n, -1, np.int64)
    tried = np.zeros(n, np.bool_)
    q = np.empty(n, np.int64)
    r = 0
    for s in order:
        if lab[s] >= 0 or tried[s] or curv[s] > cth:
            continue
        tried[s] = True
        p0 = P[s].copy()
        nn = N[s].copy()
        S1 = np.zeros(3)
        S2 = np.zeros((3, 3))
        m = 0
        lab[s] = r
        h = 0
        t = 0
        q[t] = s
        t += 1
        S1 += P[s]
        S2 += np.outer(P[s], P[s])
        m += 1
        nextfit = 8
        while h < t:
            c = q[h]
            h += 1
            for k in range(indptr[c], indptr[c + 1]):
                b = indices[k]
                if lab[b] >= 0:
                    continue
                d = (P[b, 0] - p0[0]) * nn[0] + (P[b, 1] - p0[1]) * nn[1] + (P[b, 2] - p0[2]) * nn[2]
                if abs(d) < eps[b] and abs(N[b, 0] * nn[0] + N[b, 1] * nn[1] + N[b, 2] * nn[2]) > cos_th:
                    lab[b] = r
                    q[t] = b
                    t += 1
                    S1 += P[b]
                    S2 += np.outer(P[b], P[b])
                    m += 1
                    if m >= nextfit:
                        p0, nn = plane_from_sums(S1, S2, m)
                        nextfit = m * 2
        if t < minsize:
            for k in range(t):
                lab[q[k]] = -1
        else:
            r += 1
    return lab

def csr(n, E):
    a = np.r_[E[:, 0], E[:, 1]]
    b = np.r_[E[:, 1], E[:, 0]]
    o = np.argsort(a, kind='stable')
    a = a[o]
    b = b[o]
    indptr = np.zeros(n + 1, np.int64)
    np.add.at(indptr, a + 1, 1)
    indptr = np.cumsum(indptr)
    return (indptr, b.astype(np.int64))

def finish(lab, d, E, hasm):
    n = len(lab)
    i, j = (E[:, 0], E[:, 1])
    sameb = d['bld'][i] == d['bld'][j]
    left = hasm & (lab < 0)
    cc = union_mask(n, E, sameb & (left[i] & left[j] | ~hasm[i] & ~hasm[j]))
    out = np.where(lab >= 0, lab, n + cc).astype(np.int64)
    return (out, left)

def units(prior, d):
    n = len(d['cell'])
    C0 = d['centre'].astype(np.float64)
    N = d['normal'].astype(np.float64)
    ep = CACHE / f'{prior}_edges.npy'
    if ep.exists():
        E = np.load(ep)
    else:
        log(prior, 'graph', patches=n)
        E = cKDTree(C0).query_pairs(r=0.36, output_type='ndarray').astype(np.int32)
        np.save(ep, E)
    hasm = (d['mvs_a_status'] == 0) & np.isfinite(d['z']) & np.isfinite(d['mvs_n'][:, 0])
    P = C0 + N * np.where(hasm, d['mvs_p'], 0)[:, None]
    MN = np.where(hasm[:, None], d['mvs_n'], 0).astype(np.float64)
    MN /= np.maximum(np.linalg.norm(MN, axis=1, keepdims=True), 1e-12)
    cp = CACHE / f'{prior}_curv.npy'
    if cp.exists():
        curv = np.load(cp)
    else:
        curv = np.full(n, np.inf)
        ids = np.flatnonzero(hasm)
        tr = cKDTree(P[ids])
        for st in range(0, len(ids), 200000):
            sl = ids[st:st + 200000]
            dd, nb = tr.query(P[sl], k=16)
            nb = ids[nb]
            same = d['bld'][nb] == d['bld'][sl][:, None]
            X = P[nb] - P[sl][:, None, :]
            X = np.where(same[:, :, None], X, 0)
            cnt = same.sum(1)[:, None, None]
            mu = X.sum(1, keepdims=True) / cnt
            Y = np.where(same[:, :, None], X - mu, 0)
            Cv = np.einsum('nki,nkj->nij', Y, Y) / cnt
            ev = np.linalg.eigvalsh(Cv)
            curv[sl] = ev[:, 0] / np.maximum(ev.sum(1), 1e-12)
            log(prior, 'curvature', completed_mvs_points=min(st + 200000, len(ids)), mvs_points=len(ids))
        np.save(cp, curv)
    up = CACHE / f'{prior}_units.npz'
    if up.exists():
        return (E, dict(np.load(up)), hasm)
    i, j = (E[:, 0], E[:, 1])
    sameb = d['bld'][i] == d['bld'][j]
    indptr, indices = ps.csr(n, E[sameb & hasm[i] & hasm[j]])
    cth = float(np.percentile(curv[hasm], 90))
    order = np.argsort(np.where(hasm, curv, np.inf), kind='stable')
    log(prior, 'roofer_region_growing', edges=len(E))
    lab = ps.rg_plane(n, indptr, indices, P, MN, curv, order, cth, 0.75, np.full(n, 0.3), 15)
    out, left = ps.finish(lab, d, E, hasm)
    hm = (d['mvs_a_status'] == 0) & np.isfinite(d['z'])
    mn = d['mvs_n'].astype(np.float64)
    P = C0 + N * np.where(hm, d['mvs_p'], 0)[:, None]
    u = np.where(hm, d['u_mvs'], np.nan).astype(np.float64)
    okn = hm[i] & hm[j] & np.isfinite(mn[i, 0]) & np.isfinite(mn[j, 0])
    ca = np.abs((mn[i] * mn[j]).sum(1))
    off = np.abs(((P[j] - P[i]) * mn[i]).sum(1))
    dt = np.maximum(2 * np.sqrt(u[i] ** 2 + u[j] ** 2), 0.02)
    nomvs = ~hm[i] & ~hm[j]
    shape = union_mask(n, E, sameb & (okn & (ca > np.cos(np.radians(10))) & (off < dt) | nomvs))
    U = dict(roofer_def=out, mvsshape_10=shape, plane_raw=lab, leftover=left)
    np.savez_compressed(up, **U)
    return (E, U, hasm)

def types(d, E, labels):
    a = d['area'].astype(float)
    hm = (d['mvs_a_status'] == 0) & np.isfinite(d['z'])
    _, lab = np.unique(labels, return_inverse=True)
    K = lab.max() + 1
    ea = np.bincount(lab, weights=a, minlength=K)
    nm = np.bincount(lab, weights=hm.astype(float), minlength=K)
    mn = d['mvs_n'].astype(float)
    mnu = np.where(hm[:, None] & np.isfinite(mn), mn, 0)
    M = np.zeros((K, 3, 3))
    for p in range(3):
        for q in range(p, 3):
            v = np.bincount(lab, weights=a * mnu[:, p] * mnu[:, q], minlength=K)
            M[:, p, q] = v
            M[:, q, p] = v
    M[:, 2, 2] += 1e-12
    en = np.linalg.eigh(M)[1][:, :, 2]
    tilt = np.degrees(np.arccos(np.clip(np.abs(en[:, 2]), 0, 1)))
    sc = d['mvs_a_s'].astype(float)
    ls = np.bincount(lab[hm], weights=np.log(np.maximum(sc[hm], 0.0001)) * a[hm], minlength=K) / np.maximum(np.bincount(lab[hm], weights=a[hm], minlength=K), 1e-09)
    esc = np.exp(ls)
    thr = 2 * np.median(sc[hm])
    i, j = (E[:, 0], E[:, 1])
    sb = d['bld'][i] == d['bld'][j]
    pz = d['centre'][:, 2].astype(float) + d['normal'][:, 2].astype(float) * np.where(hm, d['mvs_p'], 0)
    be = sb & (lab[i] != lab[j]) & hm[i] & hm[j]
    dz = (pz[i] - pz[j])[be]
    li = lab[i][be]
    lj = lab[j][be]
    up = np.bincount(li, weights=dz > 0.3, minlength=K) + np.bincount(lj, weights=-dz > 0.3, minlength=K)
    nb = np.bincount(li, minlength=K) + np.bincount(lj, minlength=K)
    frac = up / np.maximum(nb, 1)
    et = np.full(K, 6, np.int8)
    et[tilt < 10] = 5
    et[ea < 1] = 4
    et[(ea < 10) & (frac > 0.6) & (tilt < 60) & (nb >= 4)] = 3
    et[esc > thr] = 2
    et[tilt >= 60] = 1
    et[nm == 0] = 0
    bd = sb & (lab[i] != lab[j])
    b0 = np.zeros(len(a), bool)
    b0[i[bd]] = True
    b0[j[bd]] = True
    s1 = sb & (lab[i] == lab[j]) & (b0[i] != b0[j])
    edge = b0.copy()
    edge[i[s1]] = True
    edge[j[s1]] = True
    return dict(pt=et[lab], edge=edge, et=et, lab=lab, tilt=tilt, escat=esc, frac_up=frac, earea=ea, scatter_threshold=float(thr))
ps=SimpleNamespace(csr=csr,rg_plane=rg_plane,finish=finish)
