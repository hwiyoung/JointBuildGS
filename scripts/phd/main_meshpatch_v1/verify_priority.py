"""Independently recompute all cells for completed priority runs from saved arrays."""
import json
from pathlib import Path
import numpy as np
from mesh_common import C, D, O, LT, sha, dump, now


def close(actual, expected):
    if expected is None:
        assert actual is None
    else:
        assert np.isclose(actual, expected, rtol=1e-10, atol=1e-8), (actual, expected)


def verify():
    rows = []
    for key in json.loads((C / 'priority_delivery_v1.json').read_text())['keys']:
        p = D / 'tables/meshes' / (key + '.json')
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        if r['status'] != 'PASS':
            continue
        t = r['target']
        assert sha(t['evaluation']) == t['evaluation_sha256']
        assert sha(t['values']) == t['values_sha256']
        e = dict(np.load(t['evaluation']))
        v = dict(np.load(t['values']))
        checked = 0
        input_hashes = {}
        before_exact = None
        for stage in ['before', 'after']:
            path = O / 'patch_z' / f'{key}__{stage}.npz'
            data = dict(np.load(path))
            input_hashes[stage] = sha(path)
            z = data['z']
            good = np.isfinite(z)
            assert np.array_equal(data['no_surface'], ~good)
            assert np.array_equal(data['in_eval'], e['in_eval'])
            assert np.array_equal(data['scoring_allowed'], e['scoring_allowed'])
            dp = np.abs(z) / v['sigma_prior'].astype(np.float64)
            dm = np.abs(z - e['p_mvs']) / v['sigma_mvs'].astype(np.float64)
            prior = good & (dp <= 3) & ((dm > 3) | ~np.isfinite(dm) | (dp <= dm))
            mvs = good & ~prior & (dm <= 3)
            side = np.full(len(z), 3, dtype=np.int8)
            side[good] = 2
            side[prior] = 0
            side[mvs] = 1
            assert np.array_equal(side, data['side'])
            within = good & (np.abs(z - e['p_gt']) <= e['tau'])
            floating = good & ~within & (side == 2) & (z > e['p_gt'] + e['tau'])
            groups = dict(within_tau=within, floating=floating,
                          mvs=good & ~within & mvs, prior=good & ~within & prior)
            groups['other_missing'] = ~np.logical_or.reduce(list(groups.values()))
            elig = e['in_eval'] & e['scoring_allowed']
            for record in r[stage]:
                cell = record['cell']
                mask = elig.copy()
                if cell == '0~3':
                    mask &= (e['cell'] >= 0) & (e['cell'] <= 3)
                elif cell != '전체':
                    mask &= e['cell'] == int(cell)
                area = float(e['area'][mask].sum())
                assert int(mask.sum()) == record['patches']
                close(area, record['area_m2'])
                for name, selection in groups.items():
                    selected_area = float(e['area'][mask & selection].sum())
                    assert int((mask & selection).sum()) == record[name + '_patches']
                    close(selected_area, record[name + '_area_m2'])
                    close(100 * selected_area / area if area else None, record[name + '_pct'])
                missing_area = float(e['area'][mask & ~good].sum())
                close(missing_area, record['no_surface_area_m2'])
                close(100 * missing_area / area if area else None, record['no_surface_pct'])
                checked += 1
            if stage == 'before':
                old = dict(np.load(LT / 'patch_z' / (key + '.npz')))
                before_exact = bool(np.array_equal(old['z'], z, equal_nan=True))
                assert r['before_reference_check']['status'] == 'PASS'
                assert r['before_reference_check']['max_area_difference_pp'] <= .5
        cleanup, removed = r['cleanup'], r['removed']
        assert cleanup['before_triangles'] - cleanup['after_triangles'] == removed['triangles']
        assert sum(x['triangles'] for x in removed['categories']) == removed['triangles']
        close(sum(x['area_m2'] for x in removed['categories']), removed['area_m2'])
        assert cleanup['min_remaining_component_triangles'] >= cleanup['count_threshold']
        rows.append(dict(key=key, status='PASS', checked_cell_records=checked,
                         before_z_exact_match=before_exact,
                         patch_z_sha256=input_hashes, mesh_receipt_sha256=sha(p)))
    result = dict(status='PASS' if len(rows) == 6 else 'PARTIAL', completed=len(rows), required=6,
                  rows=rows, checked_at=now(),
                  scope='Recompute every saved before/after cell; report exact baseline z agreement and preserve the frozen 0.5 percentage point gate; side labels; removed triangle accounting. No new ray cast or visibility calculation.',
                  scientific_verdict=None)
    dump(D / 'tables/priority_validation.json', result)
    return result


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False))
