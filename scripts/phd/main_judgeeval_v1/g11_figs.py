"""나 그림(정성). 그림마다 같은 이름 json(출처, 값). 사용: GT_STAGE=ga3 g11_figs.py [0 1 2 3 4]
0 fig7_0_range: 판단이 보는 범위(B173 주변, 정답 영상, |h_I| > 3 m 패치 하나): 사전 정보 면, ① 원통(길이 후보 셋), 정답 기둥, ② 시선.
1 fig7_1_tradeoff(후보마다 변화 놓침 대 헛 변화), fig7_1_maps(지역마다 ① 결과 지도).
2 fig7_2_examples: ① 값 없음 패치, 정답 종류별 본보기 넷, 영상마다 중심 시선 끝의 분류(못 봄·지나감·막힘·일치).
3 fig7_3_examples: ③으로 간 패치, 정답 영상 / 영상 틀림마다 둘, 영상 점을 일관된 점(진한 초록)·아닌 점(연한 초록)으로.
4 fig7_4_bars, fig7_4_effect, fig7_4_maps(판 1 과 판 4, 바뀐 패치), fig7_4_curve."""
from common import *
import pandas as pd
import judge_lib as JL
from scipy.spatial import cKDTree
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle, Patch
from matplotlib.lines import Line2D
for f in ['/fonts/NotoSansCJK-Regular.ttc', '/fonts/NotoSansCJK-Bold.ttc']: fm.fontManager.addfont(f)
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'font.size': 7, 'axes.linewidth': .5})
FD = D/'figures'; TD = D/'tables/나'; COLR = {'같다': '#1D9E75', '다르다': '#D85A30', '값 없음': '#B4B2A9'}; CJ = {0: '#1D9E75', 1: '#378ADD', 2: '#EF9F27'}
CLS = {0: ('못 봄', '#B4B2A9'), 1: ('지나감', '#A32D2D'), 2: ('막힘', '#EF9F27'), 3: ('일치', '#1D9E75')}
def save(fig, name, meta):
    FD.mkdir(parents=True, exist_ok=True); fig.savefig(FD/f'{name}.png', dpi=300, bbox_inches='tight', pad_inches=.08); plt.close(fig); dump(FD/f'{name}.json', dict(at=now(), figure=name, **meta, scientific_verdict=None)); print('FIG', name, flush=True)
def load(prior):
    Z = loadz(O/'work'/STAGE/f'truth_{prior}.npz'); P = loadz(inp('patches', prior=prior), ['kind', 'area', 'centre', 'normal', 'tangent1', 'prior_height_m', 'building', 'tile', 'tiles', 'place'])
    J = loadz(O/'work'/STAGE/f'judgments_{prior}.npz'); i = Z['patch_index']; assert np.array_equal(J['patch_index'], i)
    B = buildings(); site = {b: SITES[r['experiment_sites'][0]] for b, r in B.items()}
    return dict(i=i, t=Z['answer'][:, 0], hI=Z['h_I'][:, 0], kind=P['kind'][i], area=P['area'][i], c=P['centre'][i], n=P['normal'][i], t1=P['tangent1'][i], ph=P['prior_height_m'][i], b=P['building'][i],
                site=np.array([site[x] for x in P['building'][i]]), tile=P['tiles'][P['tile'][i]], place=P['place'][i], J=J, prior=prior)
def crop(t, kind, box):
    f = inp('image_points', tile=t) if kind == 'mvs' else inp('truth_points', tile=t); X = np.load(f, mmap_mode='r'); out = []
    for s in range(0, len(X), 20_000_000):
        q = np.asarray(X[s:s+20_000_000], np.float64); m = (q[:, 0] >= box[0]) & (q[:, 0] <= box[1]) & (q[:, 1] >= box[2]) & (q[:, 1] <= box[3]) & (q[:, 2] >= box[4]) & (q[:, 2] <= box[5]); out.append(q[m])
    return np.concatenate(out)
