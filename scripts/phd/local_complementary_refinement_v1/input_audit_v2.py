"""Audit frozen training depth semantics and ramp saturation; never select by GT.

Run in CPU Docker with /inputs, /contracts and /source mounted read-only and
only /output writable. Reads training depth arrays and split metadata only.
"""
import hashlib
import json
import platform
from pathlib import Path
import time

import cv2
import numpy as np


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def summary(delta, t0, t1):
    a = np.clip((delta - t0) / (t1 - t0), 0, 1)
    return {'count': int(len(a)), 'a_sum': float(a.sum(dtype=np.float64)),
            'a_zero': int(np.count_nonzero(a == 0)),
            'a_transition': int(np.count_nonzero((a > 0) & (a < 1))),
            'a_one': int(np.count_nonzero(a == 1))}


def rates(row):
    n = row['count']
    return {**row, 'mean_a': row['a_sum']/n if n else None,
            **{k+'_fraction': row[k]/n if n else None
               for k in ('a_zero', 'a_transition', 'a_one')}}


def ray_fixture():
    import open3d as o3d
    K = np.array([[2., 0., 2.], [0., 2., 2.], [0., 0., 1.]])
    E = np.eye(4)
    rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(K, E, 4, 4)
    scene = o3d.t.geometry.RaycastingScene()
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector([[-20., -20., 5.], [20., -20., 5.],
                                   [20., 20., 5.], [-20., 20., 5.]]),
        o3d.utility.Vector3iVector([[0, 1, 2], [0, 2, 3]]))
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    d = scene.cast_rays(rays)['t_hit'].numpy()
    directions = rays.numpy()[..., 3:]
    assert np.allclose(d, 5., atol=1e-6)
    assert np.allclose(directions[..., 2], 1., atol=1e-6)
    assert np.allclose(directions[0, 0], [-.75, -.75, 1.], atol=1e-6)
    return {'status': 'PASS_CAMERA_Z_NOT_EUCLIDEAN_RANGE',
            'open3d_version': o3d.__version__, 'plane_camera_z_m': 5.,
            'all_t_hit_equal_camera_z': True,
            'corner_ray_direction': directions[0, 0].tolist(),
            'corner_range_m': float(5*np.linalg.norm(directions[0, 0])),
            'pixel_center': 'u+0.5,v+0.5 with camera direction z=1'}


