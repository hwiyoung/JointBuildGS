"""Export actual saved Gaussian parameters and rendered evaluation images for inspection.

Run in Docker. The browser kernel is a parameter inspector; authoritative images
are copies of the actual gsplat outputs. No learning or source selection occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import time

import numpy as np

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, payload):
    with Path(path).open('x') as f:
        json.dump(payload, f, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        f.write('\n')


def export_state(path, output):
    with np.load(path, allow_pickle=False) as source:
        n = len(source['xyz'])
        sizes = dict(xyz=(n, 3), scales=(n, 3), quats=(n, 4), opacity=(n,), rgb=(n, 3))
        payload = {'count': n, 'role': 'actual_saved_gaussian_parameters', 'thinned': False}
        arrays = {}
        for key, size in sizes.items():
            a = np.asarray(source[key])
            if key == 'opacity':
                a = a.reshape(-1)
            if a.shape != size or not np.isfinite(a).all():
                raise ValueError(f'{path}: invalid {key} shape or nonfinite values')
            arrays[key] = a
            payload[key] = a.reshape(-1).astype(float).tolist()
        if np.any(arrays['scales'] <= 0) or np.any(np.linalg.norm(arrays['quats'], axis=1) < 1e-6):
            raise ValueError(f'{path}: invalid scale or quaternion')
        if np.any((arrays['opacity'] < 0) | (arrays['opacity'] > 1)):
            raise ValueError(f'{path}: opacity must be decoded linear [0,1]')
        if np.any((arrays['rgb'] < 0) | (arrays['rgb'] > 1)):
            raise ValueError(f'{path}: RGB must be display decoded [0,1]')
        for key in ['group', 'seed_id', 'parent_id', 'sh0']:
            if key in source:
                payload[key] = source[key].reshape(-1).tolist()
        write(output, payload)
        return {'url': output.name, 'count': n, 'state_sha256': sha(path)}, arrays['xyz']


def build(args):
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / 'STARTED.json', {'task_id': 'PHD-P2-AB-V2-GAUSSIAN-VIEWER', 'scientific_verdict': None})
    arms, positions, inputs = [], [], {}
    for root in args.b_root:
        receipt = root / 'result.json'
        overall = json.loads(receipt.read_text()) if receipt.exists() else {}
        views_path = root / 'views.json'
        view_rows = json.loads(views_path.read_text())['views']
        views = {str(v['image_id']): v for v in view_rows}
        expected_eval_ids = {str(v['image_id']) for v in view_rows if v['role']=='eval'}
        if len(views) != len(view_rows) or len(expected_eval_ids) != 11:
            raise ValueError(f'Expected unique cameras and exactly 11 frozen evaluation views: {views_path}')
        inputs[str(views_path)] = sha(views_path)
        if receipt.exists():
            inputs[str(receipt)] = sha(receipt)
        ordering = ['structured_detail', 'geometry_fixed', 'soft_prior', 'prior_free', 'color_fixed', 'soft_prior_weak', 'soft_prior_strong', 'image_only']
        folders = [p.parent for p in root.glob('*/gaussians_final.npz')]
        folders.sort(key=lambda p: (ordering.index(p.name) if p.name in ordering else 99, p.name))
        labels = {'structured_detail': '구조 제한 · 색과 세부 갱신', 'geometry_fixed': '기하 고정 · 색 복원',
                  'soft_prior': '구조 손실 · 기준 강도', 'prior_free': 'ALS 초기화 · 기하 자유',
                  'color_fixed': '색 고정 · 기하 갱신', 'soft_prior_weak': '구조 손실 · 약하게',
                  'soft_prior_strong': '구조 손실 · 강하게', 'image_only': '영상 MVS 초기화 · 영상 복원'}
        cfg_path = root/'config.json'
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        run_label = ' · 32-step 실행 검산' if 'PREFLIGHT' in root.name else ''
        if any(s in root.name.upper() for s in ['SUBDIV', 'DENSITY', 'REPRESENTATION']): run_label = ' · 표현 4분할'
        if 'SHIFT' in root.name.upper(): run_label = ' · prior 이동 통제'
        for folder in folders:
            if f'{root.name}/{folder.name}' in args.exclude_arm:
                continue
            key = f'{root.name}__{folder.name}'
            record = {'id': key, 'label': labels.get(folder.name, folder.name)+run_label,
                      'images': [], 'metrics': {}, 'configuration': cfg}
            result = folder / 'result.json'
            if result.exists():
                record['metrics'] = json.loads(result.read_text())
                inputs[str(result)] = sha(result)
            else:
                record['metrics'] = overall.get('arms', {}).get(folder.name, {}) if isinstance(overall.get('arms'), dict) else overall
            for stage in ['initial', 'final']:
                source = folder / f'gaussians_{stage}.npz'
                record[stage], xyz = export_state(source, args.output / f'{key}__{stage}.json')
                positions.append(xyz)
                inputs[str(source)] = sha(source)
            # A separate points mode reveals seed support without pretending that
            # centre points are the rendered Gaussian surface.
            record['source'] = record['initial']
            final_images = sorted(folder.glob('final_rgb_*.png')) or sorted(folder.glob('rgb_*.png'))
            for final in final_images:
                image_id = final.stem.removeprefix('final_').removeprefix('rgb_')
                paths = dict(target=folder / f'target_{image_id}.png',
                             initial=folder / f'initial_rgb_{image_id}.png', final=final)
                if not all(p.is_file() for p in paths.values()):
                    raise ValueError(f'Missing evaluation image triple: {folder} {image_id}')
                view = views[image_id]
                if view['role'] != 'eval':
                    raise ValueError(f'Expected B evaluation view: {image_id}')
                image = {'image_id': image_id, 'camera': view,
                         'source_B_views_path': str(views_path), 'source_B_views_sha256': inputs[str(views_path)],
                         'image_sha256': {}}
                for kind, source in paths.items():
                    with source.open('rb') as f:
                        header = f.read(24)
                    if header[:8] != b'\x89PNG\r\n\x1a\n':
                        raise ValueError(f'Invalid PNG: {source}')
                    if struct.unpack('>II', header[16:24]) != (view['width'], view['height']):
                        raise ValueError(f'Image/camera dimensions differ: {source}')
                    dest = args.output / f'{key}__{kind}_{image_id}.png'
                    shutil.copyfile(source, dest)
                    image[kind] = dest.name
                    inputs[str(source)] = sha(source)
                    image['image_sha256'][kind] = inputs[str(source)]
                record['images'].append(image)
            if {row['image_id'] for row in record['images']} != expected_eval_ids:
                raise ValueError(f'Evaluation image membership incomplete: {folder}')
            arms.append(record)
    if not arms:
        raise ValueError('No complete initial/final Gaussian exports found')
    xyz = np.concatenate(positions)
    lo, hi = xyz.min(0), xyz.max(0)
    write(args.output / 'inspection.json', {
        'schema': 'jointbuildgs.phd.p2_ab.gaussian_inspection.v2',
        'description': '동일 P2의 조건부 재구성 비교 · 실제 Gaussian 전체 매개변수와 평가뷰 렌더',
        'scientific_verdict': None, 'center': ((lo+hi)/2).tolist(),
        'span': float(np.max(hi-lo)*1.15), 'bounds': [lo.tolist(), hi.tolist()],
        'coordinate_frame': 'P2 local numeric frame; EPSG:25832 project lineage; see sample frame audit',
        'browser_rendering': 'oriented 2D Gaussian kernels clipped at 3 sigma; centre-depth sorted alpha; parameter inspection, not exact gsplat replication',
        'arms': arms,
    })
    source_files = [Path(__file__), REPO/'src/apps/p2_ab_inspector_v2/index.html',
                    REPO/'src/apps/p2_ab_inspector_v2/app.js',
                    REPO/'src/apps/gs3d_4way_viewer/build/three.module.min.js']
    for source in source_files[1:]:
        shutil.copyfile(source, args.output/source.name)
    snapshot = args.output / 'source_snapshot'
    for source in source_files:
        dest = snapshot / source.relative_to(REPO)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    if any(sha(p) != h for p, h in inputs.items()):
        raise RuntimeError('An input changed during export')
    write(args.output/'technical_receipt.json', {
        'task_id': 'PHD-P2-AB-V2-GAUSSIAN-VIEWER', 'status': 'PARAMETER_EXPORT_COMPLETE',
        'scientific_verdict': None, 'arm_count': len(arms),
        'excluded_arms': args.exclude_arm,
        'input_sha256': inputs, 'source_sha256': {str(p.relative_to(REPO)): sha(p) for p in source_files},
        'container_image': os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
        'git_head': os.environ.get('JBGS_SOURCE_GIT_HEAD'),
        'elapsed_seconds': time.monotonic()-started,
        'qa_scope': 'saved-parameter validation and byte-linked gsplat images; browser QA separate',
    })
    print(json.dumps({'status': 'PARAMETER_EXPORT_COMPLETE', 'arms': len(arms), 'output': str(args.output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--b-root', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exclude-arm', action='append', default=[], help='Exact RUN/arm retained outside this comparison')
    build(parser.parse_args())
