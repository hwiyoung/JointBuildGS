"""Gaussian growth of 판 다 cells against FINALTRAIN scenes (user question 2026-11-12: is it only cell 0, or every cell?).

Facts only, from existing run records (no training):
  - count curve (target_monitor/curve.jsonl, every 100 iterations; resumed attempts joined by iteration, later attempt wins)
  - images, iterations per image, seeds / prior seeds (initialization.json), scene extent (fork rule: 1.1 x max distance of
    training camera centres from their mean; it scales the position learning rate and the clone/split/prune size limits)
  - Gaussians at the saved iteration-7000 point cloud: occupied 1 m xy grid cells, Gaussians per occupied m2,
    share inside the original cell bounds (cells) or inside the evaluation box (FINALTRAIN)

  python tu_growth.py
Writes tables/cells_growth.* and figures/cells_growth.png|json.
"""
import csv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

from tu_common import *

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'axes.unicode_minus': False, 'font.size': 9})
COL = ['#0072b2', '#e69f00', '#009e73', '#cc79a7']
MARK = [1, 3000, 6000, 7000, 9000, 12000, 13000, 14000, 15000, 30000]


def ply_xy(p):
    with open(p, 'rb') as f:
        hdr = b''
        while not hdr.endswith(b'end_header\n'):
            hdr += f.readline()
    lines = hdr.decode().splitlines()
    assert 'format binary_little_endian 1.0' in lines
    n = int(next(l for l in lines if l.startswith('element vertex')).split()[2])
    props = [l.split() for l in lines if l.startswith('property')]
    kind = {'float': '<f4', 'int': '<i4'}
    assert all(q[1] in kind for q in props)
    mm = np.memmap(p, dtype=np.dtype([(q[2], kind[q[1]]) for q in props]), mode='r', offset=len(hdr), shape=(n,))
    return n, np.asarray(mm['x'], float), np.asarray(mm['y'], float), np.asarray(mm['origin'])


def lineage(attempt_dirs):
    rows, peak = {}, 0
    for a in attempt_dirs:
        f = a / 'model/target_monitor/curve.jsonl'
        if f.exists():
            for l in f.read_text().splitlines():
                if l.strip():
                    r = json.loads(l)
                    rows[r['iteration']] = r
        t = a / 'model/jbgs_trace.jsonl'
        if t.exists():
            for l in t.read_text().splitlines():
                if l.strip():
                    peak = max(peak, json.loads(l).get('peak_cuda_reserved_bytes') or 0)
    its = sorted(rows)
    return its, [rows[i]['gaussians'] for i in its], peak


def extent(model, train):
    cams = [c for c in json.loads((model / 'cameras.json').read_text()) if c['img_name'] in set(train)]
    P = np.array([c['position'] for c in cams], float)
    return 1.1 * float(np.linalg.norm(P - P.mean(0), axis=1).max()), len(cams)


def density(ply, lo, hi):
    n, x, y, origin = ply_xy(ply)
    cells = np.unique(np.stack([np.floor(x), np.floor(y)], 1), axis=0)
    inside = (x >= lo[0]) & (x < hi[0]) & (y >= lo[1]) & (y < hi[1])
    cin = np.unique(np.stack([np.floor(x[inside]), np.floor(y[inside])], 1), axis=0)
    prior = origin == 1  # fork: origin 1 = prior-seed lineage (descendants keep it), 0 = image/background lineage
    return dict(gaussians_7000_ply=n, occupied_m2_7000=len(cells), gaussians_per_occupied_m2_7000=n / len(cells),
                share_inside_bounds_7000=float(inside.mean()), occupied_m2_inside_7000=len(cin),
                gaussians_per_occupied_m2_inside_7000=float(inside.sum()) / len(cin) if len(cin) else None,
                prior_lineage_7000=int(prior.sum()), share_prior_lineage_7000=float(prior.mean()),
                prior_lineage_per_occupied_m2_7000=float(prior.sum()) / len(cells),
                background_lineage_per_occupied_m2_7000=float((~prior).sum()) / len(cells))


