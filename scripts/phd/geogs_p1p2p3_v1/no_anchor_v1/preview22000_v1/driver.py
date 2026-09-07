#!/usr/bin/env python3
"""One declared official test-RGB preview; never train, mesh, resume or score."""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time
import traceback

POLICY_SHA = 'b104c30133fc22a26b35428a1865f78c6a8e3d86d2186d3552897c130c19dcfc'
IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
ATTEMPT = 'no_anchor_sfm_gradient_memory_v3_P2'
CID = 'SFM_noanchor_D005_Pnative'
RUN = ATTEMPT + '/runs/P2/' + CID
OUT = Path('/output')
PARENT = Path('/parent')
SOURCE = Path('/source')
NAMES = [f'{i:05d}.png' for i in range(9)]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def optional_inspection(path):
    path = Path(path)
    return read(path) if path.is_file() and path.stat().st_size else None


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def rec(path, label):
    return dict(path=label, bytes=Path(path).stat().st_size, sha256=sha(path))


def source_map():
    return {str(p.relative_to(SOURCE)): sha(p) for p in sorted(SOURCE.rglob('*.py'))
            if not {'.git', '__pycache__'}.intersection(p.relative_to(SOURCE).parts)}


def parent_state():
    """A producer receipt is authoritative; absence is never converted to FAIL."""
    p = PARENT / 'receipt.json'
    if p.exists():
        d = read(p)
        require(d.get('region') == 'P2' and d.get('condition_id') == CID and d.get('phase') == 'train'
                and d.get('status') in ('PASS', 'FAIL') and d.get('scientific_verdict') is None,
                'Parent receipt identity/status differs')
        require(isinstance(d.get('finished_unix'), (int, float)) and math.isfinite(d['finished_unix']),
                'Parent receipt has no actual completion time')
        return dict(status=d['status'], observed_unix=time.time(), training_receipt_present=True,
                    training_receipt=rec(p, RUN + '/receipt.json'))
    inspection = OUT / 'resource_observations/after.parent.json'
    if not inspection.exists():
        inspection = OUT / 'resource_observations/before.parent.json'
    observed = optional_inspection(inspection)
    running = observed is not None and observed.get('State', {}).get('Running') is True
    return dict(status='RUNNING' if running else 'UNKNOWN_NO_CLOSED_RECEIPT', observed_unix=time.time(),
                training_receipt_present=False, training_receipt=None,
                running_observation_scope='last available wrapper Docker inspection; no live Docker access inside preview',
                docker_inspection=rec(inspection, str(inspection.relative_to(OUT))) if observed else None,
                docker_observed_at=inspection.with_name(inspection.name.replace('.parent.json', '.time.txt')).read_text().strip()
                if observed else None)


