"""Stage 1 (order 3.1-3.2): GT surface = planar regions of the GT points, then the unchanged LoD2 patch rule build_plane_store (0.25 m).
usage (CPU container): g1_planes.py <site>
writes /gt/surface/<site>/{voxels.npz, regions.npz, polygons.npz, store.npz, patches.npz, receipt.json}"""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1'); sys.path.insert(0, '/repo')
from gt_common import *
from scipy.spatial import cKDTree
from scipy.ndimage import binary_closing, binary_dilation
from src.phd.prior_propagation_v6 import locations as locs

def voxelize(P, N, v):
    k = np.floor(P/v).astype(np.int64); k -= k.min(0); dims = k.max(0)+1
    key = (k[:, 0]*dims[1]+k[:, 1])*dims[2]+k[:, 2]; u, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    C = np.zeros((len(u), 3)); np.add.at(C, inv, P); C /= cnt[:, None]
    # unsigned normal average: align each point normal to the voxel's first normal before summing
    first = np.full(len(u), -1, np.int64); first[inv[::-1]] = np.arange(len(P))[::-1]
    s = np.sign((N*N[first[inv]]).sum(1)); s[s == 0] = 1
    M = np.zeros((len(u), 3)); np.add.at(M, inv, N*s[:, None]); M /= np.maximum(np.linalg.norm(M, axis=1), 1e-12)[:, None]
    return C, M, inv, cnt

def pca(X):
    c = X.mean(0); w, V = np.linalg.eigh(np.cov((X-c).T) if len(X) > 2 else np.eye(3)); return c, V[:, 0], w

def grow(C, PN, nbr, curv, g):
    cosmax = np.cos(np.radians(g['grow_angle_deg'])); dmax = g['grow_plane_distance_m']; fac = g['refit_growth_factor']
    lab = np.full(len(C), -1, np.int64); rid = 0; sizes = []
    for seed in np.argsort(curv, kind='stable'):
        if lab[seed] >= 0: continue
        lab[seed] = rid; mem = [np.array([seed])]; size = 1; c = C[seed]; n = PN[seed]; front = np.array([seed]); nxt = 2
        while len(front):
            cand = nbr[front].ravel(); cand = cand[cand >= 0]; cand = np.unique(cand); cand = cand[lab[cand] < 0]
            if not len(cand): break
            ok = (np.abs(PN[cand]@n) >= cosmax) & (np.abs((C[cand]-c)@n) <= dmax); new = cand[ok]
            if not len(new): break
            lab[new] = rid; mem.append(new); size += len(new); front = new
            if size >= nxt:
                allm = np.concatenate(mem); c, n2, _ = pca(C[allm]); n = n2 if n2@n >= 0 else -n2; nxt = int(size*fac)+1
        sizes.append(size); rid += 1
    return lab, np.array(sizes)

