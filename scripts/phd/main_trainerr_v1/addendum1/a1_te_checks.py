import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')  # addendum-1 copy of te_checks.py (tag a1 = stored run with visibility_a1)
"""Stage 2 (CPU): checks 1-4 (order 4.1-4.5) for one stem x arm from the stored distances, views/ and render/ pair tables.
argv: <stem> <arm> [tag]  (tag: '' = stored 30000 run; 'tl' = record run, used by check 5 with sets_tl/ and meshes of the record run)
Writes te/checks/<stem>__<arm>[__tag].npz (one row per set point with every class and auxiliary value) and docs tables."""
import importlib.util
import open3d as o3d
from scipy.spatial import cKDTree
from common import *
from te_views import point_table
C1 = ['1-마', '1-나', '1-가', '1-다', '1-라']; C1R = ['1-나', '1-가', '1-라']
C2 = ['2-가', '2-나', '2-라', '2-다', '2-마', '2-바']
C3 = ['3-마', '3-가', '3-나', '3-다', '3-라']; C3E = ['3-바', '3-사']
C4 = ['4-마', '4-라', '4-나', '4-가', '4-다', '4-확인불가']
NA = '대상 아님'
def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
NL = load_module(R/'scripts/phd/main_gtjudge_v1/normal_line.py', 'te_normal_line')

def scene_of(mesh):
    m = o3d.io.read_triangle_mesh(str(mesh)); sc = o3d.t.geometry.RaycastingScene(nthreads=16); sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(m)); return sc

def stored_rows(stem, arm, tag):
    """c1/c2 trained-mesh distances (row_s, row_offset) of the run being checked."""
    if tag: z = loadz(O/'meshes'/f'{stem}__{tag}_{arm}_30000'/'points.npz'); return z['reference__s_m'].astype(float), z['reference__offset']
    m = TRAINED_METHOD[arm]; z = loadz(GT/'scenes'/stem/'distances'/f'{m}.npz', ['row_s', 'row_offset']); return z['row_s'].astype(float), z['row_offset']

