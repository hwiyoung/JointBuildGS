"""Bind existing train MVS bytes and a deterministic camera neighbor graph."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, '/repo')
from src.phd.geogs_mvs_pgsr_v1.mvs_depth import load_split_manifest, read_colmap_depth, build_neighbor_graph


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--artifact-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker execution required')
    config = json.loads(args.config.read_text())
    config_sha = sha(args.config)
    base = args.artifact_root / config['base_relative']
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {'config_sha256': config_sha, 'script_sha256': sha(__file__),
               'loader_sha256': sha('/repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py'),
               'scientific_verdict': None, 'regions': {}}
    shutil.copyfile(args.config, args.output / 'experiment.json')
    if sha(args.output / 'experiment.json') != config_sha:
        raise ValueError('Exact configuration snapshot differs')
    for region in config['regions']:
        region_output = args.output / region
        (region_output / 'native').mkdir(parents=True, exist_ok=False)
        original = base / 'inputs' / region
        manifest_path = original / 'input_manifest.json'
        original_manifest = json.loads(manifest_path.read_text())
        split_path = original / 'scene' / 'split_manifest_da3_v2.json'
        split_row = next(row for row in original_manifest['files'] if row['path'] == 'scene/split_manifest_da3_v2.json')
        split = load_split_manifest(split_path, split_row['sha256'])
        arrays, bound = {}, []
        for view in split['train']:
            path = Path(view['maps']['depth']['path'])
            native_source = args.artifact_root / path.relative_to('/artifacts/JointBuildGS')
            rgb_source = args.artifact_root / Path(view['path']).relative_to('/artifacts/JointBuildGS')
            if sha(rgb_source) != view['sha256']:
                raise ValueError('Bound RGB changed: ' + view['name'])
            native = read_colmap_depth(native_source, view['maps']['depth'])
            arrays[view['name']] = native
            local = Path('native') / (view['name'] + '.geometric.bin')
            shutil.copyfile(native_source, region_output / local)
            if sha(region_output / local) != view['maps']['depth']['sha256']:
                raise ValueError('Copied native depth differs')
            bound.append({**view, 'local_depth': str(local),
                          'native_positive_finite_pixels': int((np.isfinite(native) & (native > 0)).sum())})
        graph = build_neighbor_graph(split['train'], arrays, maximum_neighbors=config['geometry']['maximum_neighbors'],
                                     maximum_axis_angle_degrees=config['geometry']['neighbor_axis_angle_degrees'],
                                     maximum_baseline_depth_ratio=config['geometry']['neighbor_baseline_depth_ratio'])
        degrees = [len(row['selected']) for row in graph['graph'].values()]
        if max(degrees) < 1:
            write(region_output / 'failed_neighbor_graph.json', graph)
            raise ValueError('Region has no valid geometry neighbors: ' + region)
        binding = {'schema': 'JBGS_MVS_PGSR_INPUT_v1', 'region': region, 'config_sha256': config_sha,
                   'parent_input_manifest_sha256': sha(manifest_path), 'split_sha256': sha(split_path),
                   'train': bound, 'evaluation_names': [view['name'] for view in split['evaluation']],
                   'neighbor_graph': graph, 'scientific_verdict': None}
        write(region_output / 'bindings.json', binding)
        receipt['regions'][region] = {'binding_sha256': sha(region_output / 'bindings.json'),
                                     'train_count': len(bound), 'neighbor_degree_min': min(degrees),
                                     'neighbor_degree_max': max(degrees),
                                     'empty_neighbor_names': [name for name, row in graph['graph'].items() if not row['selected']],
                                     'native_valid_fraction_median': float(np.median([v['native_positive_finite_pixels'] / (v['maps']['depth']['width'] * v['maps']['depth']['height']) for v in bound]))}
        print(json.dumps({'region': region, **receipt['regions'][region]}), flush=True)
    receipt['status'] = 'PASS'
    write(args.output / 'receipt.json', receipt)


if __name__ == '__main__':
    main()
