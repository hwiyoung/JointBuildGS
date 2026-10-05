"""Independently check exported region arrays and their output ledger on CPU."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    receipt = json.loads((args.result / 'receipt.json').read_text())
    total = receipt['config']['train_view_count']
    assert receipt['total_views'] == total
    assert len({r['name'] for r in receipt['views']}) == total
    for item in receipt['outputs']:
        file = args.result / item['path']
        assert file.stat().st_size == item['bytes'], item['path']
        assert hashlib.sha256(file.read_bytes()).hexdigest() == item['sha256'], item['path']
    totals = {str(i):0 for i in range(1,7)}
    native_totals = totals.copy()
    for row in receipt['views']:
        folder = args.result / row['folder']
        for level, count_key, shape_key in [('native','native_counts','native_shape'),('rgb','rgb_counts','rgb_shape')]:
            with np.load(folder / (level+'_masks.npz'), allow_pickle=False) as data:
                labels, valid, weights, inside = [data[k] for k in ('region_id','valid','weight','inside_context')]
                assert valid.dtype == np.bool_ and inside.dtype == np.bool_, 'Boolean export dtype required before indexing'
                assert list(labels.shape) == row[shape_key]
                assert labels.shape == valid.shape == weights.shape
                assert np.isin(labels,[1,2,3,4,5,6]).all()
                expected = np.zeros(labels.shape, np.float32)
                expected[np.isin(labels,[2,3])] = 1
                expected[labels == 1] = receipt['config']['display_alpha']
                np.testing.assert_array_equal(expected, weights)
                assert (weights[~valid] == 0).all()
                assert (labels[~valid] == 5).all()
                np.testing.assert_array_equal(labels == 6, valid & ~inside)
                assert np.all(data['candidate_support'][labels == 1])
                assert np.all(inside[np.isin(labels,[1,2,3,4])])
                if not row['manual_source']:
                    assert not (labels == 4).any()
                for i in range(1,7):
                    count = int((labels == i).sum())
                    assert count == row[count_key][str(i)]
                    (totals if level == 'rgb' else native_totals)[str(i)] += count
                if level == 'rgb':
                    np.testing.assert_array_equal(np.asarray(Image.open(folder/'region_id.png')), labels)
    first = receipt['views'][0]
    samples = {}
    if receipt['config'].get('region', 'P1') == 'P1':
      with np.load(args.result / first['folder'] / 'rgb_masks.npz', allow_pickle=False) as data:
        # Original A-D boxes were crop-relative to [602,259,1258,915].
        for key, (x0,y0,x1,y1) in {'A':(180,225,260,345),'B':(160,425,230,465),'C':(360,535,470,605),'D':(390,255,470,320)}.items():
            sample = data['region_id'][259+y0:259+y1,602+x0:602+x1]
            samples[key] = {str(i):int((sample == i).sum()) for i in range(1,7)}
    context = sum(r['valid_context_rgb_samples'] for r in receipt['views'])
    assigned = sum(r['assigned_context_rgb_samples'] for r in receipt['views'])
    result = {'status':'PASS_EXPORTED_ARRAYS_AND_HASHES', 'scientific_verdict':None,
              'receipt_sha256':hashlib.sha256((args.result/'receipt.json').read_bytes()).hexdigest(),
              'checked_output_hashes':len(receipt['outputs']), 'checked_view_arrays':total*2,
              'all_rgb_region_counts':totals, 'all_native_region_counts':native_totals,
              'views_with_candidate_pixels':sum(r['candidate_rgb_samples'] > 0 for r in receipt['views']),
              'views_with_at_least_100_candidate_rgb_pixels':sum(r['candidate_rgb_samples'] >= 100 for r in receipt['views']),
              'views_with_no_valid_context_depth':sum(r['valid_context_rgb_samples'] == 0 for r in receipt['views']),
              'all_valid_context_rgb_samples':context, 'all_assigned_context_rgb_samples':assigned,
              'assigned_fraction_of_valid_context_rgb_samples':assigned/context,
              'ABCD_region_counts':samples,
              'note':'RGB counts include native nearest duplicates and repeated multi-view observations, not unique 3D area or semantic accuracy.'}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