def section_pts(L, k, W=3., H=10.):
    n = np.nan_to_num(L['n'][k]); u = L['t1'][k] - (L['t1'][k]@n)*n; u /= np.linalg.norm(u); v = np.cross(n, u); ref = L['c'][k] + np.nan_to_num(L['ph'][k])*n
    box = (ref[0] - 12, ref[0] + 12, ref[1] - 12, ref[1] + 12, ref[2] - 12, ref[2] + 12); out = {}
    for kd in ['gt', 'mvs']:
        X = crop(L['tile'][k], kd, box); d = X - ref; t = d@n; a = d@u; b = d@v; m = (np.abs(b) <= .125) & (np.abs(a) <= W) & (np.abs(t) <= H); out[kd] = (a[m], t[m], np.flatnonzero(m), X)
    return ref, n, u, v, out
def cams():
    h = np.fromfile(VIS/'cams.bin', '<i4', 3); C = np.fromfile(VIS/'cams.bin', '<f8', offset=12).reshape(h[0], 16); return C, int(h[1]), int(h[2])
def read_depth(p):
    raw = Path(p).read_bytes(); end = 0
    for _ in range(3): end = raw.find(b'&', end, 100) + 1
    w, h, c = map(int, raw[:end].split(b'&')[:3]); return np.frombuffer(raw, '<f4', offset=end, count=w*h).reshape((w, h), order='F').T
def fig0():
    L = load('LoD2'); m = np.flatnonzero((L['site'] == 'B173 주변') & (L['t'] == 1) & (np.abs(L['hI']) > 3) & (L['kind'] == 1))
    if not len(m): print('fig0 확인 불가: 본보기 없음'); return
    k = m[np.argmax(L['area'][m])]; ref, n, u, v, P = section_pts(L, k, 3., 10.); C, W, H = cams(); S1 = loadz(O/'work'/STAGE/'step1_LoD2.npz', ['Hs'])
    fig, ax = plt.subplots(figsize=(6.2, 6.6)); a, t, _, _ = P['mvs']; ax.scatter(a, t, s=.8, color='#97C459', lw=0, label='영상 깊이 점'); a, t, _, _ = P['gt']; ax.scatter(a, t, s=1.2, color='k', lw=0, label='드론 LiDAR')
    ax.axhline(0, color='#534AB7', lw=1.2, label='사전 정보 면'); ax.add_patch(Rectangle((-.125, -10), .25, 20, fill=False, ec='#5F5E5A', ls='--', lw=.7, label='정답 기둥 ±10 m'))
    for j, (Hc, col) in enumerate(zip(S1['Hs'][k], ['#F0997B', '#D85A30', '#993C1D'])): ax.add_patch(Rectangle((-.075 - .05*j, -Hc), .15 + .1*j, 2*Hc, fill=False, ec=col, lw=1, label=f'① 원통 반길이 {Hc:g} m (반지름 0.075 m, 그림은 겹치지 않게 넓힘)'))
    rays = []
    for im in range(len(C)):
        R = C[im, :9].reshape(3, 3); tt = C[im, 9:12]; cc = -R.T@tt; Y = R@ref + tt
        if Y[2] <= 0: continue
        uu = C[im, 12]*Y[0]/Y[2] + C[im, 14]; vv = C[im, 13]*Y[1]/Y[2] + C[im, 15]
        if 0 <= uu < W and 0 <= vv < H: d = cc - ref; rays.append((d@u, d@n, im))
    rng = np.random.default_rng(1); pick = [rays[i] for i in rng.choice(len(rays), min(6, len(rays)), replace=False)]
    for du, dn, im in pick:
        s = 12/np.hypot(du, dn); ax.plot([0, du*s], [0, dn*s], color='#378ADD', lw=.6, alpha=.8)
    ax.plot([], [], color='#378ADD', lw=.6, label=f'② 시선(패치를 본 영상 {len(rays)}장 가운데 여섯, 단면에 투영)')
    ax.set_xlim(-3, 3); ax.set_ylim(-11, 4); ax.set_xlabel('패치 칸 옆 방향 (m)'); ax.set_ylabel('법선 거리 (m, 사전 정보 = 0)'); ax.legend(fontsize=5.5, loc='lower left')
    ax.set_title(f"판단이 보는 범위 · {L['b'][k].replace('DEBY_LOD2_', '')} · 정답 영상 · h_I {L['hI'][k]:+.2f} m", fontsize=8)
    save(fig, 'fig7_0_range', dict(patch_index=int(L['i'][k]), building=L['b'][k], h_I=float(L['hI'][k]), lengths=S1['Hs'][k].tolist(), rays_seen=len(rays), rays_drawn=[int(x[2]) for x in pick]))
