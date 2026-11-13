"""Addendum 14 part A: Gaussians per training image, per seed point and per seed-occupied area of the elongation-filter runs,
the peak-memory line, and predictions for the cellsef cells and the campus written before any cellsef cell starts. No GT read.

  python tu_density.py measure     -> tables/density_units.*, density_ratios.*, density_memory.*, density_predictions.*
  python tu_density.py check       -> tables/density_check.*   (after the cellsef cells: measured vs predicted)
"""
import sys

from tu_common import *
from tu_cause import write

A14 = C / 'addendum14.json'
RUNS = [  # (filter run, unit, seeds file)
    ('cell0ef_ALS_s0', 'cell0', TU / 'stage1/cell0__ALS/seeds.npz'),
    ('probe3ef_ALS_s0', 'probe3', TU / 'stage1/probe3__ALS/seeds.npz'),
    ('probe4ef_ALS_s0', 'probe4', TU / 'stage1/probe4__ALS/seeds.npz'),
    ('B0ef_ALS_s0', 'B0', FT / 'stage1/B0_b10__ALS/seeds.npz'),
    ('B0ef_ALS_s1', 'B0', FT / 'stage1/B0_b10__ALS/seeds.npz'),
]
GRID = 2.0
RATIOS = [('per_image', 'images'), ('per_seed_point', 'seed_points'), ('per_occupied_m2', 'occupied_m2')]


def locked():
    assert sha(A14) == json.loads((C / 'addendum14.lock.json').read_text())['sha256'], 'addendum 14 changed after lock'


def seeds(p):
    s = loadz(p, ['xyz', 'origin'])
    sq = np.unique(np.floor(s['xyz'][:, :2] / GRID).astype(np.int64), axis=0)
    return dict(seed_points=int(len(s['origin'])), prior_seeds=int((s['origin'] == 1).sum()), background_seeds=int((s['origin'] == 0).sum()),
                occupied_m2=float(len(sq) * GRID ** 2))


def trace(model):
    t = [json.loads(l) for l in (model / 'jbgs_trace.jsonl').read_text().splitlines() if l.strip()]
    at = {x['iteration']: x['gaussians'] for x in t}
    return at.get(15000), max(at.values()), max(x['peak_cuda_reserved_bytes'] for x in t) / 2 ** 30, max(at)


