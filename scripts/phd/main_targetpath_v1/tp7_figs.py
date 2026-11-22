"""Order 6 figures (CPU, reads only). usage: tp7_figs.py [stem ...]
Per scene: 본보기 A = 잃은 점 모임, 가려지지 않은 영상에서 종류 2·3이 주된 점; 본보기 B = 잃은 점 모임, 종류 1이 주된 점; 본보기 C = 고친 점 모임.
Cluster = the largest 8-connected group of the selected points on a 1 m grid (WRONGTARGET wt3 rule). View = the training view (pairs not occluded,
10 m rule) holding the most cluster points, ties by the mean cosine between the normal and the view direction.
Four panels: photo crop, target depth map of that view (pixel class colours; cluster points coloured by their kind in that view), pixel weight map,
section (slab +-0.25 m through the cluster centre along the horizontal normal or the cluster's main axis): GT points, method target surface (target
mesh offset of the wrong-target point file) and allowed band (target patch +-1.96 sigma), image depth surface (s_mvs), result surface (s_result),
centres of the largest-weight splat at the cluster points in that view (tp4 contrib). R1 x ALS floor band (TRAINERR addendum4 place floor_band):
same view, method run and GTT run side by side (GTT result = GTTARGET gtt_s0_base reference__s_m).
Each png has a json of the same name. Text in Korean, no internal names."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
from scipy import ndimage
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
from matplotlib.colors import ListedColormap, LogNorm
fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name(); plt.rcParams['axes.unicode_minus'] = False
from PIL import Image
FIG = D/'figures'; FIG.mkdir(parents=True, exist_ok=True)
KCOL = ['#1A9E3A', '#D62728', '#FF7F0E', '#9467BD', '#7F7F7F']; KSHORT = ['맞는 목표', '앞의 다른 목표', '영상 깊이 목표', '뒤의 목표', '감독 없음']
PCLS = ['일치 조각', '보존 조각', '보정 조각', '결측 조각', '영상 깊이', '감독 없음']; PCOL = ['#A6D96A', '#2C7BB6', '#FDAE61', '#D7191C', '#BBBBBB', '#FFFFFF']

def clusters(idx, xyz, cell=1.0):
    if not len(idx): return []
    xy = xyz[idx, :2]; lo = xy.min(0); ij = np.floor((xy-lo)/cell).astype(int); G = np.zeros(ij.max(0)+1, bool); G[ij[:, 0], ij[:, 1]] = True
    lab, n = ndimage.label(G, structure=np.ones((3, 3))); l = lab[ij[:, 0], ij[:, 1]]
    return sorted([idx[l == c] for c in range(1, n+1)], key=lambda a: -len(a))

def pick_view(z, C, P, idx):
    m = np.isin(z['pt'], C) & ~z['occ10']
    if not m.any(): m = np.isin(z['pt'], C)
    v = z['view'][m]; names = list(idx); Cm = np.array([cam_centre(np.asarray(idx[names[j]]['W2C'])) for j in range(len(names))])
    X = P['xyz'][z['pt'][m]].astype('f8'); d = Cm[v]-X; d /= np.linalg.norm(d, axis=1, keepdims=True); cs = (d*P['normal'][z['pt'][m]]).sum(1)
    cnt = np.bincount(v, minlength=len(names)); cm = np.bincount(v, cs, len(names))/np.maximum(cnt, 1); best = int(np.lexsort((-cm, -cnt))[0]); return best, names[best]

def panels(stem, run, P, z, C, j, nm, axes, title):
    site, prior = stem.split('__'); idx = json.loads((maps_of(stem, run)/'index.json').read_text())['views']; mm = idx[nm]
    m = loadz(maps_of(stem, run)/mm['file']); img = np.asarray(Image.open(S0/'fork_inputs/s61'/site/f'scene_{prior}'/'images'/f'{nm}.jpg').convert('RGB').resize((1024, 741)))
    sel = (z['view'] == j) & np.isin(z['pt'], C); px, py, kd = z['px'][sel], z['py'][sel], z['kind'][sel]
    x0, x1 = max(0, px.min()-60), min(1024, px.max()+60); y0, y1 = max(0, py.min()-60), min(741, py.max()+60)
    axes[0].imshow(img[y0:y1, x0:x1]); axes[0].scatter(px-x0, py-y0, s=4, c='yellow', lw=0); axes[0].set_title('사진 (노란 점 = 모임의 참값 점)', fontsize=8)
    jreg = loadz(FT/'targets'/f'{stem}.npz', ['judge_region'])['judge_region'] if run == 'ft' else None
    o = m['owner'][y0:y1, x0:x1]; w = m['weight'][y0:y1, x0:x1]; cls = np.full(o.shape, 5)
    if jreg is not None:
        rg = np.where(o >= 0, jreg[np.clip(o, 0, None)], -1); cls = np.select([(o >= 0) & (rg == 0), (o >= 0) & (rg == 1), (o >= 0) & np.isin(rg, [2, 3]), (o >= 0) & (rg == 4), (o < 0) & (w > 0)], [0, 1, 2, 3, 4], 5)
    else: cls = np.where(o >= 0, 0, np.where(w > 0, 4, 5))
    cls[w <= 0] = 5
    axes[1].imshow(cls, cmap=ListedColormap(PCOL), vmin=-.5, vmax=5.5, interpolation='nearest')
    for k in range(5):
        s_ = kd == k
        if s_.any(): axes[1].scatter(px[s_]-x0, py[s_]-y0, s=6, c=KCOL[k], lw=0, label=f'{KSHORT[k]} {int(s_.sum())}')
    axes[1].legend(fontsize=6, loc='lower left', framealpha=.8, markerscale=2)
    axes[1].set_title('목표 지도 (바탕: 화소 소유, 점: 점의 종류)' if run == 'ft' else '목표 지도 (바탕: 참값 조각 / 영상 깊이, 점: 종류)', fontsize=8)
    wv = np.where(w > 0, w, np.nan); im = axes[2].imshow(wv, norm=LogNorm(.1, 10), cmap='viridis', interpolation='nearest'); plt.colorbar(im, ax=axes[2], fraction=.046)
    axes[2].set_title('화소 무게 (빈칸 = 0)', fontsize=8)
    for a in axes[:3]: a.set_xticks([]); a.set_yticks([])
    return dict(view=nm, crop=[int(x0), int(y0), int(x1), int(y1)], kinds_in_view={KSHORT[k]: int((kd == k).sum()) for k in range(5)}, pixels=int(sel.sum()))

def section(stem, run, P, C, z, j, ax, Wt, Tg, res_s=None):
    X = P['xyz'][C].astype('f8'); c0 = np.median(X, 0); nrm = np.nanmedian(P['normal'][C], 0); hv = nrm[:2].copy()
    if np.linalg.norm(hv) < .3:   # flat cluster: cut across it (short horizontal axis)
        e, V = np.linalg.eigh(np.cov((X[:, :2]-c0[:2]).T)) if len(X) > 2 else (None, np.eye(2)); hv = V[:, 0]
    hv /= np.linalg.norm(hv); perp = np.array([-hv[1], hv[0]]); WX = Wt['xyz'].astype('f8')
    dperp = (WX[:, :2]-c0[:2])@perp; s_ = (WX[:, :2]-c0[:2])@hv; sl = (np.abs(dperp) <= .25) & (np.abs(s_) <= 8)
    Wn = Wt['n']; ax.scatter(s_[sl], WX[sl, 2], s=2, c='k', lw=0, label='참값')
    for key, col, lab in [('s_mvs', '#FF7F0E', '영상 깊이 면'), ('s_target_mesh', '#1A9E3A', '목표 면'), ('s_result', '#1F77B4', '결과 면(본 방법)')]:
        v = Wt[key][sl]; ok = np.isfinite(v); Y = WX[sl][ok]+v[ok, None]*Wn[sl][ok]
        ax.scatter((Y[:, :2]-c0[:2])@hv, Y[:, 2], s=2, c=col, lw=0, label=lab)
    if res_s is not None:
        v = res_s[sl]; ok = np.isfinite(v); Y = WX[sl][ok]+v[ok, None]*Wn[sl][ok]; ax.scatter((Y[:, :2]-c0[:2])@hv, Y[:, 2], s=2, c='#17BECF', lw=0, label='결과 면(참값 목표 판)')
    tc = Tg['target']; ok = np.isfinite(tc[:, 0]); tp = (tc[ok, :2]-c0[:2]); ts = tp@hv; td = tp@perp; tsl = (np.abs(td) <= .25) & (np.abs(ts) <= 8)
    if tsl.any():
        ax.errorbar(ts[tsl], tc[ok][tsl, 2], yerr=1.96*Tg['target_sigma_m'][ok][tsl]*np.abs(Tg['normal'][ok][tsl, 2]), fmt='none', ecolor='#1A9E3A', alpha=.35, lw=.8)
    if z is not None:
        Cs = C[np.abs((P['xyz'][C, :2].astype('f8')-c0[:2])@perp) <= .25]   # cluster points inside the slab only
        sel = (z['view'] == j) & np.isin(z['pt'], Cs)
        if sel.any():
            gx = z['gxyz'][sel]; ax.scatter((gx[:, :2]-c0[:2])@hv, gx[:, 2], s=10, marker='x', c='#D62728', lw=.7, label='무게가 가장 큰 가우시안 중심(단면 안 모임 점, 이 영상)')
    Xs = X[np.abs((X[:, :2]-c0[:2])@perp) <= .25]; xc = (Xs[:, :2]-c0[:2])@hv if len(Xs) else np.zeros(1)
    ax.axvspan(max(xc.min(), -8), min(xc.max(), 8), color='y', alpha=.15, lw=0)
    ax.set_xlabel('단면 방향 거리 (m)'); ax.set_ylabel('높이 (m)'); ax.legend(fontsize=6, loc='best', markerscale=3); ax.set_title('단면 (두께 ±0.25 m, 노란 띠 = 단면 안 모임 점의 범위)', fontsize=8)
    return dict(centre=c0.tolist(), direction=hv.tolist())

def contrib_view(stem, run, P):
    for mode in ('all', 'sub'):
        p = O/'contrib'/f'{run}_{stem}_{mode}.npz'
        if p.exists():
            c = loadz(p, ['pt', 'view', 'top_g']); g = ply_read(model_of(stem, run)/'point_cloud/iteration_30000/point_cloud.ply', ['x', 'y', 'z'])
            tg = c['top_g'][:, 0]; ok = tg >= 0; gx = np.full((len(tg), 3), np.nan); gx[ok] = np.c_[g['x'], g['y'], g['z']][tg[ok]]
            return dict(pt=c['pt'], view=c['view'], gxyz=gx)
    return None

def main(stems):
    for stem in stems:
        P = loadz(O/'points'/f'sel_{stem}.npz'); T = loadz(O/'points'/f'tp_{stem}.npz'); z = loadz(O/'pairs'/f'ft_{stem}.npz')
        Wt = loadz(WT/'points'/f'wt_{stem}.npz', ['xyz', 's_mvs', 's_target_mesh', 's_result']); Wt['n'] = gt_reference(stem)['reference__normal'][loadz(WT/'points'/f'wt_{stem}.npz', ['point_id'])['point_id']].astype('f8')
        Tg = loadz(FT/'targets'/f'{stem}.npz', ['target', 'target_sigma_m', 'normal']); idx = json.loads((maps_of(stem, 'ft')/'index.json').read_text())['views']
        cv = contrib_view(stem, 'ft', P); X = P['xyz']; mk = T['ft_main_kind_visible']
        cases = [('A', '잃은 점 · 가려지지 않은 영상에서 앞의 다른 목표·영상 깊이 목표가 주된 모임', np.flatnonzero((P['group'] == 0) & np.isin(mk, [1, 2]))),
                 ('B', '잃은 점 · 가려지지 않은 영상에서 맞는 목표가 주된 모임', np.flatnonzero((P['group'] == 0) & (mk == 0))),
                 ('C', '고친 점 · 가장 넓은 모임', np.flatnonzero(P['group'] == 2))]
        if stem == 'R1rep_b10__ALS':
            fb = loadz(TE/'addendum4/places/floor_band.npz', ['point_id'])['point_id']; cases.append(('D', 'R1 바닥 띠 · 본 방법 판과 참값 목표 판', np.flatnonzero(np.isin(P['point_id'], fb) & (P['group'] == 0))))
        for tag, desc, idxs in cases:
            cl = clusters(idxs, X) if tag != 'D' else [idxs]
            if not cl or len(cl[0]) < 3: print('FIG_SKIP', stem, tag, len(idxs), flush=True); continue
            C = cl[0]; j, nm = pick_view(z, C, P, idx)
            if cv is not None:
                key = cv['pt'].astype('i8')*100000+cv['view']; o = np.argsort(key); k2 = z['pt'].astype('i8')*100000+z['view']; pos = np.clip(np.searchsorted(key[o], k2), 0, len(o)-1)
                hit = key[o][pos] == k2; z['gxyz'] = np.where(hit[:, None], cv['gxyz'][o][pos], np.nan)
            else: z['gxyz'] = np.full((len(z['pt']), 3), np.nan)
            rows = 2 if tag == 'D' else 1; fig, axs = plt.subplots(rows, 4, figsize=(18, 4.4*rows), squeeze=False)
            info = dict(figure=None, scene=STEM_KO[stem], case=desc, points=int(len(C)), view=nm, rows={})
            info['rows']['본 방법 판'] = panels(stem, 'ft', P, z, C, j, nm, axs[0, :3], desc); info['rows']['본 방법 판'].update(section(stem, 'ft', P, C, z, j, axs[0, 3], Wt, Tg))
            axs[0, 0].set_ylabel('본 방법 판', fontsize=9)
            if tag == 'D' and has_run(stem, 'gtt') and (O/'pairs'/f'gtt_{stem}.npz').exists():
                zg = loadz(O/'pairs'/f'gtt_{stem}.npz'); cg = contrib_view(stem, 'gtt', P)
                if cg is not None:
                    key = cg['pt'].astype('i8')*100000+cg['view']; o = np.argsort(key); k2 = zg['pt'].astype('i8')*100000+zg['view']; pos = np.clip(np.searchsorted(key[o], k2), 0, len(o)-1)
                    hit = key[o][pos] == k2; zg['gxyz'] = np.where(hit[:, None], cg['gxyz'][o][pos], np.nan)
                else: zg['gxyz'] = np.full((len(zg['pt']), 3), np.nan)
                gs = loadz(GTT/'meshes'/f'{stem}__gtt_s0_base/points.npz', ['reference__s_m'])['reference__s_m'][loadz(WT/'points'/f'wt_{stem}.npz', ['point_id'])['point_id']]
                info['rows']['참값 목표 판'] = panels(stem, 'gtt', P, zg, C, j, nm, axs[1, :3], desc); info['rows']['참값 목표 판'].update(section(stem, 'gtt', P, C, zg, j, axs[1, 3], Wt, Tg, res_s=gs))
                axs[1, 0].set_ylabel('참값 목표 판', fontsize=9)
            from matplotlib.patches import Patch
            fig.legend(handles=[Patch(facecolor=c_, edgecolor='#888', label=l_) for l_, c_ in zip(PCLS, PCOL)], loc='lower center', ncol=6, fontsize=7, title='목표 지도 바탕(화소 소유)', title_fontsize=7)
            fig.suptitle(f'{STEM_KO[stem]} · {desc} · 참값 점 {len(C)}개 · 영상 {nm}', fontsize=10); fig.tight_layout(rect=(0, .07/rows, 1, 1))
            p = FIG/f'tp_{tag}_{stem}.png'; fig.savefig(p, dpi=130); plt.close(fig); info['figure'] = p.name
            info.update(colours=dict(zip(KSHORT, KCOL)), pixel_classes=dict(zip(PCLS, PCOL)), sources=dict(pairs=f'pairs/ft_{stem}.npz', points=f'points/sel_{stem}.npz'), scientific_verdict=None)
            dump(p.with_suffix('.json'), info); print('FIG', p.name, len(C), nm, flush=True)

if __name__ == '__main__': main(sys.argv[1:] or STEMS)
