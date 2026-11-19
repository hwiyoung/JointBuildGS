"""PHD-MAIN-BASE151-v1 5.1 tables of 4.2 (GTJUDGE environment; /gtjudge = OUT/gt; writes /gtjudge/tables_b151/t42_*).

  python b151_tables42.py
Inputs: /gtjudge/score151/<run>__<prior>/rows.npz + samples.npz (b151_score151.py gather), /b151/gt/gt151_<prior>.npz.
  t42_total      151 buildings together, method x prior: the four cases (0 both, 1 image only, 2 prior only, 4 image missing) and the scene
                 (all rows, case 3 included): completeness (main = each row on the mesh of its own cell; literal = on the mesh of its
                 building's cell), accuracy (score151 accuracy rule; ALS |n_z| < 0.5 excluded), n of rows / samples
  t42_buildings  the same per building, with the cases whose GT n < 200 listed in 'n_under_200'
  t42_groups     experiment buildings (JUDGECHECK-v2 group 'experiment') vs the rest
  t42_gap        151 together: per prior, case and metric the best method value and every method's value minus it (percentage points);
                 the main method is not in this task (not trained here), so 'best' is the best of the comparison methods only
Values: GTJUDGE normal_line.values (|s| <= tau of the row / of the sample). A run without its gathered files is '결과 없음'.
scientific_verdict: null
"""
import csv
import json
import sys

import numpy as np

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import O, dump  # noqa: E402
from normal_line import values  # noqa: E402
import b151_common as BC  # noqa: E402

CASES = [0, 1, 2, 4, 'all']
NAME = {0: '두 자료 모두 유효', 1: '사전정보 오류', 2: '영상 깊이 오류', 4: '영상 깊이 결측', 'all': '장면 전체'}
RUNS = [('2DGS', 'ALS', 'b151_2DGS_s0'), ('2DGS', 'LoD2', 'b151_2DGS_s0')] + \
       [(m, p, f'b151_{m}_{p}_s0') for m in ['GeoGS', 'CDGS'] for p in ['ALS', 'LoD2']] + [('LGDM', p, f'b151_LGDM_{p}') for p in ['ALS', 'LoD2']]
T = O / 'tables_b151'


