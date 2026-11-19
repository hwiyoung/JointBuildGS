"""PHD-MAIN-BASE151-v1 addendum 1 figures (GTJUDGE environment; writes /gtjudge/add1/figs/<name>.png + .json).

  python b151_add1_figs.py all
  maps__<run>       s of the GT points (median per 1 m pixel, +-1 m) in cell 2 and cell 3 side by side
  scatter__<run>    s vs x, y, height of the GT points of cell 3 (2-D histograms, |s| <= 2 m)
  buildings         per building median s on flat roofs, cell 3 vs cells 0-2 vs the bottom band, per run
  section           one flat roof of cell 3 (the building with the most flat case-0 GT points): GT points, the prior (ALS TIN vertices),
                    campus MVS points of the nearest nadir view, and the 4.2 unit meshes of the runs, in a 0.25 m band along x
GT is used for scoring and figures only. scientific_verdict: null
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

sys.path.insert(0, '/b151s')
import b151_add1 as X  # noqa: E402

for f in Path('/fonts').rglob('*CJK*'):
    font_manager.fontManager.addfont(str(f))
plt.rcParams['font.family'] = [font_manager.FontProperties(fname=str(next(Path('/fonts').rglob('NotoSansCJK-Regular*')))).get_name()] if list(Path('/fonts').rglob('NotoSansCJK-Regular*')) else plt.rcParams['font.family']
plt.rcParams['axes.unicode_minus'] = False
F = X.A / 'figs'
RUNS = [('b151_2DGS_s0', 'ALS'), ('b151_GeoGS_ALS_s0', 'ALS'), ('b151_LGDM_ALS', 'ALS')]


def save(fig, name, info):
    F.mkdir(parents=True, exist_ok=True)
    fig.savefig(F / f'{name}.png', dpi=120)
    plt.close(fig)
    X.dump(F / f'{name}.json', dict(figure=f'{name}.png', **info, scientific_verdict=None))
    print('FIG', name, flush=True)


def rows(run, prior):
    g, n = X.gt(prior)
    return g, n, np.load(X.O / 'score151' / f'{run}__{prior}' / 'rows.npz')['s_main']


def raster(xy, v, res):
    lo, hi = xy.min(0), xy.max(0) + res
    nx, ny = np.ceil((hi - lo) / res).astype(int)
    ix, iy = ((xy - lo) / res).astype(int).T
    flat = iy * nx + ix
    o = np.argsort(flat, kind='stable')
    f, vv = flat[o], v[o]
    out = np.full(nx * ny, np.nan)
    st = np.r_[0, np.flatnonzero(f[1:] != f[:-1]) + 1]
    en = np.r_[st[1:], len(f)]
    for a, b in zip(st, en):
        out[f[a]] = np.median(vv[a:b])
    return out.reshape(ny, nx), [lo[0], lo[0] + nx * res, lo[1], lo[1] + ny * res]


def maps():
    for run, prior in RUNS:
        g, n, s = rows(run, prior)
        fig, ax = plt.subplots(1, 2, figsize=(14, 7), constrained_layout=True)
        info = dict(run=run, prior=prior, pixel_m=1.0, clip_m=1.0, cells={})
        for a, k in zip(ax, [2, 3]):
            m = X.in_cell(g['xyz'][:, :2], k) & np.isfinite(s)
            img, ext = raster(g['xyz'][m, :2], s[m], 1.0)
            im = a.imshow(img, origin='lower', extent=ext, cmap='RdBu_r', vmin=-1, vmax=1, interpolation='nearest')
            st = X.stats(s[m])
            a.set_title(f'칸 {k}: s 중앙값 {st["median"]:+.2f} m (n {st["n"]:,})')
            a.set_aspect('equal')
            a.set_xlabel('x (m)')
            a.set_ylabel('y (m)')
            info['cells'][k] = st
        fig.colorbar(im, ax=ax, shrink=.7, label='s (m), 화소 중앙값, ±1 m에서 자름 (+ = 면이 참값 위)')
        fig.suptitle(f'{run} · {prior} 참값 · 칸 2와 칸 3 (4.2 단위 메시, 점이 든 칸의 메시)')
        save(fig, f'maps__{run}__{prior}', info)


def scatter():
    for run, prior in RUNS:
        g, n, s = rows(run, prior)
        m = X.in_cell(g['xyz'][:, :2], 3) & np.isfinite(s) & (np.abs(s) <= 2)
        fig, ax = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
        for a, j, lab in zip(ax, [0, 1, 2], ['x (m)', 'y (m)', '높이 z (m)']):
            a.hist2d(g['xyz'][m, j], s[m], bins=[120, 120], cmap='magma_r', cmin=1, norm=matplotlib.colors.LogNorm())
            a.axhline(0, color='k', lw=.6)
            a.set_xlabel(lab)
            a.set_ylabel('s (m)')
        fig.suptitle(f'{run} · {prior} 참값 · 칸 3의 참값 점 s 대 x, y, 높이 (|s| ≤ 2 m, n {int(m.sum()):,})')
        save(fig, f'scatter__{run}__{prior}', dict(run=run, prior=prior, n=int(m.sum()), excluded_no_surface_or_abs_s_gt_2=int((X.in_cell(g['xyz'][:, :2], 3) & ~m).sum())))


def buildings():
    b = json.loads((X.A / 'b_buildings.json').read_text())['rows']
    g, n = X.gt('ALS')
    xy = g['xyz'][:, :2]
    names, code = np.unique(g['building'], return_inverse=True)
    band = {str(names[i]): bool(np.median(xy[code == i, 1]) < -150) for i in range(len(names))}
    fig, ax = plt.subplots(1, len(RUNS), figsize=(16, 4.8), constrained_layout=True, sharey=True)
    info = {}
    for a, (run, prior) in zip(ax, RUNS):
        r = [x for x in b if x['run'] == run and x['prior'] == prior and x['flat_s_median'] is not None and x['flat_points'] >= 200]
        groups = {'칸 3': [x['flat_s_median'] for x in r if x['cell_of_most_points'] == 3],
                  '칸 0~2 (띠 밖)': [x['flat_s_median'] for x in r if x['cell_of_most_points'] != 3 and not band.get(x['building'])],
                  '아래쪽 띠 (y < −150 m)': [x['flat_s_median'] for x in r if band.get(x['building'])]}
        bins = np.linspace(-1, 3, 41)
        for lab, v in groups.items():
            a.hist(np.clip(v, -1, 3), bins=bins, histtype='step', lw=1.6, label=f'{lab} ({len(v)}동)')
        a.axvline(0, color='k', lw=.6)
        a.set_title(run)
        a.set_xlabel('건물별 평평한 지붕 s 중앙값 (m, −1~3에서 자름)')
        a.legend(fontsize=8)
        info[run] = {lab: dict(buildings=len(v), median=float(np.median(v)) if v else None, p10=X.q(np.array(v), 10), p90=X.q(np.array(v), 90)) for lab, v in groups.items()}
    ax[0].set_ylabel('건물 수')
    fig.suptitle('건물별 평평한 지붕(기울기 ≤ 10°) s 중앙값의 분포, 평평한 참값 점 200개 이상인 건물 (항공 LiDAR 참값)')
    save(fig, 'buildings', dict(rule='building cell = the cell holding most of its GT points; band = building median y < -150 m', groups=info))


def section():
    b = json.loads((X.A / 'b_buildings.json').read_text())['rows']
    pick = max((x for x in b if x['run'] == 'b151_2DGS_s0' and x['prior'] == 'ALS' and x['cell_of_most_points'] == 3), key=lambda x: x['flat_points'])['building']
    g, n = X.gt('ALS')
    fm = X.flat_mask(g, n) & (g['building'] == pick)
    P = g['xyz'][fm]
    c = np.median(P, 0)
    y0 = c[1]
    band = .25
    x0, x1 = P[:, 0].min() - 5, P[:, 0].max() + 5
    sel = lambda xyz: (np.abs(xyz[:, 1] - y0) <= band) & (xyz[:, 0] >= x0) & (xyz[:, 0] <= x1)
    fig, ax = plt.subplots(figsize=(15, 5.5), constrained_layout=True)
    info = dict(building=pick, line=f'y = {y0:.2f} m, x {x0:.1f}..{x1:.1f} m, band +-{band} m', layers={})
    gg = g['xyz'][sel(g['xyz'])]
    ax.scatter(gg[:, 0], gg[:, 2], s=2, c='k', label=f'참값 점 (항공 LiDAR 참값, {len(gg):,})', zorder=5)
    info['layers']['GT'] = len(gg)
    pr = np.load(X.B / 'prior/cell3/als_mesh.npz')
    V = pr[[k for k in pr.files if k.lower().startswith('v')][0]]
    pv = V[sel(V)]
    ax.scatter(pv[:, 0], pv[:, 2], s=6, c='tab:green', marker='^', label=f'사전정보 (항공 LiDAR TIN 꼭짓점, {len(pv):,})', zorder=4)
    info['layers']['prior_vertices'] = len(pv)
    # MVS: the nadir training view of cell 3 whose camera is nearest in xy to the roof centre
    split = json.loads((X.TU1 / 'scenes/cell3/split.json').read_text())
    im = X.colmap_images(X.B / 'scenes/2DGS/cell3/sparse/0/images.bin')
    best = min((nm for nm in split['train'] if np.degrees(np.arccos(np.clip(-im[nm][0][2, 2], -1, 1))) <= 5), key=lambda nm: np.linalg.norm(im[nm][1][:2] - c[:2]))
    R, C = im[best]
    dm = X.read_depth_bin(X.MVSD / f'{best}.JPG.geometric.bin')
    ok = np.isfinite(dm) & (dm > 0)
    K = np.array([[674.4174327342674, 0, 513.4158321884543], [0, 674.7782004194731, 365.0968300765191], [0, 0, 1]])
    yy, xx = np.mgrid[0:dm.shape[0], 0:dm.shape[1]]
    Xc = np.stack([(xx[ok] - K[0, 2]) / K[0, 0] * dm[ok], (yy[ok] - K[1, 2]) / K[1, 1] * dm[ok], dm[ok]], 1)
    Xw = Xc @ R + C
    mv = Xw[sel(Xw)]
    ax.scatter(mv[:, 0], mv[:, 2], s=3, c='tab:orange', label=f'캠퍼스 MVS ({best}, {len(mv):,})', zorder=3)
    info['layers']['mvs'] = dict(view=best, points=len(mv))
    colors = {'b151_2DGS_s0': 'tab:red', 'b151_GeoGS_ALS_s0': 'tab:purple', 'b151_LGDM_ALS': 'tab:blue'}
    for run, _ in RUNS:
        hit = None
        for rp in (X.O / 'renders').glob(f'c3_*__ALS__{run}/receipt.json'):
            bx = np.array(json.loads(rp.read_text())['box'])
            if np.all((c[:2] >= bx[0][:2]) & (c[:2] <= bx[1][:2])):
                hit = rp.parent.name
        if hit is None:
            continue
        mv_, _ = X.read_ply(X.O / 'meshes' / hit / 'final.ply', ['x', 'y', 'z'])
        M = np.stack([mv_['x'], mv_['y'], mv_['z']], 1).astype(float)
        mm = M[(np.abs(M[:, 1] - y0) <= .1) & (M[:, 0] >= x0) & (M[:, 0] <= x1)]
        ax.scatter(mm[:, 0], mm[:, 2], s=3, c=colors[run], label=f'{run} 4.2 단위 메시 꼭짓점 ({hit.split("__")[0]}, ±0.1 m, {len(mm):,})', zorder=2)
        info['layers'][run] = dict(unit=hit, vertices=len(mm))
    zr = np.percentile(gg[:, 2], [2, 98]) if len(gg) else [c[2] - 5, c[2] + 5]
    ax.set_ylim(zr[0] - 3, zr[1] + 3)
    ax.set_xlabel('x (m)')
    ax.set_ylabel('z (m)')
    ax.legend(fontsize=8, loc='upper right', markerscale=3)
    ax.set_title(f'칸 3 평평한 지붕 단면 · {pick} · y = {y0:.1f} m (±{band} m 띠)')
    save(fig, 'section', info)


if __name__ == '__main__':
    X.A.mkdir(parents=True, exist_ok=True)
    for f in ([maps, scatter, buildings, section] if sys.argv[1] == 'all' else [globals()[sys.argv[1]]]):
        f()
