"""덧붙임 1 6절(묶음 라): 건물별 판단 평가 뷰어(인터넷 없이 열리는 HTML 하나 = 건물 하나 x 사전 정보 하나, 10동). 학습 없음, 저장값만 읽음.
JUDGEGT g9_viewer2.py 를 복사해 고침(그 파일은 그대로). 범위 = 건물 LoD2 다각형 XY + 10 m. 층: 사전 정보 면, 영상 깊이 점, 참값 점(층마다 30만 점까지 씨앗 고정 솎음), 패치(솎지 않음).
패치 색: 정답 / ① / ② / ③ / 판정 넷 / 판단 맞음·틀림(틀림은 판정을 정한 단계로) / 목표 맞음·틀림 (판 4, judge4_<prior>.npz).
기둥 점을 솎지 않고 담는 패치(파일 크기 때문에 모두는 못 담음): 틀림 목록(정답 → 판정 칸마다 다섯) + 정답 x 판정 칸마다 20개 + 채점 밖 정답마다 10개(씨앗 고정).
  그 패치마다: 원통(반지름 1.5 m, 반길이 지붕 10 / 벽 5 m) 안 점 가운데 두께 ±0.125 m 의 참값·영상 점(mm), ②를 거친 패치는 영상마다 중심 시선 끝, ③을 거친 패치는 ③ 시작 점과 일관됨(judgevis fuse 다시).
VIEWER_V=2 이면 judge4_v2_<prior>.npz(덧붙임 2 목표 값)를 읽어 docs/figures/viewer_v2/ 에 씀(앞 판 그대로).
나오는 것: docs/figures/viewer/<지역>_<건물>_<사전 정보>.html(+json), index.json. 사용: GT_STAGE=ga3 g17_viewer.py"""
from common import *
import pandas as pd, base64
from g11_figs import read_depth
A1 = json.loads((C/'judgeeval_v1_add1.json').read_text()); assert sha(C/'judgeeval_v1_add1.json') == json.loads((C/'judgeeval_v1_add1.lock.json').read_text())['config_sha256']
V2 = os.environ.get('VIEWER_V', '1') == '2'   # 덧붙임 2: 목표 값 v2(h_M = 저장 mvs_mean_m), 판단은 같음
if V2: assert sha(C/'judgeeval_v1_add2.json') == json.loads((C/'judgeeval_v1_add2.lock.json').read_text())['config_sha256'], 'add2 config changed after lock'
VD = D/('figures/viewer_v2' if V2 else 'figures/viewer'); SHIFT = np.array([690953.0, 5336071.0, 604.0]); PL = {'면 안쪽': 0, '면 경계': 1, '건물 가장자리': 2, '자리 없음': 3}
COLG = json.loads((R/'configs/phd/main_judgegt_v1/judgegt_v1.json').read_text())['colours']
J4N = ['두 자료', '영상', '사전 정보·영상 없음', '사전 정보·영상 틀림']; T4 = {0: 0, 1: 1, 3: 2, 2: 3, 4: 4, 5: 5, -1: 6}
J4C = [COLG['두 자료'], COLG['영상'], COLG['사전 정보(영상 없음)'], COLG['사전 정보(영상 틀림)']]
def earclip(P2):
    idx = list(range(len(P2))); A = 0.5*sum(P2[i-1][0]*P2[i][1] - P2[i][0]*P2[i-1][1] for i in range(len(P2)))
    if A < 0: idx = idx[::-1]
    tris = []; guard = 0
    def cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    while len(idx) > 3 and guard < 10000:
        guard += 1; ok = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k-1], idx[k], idx[(k+1) % len(idx)]; a, b, c = P2[i0], P2[i1], P2[i2]
            if cross(a, b, c) <= 1e-12: continue
            if any(cross(a, b, P2[j]) >= 0 and cross(b, c, P2[j]) >= 0 and cross(c, a, P2[j]) >= 0 for j in idx if j not in (i0, i1, i2)): continue
            tris.append((i0, i1, i2)); idx.pop(k); ok = True; break
        if not ok: break
    if len(idx) == 3: tris.append(tuple(idx))
    return tris
