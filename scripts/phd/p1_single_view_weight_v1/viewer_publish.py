"""Incremental display of individually sealed 30k outputs. No training or scoring."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

ROOT = Path('/output')
EXP = Path('/experiment')
INPUT = Path('/input')
ALPHAS = (0, 1, 4)
VIEWS = [('train', 'DJI_20241217084553_0100_D.JPG'),
         ('evaluation', 'DJI_20241217084551_0099_D.JPG')]
ANCHOR_SHA = 'c08a39aa2deb81b26dd4dd75d0be9e6bb5e150db503f9d422a05423388679274'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    write(temp, value)
    os.replace(temp, path)


def verified(path, expected):
    if sha(path) != expected:
        raise ValueError('Frozen identity mismatch: ' + str(path))
    return Path(path)


def validate_training(receipt, cfg, alpha):
    expected = dict(status='PASS', completed=True, phase='train', alpha=alpha,
                    final_iteration=30000, config_sha256=cfg['config_sha256'],
                    mask_sha256=cfg['mask_sha256'], fixed_visual_weight=.05,
                    scientific_verdict=None)
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError('Individual final training receipt did not pass: alpha ' + str(alpha))


def record(path, cfg):
    return dict(url=cfg['url_prefix'] + str(path.relative_to(ROOT)),
                bytes=path.stat().st_size, sha256=sha(path))


def qualify(value, prefix):
    if isinstance(value, dict):
        return {key: prefix + item if key == 'url' else qualify(item, prefix)
                for key, item in value.items()}
    if isinstance(value, list):
        return [qualify(item, prefix) for item in value]
    return value


def manifest(cfg):
    queue = (EXP / 'status.txt').read_text().strip()
    views = []
    for role, name in VIEWS:
        image = ROOT / 'images' / name
        if not image.exists():
            image.parent.mkdir(exist_ok=True)
            shutil.copyfile(INPUT / 'scene/images' / name, image)
        views.append(dict(id=role, image_name=name, split=role,
                          label='0100_D · 학습뷰' if role == 'train' else '0099_D · 비교뷰',
                          original=record(image, cfg), depth_range_m=cfg['depth_range_m'],
                          conditions={}))
    publications = {}
    states = {}
    for alpha in ALPHAS:
        folder = ROOT / f'alpha_{alpha}'
        path = folder / 'publication.json'
        if path.exists():
            publications[alpha] = read(path)
        elif (folder / 'failure.json').exists():
            states[alpha] = dict(status='failed', reason=read(folder / 'failure.json')['error'])
        else:
            receipt_path = EXP / 'train' / f'alpha_{alpha}' / 'receipt.json'
            receipt = read(receipt_path) if receipt_path.exists() else None
            if receipt and receipt.get('status') != 'PASS':
                states[alpha] = dict(status='failed', reason='해당 학습의 완료 검사가 실패했습니다.')
            else:
                states[alpha] = dict(status='pending', reason='30k 학습 완료 · 표면과 렌더 처리 중' if receipt
                                    else '30k 학습 완료 대기')
    regions = []
    for region in cfg['regions']:
        rows = []
        for alpha in ALPHAS:
            row = dict(id=f'alpha_{alpha}', label=f'R1 가중치 {alpha}', scientific_verdict=None)
            if alpha in publications:
                publication = publications[alpha]
                row.update(status='available', mesh=publication['regions'][region['id']]['mesh'],
                           provenance=publication['provenance'])
            else:
                row.update(states[alpha])
            rows.append(row)
        regional_views = copy.deepcopy(views)
        for view in regional_views:
            for alpha in ALPHAS:
                view['conditions'][f'alpha_{alpha}'] = (publications[alpha]['views'][view['id']]
                    if alpha in publications else states[alpha])
        regions.append(dict(region, conditions=rows, views=regional_views))
    count = len(publications)
    value = dict(schema='p1_weight_comparison_v1', task_id=cfg['task_id'], scientific_verdict=None,
        generated_at=datetime.now(timezone.utc).isoformat(), regions=regions,
        run_status=dict(completed=count, total=3, queue_status=queue,
                        label=f'최종 결과 {count}/3 등록 · 완료되는 조건부터 표시'),
        surface_contract=dict(label='동일 raw RGB TSDF512 · 조건별 30k 최종 결과',
                              parameters=cfg['expected_extraction']),
        downloads=[dict(label='0100_D 실제 가중치 범위', url=cfg['url_prefix']+'scope.png')],
        training_changed=False, scoring_changed=False)
    atomic(ROOT / 'manifest.json', value)
    atomic(ROOT / 'builder_status.json', dict(status='COMPLETE' if count == 3 else 'WAITING_OR_PUBLISHING',
           published_alphas=sorted(publications), scientific_verdict=None,
           updated_at=value['generated_at']))
    return value


def next_alpha(cfg):
    manifest(cfg)
    ready = []
    for alpha in ALPHAS:
        folder = ROOT / f'alpha_{alpha}'
        if (folder / 'publication.json').exists() or (folder / 'failure.json').exists():
            continue
        path = EXP / 'train' / f'alpha_{alpha}' / 'receipt.json'
        if not path.exists():
            continue
        receipt = read(path)
        if receipt.get('status') != 'PASS':
            continue
        validate_training(receipt, cfg, alpha)
        ready.append((receipt['started_unix'] + receipt['wall_seconds'], alpha))
    if ready:
        print(min(ready)[1])
    elif all((ROOT / f'alpha_{a}' / 'publication.json').exists() for a in ALPHAS):
        print('COMPLETE')
    elif all((ROOT / f'alpha_{a}' / 'publication.json').exists() or
             (ROOT / f'alpha_{a}' / 'failure.json').exists() for a in ALPHAS):
        print('PUBLICATION_FAILED')
    elif (EXP / 'status.txt').read_text().strip().startswith('FAIL'):
        print('TRAINING_FAILED')
    else:
        print('WAIT')


def stage(cfg, alpha):
    run = EXP / 'train' / f'alpha_{alpha}'
    receipt = read(run / 'receipt.json')
    validate_training(receipt, cfg, alpha)
    restore = read(run / 'model/jbgs_restore.json')
    if restore['checkpoint_sha256'] != ANCHOR_SHA or restore['iteration'] != 8000:
        raise ValueError('Anchor identity mismatch')
    complete_dir = run / 'model/jbgs_complete/iteration_30000'
    complete = read(complete_dir / 'receipt.json')
    if complete['iteration'] != 30000 or complete['after_protection_registration'] is not True:
        raise ValueError('Incomplete final state')
    ply = verified(run / 'model/point_cloud/iteration_30000/point_cloud.ply', complete['ply_sha256'])
    verified(complete_dir / 'point_cloud.ply', complete['ply_sha256'])
    verified(complete_dir / 'checkpoint.pth', complete['checkpoint_sha256'])
    folder = ROOT / f'alpha_{alpha}' / 'extraction'
    dest = folder / 'model/point_cloud/iteration_30000'
    dest.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(ply, dest / 'point_cloud.ply')
    shutil.copyfile(run / 'model/cfg_args', folder / 'model/cfg_args')
    write(folder / 'job.json', dict(id=f'P1.alpha_{alpha}.incremental_display', alpha=alpha,
          region='P1', mode='mvs', prior=.005, scientific_verdict=None,
          files=[dict(path=str(ply), sha256=complete['ply_sha256'])],
          source_provenance_sha256=sha('/source/mvs_pgsr_source_provenance.json'),
          input_manifest_sha256=sha('/input/input_manifest.json'),
          training_receipt_sha256=sha(run / 'receipt.json'),
          final_complete_receipt_sha256=sha(complete_dir / 'receipt.json'),
          staged_cfg_sha256=sha(folder / 'model/cfg_args'), final_gaussians=complete['gaussians']))


def publish(cfg, alpha):
    import numpy as np
    from PIL import Image
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import colormaps
    from export_geometry import export_native_mesh
    folder = ROOT / f'alpha_{alpha}'
    extraction = folder / 'extraction'
    receipt = read(extraction / 'receipt.json')
    job = read(extraction / 'job.json')
    if receipt['status'] != 'PASS' or receipt['job'] != job or job['alpha'] != alpha:
        raise ValueError('Extraction receipt mismatch')
    run = EXP / 'train' / f'alpha_{alpha}'
    verified(run / 'receipt.json', job['training_receipt_sha256'])
    verified(extraction / 'model/cfg_args', job['staged_cfg_sha256'])
    for key, expected in cfg['expected_extraction'].items():
        if receipt['realized_extraction'][key] != expected:
            raise ValueError('Extraction parameters differ: ' + key)
    surface = receipt['surfaces']['raw']
    source = verified(extraction / surface['path'], surface['sha256'])
    regions = {}
    for region in cfg['regions']:
        dest = folder / 'display' / region['id']
        data = export_native_mesh(source, dest, region['bounds'], expected_sha=surface['sha256'],
                                  point_cap=cfg['point_cap'])
        write(dest / 'export.json', data)
        regions[region['id']] = qualify(data, cfg['url_prefix'] + str(dest.relative_to(ROOT)) + '/')
    split = read(INPUT / 'scene/split_manifest_da3_v2.json')
    views = {}
    lo, hi = cfg['depth_range_m']
    for role, name in VIEWS:
        rows = sorted(split[role], key=lambda row: row['name'])
        indices = [i for i, row in enumerate(rows) if row['name'] == name]
        if len(indices) != 1:
            raise ValueError('Camera name is not unique')
        index = indices[0]
        base = extraction / 'model' / ('train' if role == 'train' else 'test') / 'ours_30000'
        rgb = base / 'renders' / f'{index:05d}.png'
        depth = base / 'vis' / f'depth_{index:05d}.tiff'
        with Image.open(base / 'gt' / f'{index:05d}.png') as a, Image.open(INPUT / 'scene/images' / name) as b:
            if not np.array_equal(np.asarray(a.convert('RGB')), np.asarray(b.convert('RGB'))):
                raise ValueError('Camera and original image pixels differ')
        with Image.open(depth) as image:
            values = np.asarray(image, dtype=np.float32)
        valid = np.isfinite(values) & (values > 0)
        normalized = np.where(valid, np.clip((values-lo)/(hi-lo), 0, 1), 0)
        colors = colormaps['viridis'](normalized, bytes=True)
        colors[~valid] = [230, 230, 230, 255]
        png = folder / (role + '_depth.png')
        Image.fromarray(colors).save(png)
        views[role] = dict(status='available', rgb=record(rgb, cfg), depth=record(png, cfg),
                           source_depth_sha256=sha(depth), original_pixels_verified=True,
                           camera=name, fixed_display_range_m=[lo, hi])
    write(folder / 'publication.json', dict(status='PASS_INDIVIDUAL_FINAL_DISPLAY',
          scientific_verdict=None, alpha=alpha, regions=regions, views=views,
          provenance=dict(training_receipt_sha256=job['training_receipt_sha256'],
                          extraction_receipt_sha256=sha(extraction / 'receipt.json'),
                          mesh_sha256=surface['sha256'], checkpoint_iteration=30000,
                          mask_sha256=cfg['mask_sha256'], config_sha256=cfg['config_sha256']),
          completed_unix=time.time()))
    manifest(cfg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['refresh', 'next', 'stage', 'publish', 'fail'])
    parser.add_argument('--alpha', type=int, choices=ALPHAS)
    parser.add_argument('--error')
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    cfg = read('/driver/viewer_config.json')
    verified(EXP / 'config.json', cfg['config_sha256'])
    verified(EXP / 'mask/r1_mask.npz', cfg['mask_sha256'])
    if args.stage == 'refresh':
        manifest(cfg)
    elif args.stage == 'next':
        next_alpha(cfg)
    else:
        if args.alpha is None:
            raise ValueError('An individual alpha is required')
        if args.stage == 'fail':
            write(ROOT / f'alpha_{args.alpha}' / 'failure.json', dict(status='FAIL',
                  error=args.error or 'Incremental result processing failed; inspect worker logs',
                  scientific_verdict=None, created_unix=time.time()))
            manifest(cfg)
        else:
            {'stage': stage, 'publish': publish}[args.stage](cfg, args.alpha)


if __name__ == '__main__':
    main()
