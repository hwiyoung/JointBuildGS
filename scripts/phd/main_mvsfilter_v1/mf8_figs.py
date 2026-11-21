"""7절 그림. JUDGESTRUCT-v1 js3_figs 의 고르기 규칙·짜임·색을 그대로 쓴다(그 모듈을 읽어 씀). 참값은 표시에만.
 fig7_examples_<prior>_<method>      : JS fig13_outlier_examples 와 같은 여섯 자리(영상 오류 패치 모임, 같은 단면 패치, 같은 영상) — 단면의 영상 깊이 점을 살아남음/지워짐으로 색 나눔
 fig7_prior_error_<prior>_<method>   : 처음 상태 사전정보 오류인 차이가 유의한 패치의 본보기 여섯(같은 고르기 규칙)
 fig7_maps_<prior>                   : 세 실험 지역, 지금 점군과 방법 A 의 차이가 유의한 패치를 처음 상태로 칠함
 fig6_bars_<prior>                   : 6절 줄들의 네 경우 목표 맞음 막대
사용: mf8_figs.py <prior> <method> [<method> ...]"""
import sys, os
sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1'); sys.path.append('/repo/scripts/phd/main_judgeprobe_v1')
from jscommon import *
import js3_figs as J3
import p7_figs as P7
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mfcommon as MC
ST_C = J3.ST_C; SURV_C = {1: '#3182bd', 0: '#e6550d'}
WI_ = MC.WI

def mvs_near_idx(tile, lo, hi):
    X = np.load(WI_/'points'/tile/'mvs_a_xyz.npy', mmap_mode='r'); out = []; ids = []
    for b in range(0, len(X), 20_000_000):
        q = np.asarray(X[b:b + 20_000_000], dtype=np.float64); m = (q >= lo).all(1) & (q <= hi).all(1)
        if m.any(): out.append(q[m]); ids.append(np.flatnonzero(m) + b)
    return (np.concatenate(out), np.concatenate(ids)) if out else (np.zeros((0, 3)), np.zeros(0, int))

MASKS = {}
def survived_of(method, tile, idx):
    if method not in MASKS: MASKS[method] = np.load(MC.O/'masks'/f'{method}.npy', mmap_mode='r')
    V = np.load(WI_/'points'/tile/'mvs_a_view.npy', mmap_mode='r')[idx]; pix = np.load(MC.O/'pixmap'/f'{tile}.npy', mmap_mode='r')[idx]; s = np.zeros(len(idx), bool)
    for v in np.unique(V):
        m = V == v; row = np.unpackbits(np.asarray(MASKS[method][int(v)]), count=MC.H*MC.Wd).astype(bool); s[m] = row[pix[m]]
    return s

CMAP_ = None
COLOR_C = False   # 덧붙임 1 4절: A2 판에서 단면의 영상 깊이 점을 c(일치 시점 수)로 칠함
C_COL = [((1, 2), '#d7301f', 'c 1~2'), ((3, 4), '#fdae61', 'c 3~4'), ((5, 10**6), '#1a9850', 'c 5 이상')]
def c_of(tile, idx):
    global CMAP_
    if CMAP_ is None: CMAP_ = np.memmap(MC.O/'a2/px_c.u16', dtype='<u2', mode='r', shape=(819, MC.H*MC.Wd))
    V = np.load(WI_/'points'/tile/'mvs_a_view.npy', mmap_mode='r')[idx]; pix = np.load(MC.O/'pixmap'/f'{tile}.npy', mmap_mode='r')[idx]; out = np.zeros(len(idx), int)
    for v in np.unique(V): m = V == v; out[m] = np.asarray(CMAP_[int(v)])[pix[m]]
    return out

def groups(mask, d, A, n=6, exclude=()):   # 덧붙임 2: n·exclude(이미 쓴 건물) 더함, 기본값은 앞과 같음
    ie = np.flatnonzero(mask); X0 = d['centre'][ie] + np.nan_to_num(d['prior_height_m'][ie])[:, None]*np.nan_to_num(d['normal'][ie])
    pr = cKDTree(X0).query_pairs(.36, output_type='ndarray'); pr = pr[d['building'][ie[pr[:, 0]]] == d['building'][ie[pr[:, 1]]]]
    ncomp, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(ie), len(ie))), directed=False)
    ca = np.bincount(lab, weights=A[ie]); order = np.argsort(-ca, kind='stable'); pick = []; seen = set(exclude)
    for cc in order:
        mem = ie[lab == cc]; b = d['building'][mem[0]]
        if b in seen: continue
        seen.add(b); pick.append((cc, mem, float(ca[cc])))
        if len(pick) == n: break
    return pick

