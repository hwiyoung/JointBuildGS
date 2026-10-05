"""Read-only COLMAP lineage and SfM reprojection audit for a sealed walkthrough.

SfM observations are input-pipeline sanity evidence, not reference geometry or
an independent evaluation of the prior/DA3/MVS candidate depths.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import traceback

import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def unpack(stream, fmt):
    size = struct.calcsize('<' + fmt)
    data = stream.read(size)
    require(len(data) == size, 'Truncated COLMAP record')
    return struct.unpack('<' + fmt, data)


def rotation(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def read_cameras(path):
    result = {}
    with path.open('rb') as stream:
        for _ in range(unpack(stream, 'Q')[0]):
            cid, model, width, height = unpack(stream, 'iiQQ')
            require(model == 1, 'Expected frozen PINHOLE model')
            fx, fy, cx, cy = unpack(stream, 'dddd')
            result[cid] = dict(width=width, height=height,
                              K=np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]]))
    return result


def read_images(path, selected=frozenset(), count=0):
    result = {}
    with path.open('rb') as stream:
        for _ in range(unpack(stream, 'Q')[0]):
            row = unpack(stream, 'idddddddi')
            name = bytearray()
            while True:
                value = stream.read(1)
                require(bool(value), 'Truncated COLMAP name')
                if value == b'\0':
                    break
                name.extend(value)
            name = name.decode('utf8')
            require(name not in result, 'Duplicate image name')
            n = unpack(stream, 'Q')[0]
            observations = []
            if name in selected:
                raw = stream.read(n * 24)
                require(len(raw) == n * 24, 'Truncated COLMAP observations')
                data = np.frombuffer(raw, dtype=[('x', '<f8'), ('y', '<f8'), ('id', '<i8')])
                indices = np.flatnonzero(data['id'] >= 0)[:count]
                observations = [dict(index=int(i), point_id=int(data[i]['id']),
                                     uv=np.array([data[i]['x'], data[i]['y']])) for i in indices]
                require(len(observations) == count, 'Insufficient predeclared observation count')
            else:
                stream.seek(n * 24, 1)
            result[name] = dict(id=row[0], q=np.array(row[1:5]), R=rotation(row[1:5]),
                                t=np.array(row[5:8]), cid=row[8], observations=observations)
    return result


def read_points(path, required_ids):
    result = {}
    with path.open('rb') as stream:
        for _ in range(unpack(stream, 'Q')[0]):
            row = unpack(stream, 'QdddBBBd')
            stream.seek(unpack(stream, 'Q')[0] * 8, 1)
            if row[0] in required_ids:
                result[row[0]] = np.array(row[1:4])
    require(set(result) == required_ids, 'Referenced SfM point ID missing')
    return result


def write_csv(path, rows):
    require(bool(rows), 'Empty CSV')
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['inputs', 'original', 'walkthrough', 'config', 'launcher', 'output']:
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker is required')
    out = args.output
    require(not (out / 'receipt.json').exists(), 'Existing receipt must be preserved')
    bound = {}

    def bind(path, expected=None):
        digest = sha(path)
        require(expected is None or digest == expected, 'SHA mismatch: ' + str(path))
        bound[str(path)] = dict(path=str(path), sha256=digest, bytes=path.stat().st_size)
        return path

    def read(path, expected=None):
        return json.loads(bind(path, expected).read_text())

    receipt = dict(schema='jbgs.walkthrough_camera_audit.v3.2', status='FAIL',
                   created_utc=datetime.now(timezone.utc).isoformat(), scientific_verdict=None,
                   gt_geometry_used=False, reference_images_used=False,
                   candidate_depths_used=False, training_modified=False,
                   scope='INTERNAL_SFM_INPUT_PIPELINE_SANITY')
    try:
        cfg = read(args.config)
        require(cfg['scientific_verdict'] is None and cfg['gt_geometry_used'] is False, 'Invalid scope')
        require(cfg['observations_per_selected_view'] == 200, 'Predeclared sample differs')
        require(cfg['selection'] == 'first_valid_native_observation_entries_without_residual_filter', 'Selection changed')
        require(os.environ.get('JBGS_RUNTIME_IMAGE_ID') == cfg['image_id'], 'Runtime image differs')
        for source in [Path(__file__), args.launcher]:
            bind(source)
            shutil.copyfile(source, out / source.name)
        prior = read(args.walkthrough / 'receipt.json')
        require(prior['status'] == 'PASS_INTERNAL_FIT_DIAGNOSTIC' and prior['scientific_verdict'] is None,
                'Walkthrough must be a sealed technical diagnostic')
        outputs = {entry['path']: entry for entry in prior['outputs']}
        plan = read(args.walkthrough / 'plan.json', outputs['plan.json']['sha256'])
        names_path = bind(args.walkthrough / 'neighbor_names.tsv', outputs['neighbor_names.tsv']['sha256'])
        selected = [tuple(line.split('\t')) for line in names_path.read_text().splitlines()]
        require(len(selected) == len(set(selected)), 'Duplicate selected camera')
        planned = {(region['region'], name) for region in plan['regions']
                   for name in [region['ref_camera']] + [n['camera_id'] for n in region['neighbors']]}
        require(set(selected) == planned, 'Selected membership differs from sealed plan')
        require({region for region, name in selected} == {'P1', 'P2'}, 'Unexpected regions')
        previous_inputs = {entry['path']: entry['sha256'] for entry in prior['inputs']}
        original_paths = {key: bind(args.original / (key + '.bin')) for key in ['cameras', 'images', 'points3D']}
        original_cameras = read_cameras(original_paths['cameras'])
        original_images = read_images(original_paths['images'], {n for r, n in selected}, 200)
        point_ids = {obs['point_id'] for region, name in selected for obs in original_images[name]['observations']}
        points = read_points(original_paths['points3D'], point_ids)
        lineage, per_view, raw = [], [], []
        for region_plan in plan['regions']:
            region, refname = region_plan['region'], region_plan['ref_camera']
            root = args.inputs / region
            manifest = read(root / 'input_manifest.json', previous_inputs[f'/inputs/{region}/input_manifest.json'])
            seals = {entry['path']: entry['sha256'] for entry in manifest['files']}

            def sealed(relative):
                return bind(root / relative, seals[relative])

            split = json.loads(sealed('scene/split_manifest_da3_v2.json').read_text())
            views = {view['name']: view for view in split['train']}
            require(len(views) == len(split['train']), 'Duplicate train camera')
            require(all(name in views for r, name in selected if r == region), 'Selected camera outside train')
            local_cameras = read_cameras(sealed('scene/sparse/0/cameras.bin'))
            local_images = read_images(sealed('scene/sparse/0/images.bin'))
            text_cameras = {}
            for line in sealed('scene/train_sparse_txt/cameras.txt').read_text().splitlines():
                fields = line.split()
                if not fields or fields[0].startswith('#'):
                    continue
                require(fields[1] == 'PINHOLE', 'Unexpected text camera model')
                fx, fy, cx, cy = map(float, fields[4:8])
                text_cameras[int(fields[0])] = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
            text_images = {}
            for line in sealed('scene/train_sparse_txt/images.txt').read_text().splitlines():
                fields = line.split()
                if len(fields) >= 10 and fields[9].endswith('.JPG'):
                    text_images[fields[9]] = dict(q=np.array(fields[1:5], float), t=np.array(fields[5:8], float))
            camera_producer = json.loads(sealed('scene/camera_receipt.json').read_text())
            matched_producer_keys = set()
            for record in camera_producer['inputs']:
                for key in ['cameras', 'images']:
                    if record['path'].endswith('/colmap_dense/sparse/' + key + '.bin'):
                        require(record['sha256'] == sha(original_paths[key]), 'Original producer hash differs')
                        matched_producer_keys.add(key)
            require(matched_producer_keys == {'cameras', 'images'}, 'Original camera producer binding missing')
            differences = {}
            for name, view in views.items():
                orig, local, txt = original_images[name], local_images[name], text_images[name]
                require(view['image_id'] == orig['id'] and view['camera_id'] == orig['cid'], 'Camera identity differs')
                camera = original_cameras[orig['cid']]
                require((view['width'], view['height']) == (camera['width'], camera['height']), 'Image size differs')
                pairs = dict(K_split_original=(view['K'], camera['K']), R_split_original=(view['R'], orig['R']),
                             t_split_original=(view['t'], orig['t']), quaternion_local_original=(local['q'], orig['q']),
                             t_local_original=(local['t'], orig['t']), quaternion_txt_original=(txt['q'], orig['q']),
                             t_txt_original=(txt['t'], orig['t']), K_local_original=(local_cameras[orig['cid']]['K'], camera['K']),
                             K_txt_original=(text_cameras[orig['cid']], camera['K']))
                for key, (a, b) in pairs.items():
                    delta = float(np.max(np.abs(np.asarray(a) - np.asarray(b))))
                    differences[key] = max(differences.get(key, 0.), delta)
                    require(delta <= cfg['metadata_atol'], 'Pose/calibration lineage mismatch: ' + name + '/' + key)
            lineage.append(dict(region=region, train_count=len(views), max_absolute_differences=differences))
            ref_R = np.asarray(views[refname]['R'])
            ref_C = -ref_R.T @ np.asarray(views[refname]['t'])
            for r, name in sorted(selected):
                if r != region:
                    continue
                view = views[name]
                R, t, K = np.asarray(view['R']), np.asarray(view['t']), np.asarray(view['K'])
                observations = original_images[name]['observations']
                xyz = np.array([points[obs['point_id']] for obs in observations])
                uv = np.array([obs['uv'] for obs in observations])
                camera_xyz = xyz @ R.T + t
                require(np.all(camera_xyz[:, 2] > 0), 'Selected SfM observation behind camera')
                projected = camera_xyz @ K.T
                projected = projected[:, :2] / projected[:, 2:]
                error = np.linalg.norm(projected - uv, axis=1)
                axis_error = float(np.max(np.abs(R[2] - np.linalg.solve(R, [0., 0., 1.]))))
                require(axis_error <= cfg['axis_atol'], 'Optical-axis convention mismatch')
                angle = float(np.degrees(np.arccos(np.clip(R[2] @ ref_R[2], -1, 1))))
                center = -R.T @ t
                per_view.append(dict(region=region, name=name, observations=len(error), positive_z=len(error),
                                     median_residual_px=float(np.median(error)), p95_residual_px=float(np.quantile(error, .95)),
                                     rms_residual_px=float(np.sqrt(np.mean(error ** 2))), max_residual_px=float(error.max()),
                                     max_axis_vs_inverse_R_z=axis_error, optical_axis_angle_deg=angle,
                                     camera_center_x_m=float(center[0]), camera_center_y_m=float(center[1]), camera_center_z_m=float(center[2]),
                                     baseline_m=float(np.linalg.norm(center-ref_C)),
                                     horizontal_baseline_m=float(np.linalg.norm(center[:2]-ref_C[:2])),
                                     camera_height_difference_from_ref_m=float(center[2]-ref_C[2])))
                for obs, point, observed, calculated, cam, residual in zip(observations, xyz, uv, projected, camera_xyz, error):
                    raw.append(dict(region=region, name=name, native_observation_index=obs['index'], point_id=obs['point_id'],
                                    world_x_m=float(point[0]), world_y_m=float(point[1]), world_z_m=float(point[2]),
                                    observed_u_px=float(observed[0]), observed_v_px=float(observed[1]),
                                    projected_u_px=float(calculated[0]), projected_v_px=float(calculated[1]),
                                    camera_z_m=float(cam[2]), residual_px=float(residual)))
        write_csv(out / 'per_view.csv', per_view)
        write_csv(out / 'sampled_observations.csv', raw)
        write(out / 'lineage_checks.json', lineage)
        summary = dict(selected_views=len(selected), sampled_observations=len(raw), unique_sfm_point_ids=len(point_ids),
                       all_positive_camera_z=True, maximum_residual_px=max(row['max_residual_px'] for row in per_view),
                       metadata_max_absolute_difference=max(max(row['max_absolute_differences'].values()) for row in lineage),
                       per_view=per_view, scientific_verdict=None,
                       limitations=['SfM fit checks the input camera pipeline; it is not independent geometry accuracy.',
                                    'Candidate depth accuracy, patch visibility and occlusion are not resolved by this audit.',
                                    'No transform search, residual filtering or photo/patch reselection was performed.',
                                    'Recorded residuals have no newly chosen accuracy PASS threshold.'])
        write(out / 'summary.json', summary)
        receipt.update(status='PASS_CAMERA_LINEAGE_AND_SFM_PROJECTION_SANITY', summary=summary,
                       runtime=dict(image_id=cfg['image_id'], python=platform.python_version(), numpy=np.__version__,
                                    cpu_limit=2, memory_limit_bytes=2147483648, network='none', gpu_requested=False))
    except Exception as exc:
        receipt.update(error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        receipt['inputs'] = list(bound.values())
        receipt['outputs'] = [dict(path=str(path.relative_to(out)), bytes=path.stat().st_size, sha256=sha(path))
                              for path in sorted(out.iterdir()) if path.is_file() and path.name != 'receipt.json']
        write(out / 'receipt.json', receipt)
    print(json.dumps(dict(status=receipt['status'], selected_views=len(selected), sampled_observations=len(raw),
                          output=str(out), scientific_verdict=None)))


if __name__ == '__main__':
    main()
