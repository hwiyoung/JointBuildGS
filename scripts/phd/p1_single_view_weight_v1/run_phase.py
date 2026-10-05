"""Controlled single-view weight continuation in an isolated GPU container."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, '/parent_scripts')
from run_phase import validate_completion as parent_validate_completion


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def verify_inputs(cfg):
    if not Path('/.dockerenv').exists() or any(Path(p).exists() for p in (
            '/reference', '/base', '/artifacts/JointBuildGS')):
        raise RuntimeError('Narrow Docker input mounts required')
    for path, expected in (
        ('/experiment.json', cfg['parent_config_sha256']),
        ('/mvs/bindings.json', cfg['binding_sha256']),
        ('/anchor/checkpoint.pth', cfg['anchor_sha256']),
        ('/mask/r1_mask.npz', cfg['mask_sha256'])):
        if sha(path) != expected:
            raise ValueError('Frozen input changed: ' + path)
    if os.environ['JBGS_RUNTIME_IMAGE_ID'] != cfg['runtime_image_id']:
        raise ValueError('Runtime identity differs')
    if os.environ['PYTORCH_CUDA_ALLOC_CONF'] != cfg['allocator']:
        raise ValueError('Allocator differs')
    provenance = read('/source/p1_single_view_weight_source_provenance.json')
    for relative, expected in provenance['prepared_payload_hashes'].items():
        if sha(Path('/source') / relative) != expected:
            raise ValueError('Prepared source changed: ' + relative)
    original = read('/input/input_manifest.json')
    for row in original['files']:
        if sha(Path('/input') / row['path']) != row['sha256']:
            raise ValueError('Parent input changed: ' + row['path'])
    return original


def validate_intervention(output, cfg, alpha):
    model = Path(output) / 'model'
    traces = [json.loads(line) for line in (model / 'mvs_pgsr_trace.jsonl').read_text().splitlines()]
    if not all(row['mvs_weight'] == cfg['visual_weight'] for row in traces):
        raise ValueError('The global MVS coefficient must remain fixed')
    loaded = read(model / 'mvs_depth_loaded.json')
    if loaded['train_count'] != 98 or loaded['evaluation_depth_count'] != 0:
        raise ValueError('Depth membership differs')
    binding = read(model / 'p1_weight_binding.json')
    if (binding['alpha'] != alpha or binding['mask_sha256'] != cfg['mask_sha256']
            or binding['fixed_mvs_weight'] != cfg['visual_weight']
            or binding['dynamic_depth_weight'] is not False):
        raise ValueError('Realized region weight binding differs')
    algebra = read(model / 'p1_weight_first_target_algebra.json')
    if algebra['status'] != 'PASS' or not all(algebra['checks'].values()):
        raise ValueError('Actual target forward algebra did not pass')
    targets = [json.loads(line) for line in (model / 'p1_weight_target_trace.jsonl').read_text().splitlines()]
    if not targets or not all(row['alpha'] == alpha and row['r1']['count'] > 0 for row in targets):
        raise ValueError('Actual target-camera weighted supervision is missing')
    return dict(fixed_visual_weight=cfg['visual_weight'], alpha=alpha,
                loaded_depth_count=loaded['train_count'], target_visits=len(targets),
                first_target_algebra_status=algebra['status'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--alpha', type=int, choices=(0, 1, 4), required=True)
    parser.add_argument('--phase', choices=('preflight', 'train'), required=True)
    args = parser.parse_args()
    cfg = read('/task_config.json')
    original = verify_inputs(cfg)
    if str(args.alpha) != os.environ['JBGS_P1_WEIGHT_ALPHA']:
        raise ValueError('Actual alpha differs from invocation')
    if args.phase == 'train':
        gate = read('/gate.json')
        if (gate['status'] != 'PASS' or gate['config_sha256'] != sha('/task_config.json')
                or gate['source_provenance_sha256'] != sha('/source/p1_single_view_weight_source_provenance.json')):
            raise ValueError('A matching completed preflight gate is required')
    paths = original['training_paths']
    command = ['python', 'train.py', '-s', '/input/scene', '-m', '/output/model',
               '--lod_depth_path', str(Path('/input') / paths['prior_depth']),
               '--da_depth_path', str(Path('/input') / paths['da3_depth']),
               '--lod2_pcd_path', str(Path('/input') / paths['protection_pcd']),
               '--eval', '--lod_init', '--freeze_onlybldg', '--protect_bldg',
               '-r', '1', '--port', '0', '--iterations', str(cfg['final_iteration']),
               '--stage_switch_iter', str(cfg['anchor_iteration']), '--lambda_lod_init', '0.08',
               '--lambda_lod_anchor', str(cfg['prior_weight']),
               '--lambda_da_depth', str(cfg['visual_weight']),
               '--jbgs_resume_full', '/anchor/checkpoint.pth',
               '--jbgs_input_manifest', '/input/input_manifest.json']
    endpoint = cfg['preflight_stop'] if args.phase == 'preflight' else cfg['final_iteration']
    command += ['--jbgs_capture_iterations', str(endpoint)]
    if args.phase == 'preflight':
        command += ['--jbgs_stop_after', str(endpoint)]
    output = Path('/output')
    if (output / 'model').exists():
        raise FileExistsError('Never overwrite a model')
    invocation = dict(task_id=cfg['task_id'], phase=args.phase, alpha=args.alpha,
                      command=command, config_sha256=sha('/task_config.json'),
                      mask_sha256=cfg['mask_sha256'], driver_sha256=sha(__file__),
                      source_provenance_sha256=sha('/source/p1_single_view_weight_source_provenance.json'),
                      runtime_image_id=cfg['runtime_image_id'], scientific_verdict=None,
                      controller_override='Restore complete state; execute fixed MVS coefficient 0.05',
                      started_unix=time.time())
    write(output / 'invocation.json', invocation)
    started = time.monotonic()
    with (output / 'train.log').open('x') as log, (output / 'gpu.csv').open('x') as gpu:
        child = subprocess.Popen(command, cwd='/source', stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            subprocess.run(['nvidia-smi', '--query-gpu=timestamp,uuid,memory.used,utilization.gpu',
                            '--format=csv,noheader,nounits'], stdout=gpu, stderr=subprocess.DEVNULL)
            gpu.flush()
            time.sleep(5)
    result = dict(invocation, exit_code=child.returncode, status='FAIL', completed=False,
                  wall_seconds=time.monotonic() - started)
    try:
        if child.returncode:
            raise RuntimeError('Training process failed: ' + str(child.returncode))
        parent_cfg = read('/experiment.json')
        parent_cfg['preflight']['stop_after'] = cfg['preflight_stop']
        parent_args = argparse.Namespace(region='P1', mode='mvs', prior=cfg['prior_weight'], phase=args.phase)
        result.update(parent_validate_completion(output, parent_cfg, parent_args))
        result.update(validate_intervention(output, cfg, args.alpha), status='PASS', completed=True)
    except Exception as exc:
        result['validation_error'] = repr(exc)
    result['train_log_sha256'] = sha(output / 'train.log')
    write(output / 'receipt.json', result)
    print(json.dumps({key: result[key] for key in ('phase', 'alpha', 'status', 'wall_seconds')}), flush=True)
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
