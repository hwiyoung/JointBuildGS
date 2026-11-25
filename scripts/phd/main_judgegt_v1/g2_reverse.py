"""단계 2: 역방향 정답 (영상 쪽 패치마다). 참값은 정답을 만드는 데만.
영상 쪽 패치: 범위 안 영상 깊이 점(구역 자기 100 m 칸, 범위 건물의 LoD2 패치 중심에서 XY 1.0 m 안)을 0.25 m 3차원 격자로 추리고,
  칸마다 점들의 평균에 가장 가까운 점 = 패치 중심. 법선 = 중심 0.5 m 안 영상 점(구역 점 파일 모두)에 맞춘 평면, 10점 미만이면 1.0 m, 그래도 모자라면 만들지 않음(셈).
  방향 = 가장 가까운 학습 카메라 쪽 양. 연직에서 45° 안이면 지붕, 아니면 벽.
가장 가까운 사전 정보 패치(151동 그 사전 정보 패치의 면 위 점 = 중심 + 사전 정보 높이 × 법선): 옆·법선 거리, τ = 그 패치의 지역·사전 정보·지붕·벽.
기둥(0.25 × 0.25 m, 영상 쪽 패치 법선, 지붕 ±10 / 벽 ±5 m) 안 참값 점: [−τ, τ] 4개 이상 = 영상 사용(새 면), 그 밖에 기둥 안 4개 이상 = 버림, 4개 미만 = 정답 없음.
사용: GT_STAGE=ga|full g2_reverse.py"""
from common import *
from scipy.spatial import cKDTree
def geometry(c, B):
    R = c['reverse']; dest = O/'work'/STAGE/'reverse_geometry.npz'
    if dest.exists(): return loadz(dest)
    P = loadz(inp('patches', prior='LoD2'), ['tile', 'centre', 'building', 'tiles']); tiles = list(P['tiles']); sc = np.isin(P['building'], list(B))
    cams, ntrain = camera_centres(); ct = cKDTree(cams); out = {k: [] for k in ['centre', 'normal', 'kind', 'tile', 'cell_points', 'normal_radius', 'normal_points']}; rec = []; T = Timer()
    allc = P['centre'][sc][:, :2]; ttree = cKDTree(allc)
    for t in tiles:
        x0, x1, y0, y1 = tile_core(t); w = R['evaluation_range_xy_m']
        near = ttree.query_ball_point([(x0+x1)/2, (y0+y1)/2], r=75.)
        if not near: continue
        t0 = T.s(); f = WI/'points'/t/'mvs_a_xyz.npy'; X = np.load(f, mmap_mode='r'); sub = allc[near]; lo = sub.min(0) - w; hi = sub.max(0) + w
        keep = []
        for s in range(0, len(X), 20_000_000):
            q = np.asarray(X[s:s+20_000_000], np.float64); m = (q[:, 0] >= max(x0, lo[0])) & (q[:, 0] < min(x1, hi[0])) & (q[:, 1] >= max(y0, lo[1])) & (q[:, 1] < min(y1, hi[1]))
            ii = np.flatnonzero(m)
            if len(ii):
                d, _ = cKDTree(sub).query(q[ii, :2], distance_upper_bound=w, workers=int(os.environ.get('GT_THREADS', '24'))); keep.append(q[ii[np.isfinite(d)]])
        Q = np.concatenate(keep) if keep else np.empty((0, 3))
        if not len(Q): continue
        g = np.floor(Q/R['grid_m']).astype(np.int64); g -= g.min(0); dims = g.max(0) + 1; key = (g[:, 0]*dims[1] + g[:, 1])*dims[2] + g[:, 2]
        uk, inv, cnt = np.unique(key, return_inverse=True, return_counts=True); mean = np.stack([np.bincount(inv, weights=Q[:, k], minlength=len(uk)) for k in range(3)], 1)/cnt[:, None]
        d2 = ((Q - mean[inv])**2).sum(1); o = np.lexsort((d2, inv)); first = o[np.r_[0, np.flatnonzero(np.diff(inv[o])) + 1]]; cen = Q[first]
        pc = run('pca', f, cen, f'pca_{STAGE}_{t}'); mn = R['normal_min_points']
        use5 = pc[:, 0] >= mn; use10 = ~use5 & (pc[:, 4] >= mn); nr = np.where(use5[:, None], pc[:, 1:4], pc[:, 5:8]); ok = use5 | use10
        _, ci = ct.query(cen); sgn = np.sign(np.einsum('ij,ij->i', cams[ci] - cen, nr)); sgn[sgn == 0] = 1; nr = nr*sgn[:, None]
        kind = np.where(np.abs(nr[:, 2]) >= np.cos(np.deg2rad(R['roof_max_angle_from_vertical_deg'])), 1, 2).astype(np.int8)
        for k, v in dict(centre=cen[ok], normal=nr[ok], kind=kind[ok], tile=np.full(ok.sum(), tiles.index(t), np.int16), cell_points=cnt[inv[first]][ok],
                         normal_radius=np.where(use5, .5, 1.)[ok], normal_points=np.where(use5, pc[:, 0], pc[:, 4])[ok]).items(): out[k].append(v)
        rec.append(dict(tile=t, points_in_range=len(Q), cells=len(cen), no_normal=int((~ok).sum()), radius_1m=int(use10.sum()), seconds=T.s() - t0)); print('REVGEO', rec[-1], flush=True)
    G = {k: np.concatenate(v) for k, v in out.items()}; G['tiles'] = np.array(tiles); savez(dest, **G)
    dump(dest.with_suffix('.json'), dict(at=now(), stage=STAGE, train_cameras=len(cams), train_listed=ntrain, rows=rec, scientific_verdict=None)); return G