def static_proof():
    require(Path('/.dockerenv').exists(), 'Docker required')
    require(not any(Path(p).exists() for p in ('/task', '/reference', '/artifacts/JointBuildGS')),
            'Broad task/reference/artifact mount forbidden')
    require(os.environ.get('JBGS_RUNTIME_IMAGE_ID') == IMAGE, 'Frozen runtime image differs')
    require(sha('/policy.json') == POLICY_SHA, 'Frozen policy differs')
    policy = read('/policy.json')
    require(policy['selected_attempt'] == ATTEMPT and policy['iteration'] == 22000 and policy['gpu'] == 1,
            'Preview identity differs')
    require(sha('/config.json') == policy['config_sha256'] == sha(PARENT / 'config_snapshot.json'),
            'Parent configuration differs')
    require(sha('/amendment.json') == policy['amendment_sha256'] == sha(PARENT / 'memory_recovery_amendment_snapshot.json'),
            'Resource amendment differs')
    amendment = read('/amendment.json')
    require(amendment['status'] == 'SEALED_BEFORE_RETRY' and amendment['region'] == 'P2'
            and amendment['attempt_id'] == ATTEMPT and amendment['resource_recovery_version'] == 3
            and amendment['arithmetic_or_scientific_controls_changed'] is False, 'Invalid sealed amendment')
    runtime_path = SOURCE / 'jbgs_memory_recovery_receipt.json'
    require(sha(runtime_path) == amendment['runtime_receipt_sha256'], 'Runtime receipt differs')
    runtime = read(runtime_path)
    mapping = source_map()
    require(mapping == runtime['destination_python_sha256'] == amendment['prepared_source_python_sha256'],
            'Frozen source membership/hash differs')
    require(runtime['resource_recovery_version'] == 3 and runtime['science_config_unchanged'] is True,
            'Runtime scientific controls differ')
    require(mapping['render.py'] == policy['render_sha256'], 'Official renderer differs')
    require(mapping['train.py'] == '1680d6e357877a03811c912804d211fe7c4b77562ecf24999d573fb4897450cb'
            and mapping['jbgs_state.py'] == '7114f78e6f429c9186ce44e81a0c40d18e5087994f99a52d81eeee18ab7fa570',
            'Audited after-optimizer snapshot source differs')
    invocation = read(PARENT / 'invocation.json')
    require(invocation['region'] == 'P2' and invocation['condition_id'] == CID and invocation['phase'] == 'train'
            and invocation['config_sha256'] == policy['config_sha256']
            and invocation['memory_recovery_amendment_sha256'] == policy['amendment_sha256']
            and invocation['resource_recovery_version'] == 3, 'Training invocation differs')
    require(invocation['source_sha256'] == {k: v for k, v in mapping.items() if 'submodules' not in Path(k).parts},
            'Training and preview sources differ')
    command = invocation['command']
    for flag, value in {'--iterations': '30000', '--stage_switch_iter': '0', '--lambda_lod_anchor': '0.005',
                        '--lambda_da_depth': '0.05', '--densify_until_iter': '15000'}.items():
        require(command.count(flag) == 1 and command[command.index(flag) + 1] == value, 'Training control differs: ' + flag)
    require(not any(x in command for x in ('--start_checkpoint', '--jbgs_resume_full')), 'Resume is forbidden')
    sfm_path = Path('/sfm_input/initialization_manifest.json')
    sfm = read(sfm_path)
    require(sha(sfm_path) == invocation['sfm_manifest_sha256'], 'SfM manifest differs')
    require(sfm['source_kind'] == 'image_sfm' and sfm['contains_als_points'] is False
            and sfm['region'] == 'P2' and sfm['point_count'] == 5665, 'SfM identity differs')
    require(sha('/sfm_input/' + sfm['points_ply_path']) == sfm['points_ply_sha256'], 'SfM bytes differ')
    input_path = Path('/input/input_manifest.json')
    inputs = read(input_path)
    require(sha(input_path) == invocation['original_input_manifest_sha256'] == sfm['original_input_manifest']['sha256'],
            'Original regional input manifest differs')
    require(sha('/base_config.json') == sfm['base_config']['sha256'] == inputs['config_sha256'], 'Base configuration differs')
    split_path = Path('/input') / inputs['split_path']
    require(sha(split_path) == inputs['split_sha256'] == sfm['original_split']['sha256'], 'Image split differs')
    split = read(split_path)
    photos = split['evaluation']
    require(len(photos) == 9 and [r['name'] for r in photos] == sorted(r['name'] for r in photos),
            'Frozen nine-camera evaluation order differs')
    for row in photos:
        require(sha(Path('/input/scene/images') / row['name']) == row['sha256'], 'Evaluation image bytes differ')
    for name in ('cameras.bin', 'images.bin'):
        require(sha(Path('/sfm_input/scene/sparse/0') / name) == sha(Path('/input/scene/sparse/0') / name),
                'Regional COLMAP camera/pose bytes differ')
    init_path = PARENT / 'model/jbgs_no_anchor/initialization.json'
    first_path = PARENT / 'model/jbgs_no_anchor/first_step.json'
    init, first = read(init_path), read(first_path)
    require(init['status'] == 'PASS_PREOPTIMIZATION_PROTECTION' and init['manifest_sha256'] == sha(sfm_path)
            and init['points_ply_sha256'] == sfm['points_ply_sha256']
            and init['gaussian_xyz_matches_sfm_float32_order'] is True
            and init['fresh_optimizer_state_entries'] == 0 and init['als_gaussians_inserted'] == 0
            and init['protection_applied_before_first_step'] is True, 'Initial SfM/protection audit failed')
    require(first['status'] == 'PASS_FIRST_STEP_DIRECT_REFINEMENT' and first['iteration'] == 1
            and first['stage2_active'] is True and first['anchor_iterations_executed'] == 0
            and first['pretrained_optimizer_loaded'] is False and first['optimizer_state_entries'] == 6
            and first['lod_weight'] == .005 and first['da_weight'] == .05
            and first['protected_gaussians'] == init['protected_gaussians'] == 1437, 'First-step controls differ')
    cfg = ast.parse((PARENT / 'model/cfg_args').read_text(), mode='eval').body
    require(isinstance(cfg, ast.Call) and isinstance(cfg.func, ast.Name) and cfg.func.id == 'Namespace' and not cfg.args,
            'Unexpected native cfg_args syntax')
    args = {k.arg: ast.literal_eval(k.value) for k in cfg.keywords}
    require(args['eval'] is True and args['sh_degree'] == 3 and args['resolution'] == 1
            and args['source_path'] == '/sfm_input/scene', 'Renderer camera/SH settings differ')
    historic_path = Path('/historical_export_receipt.json')
    require(sha(historic_path) == policy['historical_export_receipt_sha256'], 'Historical GT receipt differs')
    historic = read(historic_path)
    require(historic['status'] == 'PASS' and historic['phase'] == 'export' and historic['region'] == 'P2'
            and historic['iteration'] == 8000 and historic['native_exit_code'] == historic['validated_exit_code'] == 0,
            'Historical official export is not validated')
    gt_rows = {Path(r['path']).name: r for r in historic['outputs']
               if r['path'].startswith('model/test/ours_8000/gt/')}
    require(sorted(gt_rows) == NAMES and sorted(p.name for p in Path('/historical_gt').iterdir()) == NAMES,
            'Historical GT membership differs')
    for name in NAMES:
        require(sha(Path('/historical_gt') / name) == gt_rows[name]['sha256'], 'Historical GT bytes differ')
    files = [(Path('/policy.json'), 'contracts/sfm_prefix22000_rgb_preview_v1.json'),
             (Path('/config.json'), ATTEMPT + '/config.json'), (Path('/amendment.json'), ATTEMPT + '/amendment.json'),
             (runtime_path, ATTEMPT + '/source/jbgs_memory_recovery_receipt.json'),
             (PARENT / 'invocation.json', RUN + '/invocation.json'), (PARENT / 'model/cfg_args', RUN + '/model/cfg_args'),
             (init_path, RUN + '/model/jbgs_no_anchor/initialization.json'),
             (first_path, RUN + '/model/jbgs_no_anchor/first_step.json'),
             (sfm_path, ATTEMPT + '/inputs/P2/initialization_manifest.json'),
             (input_path, 'inputs/P2/input_manifest.json'), (split_path, 'inputs/P2/' + inputs['split_path']),
             (historic_path, policy['historical_export_receipt_task_relative'])]
    proof = dict(policy_sha256=POLICY_SHA, config_sha256=sha('/config.json'), source_sha256=mapping,
                 amendment_sha256=sha('/amendment.json'), files=[rec(p, label) for p, label in files],
                 sfm_manifest_sha256=sha(sfm_path), original_input_manifest_sha256=sha(input_path),
                 photos=[dict(index=i, image_name=r['name'], image_sha256=r['sha256']) for i, r in enumerate(photos)],
                 historical_gt_sha256={n: gt_rows[n]['sha256'] for n in NAMES},
                 snapshot_source_order=dict(train_optimizer_step_line=1005, after_step_line=1217,
                                            state_checkpoint_save_line=186, state_ply_save_line=187,
                                            receipt_after_both_payloads=True))
    return policy, proof, files