def main():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('CPU Docker required')
    out = Path('/output/input_audit_v2.json')
    if out.exists():
        raise FileExistsError(out)
    cv2.setNumThreads(1)
    started = time.time()
    binding = read('/contracts/input_binding.json')
    frozen = np.load('/contracts/threshold_samples.npz', allow_pickle=False)
    assert sha('/contracts/threshold_samples.npz') == binding['threshold_samples']['sha256']
    pooled = np.concatenate([frozen[r] for r in binding['regions']])
    q10, q25 = np.quantile(pooled, [.1, .25]).tolist()
    policies = {'fixed_0p5_2': [.5, 2.], 'fixed_0p5_5': [.5, 5.],
                'fixed_1_5': [1., 5.], 'input_sample_Q10_Q25': [q10, q25],
                'historical_probe_Q50_Q90': [binding['tau0_m'], binding['tau1_m']]}
    result = {'schema': 'JBGS_LOCAL_TRAINING_INPUT_AUDIT_v2',
              'scientific_verdict': None, 'reference_accessed': False,
              'evaluation_rgb_accessed': False, 'training_rgb_accessed': False,
              'threshold_policy_selected_by_this_audit': None,
              'input_binding_sha256': sha('/contracts/input_binding.json'),
              'script_sha256': sha(__file__), 'policies': policies,
              'ray_fixture': ray_fixture(), 'regions': {},
              'sample_aggregation': 'existing equal-region, evenly spaced per-view valid-pixel samples; repeated image observations remain',
              'full_aggregation': 'all train raster pixels, not unique world area or independent buildings'}
    for region, bound in binding['regions'].items():
        root = Path('/inputs')/region
        manifest_path = root/'input_manifest.json'
        assert sha(manifest_path) == bound['manifest']['sha256']
        manifest = read(manifest_path)
        split_path = root/manifest['split_path']
        assert sha(split_path) == manifest['split_sha256']
        split = read(split_path)
        train = {v['name']: v for v in split['train']}
        assert set(train) == {v['name'] for v in manifest['images'] if v['role'] == 'train'}
        prior_receipt = read(root/'prior/receipt.json')
        da3_receipt = read(root/'da3/receipt.json')
        inference = read(root/'da3/inference_receipt.json')
        assert prior_receipt['depth_frame'] == 'CAMERA_Z_METERS'
        assert da3_receipt['depth_units'] == 'metres'
        assert da3_receipt['policy']['align_to_input_ext_scale'] is True
        assert da3_receipt['reference_accessed'] is False
        assert sha(root/'da3/inference_receipt.json') == da3_receipt['inference_receipt_sha256']
        expected = {v['name']: v for v in bound['views']}
        sums = {k: {'count': 0, 'a_sum': 0., 'a_zero': 0, 'a_transition': 0, 'a_one': 0}
                for k in policies}
        counts = {'total_pixels': 0, 'both': 0, 'prior_only': 0, 'visual_only': 0, 'neither': 0}
        views = []
        samples = []
        for name, view in train.items():
            stem = Path(name).stem
            e = expected[stem]
            assert e['available_both']
            pp = root/manifest['training_paths']['prior_depth']/'raw_depth'/f'{stem}.npy'
            vp = root/manifest['training_paths']['da3_depth']/'raw_depth'/f'{stem}.npy'
            assert sha(pp) == e['prior_sha256'] and sha(vp) == e['visual_sha256']
            size = (view['width'], view['height'])
            prior = cv2.resize(np.load(pp, allow_pickle=False), size, interpolation=cv2.INTER_LINEAR)
            visual = cv2.resize(np.load(vp, allow_pickle=False), size, interpolation=cv2.INTER_LINEAR)
            pm = np.isfinite(prior) & (prior > 0)
            vm = np.isfinite(visual) & (visual > 0)
            both = pm & vm
            delta = np.abs(prior[both]-visual[both])
            signed = prior[both]-visual[both]
            n = len(delta)
            assert n == e['valid_pixels']
            local_counts = {'total_pixels': int(prior.size), 'both': n,
                            'prior_only': int(np.count_nonzero(pm & ~vm)),
                            'visual_only': int(np.count_nonzero(vm & ~pm)),
                            'neither': int(np.count_nonzero(~pm & ~vm))}
            for k, value in local_counts.items():
                counts[k] += value
            view_policy = {}
            for key, (t0, t1) in policies.items():
                row = summary(delta, t0, t1)
                for k, value in row.items():
                    sums[key][k] += value
                row = rates(row)
                row['source_mean_prior_multiplier'] = (n-row['a_sum']+local_counts['prior_only'])/int(pm.sum()) if pm.any() else None
                row['source_mean_visual_multiplier'] = (row['a_sum']+local_counts['visual_only'])/int(vm.sum()) if vm.any() else None
                view_policy[key] = row
            indices = np.linspace(0, n-1, min(n, 4096), dtype=np.int64)
            sample = np.stack([prior[both][indices], visual[both][indices]], axis=-1)
            samples.append(sample)
            views.append({'name': name, 'counts': local_counts,
                          'source_shapes': [list(prior.shape), list(visual.shape)],
                          'delta_quantiles_m': np.quantile(delta, [.1, .5, .9]).tolist(),
                          'signed_prior_minus_visual_quantiles_m': np.quantile(signed, [.1, .5, .9]).tolist(),
                          'camera_optical_axis_world_Z_component': float(view['R'][2][2]),
                          'policies': view_policy})
        arr = np.concatenate(samples)
        full = {}
        for key in policies:
            row = rates(sums[key])
            row['source_mean_prior_multiplier'] = (counts['both']-row['a_sum']+counts['prior_only'])/(counts['both']+counts['prior_only'])
            row['source_mean_visual_multiplier'] = (row['a_sum']+counts['visual_only'])/(counts['both']+counts['visual_only'])
            row['uniform_train_view_mean_a'] = float(np.mean([v['policies'][key]['mean_a'] for v in views]))
            row['uniform_train_view_source_mean_prior_multiplier'] = float(np.mean([v['policies'][key]['source_mean_prior_multiplier'] for v in views]))
            row['uniform_train_view_source_mean_visual_multiplier'] = float(np.mean([v['policies'][key]['source_mean_visual_multiplier'] for v in views]))
            full[key] = row
        result['regions'][region] = {
            'train_view_count': len(views), 'counts': counts,
            'both_fraction_of_all_train_pixels': counts['both']/counts['total_pixels'],
            'missing_training_map_count': 0,
            'sample': {key: rates(summary(frozen[region], *tau)) for key, tau in policies.items()},
            'full_paired': full,
            'even_view_sample_prior_depth_q10_q50_q90': np.quantile(arr[:, 0], [.1, .5, .9]).tolist(),
            'even_view_sample_visual_depth_q10_q50_q90': np.quantile(arr[:, 1], [.1, .5, .9]).tolist(),
            'even_view_sample_signed_delta_q10_q50_q90': np.quantile(arr[:, 0]-arr[:, 1], [.1, .5, .9]).tolist(),
            'even_view_sample_visual_over_prior_ratio_q10_q50_q90': np.quantile(arr[:, 1]/arr[:, 0], [.1, .5, .9]).tolist(),
            'semantics': {'prior_depth_frame': prior_receipt['depth_frame'],
                          'prior_pixel_center': prior_receipt['pixel_center'],
                          'da3_units': da3_receipt['depth_units'],
                          'da3_upsample': da3_receipt['upsample'],
                          'da3_extrinsics_preserved_driver_assertion': True,
                          'da3_inference_status': inference['status'],
                          'crs': manifest['crs']},
            'receipt_sha256': {str(p.relative_to(root)): sha(p) for p in [manifest_path, split_path, root/'prior/receipt.json', root/'da3/receipt.json', root/'da3/inference_receipt.json']},
            'views': views}
        print(json.dumps({'region': region, 'counts': counts, 'candidate_0p5_2': full['fixed_0p5_2']}), flush=True)
    result['pooled_equal_region_sample'] = {k: rates(summary(pooled, *v)) for k, v in policies.items()}
    result['source_records'] = {str(p.relative_to('/source')): sha(p) for p in [
        Path('/source/GeoGS/LoD2Depth/raycasting.py'),
        Path('/source/Depth-Anything-3/src/depth_anything_3/api.py'),
        Path('/source/Depth-Anything-3/src/depth_anything_3/utils/geometry.py')]}
    result['interpretation_limits'] = [
        'Camera-Z units and shared camera raster are verified conventions, not registration or visible-surface correctness.',
        'Prior raycast uses half-pixel centers while DA3 is a resized learned raster; no subpixel resampling correction was introduced.',
        'Large target discrepancy alone cannot identify whether prior, DA3, both, registration, occlusion or crop support caused it.',
        'The historical CRS receipt retains absolute_datum_calibration_verified=false; reuse does not resolve it.',
        'Fixed .5/2 is an exploratory physical ramp; inputs do not establish those values as source accuracy or uncertainty bounds.',
        'Full-pixel and equal-view distributions answer different questions; neither is unique surface area or independent evidence.'
    ]
    result['environment'] = {'python': platform.python_version(), 'numpy': np.__version__,
                             'opencv': cv2.__version__, 'cpu_only': True,
                             'image': 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'}
    result['wall_seconds'] = time.time()-started
    result['status'] = 'PASS_INPUT_CONVENTION_AUDIT_WITH_RECORDED_LIMITATIONS'
    with out.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(out), 'sha256': sha(out), 'wall_seconds': result['wall_seconds'],
                      'pooled': result['pooled_equal_region_sample']}), flush=True)


if __name__ == '__main__':
    main()