def main():
    c = cfg(); R = c['reverse']; build(); B = buildings(); Ball = buildings('full'); tau = tau_table(); T = Timer()
    G = geometry(c, B); tiles = list(G['tiles'])
    for prior in PRIORS:
        dest = O/'work'/STAGE/f'reverse_{prior}.npz'
        if dest.exists(): continue
        P = loadz(inp('patches', prior=prior), ['centre', 'normal', 'prior_height_m', 'kind', 'region', 'building'])
        ok = np.isin(P['building'], list(Ball)) & np.isfinite(P['prior_height_m']) & np.isfinite(P['normal']).all(1); pi = np.flatnonzero(ok)
        S = P['centre'][pi] + P['prior_height_m'][pi][:, None]*P['normal'][pi]; d, j = cKDTree(S).query(G['centre'], workers=int(os.environ.get('GT_THREADS', '24')))
        near = pi[j]; v = G['centre'] - S[j]; nP = P['normal'][near]; dn = np.einsum('ij,ij->i', v, nP); lat = np.linalg.norm(v - dn[:, None]*nP, axis=1)
        nk = P['kind'][near]; key = np.where(nk == 2, f'{prior}_wall', f'{prior}_roof') if prior == 'LoD2' else np.full(len(near), 'ALS_roof')
        TAU = np.array([tau[r][k] for r, k in zip(P['region'][near], key)]); H = np.where(G['kind'] == 2, R['column_half_length_m']['wall'], R['column_half_length_m']['roof']).astype(float)
        res = np.full((len(near), 17), np.nan)
        for ti in np.unique(G['tile']):
            m = np.flatnonzero(G['tile'] == ti); t = tiles[ti]
            res[m] = run('col', WI/'points'/t/'gt_xyz.npy', np.c_[G['centre'][m], G['normal'][m], np.zeros((len(m), 3)), np.full(len(m), R['cell_half_m']), H[m], TAU[m], np.full(len(m), np.nan)], f'rcol_{STAGE}_{prior}_{t}')
        a = np.full(len(near), 2, np.int8); a[res[:, 0] >= 4] = 1; a[res[:, 1] >= 4] = 0
        savez(dest, answer=a, near_patch=near, near_lateral_m=lat, near_normal_m=dn, near_dist_m=d, tau=TAU, n_total=res[:, 0], n_b0=res[:, 1], n_dens=res[:, 3], n_cl=res[:, 4], cl=res[:, 5:])
        progress(f'단계 2 역방향 {STAGE} {PN[prior]}: 영상 쪽 패치 {len(near):,}, {T.s():.0f} s'); print('REV', prior, len(near), np.bincount(a, minlength=3), flush=True)
if __name__ == '__main__': main()