def core_points(tiles, kind, box):
    out = []
    for t in tiles:
        x0, x1, y0, y1 = tile_core(t); f = WI/'points'/t/f'{kind}_xyz.npy'
        if not f.exists(): continue
        X = np.load(f, mmap_mode='r')
        for s in range(0, len(X), 20_000_000):
            q = np.asarray(X[s:s+20_000_000], np.float64); m = (q[:, 0] >= max(x0, box[0])) & (q[:, 0] < min(x1, box[1])) & (q[:, 1] >= max(y0, box[2])) & (q[:, 1] < min(y1, box[3])); out.append(q[m])
    return np.concatenate(out) if out else np.empty((0, 3))
def b64(a): return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()
def quant(X, lo, ext): return np.clip(np.round((X - lo)/ext*65535), 0, 65535).astype('<u2')
def mm(a): return np.clip(np.round(np.asarray(a)*1000), -32767, 32767).astype('<i2')
def lod2_polys(bid, tiles, lo):
    best = None
    for t in tiles:
        mf = WI/'prior_tiles'/t/'lod2_mesh.npz'
        if not mf.exists(): continue
        z = np.load(mf); bn = list(z['building_names'])
        if bid not in bn: continue
        sel = np.flatnonzero((z['tri_building'] == bn.index(bid)) & (np.arange(len(z['F'])) < int(z['n_poly_tris'])))
        if best is None or len(sel) > len(best[1]): best = (t, sel, z['V'], z['F'], z['tri_surface'])
    if best is None: return []
    t_, sel, Vm, Fm, ts = best; Fs = Fm[sel]; used = np.unique(Fs); remap = -np.ones(len(Vm), int); remap[used] = np.arange(len(used)); ed = {}
    for tri, sf in zip(Fs, ts[sel]):
        for a_, b_ in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]: k_ = (sf, min(a_, b_), max(a_, b_)); ed[k_] = ed.get(k_, 0) + 1
    return dict(tile=t_, v=np.round(Vm[used] - lo, 3).tolist(), f=remap[Fs].tolist(), e=[[int(remap[a_]), int(remap[b_])] for (sf, a_, b_), n_ in ed.items() if n_ == 1])
class Cams:
    def __init__(s):
        h = np.fromfile(VIS/'cams.bin', '<i4', 3); s.C = np.fromfile(VIS/'cams.bin', '<f8', offset=12).reshape(h[0], 16); s.W, s.H = int(h[1]), int(h[2]); s.maps = [l.split('\t')[0] for l in (VIS/'maps.txt').read_text().splitlines()]; s.cache = {}
    def depth(s, im):
        if im not in s.cache: s.cache[im] = read_depth(s.maps[im])
        return s.cache[im]
    def rays(s, ref, n, u):
        out = []
        for im in range(len(s.C)):
            Rm = s.C[im, :9].reshape(3, 3); tt = s.C[im, 9:12]; Y = Rm@ref + tt
            if Y[2] <= .05: continue
            cu = int(round(s.C[im, 12]*Y[0]/Y[2] + s.C[im, 14])); cv = int(round(s.C[im, 13]*Y[1]/Y[2] + s.C[im, 15]))
            if not (0 <= cu < s.W and 0 <= cv < s.H): continue
            Dd = float(s.depth(im)[cv, cu]); Z = Y[2]; cl = 0 if not Dd > 0 else (1 if Dd > 1.01*Z else (2 if Dd < .99*Z else 3)); cc = -Rm.T@tt
            if Dd > 0: dr = ref - cc; dr /= np.linalg.norm(dr); e = cc + dr*Dd*np.linalg.norm(ref - cc)/Z - ref; out.append((e@u, e@n, cl))
            else: out.append((0., 0., 0))
        return out
    def unproject(s, st):
        X = np.full((len(st), 3), np.nan)
        for im in np.unique(st[:, 0]):
            m = st[:, 0] == im; row, col = np.divmod(st[m, 1], s.W); Dd = s.depth(im)[row, col].astype(np.float64); Rm = s.C[im, :9].reshape(3, 3); tt = s.C[im, 9:12]
            ray = np.c_[(col - s.C[im, 14])/s.C[im, 12], (row - s.C[im, 15])/s.C[im, 13], np.ones(len(row))]; Xi = (ray*Dd[:, None] - tt)@Rm; Xi[~(Dd > 0)] = np.nan; X[m] = Xi
        return X
