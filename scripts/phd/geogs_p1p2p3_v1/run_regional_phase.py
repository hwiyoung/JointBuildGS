"""Container-only frozen regional run driver with failure receipts."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import time

from parse_extraction import PARSER_SOURCE, PARSER_SHA256, parse_extraction_log
from resource_schedule import HELPER_SOURCE as SCHEDULER_SOURCE, acquire_extraction_lock
from repeat_contract import (REPEAT_HELPER_SOURCE, REPEAT_HELPER_SHA256,
                             load_repeat_binding, require_repeat_receipt)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--region', choices=('P1', 'P2', 'P3'), required=True)
    parser.add_argument('--condition', required=True)
    parser.add_argument('--phase', choices=('train', 'parity', 'render', 'metrics', 'auxiliary'), required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker execution is required')
    config_bytes = args.config.read_bytes()
    cfg = json.loads(config_bytes)
    runtime_layout = None
    layout_path = Path('/runtime_layout.json')
    if layout_path.exists():
        runtime_layout = json.loads(layout_path.read_text())
        if (runtime_layout['task_id'] != cfg['task_id'] or
                runtime_layout['scientific_config_sha256'] != hashlib.sha256(config_bytes).hexdigest() or
                runtime_layout['revision'] != os.environ.get('JBGS_RUNTIME_REVISION') or
                runtime_layout['allocator'] != os.environ.get('PYTORCH_CUDA_ALLOC_CONF')):
            raise ValueError('Runtime revision differs from the frozen recovery contract')
        # Release this audit CUDA context before spawning the training process.
        effective = json.loads(subprocess.check_output(['python', '-c',
            'import json,torch; torch.cuda.init(); print(json.dumps([torch.cuda.get_allocator_backend(),torch.cuda.memory_stats()["max_split_size"]]))'], text=True))
        if effective != ['native', 128 * 1024 * 1024]:
            raise ValueError('Effective allocator differs from the recovery contract')
    elif os.environ.get('JBGS_RUNTIME_REVISION') or os.environ.get('PYTORCH_CUDA_ALLOC_CONF'):
        raise ValueError('An allocator revision requires its immutable contract')
    condition = next(row for row in cfg['conditions'] if row['id'] == args.condition)
    repeat_binding = load_repeat_binding(args.config, layout_path, args.region, args.condition, args.phase)
    input_root, source, output = Path('/input'), Path('/source'), Path('/output')
    sealed = json.loads((input_root / 'input_manifest.json').read_text())
    if sealed['status'] != 'INPUTS_SEALED_FOR_EXECUTION' or sealed['region'] != args.region:
        raise ValueError('A sealed matching region input is required')
    if sealed['config_sha256'] != hashlib.sha256(config_bytes).hexdigest():
        raise ValueError('Configuration differs from the pre-training input seal')
    for row in sealed['files']:
        if sha(input_root / row['path']) != row['sha256']:
            raise ValueError(f'Input bytes changed: {row["path"]}')
    if any(p.exists() for p in (Path('/reference'), Path('/artifacts/JointBuildGS'))):
        raise ValueError('Training/rendering container may not mount reference or broad artifact root')
    receipt_path = output / f'{args.phase}_receipt.json'
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    # Preserve exact audit-driver bytes separately from the immutable native
    # source copy; future validation fixes must not erase execution provenance.
    with (output / f'{args.phase}_driver_snapshot.py').open('xb') as f:
        f.write(Path(__file__).read_bytes())
    with (output / f'{args.phase}_config_snapshot.json').open('xb') as f:
        f.write(config_bytes)
    if runtime_layout:
        with (output / f'{args.phase}_runtime_layout_snapshot.json').open('xb') as f:
            f.write(layout_path.read_bytes())
    if repeat_binding:
        with (output / f'{args.phase}_repeat_contract_snapshot.json').open('xb') as f:
            f.write(Path('/repeat_contract.json').read_bytes())
        with (output / f'{args.phase}_repeat_helper_snapshot.py').open('xb') as f:
            f.write(REPEAT_HELPER_SOURCE)
    if args.phase == 'auxiliary':
        with (output / 'auxiliary_helper_snapshot.py').open('xb') as f:
            f.write(Path('/audit/run_auxiliary.py').read_bytes())
    extraction_helper_snapshot = None
    if args.phase in ('render', 'auxiliary'):
        helper_path = output / f'{args.phase}_extraction_helper_snapshot.py'
        with helper_path.open('xb') as f:
            f.write(PARSER_SOURCE)
        extraction_helper_snapshot = {'path': helper_path.name, 'sha256': PARSER_SHA256}
    model = output / 'model'
    paths = sealed['training_paths']
    command = ['python', 'train.py', '-s', str(input_root / 'scene'), '-m', str(model),
               '--lod_depth_path', str(input_root / paths['prior_depth']),
               '--da_depth_path', str(input_root / paths['da3_depth']),
               '--lod2_pcd_path', str(input_root / paths['protection_pcd']),
               '--eval', '--lod_init', '--freeze_onlybldg', '--protect_bldg',
               '--dynamic_depth_weight', '-r', '1', '--port', '0',
               '--iterations', '30000', '--stage_switch_iter', '8000',
               '--lambda_lod_init', '0.08', '--lambda_lod_anchor', str(condition['lambda_lod_anchor']),
               '--jbgs_capture_iterations', '8000', '8100', '30000',
               '--jbgs_input_manifest', str(input_root / 'input_manifest.json')]
    if args.phase in ('train', 'parity'):
        if model.exists():
            raise FileExistsError(model)
        resume_native = bool(repeat_binding or (runtime_layout and runtime_layout['anchors'][args.region]['native_final_starts_from_anchor']))
        if args.condition != 'D005_Pnative' or args.phase == 'parity' or resume_native:
            anchor = Path('/anchor/checkpoint.pth')
            if not anchor.is_file():
                raise ValueError('Exact native complete anchor is not mounted')
            anchor_receipt = json.loads(anchor.with_name('receipt.json').read_text())
            if sha(anchor) != anchor_receipt['checkpoint_sha256'] or anchor_receipt['iteration'] != 8000:
                raise ValueError('Actual anchor bytes differ from the completed baseline checkpoint receipt')
            expected_anchor = runtime_layout['anchors'][args.region].get('checkpoint_sha256') if runtime_layout else None
            if expected_anchor and expected_anchor != anchor_receipt['checkpoint_sha256']:
                raise ValueError('Anchor differs from the recovery contract')
            command += ['--jbgs_resume_full', str(anchor)]
        if condition['protection'] == 'released':
            command += ['--jbgs_release_protection', '--lod2_building_xyz_lr_scale', '1',
                        '--protect_bldg_lr_scale', '1']
        if args.phase == 'parity':
            if args.condition != 'D005_Pnative':
                raise ValueError('Restart parity is evaluated in the native condition')
            command += ['--jbgs_stop_after', '8100']
    elif args.phase == 'render':
        train_receipt = json.loads((output / 'train_receipt.json').read_text())
        require_repeat_receipt(train_receipt, repeat_binding)
        if train_receipt['status'] != 'PASS':
            raise ValueError('Only a verified completed training may be rendered')
        command = ['python', 'render.py', '-s', '/input/scene', '-m', str(model),
                   '--iteration', '30000', '--mesh_res', str(cfg['extraction']['mesh_res'])]
    elif args.phase == 'auxiliary':
        command = ['python', '/audit/run_auxiliary.py', '--config', str(args.config),
                   '--region', args.region, '--condition', args.condition]
    else:
        render_receipt = json.loads((output / 'render_receipt.json').read_text())
        require_repeat_receipt(render_receipt, repeat_binding)
        if render_receipt['status'] != 'PASS':
            raise ValueError('Verified actual renders are required')
        command = ['python', 'metrics.py', '-m', str(model)]
    scheduling_lock, resource_scheduling = acquire_extraction_lock(args.phase)
    if scheduling_lock is not None:
        scheduling_snapshot = output / f'{args.phase}_scheduling_helper_snapshot.py'
        with scheduling_snapshot.open('xb') as f:
            f.write(SCHEDULER_SOURCE)
        resource_scheduling['helper_snapshot_path'] = scheduling_snapshot.name
    source_hashes = {str(p.relative_to(source)): sha(p) for p in sorted(source.rglob('*.py'))
                     if 'submodules' not in p.parts}
    start = time.time()
    preflight = {'task_id': cfg['task_id'], 'region': args.region, 'condition': args.condition,
                 'phase': args.phase, 'command': command,
                 'config_sha256': hashlib.sha256(config_bytes).hexdigest(),
                 'input_manifest_sha256': sha(input_root / 'input_manifest.json'),
                 'implementation_hashes': source_hashes,
                 'driver_sha256': sha(__file__), 'started_unix': start, 'scientific_verdict': None,
                 'runtime_image_id': os.environ['JBGS_RUNTIME_IMAGE_ID'],
                 'resource_scheduling': resource_scheduling,
                 'extraction_helper_snapshot': extraction_helper_snapshot,
                 'environment': {key: os.environ.get(key) for key in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'TORCH_HOME', 'OMP_NUM_THREADS', 'PYTORCH_CUDA_ALLOC_CONF', 'JBGS_RUNTIME_REVISION')},
                 'runtime_layout_sha256': sha(layout_path) if runtime_layout else None,
                 'runtime_revision': runtime_layout['revision'] if runtime_layout else 'v1',
                 'training_start_iteration': 8000 if '--jbgs_resume_full' in command else (0 if args.phase == 'train' else None),
                 'prior_initialization_and_anchor_retained': True,
                 'image_only': False}
    if repeat_binding:
        preflight.update(repeat_binding)
        preflight['repeat_helper_snapshot'] = {'path': f'{args.phase}_repeat_helper_snapshot.py',
                                               'sha256': REPEAT_HELPER_SHA256}
    if args.phase == 'render':
        render_ply = model / 'point_cloud/iteration_30000/point_cloud.ply'
        preflight['render_source_ply'] = {'path': str(render_ply.relative_to(output)), 'sha256': sha(render_ply)}
        preflight['render_cfg_args_sha256'] = sha(model / 'cfg_args')
    with (output / f'{args.phase}_invocation.json').open('x') as f:
        json.dump(preflight, f, indent=2)
    with (output / f'{args.phase}.log').open('x') as log, (output / f'{args.phase}_gpu.csv').open('x') as gpu:
        child = subprocess.Popen(command, cwd=source, stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            subprocess.run(['nvidia-smi', '--query-gpu=timestamp,uuid,memory.used,utilization.gpu',
                            '--format=csv,noheader,nounits'], stdout=gpu, stderr=subprocess.DEVNULL)
            gpu.flush()
            time.sleep(5)
        code = child.wait()
    native_code = code
    required, validation = [], []
    realized_extraction = None
    if args.phase == 'render':
        try:
            realized_extraction = parse_extraction_log(output / 'render.log', cfg['extraction']['mesh_res'],
                                                       cfg['extraction']['num_cluster'])
        except (OSError, UnicodeError, ValueError) as error:
            code = code or 96
            validation.append({'realized_extraction_validation_error': repr(error)})
    if code == 0:
        if args.phase in ('train', 'parity'):
            end = 8100 if args.phase == 'parity' else 30000
            required = [model / f'jbgs_complete/iteration_{end}/checkpoint.pth',
                        model / f'jbgs_complete/iteration_{end}/point_cloud.ply']
            if args.phase == 'train':
                required.append(model / 'point_cloud/iteration_30000/point_cloud.ply')
        elif args.phase == 'render':
            required = [model / 'train/ours_30000/fuse.ply', model / 'train/ours_30000/fuse_post.ply']
            import numpy as np
            import open3d as o3d
            for path in required:
                try:
                    mesh = o3d.io.read_triangle_mesh(str(path))
                    finite = bool(np.isfinite(np.asarray(mesh.vertices)).all())
                    area = float(mesh.get_surface_area())
                    valid = len(mesh.vertices) > 0 and len(mesh.triangles) > 0 and finite and area > 0
                    validation.append({'path': str(path.relative_to(output)), 'vertices': len(mesh.vertices),
                                       'triangles': len(mesh.triangles), 'finite_vertices': finite,
                                       'surface_area_m2': area, 'valid_triangle_surface': valid})
                    if not valid:
                        code = 95
                except Exception as error:
                    code = 95
                    validation.append({'surface_validation_error': repr(error)})
            count = len(list((model / 'test/ours_30000/renders').glob('*.png')))
            validation.append({'evaluation_renders': count, 'expected': cfg['regions'][args.region]['expected_test']})
            if count != cfg['regions'][args.region]['expected_test']:
                code = 92
        elif args.phase == 'auxiliary':
            required = [output / 'auxiliary_manifest.json']
            if json.loads(required[0].read_text())['status'] != 'PASS':
                code = 94
        else:
            required = [model / 'results.json', model / 'per_view.json']
            try:
                metrics = json.loads(required[0].read_text())['ours_30000']
                per = json.loads(required[1].read_text())['ours_30000']
                if not all(math.isfinite(metrics[k]) and len(per[k]) == cfg['regions'][args.region]['expected_test']
                           for k in ('PSNR', 'SSIM', 'LPIPS')):
                    code = 93
                validation.append({'metrics': metrics, 'native_lpips_backbone': 'vgg', 'native_lpips_range': '[0,1]'})
            except Exception as error:
                code = 93
                validation.append({'metric_validation_error': repr(error)})
        for path in required:
            exists = path.is_file() and path.stat().st_size > 0
            row = {'path': str(path.relative_to(output)), 'exists_nonempty': exists}
            if exists:
                row.update(bytes=path.stat().st_size, sha256=sha(path))
            else:
                code = 91
            validation.append(row)
    receipt = dict(preflight, status='PASS' if code == 0 else 'FAIL', native_exit_code=native_code,
                   validated_exit_code=code, wall_seconds=time.time() - start, finished_unix=time.time(),
                   child_peak_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
                   validation=validation, realized_extraction=realized_extraction)
    with receipt_path.open('x') as f:
        json.dump(receipt, f, indent=2, allow_nan=False)
    print(json.dumps({k: receipt[k] for k in ('region', 'condition', 'phase', 'status', 'wall_seconds', 'validated_exit_code')}))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
