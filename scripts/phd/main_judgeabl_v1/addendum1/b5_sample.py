"""덧붙임 1 확인 5의 2, 6, 7, 8 (표본 사진 점만 사진을 다시 읽음, 참값 없음). 사용: b5_sample.py <prior>
표본: 한계 안 패치만 가진 사진 점(all_within) 3,000개, 씨앗 20261117, 탐색 지역마다 넓이에 비례. 사전 정보 면(조각 0)만.
조각: JC photo_score 의 격자(25 x 25, 2 cm, 높이 0)와 피라미드 단계 규칙, 원본 JPEG 회색(JC photo_cameras.gray_pyramid), 쌍선형 표본.
차이(설정에 적음): 잘라낸 마스크 없이 조각 전체, 80° 확장 선택의 가림 검사는 MVS 깊이 지도(0.5 m)."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1')
from common import *
import pandas as pd, cv2, collections
sys.path.insert(0, '/repo/scripts/phd/main_judgecheck_v2/inherited')
from photo_cameras import Cameras
TAB = D/'tables/addendum1'; A1 = O/'addendum1'
OFF = np.stack(np.meshgrid(np.arange(25)*.02 - .24, np.arange(25)*.02 - .24, indexing='xy'), -1).reshape(625, 2)
CORN = np.array([[-.25, -.25], [.25, -.25], [.25, .25], [-.25, .25]])
def ncc_vec(x):
    c = x - x.mean(-1, keepdims=True); n = np.linalg.norm(c, axis=-1, keepdims=True); return np.where(n > 1e-6, c/np.maximum(n, 1e-12), np.nan)
def score_of(V):
    """V: (K,625) 정규화 벡터 -> 쌍 평균 NCC (K >= 3)."""
    K = len(V)
    if K < 3: return np.nan
    G = V @ V.T; return float((G.sum() - np.trace(G))/(K*(K - 1)))
def autocorr_len(x):
    a = (x - x.mean()).reshape(25, 25); f = np.fft.fft2(a, s=(50, 50)); ac = np.real(np.fft.ifft2(f*np.conj(f))); ac = np.fft.fftshift(ac); ac /= ac[25, 25] if ac[25, 25] > 0 else 1
    yy, xx = np.mgrid[-25:25, -25:25]; r = np.hypot(yy, xx); prof = np.array([ac[(r >= k - .5) & (r < k + .5)].mean() for k in range(13)])
    k = np.flatnonzero(prof < np.exp(-1)); return float(k[0]*.02) if len(k) else np.nan
def main(prior):
    lock = json.loads((C/'judgeabl_v1_addendum1.lock.json').read_text()); assert sha(C/'judgeabl_v1_addendum1.json') == lock['config_sha256']
    T = Timer(); rng = np.random.default_rng([20261117, 0 if prior == 'LoD2' else 1]); P = loadz(JP/f'photo_{prior}.npz', ['tile', 'row', 'kind', 'area', 'region', 'all_within', 's_P', 'texture', 'n_selected'])
    pool = np.flatnonzero(P['all_within'] & np.isfinite(P['s_P'])); rk = np.where(np.isin(P['region'], REGIONS), P['region'], 'none')
    ar = pd.Series(P['area'][pool]).groupby(rk[pool]).sum(); alloc = np.floor(3000*ar/ar.sum()).astype(int); alloc[alloc.idxmax()] += 3000 - alloc.sum(); S = []
    for reg, k in alloc.items():
        c = pool[rk[pool] == reg]; S.append(rng.choice(c, min(k, len(c)), replace=False))
    S = np.sort(np.concatenate(S)); ts = list(loadz(JP/f'patch_{prior}.npz', ['tiles'])['tiles'])
    jt = {(r['region'], r['prior'], r['kind']): r['t'] for r in json.loads((JC/'judge/base.json').read_text())['t_rows']}
    # 점 기하
    cen = np.zeros((len(S), 3)); nor = cen.copy(); e1 = cen.copy(); e2 = cen.copy(); sel = np.full((len(S), 10), -1)
    for ti in np.unique(P['tile'][S]):
        q = loadz(JC/'photo_prepared'/f'{ts[ti]}.npz', ['centres', 'normals', 'tangent1', 'tangent2', 'selected_images']); m = np.flatnonzero(P['tile'][S] == ti); r = P['row'][S[m]]
        cen[m], nor[m], e1[m], e2[m], sel[m] = q['centres'][r, 0], q['normals'][r, 0], q['tangent1'][r, 0], q['tangent2'][r, 0], q['selected_images'][r, 0]
    cam = Cameras(); NJ = len(cam.names); f2 = np.sqrt(cam.p[0]*cam.p[1]); cos80 = np.cos(np.radians(80))
    jobs = collections.defaultdict(list); ang = {}
    for j in range(NJ):
        v = cam.centres[j] - cen; dist = np.linalg.norm(v, axis=1); cs = np.einsum('ij,ij->i', v, nor)/dist
        cand = np.flatnonzero(cs >= cos80)
        if not len(cand): continue
        cx = cen[cand, None, :] + CORN[None, :, 0, None]*e1[cand, None, :] + CORN[None, :, 1, None]*e2[cand, None, :]
        uv, _, g = cam.project(cx, j); ok = g.all(1) & (uv[..., 0] >= 20).all(1) & (uv[..., 0] < cam.w - 20).all(1) & (uv[..., 1] >= 20).all(1) & (uv[..., 1] < cam.h - 20).all(1)
        stored = (sel[cand] == j).any(1); cand2 = cand[ok | stored]
        for i in cand2: jobs[j].append(int(i)); ang[(int(i), j)] = (float(np.degrees(np.arccos(np.clip(cs[i], -1, 1)))), float(dist[i]), bool((sel[i] == j).any()))
    print('JOBS', prior, len(S), sum(len(v) for v in jobs.values()), round(T.s()), flush=True)
    SAMP = {}; DEP = {}
    for jc, (j, pts) in enumerate(sorted(jobs.items())):
        pts = np.array(pts); dist = np.array([ang[(i, j)][1] for i in pts]); gsd = dist/f2; lev = np.argmin(np.abs(gsd[:, None]*2.**np.arange(6) - .02), axis=1); lev[gsd >= .02] = 0
        # 80° 확장분의 가림: MVS 깊이 (저장 선택은 그대로 둠)
        dep = cam.depth(j); uvc, zc, gc = cam.project(cen[pts], j)
        if dep is not None:
            px = np.clip(np.rint(uvc*[dep.shape[1]/cam.w, dep.shape[0]/cam.h]).astype(int), 0, [dep.shape[1] - 1, dep.shape[0] - 1]); dd = dep[px[:, 1], px[:, 0]]
            vis = np.isfinite(dd) & (dd > 0) & (zc <= dd + .5)
        else: vis = np.zeros(len(pts), bool)
        ims = cam.gray_pyramid(int(j), set(lev.tolist()))
        for i, l, vv in zip(pts, lev, vis):
            stored = ang[(i, j)][2]
            if not (stored or vv): continue
            X = cen[i] + OFF[:, 0, None]*e1[i] + OFF[:, 1, None]*e2[i]; uv, _, g = cam.project(X, j)
            if not g.all(): continue
            im = ims[int(l)]; ih, iw = im.shape; u = (uv[:, 0] + .5)*(iw/cam.w) - .5; v = (uv[:, 1] + .5)*(ih/cam.h) - .5
            if (u < 0).any() or (u > iw - 1).any() or (v < 0).any() or (v > ih - 1).any(): continue
            x = cv2.remap(np.ascontiguousarray(im), u.astype(np.float32)[None], v.astype(np.float32)[None], cv2.INTER_LINEAR)[0].astype(np.float64)
            SAMP[(int(i), int(j))] = (x, int(l), ang[(i, j)][0], gsd[list(pts).index(i)]*2**int(l)/max(np.cos(np.radians(ang[(i, j)][0])), 1e-3), stored)
        if jc % 100 == 0: print('IMG', jc, len(jobs), round(T.s()), flush=True)
    print('SAMPLED', len(SAMP), round(T.s()), flush=True)
    R5, R6, R7, R8, PTS = [], [], [], [], []
    for a, i in enumerate(range(len(S))):
        g = S[i]; t = jt.get((rk[g], prior, int(P['kind'][g])), np.nan); unit = f"{'LoD2' if prior == 'LoD2' else '항공 LiDAR'} {'지붕' if P['kind'][g] == 1 else '벽'}"
        st = [j for j in sel[i] if j >= 0 and (i, j) in SAMP]; X = np.array([SAMP[(i, j)][0] for j in st]) if st else np.zeros((0, 625))
        rec = dict(point=int(g), unit=unit, region=rk[g], area=float(P['area'][g]), t=t, s_P_stored=float(P['s_P'][g]), texture_stored=float(P['texture'][g, 0]), views=len(st))
        if len(st) >= 2:
            V = ncc_vec(X); rec['s_P_full'] = score_of(V); tex = np.median(X.std(1)); rec['texture_full'] = float(tex)
            noise = []
            for p in range(len(st)):
                for q in range(p + 1, len(st)):
                    A_ = np.c_[X[p], np.ones(625)]; coef = np.linalg.lstsq(A_, X[q], rcond=None)[0]; noise.append(np.std(X[q] - A_ @ coef)/np.sqrt(2))
            rec['sigma_n'] = float(np.median(noise))
            # 8: 닮는 거리, 조각 크기
            rec['corr_len_m'] = float(np.nanmedian([autocorr_len(x) for x in X])); rec['footprint_m'] = float(np.median([SAMP[(i, j)][3] for j in st]))
            for k in [15, 20]:
                o = (25 - k)//2; idx = (np.arange(25)[:, None]*0 + np.arange(25)[None, :]); mm = np.zeros((25, 25), bool); mm[o:o + k, o:o + k] = True
                rec[f's_P_{k}'] = score_of(ncc_vec(X[:, mm.ravel()]))
            # 7: 앞의 k장
            if len(st) == 10 and (sel[i] >= 0).sum() == 10:
                for k in range(2, 11): rec[f's_k{k}'] = float(V[0] @ V[1]) if k == 2 else score_of(V[:k])
        # 6: 80° 까지 모든 쌍
        allj = [j for (ii, j) in SAMP if ii == i]
        if len(allj) >= 2:
            Va = ncc_vec(np.array([SAMP[(i, j)][0] for j in allj])); angs = np.array([SAMP[(i, j)][2] for j in allj]); fp = np.array([SAMP[(i, j)][3] for j in allj])
            G = Va @ Va.T; pi, pj = np.triu_indices(len(allj), 1)
            for p, q in zip(pi, pj): R6.append(dict(unit=unit, region=rk[g], area=float(P['area'][g]), max_angle=max(angs[p], angs[q]), ncc=float(G[p, q]), below_t=bool(G[p, q] < t) if np.isfinite(t) else np.nan))
            for j, a_, f_ in zip(allj, angs, fp): R8.append(dict(unit=unit, angle=a_, footprint_m=f_))
        PTS.append(rec)
    df = pd.DataFrame(PTS); df.to_csv(A1/f'sample_points_{prior}.csv', index=False); pd.DataFrame(R6).to_csv(A1/f'sample_pairs_{prior}.csv', index=False); pd.DataFrame(R8).to_csv(A1/f'sample_views_{prior}.csv', index=False)
    dump(A1/f'sample_{prior}.json', dict(at=now(), prior=prior, points=len(S), jobs=int(sum(len(v) for v in jobs.values())), patches_sampled=len(SAMP), seconds=T.s(), scientific_verdict=None))
    progress(f'덧붙임 1 표본 사진 {prior}: 점 {len(S)}, 조각 {len(SAMP)}, {round(T.s())} 초')
if __name__ == '__main__': main(sys.argv[1])
