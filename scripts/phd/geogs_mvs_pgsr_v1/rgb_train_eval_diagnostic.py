"""Inspect saved full-SH train/evaluation RGB; no rendering or training.

Selection precedes image scoring and depends only on frozen camera calibration
and regional bounds. Every selected native exported photograph is checked against
the source photograph, independently for all six conditions.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

import numpy as np
from PIL import Image, ImageDraw, __version__ as pillow_version
import torch


BASE = Path('/base')
TASK = Path('/task')
OUT = Path('/out')
SOURCE = TASK / 'sources/GeoGS-mvs-pgsr-v1'
COND = {.005: 'D005_Pnative', .0005: 'D0005_Pnative'}
LABEL = {'da3': 'DA3 GeoGS', 'mvs': 'MVS GeoGS', 'mvs_pgsr': 'MVS + PGSR GeoGS'}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def identity(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


def rgb(path):
    with Image.open(path) as picture:
        return np.asarray(picture.convert('RGB')).copy()


def cfg_args(path):
    call = ast.parse(path.read_text(), mode='eval').body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != 'Namespace' or call.args:
        raise ValueError('Unexpected cfg_args syntax')
    return {item.arg: ast.literal_eval(item.value) for item in call.keywords}


def tensor(array):
    return torch.from_numpy(np.ascontiguousarray(array.transpose(2, 0, 1))).float().unsqueeze(0) / 255.0


def psnr(photo, render):
    mse = float(np.mean((photo.astype(np.float64)-render.astype(np.float64))**2))
    return None if mse == 0 else float(10*np.log10(255**2/mse))


def source_audit():
    evidence = {}
    # These are the frozen historical camera-corrected source and its MVS extension.
    for name, root in [('da3', BASE / 'sources/GeoGS-state-camera-v1'), ('mvs_pgsr', SOURCE)]:
        render = (root / 'render.py').read_text()
        reader = (root / 'scene/dataset_readers.py').read_text()
        scene = (root / 'scene/__init__.py').read_text()
        if 'shuffle=False' not in render or 'key = lambda x : x.image_name' not in reader:
            raise ValueError('Native sorted camera export path changed')
        if render.index('gaussExtractor.export_image(train_dir)') >= render.index('active_sh_degree = 0'):
            raise ValueError('Training PNG export is not before diffuse mesh extraction')
        if render.index('gaussExtractor.export_image(test_dir)') >= render.index('active_sh_degree = 0'):
            raise ValueError('Evaluation PNG export is not before diffuse mesh extraction')
        if 'if shuffle:' not in scene:
            raise ValueError('Native Scene shuffle gate missing')
        evidence[name] = {str(p.relative_to(root)): identity(p) for p in [
            root / 'render.py', root / 'scene/dataset_readers.py', root / 'scene/__init__.py',
            root / 'utils/mesh_utils.py', root / 'scene/gaussian_model.py']}
    return evidence


def verify_calibration(region, split, loader):
    sparse = BASE / 'inputs' / region / 'scene/sparse_lod/0'
    images = loader.read_extrinsics_binary(sparse / 'images.bin')
    cameras = loader.read_intrinsics_binary(sparse / 'cameras.bin')
    sorted_images = sorted(images.values(), key=lambda v: Path(v.name).stem)
    all_names = [v['name'] for v in sorted(split['all'], key=lambda v: Path(v['name']).stem)]
    if [v.name for v in sorted_images] != all_names:
        raise ValueError('Frozen image set and COLMAP input differ')
    hold = int(split['llffhold'])
    for split_name in ['train', 'evaluation']:
        expected = [v.name for i, v in enumerate(sorted_images) if (i % hold == 0) == (split_name == 'evaluation')]
        got = [v['name'] for v in sorted(split[split_name], key=lambda v: Path(v['name']).stem)]
        if got != expected:
            raise ValueError('Frozen split and actual native holdout/order differ')
    by_name = {v.name: v for v in images.values()}
    for view in split['all']:
        im = by_name[view['name']]
        camera = cameras[im.camera_id]
        if camera.model != 'PINHOLE':
            raise ValueError('Expected frozen PINHOLE calibration')
        fx, fy, cx, cy = camera.params
        k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
        checks = [(view['R'], im.qvec2rotmat()), (view['t'], im.tvec), (view['K'], k)]
        if any(not np.allclose(a, b, rtol=0, atol=1e-9) for a, b in checks):
            raise ValueError('Camera matrix differs from exact input: ' + view['name'])
        if (view['width'], view['height']) != (camera.width, camera.height):
            raise ValueError('Input calibration resolution mismatch')
        if view['image_id'] != im.id or view['camera_id'] != im.camera_id:
            raise ValueError('Stable image/camera ID mismatch')
    return {'status': 'PASS', 'all_cameras_checked': len(images),
            'calibration_abs_tolerance': 1e-9, 'llffhold': hold,
            'files': [identity(sparse / name) for name in ['images.bin', 'cameras.bin']]}


def models_for(region, cfg, plan, evaluation):
    rows = []
    for prior in cfg['prior_weights']:
        for mode in cfg['modes']:
            run_id = f'{region}.{mode}.{COND[prior]}'
            if mode == 'da3':
                matches = [v for v in plan['controls'] if v['id'] == run_id]
                if len(matches) != 1:
                    raise ValueError('Missing/duplicated historical control: ' + run_id)
                control = matches[0]
                model = (BASE / control['render_records'][0]['render_path']).parents[3]
                provenance = {'control_id': run_id, 'plan_sha256': sha(evaluation / 'plan.json')}
            else:
                receipt_path = evaluation / 'extractions' / run_id / 'receipt.json'
                receipt = read(receipt_path)
                if receipt['status'] != 'PASS' or receipt['exit_code'] != 0 or receipt['job']['id'] != run_id:
                    raise ValueError('Canonical extraction not complete: ' + run_id)
                model = receipt_path.parent / 'model'
                provenance = {'extraction_receipt': identity(receipt_path), 'job': receipt['job']}
            values = cfg_args(model / 'cfg_args')
            if values['sh_degree'] != 3 or values['resolution'] != 1 or not values['eval']:
                raise ValueError('Unexpected full-SH/resolution/split configuration: ' + run_id)
            rows.append({'id': f'{mode}_{prior:g}', 'run_id': run_id, 'mode': mode, 'prior': prior,
                         'label': f'{LABEL[mode]} | prior {prior:g}', 'model': model,
                         'provenance': provenance, 'cfg_args': identity(model / 'cfg_args'),
                         'render_sh_degree': 3})
    return rows


def montage(case, folder):
    # Native pixels are pasted unchanged; the individual PNGs remain the review source.
    w, h = case['width'], case['height']
    top, caption = 58, 38
    canvas = Image.new('RGB', (4*w, top+2*(h+caption)), '#f1f3f5')
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 10), f"{case['region']} {case['split']} | {case['name']} | bbox {case['bbox']} | native pixels", fill='black')
    for row in range(2):
        paths = [case['photo_url']] + [v['render_url'] for v in case['conditions'][row*3:(row+1)*3]]
        names = ['Original photograph'] + [v['label'] for v in case['conditions'][row*3:(row+1)*3]]
        for col, (path, label) in enumerate(zip(paths, names)):
            y = top + row*(h+caption)
            draw.text((col*w+8, y+8), label, fill='black')
            with Image.open(OUT / path) as im:
                canvas.paste(im, (col*w, y+caption))
    target = folder / 'montage.png'
    canvas.save(target)
    return str(target.relative_to(OUT))


def main():
    started = time.time()
    cfg = read('/config.json')
    if cfg['scientific_verdict'] is not None or cfg['runtime_image_id'] != os.environ['DIAGNOSTIC_IMAGE_ID']:
        raise ValueError('Unexpected science or runtime contract')
    torch.set_num_threads(cfg['cpu_threads'])
    torch.set_num_interop_threads(1)
    if torch.cuda.is_available():
        raise ValueError('CPU diagnostic must have no GPU access')
    evaluation = TASK / 'evaluation' / cfg['evaluation_attempt']
    plan = read(evaluation / 'plan.json')
    if plan['scientific_verdict'] is not None:
        raise ValueError('Unexpected scientific verdict')
    rq = module('rgb_diagnostic_legacy_quality', '/legacy_render_quality.py')
    native = module('rgb_diagnostic_native_loss', SOURCE / 'utils/loss_utils.py')
    loader = module('rgb_diagnostic_colmap_loader', SOURCE / 'scene/colmap_loader.py')
    selection, models, calibration, splits = [], {}, {}, {}
    source = source_audit()
    for region in cfg['regions']:
        split_path = BASE / 'inputs' / region / 'scene/split_manifest_da3_v2.json'
        split = read(split_path)
        splits[region] = identity(split_path)
        calibration[region] = verify_calibration(region, split, loader)
        models[region] = models_for(region, cfg, plan, evaluation)
        for split_name in ['train', 'evaluation']:
            views = sorted(split[split_name], key=lambda v: Path(v['name']).stem)
            native_split = 'train' if split_name == 'train' else 'test'
            for model in models[region]:
                folder = model['model'] / native_split / 'ours_30000'
                expected_names = {f'{i:05d}.png' for i in range(len(views))}
                for subdir in ['gt', 'renders']:
                    if {p.name for p in (folder / subdir).glob('*.png')} != expected_names:
                        raise ValueError('Missing/extra exported camera images: ' + str(folder / subdir))
            eligible = []
            for index, view in enumerate(views):
                box = rq.projected_prism_bbox(plan['regions'][region]['domain'], view['R'], view['t'], view['K'], view['width'], view['height'])
                if box:
                    eligible.append({'index': index, 'view': view, 'bbox': box,
                                     'area': (box[2]-box[0])*(box[3]-box[1])})
            eligible.sort(key=lambda v: (-v['area'], v['view']['name']))
            if len(eligible) < cfg['views_per_region_split']:
                raise ValueError('Insufficient input-visible cameras')
            for rank, chosen in enumerate(eligible[:cfg['views_per_region_split']], 1):
                selection.append({'id': f'{region}_{split_name}_{rank}', 'region': region, 'split': split_name,
                                  'selection_rank': rank, 'split_camera_count': len(views),
                                  'eligible_camera_count': len(eligible), **chosen})
    # Immutable before-render-inspection selection record.
    write(OUT / 'selection.json', {'selection': cfg['selection'], 'cases': selection,
                                 'calibration_audit': calibration, 'scientific_verdict': None})
    cases, flat = [], []
    for selected in selection:
        region, split_name, index = selected['region'], selected['split'], selected['index']
        view, box = selected['view'], selected['bbox']
        x0, y0, x1, y1 = box
        photo_path = BASE / 'inputs' / region / 'scene/images' / view['name']
        photo_identity = identity(photo_path)
        if photo_identity['sha256'] != view['sha256']:
            raise ValueError('Original photograph bytes changed: ' + view['name'])
        photo = rgb(photo_path)
        if photo.shape != (view['height'], view['width'], 3):
            raise ValueError('Photograph resolution/calibration mismatch')
        crop = photo[y0:y1, x0:x1]
        folder = OUT / 'cases' / selected['id']
        folder.mkdir(parents=True, exist_ok=False)
        Image.fromarray(crop).save(folder / 'photo.png')
        Image.fromarray(photo).save(folder / 'photo_full.png')
        prefix = str(folder.relative_to(OUT)) + '/'
        case = {key: selected[key] for key in ['id', 'region', 'split', 'index', 'selection_rank', 'split_camera_count', 'eligible_camera_count', 'bbox', 'area']}
        case.update({'name': view['name'], 'image_id': view['image_id'], 'camera_id': view['camera_id'],
                     'K': view['K'], 'R': view['R'], 't': view['t'], 'photo_source': photo_identity,
                     'photo_url': prefix+'photo.png', 'photo_full_url': prefix+'photo_full.png',
                     'photo_sha256': sha(folder / 'photo.png'), 'photo_full_sha256': sha(folder / 'photo_full.png'),
                     'width': x1-x0, 'height': y1-y0, 'full_width': view['width'], 'full_height': view['height'],
                     'conditions': []})
        native_split = 'train' if split_name == 'train' else 'test'
        for model in models[region]:
            native_dir = model['model'] / native_split / 'ours_30000'
            render_path = native_dir / 'renders' / f'{index:05d}.png'
            gt_path = native_dir / 'gt' / f'{index:05d}.png'
            exported = rgb(gt_path)
            if exported.shape != photo.shape:
                raise ValueError('Native exported GT resolution mismatch')
            discrepancy = np.abs(photo.astype(np.int16)-exported.astype(np.int16))
            max_delta = int(discrepancy.max())
            if max_delta > cfg['exported_photo_max_abs_u8_tolerance']:
                raise ValueError(f'Export index/photo association failed: {render_path}; max u8 difference {max_delta}')
            rendered = rgb(render_path)
            if rendered.shape != photo.shape:
                raise ValueError('Render resolution mismatch; no resizing is allowed')
            rendered_crop = rendered[y0:y1, x0:x1]
            if split_name == 'evaluation' and model['mode'] == 'da3':
                control = next(v for v in plan['controls'] if v['id'] == model['run_id'])
                record = control['render_records'][index]
                if record['name'] != view['name'] or record['image_id'] != view['image_id'] or record['render_sha256'] != sha(render_path):
                    raise ValueError('Historical sealed evaluation render binding differs')
            Image.fromarray(rendered_crop).save(folder / (model['id']+'.png'))
            shutil.copyfile(render_path, folder / (model['id']+'_full.png'))
            with torch.inference_mode():
                native_ssim = float(native.ssim(tensor(rendered_crop), tensor(crop)))
            row = {key: model[key] for key in ['id', 'run_id', 'label', 'mode', 'prior', 'render_sh_degree', 'cfg_args']}
            row.update({'render_url': prefix+model['id']+'.png', 'render_full_url': prefix+model['id']+'_full.png',
                        'render_sha256': sha(folder / (model['id']+'.png')),
                        'render_full_sha256': sha(folder / (model['id']+'_full.png')),
                        'psnr_roi_db': psnr(crop, rendered_crop), 'ssim_roi': native_ssim,
                        'psnr_full_db': psnr(photo, rendered), 'render_source': identity(render_path),
                        'exported_gt': identity(gt_path),
                        'photo_binding': {'status': 'PASS', 'max_abs_u8_error': max_delta,
                                          'differing_channel_fraction': float(np.mean(discrepancy != 0)),
                                          'native_export_order': 'sorted filename stem; Scene shuffle=False; exact COLMAP split/calibration checked',
                                          'pixel_comparison': 'same-original-photo decode, full frame, before cropping'}})
            case['conditions'].append(row)
            flat.append({'case_id': case['id'], 'region': region, 'split': split_name, 'name': view['name'],
                         **{key: row[key] for key in ['id', 'mode', 'prior', 'psnr_roi_db', 'ssim_roi', 'psnr_full_db']}})
        case['montage_url'] = montage(case, folder)
        cases.append(case)
        print(json.dumps({'completed_case': case['id'], 'name': view['name'], 'bbox': box,
                          'results': [{k: row[k] for k in ['id', 'psnr_roi_db', 'ssim_roi']} for row in case['conditions']]}), flush=True)
    summary = []
    for region in cfg['regions']:
        for split_name in ['train', 'evaluation']:
            for model in models[region]:
                rows = [v for v in flat if v['region'] == region and v['split'] == split_name and v['id'] == model['id']]
                summary.append({'region': region, 'split': split_name, 'id': model['id'],
                                'mode': model['mode'], 'prior': model['prior'], 'case_count': len(rows),
                                **{key: float(np.mean([v[key] for v in rows])) for key in ['psnr_roi_db', 'ssim_roi', 'psnr_full_db']}})
    if len(cases) != 12 or len(flat) != 72:
        raise ValueError('Incomplete authorized twelve-case/six-condition diagnostic')
    manifest = {'schema': 'GEOGS_RGB_TRAIN_EVAL_DIAGNOSTIC_v1', 'status': 'PASS', 'scientific_verdict': None,
                'task_id': cfg['task_id'], 'scope': cfg['scope'], 'selection': cfg['selection'],
                'created_unix': time.time(), 'wall_seconds': time.time()-started,
                'config': identity('/config.json'), 'script': identity(__file__),
                'operator_head': (OUT / 'operator_head.txt').read_text().strip(),
                'runtime_image_id': cfg['runtime_image_id'],
                'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'pillow': pillow_version, 'torch': torch.__version__},
                'metric_definition': {'psnr': '10 log10(255 squared / mean squared RGB uint8 error), unmasked bbox or whole frame',
                                      'ssim': 'Native GeoGS loss_utils.ssim, window 11 sigma 1.5, zero padding, RGB [0,1], CPU float32',
                                      'ssim_source': identity(SOURCE / 'utils/loss_utils.py'),
                                      'LPIPS': 'Not assessed in this bounded CPU diagnostic'},
                'calibration_audit': calibration, 'split_manifests': splits,
                'evaluation_plan': identity(evaluation / 'plan.json'),
                'source_audit': source, 'projection_helper': identity('/legacy_render_quality.py'),
                'lineage': {r: [{k: v for k, v in m.items() if k != 'model'} | {'model': str(m['model'])} for m in models[r]] for r in cfg['regions']},
                'render_representation': 'Native full-SH degree 3 opacity-composited RGB, exported before mesh SH0/TSDF. Native pixel crops; no image resampling.',
                'limits': ['Twelve deliberately bounded input-selected cases; not a population estimate.',
                           'Train and evaluation cameras differ in viewpoint, projected extent, coverage and visibility; their means are not a controlled generalization gap.',
                           'Fixed projected prism bbox includes background and occluders; not a building silhouette.',
                           'PSNR and SSIM assess photo reconstruction, not current geometry or ALS-vs-LoD2 causality.',
                           'Existing MVS neighbor-image lineage is non-confirmatory.'],
                'cases': cases, 'summary': summary}
    write(OUT / 'manifest.json', manifest)
    for name, rows in [('per_case_metrics.csv', flat), ('summary.csv', summary)]:
        with (OUT / name).open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    write(OUT / 'receipt.json', {'status': 'PASS', 'scientific_verdict': None, 'cases': len(cases), 'pairs': len(flat),
                               'manifest': identity(OUT / 'manifest.json'), 'wall_seconds': time.time()-started,
                               'all_selected_gt_bindings_verified': True,
                               'pixelmatch_max_abs_u8_delta': max(row['photo_binding']['max_abs_u8_error'] for case in cases for row in case['conditions']),
                               'source_full_sh_audit': source, 'new_training': False, 'new_rendering': False})
    print('PASS 12 input-selected cases / 72 native RGB comparisons', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        write(OUT / 'failure.json', {'status': 'FAIL', 'scientific_verdict': None, 'exception': repr(exc),
                                   'traceback': traceback.format_exc(), 'created_unix': time.time()})
        raise