def main():
    cfg()
    cells = json.loads((TU / 'cells/cells.json').read_text())
    boxes = {b['site']: b for b in cells['evaluation_boxes']}
    rows, curves = [], {}

    def add(label, unit, prior, attempt_dirs, train, bounds_name, lo, hi):
        attempt_dirs = [a for a in attempt_dirs if (a / 'model').exists()]
        its, g, peak = lineage(attempt_dirs)
        first = attempt_dirs[0] / 'model'
        init = json.loads((first / 'target_monitor/initialization.json').read_text())
        ext, ncam = extent(first, train)
        at = dict(zip(its, g))
        n6 = at.get(6000)
        r = dict(label=label, unit=unit, prior=prior, train_images=len(train), iterations_per_image=30000 / len(train),
                 seeds=init['seeds'], prior_seeds=init['prior_seeds'], scene_extent_m=ext, last_iteration=its[-1] if its else None,
                 **{f'gaussians_{m}': at.get(m) for m in MARK},
                 max_gaussians_7000_15000=max([v for i, v in zip(its, g) if 7000 <= i <= 15000], default=None),
                 ratio_max_to_6000=(max([v for i, v in zip(its, g) if 7000 <= i <= 15000], default=0) / n6) if n6 else None,
                 peak_reserved_GiB=peak / 2**30 if peak else None, bounds=bounds_name)
        ply = first / 'point_cloud/iteration_7000/point_cloud.ply'
        if ply.exists():
            r.update(density(ply, lo, hi))
        rows.append(r)
        curves[f'{label}|{unit}|{prior}'] = dict(iterations=its, gaussians=g)
        print(label, unit, prior, r.get('gaussians_6000'), r.get('max_gaussians_7000_15000'), flush=True)

    for site in SITES:
        train = json.loads((S0 / 'fork_inputs/s61' / site / 'split.json').read_text())['train']
        b = boxes[site]
        for prior in PRIORS:
            add('기준', site, prior, [FT / 'runs' / site / f'ft_{prior}_s0/attempt1'], train, 'evaluation box', b['box_min'], b['box_max'])
    for c in cells['cells']:
        for prior in PRIORS:
            run = TU / 'runs/cells' / f'cells_{prior}_s0' / f'cell{c["id"]}'
            atts = sorted(run.glob('attempt*'), key=lambda p: int(p.name[7:]))
            if not atts or not (atts[0] / 'model/target_monitor/initialization.json').exists():
                continue
            add('다', f'cell{c["id"]}', prior, atts, c['images'], 'original cell bounds', c['original_min'], c['original_max'])
    camp = TU / 'runs/campus/campus30k_ALS_s0/attempt1'
    if (camp / 'model/target_monitor/initialization.json').exists():
        split = json.loads((TU / 'scenes/campus/split.json').read_text())['train']
        add('가', 'campus', 'ALS', [camp], split, 'none', [-1e9, -1e9], [1e9, 1e9])

    out = D / 'tables/cells_growth'
    dump(out.with_suffix('.json'), dict(rows=rows, note='facts from run records; no training; scientific_verdict null',
         sources=['target_monitor/curve.jsonl', 'jbgs_trace.jsonl', 'initialization.json', 'cameras.json', 'point_cloud/iteration_7000'],
         scientific_verdict=None))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with out.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    with out.with_suffix('.md').open('w') as f:
        f.write('| ' + ' | '.join(fields) + ' |\n| ' + ' | '.join('---' for _ in fields) + ' |\n')
        for r in rows:
            f.write('| ' + ' | '.join('' if r.get(k) is None else (f'{r[k]:.3f}' if isinstance(r.get(k), float) else str(r[k])) for k in fields) + ' |\n')

    fig, ax = plt.subplots(1, 3, figsize=(16, 5))
    for key, cv in curves.items():
        label, unit, prior = key.split('|')
        it, g = np.array(cv['iterations']), np.array(cv['gaussians']) / 1e6
        if label == '기준':
            kw = dict(color='0.6', lw=0.8, label='기준 (FINALTRAIN 여섯 판)' if 'base' not in curves[key] else None)
        elif label == '다':
            kw = dict(color=COL[int(unit[4:])], lw=1.4, ls='-' if prior == 'ALS' else '--', label=f'다 {unit} {prior}')
        else:
            kw = dict(color='k', lw=1.2, ls=':', label='가 캠퍼스 ALS')
        ax[0].plot(it, g, **kw)
        n6 = dict(zip(cv['iterations'], cv['gaussians'])).get(6000)
        if n6:
            m = it >= 6000
            ax[1].plot(it[m], g[m] * 1e6 / n6, **kw)
    h, l = ax[0].get_legend_handles_labels()
    keep = dict(zip(l, h))
    ax[0].legend(keep.values(), keep.keys(), fontsize=7)
    ax[0].set(xlabel='반복', ylabel='가우시안 (백만)', title='가우시안 수')
    ax[1].axhline(3, color='r', lw=0.8)
    ax[1].text(7000, 3.05, '건강 규칙 문턱 (6,000회 수의 3배)', color='r', fontsize=8)
    ax[1].axvspan(7000, 15000, color='0.93', zorder=0)
    ax[1].set(xlabel='반복', ylabel='6,000회 수 대비', title='6,000회 수 대비 배율 (회색 = 점검 구간)')
    d = [r for r in rows if r.get('occupied_m2_inside_7000')]
    for dens in [10, 20, 40]:
        xs = np.linspace(0, 65000, 50)
        ax[2].plot(xs / 1e3, xs * dens / 1e6, color='0.85', lw=0.8, zorder=0)
        ax[2].text(62, 62000 * dens / 1e6, f'{dens}/m²', color='0.5', fontsize=7, ha='right', va='bottom')
    for r in d:
        x = r['occupied_m2_inside_7000'] / 1e3
        y = r['share_inside_bounds_7000'] * r['gaussians_7000_ply'] / 1e6
        c = '0.5' if r['label'] == '기준' else COL[int(r['unit'][4:])]
        ax[2].scatter([x], [y], color=c, s=30, zorder=3)
        if r['label'] != '기준':
            ax[2].annotate(f'다 {r["unit"]} {r["prior"]}', (x, y), fontsize=8, xytext=(3, 3), textcoords='offset points')
    ax[2].annotate('기준 여섯 판 (평가 상자 안)', (9, 0.2), fontsize=8, xytext=(14, 0.45), arrowprops=dict(arrowstyle='->', color='0.5'))
    ax[2].set(xlim=(0, 65), ylim=(0, 3.0), xlabel='차지한 넓이 (천 m², 1 m 칸; 기준 = 평가 상자 안, 다 = 원래 칸 경계 안)',
              ylabel='그 안의 가우시안 (백만)', title='7,000회: 넓이 × 밀도 (회색 선 = 같은 밀도)')
    fig.tight_layout()
    png = D / 'figures/cells_growth.png'
    fig.savefig(png, dpi=130)
    dump(png.with_suffix('.json'), dict(figure=str(png.name), table='tables/cells_growth.json', curves=curves,
         panels=['count vs iteration', 'count / count at 6000 (rule threshold 3)', 'iteration 7000: occupied 1 m cells inside own bounds (FINALTRAIN: evaluation box) vs Gaussians inside'],
         scientific_verdict=None))
    print('DONE', len(rows), flush=True)


if __name__ == '__main__':
    main()
