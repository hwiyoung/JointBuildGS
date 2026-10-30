"""Independent pointwise reconstruction of completed-arm outcome tables."""
import hashlib
import io
import json
from pathlib import Path
import numpy as np
from result_io import save

DOCREL = 'docs/experiments/phd/main_candpick_v1/'


def validate(read):
    def js(path): return json.loads(read(path))
    def nz(path):
        with np.load(io.BytesIO(read(path)), allow_pickle=False) as f: return {k: f[k] for k in f.files}
    cfgname = 'configs/phd/main_candpick_v1/candpick_v1.json'
    cfg = js(cfgname); digest = hashlib.sha256(read(cfgname)).hexdigest()
    assert digest == js('configs/phd/main_candpick_v1/candpick_v1.lock.json')['sha256']
    for path, expected in cfg['implementation_sha256'].items():
        assert hashlib.sha256(read(path)).hexdigest() == expected, path
    status = js(DOCREL + 'results/status.json')
    rows = js(DOCREL + 'results/outcomes.json')['rows']
    photos = js(DOCREL + 'results/photo_error.json')['rows']
    curves = js(DOCREL + 'results/opacity_curves.json')['rows']
    rep_rows = js(DOCREL + 'results/representative_outcomes.json')['rows']
    reps = {r['id']: r for r in js(DOCREL + 'representatives_v1.json')['rows']}
    checked, point_checks, logs_checked = 0, 0, 0
    for arm in status['completed_arms']:
        root = 'payload/runs/' + arm + '/'
        receipt = js(root + 'complete.json'); unit = receipt['unit']; start = receipt['start']; sh = receipt['sh_degree']
        assert receipt['config_sha256'] == digest and receipt['optimizer_steps'] == 3000
        assert receipt['frozen_before'] == receipt['frozen_after'] and receipt['frozen_unchanged']
        assert not receipt['truth_used_in_loss'] and not receipt['depth_loss_used']
        d = nz('payload/places/' + unit + '.npz'); o = nz('payload/occlusion/' + unit + '/points.npz')
        initial = nz(root + 'candidate_0.npz'); final = nz(root + 'candidate_3000.npz')
        assert hashlib.sha256(read(root + 'candidate_3000.npz')).hexdigest() == receipt['final_candidate_sha256']
        a = final['opacity'].reshape(-1, 2, 4); a0 = initial['opacity'].reshape(-1, 2, 4)
        dc0 = initial['color_dc'].reshape(-1, 2, 4, 1, 3)
        assert np.array_equal(dc0[:, 0], dc0[:, 1]) and not initial['color_sh'].any()
        assert all(np.isfinite(final[k]).all() for k in final if k != 'iteration')
        if sh == 0: assert not final['color_sh'].any()
        labels, differences = [], []
        initial_right, initial_wrong = {'right': (.9, .1), 'wrong': (.1, .9), 'equal': (.5, .5)}[start]
        for i in range(len(a)):
            ri = 1 if d['right'][i] == 'image' else 0
            assert np.allclose(a0[i, ri], initial_right, atol=2e-7, rtol=0)
            assert np.allclose(a0[i, 1 - ri], initial_wrong, atol=2e-7, rtol=0)
            r = float(np.mean(a[i, ri], dtype=np.float32)); w = float(np.mean(a[i, 1 - ri], dtype=np.float32))
            assert 0 <= r <= 1 and 0 <= w <= 1
            labels.append('both' if r >= .5 and w >= .5 else 'right_only' if r >= .5 else 'wrong_only' if w >= .5 else 'neither')
            differences.append(np.float32(r) - np.float32(w))
        labels = np.asarray(labels); differences = np.asarray(differences)
        saved = nz('payload/scoring/' + arm + '.npz')
        assert np.array_equal(saved['point_id'], d['point_id'])
        assert np.array_equal(saved['outcome'], labels)
        for row in [r for r in rep_rows if r['arm'] == arm]:
            ids = set(reps[row['representative']]['selection']['point_ids'])
            indexes = [i for i, pid in enumerate(d['point_id']) if pid in ids]
            area = sum(float(d['area'][i]) for i in indexes)
            assert row['points'] == len(indexes) == len(ids)
            assert abs(row['area_m2'] - area) < 1e-7
            for label in ['right_only', 'wrong_only', 'both', 'neither']:
                assert row[label + '_points'] == sum(labels[i] == label for i in indexes)
                selected_area = sum(float(d['area'][i]) for i in indexes if labels[i] == label)
                assert abs(row[label + '_area_fraction'] - selected_area / area) < 1e-10
        point_checks += len(labels)
        for row in [r for r in rows if r['arm'] == arm]:
            indexes = [i for i in range(len(labels)) if str(d['group'][i]) == row['group']
                       and (row['side'] == 'all' or str(d['side'][i]) == row['side'])
                       and (row['subset'] == 'all' or bool(o['over_30pct'][i]))]
            area = sum(float(d['area'][i]) for i in indexes)
            buildings = set(str(d['building'][i]) for i in indexes)
            assert row['points'] == len(indexes) and row['buildings'] == len(buildings)
            assert abs(area - row['area_m2']) < 1e-7
            for label in ['right_only', 'wrong_only', 'both', 'neither']:
                actual = sum(float(d['area'][i]) for i in indexes if labels[i] == label)
                assert abs(actual - row[label + '_area_m2']) < 1e-7
                expected = actual / area if area else None
                reported = row[label + '_area_fraction']
                assert reported is None if expected is None else abs(expected - reported) < 1e-10
                per_building = []
                for building in buildings:
                    b = [i for i in indexes if str(d['building'][i]) == building]
                    per_building.append(sum(float(d['area'][i]) for i in b if labels[i] == label) / sum(float(d['area'][i]) for i in b))
                median = float(np.median(per_building)) if per_building else None
                reported = row[label + '_building_median_fraction']
                assert reported is None if median is None else abs(median - reported) < 1e-10
            checked += 1
        logs = [json.loads(x) for x in read(root + 'metrics.jsonl').decode().splitlines()]
        assert [r['iteration'] for r in logs] == list(range(0, 3001, 100))
        for log in logs:
            for group in log['opacity']:
                row = next(r for r in curves if r['arm'] == arm and r['iteration'] == log['iteration'] and r['group'] == group['group'] and r['side'] == group['side'])
                assert all(row[k] == v for k, v in group.items())
                if log['iteration'] == 3000:
                    ids = (d['group'] == group['group']) & (d['side'] == group['side'])
                    if ids.any(): assert abs(float(differences[ids].mean()) - row['mean_right_minus_wrong']) < 1e-7
                logs_checked += 1
        photo = next(r for r in photos if r['arm'] == arm)
        for step, suffix in [(0, 'start'), (3000, 'end')]:
            error = js(root + f'photo_error_{step}.json')
            count = sum(r['candidate_pixels'] for r in error['views'])
            numerator = sum(r['candidate_pixels'] * r['candidate_l1'] for r in error['views'] if r['candidate_pixels'])
            assert count == photo['candidate_pixel_observations']
            assert abs(numerator / count - photo['candidate_l1_' + suffix]) < 1e-10
    criteria = js(DOCREL + 'results/criteria.json')['rows']
    for r in criteria:
        linked = {x['start']: x for x in rows if x['unit'] == r['unit'] and x['sh_degree'] == r['sh_degree']
                  and x['subset'] == r['subset'] and x['side'] == r['side'] and x['group'] == 'a'}
        for start in ['equal', 'wrong', 'right']:
            x = linked.get(start)
            expected = x['right_only_area_fraction'] if x else None
            assert r[start + '_right_only'] == expected
            other = x['both_area_fraction'] + x['neither_area_fraction'] if x and x['area_m2'] else None
            assert r[start + '_both_plus_neither'] == other
        delta = (r['wrong_right_only'] - r['right_right_only']) * 100 if r['wrong_right_only'] is not None and r['right_right_only'] is not None else None
        assert r['wrong_minus_right_pp'] == delta
        assert r['criterion1_equal_ge70pct'] == (r['equal_right_only'] >= .7 if r['equal_right_only'] is not None else None)
        assert r['criterion2_wrong_drop_le10pp'] == (r['wrong_minus_right_pp'] >= -10 if r['wrong_minus_right_pp'] is not None else None)
        for start in ['equal', 'wrong', 'right']:
            v = r[start + '_both_plus_neither']
            assert r['criterion3_' + start + '_le20pct'] == (v <= .2 if v is not None else None)
    assert checked == len(status['completed_arms']) * 18
    return dict(status='PASS', completed_arms=len(status['completed_arms']), point_arm_classifications=point_checks,
        outcome_rows=checked, curve_rows=logs_checked, criteria_rows=len(criteria), representative_rows=len(rep_rows),
        config_sha256=digest, scientific_verdict=None)


def local_read(path):
    p = Path('/out') / path[len('payload/'):] if path.startswith('payload/') else Path('/repo') / path
    return p.read_bytes()


if __name__ == '__main__':
    report = validate(local_read)
    save(Path('/docs/results/validation.json'), report)
    print(json.dumps(report))
