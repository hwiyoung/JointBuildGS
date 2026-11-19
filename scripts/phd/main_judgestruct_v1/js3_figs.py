"""그림 11(처음 상태 지도), 13(하한·상한 맞음 지도, 영상 오류 패치 본보기 여섯). 사용: js3_figs.py <prior>"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1'); sys.path.append('/repo/scripts/phd/main_judgeprobe_v1')
from jscommon import *
import pandas as pd
import p7_figs as P7
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import to_rgba
from matplotlib.patches import Patch
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
FONT = '/fonts/NotoSansCJK-Regular.ttc'; font_manager.fontManager.addfont(FONT); plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(), 'axes.unicode_minus': False, 'font.size': 7})
FIG = D/'figures'; FIG.mkdir(parents=True, exist_ok=True)
ST_C = {0: '#2ca02c', 1: '#ff7f0e', 2: '#1f77b4', 4: '#9467bd', 3: '#7f7f7f', -2: '#ffff33', -3: '#ffff33', -9: '#ffff33'}
OK_C = {1: '#a6d96a', 0: '#d7191c'}
def save(fig, name, meta):
    fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig); dump(FIG/f'{name}.json', dict(meta, at=now(), scientific_verdict=None))
def ortho():
    z = loadz(JC/'figures_cache/ortho_campus.npz', ['rgb', 'x0', 'y0', 'res']); return z['rgb'], float(z['x0']), float(z['y0']), float(z['res'])
def background(ax, ext, O_):
    rgb, X0, Y0, res = O_; x0, x1, y0, y1 = ext; i0 = max(int((x0 - X0)/res), 0); i1 = int((x1 - X0)/res); j0 = max(int((y0 - Y0)/res), 0); j1 = int((y1 - Y0)/res)
    ax.imshow(rgb[j0:j1, i0:i1], origin='lower', extent=[X0 + i0*res, X0 + i1*res, Y0 + j0*res, Y0 + j1*res], interpolation='bilinear')
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
def paint(ax, xy, val, colors, ext, res=.25, alpha=.8):
    x0, x1, y0, y1 = ext; W = int(np.ceil((x1 - x0)/res)); H = int(np.ceil((y1 - y0)/res)); img = np.zeros((H, W, 4))
    ix = ((xy[:, 0] - x0)/res).astype(int); iy = ((xy[:, 1] - y0)/res).astype(int); ok = (ix >= 0) & (iy >= 0) & (ix < W) & (iy < H)
    for k, c in colors.items():
        m = ok & (val == k)
        if m.any(): img[iy[m], ix[m]] = to_rgba(c, alpha)
    ax.imshow(img, origin='lower', extent=[x0, x0 + W*res, y0, y0 + H*res], interpolation='nearest')
def any_view(X):
    """P7.oblique_view 규칙에서 35~65° 각도 제한만 뺀 판(덧붙임: 비스듬한 영상이 없을 때만). 보이는 점 수가 가장 많은 영상."""
    c = P7.cam(); best = None
    for j in range(len(c.names)):
        q = X @ c.M[j, :3, :3].T + c.M[j, :3, 3]; z = q[:, 2]; uv = q[:, :2]/z[:, None]*[c.K[0, 0], c.K[1, 1]] + [c.K[0, 2], c.K[1, 2]]
        ins = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < 1024) & (uv[:, 1] >= 0) & (uv[:, 1] < 741)
        if ins.sum() < max(3, .5*len(X)): continue
        dep = P7.depth(j)
        if dep is None: continue
        px = np.clip(np.rint(uv[ins]).astype(int), [0, 0], [1023, 740]); dd = dep[px[:, 1], px[:, 0]]; vis = np.isfinite(dd) & (dd > 0) & (z[ins] <= dd + .5)
        sc = (int(vis.sum()), -float(np.linalg.norm(c.centres[j] - X.mean(0))))
        if best is None or sc > best[0]: best = (sc, j)
    return None if best is None or best[0][0] == 0 else best[1]
def scenes(prior):
    j = json.loads((JC_DOC/'figures'/f'fig1_judgment_map_{prior}.json').read_text()); chosen = j['chosen']; out = []
    for s in j['scenes']:
        full = next((b for b in chosen if b.replace('DEBY_LOD2_', '') == s['scene']), None); out.append((s['scene'], s['extent'], full))
    return out


def main(prior):
    T = Timer(); O_ = ortho(); Z = np.load(O/prior/'fig_arrays.npz'); sig, pc, E, lo, up, rb, keep = Z['sig'], Z['pc'], Z['E'], Z['lo'], Z['up'], Z['rb'], Z['keep']; n = int(Z['n'])
    okb, okl, oku = [np.unpackbits(Z[k])[:n].astype(bool) for k in ['ok_b', 'ok_lo', 'ok_up']]
    d = loadz(JP/f'patch_{prior}.npz', ['tile', 'tiles', 'centre', 'normal', 'tangent1', 'prior_height_m', 'mvs_mean_m', 'building', 'place', 'kind', 'area', 'd_for_check', 'L_m', 's_P', 's_M', 't', 'j_region', 'target_h'])
    A = d['area']; kind = d['kind']; SC = scenes(prior); meta = []
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz', 'gt_kind', 'gid', 'case', 'paired'])
    gx = g['xyz'][keep]; gk = g['gt_kind'][keep]; ggid = g['gid'][keep]
    def in_scene(xy, ext): return (xy[:, 0] >= ext[0]) & (xy[:, 0] <= ext[1]) & (xy[:, 1] >= ext[2]) & (xy[:, 1] <= ext[3])
    # ---- 그림 11
    fig, axs = plt.subplots(3, 3, figsize=(12, 13)); axs = axs.ravel()
    for i, (name, ext, full) in enumerate(SC):
        ax = axs[i]; background(ax, ext, O_)
        pm = in_scene(d['centre'][:, :2], ext) & (d['building'] == full) if full else in_scene(d['centre'][:, :2], ext)
        roof = pm & (kind == 1); paint(ax, d['centre'][roof & ~sig, :2], np.zeros((roof & ~sig).sum()), {0: '#dddddd'}, ext, alpha=.45)
        paint(ax, d['centre'][roof & sig, :2], pc[roof & sig], ST_C, ext)
        sm = pm & sig; a_st = A[sm & np.isin(pc, STATE_ORDER)].sum(); sh = {s_: 100*A[sm & (pc == s_)].sum()/a_st if a_st else np.nan for s_ in STATE_ORDER}
        ax.set_title(name, fontsize=8)
        ax.set_xlabel(f"차이가 유의한 넓이 {A[sm].sum():.0f} m² (지붕 {A[sm & (kind == 1)].sum():.0f}, 벽 {A[sm & (kind == 2)].sum():.0f})\n유효/사전 오류/영상 오류/결측/밖 % = " + ' / '.join(f'{sh[s_]:.0f}' for s_ in STATE_ORDER), fontsize=6.5)
        meta.append(dict(scene=name, building=full, extent=ext, sig_area_m2=float(A[sm].sum()), state_area_pct={STATE[s_]: sh[s_] for s_ in STATE_ORDER}))
    h = [Patch(color=ST_C[s_], label=STATE[s_]) for s_ in STATE_ORDER] + [Patch(color='#ffff33', label='처음 상태 없음(동률·점 3개 미만·참값 없음)'), Patch(color='#dddddd', label='차이가 유의하지 않은 지붕 패치')]
    fig.legend(handles=h, ncol=4, fontsize=7, loc='lower center', bbox_to_anchor=(.5, -.01), frameon=False)
    fig.suptitle(f'{PN[prior]}: 차이가 유의한 패치의 처음 상태 — 세 실험 지역과 JUDGECHECK-v2 그림 1의 여섯 동 (지붕만 칠함; 칸 아래 비율은 지붕+벽 넓이)', fontsize=9, y=1.0)
    fig.tight_layout(rect=[0, .03, 1, .99]); save(fig, f'fig11_initial_state_{prior}', dict(prior=prior, scenes=meta, rule='scenes = JC fig1 json; walls not drawn (not visible from above)'))
    # ---- 그림 13 맞음 지도
    fig, axs = plt.subplots(len(SC), 3, figsize=(10, 3.2*len(SC))); meta = []
    for r, (name, ext, full) in enumerate(SC):
        m = (gk != 2) & in_scene(gx[:, :2], ext) & ((d['building'][ggid] == full) if full else True); ins = m & sig[ggid]
        for c, (lab, ok) in enumerate([('본 방법', okb), ('구조 하한', okl), ('구조 상한 (참값으로)', oku)]):
            ax = axs[r, c]; background(ax, ext, O_); paint(ax, gx[m, :2], ok[m].astype(int), OK_C, ext)
            ax.set_title(f'{name} · {lab}' if c == 0 else lab, fontsize=8)
            ax.set_xlabel(f'지붕 참값 점 목표 맞음 {100*ok[m].mean():.1f} % · 차이가 유의한 패치 안 {100*ok[ins].mean() if ins.any() else np.nan:.1f} %', fontsize=6.5)
        meta.append(dict(scene=name, roof_points=int(m.sum()), in_sig=int(ins.sum()), ok_pct={k: float(100*v[m].mean()) for k, v in [('본 방법', okb), ('구조 하한', okl), ('구조 상한', oku)]}))
    fig.legend(handles=[Patch(color=OK_C[1], label='목표 맞음'), Patch(color=OK_C[0], label='목표 틀림')], ncol=2, fontsize=7, loc='lower center', bbox_to_anchor=(.5, -.005), frameon=False)
    fig.suptitle(f'{PN[prior]}: 본 방법·구조 하한·구조 상한의 목표 맞음 지도 (지붕 참값 점)', fontsize=10, y=1.0); fig.tight_layout(rect=[0, .01, 1, .99])
    save(fig, f'fig13_bounds_maps_{prior}', dict(prior=prior, scenes=meta))
    # ---- 그림 13 본보기: 영상 오류 패치 모임 (건물마다 0.36 m 안 이어짐), 넓은 모임 차례, 한 건물에서 하나
    ie = np.flatnonzero(E); X0 = d['centre'][ie] + np.nan_to_num(d['prior_height_m'][ie])[:, None]*np.nan_to_num(d['normal'][ie])
    pr = cKDTree(X0).query_pairs(.36, output_type='ndarray'); pr = pr[d['building'][ie[pr[:, 0]]] == d['building'][ie[pr[:, 1]]]]
    ncomp, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(ie), len(ie))), directed=False)
    ca = np.bincount(lab, weights=A[ie]); order = np.argsort(-ca, kind='stable'); pick = []; seen = set()
    for cc in order:
        mem = ie[lab == cc]; b = d['building'][mem[0]]
        if b in seen: continue
        seen.add(b); pick.append((cc, mem))
        if len(pick) == 6: break
    gtree = cKDTree(g['xyz'][:, :2]); ts = list(d['tiles'])
    fig, axs = plt.subplots(len(pick), 2, figsize=(9.5, 3.4*len(pick)), squeeze=False); meta = []
    for r, (cc, mem) in enumerate(pick):
        cnts = np.bincount(g['gid'][g['paired']], minlength=len(A)); i = int(mem[np.argmax(cnts[mem])])
        c0 = d['centre'][i]; nn = d['normal'][i]; t1 = d['tangent1'][i]; t2 = np.cross(nn, t1); t2 /= np.linalg.norm(t2); hp = d['prior_height_m'][i]; hm = d['mvs_mean_m'][i]
        sq = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])*.125
        corners = np.concatenate([d['centre'][k] + d['prior_height_m'][k]*d['normal'][k] + sq[:, :1]*d['tangent1'][k] + sq[:, 1:]*np.cross(d['normal'][k], d['tangent1'][k]) for k in mem[:400]])
        mine = np.flatnonzero(g['paired'] & np.isin(g['gid'], mem)); X = np.r_[corners, g['xyz'][mine]]
        j = P7.oblique_view(X); cols = ['#ffe600']*len(corners) + [ST_C.get(int(c), 'k') for c in g['case'][mine]]; view_rule = '모임 전체'
        if j is None:   # 모임 전체로 영상을 못 찾으면 단면 패치 둘레 1.5 m 안의 모임 패치와 그 참값 점으로 다시 찾음
            near = mem[np.linalg.norm(d['centre'][mem] - c0, axis=1) <= 1.5]
            cn = np.concatenate([d['centre'][k] + d['prior_height_m'][k]*d['normal'][k] + sq[:, :1]*d['tangent1'][k] + sq[:, 1:]*np.cross(d['normal'][k], d['tangent1'][k]) for k in near])
            mn = np.flatnonzero(g['paired'] & np.isin(g['gid'], near)); X = np.r_[cn, g['xyz'][mn]]; cols = ['#ffe600']*len(cn) + [ST_C.get(int(c), 'k') for c in g['case'][mn]]
            j = P7.oblique_view(X); view_rule = '단면 패치 둘레 1.5 m'
        if j is None: j = any_view(X); view_rule += ' → 각도 제한 없이 가장 많이 보이는 영상' if j is not None else ''
        if j is None: axs[r, 0].text(.5, .5, '비스듬한 영상 없음', ha='center', transform=axs[r, 0].transAxes); axs[r, 0].axis('off')
        else:   # P7.draw_on_view 은 영상 안 점만 그리고 색은 그대로 받으므로, 같은 규칙으로 먼저 거름
            cm_ = P7.cam(); uv, _, okv = cm_.project(X, j); okv &= (uv[:, 0] >= 0) & (uv[:, 0] < cm_.w) & (uv[:, 1] >= 0) & (uv[:, 1] < cm_.h)
            P7.draw_on_view(axs[r, 0], j, X[okv], list(np.array(cols, dtype=object)[okv]), pad=40)
        axs[r, 0].set_title(f"{str(d['building'][i]).replace('DEBY_LOD2_', '')} · {PLACE.get(int(d['place'][i]), '')} · 모임 {len(mem)} 패치 {ca[cc]:.1f} m² · 참값 점 {len(mine)}" + (' · 영상: 각도 제한 없음' if '각도' in view_rule else ''), fontsize=6.5)
        B = axs[r, 1]; own = (g['xyz'][g['paired'] & (g['gid'] == i)] - c0) @ nn; ys = np.r_[own, [hp, hm]]; ys = ys[np.isfinite(ys)]
        ylo, yhi = (ys.min() - .5, ys.max() + .5) if len(ys) else (-1.5, 1.5)
        if yhi - ylo < 3: m_ = (ylo + yhi)/2; ylo, yhi = m_ - 1.5, m_ + 1.5
        sec = lambda Q: (np.abs((Q - c0) @ t2) <= .15) & (np.abs((Q - c0) @ t1) <= 1.5) & ((Q - c0) @ nn >= ylo) & ((Q - c0) @ nn <= yhi)
        nb = gtree.query_ball_point(c0[:2], 2.5); G = g['xyz'][nb]; gc = g['case'][nb]; sm = sec(G); G, gc = G[sm], gc[sm]
        M = P7.mvs_near(ts[d['tile'][i]], c0 - 2.5 + np.minimum(0, ylo)*np.abs(nn), c0 + 2.5 + np.maximum(0, yhi)*np.abs(nn)); M = M[sec(M)]
        if len(M) > 4000: M = M[np.random.default_rng(1).choice(len(M), 4000, replace=False)]
        B.scatter((M - c0) @ t1, (M - c0) @ nn, s=.5, c='#9ecae1', lw=0, label='영상 깊이 점')
        for c in [0, 1, 2, 4, 3]:
            m = gc == c
            if m.any(): B.scatter((G[m] - c0) @ t1, (G[m] - c0) @ nn, s=2, c=ST_C[c], lw=0, label=f'참값 점: {STATE[c]}')
        B.plot([-1.5, 1.5], [hp, hp], color='#d9822b', lw=1, label='사전 정보 면')
        if np.isfinite(hm): B.plot([-.125, .125], [hm, hm], color='#1f4e9c', lw=2.2, label='영상 깊이 평균 높이(패치)')
        for xv in [-.125, .125]: B.axvline(xv, color='k', ls=':', lw=.7)
        B.set_xlim(-1.5, 1.5); B.set_ylim(ylo, yhi); B.tick_params(labelsize=5); B.set_title('단면 ±0.15 m (점선 = 패치 경계, 세로 = 법선 방향 m)', fontsize=6.5)
        B.set_xlabel(f"d {d['d_for_check'][i]:.2f} m · L {d['L_m'][i]:.2f} m · s_P {d['s_P'][i]:.2f} · s_M {d['s_M'][i]:.2f} (t {d['t'][i]:.2f}) · 본 방법 {JUD.get(int(rb[i]))}", fontsize=5.5)
        if r == 0: B.legend(fontsize=4.5, loc='lower left', markerscale=3, frameon=False)
        meta.append(dict(group_rank=r + 1, building=str(d['building'][i]), group_patches=int(len(mem)), group_area_m2=float(ca[cc]), section_patch_gid=i, gt_points=int(len(mine)),
                         d_m=float(d['d_for_check'][i]), L_m=float(d['L_m'][i]), s_P=float(d['s_P'][i]), s_M=float(d['s_M'][i]), t=float(d['t'][i]), base=JUD.get(int(rb[i])),
                         base_region_area_in_group={JUD.get(int(k)): float(A[mem][rb[mem] == k].sum()) for k in np.unique(rb[mem])}, view=None if j is None else P7.cam().names[j], view_rule=view_rule))
    fig.suptitle(f'{PN[prior]}: 영상 오류 패치(차이가 유의하고 처음 상태 영상 깊이 오류)의 본보기 — 넓은 모임 차례, 한 건물에서 하나', fontsize=8); fig.tight_layout(rect=[0, 0, 1, .98])
    save(fig, f'fig13_outlier_examples_{prior}', dict(prior=prior, rule='image-error patches connected within 0.36 m (prior-plane centre) per building; group area descending; one per building; section through the group patch with most GT points', groups=meta))
    progress(f'js3 {prior} 그림 11·13 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main(sys.argv[1])
