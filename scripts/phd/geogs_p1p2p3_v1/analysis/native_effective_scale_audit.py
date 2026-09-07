"""Measure camera-dependent defaults in existing native and regional inputs."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from plyfile import PlyData


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    base, config_path, output = map(Path, sys.argv[1:])
    config = json.loads(config_path.read_text())
    inputs = {}

    def read(relative):
        path = base / relative
        inputs[relative] = digest(path)
        return json.loads(path.read_text())

    native = sorted(read(config['native_cameras']), key=lambda row: row['img_name'])
    native_train = [row for i, row in enumerate(native) if i % config['native_llffhold'] != 0]
    groups = {'native_example': np.asarray([row['position'] for row in native_train])}
    for region in config['regions']:
        split = read(f'inputs/{region}/scene/split_manifest_da3_v2.json')
        rows = split['train']
        if isinstance(rows[0], str):
            by_name = {row['name']: row for row in split['all']}
            rows = [by_name[name] for name in rows]
        groups[region] = np.asarray([-np.asarray(row['R']).T @ np.asarray(row['t']) for row in rows])
    results = []
    for name, centers in groups.items():
        extent = float(1.1 * np.linalg.norm(centers - centers.mean(axis=0), axis=1).max())
        results.append({'condition': name, 'train_views': len(centers), 'camera_extent': extent,
                        'clone_split_scale_boundary': config['percent_dense'] * extent,
                        'initial_xyz_lr': config['position_lr_init'] * extent,
                        'mean_camera_draws_by_30000': config['iterations'] / len(centers),
                        'mean_camera_draws_by_15000': config['densify_until_iter'] / len(centers)})
    initialization = []
    for relative in ['native_example_retry_compat_v1/output/model/input.ply',
                     'native_example/scene/sparse_lod/0/points3D.ply',
                     'native_example/scene/sparse/0/points3D.ply']:
        path = base / relative
        inputs[relative] = digest(path)
        initialization.append({'path': relative, 'sha256': inputs[relative],
                               'points': len(PlyData.read(str(path))['vertex'].data)})
    assert initialization[0]['sha256'] == initialization[1]['sha256']
    assert initialization[0]['sha256'] != initialization[2]['sha256']
    source_hashes = {name: digest(base / name / 'scene/gaussian_model.py')
                     for name in ['sources/GeoGS', 'sources/GeoGS-state-camera-v1']}
    assert len(set(source_hashes.values())) == 1
    result = {'status': 'PASS_READONLY_EFFECTIVE_SCALE_AUDIT', 'scientific_verdict': None,
              'config': config, 'results': results, 'initialization': initialization,
              'input_sha256': inputs, 'gaussian_source_sha256': source_hashes,
              'script_sha256': digest(Path(__file__)), 'config_sha256': digest(config_path),
              'new_training_steps': 0,
              'limitations': 'Scale boundary requires gradient and protection eligibility. Camera draws are not per-surface update counts. No causal attribution or paper-matched outcome claim.'}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'results': results, 'initialization': initialization}))


if __name__ == '__main__':
    main()