def classify(X_, rows, area, rng):
    """판 4 갈래, 색 갈래, 틀림 목록과 기둥 점 담을 패치(씨앗 = 건물·사전 정보마다 고정)."""
    Z = X_['Z']; F4 = X_['F4']; Jg = X_['J']
    # 패치 갈래
    t = Z['answer'][rows, 0]; tm = np.array([T4[int(x)] for x in t], np.uint8); r1 = Jg['r1'][rows]; r2 = Jg['r2'][rows]; a3 = Jg['r3a'][rows]; b3 = Jg['r3b'][rows]
    j4 = F4['J4_판 4'][rows]; st = F4['stage_판 4'][rows]; df = F4['default_판 4'][rows]; okT = F4['ok_판 4'][rows]; hT = F4['hT_판 4'][rows]; tT = F4['tauT_판 4'][rows]
    go3a = r1 == 1; go3b = (r1 == 2) & (r2 == 1); m_r2 = np.where(r1 == 2, r2, 255).astype(np.uint8); m_r3 = np.where(go3a, a3, np.where(go3b, b3, 255)).astype(np.uint8)
    m_j4 = np.where(j4 >= 0, j4, 4).astype(np.uint8); inm = tm < 4; okj = np.where(~inm, 4, np.where(j4 == tm, 0, st)).astype(np.uint8); okt = np.where(~inm, 2, np.where(okT, 0, 1)).astype(np.uint8)
    A = lambda cl, K_: [float(area[cl == k].sum()) for k in range(K_)]
    truthN = J4N + ['둘 다 틀림(채점 밖)', '정답 없음(채점 밖)', '사전 정보 높이 없음(채점 밖)']; truthC = J4C + [COLG['둘 다 틀림'], COLG['정답 없음'], COLG['사전 정보 높이 없음']]
    modes = dict(truth=dict(title='패치: 정답(가3)', names=truthN, colors=truthC, area=A(tm, 7)),
                 r1=dict(title='패치: ① 결과', names=['같다', '다르다', '값 없음'], colors=['#1D9E75', '#D85A30', '#B4B2A9'], area=A(r1, 3)),
                 r2=dict(title='패치: ② 결과(②를 거친 패치만)', names=['사전 정보', '③으로'], colors=['#EF9F27', '#7F77DD'], area=A(m_r2, 2), note='① 값 없음 패치만 칠함'),
                 r3=dict(title='패치: ③ 결과(③을 거친 패치만)', names=['사전 정보', '영상'], colors=['#D85A30', '#378ADD'], area=A(m_r3, 2), note='① 다르다, 또는 ① 값 없음·② ③으로 패치만 칠함'),
                 j4=dict(title='패치: 최종 판정(판정 넷)', names=J4N + ['그 밖'], colors=J4C + ['#444441'], area=A(m_j4, 5)),
                 okj=dict(title='패치: 판단 맞음·틀림', names=['맞음', '틀림: ①이 정함', '틀림: ②가 정함', '틀림: ③이 정함', '채점 밖'], colors=['#D3D1C7', '#E24B4A', '#EF9F27', '#7F77DD', '#F1EFE8'], area=A(okj, 5), note='판정을 정한 단계: 뺀 단계 없음(판 4). 채점 밖 = 정답이 둘 다 틀림·정답 없음·높이 없음'),
                 okt=dict(title='패치: 목표 맞음·틀림', names=['맞음', '틀림', '채점 밖'], colors=['#D3D1C7', '#E24B4A', '#F1EFE8'], area=A(okt, 3), note='목표 높이 h_T 의 ±τ_T 안에 참값 점 4개 이상' + (' · v2: h_M = 저장 mvs_mean_m(덧붙임 2)' if V2 else '')))
    # 틀림 목록과 기둥 점 담을 패치
    worst = []; emb = set()
    for k in range(4):
        for jv in range(5):
            if jv == k: continue
            cell = np.flatnonzero((tm == k) & (m_j4 == jv))
            if not len(cell): continue
            o = cell[np.lexsort((rng.random(len(cell)), -area[cell]))][:5]; worst.append(dict(cell=f'정답 {J4N[k]} → 판정 {(J4N + ["그 밖"])[jv]}', area=float(area[cell].sum()), items=[int(x) for x in o])); emb.update(int(x) for x in o)
    worst.sort(key=lambda w: -w['area'])
    for k in range(7):
        for jv in range(5):
            cell = np.flatnonzero((tm == k) & (m_j4 == jv))
            if len(cell): emb.update(int(x) for x in rng.choice(cell, min(len(cell), 20 if k < 4 else 10), replace=False))
    return dict(tm=tm, r1=r1, go3a=go3a, go3b=go3b, m_r2=m_r2, m_r3=m_r3, m_j4=m_j4, okj=okj, okt=okt, st=st, df=df, hT=hT, tT=tT, modes=modes, worst=worst, emb=np.array(sorted(emb)))