def snapshot_proof():
    import numpy as np
    from plyfile import PlyData
    trace_path = PARENT / 'model/jbgs_trace.jsonl'
    lines, rows, ready = [], [], None
    with trace_path.open('rb') as f:
        for line in f:
            if not line.endswith(b'\n'):
                break
            row = json.loads(line)
            if row['iteration'] <= 22000:
                lines.append(line)
                rows.append(row)
            if row['iteration'] >= 22100:
                ready = row
                break
    require(ready is not None, 'NOT_READY: observed trace must reach 22100 after completed 22000 capture')
    require([r['iteration'] for r in rows] == [1] + list(range(100, 22001, 100)), 'Trace prefix membership differs')
    for row in rows:
        require(all(not isinstance(v, (float, int)) or math.isfinite(v) for v in row.values()), 'Nonfinite trace')
        require(row['lod_weight'] == .005 and row['da_weight'] > 0 and row['protected'] == 1437, 'Trace controls differ')
    root = PARENT / 'model/jbgs_complete/iteration_22000'
    capture = read(root / 'receipt.json')
    require(capture['schema'] == 'JBGS_GEOGS_COMPLETE_STATE_v1' and capture['iteration'] == 22000
            and capture['after_protection_registration'] is True and capture['scientific_verdict'] is None
            and capture['gaussians'] == rows[-1]['gaussians'] > 0, 'Complete capture identity differs')
    require(re.fullmatch('[0-9a-f]{64}', capture['checkpoint_sha256']) is not None
            and (root / 'checkpoint.pth').stat().st_size > 0, 'Missing declared checkpoint')
    source_ply = root / 'point_cloud.ply'
    source_record = rec(source_ply, RUN + '/model/jbgs_complete/iteration_22000/point_cloud.ply')
    require(source_record['sha256'] == capture['ply_sha256'], 'Completed PLY digest differs')
    ply = PlyData.read(str(source_ply), mmap='r')
    fields = ['x', 'y', 'z', 'nx', 'ny', 'nz'] + [f'f_dc_{i}' for i in range(3)]
    fields += [f'f_rest_{i}' for i in range(45)] + ['opacity', 'scale_0', 'scale_1'] + [f'rot_{i}' for i in range(4)]
    require(not ply.text and ply.byte_order == '<' and [e.name for e in ply.elements] == ['vertex'], 'Native PLY format differs')
    data = ply['vertex'].data
    require(len(data) == capture['gaussians'] and list(data.dtype.names) == fields and data.dtype.itemsize == 244,
            'Gaussian count/61-field order differs')
    require(all(data.dtype.fields[name][0] == np.dtype('<f4') and data.dtype.fields[name][1] == i * 4
                for i, name in enumerate(fields)), 'PLY scalar dtype/layout differs')
    values = data.view('<f4').reshape(len(data), 61)
    for start in range(0, len(data), 16384):
        require(np.isfinite(values[start:start + 16384]).all(), 'Nonfinite Gaussian attribute')
    metadata = dict(gaussians=len(data), scalar_dtype='little-endian float32', field_order=fields,
                    vertex_order='unaltered byte copy', all_attributes_finite=True)
    del values, data, ply
    destination = OUT / 'model/point_cloud/iteration_22000/point_cloud.ply'
    destination.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source_ply, destination)
    require(sha(destination) == source_record['sha256'], 'PLY copy differs')
    shutil.copyfile(PARENT / 'model/cfg_args', OUT / 'model/cfg_args')
    require(sha(OUT / 'model/cfg_args') == sha(PARENT / 'model/cfg_args'), 'cfg_args copy differs')
    prefix = b''.join(lines)
    (OUT / 'trace_through_22000.jsonl').write_bytes(prefix)
    shutil.copyfile(root / 'receipt.json', OUT / 'capture_receipt_snapshot.json')
    return dict(capture_receipt=rec(root / 'receipt.json', RUN + '/model/jbgs_complete/iteration_22000/receipt.json'),
                ply=source_record, ply_structure=metadata,
                checkpoint=dict(path=RUN + '/model/jbgs_complete/iteration_22000/checkpoint.pth',
                                bytes=(root / 'checkpoint.pth').stat().st_size,
                                capture_declared_sha256=capture['checkpoint_sha256'],
                                independently_digested=False, tensor_payload_loaded=False, full_state_validated=False),
                trace_prefix=rec(OUT / 'trace_through_22000.jsonl', 'trace_through_22000.jsonl'),
                trace_original_path=RUN + '/model/jbgs_trace.jsonl', readiness_row=ready)


