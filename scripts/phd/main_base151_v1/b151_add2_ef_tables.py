"""PHD-MAIN-BASE151-v1 addendum 2 item 1-7 tables and map (GTJUDGE environment; /gtjudge = OUT/gt; writes /gtjudge/add2/).
Cell 3 only (GT rows with point_cell 3 = the rows scored on the cell-3 unit meshes; samples inside the original cell-3 rectangle), ALS GT:
the four cases + scene (b151_tables42.block, the 4.2 rule), flat roof s median for the cell and per building (flat roof >= 200 rows), for
a2_JBGSef_ALS (TRAINUNIT-v2 cellsef_ALS_s0 cell 3, no new training) and b151_2DGS_s0, b151_GeoGS_ALS_s0, b151_LGDM_ALS.

  python b151_add2_ef_tables.py
scientific_verdict: null
"""
import sys

import numpy as np

sys.path.insert(0, '/b151s')
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import b151_tables42 as T42  # noqa: E402
from b151_add2 import A, dump, table  # noqa: E402
from b151_add1 import in_cell  # noqa: E402
import b151_common as BC  # noqa: E402

RUNS = [('본 방법(cellsef_ALS_s0, 칸 3)', 'a2_JBGSef_ALS'), ('2DGS', 'b151_2DGS_s0'), ('GeoGS', 'b151_GeoGS_ALS_s0'), ('LGDM', 'b151_LGDM_ALS')]


def main():
    BC.cfg('score151')
    g = dict(np.load(BC.B / 'gt' / 'gt151_ALS.npz'))
    names, code = np.unique(g['building'], return_inverse=True)
    g['bcode'] = code
    r3 = g['point_cell'] == 3
    flat = (~g['wall']) & (g['normal'][:, 2] >= .985) & (g['case'] == 0)
    rows, blds, maps = [], {}, {}
    for label, run in RUNS:
        z = T42.load(run, 'ALS', g)
        if z is None:
            rows.append(dict(method=label, run=run, status='결과 없음')); continue
        s3 = in_cell(np.load(T42.O / 'score151' / f'{run}__ALS' / 'samples.npz')['sample_xyz'][:, :2].astype(float), 3)
        b = T42.block(z, g, r3, s3)
        miss = int((r3 & ~z['covered']).sum())
        fs = z['s_main'][r3 & flat]
        r = dict(method=label, run=run, status='있음', cell3_rows_not_covered=miss)
        r.update(T42.flat(b))
        r.update(flat_roof_rows=int((r3 & flat).sum()), flat_roof_s_finite=int(np.isfinite(fs).sum()),
                 flat_roof_s_median=float(np.nanmedian(fs)) if np.isfinite(fs).any() else None)
        rows.append(r)
        for i in np.unique(code[r3 & flat]):
            m = r3 & flat & (code == i)
            if m.sum() < 200:
                continue
            v = z['s_main'][m]
            blds.setdefault(names[i], dict(building=names[i], flat_roof_rows_in_cell3=int(m.sum())))[f's_median_{label}'] = \
                float(np.nanmedian(v)) if np.isfinite(v).any() else None
        maps[label] = z['s_main']
    table('a2_17_cell3', rows, '1-7: cell 3 (GT rows with point_cell 3, samples inside the original cell-3 rectangle), ALS GT, the 4.2 rule (b151_tables42.block): '
          'completeness / accuracy % per case and scene; flat roof (not wall, n_z >= 0.985, case 0) s median over finite s. The main-method model is the '
          'TRAINUNIT-v2 cellsef_ALS_s0 cell 3 (not the final run; its target files were not made from the 151-building judgement); only whether the '
          'surfaces float is looked at')
    table('a2_17_buildings', sorted(blds.values(), key=lambda r: r['building']), '1-7: per building, flat roof rows of cell 3 >= 200: s median (m) per method')
    # map of cell 3 like the campus map: GT rows of cell 3 seen from above, tau in / out
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from pathlib import Path
    for f in Path('/fonts').rglob('NotoSansCJK*.ttc'):
        font_manager.fontManager.addfont(str(f))
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    xy = g['xyz'][r3, :2]; tau = g['tau'][r3]
    fig, ax = plt.subplots(1, len(maps), figsize=(6 * len(maps), 6.4), sharex=True, sharey=True)
    for a, (label, s) in zip(np.atleast_1d(ax), maps.items()):
        v = s[r3]
        col = np.where(~np.isfinite(v), '#999999', np.where(np.abs(v) <= tau, '#f0f0f0', np.where(v < 0, '#2166ac', '#b2182b')))
        o = np.argsort(np.isfinite(v) & (np.abs(v) <= tau))[::-1]
        a.scatter(xy[o, 0], xy[o, 1], s=.3, c=col[o], rasterized=True)
        a.set_facecolor('#d9d9d9')
        w = 100 * float((np.isfinite(v) & (np.abs(v) <= tau)).mean())
        a.set_title(f'{label}\n칸 3 τ 안 {w:.1f} %'); a.set_aspect('equal')
    fig.suptitle('칸 3 참값 점(ALS) 위에서 본 τ 안/밖 · 흰색 τ 안 / 파랑 −τ보다 작음 / 빨강 +τ보다 큼 / 회색 면 없음')
    fig.tight_layout(rect=(0, 0, 1, .9))
    (A / 'figures').mkdir(parents=True, exist_ok=True)
    fig.savefig(A / 'figures' / 'a2_17_cell3_map.png', dpi=110, facecolor='white'); plt.close(fig)
    dump(A / 'figures' / 'a2_17_cell3_map.json', dict(item='1-7', runs=[r for _, r in RUNS], rows=int(r3.sum()),
                                                     crs='EPSG:25832; local XY = EPSG:25832 - [690953, 5336071]', scientific_verdict=None))
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
