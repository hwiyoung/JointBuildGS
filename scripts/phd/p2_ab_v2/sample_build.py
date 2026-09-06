"""Freeze continuous native P2 geometry and actual original-image pinhole crops.

Run in Docker. All source inputs are read-only; existing output roots fail closed.
Reference point clouds and LoD geometry are deliberately not read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from src.stage2.colmap_io import read_cameras_bin, read_images_bin

REPO = Path(__file__).resolve().parents[3]


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def record(path, expected=None):
    path = Path(path)
    got = digest(path)
    if expected is not None and got != expected:
        raise ValueError(f'Hash mismatch: {path}: {got} != {expected}')
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': got}


def dense_record(path):
    if not path.exists():
        return {'path': str(path), 'available': False, 'dimensions': None}
    with path.open('rb') as f:
        header = b''
        while header.count(b'&') < 3 and len(header) < 128:
            header += f.read(1)
    dimensions = [int(v) for v in header.decode('ascii').split('&')[:3]]
    return dict(record(path), available=True, dimensions=dimensions)


def quantiles(array):
    a = np.asarray(array)
    return dict(zip(['minimum', 'p10', 'median', 'p90', 'maximum'],
                    np.percentile(a, [0, 10, 50, 90, 100], axis=0).tolist())) if len(a) else None


def project_camera(camera_xyz, K):
    uvh = camera_xyz @ K.T
    return uvh[:, :2] / uvh[:, 2:3]


def build(config_path):
    started = time.time()
    cfg = read(config_path)
    root = Path(cfg['artifact_root'])
    out = root / cfg['output_relative_root']
    out.mkdir(parents=True, exist_ok=False)
    for name in ['images', 'valid', 'source_snapshot']:
        (out / name).mkdir()
    try:
        cv2.setNumThreads(2)
        common = root / cfg['common_relative_root']
        inputs = [record(common / 'units.npz', cfg['expected_native_sha256'])]
        for name in ['views.json', 'sample_manifest.json', 'frame_audit.json', 'units.json']:
            inputs.append(record(common / name))
        old_manifest, old_views = read(common / 'sample_manifest.json'), read(common / 'views.json')
        frame_audit = read(common / 'frame_audit.json')
        native = np.load(common / 'units.npz')
        xyz = np.concatenate([native['mvs_xyz'], native['als_xyz']]).astype(np.float64)
        assert len(xyz) == 330679 + 45986
        original_cameras = root / cfg['raw_model_relative_root'] / 'cameras.bin'
        original_images = root / cfg['raw_model_relative_root'] / 'images.bin'
        dense_images = root / cfg['dense_relative_root'] / 'sparse/images.bin'
        raw_cams = read_cameras_bin(original_cameras)
        raw_poses, low_poses = read_images_bin(original_images), read_images_bin(dense_images)
        assert set(raw_poses) == set(low_poses) and len(raw_poses) == 937
        for iid, im in raw_poses.items():
            low = low_poses[iid]
            assert im.name == low.name and np.array_equal(im.R(), low.R()) and np.array_equal(im.tvec, low.tvec)
        inventory_path = REPO / cfg['member_inventory']
        with inventory_path.open() as f:
            inventory = {r['basename']: r for r in csv.DictReader(f)}
        inputs += [record(p) for p in [original_cameras, original_images, dense_images,
                                      inventory_path, REPO / cfg['derivative_lineage']]]
        for name, destination in [('units.npz', 'native_geometry.npz'), ('units.json', 'units.json'),
                                  ('frame_audit.json', 'frame_audit.json')]:
            shutil.copyfile(common / name, out / destination)
        shutil.copyfile(config_path, out / 'source_snapshot/config.json')
        shutil.copyfile(__file__, out / 'source_snapshot/sample_build.py')
        rows, audits = [], []
        source_offsets = {'mvs': (0, len(native['mvs_xyz'])), 'als': (len(native['mvs_xyz']), len(xyz))}
        for index, old in enumerate(old_views['views']):
            iid = old['image_id']
            im = raw_poses[iid]
            assert im.name == old['name'] and np.array_equal(im.R(), np.array(old['R'])) and np.array_equal(im.tvec, np.array(old['t']))
            camera = raw_cams[im.camera_id]
            assert camera.model == 'FULL_OPENCV'
            K = camera.K()
            dist = camera.params[4:]
            raw_path = root / cfg['raw_image_relative_root'] / im.name
            raw_record = record(raw_path, inventory[im.name]['sha256'])
            inputs.append(raw_record)
            raw_bgr = cv2.imread(str(raw_path), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
            assert raw_bgr.shape[:2] == (camera.height, camera.width)
            cxyz = xyz @ im.R().T + im.tvec
            uv = project_camera(cxyz, K)
            positive = cxyz[:, 2] > 1e-6
            pad = cfg['crop_padding_px']
            lo = np.floor(uv[positive].min(axis=0)).astype(int) - pad
            hi = np.ceil(uv[positive].max(axis=0)).astype(int) + pad + 1
            x0, y0 = np.maximum(lo, 0)
            x1, y1 = np.minimum(hi, [camera.width, camera.height])
            width, height = int(x1-x0), int(y1-y0)
            assert width > 0 and height > 0
            cropK = K.copy()
            cropK[0, 2] -= x0
            cropK[1, 2] -= y0
            mapx, mapy = cv2.initUndistortRectifyMap(K, dist, np.eye(3), cropK, (width, height), cv2.CV_32FC1)
            valid = (mapx >= 0) & (mapy >= 0) & (mapx < camera.width - 1) & (mapy < camera.height - 1)
            image_bgr = cv2.remap(raw_bgr, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            image_path, valid_path = out / 'images' / f'{iid}.png', out / 'valid' / f'{iid}.png'
            assert cv2.imwrite(str(image_path), image_bgr, [cv2.IMWRITE_PNG_COMPRESSION, 3])
            assert cv2.imwrite(str(valid_path), valid.astype(np.uint8)*255)
            # Independent rational-camera point projection checks the remap calibration.
            check_x = np.linspace(0, width-1, min(17, width)).round().astype(int)
            check_y = np.linspace(0, height-1, min(17, height)).round().astype(int)
            xx, yy = np.meshgrid(check_x, check_y)
            rays = np.column_stack([xx.ravel(), yy.ravel(), np.ones(xx.size)]) @ np.linalg.inv(cropK).T
            check_raw = cv2.projectPoints(rays, np.zeros(3), np.zeros(3), K, dist)[0].reshape(-1, 2)
            checked_map = np.column_stack([mapx[yy, xx].ravel(), mapy[yy, xx].ravel()])
            map_error = float(np.max(np.abs(check_raw-checked_map)))
            assert map_error < .001
            depth_root = root / cfg['dense_relative_root'] / 'stereo'
            depth = dense_record(depth_root / 'depth_maps' / (im.name + '.geometric.bin'))
            normal = dense_record(depth_root / 'normal_maps' / (im.name + '.geometric.bin'))
            row = dict(old)
            row.update(path=str(image_path), sha256=digest(image_path), image_path=str(image_path),
                       valid_mask_path=str(valid_path), valid_mask_sha256=digest(valid_path),
                       width=width, height=height, K=cropK.tolist(), camera_model='PINHOLE',
                       original_image=raw_record, original_camera_model=camera.model,
                       original_camera_params=camera.params.tolist(), original_width=camera.width,
                       original_height=camera.height, crop_xyxy=[int(x0), int(y0), int(x1), int(y1)],
                       original_focal_preserved=True, resize_scale=1.0,
                       low_resolution_derivative={'path': old['path'], 'sha256': old['sha256'], 'K': old['K'],
                                                  'width': old['width'], 'height': old['height']},
                       geometric_depth=depth, geometric_normal=normal,
                       geometric_map_calibration='Use low_resolution_derivative K and original COLMAP map dimensions; not native crop pixels')
            rows.append(row)
            inframe = positive & (uv[:, 0] >= x0) & (uv[:, 0] < x1) & (uv[:, 1] >= y0) & (uv[:, 1] < y1)
            audit = {'image_id': iid, 'role': old['role'], 'width': width, 'height': height,
                     'valid_pixel_fraction': float(valid.mean()), 'remap_projection_max_abs_error_px': map_error,
                     'focal_ratio_to_low_resolution': [float(K[0,0]/old['K'][0][0]), float(K[1,1]/old['K'][1][1])],
                     'native_sources': {source: {'positive_depth_fraction': float(positive[a:b].mean()),
                                                'inframe_fraction': float(inframe[a:b].mean())}
                                        for source, (a,b) in source_offsets.items()}}
            selected = np.flatnonzero(inframe)[::max(1, int(inframe.sum())//4096)]
            if len(selected):
                base = cxyz[selected]
                delta = cfg['projection_pixel_probe_length_m']
                pixel_vectors = []
                for axis in range(3):
                    shift_camera = im.R()[:, axis] * delta
                    pixel_vectors.append(np.linalg.norm(project_camera(base+shift_camera, K)-uv[selected], axis=1))
                audit['scene_axis_0p1m_projected_pixel_length_xyz'] = quantiles(np.stack(pixel_vectors, axis=1))
            audits.append(audit)
            print(json.dumps({'view': index+1, 'of': 66, 'image_id': iid, 'role': old['role'],
                              'dimensions': [width, height], 'depth_available': depth['available']}), flush=True)
        view_doc = dict(old_views)
        view_doc.update(views=rows, image_derivation=cfg['rectification'], no_new_view_membership=True)
        write(out/'views.json', view_doc)
        audit_doc = {'schema': cfg['schema'], 'scientific_verdict': None, 'views': audits,
                     'all_937_poses_exactly_unchanged': True, 'all_66_original_member_sha256_verified': True,
                     'crop_total_megapixels': sum(a['width']*a['height'] for a in audits)/1e6,
                     'crop_dimensions_wh': quantiles([[a['width'], a['height']] for a in audits]),
                     'role_counts': {role: sum(v['role']==role for v in rows) for role in ['decision', 'train', 'appearance_eval']},
                     'interpretation': 'Projection support and pixel scale only. Does not test visibility, texture identifiability, current source usability, camera uncertainty, or reference accuracy.'}
        write(out/'projection_audit.json', audit_doc)
        output_names = ['native_geometry.npz', 'units.json', 'views.json', 'frame_audit.json', 'projection_audit.json',
                        'source_snapshot/config.json', 'source_snapshot/sample_build.py']
        manifest = {'schema': cfg['schema'], 'task_id': cfg['task_id'], 'scientific_verdict': None,
                    'status': 'CONTINUOUS_NATIVE_P2_AND_ORIGINAL_FOCAL_CROPS_FROZEN_DEVELOPMENT_ONLY',
                    'domain': old_manifest['domain'], 'frame': old_manifest['frame'], 'frame_audit': str(out/'frame_audit.json'),
                    'gravity': frame_audit['gravity'], 'source_lineage': old_manifest['source_lineage'],
                    'source_transform': old_manifest['source_transform'], 'denominators': old_manifest['denominators'],
                    'geometry_contract': 'All native prism rows, normals, patch labels, unit_index, tile and raw-file/original-row membership retained. No 64-cell or per-cell point restriction.',
                    'native_geometry': str(out/'native_geometry.npz'), 'views': str(out/'views.json'),
                    'unit_count': old_manifest['unit_count'], 'pilot_unit_indices': None,
                    'view_roles': audit_doc['role_counts'], 'view_independence_caveat': old_views['independence_caveat'],
                    'image_derivation': cfg['rectification'], 'crop_rule': cfg['crop_rule'],
                    'depth_normal_resolution_caveat': 'Geometric depth/normal remain existing COLMAP-resolution derivatives. RGB recovery does not create higher-resolution depth or independently validate MVS.',
                    'evaluation_reference_accessed': False, 'reference_role': cfg['reference_role'],
                    'inputs': inputs, 'outputs': {name: record(out/name) for name in output_names},
                    'git_commit': subprocess.check_output(['git','-c',f'safe.directory={REPO}','rev-parse','HEAD'], cwd=REPO, text=True).strip(),
                    'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'opencv': cv2.__version__},
                    'docker_image': cfg['docker_image'], 'docker_image_id': cfg['docker_image_id'],
                    'config': record(config_path), 'source': record(__file__), 'elapsed_seconds': time.time()-started}
        write(out/'sample_manifest.json', manifest)
        print(json.dumps({'output': str(out), 'status': manifest['status'], 'projection': {k:v for k,v in audit_doc.items() if k != 'views'}}), flush=True)
    except Exception as error:
        write(out/'failure_receipt.json', {'task_id': cfg['task_id'], 'scientific_verdict': None,
                                         'exception_type': type(error).__name__, 'message': str(error),
                                         'elapsed_seconds': time.time()-started, 'source': record(__file__), 'config': record(config_path)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    build(Path(parser.parse_args().config))
