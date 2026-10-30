"""Independent scalar recomputation of every locked place and summary cell."""
import json
from pathlib import Path
import numpy as np
from input_audit import sha
from prepare_places import save, load_points


def main():
    cfgfile = Path('/config/places_v1.json'); cfg = json.loads(cfgfile.read_text())
    assert sha(cfgfile) == json.loads(Path('/config/places_v1.lock.json').read_text())['sha256']
    rows = json.loads(Path('/docs/tables/places.json').read_text())['rows']
    original = {}
    for prior in ['ALS', 'LoD2']:
        d = load_points(prior, [])
        original[prior] = {str(i): j for i, j in zip(d['point_id'], d['judgment'])}
    comparisons = 0
    for unit, metadata in cfg['units'].items():
        site, prior = unit.split('_'); tau = cfg['tau_m'][prior]
        path = Path('/out/places') / (unit + '.npz')
        assert sha(path) == metadata['payload']['sha256']
        with np.load(path) as z:
            n = len(z['point_id']); assert n == metadata['points']
            assert len(set(z['point_id'])) == n
            assert z['point_id'].tolist() == metadata['point_ids']
            total = {}
            for i in range(n):
                m, gt, j = float(z['mvs_p'][i]), float(z['gt_p'][i]), int(z['judgment'][i])
                assert np.isfinite(m) and np.isfinite(gt) and abs(m) >= 2 * tau
                prior_ok = -tau <= gt <= tau
                image_ok = -tau <= gt - m <= tau
                assert prior_ok != image_ok
                right = 'prior' if prior_ok else 'image'
                hright, hwrong = (0., m) if prior_ok else (m, 0.)
                side = 'front' if hright > hwrong else 'back'
                group = 'b' if j >= 2 else ('a' if (j == 0) == prior_ok else 'c')
                assert (right, side, group) == (z['right'][i], z['side'][i], z['group'][i])
                judgments = original[prior][str(z['point_id'][i])]
                assert int(judgments[4]) == j
                for label, column in [('main_display', 4), ('supplement_stage1', 0)]:
                    jc = int(judgments[column])
                    gc = 'b' if jc >= 2 else ('a' if (jc == 0) == prior_ok else 'c')
                    key = label, right, gc, side
                    value = total.setdefault(key, [0, 0., set()])
                    value[0] += 1; value[1] += float(z['area'][i]); value[2].add(str(z['building'][i]))
                comparisons += 1
            assert abs(sum(v[1] for k, v in total.items() if k[0] == 'main_display') - metadata['area_m2']) < 1e-8
            for r in rows:
                if r['site'] != site or r['prior'] != prior: continue
                actual = total.get((r['judgment'], r['right'], r['group'], r['side']), [0, 0., set()])
                assert r['points'] == actual[0] and abs(r['area_m2'] - actual[1]) < 1e-8 and r['buildings'] == len(actual[2])
    report = dict(status='PASS', independently_checked_points=comparisons,
        checked_summary_rows=len(rows),
        supplemental_source_column=0, main_source_column=4, optimizer_steps=0,
        places_sha256=sha(cfgfile), script_sha256=sha(__file__), scientific_verdict=None)
    save(Path('/docs/places_validation_v2.json'), report)
    print(json.dumps(report))


if __name__ == '__main__': main()
