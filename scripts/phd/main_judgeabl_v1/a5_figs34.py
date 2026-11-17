"""그림 3 (판정 지도: 세 실험 지역 + JC 그림 1의 여섯 동, 판 여섯의 목표 맞음·틀림)과 그림 4 (달라진 자리: 기존 2·3과 본 방법 사이).
바탕: 그림 3 = JC 드론 LiDAR 색 정사영상(JC 그림 1과 같음), 그림 4 = 비스듬한 학습 영상(JP p7_figs.oblique_view / draw_on_view 그대로). 참값은 표시에만."""
from common import *
import pandas as pd
sys.path.append('/repo/scripts/phd/main_judgeprobe_v1')
import p7_figs as P7
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.patches import Patch
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
FIG = D/'figures'; CN = [CASE[c] for c in CASES]
OK_C = {1: '#a6d96a', 0: '#fdae61'}   # JC 그림 1: 목표 맞음, 목표 틀림
COLS = [('기존 1 T=0.5 m', '기존 1 (0.5 m)'), ('기존 2 대표(저장된 L)', '기존 2'), ('기존 3 아래 5 %', '기존 3'), ('기존 4 결합(세 실험 지역)', '기존 4'), ('본 방법', '본 방법'), ('패치 다수결 상한', '정답 판정')]
def save(fig, name, meta):
    fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig); dump(FIG/f'{name}.json', dict(meta, at=now(), scientific_verdict=None))
def okmat(prior):
    z = np.load(O/f'okbits_{prior}.npz'); names = list(z['names']); n = int(z['n'])
    return names, z['bits'], n, z['keep']
def ok_of(names, bits, n, v): return np.unpackbits(bits[names.index(v)])[:n].astype(bool)
def ortho():
    z = loadz(JC/'figures_cache/ortho_campus.npz', ['rgb', 'x0', 'y0', 'res']); return z['rgb'], float(z['x0']), float(z['y0']), float(z['res'])
def background(ax, ext, O_):
    rgb, X0, Y0, res = O_; x0, x1, y0, y1 = ext; i0 = max(int((x0 - X0)/res), 0); i1 = int((x1 - X0)/res); j0 = max(int((y0 - Y0)/res), 0); j1 = int((y1 - Y0)/res)
    ax.imshow(rgb[j0:j1, i0:i1], origin='lower', extent=[X0 + i0*res, X0 + i1*res, Y0 + j0*res, Y0 + j1*res], interpolation='bilinear'); ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
def paint(ax, xy, val, colors, ext, res=.25, alpha=.75):
    x0, x1, y0, y1 = ext; W = int(np.ceil((x1 - x0)/res)); H = int(np.ceil((y1 - y0)/res)); img = np.zeros((H, W, 4))
    ix = ((xy[:, 0] - x0)/res).astype(int); iy = ((xy[:, 1] - y0)/res).astype(int); ok = (ix >= 0) & (iy >= 0) & (ix < W) & (iy < H)
    for k, c in colors.items():
        m = ok & (val == k)
        if m.any(): img[iy[m], ix[m]] = to_rgba(c, alpha)
    ax.imshow(img, origin='lower', extent=[x0, x0 + W*res, y0, y0 + H*res], interpolation='nearest')
def fig3():
    O_ = ortho()
    for prior in ['LoD2', 'ALS']:
        names, bits, n, keep = okmat(prior); g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz', 'gt_kind', 'src', 'site', 'building', 'case'])
        g = {k: v[keep] for k, v in g.items()}; ci = np.searchsorted(CASES, g['case'])
        OK = {v: ok_of(names, bits, n, v) for v, _ in COLS}
        f3 = np.zeros(n, bool)
        jf = json.loads((R/'docs/experiments/phd/main_judgecheck_v2/figures'/f'fig1_judgment_map_{prior}.json').read_text())
        f3 = fusion_scope(prior, keep, g)
        scenes = []
        for s in jf['scenes']:
            nm = s['scene']; m = (g['src'] == 1) & (g['site'] == nm) if nm in SITES else (g['building'] == next(b for b in jf['chosen'] if b.endswith(nm)))
            scenes.append((nm, m, s['extent']))
        fig, axs = plt.subplots(len(scenes), len(COLS), figsize=(2.6*len(COLS), 2.5*len(scenes)), squeeze=False); meta = []
        for r, (nm, m, ext) in enumerate(scenes):
            top = m & (g['gt_kind'] != 2); row = dict(scene=nm, gt_points=int(m.sum()), extent=ext, values={})
            for c, (v, lab) in enumerate(COLS):
                ax = axs[r, c]; background(ax, ext, O_); sel = top & (f3 if v.startswith('기존 4') else True)
                if v.startswith('기존 4') and not (m & f3).any():
                    ax.text(.5, .5, '없음\n(세 실험 지역만)', ha='center', va='center', transform=ax.transAxes, fontsize=7, bbox=dict(fc='white', alpha=.8)); row['values'][lab] = None
                else:
                    paint(ax, g['xyz'][sel, :2], OK[v][sel].astype(int), OK_C, ext); mm = m & (f3 if v.startswith('기존 4') else True)
                    pc = [100*OK[v][mm & (ci == k)].mean() if (mm & (ci == k)).any() else np.nan for k in range(4)]; row['values'][lab] = pc
                    ax.set_xlabel(' / '.join('-' if not np.isfinite(x) else f'{x:.0f}' for x in pc), fontsize=6.5)
                if r == 0: ax.set_title(lab, fontsize=8)
                if c == 0: ax.set_ylabel(nm.replace('_b10', ''), fontsize=7)
            meta.append(row)
        fig.legend(handles=[Patch(color=OK_C[1], label='목표 맞음'), Patch(color=OK_C[0], label='목표 틀림')], ncol=2, loc='lower center', bbox_to_anchor=(.5, -.005), frameon=False, fontsize=7)
        fig.suptitle(f"{'LoD2' if prior == 'LoD2' else '항공 LiDAR'}: 장면마다 판 여섯의 목표 맞음·틀림 (위에서 보이는 지붕·땅의 참값 점)", fontsize=10, y=1.0)
        fig.text(.01, -.01, '칸 아래 숫자 = 그 장면의 목표 맞음 % (두 자료 모두 유효 / 사전정보 오류 / 영상 깊이 오류 / 영상 깊이 결측, 벽 포함). 장면 = 세 실험 지역 + JC 그림 1의 여섯 동', fontsize=6.5)
        fig.tight_layout(rect=[0, .015, 1, .99]); save(fig, f'fig3_judgment_maps_{prior}', dict(figure=3, prior=prior, scenes=meta, columns=[c[0] for c in COLS], scene_rule='JC fig1_judgment_map scenes', colours=OK_C))