def merge(C, nbr, lab, g):
    """union adjacent regions whose combined PCA plane is thin (rms <= merge_rms_m) and whose normals agree (merge_angle_deg)."""
    R = lab.max()+1; cnt = np.bincount(lab[lab >= 0], minlength=R).astype(float)
    S1 = np.zeros((R, 3)); S2 = np.zeros((R, 3, 3)); ok = lab >= 0
    np.add.at(S1, lab[ok], C[ok]); np.add.at(S2, lab[ok], C[ok][:, :, None]*C[ok][:, None, :])
    def plane(n_, s1, s2):
        mu = s1/n_; cov = s2/n_-np.outer(mu, mu); w, V = np.linalg.eigh(cov); return np.sqrt(max(w[0], 0)), V[:, 0]
    nrm = np.zeros((R, 3)); rms = np.zeros(R)
    for k in range(R):
        if cnt[k] >= 3: rms[k], nrm[k] = plane(cnt[k], S1[k], S2[k])
    a = np.repeat(np.arange(len(C)), nbr.shape[1]); b = nbr.ravel(); v = b >= 0; a, b = a[v], b[v]
    la, lb = lab[a], lab[b]; e = (la >= 0) & (lb >= 0) & (la != lb); pairs = np.unique(np.sort(np.c_[la[e], lb[e]], 1), axis=0)
    # strongest contacts first (number of voxel edges between the two regions)
    key = pairs[:, 0]*R+pairs[:, 1]; ek = np.sort(np.c_[la[e], lb[e]], 1); ek = ek[:, 0]*R+ek[:, 1]; u, cc = np.unique(ek, return_counts=True)
    pairs = np.c_[u//R, u % R][np.argsort(-cc, kind='stable')]
    parent = np.arange(R); cosm = np.cos(np.radians(g['merge_angle_deg'])); merged = 0
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri == rj or cnt[ri] < 3 or cnt[rj] < 3: continue
        if abs(nrm[ri]@nrm[rj]) < cosm: continue
        n_ = cnt[ri]+cnt[rj]; r_, v_ = plane(n_, S1[ri]+S1[rj], S2[ri]+S2[rj])
        if r_ > g['merge_rms_m']: continue
        parent[rj] = ri; cnt[ri] = n_; S1[ri] += S1[rj]; S2[ri] += S2[rj]; rms[ri], nrm[ri] = r_, v_; merged += 1
    root = np.array([find(k) for k in range(R)]); out = np.where(lab >= 0, root[np.maximum(lab, 0)], -1)
    return out, merged

def absorb(C, nbr, lab, g, rounds=3):
    """unassigned voxels next to a region join it when within absorb_distance_m of the region plane."""
    for _ in range(rounds):
        R = lab.max()+1; ok = lab >= 0; cnt = np.bincount(lab[ok], minlength=R).astype(float)
        mu = np.zeros((R, 3)); np.add.at(mu, lab[ok], C[ok]); mu /= np.maximum(cnt, 1)[:, None]
        S2 = np.zeros((R, 3, 3)); X = C[ok]-mu[lab[ok]]; np.add.at(S2, lab[ok], X[:, :, None]*X[:, None, :])
        w, V = np.linalg.eigh(S2/np.maximum(cnt, 1)[:, None, None]); nr = V[:, :, 0]
        free = np.flatnonzero(lab < 0); nb = nbr[free]; nl = np.where(nb >= 0, lab[np.maximum(nb, 0)], -1)
        best = np.full(len(free), -1); bd = np.full(len(free), np.inf)
        for q in range(nl.shape[1]):
            l = nl[:, q]; v = l >= 0; d = np.full(len(free), np.inf); d[v] = np.abs(((C[free[v]]-mu[l[v]])*nr[l[v]]).sum(1))
            take = d < bd; best[take] = l[take]; bd[take] = d[take]
        new = (best >= 0) & (bd <= g['absorb_distance_m'])
        if not new.any(): break
        lab = lab.copy(); lab[free[new]] = best[new]
    return lab

def main(site, trial=None):
    c = cfg(1); g = dict(c['gt_surface']); t0 = time.monotonic(); out = O/'surface'/site
    if trial:  # parameter trial (not a result): JSON overrides, output under surface_trials/<site>/<name>
        name, over = trial.split('=', 1); g.update(json.loads(over)); out = O/'surface_trials'/site/name
    out.mkdir(parents=True, exist_ok=True)
    d = loadz(GT/'reference'/site/'dense.npz', ['xyz', 'normal']); box = view_box(site)
    if g.get('source_sets') == 'dense+normal_points':  # eval rows are a subset of normal_points (B0: 3.3 % of rows > 0.2 m from dense)
        q = loadz(GT/'reference'/site/'normal_points.npz'); d = dict(xyz=np.r_[d['xyz'], q['xyz'].astype('f8')], normal=np.r_[d['normal'], q['normal'].astype('f8')])
    inb = ((d['xyz'] >= box[0]) & (d['xyz'] <= box[1])).all(1); P = d['xyz'][inb]; Nn = d['normal'][inb]; src_idx = np.flatnonzero(inb)
    C, M, inv, cnt = voxelize(P, Nn, g['voxel_m']); t1 = time.monotonic()
    tree = cKDTree(C); dist, nbr = tree.query(C, k=g['neighbours_k']+1, distance_upper_bound=g['neighbour_radius_m'], workers=16)
    nbr = np.where(np.isfinite(dist), nbr, -1)[:, 1:]; nbr[nbr >= len(C)] = -1
    # local PCA normal and curvature from the voxel and its neighbours
    idx = np.where(nbr >= 0, nbr, np.arange(len(C))[:, None]); X = np.concatenate([C[:, None], C[idx]], 1)
    Xc = X-X.mean(1, keepdims=True); cov = np.einsum('nki,nkj->nij', Xc, Xc)/X.shape[1]; w, V = np.linalg.eigh(cov)
    PN = V[:, :, 0]; PN *= np.where((PN*M).sum(1) < 0, -1, 1)[:, None]; curv = w[:, 0]/np.maximum(w.sum(1), 1e-12)
    del X, Xc, cov, V; t2 = time.monotonic()
    GN = M if g.get('grow_normal') == 'axes71' else PN
    lab, sizes = grow(C, GN, nbr, curv, g); t3 = time.monotonic()
    merged = 0
    if g.get('merge_rms_m'):
        lab, merged = merge(C, nbr, lab, g); u_, lab = np.unique(lab, return_inverse=True); lab = lab-(1 if u_[0] < 0 else 0); lab[lab < 0] = -1
        sizes = np.bincount(lab[lab >= 0])
    keep = np.flatnonzero(sizes >= g['min_region_voxels']); remap = np.full(len(sizes), -1, np.int64); remap[keep] = np.arange(len(keep)); lab = np.where(lab >= 0, remap[np.maximum(lab, 0)], -1)
    if g.get('absorb_distance_m'): lab = absorb(C, nbr, lab, g)
    savez(out/'voxels.npz', centre=C.astype('f4'), normal=PN.astype('f4'), curvature=curv.astype('f4'), count=cnt.astype('i4'), region=lab.astype('i4'))
    savez(out/'point_voxel.npz', dense_index=src_idx.astype('i8'), voxel=inv.astype('i4'))
    # polygons: per region plane, uv occupancy raster (closing), row runs -> rectangles -> triangles (one flat mesh, tri_surface = region)
    r = g['polygon_raster_m']; Vs = []; Fs = []; TS = []; surfaces = []; nv = 0; reg_rows = []
    order = np.argsort(lab, kind='stable'); lab_s = lab[order]; b = np.searchsorted(lab_s, np.arange(len(keep)+1))
    for k in range(len(keep)):
        m = order[b[k]:b[k+1]]; cc, n, ev = pca(C[m]); meanN = M[m].sum(0)
        if n@meanN < 0: n = -n
        e1, e2 = locs._plane_axes(n); uv = np.c_[(C[m]-cc)@e1, (C[m]-cc)@e2]; lo = np.floor(uv.min(0)/r).astype(int)-2
        # aligned=True: raster = the patch grid itself (r = cell_m, grid origin o = cc passed to build_plane_store)
        ij = np.floor(uv/r).astype(int)-lo; occ = np.zeros(ij.max(0)+3, bool); occ[ij[:, 0], ij[:, 1]] = True
        pad = int(np.ceil(g.get('polygon_dilate_m', 0)/r)); occ = np.pad(occ, pad+1)
        lo = lo-(pad+1)
        if g['polygon_closing_cells']: occ = binary_closing(occ, structure=np.ones((3, 3), bool), iterations=g['polygon_closing_cells']) | occ
        if pad: occ = binary_dilation(occ, structure=np.ones((3, 3), bool), iterations=pad)
        verts = []; faces = []
        for i in range(occ.shape[0]):
            row = occ[i]
            if not row.any(): continue
            dif = np.diff(np.r_[0, row.astype(np.int8), 0]); s0 = np.flatnonzero(dif == 1); s1 = np.flatnonzero(dif == -1)
            for a_, b_ in zip(s0, s1):
                u0, u1 = (i+lo[0])*r, (i+1+lo[0])*r; v0, v1 = (a_+lo[1])*r, (b_+lo[1])*r; q = len(verts)
                verts += [cc+u0*e1+v0*e2, cc+u1*e1+v0*e2, cc+u1*e1+v1*e2, cc+u0*e1+v1*e2]; faces += [[q, q+1, q+2], [q, q+2, q+3]]
        V_ = np.array(verts); F_ = np.array(faces)+nv; nv += len(V_); Vs.append(V_); Fs.append(F_); TS.append(np.full(len(F_), k))
        res = np.abs((C[m]-cc)@n); surfaces.append(dict(ext=k, normal=n.tolist(), **({'o': cc.tolist()} if g.get('aligned') else {})))
        reg_rows.append((len(m), int(cnt[m].sum()), float(occ.sum()*r*r), float(np.percentile(res, 95)), float(res.max()), abs(n[2])))
    V = np.concatenate(Vs); F = np.concatenate(Fs); TSa = np.concatenate(TS); RR = np.array(reg_rows)
    savez(out/'polygons.npz', V=V, F=F, tri_surface=TSa, normal=np.array([s['normal'] for s in surfaces]), origin=np.array([s.get('o', [np.nan]*3) for s in surfaces]))
    savez(out/'regions.npz', voxels=RR[:, 0].astype('i4'), points=RR[:, 1].astype('i8'), polygon_area_m2=RR[:, 2], plane_residual_p95_m=RR[:, 3], plane_residual_max_m=RR[:, 4], abs_nz=RR[:, 5])
    t4 = time.monotonic(); rect = np.array([box[0][:2], box[1][:2]])
    st = locs.build_plane_store(V, F, TSa, surfaces, rect, g['cell_m']); t5 = time.monotonic()
    locs.save_store(out/'store.npz', st) if hasattr(locs, 'save_store') else savez(out/'store.npz', **st)
    zc = st['loc_center'][:, 2]; inz = (zc >= box[0][2]) & (zc <= box[1][2])
    nrm = np.array([surfaces[st['surf_ext'][s]]['normal'] for s in st['loc_surface']])
    savez(out/'patches.npz', centre=st['loc_center'], normal=nrm, kind=st['loc_kind'], area=st['loc_area'], surf=st['surf_ext'][st['loc_surface']],
          extra=st['loc_extra'], t1=st['loc_t1'], t2=st['loc_t2'], in_box=inz)
    pts_in_region = int(cnt[lab >= 0].sum())
    rec = dict(at=now(), site=site, title=TITLE, dense_points=int(len(d['xyz'])), points_in_box=int(len(P)), voxels=int(len(C)),
        regions_grown=int(len(sizes)), regions_merged=int(merged), regions_kept=int(len(keep)), points_in_kept_regions=pts_in_region, points_in_kept_regions_pct=100*pts_in_region/len(P),
        plane_residual_p95_m_median=float(np.median(RR[:, 3])), plane_residual_max_m_p99=float(np.percentile(RR[:, 4], 99)),
        polygon_triangles=int(len(F)), patches=int(len(st['loc_area'])), patches_extra=int(st['loc_extra'].sum()), patches_in_box_z=int(inz.sum()),
        patches_wall=int((st['loc_kind'] == 2).sum()), patch_area_m2=float(st['loc_area'].sum()), cell_m=g['cell_m'],
        rule='locations.build_plane_store unchanged', parameters=g, mesh_existed=False, seconds=dict(voxel=t1-t0, pca=t2-t1, grow=t3-t2, polygons=t4-t3, store=t5-t4, total=time.monotonic()-t0),
        scientific_verdict=None)
    dump(out/'receipt.json', rec); print('PLANES', site, json.dumps(rec, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