def examples(prior, method, kind_, d, g, Z, Pn, Pm, title, pick=None, xlab=None):   # 덧붙임 2: pick(고른 모임)·xlab(칸 아래 한 줄 함수) 을 줄 수 있음
    A = d['area']; sig, pc, E = Z['sig'], Z['pc'], Z['E']; sel = E if kind_ == 'image' else (sig & (pc == 1))
    pick = groups(sel, d, A) if pick is None else pick; gtree = cKDTree(g['xyz'][:, :2]); ts = list(d['tiles']); cnts = np.bincount(g['gid'][g['paired']], minlength=len(A))
    fig, axs = plt.subplots(len(pick), 2, figsize=(9.5, 3.4*len(pick)), squeeze=False); meta = []
    sq = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])*.125
    for r, (cc, mem, area) in enumerate(pick):
        i = int(mem[np.argmax(cnts[mem])]); c0 = d['centre'][i]; nn = d['normal'][i]; t1 = d['tangent1'][i]; t2 = np.cross(nn, t1); t2 /= np.linalg.norm(t2); hp = d['prior_height_m'][i]
        corners = np.concatenate([d['centre'][k] + d['prior_height_m'][k]*d['normal'][k] + sq[:, :1]*d['tangent1'][k] + sq[:, 1:]*np.cross(d['normal'][k], d['tangent1'][k]) for k in mem[:400]])
        mine = np.flatnonzero(g['paired'] & np.isin(g['gid'], mem)); X = np.r_[corners, g['xyz'][mine]]; cols = ['#ffe600']*len(corners) + [ST_C.get(int(c), 'k') for c in g['case'][mine]]
        j = P7.oblique_view(X); view_rule = '모임 전체'
        if j is None:
            near = mem[np.linalg.norm(d['centre'][mem] - c0, axis=1) <= 1.5]
            cn = np.concatenate([d['centre'][k] + d['prior_height_m'][k]*d['normal'][k] + sq[:, :1]*d['tangent1'][k] + sq[:, 1:]*np.cross(d['normal'][k], d['tangent1'][k]) for k in near])
            mn = np.flatnonzero(g['paired'] & np.isin(g['gid'], near)); X = np.r_[cn, g['xyz'][mn]]; cols = ['#ffe600']*len(cn) + [ST_C.get(int(c), 'k') for c in g['case'][mn]]
            j = P7.oblique_view(X); view_rule = '단면 패치 둘레 1.5 m'
        if j is None: j = J3.any_view(X); view_rule += ' → 각도 제한 없이' if j is not None else ''
        if j is None: axs[r, 0].text(.5, .5, '영상 없음', ha='center', transform=axs[r, 0].transAxes); axs[r, 0].axis('off')
        else:
            cm_ = P7.cam(); uv, _, okv = cm_.project(X, j); okv &= (uv[:, 0] >= 0) & (uv[:, 0] < cm_.w) & (uv[:, 1] >= 0) & (uv[:, 1] < cm_.h)
            P7.draw_on_view(axs[r, 0], j, X[okv], list(np.array(cols, dtype=object)[okv]), pad=40)
        bname = str(d['building'][i]).replace('DEBY_LOD2_', '')
        axs[r, 0].set_title(f"{bname} · {PLACE.get(int(d['place'][i]), '')} · 모임 {len(mem)} 패치 {area:.1f} m²", fontsize=6.5)
        B = axs[r, 1]; own = (g['xyz'][g['paired'] & (g['gid'] == i)] - c0) @ nn; hm0 = d['mvs_mean_m'][i]; ys = np.r_[own, [hp, hm0]]; ys = ys[np.isfinite(ys)]
        ylo, yhi = (ys.min() - .5, ys.max() + .5) if len(ys) else (-1.5, 1.5)
        if yhi - ylo < 3: m_ = (ylo + yhi)/2; ylo, yhi = m_ - 1.5, m_ + 1.5
        sec = lambda Q: (np.abs((Q - c0) @ t2) <= .15) & (np.abs((Q - c0) @ t1) <= 1.5) & ((Q - c0) @ nn >= ylo) & ((Q - c0) @ nn <= yhi)
        nb = gtree.query_ball_point(c0[:2], 2.5); G = g['xyz'][nb]; gc = g['case'][nb]; sm = sec(G); G, gc = G[sm], gc[sm]
        M, mid = mvs_near_idx(ts[d['tile'][i]], c0 - 2.5 + np.minimum(0, ylo)*np.abs(nn), c0 + 2.5 + np.maximum(0, yhi)*np.abs(nn)); k_ = sec(M); M, mid = M[k_], mid[k_]
        sv = survived_of(method, ts[d['tile'][i]], mid); cv = c_of(ts[d['tile'][i]], mid) if COLOR_C else np.zeros(len(mid), int)
        if len(M) > 4000: ch = np.random.default_rng(1).choice(len(M), 4000, replace=False); M, sv, cv = M[ch], sv[ch], cv[ch]
        if COLOR_C:
            for (a_, b_), col_, lab in C_COL:
                m = (cv >= a_) & (cv <= b_); B.scatter((M[m] - c0) @ t1, (M[m] - c0) @ nn, s=.7, c=col_, lw=0, label=f'영상 깊이 점: {lab}', alpha=.8)
        else:
          for val, lab in [(0, '영상 깊이 점: 지워짐'), (1, '영상 깊이 점: 살아남음')]:
            m = sv == bool(val); B.scatter((M[m] - c0) @ t1, (M[m] - c0) @ nn, s=.7, c=SURV_C[val], lw=0, label=lab, alpha=.8)
        for c in [0, 1, 2, 4, 3]:
            m = gc == c
            if m.any(): B.scatter((G[m] - c0) @ t1, (G[m] - c0) @ nn, s=2.5, c=ST_C[c], lw=0, marker='s', label=f'참값 점: {STATE[c]}')
        B.plot([-1.5, 1.5], [hp, hp], color='#d9822b', lw=1, label='사전 정보 면')
        hm1 = Pm['mean'][i]
        if np.isfinite(hm0): B.plot([-.125, .125], [hm0, hm0], color='#1f4e9c', lw=2.2, label='영상 깊이 평균(지금)')
        if np.isfinite(hm1): B.plot([-.125, .125], [hm1, hm1], color='#e6550d', lw=1.6, ls='--', label='영상 깊이 평균(걸러낸 뒤)')
        for xv in [-.125, .125]: B.axvline(xv, color='k', ls=':', lw=.7)
        B.set_xlim(-1.5, 1.5); B.set_ylim(ylo, yhi); B.tick_params(labelsize=5); B.set_title('단면 ±0.15 m (세로 = 법선 방향 m)', fontsize=6.5)
        rn0, rn1 = int(Pn['raw_n'][i]), int(Pm['raw_n'][i]); sr = 100*rn1/rn0 if rn0 > 0 else np.nan
        pm_ = mem; a0 = A[pm_]; sr_g = 100*Pm['raw_n'][pm_].sum()/max(Pn['raw_n'][pm_].sum(), 1)
        B.set_xlabel(f"{bname} · 살아남은 비율 {sr:.0f} % (모임 {sr_g:.0f} %) · 판정 {JUD.get(int(Pn['lo'][i]))} → {JUD.get(int(Pm['lo'][i]))}" if xlab is None else xlab(i, bname), fontsize=6.5)
        if r == 0: B.legend(fontsize=4.3, loc='lower left', markerscale=3, frameon=False)
        moved = {f'{JUD.get(int(a))}→{JUD.get(int(b))}': float(a0[(Pn['lo'][pm_] == a) & (Pm['lo'][pm_] == b)].sum()) for a in np.unique(Pn['lo'][pm_]) for b in np.unique(Pm['lo'][pm_]) if ((Pn['lo'][pm_] == a) & (Pm['lo'][pm_] == b)).any()}
        meta.append(dict(rank=r + 1, building=str(d['building'][i]), group_patches=int(len(mem)), group_area_m2=area, section_patch_gid=i, view=None if j is None else P7.cam().names[j], view_rule=view_rule,
                         section_cyl_points_before=rn0, section_cyl_points_after=rn1, section_survive_pct=sr, group_survive_pct=float(sr_g), judgment_before=JUD.get(int(Pn['lo'][i])), judgment_after=JUD.get(int(Pm['lo'][i])),
                         group_judgment_area_m2=moved, section_mvs_points_drawn=int(len(M)), section_survived_drawn=int(sv.sum()),
                         **({'section_drawn_by_c': {lab: int(((cv >= a_) & (cv <= b_)).sum()) for (a_, b_), _, lab in C_COL}} if COLOR_C else {})))
    fig.suptitle(title, fontsize=8); fig.tight_layout(rect=[0, 0, 1, .98])
    return fig, meta