def fig1():
    df = pd.read_csv(TD/'t71_step1.csv'); df = df[(df.version == '전체') & (df.unit == '넓이')]; units = [(p, s) for p in ['LoD2', '항공 LiDAR'] for s in (['지붕', '벽'] if p == 'LoD2' else ['지붕'])]
    fig, axs = plt.subplots(1, len(units), figsize=(4.2*len(units), 3.8)); meta = {}
    for ax, (p, s) in zip(axs, units):
        g = df[(df.prior == p) & (df.surface == s)]; main = g.candidate.str.startswith('길이 긺(본) · 평균 · 크기 경계 뺌 · 한계 PM')
        ax.scatter(g['헛 변화 m²'], g['변화 놓침 m²'], s=10, color='#888780'); ax.scatter(g['헛 변화 m²'][main], g['변화 놓침 m²'][main], s=40, color='#D85A30', label='본 판')
        for _, r in g.iterrows(): ax.annotate(r.candidate.replace('길이 ', '').replace(' · 크기 경계 ', '·경계').replace(' · 한계 ', '·'), (r['헛 변화 m²'], r['변화 놓침 m²']), fontsize=3.2, alpha=.7)
        ax.set_xlabel('헛 변화(정답 두 자료인데 다르다) m²'); ax.set_ylabel('변화 놓침(정답 영상인데 같다) m²'); ax.set_title(f'{p} · {s}'); ax.legend(fontsize=6)
        meta[f'{p}_{s}'] = g[['candidate', '헛 변화 m²', '변화 놓침 m²']].to_dict('records')
    fig.suptitle('① M3C2 후보마다 변화 놓침 대 헛 변화(넓이)', fontsize=9); save(fig, 'fig7_1_tradeoff', dict(source=str(TD/'t71_step1.csv'), points=meta))
    fig, axs = plt.subplots(3, 2, figsize=(7.6, 10)); meta = {}
    for pi, prior in enumerate(PRIORS):
        L = load(prior)
        for si, site in enumerate(['B0', 'B173 주변', 'R1']):
            ax = axs[si, pi]; m = L['site'] == site; o = np.argsort(L['kind'][m])[::-1]; c = L['c'][m][o]; r = L['J']['r1'][m][o]
            ax.scatter(c[:, 0], c[:, 1], s=.3, c=[list(COLR.values())[x] for x in r], lw=0, rasterized=True); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([]); ax.set_title(f'{site} · {PN[prior]}')
            meta[f'{site}_{prior}'] = {k: float(L['area'][m][L['J']['r1'][m] == j].sum()) for j, k in enumerate(COLR)}
    fig.legend(handles=[Patch(color=v, label=k) for k, v in COLR.items()], loc='lower center', ncol=3, frameon=False); fig.suptitle('① 결과 지도(본 판, 위에서 본 패치 중심)', fontsize=9); save(fig, 'fig7_1_maps', dict(area_m2=meta))
