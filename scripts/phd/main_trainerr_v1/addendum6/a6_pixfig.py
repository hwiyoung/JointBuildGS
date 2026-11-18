"""Order 10 pixel figures (work da), FINALTRAIN 30000, views on the outward side of the point (work-da view set 2). GPU (/source = r31).
  absent  : state-1 points (no Gaussian within 0.2 m), B0 x LoD2 (most kept points labelled '이웃이 그린다'): three kept and three lost points at the 25/50/75 % quantiles of
            the point's median within-tau weight; for each the view whose within weight is closest to that median -> figures/da_pix_absent.png
  present : lost state-2 points, one per work-da label (5.3): the scene with the most lost points of that label, the point at the median of its (mean depth - point depth),
            the view closest to that median -> figures/da_pix_present.png
Each panel: splat weight alpha*T along the pixel ray against (splat depth - point depth), 0.1 m bins, stacked by kind relative to the point's patch; tau band; lines at the
point depth, the weighted-mean depth (used by the mesh) and the median depth. Plotted values -> payload addendum6/da/pixfig_<name>.npz; choice rule in the json."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
import a6_da as DA
FIG = A6D/'figures'; KIND4 = ['같은 목표', '다른 목표', '풀린 것', '묶이지 않은 것']; KC = ['#1f77b4', '#9467bd', '#ff7f0e', '#7f7f7f']
SC_KO = {'R1rep_b10__LoD2': 'R1 × LoD2', 'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B0_b10__LoD2': 'B0 × LoD2', 'B0_b10__ALS': 'B0 × 항공 LiDAR', 'B173nb_b10__ALS': 'B173 × 항공 LiDAR', 'B173nb_b10__LoD2': 'B173 × LoD2'}

def pairs(stem):
    z = loadz(A6O/'da'/f'pix_{stem}.npz', ['pt', 'view', 'zp', 'mean', 'median', 'w3', 'acc']); L = loadz(A6O/'da'/f'labels_{stem}.npz'); P = loadz(A6O/'points'/f'sel_{stem}.npz')
    pos = np.full(len(P['state']), -1, 'i8'); pos[L['sel']] = np.arange(len(L['sel'])); k = pos[z['pt']]; return z, L, P, k, L['facing_pairs']

def choose_absent():
    stem = 'B0_b10__LoD2'; z, L, P, k, fc = pairs(stem); out = []
    for gk in [0, 1]:
        cand = np.flatnonzero((L['state'] == 1) & (L['group'] == gk) & (L['facing__views'] > 0)); mw = L['facing__med_within'][cand]; o = cand[np.argsort(mw, kind='stable')]
        for q in (.25, .5, .75):
            i = int(o[int(round(q*(len(o)-1)))]); pr = np.flatnonzero((k == i) & fc); j = pr[np.argmin(np.abs(z['w3'][pr, 1]-L['facing__med_within'][i]))]
            out.append(dict(stem=stem, group=GROUP_KO[gk], quantile=int(q*100), li=i, sel=int(L['sel'][i]), pair=int(j), view=int(z['view'][j]), label=DA.L1[int(L['facing__label1'][i])]))
    return out

def choose_present():
    out = []
    for li, lab in enumerate(DA.L2[:5]):
        best = None
        for stem in cfg6()['points']['scenes']:
            L = loadz(A6O/'da'/f'labels_{stem}.npz', ['state', 'group', 'facing__label2']); n = int(((L['state'] == 2) & (L['group'] == 1) & (L['facing__label2'] == li)).sum())
            if n and (best is None or n > best[1]): best = (stem, n)
        if best is None: out.append(dict(label=lab, none=True)); continue
        stem = best[0]; z, L, P, k, fc = pairs(stem); cand = np.flatnonzero((L['state'] == 2) & (L['group'] == 1) & (L['facing__label2'] == li))
        mo = L['facing__med_mean_off'][cand]; ok = np.isfinite(mo); cand = cand[ok]; mo = mo[ok]
        if not len(cand): out.append(dict(label=lab, none=True)); continue
        i = int(cand[np.argsort(mo)[len(mo)//2]]); pr = np.flatnonzero((k == i) & fc); d = (z['mean'][pr]-z['zp'][pr]); d = np.where(np.isfinite(d), d, 1e9); j = pr[np.argmin(np.abs(d-L['facing__med_mean_off'][i]))]
        out.append(dict(stem=stem, label=lab, n_label=best[1], li=i, sel=int(L['sel'][i]), pair=int(j), view=int(z['view'][j])))
    return out

def render(items):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4'); import a4_da as D4
    camera = D4.gpu_setup(); res = []; cache = {}
    for it in items:
        if it.get('none'): res.append(None); continue
        stem = it['stem']
        if stem not in cache:
            cache.clear(); g, tag, tidx, _ = DA.load_ft(stem); md, mi = D4.views_of(stem); cache[stem] = (g, tag, tidx, md, mi, sorted(mi))
        g, tag, tidx, md, mi, vn = cache[stem]; P = loadz(A6O/'points'/f'sel_{stem}.npz'); s = it['sel']; X = P['xyz'][s].astype('f8'); v = int(P['v'][s]); tau = float(P['tau'][s])
        nm = vn[it['view']]; m = mi[nm]; K = np.asarray(m['K']); M = np.asarray(m['W2C'])
        with np.load(md/m['file']) as zz: H, W = zz['owner'].shape
        xc = M[:3, :3]@X+M[:3, 3]; u = K[0, 0]*xc[0]/xc[2]+K[0, 2]; vv = K[1, 1]*xc[1]/xc[2]+K[1, 2]
        with torch.no_grad(): C = D4.contrib(g, camera(W, H, K, M, nm), np.array([int(np.floor(u))]), np.array([int(np.floor(vv))]))
        gi = C[:, 1].astype('i8'); kd = np.where(tag[gi] == 1, np.where(tidx[gi] == v, 0, 1), np.where(tag[gi] == 2, 2, 3)); acc, mean, med_ = D4.per_pixel(C, 1)
        res.append(dict(it, view_name=nm, zp=float(xc[2]), tau=tau, dep=C[:, 3], w=C[:, 2], kind=kd, mean=float(mean[0]), median=float(med_[0]), acc=float(acc[0]), xyz=X))
    return res

def panel(ax, r, title):
    d = r['dep']-r['zp']; lo, hi = -6., 3.; bins = np.arange(lo, hi+.1, .1); dc = np.clip(d, lo, hi-1e-6); bottom = np.zeros(len(bins)-1)
    for k in range(4):
        h, _ = np.histogram(dc[r['kind'] == k], bins, weights=r['w'][r['kind'] == k]); ax.bar(bins[:-1]+.05, h, width=.1, bottom=bottom, color=KC[k], label=KIND4[k], edgecolor='none'); bottom += h
    ax.axvspan(-r['tau'], r['tau'], color='#2ca02c', alpha=.12, label=f'점 깊이 ±τ ({r["tau"]:.2f} m)'); ax.axvline(0, color='k', lw=2.2, label='점 깊이')
    for val, col, ls, nm in [(r['mean']-r['zp'], '#e31a1c', '-', '평균 깊이(메시에 쓰임)'), (r['median']-r['zp'], '#e31a1c', '--', '중앙 깊이')]:
        if np.isfinite(val): ax.axvline(np.clip(val, lo, hi), color=col, lw=2.2, ls=ls, label=f'{nm} {val:+.2f} m')
    ax.set_xlim(lo, hi); ax.set_xlabel('시선 위 깊이 − 점 깊이 (m)   ← 카메라 쪽 | 점 뒤 →  (−6 m 밖은 왼쪽 끝 칸에 모음)', fontsize=10); ax.set_ylabel('무게 αT (0.1 m 칸 합)'); ax.grid(alpha=.3)
    ax.set_title(title, fontsize=12, loc='left'); top = max(bottom.max(), 1e-3)
    if bottom[:int((-r['tau']-lo)/.1)].sum() > .5: ax.annotate('점 앞의 무게', xy=(lo+.3, bottom[:3].max()*.9 if bottom[:3].max() > 0 else top*.5), xytext=(lo+1.5, top*.85), arrowprops=dict(arrowstyle='->', lw=1.8), fontsize=12, weight='bold')
    return dict(bins=bins, stacked_top=bottom)

def main(which):
    plt = korean_plt(); items = choose_absent() if which == 'absent' else choose_present(); res = render(items); out = {}
    if which == 'absent':
        fig, axs = plt.subplots(2, 3, figsize=(30, 13), sharey=False)
        for i, r in enumerate(res):
            ax = axs[i//3, i % 3]; q = panel(ax, r, f'{r["group"]} · 그 점의 \'점 깊이 무게\' 중앙값 {r["quantile"]} % 분위 · 붙인 말: {r["label"]} · 이 화소 불투명도 합 {r["acc"]:.2f}')
            out.update({f'p{i}__{k}': v for k, v in q.items()}); out[f'p{i}__dep_minus_point'] = r['dep']-r['zp']; out[f'p{i}__w'] = r['w']; out[f'p{i}__kind'] = r['kind']
        axs[0, 0].legend(fontsize=10, loc='upper right'); fig.suptitle('지킨 점(위)은 이웃이 그리고, 잃은 점(아래)은 그렇지 않다 — B0 × LoD2, 그 자리에 가우시안이 없는 점, 대표 화소 셋씩', fontsize=17, weight='bold')
    else:
        rr = [r for r in res if r is not None]; fig, axs = plt.subplots(len(rr), 1, figsize=(20, 5.2*len(rr))); axs = np.atleast_1d(axs)
        for i, (ax, r) in enumerate(zip(axs, rr)):
            q = panel(ax, r, f'붙인 말: {r["label"]} ({SC_KO[r["stem"]]}, 이 말이 붙은 잃은 점 {r["n_label"]:,}개 가운데 평균 깊이 차 중앙값의 점) · 불투명도 합 {r["acc"]:.2f}')
            out.update({f'p{i}__{k}': v for k, v in q.items()}); out[f'p{i}__dep_minus_point'] = r['dep']-r['zp']; out[f'p{i}__w'] = r['w']; out[f'p{i}__kind'] = r['kind']
        axs[0].legend(fontsize=10, loc='upper right'); fig.suptitle('가우시안이 그 자리에 있는데 그린 깊이는 다른 곳에 놓인다 — 잃은 점, 붙인 말마다 대표 화소 하나', fontsize=17, weight='bold')
    fig.tight_layout(rect=(0, 0, 1, .96)); fig.savefig(FIG/f'da_pix_{which}.png', dpi=100); plt.close(fig)
    savez(A6O/'da'/f'pixfig_{which}.npz', **out)
    dump(FIG/f'da_pix_{which}.json', dict(at=now(), figure=f'da_pix_{which}.png', model='FINALTRAIN 30000', items=[{k: v for k, v in (r or it).items() if k not in ('dep', 'w', 'kind', 'xyz')} | ({'xyz': r['xyz'].tolist()} if r else {}) for it, r in zip(items, res)],
                                              rule=__doc__.split('\n')[2:6], scientific_verdict=None))
    print('PIXFIG', which, flush=True)

if __name__ == '__main__': main(sys.argv[1])
