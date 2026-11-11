"""Stage 3 (CPU): check 5 (order 5) on one record run, from te/checks/<stem>__<arm>__tl.npz (checks 1-4 on the record 30000 run) and the run's log.
argv: <run>. Writes te/check5/<run>.npz and tables check5_<run>* (gaussian-level and point-weighted), curves."""
import glob
import open3d as o3d
import torch
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from common import *
from te_sets_tl import RUNS
C5 = ['5-가', '5-나', '5-다', '5-라', '5-마', '5-확인불가']; C5E = ['5-바', '5-사', '5-아', '5-확인불가']

def events(root, kind):
    parts = [loadz(f) for f in sorted(glob.glob(str(root/'events'/f'{kind}_*.npz')))]
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]} if parts else {}

def model_of(run):
    site = RUNS[run][0].split('__')[0]
    for a in sorted((O/'runs'/site/run).glob('attempt*'), reverse=True):
        if (a/'TRAINING_COMPLETE.json').exists(): return a/'model'

def pieces(mesh_path, box, merge=.1, angle=30.):
    """faces of the record 30000 mesh inside the range box, edge-adjacent after merging vertices closer than 0.1 m, dihedral <= 30 deg."""
    m = o3d.io.read_triangle_mesh(str(mesh_path)); V = np.asarray(m.vertices); F = np.asarray(m.triangles)
    inb = ((V >= box[0]) & (V <= box[1])).all(1); F = F[inb[F].all(1)]
    used = np.unique(F); pairs = cKDTree(V[used]).query_pairs(merge, output_type='ndarray')
    A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(used), len(used))); _, lab = connected_components(A, directed=False)
    vid = np.full(len(V), -1, np.int64); vid[used] = lab; G = vid[F]
    nrm = np.cross(V[F[:, 1]]-V[F[:, 0]], V[F[:, 2]]-V[F[:, 0]]); area = .5*np.linalg.norm(nrm, axis=1); nrm /= np.maximum(2*area, 1e-20)[:, None]
    e = np.concatenate([np.sort(G[:, [0, 1]], 1), np.sort(G[:, [1, 2]], 1), np.sort(G[:, [2, 0]], 1)]); fi = np.tile(np.arange(len(F)), 3)
    key = e[:, 0]*(G.max()+1)+e[:, 1]; o = np.argsort(key, kind='stable'); key, fi = key[o], fi[o]; same = np.flatnonzero(key[1:] == key[:-1])
    a, b = fi[same], fi[same+1]; ok = (np.abs((nrm[a]*nrm[b]).sum(1)) >= np.cos(np.radians(angle))) & (a != b)
    B = coo_matrix((np.ones(int(ok.sum())), (a[ok], b[ok])), shape=(len(F), len(F))); _, comp = connected_components(B, directed=False)
    cent = V[F].mean(1); return dict(F=F, V=V, comp=comp, area=area, cent=cent, nrm=nrm)