def main(prior, methods):
    T = Timer(); Z = np.load(MC.JS/prior/'fig_arrays.npz')
    d = loadz(JP/f'patch_{prior}.npz', ['tile', 'tiles', 'centre', 'normal', 'tangent1', 'prior_height_m', 'mvs_mean_m', 'building', 'place', 'kind', 'area'])
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz', 'gid', 'case', 'paired', 'gt_kind'])
    jd = MC.O/'judge'/prior; Pn = dict(np.load(jd/'patch_none.npz')); Pn['mean'] = d['mvs_mean_m']
    for method in ([] if os.environ.get('MF_MAPS_ONLY') == '1' else methods):   # MF_MAPS_ONLY=1: 지도만 (덧붙임 1 2절 대조 뒤 A2 지도)
        Pm = dict(np.load(jd/f'patch_{method}.npz')); Pm['mean'] = load_mean(prior, method, d)
        for kind_, nm, tt in [('image', 'examples', '영상 오류 패치(처음 상태 영상 깊이 오류) 본보기 — JUDGESTRUCT 그림 13 과 같은 자리'), ('prior', 'prior_error', '사전정보 오류 패치 본보기 — 같은 고르기 규칙')]:
            fig, meta = examples(prior, method, kind_, d, g, Z, Pn, Pm, f'{PN[prior]} · {MC.MNAME[method]}: {tt}')
            J3.save(fig, f'fig7_{nm}_{prior}_{method}', dict(prior=prior, method=method, rule='JS js3 그림 13 고르기 규칙 (0.36 m 이어짐, 넓은 모임 차례, 한 건물에서 하나, 단면 = 모임에서 참값 점이 가장 많은 패치)', groups=meta))
        if method == 'A2':   # 덧붙임 1 4절: c 로 칠한 판
            global COLOR_C
            COLOR_C = True
            fig, meta = examples(prior, method, 'image', d, g, Z, Pn, Pm, f'{PN[prior]} · {MC.MNAME[method]}: 영상 오류 패치 본보기 — 단면의 영상 깊이 점을 c(일치 시점 수, 자기 포함)로 칠함')
            COLOR_C = False
            J3.save(fig, f'fig7_examples_{prior}_A2_c', dict(prior=prior, method=method, colors={lab: col_ for _, col_, lab in C_COL}, rule='fig7_examples_<prior>_A2 와 같은 자리·같은 영상', groups=meta))
    # 지도: 세 실험 지역
    for mm in [m_ for m_ in ('A', 'A2') if m_ in methods]:   # A = 발주 7절, A2 = 덧붙임 1 2절('7절을 A2 로 똑같이')
        O_ = J3.ortho(); SC = J3.scenes(prior)[:3]; A_ = d['area']; kind = d['kind']; PA = dict(np.load(jd/f'patch_{mm}.npz')); mlab = '방법 A' if mm == 'A' else '방법 A2(세션 판)'
        fig, axs = plt.subplots(len(SC), 2, figsize=(9, 4.3*len(SC)), squeeze=False); meta = []
        for r, (name, ext, full) in enumerate(SC):
            pm = (d['centre'][:, 0] >= ext[0]) & (d['centre'][:, 0] <= ext[1]) & (d['centre'][:, 1] >= ext[2]) & (d['centre'][:, 1] <= ext[3])
            for c, (lab, P_) in enumerate([('지금 점군', Pn), (mlab, PA)]):
                ax = axs[r, c]; J3.background(ax, ext, O_); sg = P_['sig']; roof = pm & (kind == 1)
                J3.paint(ax, d['centre'][roof & ~sg, :2], np.zeros((roof & ~sg).sum()), {0: '#dddddd'}, ext, alpha=.45); J3.paint(ax, d['centre'][roof & sg, :2], Z['pc'][roof & sg], ST_C, ext)
                sm = pm & sg; a_st = A_[sm & np.isin(Z['pc'], STATE_ORDER)].sum(); sh = {s_: 100*A_[sm & (Z['pc'] == s_)].sum()/a_st if a_st else np.nan for s_ in STATE_ORDER}
                ax.set_title(f'{name} · {lab}', fontsize=8); ax.set_xlabel(f"차이가 유의한 넓이 {A_[sm].sum():.0f} m² · 유효/사전 오류/영상 오류/결측/밖 % = " + ' / '.join(f'{sh[s_]:.0f}' for s_ in STATE_ORDER), fontsize=6.3)
                meta.append(dict(scene=name, line=lab, sig_area_m2=float(A_[sm].sum()), state_area_pct={STATE[s_]: sh[s_] for s_ in STATE_ORDER}))
        h = [Patch(color=ST_C[s_], label=STATE[s_]) for s_ in STATE_ORDER] + [Patch(color='#ffff33', label='처음 상태 없음'), Patch(color='#dddddd', label='차이가 유의하지 않은 지붕 패치')]
        fig.legend(handles=h, ncol=4, fontsize=6.5, loc='lower center', bbox_to_anchor=(.5, -.01), frameon=False)
        fig.suptitle(f'{PN[prior]}: 차이가 유의한(변화가 탐지된) 지붕 패치의 처음 상태 — 지금 점군 대 {mlab} (칸 아래 비율은 지붕+벽)', fontsize=8.5, y=1.0); fig.tight_layout(rect=[0, .03, 1, .99])
        J3.save(fig, f'fig7_maps_{prior}' + ('' if mm == 'A' else '_A2'), dict(prior=prior, method=mm, scenes=meta))
    if os.environ.get('MF_MAPS_ONLY') == '1': return
    # 막대
    R6 = pd.read_csv(MC.D/'tables/t6_rejudge.csv'); q = R6[(R6.prior == PN[prior]) & (R6.surface == ('모두' if prior == 'LoD2' else '지붕'))]
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, lv, lab in [(axs[0], 'ok', '점 단위'), (axs[1], 'patch_ok', '패치 단위')]:
        L = list(q.line); w = .8/len(L); cmap = plt.get_cmap('tab10')
        for k, (_, r) in enumerate(q.iterrows()):
            vals = [r[f'{lv}_{c}'] for c in CN]; ax.bar(np.arange(4) + (k - len(L)/2 + .5)*w, vals, w, color=cmap(k % 10), label=r.line)
        ax.set_xticks(range(4)); ax.set_xticklabels(CN, fontsize=7); ax.set_ylim(0, 100); ax.set_ylabel('목표 맞음 %'); ax.set_title(lab, fontsize=8)
    axs[1].legend(fontsize=5.5, loc='lower left', frameon=False)
    fig.suptitle(f'{PN[prior]}: 네 경우 목표 맞음 — 6절 줄', fontsize=8.5); fig.tight_layout()
    J3.save(fig, f'fig6_bars_{prior}', dict(prior=prior, lines=list(q.line), values=json.loads(q.to_json(orient='records', force_ascii=False))))
    MC.progress(f'mf8 그림 {prior} {methods} 끝 ({round(T.s())} 초)')

def load_mean(prior, method, d):
    out = np.full(len(d['tile']), np.nan)
    for ti, t in enumerate(d['tiles']):
        m = np.flatnonzero(d['tile'] == ti); z = loadz(MC.O/'patch'/method/f'{t}.npz', [f'{prior}__mvs_mean_m']); out[m] = z[f'{prior}__mvs_mean_m']
    return out

if __name__ == '__main__': main(sys.argv[1], sys.argv[2:])