def main():
    c = cfg(); build(); build_vis(); rng = np.random.default_rng(A1['viewer']['seed']); cap = A1['viewer']['point_cap_per_layer'][0]; B = buildings(); VD.mkdir(parents=True, exist_ok=True); CM = Cams()
    lod = {b['id']: b for b in json.loads((PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/lod2_buildings.json').read_text())}
    three = (R/'src/apps/gs3d_4way_viewer/build/three.module.min.js').read_text(); tpl = (HERE/'viewer/building_eval.html').read_text(); index = []
    G = {p: loadz(inp('patches', prior=p), ['centre', 'normal', 'tangent1', 'prior_height_m', 'tile', 'tiles', 'kind']) for p in PRIORS}
    DD = {}
    for p in PRIORS:
        Z = loadz(O/'work'/STAGE/f'truth_{p}.npz', ['patch_index', 'answer', 'h_I', 'img_col', 'n_total', 'tau_P', 'tau_I', 'two_layer']); F4 = loadz(O/'work'/STAGE/(f'judge4_v2_{p}.npz' if V2 else f'judge4_{p}.npz')); Jg = loadz(O/'work'/STAGE/f'judgments_{p}.npz')
        S1 = loadz(O/'work'/STAGE/f'step1_{p}.npz', ['patch_index', 'd_mean', 'L_m', 'starts', 'start_owner']); S2 = loadz(O/'work'/STAGE/f'step2_{p}.npz', ['patch_index', 'counts', 'pass_pix']); S3 = loadz(O/'work'/STAGE/f'step3_{p}.npz')
        for X_ in [F4, Jg, S1, S2, S3]: assert np.array_equal(X_['patch_index'], Z['patch_index'])
        fwd = pd.read_csv(O/f'forward_{p}_ga3.csv.gz', usecols=['patch_index', 'patch_id', 'building', 'place', 'area_m2']).set_index('patch_index').loc[Z['patch_index']].reset_index()
        DD[p] = dict(Z=Z, F4=F4, J=Jg, S1=S1, S2=S2, S3=S3, fwd=fwd)
    BI = {b: k for k, b in enumerate(sorted(B))}; TILES = {}; global TILECOL; TILECOL = {}; reqs = {}
    for bid, br in sorted(B.items()):
        L_ = lod[bid]; allv = np.array([v for s in L_['surfaces'].values() for poly in s for v in poly['ext']], float) - SHIFT
        box = (allv[:, 0].min() - 10, allv[:, 0].max() + 10, allv[:, 1].min() - 10, allv[:, 1].max() + 10)
        TILES[bid] = sorted({t for t in G['LoD2']['tiles'] if (lambda r: r[0] < box[1] and r[1] > box[0] and r[2] < box[3] and r[3] > box[2])(tile_core(t))})
        for prior in PRIORS:
            X_ = DD[prior]; rows = np.flatnonzero(X_['fwd'].building.values == bid)
            if not len(rows): continue
            g = G[prior]; i = X_['Z']['patch_index'][rows]; nrm = np.nan_to_num(g['normal'][i]); S = g['centre'][i] + np.nan_to_num(g['prior_height_m'][i])[:, None]*nrm; kind = g['kind'][i]
            emb = classify(X_, rows, X_['fwd'].area_m2.values[rows], np.random.default_rng([A1['viewer']['seed'], BI[bid], PRIORS.index(prior)]))['emb']
            if not len(emb): continue
            U = g['tangent1'][i][emb] - np.einsum('ij,ij->i', g['tangent1'][i][emb], nrm[emb])[:, None]*nrm[emb]; U /= np.linalg.norm(U, axis=1)[:, None]
            reqs[(bid, prior)] = dict(S=S[emb], n=nrm[emb], U=U, V=np.cross(nrm[emb], U), H=np.where(kind[emb] == 2, 5., 10.), tiles=TILES[bid])
    for tl in sorted({t for r in reqs.values() for t in r['tiles']}):
        ks = [k for k, r in reqs.items() if tl in r['tiles']]
        core = np.concatenate([np.c_[reqs[k]['S'], reqs[k]['n'], np.full(len(reqs[k]['S']), 1.5), reqs[k]['H']] for k in ks]); grp = np.concatenate([np.full(len(reqs[k]['S']), j) for j, k in enumerate(ks)]); loc = np.concatenate([np.arange(len(reqs[k]['S'])) for k in ks])
        for key, path in [('g', inp('truth_points', tile=tl)), ('m', inp('image_points', tile=tl))]:
            if not path.exists(): continue
            _, pr = run_ids(path, core, f'vw_{tl}_{key}'); TILECOL[(tl, key)] = {}
            if not len(pr): continue
            Xa = np.load(path, mmap_mode='r'); o = np.argsort(pr[:, 1], kind='stable'); P_ = np.asarray(Xa[pr[o, 1]], np.float64); cr = pr[o, 0]
            for j, k in enumerate(ks):
                m_ = grp[cr] == j; e = loc[cr[m_]]; r = reqs[k]; dlt = P_[m_] - r['S'][e]
                TILECOL[(tl, key)][k] = (np.einsum('ij,ij->i', dlt, r['U'][e]), np.einsum('ij,ij->i', dlt, r['n'][e]), np.einsum('ij,ij->i', dlt, r['V'][e]), e)
            print('TILE', tl, key, len(pr), flush=True)
        progress(f'뷰어 기둥 점: 구역 {tl}')
    for bid, br in sorted(B.items()):
        L_ = lod[bid]; allv = np.array([v for s in L_['surfaces'].values() for poly in s for v in poly['ext']], float) - SHIFT
        box = (allv[:, 0].min() - 10, allv[:, 0].max() + 10, allv[:, 1].min() - 10, allv[:, 1].max() + 10)
        tiles = TILES[bid]
        pts = {k: core_points(tiles, k2, box) for k, k2 in [('mvs', 'mvs_a'), ('gt', 'gt'), ('als', 'als')]}; site = SITES[br['experiment_sites'][0]]
        for prior in PRIORS:
            T = Timer(); X_ = DD[prior]; rows = np.flatnonzero(X_['fwd'].building.values == bid)
            if not len(rows): continue
            g = G[prior]; Z = X_['Z']; F4 = X_['F4']; Jg = X_['J']; S1 = X_['S1']; S2 = X_['S2']; S3 = X_['S3']; f = X_['fwd'].iloc[rows]; i = Z['patch_index'][rows]
            nrm = np.nan_to_num(g['normal'][i]); S = g['centre'][i] + np.nan_to_num(g['prior_height_m'][i])[:, None]*nrm; kind = g['kind'][i]
            layers = {'mvs': pts['mvs'], 'gt': pts['gt']}
            if prior == 'ALS': layers['als'] = pts['als'] + np.array(br['als_shift_m'])
            allp = np.concatenate([S] + [v for v in layers.values() if len(v)]); lo = allp.min(0) - .5; ext = allp.max(0) + .5 - lo; info = {}; data = {}
            for k, Xp in layers.items():
                n0 = len(Xp)
                if n0 > cap: Xp = Xp[np.sort(rng.choice(n0, cap, replace=False))]
                data[k] = b64(quant(Xp, lo, ext)); info[k] = dict(total=n0, shown=len(Xp), ratio=len(Xp)/max(n0, 1))
            polys = lod2_polys(bid, tiles, lo) if prior == 'LoD2' else []
            area = f.area_m2.values; K_ = classify(X_, rows, area, np.random.default_rng([A1['viewer']['seed'], BI[bid], PRIORS.index(prior)]))
            tm, r1, go3a, go3b, m_r2, m_r3, m_j4, okj, okt, st, df, hT, tT, modes, worst = [K_[k] for k in ['tm', 'r1', 'go3a', 'go3b', 'm_r2', 'm_r3', 'm_j4', 'okj', 'okt', 'st', 'df', 'hT', 'tT', 'modes', 'worst']]
            emb = K_['emb']; cols = {}
            if len(emb):
                H = np.where(kind[emb] == 2, 5., 10.); core = np.c_[S[emb], nrm[emb], np.full(len(emb), 1.5), H]; U = g['tangent1'][i][emb] - np.einsum('ij,ij->i', g['tangent1'][i][emb], nrm[emb])[:, None]*nrm[emb]; U /= np.linalg.norm(U, axis=1)[:, None]
                V = np.cross(nrm[emb], U); got = {e: {'g': [], 'm': []} for e in range(len(emb))}
                for tl in tiles:
                    for key in ['g', 'm']:
                        if (tl, key) not in TILECOL: continue
                        a_, t_, b_, own = TILECOL[(tl, key)].get((bid, prior), (None,)*4)
                        if a_ is None: continue
                        m_ = (np.abs(b_) <= .125) & (np.abs(a_) <= 1.5)
                        for e in np.unique(own[m_]): s_ = m_ & (own == e); got[int(e)][key].append(np.c_[a_[s_], t_[s_]])
                # ③ 시작 점
                pos = {int(x): r for r, x in enumerate(rows)}; own1 = S1['start_owner']; pidx = Z['patch_index']; rowof = -np.ones(int(pidx.max()) + 1, np.int64); rowof[pidx] = np.arange(len(pidx))
                starts = []; sown = []
                for e, r in enumerate(emb):
                    gi = rows[r]
                    if go3a[r]: sel = np.flatnonzero(own1 == pidx[gi]); starts.append(S1['starts'][sel]); sown.append(np.full(len(sel), e))
                    elif go3b[r]: sel = np.flatnonzero(S2['pass_pix'][:, 0] == gi); starts.append(S2['pass_pix'][sel][:, 1:]); sown.append(np.full(len(sel), e))
                cons = {}
                if starts and sum(len(x) for x in starts):
                    st_ = np.concatenate(starts).astype('<i4'); so = np.concatenate(sown); sb = O/'tmp'/f'vwf_{prior}.bin'; ob = O/'tmp'/f'vwf_{prior}.out'; st_.tofile(sb)
                    subprocess.run([str(VBIN), 'fuse', str(VIS/'cams.bin'), str(VIS/'maps.txt'), str(VIS/'overlap.bin'), str(sb), str(len(st_)), str(ob)], check=True, env=dict(os.environ, OMP_NUM_THREADS='30'), stderr=subprocess.DEVNULL)
                    Rf = np.fromfile(ob, '<i4').reshape(-1, 3); sb.unlink(); ob.unlink(); Xs = CM.unproject(st_)
                    for e in np.unique(so):
                        m_ = so == e; dlt = Xs[m_] - S[emb][e]; cons[int(e)] = np.c_[dlt@U[e], dlt@nrm[emb][e], Rf[m_, 0]]
                for e, r in enumerate(emb):
                    gpt = np.concatenate(got[e]['g']) if got[e]['g'] else np.empty((0, 2)); mpt = np.concatenate(got[e]['m']) if got[e]['m'] else np.empty((0, 2)); d_ = dict(g=b64(mm(gpt)), m=b64(mm(mpt)))
                    if r1[r] == 2: d_['r'] = b64(mm(np.array(CM.rays(S[emb][e], nrm[emb][e], U[e])).reshape(-1, 3)*np.array([1, 1, .001])))
                    if e in cons: s3 = cons[e]; s3 = s3[np.isfinite(s3[:, 0])]; d_['s'] = b64(mm(s3*np.array([1, 1, .001])))
                    cols[int(r)] = d_
            # 값
            cons3 = np.where(go3a, S3['from1_cons'][rows], np.where(go3b, S3['from2_cons'][rows], np.nan)); tot3 = np.where(go3a, S3['from1_total'][rows], np.where(go3b, S3['from2_total'][rows], np.nan))
            floats = dict(d=S1['d_mean'][rows, 2], L=S1['L_m'][rows], hI=Z['h_I'][rows, 0], hT=hT, tauP=Z['tau_P'][rows, 0], tauI=Z['tau_I'][rows, 0], tauT=tT, area=area, nI=Z['img_col'][rows], nG=Z['n_total'][rows], cons3=cons3, tot3=tot3, stage=st.astype(float) + 3*df)
            ptiles = sorted(set(f.patch_id.str.split(':').str[1])); t1 = g['tangent1'][i]
            P = dict(c=b64((S - lo).astype('<f4')), n=b64(np.round(nrm*127).astype('i1')), t1=b64(np.round(np.nan_to_num(t1)*127).astype('i1')), k=b64(kind.astype(np.uint8)), pl=b64(np.array([PL.get(x, 3) for x in f.place], np.uint8)),
                     two=b64(Z['two_layer'][rows].astype(np.uint8)), id=b64(f.patch_id.str.split(':').str[-1].astype(int).values.astype('<i4')), tl=b64(np.array([ptiles.index(x) for x in f.patch_id.str.split(':').str[1]], np.uint8)),
                     c2=b64(S2['counts'][rows][:, 0:4].astype('<f4')), **{f'm_{k}': b64(v) for k, v in dict(truth=tm, r1=r1.astype(np.uint8), r2=m_r2, r3=m_r3, j4=m_j4, okj=okj, okt=okt).items()}, **{f'f_{k}': b64(np.asarray(v, '<f4')) for k, v in floats.items()})
            bb = S if not polys else np.array(polys['v']) + lo; bl = np.r_[allv[:, :2].min(0), bb[:, 2].min()] - lo; bh = np.r_[allv[:, :2].max(0), bb[:, 2].max()] - lo
            meta = dict(view=dict(c=((bl + bh)/2).tolist(), bl=bl.tolist(), bh=bh.tolist(), span=float(max(bh[0] - bl[0], bh[1] - bl[1]) + 20), h=float(bh[2] - bl[2])), building=bid, site=site, prior=prior, prior_name=PN[prior], id_prefix=prior, patch_tiles=ptiles,
                        lo=lo.tolist(), ext=ext.tolist(), patches=len(rows), info=info, modes=modes, floats=list(floats), places=list(PL), worst=worst, H=dict(roof=10, wall=5), Hcyl=dict(roof=10, wall=5),
                        radius=dict(roof=.075, wall=.125 if prior == 'LoD2' else .075), stage_names={1: '①', 2: '②', 3: '③', 4: '①(기본)', 5: '②(기본)', 6: '③(기본)'}, embedded=len(cols))
            html = tpl.replace('/*THREE*/', three).replace('/*META*/', json.dumps(meta, ensure_ascii=False)).replace('/*POLYS*/', json.dumps(polys)).replace('/*PATCHES*/', json.dumps(P)).replace('/*POINTS*/', json.dumps(data)).replace('/*COLS*/', json.dumps(cols))
            name = f"{site.replace(' ', '')}_{bid.replace('DEBY_LOD2_', '')}_{prior}"; out = VD/f'{name}.html'; out.write_text(html); mb = out.stat().st_size/1e6
            dump(VD/f'{name}.json', dict(at=now(), file=out.name, mb=mb, seconds=T.s(), **{k: v for k, v in meta.items() if k not in ['modes', 'view', 'floats', 'places', 'stage_names']}, area_by_mode={k: dict(zip(v['names'], v['area'])) for k, v in modes.items()}, scientific_verdict=None))
            index.append(dict(file=out.name, building=bid, site=site, prior=prior, patches=len(rows), embedded=len(cols), mb=round(mb, 1), **{f'{k}_shown_pct': round(100*v['ratio'], 1) for k, v in info.items()}))
            print('VIEW', name, len(rows), len(cols), round(mb, 1), round(T.s()), flush=True); progress(f'뷰어 {name}: 패치 {len(rows):,}, 기둥 담음 {len(cols)}, {mb:.1f} MB, {T.s():.0f} s')
    dump(VD/'index.json', dict(at=now(), files=index, scientific_verdict=None)); progress(f"뷰어({'v2, 덧붙임 2' if V2 else '묶음 라'}): HTML {len(index)}개")
if __name__ == '__main__': main()