def main(run):
    c = cfg(); t = Timer(f'check5_{run}'); stem, arm = RUNS[run]; site, prior = stem.split('__'); model = model_of(run); log = model/'trainlog'
    z = loadz(O/'checks'/f'{stem}__{arm}__tl.npz'); n = len(z['cell']); L = z['set'] == 0
    d30 = torch.load(log/'scene/30000.pt', map_location='cpu', weights_only=False); uid30 = d30['uid'].numpy(); xyz30 = d30['xyz'].double().numpy()
    tg = loadz(arm_paths(stem, arm)['targets'], ['target', 'normal', 'sigma']); vp = np.flatnonzero(valid_patch(loadz(arm_paths(stem, arm)['targets'], ['target', 'normal', 'sigma', 'region'])))
    ref = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz'].astype(float); rtree = cKDTree(ref)
    reg = json.loads((O/'region'/f'{stem}.json').read_text()); lo = np.asarray(reg['grid_origin']); hi = lo+np.asarray(reg['grid_shape'])*reg['voxel_m']
    mesh = O/'gtj/meshes'/f'{stem}__tl_{arm}_30000'/'final.ply'; PC = pieces(mesh, (lo, hi)); sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.core.Tensor(PC['V'].astype(np.float32)), o3d.core.Tensor(PC['F'].astype(np.uint32)))
    mv = o3d.io.read_triangle_mesh(str(AX/'mvs'/site/'mesh_mvs_a.ply')); msc = o3d.t.geometry.RaycastingScene(); msc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mv)); del mv
    s0 = torch.load(log/'scene/0.pt', map_location='cpu', weights_only=False); born0 = dict(zip(s0['uid'].numpy().tolist(), range(len(s0['uid'])))); xyz0 = s0['xyz'].double().numpy()
    birth = events(log, 'birth'); bpos = dict(zip(birth['uid'].tolist(), birth['xyz'].astype(float))) if birth else {}
    link = events(log, 'link'); parent_of = dict(zip(link['uid'].tolist(), link['parent_uid'].tolist())) if link else {}
    gfiles = {int(Path(f).stem): f for f in glob.glob(str(log/'grads/*.npz'))}; sfiles = {}
    for f in glob.glob(str(log/'states/*.npz')):
        nm = Path(f).stem
        if nm.isdigit(): sfiles[int(nm)] = f
    def birth_pos(u):
        if u in born0: return xyz0[born0[u]]
        return bpos.get(u)
    # ---- gaussian-level classification for 3-나/다/라 drawers ----
    tgt = np.isin(z['check3'], ['3-나', '3-다', '3-라']) & L; drawers = np.unique(z['drawer'][tgt]); cls = {}; info = {}
    compfrac = {}
    for gi in drawers.tolist():
        pts = np.flatnonzero(tgt & (z['drawer'] == gi)); p = z['xyz'][pts[0]]; npnt = z['normal'][pts[0]]; tau = float(z['tau'][pts[0]]); x = xyz30[gi]; u = int(uid30[gi])
        tag = int(d30['target_tag'][gi]); ti = int(d30['target_index'][gi]); r = dict(uid=u, points=len(pts), tag=tag, how=int(d30['born_how'][gi]), born_at=int(d30['born_at'][gi]))
        if tag == 1:
            q = vp[ti]; nq = tg['normal'][q]/np.linalg.norm(tg['normal'][q]); r['neighbour_plane_m'] = float(abs(nq@(x-tg['target'][q])))
            if r['neighbour_plane_m'] <= tau: cls[gi] = '5-가'; info[gi] = r; continue
        cp = sc.compute_closest_points(o3d.core.Tensor(x[None].astype(np.float32)))['primitive_ids'].numpy()[0]; k = int(PC['comp'][cp])
        if (k, int(pts[0])) not in compfrac:
            f = np.flatnonzero(PC['comp'] == k); near = rtree.query_ball_point(PC['cent'][f], tau); hit = np.zeros(len(f), bool)
            for jj, lst in enumerate(near):
                if lst: hit[jj] = bool((np.abs((ref[lst]-p)@npnt) > tau).any())
            compfrac[(k, int(pts[0]))] = float(PC['area'][f][hit].sum()/max(PC['area'][f].sum(), 1e-12))
        r['piece_other_surface_area_frac'] = compfrac[(k, int(pts[0]))]
        if r['piece_other_surface_area_frac'] >= .3: cls[gi] = '5-나'; info[gi] = r; continue
        bp = birth_pos(u)
        if bp is None: cls[gi] = '5-확인불가'; r['why'] = 'birth outside range (no birth event position)'; info[gi] = r; continue
        r['moved_m'] = float(np.linalg.norm(x-bp))
        if r['how'] >= 2:
            pu = parent_of.get(u); pb = birth_pos(pu) if pu is not None else None; r['parent_uid'] = pu; r['parent_birth_moved_m'] = float(np.linalg.norm(x-pb)) if pb is not None else None
        if r['moved_m'] <= tau: cls[gi] = '5-다'; info[gi] = r; continue
        r['mvs_distance_m'] = float(msc.compute_distance(o3d.core.Tensor(x[None].astype(np.float32))).numpy()[0]); r['tau'] = tau
        cls[gi] = '5-라?'; info[gi] = r
    # 5-라 needs per-state positions and per-iteration gradients: read every state / gradient file once
    cand = [g for g in drawers.tolist() if cls[g] == '5-라?']
    if cand:
        cu = np.array([info[g]['uid'] for g in cand]); order = np.argsort(cu); cs_ = cu[order]; X30 = xyz30[np.array(cand)]
        ph = np.zeros(len(cand)); dp = np.zeros(len(cand)); first = np.full(len(cand), -1); born = np.array([info[g]['born_at'] for g in cand]); taus = np.array([info[g]['tau'] for g in cand])
        for it in sorted(sfiles):
            active = (born <= it) & (first < 0)
            if not active.any(): break
            if it in gfiles:
                gz = np.load(gfiles[it]); k = np.searchsorted(cs_, gz['uid']); ok = (k < len(cs_)) & (cs_[np.clip(k, 0, len(cs_)-1)] == gz['uid'])
                j = order[k[ok]]; a_ = active[j]; np.add.at(ph, j[a_], gz['photo_xyz'][ok][a_]); np.add.at(dp, j[a_], gz['depth_xyz'][ok][a_])
            st = np.load(sfiles[it]); k = np.searchsorted(cs_, st['uid']); ok = (k < len(cs_)) & (cs_[np.clip(k, 0, len(cs_)-1)] == st['uid'])
            j = order[k[ok]]; near = np.linalg.norm(st['xyz'][ok].astype(float)-X30[j], axis=1) <= taus[j]; hitj = j[near & active[j]]; first[hitj] = it
        for q, g in enumerate(cand):
            info[g].update(photo_grad_sum=float(ph[q]), depth_grad_sum=float(dp[q]), first_within_final_iteration=int(first[q]) if first[q] >= 0 else None)
            cls[g] = '5-라' if (info[g]['mvs_distance_m'] <= info[g]['tau'] and ph[q] > dp[q]) else '5-마'
    # ---- 3-사 points: fate of Gaussians once bound to the point's patch ----
    emp = (z['check3_empty'] == '3-사') & L; dele = events(log, 'delete'); rel = events(log, 'release'); rng = events(log, 'range')
    bound_uids = {}
    pr_need = set(z['patch_row'][emp].tolist()); vidx = {int(q): i for i, q in enumerate(vp)}
    want = {vidx[q] for q in pr_need if q in vidx}
    for it in sorted(sfiles):
        st = np.load(sfiles[it]); m = (st['target_tag'] == 1) & np.isin(st['target_index'], list(want))
        for ti, u in zip(st['target_index'][m].tolist(), st['uid'][m].tolist()): bound_uids.setdefault(int(vp[ti]), set()).add(int(u))
    del_reason = dict(zip(dele['uid'].tolist(), dele['reason'].tolist())) if dele else {}; released = set(rel['uid'].tolist()) if rel else set()
    exited = set(rng['uid'][rng['enter'] == 0].tolist()) if rng else set(); alive30 = dict(zip(uid30.tolist(), range(len(uid30)))); ins30 = d30['inside'].numpy()
    pclass = np.full(n, '대상 아님', object); fates = []
    for i in np.flatnonzero(emp):
        us = bound_uids.get(int(z['patch_row'][i]), set()); f = []
        for u in us:
            if u in del_reason: f.append(('5-바', int(del_reason[u])))
            elif u in released and u in alive30 and ins30[alive30[u]]: f.append(('5-사', None))
            elif u in exited or (u in alive30 and not ins30[alive30[u]]): f.append(('5-아', None))
        if not f: pclass[i] = '5-확인불가'; continue
        lab = [a for a, _ in f]; best = max(['5-바', '5-사', '5-아'], key=lambda k: (lab.count(k), -['5-바', '5-사', '5-아'].index(k))); pclass[i] = best
        for a, rsn in f:
            row = dict(point=int(i), fate=a, reason=rsn)
            fates.append(row)
    g_rows = [dict(run=run, drawer=int(g), cls=cls[g], **{k: v for k, v in info[g].items()}) for g in drawers.tolist()]
    pt_cls = np.full(n, '대상 아님', object)
    for g in drawers.tolist(): pt_cls[tgt & (z['drawer'] == g)] = cls[g]
    savez(O/'check5'/f'{run}.npz', check5=pt_cls.astype('U12'), check5_empty=pclass.astype('U12'))
    rows = []
    for k in C5:
        rows.append(dict(run=run, level='gaussian', cls=k, n=sum(1 for g in drawers if cls[g] == k), pct=100*sum(1 for g in drawers if cls[g] == k)/max(1, len(drawers))))
        for cell in sorted(set(z['cell'][tgt].tolist())):
            m = tgt & (z['cell'] == cell); rows.append(dict(run=run, level=f'point c{cell}', cls=k, n=int((pt_cls[m] == k).sum()), pct=100*float((pt_cls[m] == k).mean()) if m.any() else None))
    for k in C5E:
        for cell in sorted(set(z['cell'][emp].tolist())):
            m = emp & (z['cell'] == cell); rows.append(dict(run=run, level=f'empty point c{cell}', cls=k, n=int((pclass[m] == k).sum()), pct=100*float((pclass[m] == k).mean()) if m.any() else None))
    rs = {}
    for r in fates:
        if r['fate'] == '5-바': rs[r['reason']] = rs.get(r['reason'], 0)+1
    table(f'check5_{run}', rows); table(f'check5_{run}_gaussians', g_rows or [dict(run=run, note='no 3-나/다/라 drawer')])
    table(f'check5_{run}_delete_reasons', [dict(run=run, reason={1: 'opacity', 2: 'world_size', 3: 'screen_size', 4: 'other', 5: 'split_parent'}.get(k, k), n=v) for k, v in sorted(rs.items())] or [dict(run=run, note='none')])
    dump(O/'check5'/f'{run}.json', dict(at=now(), run=run, drawers=len(drawers), empty_points=int(emp.sum()), pieces=int(PC['comp'].max()+1), seconds=t.done(), scientific_verdict=None))
    print('CHECK5', run, {k: sum(1 for g in drawers if cls[g] == k) for k in C5}, flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