def fig2():
    C, W, H = cams(); maps = [l.split('\t')[0] for l in (VIS/'maps.txt').read_text().splitlines()]; L = load('LoD2'); none = L['J']['r1'] == 2; exs = []
    for tv in [1, 3, 0, 4]:
        m = np.flatnonzero(none & (L['t'] == tv))
        if len(m): exs.append((tv, m[np.random.default_rng(tv).integers(len(m))]))
    cache = {}; fig, axs = plt.subplots(1, len(exs), figsize=(3.4*len(exs), 3.8)); meta = []
    for ax, (tv, k) in zip(np.atleast_1d(axs), exs):
        ref, n, u, v, P = section_pts(L, k, 3., 6.); a, t, _, _ = P['mvs']; ax.scatter(a, t, s=.6, color='#97C459', lw=0); a, t, _, _ = P['gt']; ax.scatter(a, t, s=1, color='k', lw=0); ax.axhline(0, color='#534AB7', lw=1); cnt = {x: 0 for x in range(4)}
        for im in range(len(C)):
            R = C[im, :9].reshape(3, 3); tt = C[im, 9:12]; Y = R@ref + tt
            if Y[2] <= .05: continue
            uu = C[im, 12]*Y[0]/Y[2] + C[im, 14]; vv = C[im, 13]*Y[1]/Y[2] + C[im, 15]; cu, cv = int(round(uu)), int(round(vv))
            if not (0 <= cu < W and 0 <= cv < H): continue
            if im not in cache: cache[im] = read_depth(maps[im])
            Dd = float(cache[im][cv, cu]); Z = Y[2]; cl = 0 if not Dd > 0 else (1 if Dd > 1.01*Z else (2 if Dd < .99*Z else 3)); cnt[cl] += 1
            if Dd > 0:
                cc = -R.T@tt; dr = ref - cc; dr /= np.linalg.norm(dr); end = cc + dr*Dd*np.linalg.norm(ref - cc)/Z; e = end - ref; ax.scatter([e@u], [e@n], s=6, color=CLS[cl][1], lw=0, zorder=5)
        ax.set_xlim(-3, 3); ax.set_ylim(-6, 6); ax.set_title(f"정답 {FWD[tv]}\n{L['b'][k].replace('DEBY_LOD2_', '')} · 영상 {sum(cnt.values())}장", fontsize=7)
        ax.text(0, -.14, ' · '.join(f'{CLS[x][0]} {cnt[x]}' for x in range(4)), transform=ax.transAxes, fontsize=6, va='top'); meta.append(dict(truth=FWD[tv], patch_index=int(L['i'][k]), counts={CLS[x][0]: cnt[x] for x in range(4)}))
    fig.legend(handles=[Line2D([], [], marker='o', ls='', color=v[1], label=f'시선 끝: {v[0]}') for v in CLS.values()], loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(.5, -.08))
    fig.suptitle('② 가시성: 패치 중심을 영상마다 투영, 깊이 지도 값으로 시선 끝을 그림(단면에 투영, δ 1 %)', fontsize=8); save(fig, 'fig7_2_examples', dict(examples=meta, note='시선 끝 = 카메라에서 패치 중심 방향으로 깊이 지도 값만큼 간 점(단면 밖 거리는 무시하고 투영)'))
def fig3():
    build_vis(); L = load('LoD2'); S1 = loadz(O/'work'/STAGE/'step1_LoD2.npz', ['starts', 'start_owner', 'patch_index']); pos = -np.ones(int(S1['patch_index'].max()) + 1, np.int64); pos[S1['patch_index']] = np.arange(len(S1['patch_index']))
    own = pos[S1['start_owner']]; go = L['J']['r1'] == 1; exs = []
    for tv in [1, 1, 2, 2]:
        m = np.flatnonzero(go & (L['t'] == tv) & (L['kind'] == 1)); exs.append((tv, m[np.random.default_rng(len(exs)).integers(len(m))]) if len(m) else None)
    fig, axs = plt.subplots(1, 4, figsize=(13, 3.8)); meta = []
    for ax, e in zip(axs, exs):
        if e is None: ax.axis('off'); continue
        tv, k = e; st = S1['starts'][own == k].astype('<i4'); sb = O/'tmp/f3.bin'; ob = O/'tmp/f3.out'; st.tofile(sb)
        subprocess.run([str(VBIN), 'fuse', str(VIS/'cams.bin'), str(VIS/'maps.txt'), str(VIS/'overlap.bin'), str(sb), str(len(st)), str(ob)], check=True, env=dict(os.environ, OMP_NUM_THREADS='30'), stderr=subprocess.DEVNULL)
        R = np.fromfile(ob, '<i4').reshape(-1, 3); ref, n, u, v, P = section_pts(L, k, 3., 10.); C, W, H = cams()
        Xs = []
        for (im, px) in st:
            row, col = divmod(int(px), W); Rm = C[im, :9].reshape(3, 3); tt = C[im, 9:12]
            Dd = read_depth((VIS/'maps.txt').read_text().splitlines()[im].split('\t')[0])[row, col] if len(st) < 400 else np.nan
            Y = np.array([(col - C[im, 14])/C[im, 12]*Dd, (row - C[im, 15])/C[im, 13]*Dd, Dd]); Xs.append(Rm.T@(Y - tt))
        Xs = np.array(Xs); d = Xs - ref; ok = R[:, 0] == 1
        a, t, _, _ = P['gt']; ax.scatter(a, t, s=1, color='k', lw=0); ax.axhline(0, color='#534AB7', lw=1)
        ax.scatter((d@u)[~ok], (d@n)[~ok], s=5, color='#C0DD97', lw=0, label='일관되지 않은 점'); ax.scatter((d@u)[ok], (d@n)[ok], s=5, color='#27500A', lw=0, label='일관된 점')
        ax.set_xlim(-.6, .6); ax.set_title(f"정답 {FWD[tv]} · 일관 {int(ok.sum())}/{len(ok)}", fontsize=7); ax.legend(fontsize=5); meta.append(dict(truth=FWD[tv], patch_index=int(L['i'][k]), consistent=int(ok.sum()), points=len(ok)))
    fig.suptitle('③ 다시점 검증: ①에서 다르다로 온 패치의 원통 안 영상 점(COLMAP 규칙 일관성)', fontsize=8); save(fig, 'fig7_3_examples', dict(examples=meta))