def validate_png(proof):
    import numpy as np
    from PIL import Image
    root = OUT / 'model/test/ours_22000'
    rows = []
    for kind in ('renders', 'gt'):
        require(sorted(p.name for p in (root / kind).iterdir()) == NAMES, 'Native PNG membership differs: ' + kind)
    for i, name in enumerate(NAMES):
        arrays = []
        for path in (root / 'renders' / name, root / 'gt' / name, Path('/historical_gt') / name):
            with Image.open(path) as im:
                require(im.format == 'PNG' and im.mode in ('RGB', 'RGBA'), 'Native PNG format differs')
                im.load()
                arrays.append(np.array(im.convert('RGB')))
        require(arrays[0].shape == arrays[1].shape == arrays[2].shape, 'PNG dimensions differ')
        require(np.array_equal(arrays[1], arrays[2]), 'Official GT pixels differ from validated historical GT')
        rows.append(dict(**proof['photos'][i], png_name=name, width=arrays[0].shape[1], height=arrays[0].shape[0],
                         historical_gt_decoded_rgb_equal=True,
                         historical_gt_byte_equal=sha(root / 'gt' / name) == proof['historical_gt_sha256'][name]))
    require(not (OUT / 'model/train').exists() and not list((OUT / 'model').rglob('fuse*.ply')),
            'Unexpected train rendering or mesh output')
    return rows