def write(name, rows, note):
    T.mkdir(parents=True, exist_ok=True)
    dump(T / f'{name}.json', dict(note=note, rows=rows, scientific_verdict=None))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (T / f'{name}.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    fmt = lambda v: '' if v is None else (f'{v:.2f}' if isinstance(v, float) else str(v))
    with (T / f'{name}.md').open('w') as f:
        f.write(f'{note}\n\nscientific_verdict: null\n\n| ' + ' | '.join(fields) + ' |\n| ' + ' | '.join('---' for _ in fields) + ' |\n')
        for r in rows:
            f.write('| ' + ' | '.join(fmt(r.get(k)) for k in fields) + ' |\n')


def load(run, prior, g):
    d = O / 'score151' / f'{run}__{prior}'
    if not (d / 'summary.json').exists():
        return None
    rw, sm = np.load(d / 'rows.npz'), np.load(d / 'samples.npz')
    srow = sm['sample_row'].astype(np.int64)
    brow = sm['sample_building_row'].astype(np.int64)
    scase = np.where(srow >= 0, g['case'][np.clip(srow, 0, None)], -1)
    sbld = np.where(brow >= 0, g['bcode'][np.clip(brow, 0, None)], -1)
    ok = sm['sample_eligible'].astype(bool)
    if prior == 'ALS':
        ok &= ~(np.abs(sm['sample_nz']) < .5)
    summ = json.loads((d / 'summary.json').read_text())
    return dict(s_main=rw['s_main'], s_lit=rw['s_literal'], covered=rw['covered'], ss=sm['sample_s'], st=sm['sample_tau'], ok=ok,
                steep=int((sm['sample_eligible'].astype(bool) & (np.abs(sm['sample_nz']) < .5)).sum()) if prior == 'ALS' else 0,
                scase=scase, sbld=sbld, units=sum(u['scored'] for u in summ['units']), units_all=len(summ['units']))


def block(z, g, rmask, smask):
    out = {}
    for c in CASES:
        rm = rmask & (np.ones(len(rmask), bool) if c == 'all' else g['case'] == c)
        sq = smask & (np.ones(len(smask), bool) if c == 'all' else z['scase'] == c)
        main, lit = values(z['s_main'][rm], g['tau'][rm]), values(z['s_lit'][rm], g['tau'][rm])
        acc = values(z['ss'][sq], z['st'][sq], z['ok'][sq])
        out[c] = dict(completeness=main['within_pct'], completeness_literal=lit['within_pct'], accuracy=acc['within_pct'], n_gt=main['n'], n_samples=acc['n'])
    return out


def flat(b):
    r = {}
    for c in CASES:
        for k, lab in [('completeness', '완전성'), ('completeness_literal', '완전성_문자대로'), ('accuracy', '정확성'), ('n_gt', 'n_gt'), ('n_samples', 'n_표본')]:
            r[f'{lab}_{NAME[c]}'] = b[c][k]
    return r


def main():
    grp = {r['building']: r['group'] for r in json.loads((BC.JC2 / 'stage0/buildings.json').read_text())['rows'] if r['in_scope']}
    G = {}
    for p in ['ALS', 'LoD2']:
        with np.load(BC.B / 'gt' / f'gt151_{p}.npz') as z:
            G[p] = {k: z[k] for k in ['case', 'tau', 'building']}
        names, G[p]['bcode'] = np.unique(G[p]['building'], return_inverse=True)
        G[p]['code_of'] = {n: i for i, n in enumerate(names.tolist())}
    total, blds, groups, have = [], [], [], {}
    for method, prior, run in RUNS:
        g = G[prior]
        z = load(run, prior, g)
        head = dict(method=method, prior=prior, run=run)
        if z is None:
            total.append(dict(head, status='결과 없음'))
            groups.append(dict(head, group='all', status='결과 없음'))
            continue
        allr, alls = np.ones(len(g['case']), bool), np.ones(len(z['ss']), bool)
        b = block(z, g, allr, alls)
        have[(method, prior)] = b
        total.append(dict(head, status='있음', units_scored=f"{z['units']}/{z['units_all']}", rows_on_a_unit=int(z['covered'].sum()), rows=int(len(g['case'])),
                          samples=int(len(z['ss'])), samples_steep_excluded=z['steep'], samples_without_building=int((z['sbld'] < 0).sum()), **flat(b)))
        for gname in ['experiment', 'rest']:
            names = [n for n, v in grp.items() if (v == 'experiment') == (gname == 'experiment')]
            codes = np.array([g['code_of'][n] for n in names if n in g['code_of']], np.int64)
            bb = block(z, g, np.isin(g['bcode'], codes), np.isin(z['sbld'], codes))
            groups.append(dict(head, group=gname, buildings=int(len(names)), status='있음', **flat(bb)))
        for name in sorted(grp):
            c = g['code_of'].get(name, -2)
            bb = block(z, g, g['bcode'] == c, z['sbld'] == c)
            small = [str(c) for c in [0, 1, 2, 4] if 0 < bb[c]['n_gt'] < 200]
            blds.append(dict(head, building=name, group=grp[name], n_under_200=','.join(small), **flat(bb)))
    gap = []
    for prior in ['ALS', 'LoD2']:
        for c in CASES:
            for key, lab in [('completeness', '완전성'), ('accuracy', '정확성')]:
                vals = {m: have[(m, prior)][c][key] for m in ['2DGS', 'GeoGS', 'CDGS', 'LGDM'] if (m, prior) in have and have[(m, prior)][c][key] is not None}
                row = dict(prior=prior, case=NAME[c], metric=lab)
                if not vals:
                    gap.append(dict(row, status='결과 없음'))
                    continue
                best = max(vals.values())
                row.update(best_method=','.join(m for m, v in vals.items() if v == best), best_pct=best)
                for m in ['2DGS', 'GeoGS', 'CDGS', 'LGDM']:
                    row[f'{m}_minus_best_pp'] = vals[m] - best if m in vals else '결과 없음'
                row['main_method'] = '없음 (이 과제에서 학습하지 않음)'
                gap.append(row)
    write('t42_total', total, '4.2: 151 buildings together, method x prior: completeness (main / literal), accuracy %, n per case and the scene')
    write('t42_buildings', blds, '4.2: per building, method x prior, the same columns; n_under_200 = cases with 1-199 GT points')
    write('t42_groups', groups, '4.2: experiment buildings (10) vs the rest (141)')
    write('t42_gap', gap, '4.2: 151 together, value minus the best comparison method (pp); the main method is not in this task')
    print('T42', len(total), len(blds), len(groups), len(gap), flush=True)


if __name__ == '__main__':
    main()
