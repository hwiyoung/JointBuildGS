"""Verify ZIP bytes and recompute both place tables and occlusion counts in ZIP."""
import argparse
import hashlib
import io
import json
import zipfile
import numpy as np


def verify(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None, 'ZIP CRC failure'
        names = z.namelist(); assert len(set(names)) == len(names)
        manifest = json.loads(z.read('MANIFEST.json'))
        assert set(names) == set(manifest['files']) | {'MANIFEST.json'}
        for name, expected in manifest['files'].items():
            data = z.read(name)
            assert len(data) == expected['bytes']
            assert hashlib.sha256(data).hexdigest() == expected['sha256'], name
        def js(name): return json.loads(z.read(name))
        def npz(name):
            with np.load(io.BytesIO(z.read(name)), allow_pickle=False) as f:
                return {k: f[k] for k in f.files}
        base = 'docs/experiments/phd/main_candpick_v1/'
        cfg_name = 'configs/phd/main_candpick_v1/places_v1.json'
        cfg = js(cfg_name)
        assert hashlib.sha256(z.read(cfg_name)).hexdigest() == js('configs/phd/main_candpick_v1/places_v1.lock.json')['sha256']
        rows = js(base + 'tables/places.json')['rows']
        summary = js(base + 'stage1_summary.json')
        checked = points = 0
        for unit, metadata in cfg['units'].items():
            d = npz('payload/places/' + unit + '.npz')
            j = npz('payload/validation/' + unit + '_photo_judgments.npz')
            o = npz('payload/occlusion/' + unit + '/points.npz')
            masks = npz('payload/scenes/' + unit + '/cleanup_masks.npz')
            assert hashlib.sha256(z.read('payload/places/' + unit + '.npz')).hexdigest() == metadata['payload']['sha256']
            assert d['point_id'].tolist() == metadata['point_ids']
            assert np.array_equal(d['point_id'], j['point_id']) and np.array_equal(d['point_id'], o['point_id'])
            assert np.array_equal(d['judgment'], j['judgment'][:, 4])
            prior = unit.split('_')[1]; tau = cfg['tau_m'][prior]
            gt, m = d['gt_p'], d['mvs_p']
            pok, iok = np.abs(gt) <= tau, np.abs(gt - m) <= tau
            assert np.isfinite(gt).all() and np.isfinite(m).all()
            assert (np.abs(m) >= 2 * tau).all() and (pok != iok).all()
            right = np.where(pok, 'prior', 'image')
            side = np.where(np.where(pok, -m, m) > 0, 'front', 'back')
            assert np.array_equal(right, d['right']) and np.array_equal(side, d['side'])
            for row in rows:
                if row['site'] + '_' + row['prior'] != unit: continue
                judgment = j['judgment'][:, row['column_zero_based']]
                group = np.where(judgment >= 2, 'b', np.where((judgment == 0) == pok, 'a', 'c'))
                selected = (right == row['right']) & (side == row['side']) & (group == row['group'])
                assert int(selected.sum()) == row['points']
                assert abs(float(d['area'][selected].sum()) - row['area_m2']) < 1e-8
                assert len(np.unique(d['building'][selected])) == row['buildings']
                checked += 1
            total, blocked = o['observed_pixels'].sum(1), o['occluded_pixels'].sum(1)
            assert (o['occluded_pixels'] <= o['observed_pixels']).all()
            ratio = np.divide(blocked, total, out=np.full(len(total), np.nan), where=total > 0)
            assert np.allclose(ratio, o['occluded_fraction'], equal_nan=True)
            assert np.array_equal(ratio > .3, o['over_30pct'])
            s = next(r for r in summary['rows'] if r['unit'] == unit)
            assert s['occlusion_over_30pct_points'] == int((ratio > .3).sum())
            assert abs(s['occlusion_over_30pct_area_m2'] - float(d['area'][ratio > .3].sum())) < 1e-8
            assert s['deleted_evidence'] == int(masks['delete_evidence'].sum())
            assert s['remaining'] == int(masks['keep'].sum())
            assert s['gradient_variants_status'] == 'PASS' and s['optimizer_steps'] == 0
            points += len(total)
        assert points == 13849 and checked == 96
        return dict(status='PASS', zip_crc='PASS', member_sha256='PASS', members=len(names),
                    recomputed_place_rows=checked, recomputed_occlusion_points=points,
                    training_arms=summary['completed_training_arms'], experiment_status=summary['status'],
                    scientific_verdict=None)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('zip'); args = p.parse_args()
    print(json.dumps(verify(args.zip)))
