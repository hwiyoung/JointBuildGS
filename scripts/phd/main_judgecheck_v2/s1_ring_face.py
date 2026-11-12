"""같은 면 고리 (발주 6.1 '같은 면 고리' 판): 고리 바깥 반지름 1.5 m, UNCERT 커널(ring_kernel column/ring_points, u_core find_face/lmeds_plane/stats)을
그대로 쓰되, 안쪽 원(상한 2000)과 고리(상한 8000) 점 가운데 패치 법선 방향으로 사전 정보 면에 투영해 같은 면에 떨어지는 점만 남긴다.
같은 면: LoD2 = 투영(±n 광선, 3 m 안 가장 가까운 맞음)한 삼각형의 tri_surface == 패치 surf; ALS = (점 - 지역 이동)을 ALS TIN 에 투영한 자리에서
0.25 m 안 가장 가까운 ALS 패치의 면(s2_place) == 패치 면. 남은 점이 min_inner 5 / min_ring 20 보다 적으면 상태 2(u_M 없음). 시드는 R1.5 와 같다.
  s1_ring_face.py <tile>  -> ring/face/<tile>__<prior>.npz (u_mvs_face, status, n_inner_face, n_ring_face; ALS 는 sigma_P_face 도)."""
from common import *
sys.path.insert(0, str(HERE/'inherited'))
import ring_kernel as K
import s1_ring as SR
from scipy.spatial import cKDTree
import multiprocessing as mp
C = K.C; D = K.D; RI = K.RI; F = {}
def scene():
    if 'scene' not in F:
        import open3d as o3d
        s = o3d.t.geometry.RaycastingScene(nthreads=1); s.add_triangles(o3d.core.Tensor(F['V'].astype('f4')), o3d.core.Tensor(F['F'].astype('u4'))); F['scene'] = s; F['o3d'] = o3d
    return F['scene']
def same_face(i, P):
    """P: 점 좌표(MVS 틀 또는 ALS raw 틀). 반환 bool."""
    s = scene(); o3d = F['o3d']; n = K.G['n'][i]; Q = P - F['shift'][i]
    best = np.full(len(Q), np.inf); prim = np.full(len(Q), -1, np.int64); sg = np.zeros(len(Q))
    for sign in (1., -1.):
        r = np.c_[Q, np.broadcast_to(sign*n, Q.shape)].astype('f4'); a = s.cast_rays(o3d.core.Tensor(r)); t = a['t_hit'].numpy(); pid = a['primitive_ids'].numpy().astype(np.int64)
        take = np.isfinite(t) & (t <= 3.) & (t < best); best[take] = t[take]; prim[take] = pid[take]; sg[take] = sign
    hit = prim >= 0
    if F['prior'] == 'LoD2':
        ok = np.zeros(len(Q), bool); ok[hit] = F['tri_surface'][prim[hit]] == F['surf'][i]; return ok
    proj = Q + (sg*np.where(hit, best, 0))[:, None]*n
    d, j = F['ptree'].query(proj, distance_upper_bound=.25); ok = hit & np.isfinite(d)
    out = np.zeros(len(Q), bool); jj = np.where(ok, j, 0); out[ok] = (F['pface'][jj[ok]] == F['face'][i]) & (F['pbld'][jj[ok]] == F['bld'][i]); return out
def one(i):
    t0 = time.time(); data = K.G['data']; idx, t, rho, H = K.column(i); o, runs, M = C.find_face(t, H, D)
    r = dict(status=1, n_inner=0, n_ring=0)
    if o is None: return r
    m = np.abs(t - o) <= D['slab_half_m']; inn = idx[m]; cap_i = D['mvs_cap_inner'] if data == 'mvs_a' else None
    if cap_i and len(inn) > cap_i: inn = inn[np.argsort(inn)[:cap_i]]
    ridx, L, lev, found = K.ring_points(i, o, 1.5, int(m.sum()))
    c = K.G['c'][i]; keep_i = same_face(i, K.G['X'][inn]); keep_r = same_face(i, K.G['X'][ridx]) if len(ridx) else np.zeros(0, bool)
    inn = inn[keep_i]; ridx = ridx[keep_r]; r.update(n_inner=int(len(inn)), n_ring=int(len(ridx)))
    if len(inn) < D['min_inner'] or len(ridx) < D['min_ring']: r['status'] = 2; return r
    Q = K.G['X'][inn] - c; Pp = K.G['X'][ridx] - c; n = K.G['n'][i]
    rng = np.random.default_rng([K.U.CFG['seed'], K.U.SITE_ID[K.G['site']], K.U.SET_ID[K.G['pset']], K.U.DATA_ID[data], K.U.R_ID[1.5], int(K.G['original_index'][i])])
    pl = C.lmeds_plane(Pp, n, rng, D)
    if pl is None: r['status'] = 3; return r
    d = (Q - pl['point']) @ pl['normal']; st = C.stats(d, D); r.update(status=0, u=st['u']); return r
