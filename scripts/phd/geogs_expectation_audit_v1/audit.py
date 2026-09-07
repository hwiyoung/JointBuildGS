"""Read frozen input metadata, sample IDs and cached distances only."""
import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

import numpy as np


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--image-id', required=True)
    p.add_argument('--git-commit', required=True)
    a = p.parse_args()
    cfg = json.loads(a.config.read_text())
    a.output.mkdir(exist_ok=False, parents=True)
    inputs = {}

    def source(rel):
        path = a.source / rel
        inputs.setdefault(rel, sha(path))
        return path

    def read_json(rel):
        return json.loads(source(rel).read_text())

    evidence = {'task_id': cfg['task_id'], 'scientific_verdict': None}
    region_rows = []
    for region in cfg['regions']:
        prefix = f'inputs/{region}'
        manifest = read_json(f'{prefix}/input_manifest.json')
        split_path = f"{prefix}/{manifest['split_path']}"
        split = read_json(split_path)
        assert inputs[split_path] == manifest['split_sha256']
        train = {r['name'] for r in split['train']}
        evaluation = {r['name'] for r in split['evaluation']}
        assert not train & evaluation
        assert train | evaluation == {r['name'] for r in split['all']}
        for role in ['prior', 'da3']:
            assert {r['name'] for r in manifest['depth_statistics'][role]} == {Path(n).stem for n in train}
        region_rows.append({'region': region, 'train_count': len(train), 'evaluation_count': len(evaluation),
                            'prior_depth_count': len(manifest['depth_statistics']['prior']),
                            'da3_depth_count': len(manifest['depth_statistics']['da3']),
                            'training_paths': manifest['training_paths'], 'source_role': manifest['source_role']})
        if region == 'P2':
            selected = []
            for row in manifest['images']:
                if row['image_id'] in cfg['p2_photo_ids']:
                    rel = f"{prefix}/scene/images/{row['name']}"
                    assert sha(source(rel)) == row['sha256']
                    selected.append(dict(row, source_relative_path=rel))
            assert len(selected) == len(cfg['p2_photo_ids'])
            evidence['selected_p2_photos'] = selected
            sealed_files = {r['path']: r['sha256'] for r in manifest['files']}
    evidence['input_roles'] = region_rows
    evidence['comparison_mvs_lineage'] = read_json('contracts/evaluation_sources_v1.json')['baselines']

    prefix = 'inputs/P2/initialization'
    init = read_json(f'{prefix}/receipt.json')
    with np.load(source(f'{prefix}/all_surface_samples.npz'), allow_pickle=False) as z:
        xyz = z['xyz']
    ids = np.load(source(f'{prefix}/retained_sample_ids.npy'), allow_pickle=False)
    assert len(np.unique(ids)) == len(ids) == init['counts']['retained']
    assert ids.min() >= 0 and ids.max() < len(xyz)
    retained = np.zeros(len(xyz), dtype=bool)
    retained[ids] = True
    bounds = np.array(cfg['p2_initialization_window']['bounds_half_open'])
    window = ((xyz >= bounds[:, 0]) & (xyz < bounds[:, 1])).all(axis=1)
    bins = []
    for lo in np.arange(bounds[1, 0], bounds[1, 1], cfg['p2_initialization_window']['y_bin_width_m']):
        hi = min(lo + cfg['p2_initialization_window']['y_bin_width_m'], bounds[1, 1])
        mask = window & (xyz[:, 1] >= lo) & (xyz[:, 1] < hi)
        bins.append({'y_min': float(lo), 'y_max': float(hi), 'sampled': int(mask.sum()),
                     'retained': int((mask & retained).sum()), 'excluded': int((mask & ~retained).sum())})
    for rel in ['initialization/lod2_pcd.ply', 'scene/sparse_lod/0/points3D.ply']:
        key = f'inputs/P2/{rel}'
        assert sha(source(key)) == sealed_files[rel]
    assert inputs['inputs/P2/initialization/lod2_pcd.ply'] == inputs['inputs/P2/scene/sparse_lod/0/points3D.ply']
    # Independently read the actual trainer initialization coordinates, not just IDs.
    from plyfile import PlyData
    vertices = PlyData.read(str(a.source / 'inputs/P2/scene/sparse_lod/0/points3D.ply'))['vertex']
    trainer_xyz = np.column_stack([vertices[k] for k in ('x', 'y', 'z')]).astype(np.float64)
    assert trainer_xyz.shape == xyz[ids].shape
    max_delta = float(np.max(np.abs(trainer_xyz - xyz[ids])))
    assert np.allclose(trainer_xyz, xyz[ids], rtol=0, atol=2e-5)
    evidence['p2_initialization_window'] = {
        'config': cfg['p2_initialization_window'], 'source_total': len(xyz), 'retained_total': len(ids),
        'sampled_in_window': int(window.sum()), 'retained_in_window': int((window & retained).sum()),
        'actual_trainer_xyz_max_abs_delta_m': max_delta, 'y_bins': bins,
        'interpretation': 'Spatial sample membership and trainer transfer, not correctness, visibility sufficiency, or surface continuity.'}

    transitions = []
    for condition in cfg['raw_post_pairs']:
        arrays = {}
        for kind in ['raw', 'post']:
            rel = f"evaluation/geometry/P2/{condition}.final.{kind}/{cfg['setting']}"
            metric = read_json(rel + '.json')
            with np.load(source(rel + '.npz'), allow_pickle=False) as z:
                arrays[kind] = {k: z[k] for k in ['reference_points', 'reference_original_indices', 'reference_to_triangle_distance']}
            assert metric['mesh_res'] == 1024
        for key in ['reference_points', 'reference_original_indices']:
            assert np.array_equal(arrays['raw'][key], arrays['post'][key])
        raw = arrays['raw']['reference_to_triangle_distance']
        post = arrays['post']['reference_to_triangle_distance']
        assert np.isfinite(raw).all() and np.isfinite(post).all()
        for threshold in cfg['thresholds_m']:
            hit_raw, hit_post = raw < threshold, post < threshold
            row = {'condition': condition, 'mesh_res': 1024, 'threshold_m': threshold, 'reference_count': len(raw),
                   'raw_hits': int(hit_raw.sum()), 'post_hits': int(hit_post.sum()),
                   'lost': int((hit_raw & ~hit_post).sum()), 'gained': int((~hit_raw & hit_post).sum()),
                   'raw_recall': float(hit_raw.mean()), 'post_recall': float(hit_post.mean()),
                   'distance_decreased_over_1e_6m': int((post < raw - 1e-6).sum())}
            assert row['raw_hits'] - row['post_hits'] == row['lost'] - row['gained']
            transitions.append(row)
    with (a.output / 'raw_post_reference_transitions.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(transitions[0]))
        writer.writeheader(); writer.writerows(transitions)
    evidence['raw_post_transitions'] = transitions
    evidence['input_files'] = inputs
    evidence['inputs_unchanged'] = all(sha(a.source / rel) == digest for rel, digest in inputs.items())
    assert evidence['inputs_unchanged']
    evidence['execution'] = {'python': platform.python_version(), 'numpy': np.__version__, 'image_id': a.image_id,
                             'git_commit': a.git_commit, 'script_sha256': sha(Path(__file__)), 'config_sha256': sha(a.config),
                             'new_training': 0, 'new_scene_renders': 0, 'new_mesh_extractions': 0, 'new_distance_queries': 0}
    (a.output / 'evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': 'PASS_STATIC_EVIDENCE_AUDIT', 'scientific_verdict': None,
                      'input_files': len(inputs), 'retained_in_window': evidence['p2_initialization_window']['retained_in_window'],
                      'raw_post_rows': len(transitions)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