def fusion_scope(prior, keep, g):
    """a1 과 같은 규칙: 세 실험 지역 참값 점 중 JUDGEAPPLY 결합 패치에 짝이 있는 점."""
    f3 = np.zeros(len(keep), bool)
    gall = loadz(JC/'analysis'/f'gt_{prior}.npz', ['src', 'site'])
    for site in SITES:
        z = loadz(JC/'truth/exp'/f'{site}__{prior}.npz', ['current_patch_id']); rows = np.flatnonzero((g['src'] == 1) & (g['site'] == site))
        allrows = np.flatnonzero((gall['src'] == 1) & (gall['site'] == site)); pos = np.searchsorted(allrows, keep[rows])
        dec = set(loadz(JA/'decisions'/f'{site}__{prior}.npz', ['patch_id'])['patch_id']); cp = z['current_patch_id'][pos]
        f3[rows] = np.array([s in dec for s in cp])
    return f3
def fig4():
    for prior in ['LoD2', 'ALS']:
        names, bits, n, keep = okmat(prior)
        g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz', 'gid', 'cell', 'building', 'case']); g = {k: v[keep] for k, v in g.items()}
        d = loadz(JP/f'patch_{prior}.npz', ['tile', 'centre', 'normal', 'tangent1', 'prior_height_m', 'mvs_mean_m', 'case', 'building', 'region', 'd_for_check', 'L_m', 's_P', 's_M', 't', 'j_region', 'target_h', 'tiles', 'kind'])
        ts = list(d['tiles']); pid = np.concatenate([loadz(JC/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id'])['patch_id'] for t in ts])
        VZ = {}
        for r in REGIONS + ['none']:
            p = O/'variants'/f'{r}__{prior}.npz'
            if p.exists(): VZ[r] = np.load(p)
        def var_of(i, v):
            z = VZ[d['region'][i]]; vn = list(z['variants']); k = int(np.flatnonzero(z['patch_id'] == pid[i])[0]); j = vn.index(v); return int(z['region'][j, k]), float(z['target_h'][j, k])
        gtree = cKDTree(g['xyz'][:, :2]); okm = ok_of(names, bits, n, '본 방법')
        for vo, lab in [('기존 2 대표(저장된 L)', '기존 2'), ('기존 3 아래 5 %', '기존 3')]:
            oko = ok_of(names, bits, n, vo); sets = {}
            for kind, m in [('본 방법만 맞음', okm & ~oko), (f'{lab}만 맞음', ~okm & oko)]:
                idx = np.flatnonzero(m); df = pd.DataFrame(dict(b=g['building'][idx], c=g['cell'][idx], x=g['xyz'][idx, 0], y=g['xyz'][idx, 1], z=g['xyz'][idx, 2], i=idx))
                cells = df.groupby(['b', 'c']).agg(x=('x', 'mean'), y=('y', 'mean'), z=('z', 'mean')).reset_index(); comps = []
                for b, q in cells.groupby('b'):
                    P = q[['x', 'y', 'z']].values; pr = cKDTree(P).query_pairs(.6, output_type='ndarray')
                    nc, lab_ = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(P), len(P))), directed=False)
                    for k in range(nc): comps.append((b, set(q['c'].values[lab_ == k]), int((lab_ == k).sum())*.0625))
                comps.sort(key=lambda c: -c[2]); pick, seen = [], set()
                for b, cs, a in comps:
                    if b in seen: continue
                    pick.append((b, cs, a)); seen.add(b)
                    if len(pick) == 3: break
                sets[kind] = [(b, df['i'].values[(df['b'].values == b) & df['c'].isin(cs).values], a) for b, cs, a in pick]
            fig, axs = plt.subplots(6, 2, figsize=(8, 18), squeeze=False); meta = []; r_ = 0
            for kind, pk in sets.items():
                for b, pts, a in pk:
                    axA, axB = axs[r_, 0], axs[r_, 1]; gids = g['gid'][pts]; ug, cnt = np.unique(gids, return_counts=True); i = int(ug[np.argmax(cnt)])
                    X0 = d['centre'][ug] + np.nan_to_num(d['prior_height_m'][ug])[:, None]*np.nan_to_num(d['normal'][ug])
                    j = P7.oblique_view(X0)
                    if j is None: axA.text(.5, .5, '비스듬한 영상 없음', ha='center', transform=axA.transAxes); axA.axis('off')
                    else: P7.draw_on_view(axA, j, X0, '#ffe600')
                    axA.set_title(f"({kind}) 가. {b.replace('DEBY_LOD2_', '')} · {a:.1f} m²", fontsize=6.5)
                    c0 = d['centre'][i]; nn = d['normal'][i]; t1 = d['tangent1'][i]; t2 = np.cross(nn, t1); t2 /= np.linalg.norm(t2)
                    sec = lambda Q: (np.abs((Q - c0) @ t2) <= .15) & (np.abs((Q - c0) @ t1) <= 3) & (np.abs((Q - c0) @ nn) <= 3)
                    G = g['xyz'][gtree.query_ball_point(c0[:2], 4.5)]; G = G[sec(G)]; M = P7.mvs_near(ts[d['tile'][i]], c0 - 4.5, c0 + 4.5); M = M[sec(M)]
                    if len(M) > 5000: M = M[np.random.default_rng(1).choice(len(M), 5000, replace=False)]
                    axB.scatter((M - c0) @ t1, (M - c0) @ nn, s=.5, c='#1f77b4', lw=0, alpha=.5, label='영상 깊이 점'); axB.scatter((G - c0) @ t1, (G - c0) @ nn, s=.8, c='#333', lw=0, label='참값')
                    aa = [-3, 3]; hp = d['prior_height_m'][i]; axB.plot(aa, [hp, hp], c='#ff7f0e', lw=1, label='사전 정보')
                    rm, hm = int(d['j_region'][i, 4]), float(d['target_h'][i, 4]); ro, ho = var_of(i, vo)
                    if np.isfinite(hm): axB.plot([-1.5, 1.5], [hm, hm], c='#1f4e9c', lw=1.6, ls='--', label='본 방법 목표')
                    if np.isfinite(ho): axB.plot([-1.5, 1.5], [ho, ho], c='#8e44ad', lw=1.6, ls=':', label=f'{lab} 목표')
                    axB.set_xlim(-3, 3); axB.set_ylim(-3, 3); axB.set_aspect('equal'); axB.tick_params(labelsize=5); axB.set_title('나. 단면 ±0.15 m', fontsize=6.5)
                    if r_ == 0: axB.legend(fontsize=4.5, loc='lower left', markerscale=3, frameon=False)
                    cs = CASE.get(int(d['case'][i]), '네 경우 밖') if d['case'][i] >= 0 else '없음'
                    line = f"{b.replace('DEBY_LOD2_', '')} · {cs} · 본 방법 {JUD.get(rm)} / {lab} {JUD.get(ro)}\nd {d['d_for_check'][i]:.2f} L {d['L_m'][i]:.2f} s_P {d['s_P'][i]:.2f} s_M {d['s_M'][i]:.2f} t {d['t'][i]:.2f}"
                    axB.set_xlabel(line, fontsize=5); meta.append(dict(type=kind, building=b, area_m2=a, gt_points=len(pts), patches=len(ug), section_patch=int(i), view=None if j is None else P7.cam().names[j], line=line)); r_ += 1
            for k in range(r_, 6): axs[k, 0].axis('off'); axs[k, 1].axis('off')
            fig.suptitle(f"{'LoD2' if prior == 'LoD2' else '항공 LiDAR'}: {lab}와 본 방법의 목표 맞음이 달라진 자리 (넓이 큰 차례, 한 건물에서 하나)", fontsize=8)
            fig.tight_layout(rect=[0, 0, 1, .98]); save(fig, f"fig4_changed_{'old2' if lab == '기존 2' else 'old3'}_{prior}", dict(figure=4, prior=prior, pair=[vo, '본 방법'], rule='GT points whose target-ok differs; 0.25 m cells (JC cell) joined within 0.6 m per building; area = cells x 0.0625', clusters=meta))
            print('FIG4', prior, lab, flush=True)
if __name__ == '__main__':
    for f in sys.argv[1:]: globals()[f]()
    progress('그림 ' + ', '.join(sys.argv[1:]) + ' 끝')