def measure():
    locked()
    rows = []
    for run, unit, sp in RUNS:
        att = TU / 'runs/ef' / run / 'attempt1'
        g15, gmax, peak, last = trace(att / 'model')
        cams = json.loads((att / 'extent_override.json').read_text())['cameras']
        rows.append(dict(run=run, unit=unit, images=cams, **seeds(sp), gaussians_15000=g15, gaussians_max=gmax, last_iteration=last, peak_reserved_GiB=peak))
        print('UNIT', rows[-1], flush=True)
    write('density_units', rows, f'addendum 14 part A: elongation-filter runs; gaussians at 15,000 (end of densification), peak reserved GPU memory over the run, training cameras, seed points and {GRID:g} m seed-occupied area; no GT')
    # one row per distinct unit (B0 seeds 0 and 1 averaged)
    units = {}
    for r in rows:
        units.setdefault(r['unit'], []).append(r)
    du = []
    for u, rs in units.items():
        g = float(np.mean([r['gaussians_15000'] for r in rs]))
        du.append(dict(unit=u, runs=len(rs), gaussians=g, **{k: rs[0][k] for _, k in RATIOS}, **{n: g / rs[0][k] for n, k in RATIOS}))
    b0 = [r['gaussians_15000'] for r in units['B0']]
    ratios = []
    for n, k in RATIOS:
        v = np.array([d[n] for d in du])
        med = float(np.median(v))
        ratios.append(dict(ratio=n, **{d['unit']: d[n] for d in du}, median=med, min=float(v.min()), max=float(v.max()), relative_range=float((v.max() - v.min()) / med)))
    ratios.append(dict(ratio='B0_two_seed_count_difference', B0=float(abs(b0[0] - b0[1])), relative_range=float(abs(b0[0] - b0[1]) / np.mean(b0))))
    write('density_ratios', ratios, 'addendum 14 part A: gaussians at 15,000 per training image, per seed point and per seed-occupied m2 over the four distinct units (B0 = mean of seeds 0 and 1); relative_range = (max-min)/median; last row: B0 seed-0 vs seed-1 count difference')
    for r in ratios:
        print('RATIO', r, flush=True)
    gm = np.array([r['gaussians_15000'] for r in rows]) / 1e6
    pk = np.array([r['peak_reserved_GiB'] for r in rows])
    b, a = np.polyfit(gm, pk, 1)
    res = pk - (a + b * gm)
    mem = [dict(fit='peak_GiB = a + b * gaussians_M', a=float(a), b=float(b), max_abs_residual_GiB=float(np.abs(res).max()), runs=len(rows),
                fitted_gaussians_M_min=float(gm.min()), fitted_gaussians_M_max=float(gm.max()),
                **{f'gaussians_M_at_{L}GiB': float((L - a) / b) for L in (16, 20, 24)})]
    write('density_memory', mem, 'addendum 14 part A: least-squares line of peak reserved GPU memory against gaussians (millions) over the five filter runs; counts where the line reaches 16, 20 and 24 GiB (extrapolated beyond the fitted range); no margin chosen')
    print('MEM', mem[0], flush=True)
    # predictions for the cellsef cells (from each cell's own inputs) and for the campus as one unit
    cells = json.loads((TU / 'cells/cells.json').read_text())['cells']
    targets = [(f'cellsef_ALS_s0_cell{c["id"]}', len(json.loads((TU / f'scenes/cell{c["id"]}/split.json').read_text())['train']), TU / f'stage1/cell{c["id"]}__ALS/seeds.npz') for c in cells]
    targets.append(('campus_one_unit', len(json.loads((TU / 'scenes/campus/split.json').read_text())['train']), TU / 'stage1/campus__ALS/seeds.npz'))
    med = {r['ratio']: r['median'] for r in ratios if 'median' in r}
    rng = {r['ratio']: (r['min'], r['max']) for r in ratios if 'median' in r}
    pred = []
    for name, imgs, sp in targets:
        s = seeds(sp)
        q = dict(images=imgs, **s)
        row = dict(target=name, **q)
        for n, k in RATIOS:
            g = med[n] * q[k]
            row[f'pred_gaussians_{n}'] = g
            row[f'pred_gaussians_{n}_low'] = rng[n][0] * q[k]
            row[f'pred_gaussians_{n}_high'] = rng[n][1] * q[k]
            row[f'pred_peak_GiB_{n}'] = float(a + b * g / 1e6)
        pred.append(row)
        print('PRED', row, flush=True)
    write('density_predictions', pred, f'addendum 14 part A, written {now()} before any cellsef cell started: predicted gaussians (median ratio; low/high = min/max ratio) and peak memory (memory line) for the cellsef cells from their own training images, seed points and {GRID:g} m seed-occupied area, and for the campus as one unit')


def check():
    locked()
    pred = json.loads((D / 'tables/density_predictions.json').read_text())['rows']
    out = []
    for p in pred:
        if not p['target'].startswith('cellsef_'):
            continue
        rec = TU / 'runs/ef' / p['target'] / 'receipt.json'
        if not rec.exists():
            continue
        r = json.loads(rec.read_text())
        att = TU / 'runs/ef' / p['target'] / f'attempt{r["attempts"][-1]["attempt"]}'
        g15, gmax, peak, last = trace(att / 'model')
        if p['target'].endswith('cell0'):   # resumed from cell0ef at 15,000: its first half is that run
            first = trace(TU / 'runs/ef/cell0ef_ALS_s0/attempt1/model')
            g15 = g15 or first[0]
            gmax, peak = max(gmax, first[1]), max(peak, first[2])
        row = dict(target=p['target'], status=r['status'], last_iteration=last, gaussians_15000=g15, gaussians_max=gmax, peak_reserved_GiB=peak)
        for n, _ in RATIOS:
            row[f'pred_{n}'] = p[f'pred_gaussians_{n}']
            row[f'measured_over_pred_{n}'] = g15 / p[f'pred_gaussians_{n}'] if g15 else None
            row[f'pred_peak_GiB_{n}'] = p[f'pred_peak_GiB_{n}']
        out.append(row)
        print('CHECK', row, flush=True)
    write('density_check', out, 'addendum 14: measured cellsef cell gaussians at 15,000 and peak memory vs the part-A predictions written before training')


if __name__ == '__main__':
    dict(measure=measure, check=check)[sys.argv[1]](*sys.argv[2:])