def chunk(ids): return [(int(i), one(int(i))) for i in ids]
def main(tile):
    cfg(); dests = {}; T = Timer()
    for prior in ['LoD2', 'ALS']:
        if (O/'geometry_raw'/f'{tile}__{prior}.npz').exists(): dests[prior] = O/'ring/face'/f'{tile}__{prior}.npz'
    if not dests or all(p.exists() for p in dests.values()): return
    geo = {}; res = {}
    for prior in dests:
        d = loadz(O/'geometry_raw'/f'{tile}__{prior}.npz'); pg = loadz(WI/'patch_geometry'/f'{tile}_{prior}.npz', ['patch_id']); pos = {s: i for i, s in enumerate(pg['patch_id'])}
        d['widen0_index'] = np.array([pos[s] for s in d['patch_id']], np.int64); d['face'] = loadz(O/'place'/f'{tile}__{prior}.npz', ['face'])['face']; geo[prior] = d; res[prior] = dict(patch_id=d['patch_id'])
    for data in ['mvs_a', 'als']:
        priors = list(dests) if data == 'mvs_a' else [p for p in dests if p == 'ALS']
        if not priors: continue
        SR.setup(tile, data)
        for prior in priors:
            d = geo[prior]; N = len(d['kind']); ok = d['normal_defined'] & np.isfinite(d['old_normal']).all(1); ids = np.flatnonzero(ok)
            if prior == 'LoD2':
                m = loadz(WI/'prior_tiles'/tile/'lod2_mesh.npz', ['V', 'F', 'tri_surface']); F.clear(); F.update(V=m['V'], F=m['F'], tri_surface=m['tri_surface'], prior='LoD2', surf=d['surf'], shift=np.zeros((N, 3)))
            else:
                m = loadz(WI/'prior_tiles'/tile/'als_mesh.npz', ['V', 'F']); F.clear()
                allc = []; allf = []; allb = []
                for q in (O/'geometry_raw').glob('*__ALS.npz'):
                    z = loadz(q, ['raw_centre', 'building']); fz = loadz(O/'place'/q.name, ['face'])['face']
                    mm = ((z['raw_centre'][:, :2] >= d['raw_centre'][:, :2].min(0) - 5) & (z['raw_centre'][:, :2] <= d['raw_centre'][:, :2].max(0) + 5)).all(1)
                    allc.append(z['raw_centre'][mm]); allf.append(fz[mm]); allb.append(z['building'][mm])
                F.update(V=m['V'], F=m['F'], prior='ALS', ptree=cKDTree(np.concatenate(allc)), pface=np.concatenate(allf), pbld=np.concatenate(allb), face=d['face'], bld=d['building'],
                         shift=(d['shift_m'] if data == 'mvs_a' else np.zeros((N, 3))))
            K.G.update(radii=[1.5], pset=prior, c=(d['centre'] if data == 'mvs_a' else d['raw_centre']), n=d['old_normal'], roof=d['roof_like'], original_index=d['widen0_index'])
            u = np.full(N, np.nan); st = np.full(N, -1, np.int8); ni = np.full(N, -1, np.int32); nr = ni.copy()
            blocks = [ids[i:i+100] for i in range(0, len(ids), 100)]; done = 0
            with mp.get_context('fork').Pool(SR.WORKERS) as pool:
                for out in pool.imap_unordered(chunk, blocks):
                    for i, r in out:
                        st[i] = r['status']; ni[i] = r['n_inner']; nr[i] = r['n_ring']
                        if r['status'] == 0: u[i] = r['u']
                    done += len(out)
                    if done % 20000 < 100: print('RING_FACE', tile, prior, data, done, len(ids), round(T.mark('x')), flush=True)
            key = 'u_mvs' if data == 'mvs_a' else 'sigma_P'
            res[prior].update({f'{key}_face': u, f'{key}_status_face': st, f'{key}_n_inner_face': ni, f'{key}_n_ring_face': nr})
        K.G.clear()
    for p, dst in dests.items(): savez(dst, **res[p])
    dump(O/'ring/face'/f'{tile}.json', dict(at=now(), tile=tile, seconds=T.mark('end'), workers=SR.WORKERS, GT_read=False, scientific_verdict=None)); print('RING_FACE_DONE', tile, round(T.mark('end')), flush=True)
if __name__ == '__main__': main(sys.argv[1])
