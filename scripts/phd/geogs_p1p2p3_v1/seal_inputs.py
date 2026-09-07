"""Freeze the actual regional input bytes after all reference-free preflights."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from plyfile import PlyData


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def names(rows):
    return {Path(row['name']).stem for row in rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--region', choices=('P1', 'P2', 'P3'), required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--split', type=Path, required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker execution is required')
    if Path('/reference').exists() or Path('/artifacts/JointBuildGS').exists():
        raise RuntimeError('Seal with only the new input folder; reference access is forbidden')
    start = time.time()
    target = args.input / 'input_manifest.json'
    if target.exists():
        raise FileExistsError(target)
    config_bytes = args.config.read_bytes()
    cfg = json.loads(config_bytes)
    split = json.loads(args.split.read_text())
    train_key = 'train'
    eval_key = 'evaluation' if 'evaluation' in split else 'eval'
    train, evaluation = names(split[train_key]), names(split[eval_key])
    spec = cfg['regions'][args.region]
    validity_path = Path('/depth_validity_audit.json')
    validity = json.loads(validity_path.read_text())
    audited = validity['regions'][args.region]
    if validity['status'] != 'PASS_EXACT_CUBIC_AUDIT' or not audited['all_exact_cubic_byte_match'] or audited['native_negative'] or audited['native_nonfinite']:
        raise ValueError('Exact native-positive / official cubic depth audit is required')
    if len(train) != spec['expected_train'] or len(evaluation) != spec['expected_test'] or train & evaluation:
        raise ValueError('Unexpected train/evaluation membership')
    if train | evaluation != names(split['all']):
        raise ValueError('Split does not partition the frozen regional images')
    image_records = []
    for row in split['all']:
        path = args.input / 'scene/images' / row['name']
        if sha(path) != row['sha256']:
            raise ValueError(f'RGB bytes differ: {path}')
        image_records.append({'name': row['name'], 'image_id': row['image_id'],
                              'sha256': row['sha256'], 'role': 'train' if Path(row['name']).stem in train else 'evaluation'})
    depth_stats = {}
    shape = (cfg['image_resolution']['height'], cfg['image_resolution']['width'])
    for owner in ('prior', 'da3'):
        directory = args.input / owner / 'raw_depth'
        paths = sorted(directory.glob('*.npy'))
        if {p.stem for p in paths} != train:
            raise ValueError(f'{owner} depth membership differs from train-only split')
        rows = []
        for path in paths:
            array = np.load(path, mmap_mode='r', allow_pickle=False)
            if array.shape != shape or array.dtype.kind != 'f':
                raise ValueError(f'Depth shape/type mismatch: {path}')
            valid = np.isfinite(array) & (array > 0)
            if np.isneginf(array).any() or (owner == 'prior' and np.any(np.isfinite(array) & (array < 0))):
                raise ValueError(f'Invalid negative depth: {path}')
            if owner == 'da3' and not np.isfinite(array).all():
                raise ValueError(f'Nonfinite visual depth: {path}')
            if owner == 'da3' and not valid.any():
                raise ValueError(f'Empty visual depth: {path}')
            rows.append({'name': path.stem, 'valid_pixels': int(valid.sum()), 'pixels': array.size,
                         'positive_inf_ray_misses': int(np.isposinf(array).sum()),
                         'nan_ray_misses': int(np.isnan(array).sum()),
                         'negative_cubic_pixels': int(np.sum(array < 0)),
                         'min_valid_m': float(array[valid].min()) if valid.any() else None,
                         'max_valid_m': float(array[valid].max()) if valid.any() else None})
        depth_stats[owner] = rows
    if sum(row['negative_cubic_pixels'] for row in depth_stats['da3']) != audited['upsampled_negative']:
        raise ValueError('DA3 nonpositive pixel counts differ from the exact cubic audit')
    initialization = args.input / 'initialization/lod2_pcd.ply'
    cached = args.input / 'scene/sparse_lod/0/points3D.ply'
    if not cached.is_file() or not initialization.is_file():
        raise ValueError('Initialization/protection point cloud is absent')
    points = PlyData.read(cached)['vertex']
    if len(points) == 0:
        raise ValueError('No initialized Gaussians')
    xyz = np.column_stack([points[key] for key in ('x', 'y', 'z')])
    if not np.isfinite(xyz).all():
        raise ValueError('Nonfinite initialization')
    if not (args.input / 'scene/sparse/0/points3D.ply').is_file():
        raise ValueError('Native render camera loader would try writing an uncached PLY')
    calibration = json.loads((args.input / 'scene/jbgs_calibration.json').read_text())
    if set(calibration['images']) != train | evaluation:
        raise ValueError('Calibration metadata does not cover exactly the regional views')
    # Bind every actual payload/receipt, including source-byte and batch ledgers.
    files = []
    for path in sorted(args.input.rglob('*')):
        if path.is_file():
            if path.is_symlink() and not path.resolve().is_relative_to(args.input.resolve()):
                raise ValueError(f'Input symlink escapes the isolated package: {path}')
            files.append({'path': str(path.relative_to(args.input)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    manifest = {'task_id': cfg['task_id'], 'status': 'INPUTS_SEALED_FOR_EXECUTION', 'region': args.region,
                'scientific_verdict': None, 'created_unix': time.time(), 'seal_seconds': time.time() - start,
                'config_sha256': hashlib.sha256(config_bytes).hexdigest(),
                'split_path': str(args.split.relative_to(args.input)), 'split_sha256': sha(args.split),
                'training_paths': {'prior_depth': 'prior', 'da3_depth': 'da3',
                                   'protection_pcd': 'initialization/lod2_pcd.ply'},
                'source_role': 'ALS_SURFACE_ADAPTATION_WITH_EXPLICIT_CALIBRATION',
                'crs': cfg['crs'], 'images': image_records, 'initialization_points': len(points),
                'depth_statistics': depth_stats, 'files': files,
                'reference_accessed': False, 'independent_acquisition_test': False,
                'prior_miss_encoding': 'official positive-inf/NaN preserved; native finite-positive loss mask excludes them',
                'da3_cubic_validity_audit_sha256': sha(validity_path),
                'da3_negative_encoding': 'verified exact official cubic overshoot; preserved and excluded by native finite-positive loss mask',
                'script_sha256': sha(__file__)}
    with target.open('x') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'status': manifest['status'], 'region': args.region, 'files': len(files),
                      'initialization_points': len(points), 'sha256': sha(target)}))


if __name__ == '__main__':
    main()
