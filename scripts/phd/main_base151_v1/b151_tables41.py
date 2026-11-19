"""PHD-MAIN-BASE151-v1 5.1 table of 4.1 (GTJUDGE environment; /gtjudge = OUT/gt; writes /gtjudge/tables_b151/t41_*).

  python b151_tables41.py
Method x prior x site: the 2 x 2 run (this task) and the previous building-unit result of the same method and site, both through the
unchanged GTJUDGE scorer add2_scores.metric_rows (section 3.4 accuracy rule): four cases (0 both, 1 image only, 2 prior only, 4 image
missing) and the scene, n_gt per case. Missing runs are written as '결과 없음'. scientific_verdict: null
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import add2_scores  # noqa: E402
from inherited import O, dump  # noqa: E402

SITES = ['B0_b10', 'R1rep_b10', 'B173nb_b10']
CASES = [0, 1, 2, 4]
NAME = {0: '두 자료 모두 유효', 1: '사전정보 오류', 2: '영상 깊이 오류', 4: '영상 깊이 결측', 'all': '장면 전체'}
MET = [('완전성', 'completeness_pct'), ('정확성', 'accuracy_pct')]
RUNS = {'2DGS': {'ALS': 'b151_2DGS_s0', 'LoD2': 'b151_2DGS_s0'}, 'GeoGS': {p: f'b151_GeoGS_{p}_s0' for p in ['ALS', 'LoD2']},
        'CDGS': {p: f'b151_CDGS_{p}_s0' for p in ['ALS', 'LoD2']}, 'LGDM': {p: f'b151_LGDM_{p}' for p in ['ALS', 'LoD2']}}
PREV = {'2DGS': '2DGS_30000', 'GeoGS': 'GeoGS_30000', 'CDGS': 'CDGS_30000', 'LGDM': 'fusion'}
MESH = {'2x2': 'TRAINUNIT-v2 rule: render_model with the method renderer at the GTJUDGE site views, streamed TSDF 0.05 / 0.25, bounded cleanup',
        'previous': "RESCORE addendum3 'primary': the method's own TSDF (0.05 / 0.25, the same site views) + bounded cleanup"}
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


def main():
    out = []
    for method, by in RUNS.items():
        for prior in [p for p in ['ALS', 'LoD2'] if p in by]:
            for site in SITES:
                stem = f'{site}__{prior}'
                for version, fam in [('2x2', by[prior]), ('건물 단위(앞 작업)', PREV[method])]:
                    row = dict(method=method, prior=prior, site=site, version=version, family=fam,
                               mesh_rule=MESH['2x2' if version == '2x2' else 'previous'], scorer='GTJUDGE add2_scores.metric_rows (same)')
                    if not (O / 'scenes' / stem / 'distances' / f'{fam}.npz').exists():
                        out.append(dict(row, status='결과 없음'))
                        continue
                    look = {(r['surface'], r['case_id']): r for r in add2_scores.metric_rows(site, prior, [fam])}
                    row['status'] = '있음'
                    for case in CASES + ['all']:
                        r = look[('all', case)]
                        for m, k in MET:
                            row[f'{m}_{NAME[case]}'] = r[k]
                        row[f'n_gt_{NAME[case]}'] = r['n_gt']
                    out.append(row)
    write('t41_scores', out, '4.1: method x prior x site, 2 x 2 (this task) and the previous building-unit result, completeness / accuracy % of the four cases '
          'and the scene (section 3.4 accuracy rule), n_gt per case; the same scorer; the mesh rules differ as in mesh_rule')
    print('T41', len(out), flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1:   # interim bundle: only the named runs (method_prior keys of RUNS), written to tables_b151/interim/
        keep = set(sys.argv[1:])
        RUNS = {m: {p: r for p, r in by.items() if r in keep} for m, by in RUNS.items()}
        RUNS = {m: by for m, by in RUNS.items() if by}
        T = O / 'tables_b151' / 'interim'
    main()
