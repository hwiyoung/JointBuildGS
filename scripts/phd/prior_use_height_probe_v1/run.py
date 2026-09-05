"""Bounded native-ALS photometric height probe; never a full current-use verdict."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

import cv2
import numpy as np

from src.stage2.colmap_io import read_cameras_bin, read_images_bin
from scripts.phd.warp_ncc_v1.run import project_pixels
from scripts.phd.prior_use_height_probe_v1.photometry import measure_height_sweep
from scripts.phd.prior_use_height_probe_v1.decision import aggregate_height_sweep, validate_decision_logic
from scripts.phd.prior_use_height_probe_v1.figures import make_figures
from scripts.phd.prior_use_height_probe_v1.verify import verify_photometry

REPO = Path(__file__).resolve().parents[3]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def sample_indices(length, cap):
    return np.linspace(0, length - 1, min(length, cap), dtype=np.int64)


def load_groups(root, cfg):
    inputs, spec = cfg['inputs'], cfg['groups']
    patch_root = root / inputs['patch_root']
    tile = np.memmap(root / inputs['als_tile'], dtype='<f4', mode='r').reshape(-1, 3)
    original_rows = np.load(patch_root / 'point_rows_als.npy', allow_pickle=False)
    metadata = np.load(patch_root / 'points_als.npy', allow_pickle=False)
    patches = np.load(patch_root / 'patches_als.npy', allow_pickle=False)
    assert len(original_rows) == len(metadata)
    assert np.all(original_rows < len(tile)) and len(np.unique(original_rows)) == len(original_rows)
    xyz_all = np.asarray(tile[original_rows], dtype=np.float64)
    assert np.isfinite(xyz_all).all()
    planar_ids = patches['patch_id'][patches['type'] == spec['planar_type']]
    planar = np.isin(metadata['patch_id'], planar_ids)
    xy_bins = np.floor(xyz_all[:, :2] / spec['grid_size_m']).astype(np.int64)
    group_members = {}
    for i in np.flatnonzero(planar):
        key = (int(metadata['patch_id'][i]), int(xy_bins[i, 0]), int(xy_bins[i, 1]))
        group_members.setdefault(key, []).append(int(i))
    eligible = sorted(key for key, rows in group_members.items() if len(rows) >= spec['min_points'])
    if not eligible:
        raise ValueError('No native prior groups meet the predeclared geometry-only selection')
    selected = [eligible[i] for i in sample_indices(len(eligible), spec['max_groups'])]
    rows, labels, groups = [], [], []
    for gi, key in enumerate(selected):
        members = np.array(group_members[key], dtype=np.int64)
        members = members[np.argsort(original_rows[members], kind='stable')]
        sampled = members[sample_indices(len(members), spec['max_points_per_group'])]
        points = xyz_all[members]
        singular = np.linalg.svd((points[:, :2] - points[:, :2].mean(0)) / np.sqrt(len(points)), compute_uv=False)
        groups.append({
            'group_index': gi, 'patch_id': key[0], 'grid_ix': key[1], 'grid_iy': key[2],
            'native_count': len(members), 'sample_count': len(sampled),
            'native_tile_rows': original_rows[members].astype(int).tolist(),
            'sampled_tile_rows': original_rows[sampled].astype(int).tolist(),
            'centroid_scene_local': points.mean(0).tolist(),
            'xy_spread_singular_values_m': singular.tolist(),
            'bbox_min': points.min(0).tolist(), 'bbox_max': points.max(0).tolist(),
        })
        rows.extend(sampled.tolist())
        labels.extend([gi] * len(sampled))
    rows = np.array(rows, dtype=np.int64)
    return xyz_all[rows], np.array(labels, dtype=np.int64), original_rows[rows], groups, {
        'prism_native_points': len(original_rows), 'planar_native_points': int(planar.sum()),
        'all_nonempty_planar_groups': len(group_members), 'eligible_groups': len(eligible),
        'excluded_small_groups': len(group_members) - len(eligible),
        'selected_groups': len(selected), 'unsampled_eligible_groups': len(eligible) - len(selected),
        'sampled_native_points': len(rows),
        'selected_unique_xy_cells': len(set(key[1:] for key in selected)),
        'area_interpretation': 'group and nominal XY-cell counts only; no confirmed physical-area coverage',
    }


def main(config_path):
    start, started = time.monotonic(), now()
    cfg = json.loads(config_path.read_text())
    assert cfg['schema'] == 'jointbuildgs.phd.prior_use_height_probe.v1'
    assert cfg['scientific_verdict'] is None and cfg['scope']['full_current_use_action'] is None
    assert cfg['status'] == 'USER_DIRECTED_DEVELOPMENT_NON_CONFIRMATORY'
    root, output = Path(cfg['artifact_root']), Path(cfg['output_root'])
    if not output.is_dir() or any(output.iterdir()):
        raise ValueError('Output must be a separately mounted, empty, newly created directory')
    write_json(output / 'STARTED.json', {'task_id': cfg['task_id'], 'started_utc': started, 'scientific_verdict': None})
    try:
        cv2.setNumThreads(1)
        checks = validate_decision_logic()
        photometry_checks = verify_photometry()
        inputs = cfg['inputs']
        camera_root = root / inputs['camera_root']
        expected = {
            root / inputs['als_tile']: inputs['als_tile_sha256'],
            root / inputs['views']: inputs['views_sha256'],
            camera_root / 'sparse/cameras.bin': inputs['cameras_sha256'],
            camera_root / 'sparse/images.bin': inputs['images_sha256'],
            REPO / inputs['crosswalk']: inputs['crosswalk_sha256'],
        }
        expected.update({root / inputs['patch_root'] / name: digest for name, digest in inputs['patch_files'].items()})
        for path, digest in expected.items():
            if sha(path) != digest:
                raise ValueError(f'Input hash mismatch: {path}')
        xyz, group_index, tile_rows, groups, denominators = load_groups(root, cfg)
        cameras = read_cameras_bin(camera_root / 'sparse/cameras.bin')
        images = read_images_bin(camera_root / 'sparse/images.bin')
        frozen = json.loads((root / inputs['views']).read_text())['views']
        crosswalk = json.loads((REPO / inputs['crosswalk']).read_text())['rows']
        exact = {int(row['colmap_image_id']) for row in crosswalk}
        assert len(exact) == 937
        reference = np.median(xyz, axis=0)
        candidates, by_id = [], {}
        for view in frozen:
            iid = int(view['colmap_image_id'])
            assert iid in exact and images[iid].name == view['name']
            assert iid not in by_id
            by_id[iid] = view
            im = images[iid]
            cam = cameras[im.camera_id]
            u, v, z, _, _, inside = project_pixels(xyz, im.R(), im.tvec, cam.K(), cam.width, cam.height)
            inside &= (u >= 1) & (u < cam.width - 2) & (v >= 1) & (v < cam.height - 2)
            centre = -im.R().T @ im.tvec
            candidates.append({'image_id': iid, 'name': im.name,
                               'native_in_fov_fraction': float(inside.mean()),
                               'distance_to_reference_m': float(np.linalg.norm(centre - reference)),
                               'image_sha256': view['image_sha256']})
        candidates.sort(key=lambda row: (-row['native_in_fov_fraction'], row['distance_to_reference_m'], row['image_id']))
        selected = candidates[:cfg['views']['max_views']]
        view_ids = [row['image_id'] for row in selected]
        for row in selected:
            path = camera_root / 'images' / row['name']
            expected[path] = row['image_sha256']
            if sha(path) != row['image_sha256']:
                raise ValueError(f'Image hash mismatch: {path}')
        sources = list((REPO / 'scripts/phd/prior_use_height_probe_v1').glob('*.py'))
        sources += list((REPO / 'scripts/phd/prior_use_height_probe_v1').glob('*.sh'))
        sources += [REPO / name for name in (
            'scripts/phd/warp_ncc_v1/run.py', 'scripts/phd/evidence_bank_v1/run.py',
            'src/stage2/colmap_io.py',
            'docs/experiments/phd/prior_use_height_probe_v1/DESIGN_ko_v1.md')]
        sources.append(config_path.resolve())
        source_hashes = {str(path.relative_to(REPO)): sha(path) for path in sources}
        snapshot = output / 'source_snapshot'
        for path in sources:
            dest = snapshot / path.relative_to(REPO)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        write_json(output / 'premeasurement.json', {
            'started_utc': started, 'frozen_before_measurement_utc': now(), 'config': cfg,
            'source_sha256': source_hashes, 'input_sha256': {str(p): h for p, h in expected.items()},
            'git_head': os.environ.get('JBGS_SOURCE_GIT_HEAD', 'UNKNOWN'),
            'container_image_id': os.environ.get('JBGS_CONTAINER_IMAGE_ID', 'UNKNOWN'),
            'denominators': denominators, 'selected_views': selected,
            'versions': {'python': sys.version, 'numpy': np.__version__, 'opencv': cv2.__version__, 'platform': platform.platform()},
            'scientific_verdict': None,
        })
        write_json(output / 'groups.json', groups)
        write_json(output / 'view_selection.json', {'all_ranked': candidates, 'selected_image_ids': view_ids})
        np.savez_compressed(output / 'native_membership.npz', xyz=xyz, group_index=group_index, tile_rows=tile_rows)
        print(json.dumps({'premeasurement': 'PASS', 'denominators': denominators, 'selected_views': view_ids}), flush=True)
        def load_image(iid):
            path = camera_root / 'images' / images[iid].name
            gray = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if gray is None:
                raise ValueError(f'Image decoding failed: {path}')
            return gray.astype(np.float32)
        params = cfg['measurement']
        count = round((params['height_max_m'] - params['height_min_m']) / params['height_step_m']) + 1
        heights = np.linspace(params['height_min_m'], params['height_max_m'], count)
        result = measure_height_sweep(xyz, group_index, heights, cameras, images, view_ids, load_image, params,
                                      progress=lambda done, total: print(f'Image projection {done}/{total}', flush=True))
        np.savez_compressed(output / 'measurements.npz', **{k: v for k, v in result.items() if isinstance(v, np.ndarray)})
        write_json(output / 'measurement_metadata.json', result['metadata'])
        aggregation = aggregate_height_sweep(result, cfg)
        rows = aggregation['rows']
        write_json(output / 'decision_rows.json', rows)
        write_json(output / 'decision_summary.json', aggregation['summary'])
        np.savez_compressed(output / 'curves.npz', heights=heights, **{'angle_' + key: value for key, value in aggregation['curves'].items()})
        np.savez_compressed(output / 'common_pair_masks.npz', **{'angle_' + key: value for key, value in aggregation['pair_masks'].items()})
        if rows:
            with (output / 'decision_rows.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})
        figures = make_figures(output, heights, aggregation['curves'], groups, rows)
        # A photograph with projected native candidates locates cases; it is not a visibility label.
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        iid = view_ids[0]
        im, cam = images[iid], cameras[images[iid].camera_id]
        u, v, _, _, _, inside = project_pixels(xyz, im.R(), im.tvec, cam.K(), cam.width, cam.height)
        fig, ax = plt.subplots(figsize=(14, 10))
        ax.imshow(load_image(iid), cmap='gray', vmin=0, vmax=255)
        ax.scatter(u[inside] - .5, v[inside] - .5, c=group_index[inside], cmap='turbo', s=3, alpha=.65)
        for gi in range(len(groups)):
            mask = inside & (group_index == gi)
            if mask.any():
                ax.text(float(np.median(u[mask]) - .5), float(np.median(v[mask]) - .5), str(gi), fontsize=7,
                        color='white', bbox={'facecolor': 'black', 'alpha': .55, 'pad': .6})
        ax.set_title(f'Native prior group IDs projected in image {iid}; occlusion unverified')
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(output / 'native_prior_location.png', dpi=160)
        plt.close(fig)
        figures['native_prior_location'] = {'path': 'native_prior_location.png', 'image_id': iid, 'image_sha256': by_id[iid]['image_sha256']}
        write_json(output / 'figures.json', figures)
        # Validate stored support against exact native membership and validate immutability.
        for pi in range(len(result['pair_indices'])):
            a, b = result['support_offsets'][pi:pi+2]
            support = result['support_point_indices'][a:b]
            digest = hashlib.sha256(np.asarray(support, dtype='<i8').tobytes()).hexdigest()
            assert digest == result['support_sha256'][pi]
            assert np.array_equal(np.bincount(group_index[support], minlength=len(groups)), result['count'][pi])
        finite = result['rho'][np.isfinite(result['rho'])]
        assert np.all((finite >= -1) & (finite <= 1))
        assert all(row['full_current_use_action'] is None for row in rows)
        assert all(sha(path) == digest for path, digest in expected.items())
        assert all(sha(REPO / path) == digest for path, digest in source_hashes.items())
        outputs = {str(path.relative_to(output)): sha(path) for path in output.rglob('*') if path.is_file()}
        write_json(output / 'TECHNICAL_RETURN.json', {
            'task_id': cfg['task_id'], 'status': 'TECHNICAL_COMPLETE_NON_CONFIRMATORY',
            'started_utc': started, 'completed_utc': now(), 'elapsed_seconds': time.monotonic() - start,
            'denominators': denominators, 'pair_count': len(result['pair_indices']),
            'height_count': len(heights), 'decision_row_count': len(rows), 'figures': figures,
            'validation': {'decision_logic': checks, 'photometry': photometry_checks, 'support_hashes_and_counts': 'PASS',
                           'source_input_immutability': 'PASS', 'full_current_use_actions_null': 'PASS'},
            'output_sha256': outputs, 'full_current_use_action': None, 'scientific_verdict': None,
        })
        print(json.dumps({'status': 'TECHNICAL_COMPLETE_NON_CONFIRMATORY', 'output': str(output), 'elapsed_seconds': time.monotonic() - start}), flush=True)
    except Exception:
        write_json(output / 'FAILURE.json', {'time_utc': now(), 'traceback': traceback.format_exc(), 'scientific_verdict': None})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REPO / 'configs/phd/prior_use_height_probe_v1/p2_v1.json')
    main(parser.parse_args().config)
