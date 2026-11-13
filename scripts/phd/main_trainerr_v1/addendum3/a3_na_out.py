"""Work na outputs: tables (per model x view x pixel class: accumulated opacity, rendered depth - target, median depth - target, weight per depth bin
and per bin x constraint state; re-implementation check) and figures (per view: four bin-weight maps + rendered depth - target, one row per model). CPU."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
from a3_na import NA, VIEWS, MODELS, BINS, CLASSES
BIN_KO = {'front': '목표 앞 (1 m 넘게 가까움)', 'target': '목표 ±1 m', 'behind_near': '목표 뒤 1~5 m', 'behind_far': '목표 뒤 5 m 넘게'}
CLS_KO = {'front': '앞에 다른 것', 'same': '같음', 'none': '영상 깊이 없음', 'behind': '뒤(1 m 넘게)'}

def tables():
    rows = []; chk = []
    for m in MODELS:
        for v in VIEWS:
            f = NA/f'{m}__{v}.npz'
            if not f.exists(): continue
            z = loadz(f); j = json.loads(f.with_suffix('.json').read_text()); chk.append(dict(model=m, view=v, pixels=j['pixels'], **j['check']))
            for ci, cn in enumerate(CLASSES):
                k = z['cls'] == ci
                if not k.any(): continue
                w = z['w'][k]; acc = z['acc'][k]; r = dict(model=m, view=v, pixel_class=cn, pixels=int(k.sum()), acc_median=med(acc), depth_mean_minus_target_median_m=med(z['depth_mean'][k]-z['target'][k]),
                                                          depth_median_minus_target_median_m=med(np.where(z['depth_median'][k] > 0, z['depth_median'][k]-z['target'][k], np.nan)), contributors_median=med(z['contributors'][k]))
                for bi, bn in enumerate(BINS):
                    r[f'w_{bn}_median'] = med(w[:, bi, :].sum(1)); r[f'w_{bn}_mean'] = float(w[:, bi, :].sum(1).mean())
                    for si, sn in enumerate(STATE_NAMES): r[f'w_{bn}_{sn}_mean'] = float(w[:, bi, si].mean())
                rows.append(r)
    ctable('na_bins', rows); ctable('na_check', chk); print('NA_TABLES', len(rows), flush=True)

def figures():
    plt = korean_plt(); FIG = A3D/'figures'
    for v in VIEWS:
        ms = [m for m in MODELS if (NA/f'{m}__{v}.npz').exists()]
        if not ms: continue
        fig, axs = plt.subplots(len(ms), 6, figsize=(24, 4.2*len(ms)), dpi=100, squeeze=False); srcs = []
        for i, m in enumerate(ms):
            z = loadz(NA/f'{m}__{v}.npz'); px, py = z['px'].astype(int), z['py'].astype(int); x0, x1, y0, y1 = px.min()-8, px.max()+9, py.min()-8, py.max()+9; srcs.append(str(NA/f'{m}__{v}.npz'))
            def img(val):
                a = np.full((y1-y0, x1-x0), np.nan, 'f4'); a[py-y0, px-x0] = val; return a
            cl = img(z['cls'].astype('f4')); axs[i, 0].imshow(cl, cmap=matplotlib_cmap(), vmin=-.5, vmax=3.5, interpolation='nearest'); axs[i, 0].set_title(f'{m}: 화소 분류', fontsize=9)
            for bi, bn in enumerate(BINS):
                im = axs[i, bi+1].imshow(img(z['w'][:, bi, :].sum(1)), cmap='magma', vmin=0, vmax=1, interpolation='nearest'); axs[i, bi+1].set_title(f'가중치: {BIN_KO[bn]}', fontsize=9)
            fig.colorbar(im, ax=axs[i, 4], fraction=.046)
            im2 = axs[i, 5].imshow(img(z['depth_mean']-z['target']), cmap='RdBu_r', vmin=-10, vmax=10, interpolation='nearest'); axs[i, 5].set_title('렌더링 깊이 − 목표 깊이 (m)', fontsize=9); fig.colorbar(im2, ax=axs[i, 5], fraction=.046)
            for ax in axs[i]: ax.set_xticks([]); ax.set_yticks([])
        hs = [plt.Line2D([], [], color=c, marker='s', ls='', label=CLS_KO[k]) for k, c in zip(CLASSES, ['#D62728', '#2CA02C', '#7F8C8D', '#1F5FD6'])]
        fig.legend(handles=hs, loc='lower left', ncol=4, fontsize=9); fig.suptitle(v, fontsize=11); fig.tight_layout(rect=(0, .03, 1, .97))
        p = FIG/f'na_maps_{v}.png'; fig.savefig(p, facecolor='white'); plt.close(fig)
        dump(p.with_suffix('.json'), dict(at=now(), figure=p.name, view=v, models=ms, sources=srcs, crop='bounding box of the south-wall target pixels +- 8 px', bins=BIN_KO, scientific_verdict=None))
    print('NA_FIGURES', flush=True)

def matplotlib_cmap():
    from matplotlib.colors import ListedColormap
    return ListedColormap(['#D62728', '#2CA02C', '#7F8C8D', '#1F5FD6'])

if __name__ == '__main__':
    {'tables': tables, 'figures': figures}[sys.argv[1]]()