def fig4():
    df = pd.read_csv(TD/'t74_plans.csv'); df = df[df.version == '전체']; plans = ['판 1', '판 2', '판 3', '판 4', '판 4(가장 나은 후보)', '상한: ①만 정답', '상한: ②만 정답', '상한: ③만 정답', 'JUDGECHECK-v2 본 방법', '11/22 구조', '늘 사전 정보', '늘 영상']
    units = [(p, s) for p in ['LoD2', '항공 LiDAR'] for s in (['지붕', '벽'] if p == 'LoD2' else ['지붕'])]
    fig, axs = plt.subplots(len(units), 1, figsize=(9, 2.6*len(units)), sharex=True)
    for ax, (p, s) in zip(axs, units):
        g = df[(df.prior == p) & (df.surface == s)].set_index('plan').reindex(plans); x = np.arange(len(plans))
        ax.bar(x - .2, g.judgment_acc_area, .4, color='#378ADD', label='판정 정확도'); ax.bar(x + .2, g.target_acc_area, .4, color='#1D9E75', label='목표 정확도'); ax.set_ylim(0, 100); ax.set_ylabel(f'{p} {s} %'); ax.legend(fontsize=6, loc='lower right')
    axs[-1].set_xticks(np.arange(len(plans))); axs[-1].set_xticklabels(plans, rotation=35, ha='right', fontsize=6); fig.suptitle('판 1~4, 바꿔 끼운 상한, 참고 열의 정확도(넓이, 전체)', fontsize=9)
    save(fig, 'fig7_4_bars', dict(source=str(TD/'t74_plans.csv'), plans=plans))
    ef = pd.read_csv(TD/'t74_effect.csv'); ef = ef[(ef.version == '전체') & (ef.unit == '넓이')]; fig, axs = plt.subplots(1, 4, figsize=(13, 3.6)); meta = {}
    for ax, ch in zip(axs, ['판 1 → 판 2', '판 1 → 판 3', '판 3 → 판 4', '판 2 → 판 4']):
        g = ef[(ef.change == ch) & (ef.surface.isin(['모두'])) | (ef.change == ch) & (ef.prior == '항공 LiDAR')]; lab = [f"{r.prior[:2]} {r.truth[:7]}" for r in g.itertuples()]; x = np.arange(len(g))
        ax.bar(x, g['맞게_바뀜'], color='#1D9E75', label='맞게 바뀜'); ax.bar(x, -g['틀리게_바뀜'], color='#A32D2D', label='틀리게 바뀜'); ax.bar(x, g['틀림_틀림'], bottom=g['맞게_바뀜'], color='#B4B2A9', label='틀림 → 틀림')
        ax.set_xticks(x); ax.set_xticklabels(lab, rotation=60, ha='right', fontsize=5); ax.set_title(ch); ax.axhline(0, color='k', lw=.5); meta[ch] = g.to_dict('records')
    axs[0].legend(fontsize=6); fig.suptitle('단계의 효과: 판정이 바뀐 넓이 m²(정답 종류별, LoD2 모두·항공 LiDAR 지붕)', fontsize=9); save(fig, 'fig7_4_effect', dict(values=meta))
    fig, axs = plt.subplots(3, 2, figsize=(7.6, 10)); meta = {}
    for pi, prior in enumerate(PRIORS):
        L = load(prior); j1 = L['J']['J_판 1']; j4 = L['J']['J_판 4']; c1 = ((L['t'] == 0) & (j1 == 0)) | ((L['t'] == 1) & (j1 == 1)) | (np.isin(L['t'], [2, 3]) & (j1 == 2)); c4 = ((L['t'] == 0) & (j4 == 0)) | ((L['t'] == 1) & (j4 == 1)) | (np.isin(L['t'], [2, 3]) & (j4 == 2))
        for si, site in enumerate(['B0', 'B173 주변', 'R1']):
            ax = axs[si, pi]; m = L['site'] == site; ch = m & (j1 != j4); ax.scatter(L['c'][m][:, 0], L['c'][m][:, 1], s=.2, color='#E7E5DF', lw=0, rasterized=True)
            for mm, col in [(ch & ~c1 & c4, '#1D9E75'), (ch & c1 & ~c4, '#A32D2D'), (ch & (c1 == c4), '#5F5E5A')]: ax.scatter(L['c'][mm][:, 0], L['c'][mm][:, 1], s=.6, color=col, lw=0, rasterized=True)
            ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([]); ax.set_title(f'{site} · {PN[prior]}'); meta[f'{site}_{prior}'] = dict(changed_m2=float(L['area'][ch].sum()), right_m2=float(L['area'][ch & ~c1 & c4].sum()), wrong_m2=float(L['area'][ch & c1 & ~c4].sum()))
    fig.legend(handles=[Patch(color='#1D9E75', label='맞게 바뀜'), Patch(color='#A32D2D', label='틀리게 바뀜'), Patch(color='#5F5E5A', label='바뀌었으나 맞고 틀림 같음')], loc='lower center', ncol=3, frameon=False)
    fig.suptitle('판 1 → 판 4 판정이 바뀐 패치(바탕 = 모든 패치)', fontsize=9); save(fig, 'fig7_4_maps', dict(area_m2=meta))
    cu = pd.read_csv(TD/'t74_threshold_curve.csv'); cu = cu[(cu.version == '전체') & (cu.unit == '넓이')]; fig, axs = plt.subplots(1, 3, figsize=(11, 3.4)); meta = {}
    for ax, (p, s) in zip(axs, units):
        for nm, col in [('판 1', '#B4B2A9'), ('판 4', '#D85A30'), ('JUDGECHECK-v2 본 방법', '#378ADD'), ('11/22 구조', '#7F77DD')]:
            g = cu[(cu.prior == p) & (cu.surface == s) & (cu.plan == nm)]; ax.plot(g.tau_m, g.judgment_acc, '-o', ms=2.5, color=col, label=f'{nm} 판정'); ax.plot(g.tau_m, g.target_acc, '--', color=col, lw=.8)
        ax.set_xscale('log'); ax.set_xticks([.1, .15, .2, .3, .5, 1]); ax.set_xticklabels(['0.10', '0.15', '0.20', '0.30', '0.50', '1.00']); ax.set_ylim(0, 100); ax.set_title(f'{p} {s}'); ax.set_xlabel('정답 τ (m, 세 자료 같음)')
    axs[0].legend(fontsize=5); axs[0].set_ylabel('% (실선 판정, 점선 목표)'); fig.suptitle('문턱 곡선', fontsize=9); save(fig, 'fig7_4_curve', dict(source=str(TD/'t74_threshold_curve.csv')))
def main(w):
    for x in w: {'0': fig0, '1': fig1, '2': fig2, '3': fig3, '4': fig4}[x]()
if __name__ == '__main__': main(sys.argv[1:] or list('01234'))
