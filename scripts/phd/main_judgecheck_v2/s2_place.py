"""자리 (발주 2.4)와 면 나눔. 참값 쓰지 않음.
면: LoD2 = surf, ALS = 같은 건물 패치를 0.36 m 안으로 잇되 법선(다시 맞춘 LiDAR 법선) 20 도 이하, 중심 높이 차 0.5 m 이하인 것만 잇는 덩어리.
자리: 패치 중심에서 1.5 m 원(패치 접평면 t1,t2) 안 0.18 m 격자 표본마다, 같은 사전 정보 패치 중심이 접평면 투영 0.18 m 안이고 법선 방향 1.5 m 안이면 채움.
  채운 표본의 면 = 그 표본에 가장 가까운 패치의 면.
  0 면 안쪽(모든 표본이 같은 면), 1 면 경계(다른 면·다른 건물로만 채워진 표본이 있음), 2 건물 가장자리(빈 표본이 있음; 가장자리가 경계보다 앞섬)."""
from common import *
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import multiprocessing as mp
G = {}
def als_faces(c, n, b):
    face = np.full(len(c), -1, np.int64); nxt = 0
    for bid in np.unique(b):
        ix = np.flatnonzero(b == bid); ok = ix[np.isfinite(n[ix]).all(1)]
        if not len(ok): continue
        pairs = cKDTree(c[ok]).query_pairs(.36, output_type='ndarray')
        if len(pairs):
            cosang = np.abs(np.einsum('ij,ij->i', n[ok[pairs[:, 0]]], n[ok[pairs[:, 1]]])); dz = np.abs(c[ok[pairs[:, 0]], 2] - c[ok[pairs[:, 1]], 2])
            pairs = pairs[(cosang >= np.cos(np.deg2rad(20))) & (dz <= .5)]
        gph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])) if len(pairs) else ([], ([], [])), shape=(len(ok), len(ok)))
        k, lab = connected_components(gph, directed=False); face[ok] = nxt + lab; nxt += k
    return face
R0, GRID = 1.5, 0.18
ax = np.arange(-R0, R0 + 1e-9, GRID); AA, BB = np.meshgrid(ax, ax); keep = AA**2 + BB**2 <= R0**2 + 1e-9; SA, SB = AA[keep], BB[keep]
def work(ids):
    c, n, t1, t2, face, bld, tree = G['c'], G['n'], G['t1'], G['t2'], G['face'], G['bld'], G['tree']
    out = []
    for i in ids:
        if not (np.isfinite(n[i]).all() and np.isfinite(t1[i]).all()): out.append((i, -1, 0, 0, 0)); continue
        near = np.asarray(tree.query_ball_point(c[i], np.hypot(R0 + GRID, R0) + 1e-6), int)
        v = c[near] - c[i]; h = v @ n[i]; near = near[np.abs(h) <= R0]; v = c[near] - c[i]
        pu, pv = v @ t1[i], v @ t2[i]
        st = cKDTree(np.c_[pu, pv]); dist, j = st.query(np.c_[SA, SB], distance_upper_bound=GRID)
        filled = np.isfinite(dist); empty = int((~filled).sum())
        jj = near[j[filled]]; same = (face[jj] == face[i]) & (bld[jj] == bld[i])   # 표본에 가장 가까운 패치(0.18 m 안)의 면
        other = int((~same).sum())
        out.append((i, 2 if empty else (1 if other else 0), empty, other, int(filled.sum())))
    return out
def main(prior):
    cfg(); T = Timer(); files = sorted((O/'geometry_raw').glob(f'*__{prior}.npz')); parts = []; offs = []; n0 = 0
    for p in files:
        g = loadz(p, ['patch_id', 'centre', 'normal', 'tangent1', 'tangent2', 'building', 'surf', 'kind', 'area'])
        if prior == 'ALS':
            t1 = np.full_like(g['normal'], np.nan); t2 = t1.copy()
            for i, nn in enumerate(g['normal']):
                if np.isfinite(nn).all():
                    a = np.array([1., 0., 0.]) if abs(nn[0]) < .9 else np.array([0., 1., 0.]); e = a - nn*(a@nn); e /= np.linalg.norm(e); t1[i] = e; t2[i] = np.cross(nn, e)
            g['tangent1'], g['tangent2'] = t1, t2
        parts.append(g); offs.append((p.name, n0, n0 + len(g['kind']))); n0 += len(g['kind'])
    d = {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}; del parts
    face = als_faces(d['centre'], d['normal'], d['building']) if prior == 'ALS' else d['surf'].astype(np.int64)
    G.update(c=d['centre'], n=d['normal'], t1=d['tangent1'], t2=d['tangent2'], face=face, bld=d['building'], tree=cKDTree(d['centre'], leafsize=32))
    N = len(face); place = np.full(N, -1, np.int8); empty = np.zeros(N, np.int16); other = np.zeros(N, np.int16); filled = np.zeros(N, np.int16)
    blocks = [np.arange(i, min(i+2000, N)) for i in range(0, N, 2000)]; done = 0
    with mp.get_context('fork').Pool(int(os.environ.get('JC2_CPUS', '4'))) as pool:
        for res in pool.imap_unordered(work, blocks):
            for i, pl, e, o, f in res: place[i] = pl; empty[i] = e; other[i] = o; filled[i] = f
            done += len(res)
            if done % 200000 < 2000: print('PLACE', prior, done, N, round(T.mark('x')), flush=True)
    for name, l, r in offs:
        savez(O/'place'/name, patch_id=d['patch_id'][l:r], place=place[l:r], face=face[l:r], empty_samples=empty[l:r], other_face_samples=other[l:r], filled_samples=filled[l:r])
    a = d['area']; rec = dict(at=now(), prior=prior, patches=N, samples_per_circle=int(len(SA)), area_m2={str(k): float(a[place == k].sum()) for k in [-1, 0, 1, 2]}, faces=int(len(np.unique(face[face >= 0]))), seconds=T.mark('end'), GT_read=False, scientific_verdict=None)
    dump(O/'place'/f'{prior}.json', rec); print('PLACE_DONE', json.dumps(rec), flush=True)
if __name__ == '__main__': main(sys.argv[1])
