"""Docker-only SfM/no-anchor training and native surface export, isolated outputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def validate_v3_bundle(amendment, runtime, source, evidence, region, config_sha):
    """Recheck only narrow sealed evidence copies; never mount a reference/task root."""
    from seal_memory_attempt import (validate_runtime, validate_final_policy, validate_predecessor,
                                     validate_cgroup_failure, bundle_filename,
                                     FINAL_POLICY_SHA, RETRY_ATTEMPTS, PREDECESSORS)
    meta = amendment.get('final_resource_retry', {})
    records = amendment.get('final_retry_evidence_bundle', {})
    names = {'policy', 'predecessor_training_receipt', 'predecessor_native_log',
             'predecessor_amendment', 'predecessor_first_step', 'runtime_validation'}
    resource_records = {}
    if 'predecessor_resource_failure' in meta:
        names.add('predecessor_resource_failure')
        for record in meta.get('resource_failure_evidence', []):
            role = record.get('role')
            if role not in ('kernel_journal', 'docker_inspect', 'docker_inspect_command') or role in resource_records:
                raise ValueError('Unexpected or duplicate cgroup evidence role')
            resource_records[role] = record
            names.add('resource_evidence_' + role)
    if (set(records) != names or amendment.get('resource_recovery_version') != 3
            or amendment.get('attempt_id') != RETRY_ATTEMPTS[region]
            or meta.get('predecessor_attempt_id') != PREDECESSORS[region]
            or meta.get('region') != region or meta.get('attempt_index') != 1 or meta.get('max_attempts') != 1
            or meta.get('fresh_only') is not True or meta.get('resume') is not False
            or meta.get('automatic_further_retry') is not False
            or meta.get('resource_recovery_version') != 3 or meta.get('storage_version') != 2):
        raise ValueError('Final resource retry identity or evidence membership differs')
    loaded = {}
    for key in sorted(names):
        record = records[key]
        filename = bundle_filename(key)
        path = evidence / filename
        canonical = (amendment['validation'] if key == 'runtime_validation'
                     else resource_records[key.removeprefix('resource_evidence_')] if key.startswith('resource_evidence_')
                     else meta[key])
        if (record.get('filename') != filename or path.stat().st_size != record.get('bytes')
                or sha(path) != record.get('sha256') or record['sha256'] != canonical.get('sha256')
                or (key != 'runtime_validation' and record['bytes'] != canonical.get('bytes'))):
            raise ValueError('Final retry evidence copy differs: ' + key)
        loaded[key] = path.read_text() if path.suffix in ('.log', '.txt') else json.loads(path.read_text())
    validate_final_policy(evidence / 'policy.json', FINAL_POLICY_SHA, region, amendment['attempt_id'],
                          meta['predecessor_attempt_id'], config_sha)
    validate_runtime(source, runtime, loaded['runtime_validation'])
    predecessor = loaded['predecessor_amendment']
    cgroup_oom = False
    if 'predecessor_resource_failure' in loaded:
        proof = loaded['predecessor_resource_failure']
        expected_records = {row['role']: {key: row[key] for key in ('role', 'path', 'bytes', 'sha256')}
                            for row in proof.get('evidence', [])
                            if row.get('role') in ('kernel_journal', 'docker_inspect', 'docker_inspect_command')}
        if expected_records != resource_records:
            raise ValueError('Cgroup source receipt and resource evidence binding differ')
        cgroup_oom = validate_cgroup_failure(proof,
            {role: loaded['resource_evidence_' + role] for role in resource_records},
            loaded['predecessor_training_receipt'], meta['predecessor_training_receipt']['sha256'],
            region, meta['predecessor_attempt_id'])
    validate_predecessor(loaded['predecessor_training_receipt'], loaded['predecessor_first_step'],
                         loaded['predecessor_native_log'], predecessor, region, config_sha,
                         meta['predecessor_attempt_id'], cgroup_oom=cgroup_oom)
    if (loaded['predecessor_training_receipt'].get('memory_recovery_amendment_sha256')
            != meta['predecessor_amendment']['sha256']):
        raise ValueError('Predecessor producer amendment binding differs')
    for key in ('original_failed_run_receipt', 'original_failed_log', 'prior_resource_attempts',
                'prior_initialization_failure'):
        if predecessor.get(key) != amendment.get(key):
            raise ValueError('Final retry must retain complete earlier failure history: ' + key)
    return meta


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--region', required=True, choices=['P1', 'P2', 'P3'])
    p.add_argument('--phase', required=True, choices=['train', 'export'])
    p.add_argument('--iteration', type=int, choices=[22000, 30000])
    p.add_argument('--memory-recovery', action='store_true')
    p.add_argument('--resource-recovery-version', type=int, choices=[3])
    a = p.parse_args()
    if a.resource_recovery_version and not a.memory_recovery:
        raise ValueError('Resource v3 requires the memory recovery path')
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    if any(Path(x).exists() for x in ['/reference', '/task', '/artifacts/JointBuildGS']):
        raise RuntimeError('Training/export cannot mount broad artifact or reference roots')
    cfg = json.loads(Path('/config.json').read_text())
    base = json.loads(Path('/base_config.json').read_text())
    if sha('/base_config.json') != cfg['base_config_sha256']:
        raise ValueError('Frozen base configuration changed')
    if os.environ['JBGS_RUNTIME_IMAGE_ID'] != cfg['runtime_image_id']:
        raise ValueError('Unexpected runtime image')
    if os.environ['PYTORCH_CUDA_ALLOC_CONF'] != cfg['resources']['allocator']:
        raise ValueError('Unexpected allocator')
    sealed = json.loads(Path('/input/input_manifest.json').read_text())
    if sealed['region'] != a.region or sealed['config_sha256'] != cfg['base_config_sha256']:
        raise ValueError('Regional input seal mismatch')
    for item in sealed['files']:
        if sha(Path('/input') / item['path']) != item['sha256']:
            raise ValueError('Original input changed: ' + item['path'])
    out = Path('/output')
    receipt = out / 'receipt.json'
    if receipt.exists():
        raise FileExistsError(receipt)
    shutil.copyfile(__file__, out / 'driver_snapshot.py')
    shutil.copyfile('/config.json', out / 'config_snapshot.json')
    sfm_manifest = Path('/sfm_input/initialization_manifest.json')
    if not sfm_manifest.exists():
        raise FileNotFoundError(sfm_manifest)
    sfm = json.loads(sfm_manifest.read_text())
    if sfm['region'] != a.region or sfm['source_points3D_sha256'] != cfg['initialization']['points3D_sha256']:
        raise ValueError('SfM initialization lineage differs from the plan')
    if sha(Path('/sfm_input') / sfm['points_ply_path']) != sfm['points_ply_sha256']:
        raise ValueError('SfM initialization bytes changed')
    for name in ['cameras.bin', 'images.bin']:
        if sha(Path('/sfm_input/scene/sparse/0') / name) != sha(Path('/input/scene/sparse/0') / name):
            raise ValueError('SfM path changed frozen cameras or poses')
    for name in ['jbgs_calibration.json', 'scene_reference_frame.json']:
        if sha(Path('/sfm_input/scene') / name) != sha(Path('/input/scene') / name):
            raise ValueError('SfM path changed scene calibration')
    runtime = json.loads(Path('/source/jbgs_no_anchor_runtime_receipt.json').read_text())
    if runtime['status'] != 'PASS_RUNTIME_PREPARED_NO_TRAINING':
        raise ValueError('Runtime preparation has not passed')
    expected_source = runtime['destination_python_sha256']
    recovery_metadata = {}
    additional_captures = []
    if a.memory_recovery:
        amendment = json.loads(Path('/amendment.json').read_text())
        memory_runtime = json.loads(Path('/source/jbgs_memory_recovery_receipt.json').read_text())
        if (amendment['original_config_sha256'] != sha('/config.json')
                or amendment['arithmetic_or_scientific_controls_changed'] is not False
                or amendment['scientific_verdict'] is not None
                or amendment['runtime_receipt_sha256'] != sha('/source/jbgs_memory_recovery_receipt.json')
                or memory_runtime['status'] != 'PASS_MEMORY_RECOVERY_RUNTIME_PREPARED'
                or memory_runtime['science_config_unchanged'] is not True
                or memory_runtime['parent_runtime_receipt_sha256'] != sha('/source/jbgs_no_anchor_runtime_receipt.json')
                or memory_runtime['original_source_python_sha256'] != expected_source):
            raise ValueError('Memory-only recovery amendment mismatch')
        expected_source = memory_runtime['destination_python_sha256']
        additional_captures = amendment.get('additional_capture_iterations', [])
        if additional_captures and (memory_runtime.get('storage_version') != 2
                                    or additional_captures != [8000, 15000]):
            raise ValueError('Unexpected diagnostic checkpoint schedule')
        if memory_runtime.get('resource_recovery_version') != a.resource_recovery_version:
            raise ValueError('Explicit resource implementation version differs from source')
        recovery_metadata = {
            'memory_recovery_amendment_sha256': sha('/amendment.json'),
            'memory_recovery_amendment_path': amendment['task_relative_path'],
            'attempt_id': amendment['attempt_id'],
        }
        if a.resource_recovery_version == 3:
            if additional_captures != [8000, 15000]:
                raise ValueError('Final retry requires the frozen intermediate captures')
            meta = validate_v3_bundle(amendment, memory_runtime, Path('/source'), Path('/retry_evidence'),
                                      a.region, sha('/config.json'))
            recovery_metadata.update(resource_recovery_version=3, storage_version=2,
                                     final_resource_retry=meta,
                                     resource_contract_validator_sha256=sha(Path(__file__).with_name('seal_memory_attempt.py')))
        shutil.copyfile('/amendment.json', out / 'memory_recovery_amendment_snapshot.json')
    actual_source_files = {str(p.relative_to('/source')) for p in Path('/source').rglob('*.py')
                           if not {'.git', '__pycache__'}.intersection(p.relative_to('/source').parts)}
    if actual_source_files != set(expected_source):
        raise ValueError('Prepared runtime Python file membership changed')
    for name, expected in expected_source.items():
        if sha(Path('/source') / name) != expected:
            raise ValueError('Prepared runtime changed: ' + name)
    t = cfg['training']
    capture_iterations = sorted(set(t['capture_iterations'] + additional_captures))
    if a.phase == 'train':
        model = out / 'model'
        if model.exists():
            raise FileExistsError(model)
        paths = sealed['training_paths']
        cmd = [sys.executable, 'train.py', '-s', '/sfm_input/scene', '-m', str(model),
               '--lod_depth_path', '/input/' + paths['prior_depth'],
               '--da_depth_path', '/input/' + paths['da3_depth'],
               '--lod2_pcd_path', '/input/' + paths['protection_pcd'],
               '--eval', '--freeze_onlybldg', '--protect_bldg', '--dynamic_depth_weight',
               '-r', '1', '--port', '0', '--iterations', str(t['iterations']),
               '--stage_switch_iter', '0', '--lambda_lod_anchor', str(t['lambda_lod_anchor']),
               '--lambda_da_depth', str(t['lambda_da_depth']),
               '--position_lr_max_steps', str(t['position_lr_max_steps']),
               '--densify_until_iter', str(t['densify_until_iter']),
               '--test_iterations', '22000', '30000', '--save_iterations', '22000', '30000',
               '--jbgs_capture_iterations', *map(str, capture_iterations),
               '--jbgs_input_manifest', str(sfm_manifest),
               '--jbgs_sfm_initialization_manifest', str(sfm_manifest)]
    else:
        if a.iteration is None:
            raise ValueError('Export iteration required')
        train = Path('/trained')
        if json.loads((train / 'receipt.json').read_text())['status'] != 'PASS':
            raise ValueError('Verified training required')
        source = train / 'model/jbgs_complete' / f'iteration_{a.iteration}'
        stored = json.loads((source / 'receipt.json').read_text())
        if sha(source / 'point_cloud.ply') != stored['ply_sha256']:
            raise ValueError('Completed snapshot PLY changed')
        model = out / 'model'
        ply_dir = model / 'point_cloud' / f'iteration_{a.iteration}'
        ply_dir.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(source / 'point_cloud.ply', ply_dir / 'point_cloud.ply')
        shutil.copyfile(train / 'model/cfg_args', model / 'cfg_args')
        cmd = [sys.executable, 'render.py', '-s', '/sfm_input/scene', '-m', str(model),
               '--iteration', str(a.iteration), '--mesh_res', '512', '--num_cluster', '50']
    invocation = {'task_id': cfg['task_id'], 'scientific_verdict': None, 'region': a.region,
                  'condition_id': cfg['condition_id'], 'phase': a.phase, 'iteration': a.iteration,
                  'command': cmd, 'cwd': '/source', 'config_sha256': sha('/config.json'),
                  'source_sha256': {str(x.relative_to('/source')): sha(x)
                                    for x in Path('/source').rglob('*.py')
                                    if 'submodules' not in x.parts and '__pycache__' not in x.parts},
                  'sfm_manifest_sha256': sha(sfm_manifest),
                  'original_input_manifest_sha256': sha('/input/input_manifest.json'),
                  'runtime_image_id': cfg['runtime_image_id'], 'reference_accessed': False,
                  'started_unix': time.time(), 'measurement_scope': 'native child launch through output validation'}
    invocation.update(recovery_metadata)
    write(out / 'invocation.json', invocation)
    start = time.monotonic()
    with (out / 'native.log').open('x') as log, (out / 'gpu.csv').open('x') as gpu:
        child = subprocess.Popen(cmd, cwd='/source', stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            subprocess.run(['nvidia-smi', '--query-gpu=timestamp,uuid,memory.used,utilization.gpu',
                            '--format=csv,noheader,nounits'], stdout=gpu, stderr=subprocess.DEVNULL)
            gpu.flush()
            time.sleep(5)
        native_code = child.wait()
    code = native_code
    checks, outputs = [], []
    try:
        if native_code == 0 and a.phase == 'train':
            if a.memory_recovery:
                lifecycle_root = model / 'jbgs_memory_recovery'
                lifecycle = json.loads((lifecycle_root / 'receipt.json').read_text())
                depth_transfer = json.loads((lifecycle_root / 'first_depth_transfer.json').read_text())
                if (lifecycle['status'] != 'PASS_MEMORY_LIFECYCLE_COMPLETED'
                        or lifecycle['last_completed_iteration'] != t['iterations']
                        or lifecycle['moments_restored'] is not True
                        or lifecycle['first_populated_moment_roundtrip_checked'] is not True
                        or depth_transfer['status'] != 'PASS_SELECTED_DEPTH_TRANSFER'):
                    raise ValueError('Memory placement lifecycle did not complete')
                checks.append({'memory_lifecycle': lifecycle, 'selected_depth_transfer': depth_transfer})
                for filename in ['initialization.json', 'first_depth_transfer.json', 'receipt.json', 'trace.jsonl']:
                    f = lifecycle_root / filename
                    outputs.append({'path': str(f.relative_to(out)), 'bytes': f.stat().st_size, 'sha256': sha(f)})
                if a.resource_recovery_version == 3:
                    initialized = json.loads((lifecycle_root / 'initialization.json').read_text())
                    if (lifecycle.get('resource_recovery_version') != 3
                            or lifecycle.get('early_gradient_clear_calls') != t['iterations']
                            or lifecycle.get('original_before_backward_zero_grad_retained') is not True
                            or initialized.get('early_zero_grad_added') is not True
                            or initialized.get('stream_ply_instance_binding') is not True):
                        raise ValueError('v3 early gradient release lifecycle incomplete')
                    stream_audit = lifecycle_root / 'ply_saves.jsonl'
                    stream_rows = [json.loads(line) for line in stream_audit.read_text().splitlines()]
                    for n in capture_iterations:
                        path = model / 'jbgs_complete' / f'iteration_{n}' / 'point_cloud.ply'
                        matching = [row for row in stream_rows if row.get('path') == str(path)]
                        if (len(matching) != 1 or matching[0].get('status') != 'PASS_STREAMED_PLY_WRITTEN'
                                or matching[0].get('sha256') != sha(path)
                                or matching[0].get('fields') != 61
                                or matching[0].get('full_model_tuple_list_created') is not False):
                            raise ValueError('v3 completed capture lacks matching streamed PLY proof')
                    outputs.append({'path': str(stream_audit.relative_to(out)), 'bytes': stream_audit.stat().st_size,
                                    'sha256': sha(stream_audit)})
            initial = json.loads((model / 'jbgs_no_anchor/initialization.json').read_text())
            first = json.loads((model / 'jbgs_no_anchor/first_step.json').read_text())
            if initial['status'] != 'PASS_PREOPTIMIZATION_PROTECTION' or first['status'] != 'PASS_FIRST_STEP_DIRECT_REFINEMENT':
                raise ValueError('Fresh-SfM/refinement controls did not pass')
            checks.append({'initialization': initial, 'first_step': first, 'actual_optimizer_updates': 30000})
            rows = [json.loads(x) for x in (model / 'jbgs_trace.jsonl').read_text().splitlines()]
            direct_refinement = all(x['lod_weight'] == .005 and x['da_weight'] > 0 for x in rows)
            checks.append({'all_recorded_steps_refinement': direct_refinement})
            checks.append({'first_recorded_step': rows[0]['iteration'], 'last_recorded_step': rows[-1]['iteration']})
            if rows[0]['iteration'] != 1 or rows[-1]['iteration'] != 30000 or not direct_refinement:
                raise ValueError('Refinement trace contract failed')
            for n in capture_iterations:
                root = model / 'jbgs_complete' / f'iteration_{n}'
                record = json.loads((root / 'receipt.json').read_text())
                for filename, key in [('point_cloud.ply', 'ply_sha256'), ('checkpoint.pth', 'checkpoint_sha256')]:
                    f = root / filename
                    if sha(f) != record[key]:
                        raise ValueError('Incomplete snapshot')
                    outputs.append({'path': str(f.relative_to(out)), 'bytes': f.stat().st_size, 'sha256': record[key]})
        elif native_code == 0:
            import numpy as np
            import open3d as o3d
            sys.path.insert(0, '/audit')
            from parse_extraction import parse_extraction_log
            checks.append({'realized_extraction': parse_extraction_log(out / 'native.log', 512, 50)})
            for name in ['fuse.ply', 'fuse_post.ply']:
                f = model / 'train' / f'ours_{a.iteration}' / name
                mesh = o3d.io.read_triangle_mesh(str(f))
                valid = len(mesh.triangles) > 0 and np.isfinite(np.asarray(mesh.vertices)).all() and mesh.get_surface_area() > 0
                if not valid:
                    raise ValueError('Invalid extracted surface')
                checks.append({'file': name, 'vertices': len(mesh.vertices), 'triangles': len(mesh.triangles), 'area_m2': mesh.get_surface_area()})
                outputs.append({'path': str(f.relative_to(out)), 'bytes': f.stat().st_size, 'sha256': sha(f)})
                del mesh
            render_count = len(list((model / 'test' / f'ours_{a.iteration}' / 'renders').glob('*.png')))
            if render_count != base['regions'][a.region]['expected_test']:
                raise ValueError('Evaluation render membership count mismatch')
            checks.append({'evaluation_render_count': render_count})
    except Exception as error:
        checks.append({'validation_error': repr(error)})
        code = 91
    write(receipt, dict(invocation, status='PASS' if code == 0 else 'FAIL', native_exit_code=native_code,
                        validated_exit_code=code, finished_unix=time.time(),
                        wall_seconds=time.monotonic() - start,
                        child_peak_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
                        validation=checks, outputs=outputs))
    print(json.dumps({'region': a.region, 'phase': a.phase, 'iteration': a.iteration, 'status': 'PASS' if code == 0 else 'FAIL'}), flush=True)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
