"""PHD-MAIN-BASE151-v1 5.2 figures, error maps of the GT points seen from above (GTJUDGE environment; /gtjudge = OUT/gt, /b151 = OUT ro).

  python b151_figs.py scenes [run ...]   # 4.1: one figure per scene x prior x result (this task's 2 x 2 run, or the previous building-unit result)
  python b151_figs.py campus [run ...]   # 4.2: one figure per run x prior, the 151 buildings, original cell boundaries drawn
Each figure: left = signed normal-line distance s of the GT points (median per pixel, clipped to +-0.5 m; grey = GT points with no
surface found along the line), right = share of the GT points of the pixel with |s| <= tau of the point (no surface counts as outside).
Pixel 0.25 m (scenes) / 1 m (campus); points drawn from above, so walls show as their footprint lines. The four cases and the scene
(completeness %, n) are written under the maps. Each png has a json beside it (inputs with sha256, rule, counts). GT is used here only
for the score figures. scientific_verdict: null
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import O, dump, now, sha  # noqa: E402

for f in ['/fonts/NotoSansCJK-Regular.ttc', '/fonts/NotoSerifCJK-Regular.ttc']:
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=f).get_name()
        break
plt.rcParams['axes.unicode_minus'] = False

SITES = ['B0_b10', 'R1rep_b10', 'B173nb_b10']
CASES = [(0, '두 자료 모두 유효'), (1, '사전정보 오류'), (2, '영상 깊이 오류'), (4, '영상 깊이 결측'), ('all', '장면 전체')]
PREV = {'2DGS': '2DGS_30000', 'GeoGS': 'GeoGS_30000', 'CDGS': 'CDGS_30000', 'LGDM': 'fusion'}
CELLS = Path('/art/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1/cells/cells.json')
FIG = O / 'figs_b151'
CLIP = 0.5


def priors_of(run):
    m = run.split('_')[1]
    return ['ALS', 'LoD2'] if m == '2DGS' else [run.split('_')[2]]


def raster(xy, s, tau, res, lo, hi):
    nx, ny = int(np.ceil((hi[0] - lo[0]) / res)), int(np.ceil((hi[1] - lo[1]) / res))
    ix = np.clip(((xy[:, 0] - lo[0]) / res).astype(int), 0, nx - 1)
    iy = np.clip(((xy[:, 1] - lo[1]) / res).astype(int), 0, ny - 1)
    flat = iy * nx + ix
    hit = np.isfinite(s)
    within = hit & (np.abs(s) <= tau)
    n = np.bincount(flat, minlength=nx * ny)
    share = np.full(nx * ny, np.nan)
    share[n > 0] = np.bincount(flat, within, nx * ny)[n > 0] / n[n > 0]
    med = np.full(nx * ny, np.nan)
    if hit.any():
        order = np.argsort(flat[hit], kind='stable')
        f, v = flat[hit][order], s[hit][order]
        starts = np.r_[0, np.flatnonzero(f[1:] != f[:-1]) + 1]
        ends = np.r_[starts[1:], len(f)]
        for a, b in zip(starts, ends):   # median per pixel
            med[f[a]] = np.median(v[a:b])
    nosurf = (n > 0) & np.isnan(med)
    return share.reshape(ny, nx), med.reshape(ny, nx), nosurf.reshape(ny, nx), (nx, ny)


def case_rows(s, tau, case):
    out = []
    for c, name in CASES:
        m = np.ones(len(s), bool) if c == 'all' else case == c
        n = int(m.sum())
        w = int((m & np.isfinite(s) & (np.abs(s) <= tau)).sum())
        out.append(dict(case=name, n_gt=n, completeness_pct=100 * w / n if n else None, no_surface=int((m & ~np.isfinite(s)).sum())))
    return out


def draw(path, title, xy, s, tau, case, res, lo, hi, boxes=(), info=None):
    share, med, nosurf, (nx, ny) = raster(xy, s, tau, res, lo, hi)
    rows = case_rows(s, tau, case)
    ext = [lo[0], lo[0] + nx * res, lo[1], lo[1] + ny * res]
    w = 13 if (hi[0] - lo[0]) >= (hi[1] - lo[1]) * .8 else 11
    fig, ax = plt.subplots(1, 2, figsize=(w, 6.6), constrained_layout=True)
    grey = np.where(nosurf, 1.0, np.nan)
    for a in ax:
        a.imshow(grey, origin='lower', extent=ext, cmap='Greys', vmin=0, vmax=2.5, interpolation='nearest')
    im0 = ax[0].imshow(med, origin='lower', extent=ext, cmap='RdBu_r', vmin=-CLIP, vmax=CLIP, interpolation='nearest')
    im1 = ax[1].imshow(np.where(nosurf, np.nan, share), origin='lower', extent=ext, cmap='viridis', vmin=0, vmax=1, interpolation='nearest')
    fig.colorbar(im0, ax=ax[0], shrink=.75, label='법선 측정선 거리 s (m), 화소 중앙값, ±0.5 m에서 자름')
    fig.colorbar(im1, ax=ax[1], shrink=.75, label='|s| ≤ τ 인 참값 점의 몫 (면 없음 = 밖)')
    ax[0].set_title('참값까지의 거리 (회색 = 면을 못 찾은 참값 점)')
    ax[1].set_title('τ 안의 몫')
    for a in ax:
        for (x0, y0), (x1, y1) in boxes:
            a.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color='k', lw=.8)
        a.set_aspect('equal')
        a.set_xlabel('x (m)')
        a.set_ylabel('y (m)')
        a.set_xlim(ext[0], ext[1])
        a.set_ylim(ext[2], ext[3])
    txt = '   '.join(f"{r['case']} {r['completeness_pct']:.1f} % (n {r['n_gt']:,})" if r['completeness_pct'] is not None else f"{r['case']} 없음 (n 0)"
                   for r in rows)
    fig.suptitle(title + '\n완전성: ' + txt, fontsize=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    dump(path.with_suffix('.json'), dict(at=now(), figure=path.name, title=title, pixel_m=res, clip_m=CLIP, extent=ext, cases=rows,
                                         rule='GT points from above; left: median signed normal-line distance per pixel, grey: pixels whose GT points '
                                              'have no surface; right: share of GT points with |s| <= tau (no surface = outside)', **(info or {}),
                                         scientific_verdict=None))
    print('FIG', path.name, flush=True)


def scenes(runs):
    for run in runs:
        method = run.split('_')[1]
        for prior in priors_of(run):
            for site in SITES:
                root = O / 'scenes' / f'{site}__{prior}'
                rw = np.load(root / 'rows.npz')
                case = np.load(root / 'stage1_cells.npz')['case_id']
                box = json.loads((O / 'views' / f'{site}.json').read_text())['box']
                lo, hi = np.array(box[0][:2]), np.array(box[1][:2])
                for fam, label in [(run, '이 작업 2 × 2'), (PREV[method], '앞 작업 건물 단위')]:
                    p = root / 'distances' / f'{fam}.npz'
                    out = FIG / 'scenes' / f'{site}__{prior}__{fam}.png'
                    if not p.exists():
                        print('NO_RESULT', site, prior, fam, flush=True)
                        continue
                    s = np.load(p)['row_s']
                    draw(out, f'{site} · {prior} 참값 · {method} · {label} ({fam})', rw['xyz'][:, :2], s, rw['row_tau_m'], case, .25, lo, hi,
                         info=dict(site=site, prior=prior, method=method, result=fam, version=label,
                                   inputs={str(q): sha(q) for q in [root / 'rows.npz', root / 'stage1_cells.npz', p]}))


def campus(runs):
    cells = json.loads(CELLS.read_text())['cells']
    boxes = [(c['original_min'], c['original_max']) for c in cells]
    for run in runs:
        method = run.split('_')[1]
        for prior in priors_of(run):
            d = O / 'score151' / f'{run}__{prior}'
            if not (d / 'summary.json').exists():
                print('NO_RESULT', run, prior, flush=True)
                continue
            g = np.load(Path('/b151/gt') / f'gt151_{prior}.npz')
            s = np.load(d / 'rows.npz')['s_main']
            xy = g['xyz'][:, :2]
            lo, hi = xy.min(0) - 5, xy.max(0) + 5   # cell outer edges are open (+-1e9 m): extent from the GT points, boxes clipped to it
            boxes_c = [(np.clip(b0, lo, hi), np.clip(b1, lo, hi)) for b0, b1 in boxes]
            draw(FIG / 'campus' / f'campus__{prior}__{run}.png', f'캠퍼스 151동 · {prior} 참값 · {method} · {run} (점이 든 칸의 메시, 검은 선 = 원래 칸 경계)',
                 xy, s, g['tau'], g['case'], 1.0, lo, hi, boxes=boxes_c,
                 info=dict(run=run, prior=prior, method=method, buildings_with_gt=int(len(np.unique(g['building']))),
                           per_cell=[dict(cell=k, n_gt=int((g['point_cell'] == k).sum()),
                                          median_s_m=float(np.median(s[(g['point_cell'] == k) & np.isfinite(s)])) if ((g['point_cell'] == k) & np.isfinite(s)).any() else None,
                                          completeness_pct=float(100 * ((g['point_cell'] == k) & np.isfinite(s) & (np.abs(s) <= g['tau'])).sum() / max(int((g['point_cell'] == k).sum()), 1)))
                                     for k in range(4)],
                           inputs={str(q): sha(q) for q in [Path('/b151/gt') / f'gt151_{prior}.npz', d / 'rows.npz']}))


if __name__ == '__main__':
    a = sys.argv[1:]
    dict(scenes=scenes, campus=campus)[a[0]](a[1:])