BASE = O
def main(stem, arm, tag=''):
    global BASE; BASE = O/'addendum1' if tag == 'a1' else O
    c = cfg(); t = Timer(f'checks_{stem}_{arm}{"_"+tag if tag else ""}'); site, prior = stem.split('__'); ap = arm_paths(stem, arm)
    name = f'{stem}__{arm}' + (f'__{tag}' if tag else ''); rec = bool(tag) and tag != 'a1'  # a1 = addendum-1 visibility on the stored run
    sroot = O/('sets_'+tag if rec else 'sets')
    P = point_table(stem, arm, sroot); n = len(P['xyz']); X = P['xyz']; Nn = P['normal']/np.linalg.norm(P['normal'], axis=1)[:, None]; tau = P['tau']; res = P['result']
    sets = {}
    for cell in sorted(k for k, v in STEMS.items() if v == stem):
        for setname in ['lost', 'control']: sets[(cell, setname)] = loadz(sroot/f'{cell}_{arm}_{setname}.npz')
    def col(key, default=np.nan, dtype=float):
        out = np.full(n, default, dtype=dtype)
        for (cell, setname), z in sets.items():
            m = (P['cell'] == int(cell[1])) & (P['set'] == (0 if setname == 'lost' else 1))
            if key in z: out[m] = z[key]
        return out
    point_id = col('point_id', -1, np.int64); patch_row = col('patch_row', -1, np.int64); trained_s = col('trained_s_m'); trained_state = col('trained_state', 0, np.int64)
    wall = col('wall', 0, np.int64).astype(bool)
    model = Path(ap['model']) if not rec else O/'runs'/site/f'tl_{site.split("_")[0].replace("rep","")}_{prior}_{arm}'/'model'
    trained_mesh = ap['trained_mesh'] if not rec else O/'gtj/meshes'/f'{stem}__{tag}_{arm}_30000'/'final.ply'
    sc = scene_of(trained_mesh)
    # ---------------- check 1 ----------------
    c1 = np.full(n, '', object); aux = {}
    ref = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz'].astype(float); rtree = cKDTree(ref)
    closest = sc.compute_distance(o3d.core.Tensor(X.astype(np.float32))).numpy().astype(float); aux['closest_trained_m'] = closest
    g = ~res
    if g.any():
        rs, roff = stored_rows(stem, arm, tag if rec else ''); s = rs[point_id[g]]; off = roff[point_id[g]]
        if not rec: assert np.allclose(np.nan_to_num(s, nan=-999), np.nan_to_num(trained_s[g], nan=-999), atol=1e-5), 'stored trained distance mismatch'
        a, b = NL.tangents(Nn[g]); shifts = np.stack([np.zeros_like(a), .05*a, -.05*a, .05*b, -.05*b], 1)
        Xh = X[g]+shifts[np.arange(g.sum()), np.clip(off, 0, 4)]+np.nan_to_num(s)[:, None]*Nn[g]
        other = np.zeros(g.sum(), bool); hits = np.isfinite(s)
        for k, lst in zip(np.flatnonzero(hits), rtree.query_ball_point(Xh[hits], tau[g][hits])):
            if lst: other[k] = bool((np.abs((ref[lst]-X[g][k])@Nn[g][k]) > tau[g][k]).any())
        ab = np.abs(s); cls = np.where(~hits, '1-마', np.where((closest[g] <= tau[g]) & (ab > tau[g]), '1-나', np.where((ab > tau[g]) & (ab <= 2*tau[g]), '1-가', np.where(other, '1-다', '1-라'))))
        cls[(hits) & (ab <= tau[g])] = '맞음(τ 안)'
        c1[g] = cls; aux['first_hit'] = np.full((n, 3), np.nan); aux['first_hit'][g] = np.where(hits[:, None], Xh, np.nan); aux['s_used'] = np.full(n, np.nan); aux['s_used'][g] = s
    if res.any():
        nd, _ = rtree.query(X[res]); s = trained_s[res]; ab = np.abs(s)
        cls = np.where((nd <= tau[res]) & ~(ab <= tau[res]), '1-나', np.where((ab > tau[res]) & (ab <= 2*tau[res]), '1-가', '1-라'))
        cls[np.isfinite(s) & (ab <= tau[res])] = '맞음(τ 안)'; c1[res] = cls; aux['nearest_reference_m'] = np.full(n, np.nan); aux['nearest_reference_m'][res] = nd
    # ---------------- shared per-pair values ----------------
    V = loadz(BASE/'views'/f'{name}.npz'); Rr = loadz(BASE/'render'/f'{name}.npz'); pt = V['point']
    assert len(pt) == len(Rr['drawer'])
    nseen = np.bincount(pt, minlength=n)
    views = [v for v in json.loads((GT/'views'/f'{site}.json').read_text())['views'] if not v['virtual']]
    Ks = np.array([v['K'] for v in views]); Es = np.array([v['W2C'] for v in views])
    # ---------------- check 2 (c1/c2) ----------------
    tg = loadz(ap['targets'], ['target', 'normal', 'sigma', 'region']); vp = valid_patch(tg)
    has = (patch_row >= 0); ok_patch = has.copy(); ok_patch[has] = vp[patch_row[has]]
    pr = np.clip(patch_row, 0, None); tpt = tg['target'][pr]; tn = tg['normal'][pr]/np.linalg.norm(tg['normal'][pr], axis=1)[:, None]
    den = np.einsum('ij,ij->i', tn, Nn); tdist = np.where(np.abs(den) > 1e-6, np.einsum('ij,ij->i', tn, tpt-X)/np.where(np.abs(den) > 1e-6, den, 1), np.inf); aux['target_plane_t_m'] = tdist
    match = V['owner'] == patch_row[pt]; nmatch = np.bincount(pt, weights=match, minlength=n).astype(int)
    floor = match & (V['weight'] <= .1+1e-6); nfloor = np.bincount(pt, weights=floor, minlength=n).astype(int)
    c2 = np.full(n, NA, object); gg = ~res
    c2[gg] = np.where(~ok_patch[gg], '2-가', np.where(np.abs(tdist[gg]) > tau[gg], '2-나', np.where(nseen[gg] < 3, '2-라', np.where(nmatch[gg] < 3, '2-다', np.where(nfloor[gg]*2 > nmatch[gg], '2-마', '2-바')))))
    c2[(P['set'] == 0) & ~res & ~np.isin(c1, c['check1']['forward']['c1_c2'])] = NA  # only forwarded lost points (order 4.1); every control point
    aux.update(seen_views=nseen, owner_match_views=nmatch, weight_floor_views=nfloor)
    wsum = np.bincount(pt, weights=np.where(match, V['weight'], 0), minlength=n); aux['mean_weight_matching'] = np.where(nmatch > 0, wsum/np.maximum(nmatch, 1), np.nan)
    # ---------------- check 3 ----------------
    snap = loadz(model/'target_monitor/snapshot_30000.npz', ['xyz', 'origin', 'target_tag', 'target_index', 'patch_ids']) if not rec else None
    if rec:
        import torch; d = torch.load(model/'trainlog/scene/30000.pt', map_location='cpu', weights_only=False)
        snap = dict(xyz=d['xyz'].numpy(), origin=d['origin'].numpy(), target_tag=d['target_tag'].numpy(), target_index=d['target_index'].numpy(), patch_ids=np.flatnonzero(vp), uid=d['uid'].numpy())
    assert np.array_equal(snap['patch_ids'], np.flatnonzero(vp)), 'snapshot patch ids differ from target valid patches'
    drawer = Rr['drawer']; modal = np.full(n, -1, np.int64); mcount = np.zeros(n, int)
    okd = drawer >= 0; key = np.c_[pt[okd], drawer[okd]]
    if len(key):
        u, cnt = np.unique(key, axis=0, return_counts=True)
        order = np.lexsort((u[:, 1], -cnt, u[:, 0])); u, cnt = u[order], cnt[order]; first = np.r_[True, u[1:, 0] != u[:-1, 0]]
        modal[u[first, 0]] = u[first, 1]; mcount[u[first, 0]] = cnt[first]
    gi = np.clip(modal, 0, None); dtag = np.where(modal >= 0, snap['target_tag'][gi], -1); dorig = np.where(modal >= 0, snap['origin'][gi], -1)
    dpatch = np.where((modal >= 0) & (dtag == 1), snap['patch_ids'][np.clip(snap['target_index'][gi], 0, None)], -1)
    cls3 = np.where((modal < 0) | (mcount*2 < nseen) | (nseen == 0), '3-마', np.where((dtag == 1) & (dpatch == patch_row), '3-가', np.where(dtag == 1, '3-나',
                    np.where(dorig == 1, '3-다', np.where(dorig == 0, '3-라', '3-마')))))
    # empty-surface classes for 1-다 / 1-마 and every control point
    bt = np.flatnonzero(snap['target_tag'] == 1); bpatch = snap['patch_ids'][snap['target_index'][bt]]; ordp = np.argsort(bpatch, kind='stable'); bpatch_s = bpatch[ordp]; bt_s = bt[ordp]
    lo = np.searchsorted(bpatch_s, patch_row, 'left'); hi = np.searchsorted(bpatch_s, patch_row, 'right'); remain = np.zeros(n, bool); nbound = hi-lo
    for i in np.flatnonzero((patch_row >= 0) & (nbound > 0)):
        xs = snap['xyz'][bt_s[lo[i]:hi[i]]]; remain[i] = bool((np.abs((xs-X[i])@Nn[i]) <= tau[i]).any())
    c3e = np.where(remain, '3-바', '3-사')
    isl = P['set'] == 0; fwd_ra = (isl & (c1 == '1-라')) | (isl & res) | (P['set'] == 1)
    fwd_e = (isl & ~res & np.isin(c1, ['1-다', '1-마'])) | ((P['set'] == 1) & ~res)
    c3 = np.full(n, NA, object); c3[fwd_ra] = cls3[fwd_ra]; c3x = np.full(n, NA, object); c3x[fwd_e] = c3e[fwd_e]
    aux.update(drawer=modal, drawer_votes=mcount, drawer_tag=dtag, drawer_origin=dorig, drawer_patch=dpatch, bound_to_patch_30000=nbound)
    # 3-가 detail: centre height vs target and interval width
    sp = np.full(n, np.nan); wdt = np.full(n, np.nan); cn = np.full(n, np.nan)
    m3 = (cls3 == '3-가'); xs = snap['xyz'][gi[m3]]; sp[m3] = np.einsum('ij,ij->i', tn[m3], xs-tpt[m3]); wdt[m3] = 1.96*tg['sigma'][pr[m3]]; cn[m3] = np.einsum('ij,ij->i', Nn[m3], xs-X[m3])
    aux.update(drawer_target_height_m=sp, drawer_interval_m=wdt, drawer_point_normal_m=cn)
    # page 50 recount
    surf = np.where(res[:, None], X, aux.get('first_hit', np.full((n, 3), np.nan)))
    pdist = np.abs(np.einsum('ij,ij->i', tn, surf-tpt)); fixed = c['check3']['page50']['fixed_radius_m'][prior]; per = 1.96*tg['sigma'][pr]+.5
    aux.update(page50_distance_m=np.where(ok_patch, pdist, np.nan), page50_outside_fixed=ok_patch & (pdist > fixed), page50_outside_patch=ok_patch & (pdist > per))
    # ---------------- check 4 ----------------
    Kv = Ks[V['view']]; Ev = Es[V['view']]; D = Rr['rdepth'].astype(float)
    xc = np.c_[(V['u']-Kv[:, 0, 2])/Kv[:, 0, 0]*D, (V['v']-Kv[:, 1, 2])/Kv[:, 1, 1]*D, D]
    Rm = Ev[:, :3, :3]; tv = Ev[:, :3, 3]; Xw = np.einsum('nji,nj->ni', Rm, xc-tv)
    dv = np.einsum('ij,ij->i', Nn[pt], Xw-X[pt]); empty = ~(Rr['ralpha'] >= .5) | ~np.isfinite(D) | (D <= 0)
    right = ~empty & (np.abs(dv) <= tau[pt]); wrong = ~empty & ~right
    nr = np.bincount(pt, weights=right, minlength=n); nw = np.bincount(pt, weights=wrong, minlength=n); ne = np.bincount(pt, weights=empty, minlength=n)
    fr = np.bincount(pt, weights=right & (V['facing'] == 1), minlength=n); fw = np.bincount(pt, weights=wrong & (V['facing'] == 1), minlength=n)
    orr = nr-fr; ow = nw-fw
    def maj(a_, b_): return np.where(a_ > b_, 1, np.where(b_ > a_, -1, 0))
    mf, mo = maj(fr, fw), maj(orr, ow); viewdep = ((fr+fw) >= 2) & ((orr+ow) >= 2) & (mf != 0) & (mo != 0) & (mf != mo)
    mesh_wrong = ~res & (P['set'] == 0)
    cls4 = np.where(nseen < 3, '4-마', np.where(ne*2 > nseen, '4-라', np.where(viewdep, '4-나',
                    np.where(np.where(res, nw*2 > nseen, nr*2 > nseen) & (mesh_wrong | res), '4-가', np.where(np.where(res, nr*2 > nseen, nw*2 > nseen), '4-다', '4-확인불가')))))
    fwd4 = (isl & ~res & ((c1 == '1-라') | (c3x == '3-바'))) | (isl & res) | (P['set'] == 1)
    c4 = np.full(n, NA, object); c4[fwd4] = cls4[fwd4]
    aux.update(views_right=nr, views_wrong=nw, views_empty=ne, facing_right=fr, facing_wrong=fw, oblique_right=orr, oblique_wrong=ow)
    pair = dict(point=pt, view=V['view'], d_normal_m=dv.astype('f4'), empty=empty, right=right, ref_z=np.where(res[pt], V['zbuf'], V['z']).astype('f4'),
                target_z=V['tdepth'], render_z=Rr['rdepth'], mesh_z=V['mesh_z'], facing=V['facing'], alpha=Rr['ralpha'])
    out = dict(cell=P['cell'], set=P['set'], row=P['row'], point_id=point_id, xyz=X, normal=Nn, tau=tau, result=res, patch_row=patch_row, wall=wall,
               check1=c1.astype('U12'), check2=c2.astype('U12'), check3=c3.astype('U12'), check3_empty=c3x.astype('U12'), check4=c4.astype('U12'),
               check3_all=cls3.astype('U12'), check4_all=cls4.astype('U12'), **{k: v for k, v in aux.items()})
    savez(BASE/'checks'/f'{name}.npz', **out); savez(BASE/'checks'/f'{name}_pairs.npz', **pair)
    dump(BASE/'checks'/f'{name}.json', dict(at=now(), stem=stem, arm=arm, tag=tag or None, points=n, pairs=len(pt), trained_mesh=str(trained_mesh), model=str(model), seconds=t.done(), scientific_verdict=None))
    print('CHECKS_DONE', name, n, flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
