"""Execute a bound GeoGS continuation inside one isolated Docker container."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)


def validate_runtime_controls(cfg, args, environment):
    if (environment.get('JBGS_MVS_PGSR_MODE') != args.mode
            or environment.get('JBGS_MVS_REGION') != args.region):
        raise ValueError('Driver region/mode differs from actual integration environment')
    if (args.mode not in cfg['modes'] or args.region not in cfg['regions']
            or args.prior not in cfg['prior_weights'] or cfg['protection'] != 'native'):
        raise ValueError('Invocation differs from frozen experiment controls')
    if environment.get('JBGS_RUNTIME_IMAGE_ID') != cfg['runtime_image_id']:
        raise ValueError('Runtime image differs from frozen configuration')
    if environment.get('PYTORCH_CUDA_ALLOC_CONF') != cfg['allocator']:
        raise ValueError('CUDA allocator differs from frozen configuration')


def validate_completion(output, cfg, args):
    """Require restored identity, realized controls and hash-verified full state."""
    output = Path(output)
    model = output / 'model'
    restore = json.loads((model / 'jbgs_restore.json').read_text())
    if (restore.get('schema') != 'JBGS_GEOGS_COMPLETE_STATE_v1'
            or restore.get('checkpoint_sha256') != cfg['anchors'][args.region]['sha256']
            or restore.get('iteration') != cfg['anchor_iteration']
            or restore.get('release') is not False
            or restore.get('lambda_lod_anchor') != args.prior
            or restore.get('scientific_verdict') is not None):
        raise ValueError('Actual restored checkpoint identity or native controls differ')
    equality = restore.get('restore_equivalence', {})
    if (equality.get('status') != 'PASS'
            or equality.get('scope') != 'immediate_complete_anchor_restore'
            or equality.get('protection') != 'native_exact'
            or equality.get('scientific_verdict') is not None
            or not all(equality.get(key) is True for key in (
                'model_optimizer_exact', 'controller_exact', 'camera_order_and_stack_exact', 'rng_exact'))):
        raise ValueError('Immediate complete Anchor8k restoration was not verified')
    traces = [json.loads(line) for line in (model / 'mvs_pgsr_trace.jsonl').read_text().splitlines()]
    expected = cfg['preflight']['stop_after'] if args.phase == 'preflight' else cfg['final_iteration']
    iterations = [row['iteration'] for row in traces]
    if (not traces or iterations[0] != cfg['anchor_iteration'] + 1 or iterations[-1] != expected
            or any(right <= left for left, right in zip(iterations, iterations[1:]))):
        raise ValueError('Requested continuation trace interval not observed')
    for row in traces:
        if (row.get('mode') != args.mode or row.get('visual_source') != cfg.get('visual_source', 'COLMAP_MVS_CAMERA_Z')
                or row.get('prior_weight') != args.prior or row.get('scientific_verdict') is not None):
            raise ValueError('Realized trace mode, supervision source or prior differs')
        if not all(isinstance(row.get(key), (int, float)) and math.isfinite(row[key])
                   for key in ('prior_loss', 'mvs_loss', 'prior_weight', 'mvs_weight',
                               'geometry_weighted_total', 'rgb_loss')):
            raise ValueError('Realized losses or weights are nonfinite or missing')
    if args.mode == 'mvs_pgsr' and not any(row.get('counts', {}).get('ncc_valid', 0) > 0
                                         and row.get('counts', {}).get('mv_valid', 0) > 0 for row in traces):
        raise ValueError('Multi-view geometry did not have actual usable support')
    complete = model / 'jbgs_complete' / f'iteration_{expected}'
    complete_receipt = json.loads((complete / 'receipt.json').read_text())
    if (complete_receipt.get('schema') != 'JBGS_GEOGS_COMPLETE_STATE_v1'
            or complete_receipt.get('iteration') != expected
            or complete_receipt.get('after_protection_registration') is not True
            or complete_receipt.get('scientific_verdict') is not None):
        raise ValueError('Final complete-state producer receipt differs')
    verified_outputs = []
    for name, key in (('checkpoint.pth', 'checkpoint_sha256'), ('point_cloud.ply', 'ply_sha256')):
        path = complete / name
        actual = sha(path)
        if not path.stat().st_size or complete_receipt.get(key) != actual:
            raise ValueError('Final complete-state payload changed: ' + name)
        verified_outputs.append({'path': str(path.relative_to(output)),
                                 'sha256': actual, 'bytes': path.stat().st_size})
    return dict(final_iteration=expected, restore=restore, first_trace=traces[0],
                final_trace=traces[-1], complete_state_receipt=complete_receipt,
                complete_state_receipt_sha256=sha(complete / 'receipt.json'),
                verified_outputs=verified_outputs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', choices=('P1', 'P2', 'P3'), required=True)
    parser.add_argument('--mode', choices=('mvs', 'mvs_pgsr'), required=True)
    parser.add_argument('--prior', type=float, choices=(.005, .0005), required=True)
    parser.add_argument('--phase', choices=('preflight', 'train'), required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    if Path('/artifacts/JointBuildGS').exists() or Path('/reference').exists():
        raise RuntimeError('Training container must not expose the broad artifact root or references')
    cfg = json.loads(Path('/experiment.json').read_text())
    validate_runtime_controls(cfg, args, os.environ)
    config_sha = sha('/experiment.json')
    if config_sha != os.environ['JBGS_MVS_CONFIG_SHA256']:
        raise ValueError('Config changed')
    binding_sha = sha('/mvs/bindings.json')
    if binding_sha != os.environ['JBGS_MVS_BINDING_SHA256']:
        raise ValueError('MVS binding changed')
    source_provenance = json.loads(Path('/source/mvs_pgsr_source_provenance.json').read_text())
    for relative, expected in source_provenance['prepared_implementation_hashes'].items():
        if sha(Path('/source') / relative) != expected:
            raise ValueError('Prepared source changed: ' + relative)
    original = json.loads(Path('/input/input_manifest.json').read_text())
    for row in original['files']:
        if sha(Path('/input') / row['path']) != row['sha256']:
            raise ValueError('Original scene file changed: ' + row['path'])
    if sha('/anchor/checkpoint.pth') != cfg['anchors'][args.region]['sha256']:
        raise ValueError('Exact Anchor8k changed')
    if args.phase == 'train':
        gate = json.loads(Path('/execution_gate.json').read_text())
        if (gate.get('status') != 'PASS' or gate['config_sha256'] != config_sha
                or gate['source_provenance_sha256'] != sha('/source/mvs_pgsr_source_provenance.json')
                or gate['inputs'][args.region] != binding_sha):
            raise ValueError('Main training requires matching completed technical gate')
    paths = original['training_paths']
    command = ['python', 'train.py', '-s', '/input/scene', '-m', '/output/model',
               '--lod_depth_path', str(Path('/input') / paths['prior_depth']),
               '--da_depth_path', str(Path('/input') / paths['da3_depth']),
               '--lod2_pcd_path', str(Path('/input') / paths['protection_pcd']),
               '--eval', '--lod_init', '--freeze_onlybldg', '--protect_bldg',
               '--dynamic_depth_weight', '-r', '1', '--port', '0',
               '--iterations', '30000', '--stage_switch_iter', '8000',
               '--lambda_lod_init', '0.08', '--lambda_lod_anchor', str(args.prior),
               '--jbgs_resume_full', '/anchor/checkpoint.pth',
               '--jbgs_input_manifest', '/input/input_manifest.json']
    if args.phase == 'preflight':
        command += ['--jbgs_stop_after', str(cfg['preflight']['stop_after']),
                    '--jbgs_capture_iterations', str(cfg['preflight']['stop_after'])]
    else:
        command += ['--jbgs_capture_iterations', '30000']
    output = Path('/output')
    if (output / 'model').exists():
        raise FileExistsError('Never overwrite an existing model')
    invocation = {'task_id': cfg['task_id'], 'region': args.region, 'mode': args.mode,
                  'prior': args.prior, 'phase': args.phase, 'command': command,
                  'config_sha256': config_sha, 'binding_sha256': binding_sha,
                  'source_provenance_sha256': sha('/source/mvs_pgsr_source_provenance.json'),
                  'driver_sha256': sha(__file__), 'runtime_image_id': os.environ['JBGS_RUNTIME_IMAGE_ID'],
                  'scientific_verdict': None, 'started_unix': time.time()}
    write(output / 'invocation.json', invocation)
    (output / 'driver_snapshot.py').write_bytes(Path(__file__).read_bytes())
    (output / 'experiment_snapshot.json').write_bytes(Path('/experiment.json').read_bytes())
    start = time.monotonic()
    with (output / 'train.log').open('x') as log, (output / 'gpu.csv').open('x') as gpu:
        child = subprocess.Popen(command, cwd='/source', stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            subprocess.run(['nvidia-smi', '--query-gpu=timestamp,uuid,memory.used,utilization.gpu',
                            '--format=csv,noheader,nounits'], stdout=gpu, stderr=subprocess.DEVNULL)
            time.sleep(5)
    result = {**invocation, 'exit_code': child.returncode,
              'wall_seconds': time.monotonic() - start, 'status': 'FAIL', 'completed': False}
    if child.returncode == 0:
        try:
            result.update(validate_completion(output, cfg, args), status='PASS', completed=True)
        except Exception as exc:
            result['validation_error'] = str(exc)
    result['train_log_sha256'] = sha(output / 'train.log')
    write(output / 'receipt.json', result)
    print(json.dumps({key: result[key] for key in ('region', 'mode', 'prior', 'phase', 'status', 'wall_seconds')}), flush=True)
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