def boundary_receipt(exit_code):
    """Called in a separate CPU-only container after GPU process/container release."""
    files = [rec(p, str(p.relative_to(OUT))) for p in sorted((OUT / 'resource_observations').iterdir()) if p.is_file()]
    before = optional_inspection(OUT / 'resource_observations/before.parent.json')
    after_path = OUT / 'resource_observations/after.parent.json'
    after = read(after_path) if after_path.exists() and after_path.stat().st_size else None
    payload = dict(schema='GEOGS_PREVIEW22000_EXECUTION_BOUNDARY_v1', scientific_verdict=None,
                   status='PASS' if exit_code == 0 else 'FAIL', wrapper_exit_code=exit_code,
                   observed_unix=time.time(), observations=files,
                   parent_running_before=before.get('State', {}).get('Running') if before else None,
                   parent_running_after=after.get('State', {}).get('Running') if after else None,
                   parent_receipt_at_boundary=parent_state(),
                   shared_host_cpu_memory_storage_pcie_interference=True,
                   preview_additional_cost_not_main_pipeline_replacement=True,
                   native_receipt=rec(OUT / 'receipt.json', 'receipt.json') if (OUT / 'receipt.json').exists() else None,
                   command=rec(OUT / 'command.sh', 'command.sh') if (OUT / 'command.sh').exists() else None,
                   driver_sources={n: sha(OUT / 'driver_snapshot' / n) for n in ('driver.py', 'run.sh')})
    write(OUT / 'execution_receipt.json', payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true', help='Static CPU-only proof; no capture requirement, writes or rendering')
    parser.add_argument('--boundary-exit', type=int)
    args = parser.parse_args()
    if args.boundary_exit is not None:
        boundary_receipt(args.boundary_exit)
        return args.boundary_exit
    if args.preflight:
        _, proof, _ = static_proof()
        print(json.dumps(dict(status='PASS_STATIC_PREVIEW_PREFLIGHT', scientific_verdict=None,
                              snapshot_validated=False, gpu_work_performed=False, proof=proof), indent=2))
        return 0
    require(not (OUT / 'receipt.json').exists() and not (OUT / 'model').exists(), 'Single attempt output already exists')
    started = time.time()
    result = dict(schema='GEOGS_SFM_PREVIEW22000_RGB_v1', status='FAIL', region='P2', condition_id=CID,
                  iteration=22000, planned_total_updates=30000, scientific_verdict=None,
                  analysis_role='EARLY_OFFICIAL_TEST_RGB_PREVIEW', selected_attempt=ATTEMPT,
                  main_completion_inferred=False, main_experiment_replaced=False, geometry_assessed=False,
                  historical_prefix8000_replaced=False, full_checkpoint_tensor_validation_performed=False,
                  runtime_image_id=IMAGE, started_unix=started, native_exit_code=None, validated_exit_code=1,
                  render_attempts=0, max_render_attempts=1, reference_accessed=False, outputs=[])
    try:
        policy, proof, files = static_proof()
        result.update(proof)
        result['parent_observation_before'] = parent_state()
        result['parent_status_at_observation'] = result['parent_observation_before']['status']
        require(result['parent_status_at_observation'] in ('RUNNING', 'PASS', 'FAIL'), 'Parent state not observed')
        result['snapshot'] = snapshot_proof()
        for src, dst in (('/policy.json', 'policy_snapshot.json'), ('/config.json', 'config_snapshot.json'),
                         ('/amendment.json', 'amendment_snapshot.json')):
            shutil.copyfile(src, OUT / dst)
        command = [sys.executable, 'render.py', '-s', '/sfm_input/scene', '-m', '/output/model'] + policy['render_flags']
        result['command'] = command
        result['cwd'] = '/source'
        write(OUT / 'invocation.json', dict(result, finished_unix=None))
        result['render_attempts'] = 1
        native_started = time.monotonic()
        with (OUT / 'native.log').open('xb') as log:
            result['native_exit_code'] = subprocess.run(command, cwd=SOURCE, stdout=log, stderr=subprocess.STDOUT).returncode
        result['native_wall_seconds'] = time.monotonic() - native_started
        require(result['native_exit_code'] == 0, 'Official renderer failed; one attempt closed without retry')
        result['png_validation'] = validate_png(proof)
        require(source_map() == proof['source_sha256'], 'Source changed during preview')
        require([rec(p, label) for p, label in files] == proof['files'], 'Immutable provenance changed during preview')
        require(sha(OUT / 'model/cfg_args') == sha(PARENT / 'model/cfg_args'), 'Native cfg_args changed')
        result['status'], result['validated_exit_code'] = 'PASS', 0
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
        (OUT / 'failure.log').write_text(traceback.format_exc())
    finally:
        try:
            result['parent_observation_after'] = parent_state()
        except Exception as error:
            result['parent_observation_after'] = dict(status='UNKNOWN', error=str(error))
        result['finished_unix'] = time.time()
        result['wall_seconds'] = result['finished_unix'] - started
        result['peak_child_rss_bytes'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024
        result['outputs'] = [rec(p, str(p.relative_to(OUT))) for p in sorted(OUT.rglob('*'))
                             if p.is_file() and p.name not in ('wrapper_stdout.log', 'wrapper_stderr.log')
                             and 'resource_observations' not in p.parts]
        write(OUT / 'receipt.json', result)
    print(json.dumps(dict(status=result['status'], native_exit_code=result['native_exit_code'],
                          validated_exit_code=result['validated_exit_code'], error=result.get('error'))))
    return result['validated_exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
