"""Opt-in 8000→8100 allocator diagnostic; the pinned GeoGS source stays read-only.

No project modules or torch are imported before provenance checks. Hooks retain
no env/model/tensor references and never change a native return or exception.
The shell launcher invokes finalization only after native stdout/stderr close.
"""
import argparse
from datetime import datetime, timezone
import functools
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import runpy
import subprocess
import sys
import time


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def record(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def contained_file(root, relative):
    root, relative = Path(root).resolve(), Path(relative)
    require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe relative input path')
    path = root / relative
    require(path.is_file() and path.resolve().is_relative_to(root), 'Input escapes its mounted root')
    return path


def validate_inputs(cfg, failed_path, execution_path, input_root, anchor_root, source_root, environment):
    """Byte checks only. Never deserialize the checkpoint or inspect tensor data."""
    require(cfg['schema'] == 'GEOGS_REPEAT_MEMORY_DIAGNOSTIC_v1'
            and cfg['region'] == 'P2' and cfg['condition'] == 'D005_Pnative'
            and cfg['start_iteration'] == 8000 and cfg['stop_after_iteration'] == 8100
            and cfg['sample_every_completed_steps'] == 10 and cfg['implementation_file_count'] == 45
            and cfg['scientific_verdict'] is None and cfg['replaces_official_repeat'] is False
            and cfg['run_family'] == 'diagnostic_only', 'Diagnostic scope changed')
    require(sha(failed_path) == cfg['failed_invocation_sha256'], 'Failed invocation bytes changed')
    failed = read(failed_path)
    expected = dict(region='P2', condition='D005_Pnative', phase='train', training_start_iteration=8000,
                    repeat_id='native_repeat_1', scientific_verdict=None,
                    repeat_contract_sha256=cfg['native_repeat_contract_sha256'],
                    config_sha256=cfg['scientific_config_sha256'],
                    input_manifest_sha256=cfg['input_manifest_sha256'],
                    runtime_layout_sha256=cfg['runtime_layout_sha256'],
                    runtime_image_id=cfg['runtime_image_id'],
                    repeat_anchor_checkpoint_sha256=cfg['anchor_checkpoint_sha256'],
                    repeat_anchor_gate_sha256=cfg['anchor_gate_sha256'])
    require(all(failed.get(key) == value for key, value in expected.items()), 'Failed invocation identity differs')
    require(failed['environment'] == cfg['environment'], 'Pinned failed environment differs')
    require(all(environment.get(key) == value for key, value in cfg['environment'].items()),
            'Actual recorded environment differs')
    repeat_environment = dict(JBGS_REPEAT_ID='native_repeat_1',
                              JBGS_REPEAT_CONTRACT_SHA256=cfg['native_repeat_contract_sha256'])
    require(all(environment.get(key) == value for key, value in repeat_environment.items()),
            'Native repeat-binding environment differs')
    require(environment.get('JBGS_RUNTIME_IMAGE_ID') == cfg['runtime_image_id'], 'Image binding differs')
    require(all(not environment.get(key) for key in cfg['forbidden_environment']),
            'An undeclared CUDA debugging/cache override is present')
    require(sha(execution_path) == cfg['scientific_config_sha256'], 'Scientific config bytes changed')
    manifest_path = Path(input_root) / 'input_manifest.json'
    require(sha(manifest_path) == cfg['input_manifest_sha256'], 'Input manifest bytes changed')
    manifest = read(manifest_path)
    require(manifest['status'] == 'INPUTS_SEALED_FOR_EXECUTION' and manifest['region'] == 'P2'
            and manifest['config_sha256'] == cfg['scientific_config_sha256'], 'Input seal identity differs')
    files = manifest['files']
    require(files and len({row['path'] for row in files}) == len(files), 'Missing/duplicate input membership')
    checked_inputs = []
    for row in files:
        path = contained_file(input_root, row['path'])
        item = record(path)
        require(item['sha256'] == row['sha256'] and
                ('bytes' not in row or item['bytes'] == row['bytes']), 'Sealed input differs: ' + row['path'])
        checked_inputs.append(dict(relative_path=row['path'], bytes=item['bytes'], sha256=item['sha256']))
    checkpoint = Path(anchor_root) / 'checkpoint.pth'
    checkpoint_record = record(checkpoint)
    anchor_receipt = read(Path(anchor_root) / 'receipt.json')
    require(anchor_receipt['iteration'] == 8000 and anchor_receipt['after_protection_registration'] is True
            and anchor_receipt['scientific_verdict'] is None
            and anchor_receipt['checkpoint_sha256'] == cfg['anchor_checkpoint_sha256']
            and checkpoint_record['sha256'] == cfg['anchor_checkpoint_sha256'], 'Exact anchor bytes/identity differ')
    source_root = Path(source_root)
    declared = failed['implementation_hashes']
    require(len(declared) == cfg['implementation_file_count'], 'Expected exactly 45 implementation files')
    current = {str(path.relative_to(source_root)): sha(path) for path in sorted(source_root.rglob('*.py'))
               if 'submodules' not in path.parts and '__pycache__' not in path.parts}
    require(current == declared, 'Implementation membership or bytes differ')
    command = failed['command']
    require(isinstance(command, list) and all(isinstance(arg, str) for arg in command)
            and command[:2] == ['python', 'train.py'] and '--jbgs_stop_after' not in command,
            'Unexpected failed command')
    required_options = {'-m': '/output/model', '-s': '/input/scene', '--jbgs_resume_full': '/anchor/checkpoint.pth',
                        '--iterations': '30000', '--stage_switch_iter': '8000', '--lambda_lod_anchor': '0.005'}
    for key, value in required_options.items():
        require(command.count(key) == 1 and command[command.index(key) + 1] == value, 'Native option differs: ' + key)
    return dict(failed_invocation=record(failed_path), scientific_config=record(execution_path),
                input_manifest=record(manifest_path), verified_input_files=checked_inputs,
                anchor_checkpoint=checkpoint_record, anchor_receipt=record(Path(anchor_root) / 'receipt.json'),
                implementation_hashes=current, environment=dict(cfg['environment'], **repeat_environment),
                runtime_image_id=cfg['runtime_image_id'], native_command=command + ['--jbgs_stop_after', '8100'])


def allocator_json(value):
    """Accept only JSON primitives returned by allocator APIs, never tensor objects."""
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, (list, tuple)):
        return [allocator_json(item) for item in value]
    if isinstance(value, dict):
        require(all(type(key) is str for key in value), 'Allocator metadata has a non-string key')
        return {key: allocator_json(item) for key, item in value.items()}
    raise TypeError('Allocator metadata contains a non-JSON object: ' + type(value).__name__)


class MemoryRecorder:
    def __init__(self, output, cuda, every=10):
        self.output, self.cuda, self.every = Path(output), cuda, every
        self.started = time.monotonic()
        self.last_completed_iteration = None
        self.last_entered_after_step_iteration = None
        self.densify_call_count = 0
        self.samples = 0
        self.secondary_errors = []
        self.exception_metadata_attempted = False
        self.trace_path = self.output / 'diagnostic_memory.jsonl'
        self.trace_path.touch(exist_ok=False)

    def secondary(self, stage, error):
        self.secondary_errors.append(dict(stage=stage, error_type=type(error).__name__, message=str(error)[:4096]))

    def sample(self, event, **metadata):
        try:
            require(self.last_completed_iteration is not None, 'Allocator observation is disabled before native restore completes')
            free, total = self.cuda.mem_get_info()
            row = dict(event=event, observed_at_utc=utc(), elapsed_seconds=time.monotonic() - self.started,
                       last_completed_iteration=self.last_completed_iteration,
                       last_entered_after_step_iteration=self.last_entered_after_step_iteration,
                       densify_call_count=self.densify_call_count,
                       first_densify_call=self.densify_call_count == 1,
                       allocated_bytes=self.cuda.memory_allocated(), reserved_bytes=self.cuda.memory_reserved(),
                       peak_allocated_bytes=self.cuda.max_memory_allocated(),
                       peak_reserved_bytes=self.cuda.max_memory_reserved(),
                       device_free_bytes=free, device_total_bytes=total,
                       process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                       memory_stats=allocator_json(dict(self.cuda.memory_stats())),
                       scientific_verdict=None, **metadata)
            with self.trace_path.open('a') as stream:
                stream.write(json.dumps(row, allow_nan=False) + '\n')
            self.samples += 1
        except Exception as error:
            self.secondary('sample:' + event, error)

    def exception_metadata(self, stage, error):
        if self.last_completed_iteration is None:
            self.secondary('exception_metadata_skipped_before_restore',
                           RuntimeError('No logger CUDA API is called before native restore completes'))
            return
        self.sample(stage + '_exception', exception_type=type(error).__name__)
        if self.exception_metadata_attempted:
            return
        self.exception_metadata_attempted = True
        for kind, name in (('summary', 'memory_summary'), ('snapshot', 'memory_snapshot')):
            try:
                function = getattr(self.cuda, name)
                value = function()
                if kind == 'summary':
                    require(type(value) is str, 'Allocator summary is not text')
                    with (self.output / 'diagnostic_exception_memory_summary.txt').open('x') as stream:
                        stream.write(value)
                else:
                    dump(self.output / 'diagnostic_exception_memory_snapshot.json', allocator_json(value))
            except Exception as secondary:
                self.secondary('exception_' + kind, secondary)


def install_hooks(state_module, model_class, recorder):
    restore, after_step, densify = state_module.restore_state, state_module.after_step, model_class.densify_and_prune

    @functools.wraps(restore)
    def observed_restore(*args, **kwargs):
        result = restore(*args, **kwargs)
        recorder.last_completed_iteration = int(result['first_iter'])
        recorder.sample('restore_complete')
        return result

    @functools.wraps(after_step)
    def observed_after_step(env):
        # Keep no env/model/tensor reference beyond this call; original capture runs first.
        iteration = int(env['iteration'])
        recorder.last_entered_after_step_iteration = iteration
        result = after_step(env)
        recorder.last_completed_iteration = iteration
        if iteration % recorder.every == 0:
            recorder.sample('after_step_complete', completed_iteration=iteration)
        return result

    @functools.wraps(densify)
    def observed_densify(instance, *args, **kwargs):
        recorder.densify_call_count += 1
        recorder.sample('densify_before')
        try:
            result = densify(instance, *args, **kwargs)
        except BaseException as error:
            recorder.exception_metadata('densify', error)
            raise
        recorder.sample('densify_after')
        return result

    state_module.restore_state, state_module.after_step = observed_restore, observed_after_step
    model_class.densify_and_prune = observed_densify

    def uninstall():
        state_module.restore_state, state_module.after_step = restore, after_step
        model_class.densify_and_prune = densify
    return uninstall


def preflight(config_path, output):
    """CPU byte verification plus the original allocator audit in a terminated child."""
    started, started_utc = time.monotonic(), utc()
    cfg, provenance, error_record, code = read(config_path), None, None, 1
    try:
        require(Path('/.dockerenv').exists() and Path.cwd() == Path('/source'), 'Run in scoped Docker CWD')
        require(not Path('/reference').exists() and not Path('/artifacts/JointBuildGS').exists(), 'Broad/reference mount prohibited')
        require(not (output / 'model').exists(), 'Diagnostic model output already exists')
        provenance = validate_inputs(cfg, '/failed_invocation.json', '/execution_config.json', '/input', '/anchor', '/source', os.environ)
        provenance.update(diagnostic_code=record(__file__), diagnostic_config=record(config_path),
                          launcher_source=record('/diagnostic/run_repeat_memory_diagnostic.sh'),
                          docker_command=record('/diagnostic/docker_command.sh'))
        gpu_uuid = subprocess.check_output(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'], text=True).strip().splitlines()
        require(gpu_uuid == [cfg['gpu_uuid']], 'Expose only the pinned GPU1 UUID')
        provenance['visible_gpu_uuids'] = gpu_uuid
        allocator_command = ['python', '-c',
            'import json,torch; torch.cuda.init(); print(json.dumps([torch.cuda.get_allocator_backend(),torch.cuda.memory_stats()["max_split_size"]]))']
        effective = json.loads(subprocess.check_output(allocator_command, text=True))
        require(effective == ['native', 128 * 1024 * 1024], 'Effective allocator differs from native/max_split128')
        provenance['effective_allocator_child'] = dict(command=allocator_command, result=effective,
                                                       completed_before_native_process=True)
        dump(output / 'diagnostic_invocation.json', dict(schema=cfg['schema'], scientific_verdict=None,
             diagnostic_only=True, replaces_official_repeat=False, provenance=provenance,
             native_process_policy='Fresh Python process after this preflight and allocator child exit; first logger CUDA API call follows native restore.',
             interpretation=cfg['interpretation']))
        code = 0
    except BaseException as error:
        error_record = dict(type=type(error).__name__, message=str(error)[:8192])
        raise
    finally:
        dump(output / 'diagnostic_preflight_receipt.json', dict(schema=cfg['schema'],
             status='DIAGNOSTIC_PREFLIGHT_VERIFIED' if code == 0 else 'DIAGNOSTIC_PRECHECK_FAILURE',
             scientific_verdict=None, started_at_utc=started_utc, completed_at_utc=utc(),
             preflight_wall_seconds=time.monotonic() - started, exit_code=code,
             native_process_started=False, error=error_record, provenance=provenance))


def run(config_path, output):
    started, started_utc = time.monotonic(), utc()
    cfg, provenance, recorder = read(config_path), None, None
    native_started, native_finished, exception, code = None, None, None, 1
    uninstall = None
    old_argv = sys.argv
    try:
        require(Path('/.dockerenv').exists() and Path.cwd() == Path('/source'), 'Run in the scoped source Docker CWD')
        require(not Path('/reference').exists() and not Path('/artifacts/JointBuildGS').exists(), 'Broad/reference mount prohibited')
        require(not (output / 'model').exists(), 'Diagnostic model output already exists')
        preflight_receipt = read(output / 'diagnostic_preflight_receipt.json')
        require(preflight_receipt['status'] == 'DIAGNOSTIC_PREFLIGHT_VERIFIED', 'A completed preflight is required')
        provenance = read(output / 'diagnostic_invocation.json')['provenance']
        require(provenance == preflight_receipt['provenance'], 'Preflight/invocation binding differs')
        require(record(__file__) == provenance['diagnostic_code']
                and record(config_path) == provenance['diagnostic_config'], 'Diagnostic source/config changed after preflight')
        require(all(os.environ.get(key) == value for key, value in provenance['environment'].items()),
                'Native process environment differs from the preflight')
        sys.path.insert(0, '/source')
        torch = importlib.import_module('torch')
        # Merely retain the module reference. No logger CUDA API/context query precedes restore.
        recorder = MemoryRecorder(output, torch.cuda, cfg['sample_every_completed_steps'])
        state_module = importlib.import_module('jbgs_state')
        model_class = importlib.import_module('scene.gaussian_model').GaussianModel
        uninstall = install_hooks(state_module, model_class, recorder)
        sys.argv = provenance['native_command'][1:]
        native_started = utc()
        runpy.run_path('/source/train.py', run_name='__main__')
        code = 0
    except BaseException as error:
        code = int(error.code or 0) if isinstance(error, SystemExit) and isinstance(error.code, (int, type(None))) else 1
        exception = dict(type=type(error).__name__, message=str(error)[:8192])
        if recorder is not None and code != 0:
            recorder.exception_metadata('native_run', error)
        raise
    finally:
        native_finished = utc() if native_started is not None else None
        sys.argv = old_argv
        if uninstall is not None:
            uninstall()
        status = ('DIAGNOSTIC_RUN_COMPLETED' if code == 0 else
                  ('DIAGNOSTIC_NATIVE_FAILURE' if native_started else 'DIAGNOSTIC_PRECHECK_FAILURE'))
        # Filesystem/metadata failures must not replace a pending native exception.
        try:
            receipt = dict(schema=cfg['schema'], status=status, scientific_verdict=None,
                       diagnostic_only=True, replaces_official_repeat=False, interpretation=cfg['interpretation'],
                       started_at_utc=started_utc, completed_at_utc=utc(),
                       diagnostic_driver_wall_seconds=time.monotonic() - started,
                       native_run_started_at_utc=native_started, native_run_finished_at_utc=native_finished,
                       native_exit_code=code, native_exception=exception, provenance=provenance,
                       diagnostic_code=record(__file__), diagnostic_config=record(config_path),
                       last_completed_iteration=recorder.last_completed_iteration if recorder else None,
                       last_entered_after_step_iteration=recorder.last_entered_after_step_iteration if recorder else None,
                       densify_call_count=recorder.densify_call_count if recorder else 0,
                       memory_samples=recorder.samples if recorder else 0,
                       secondary_errors=recorder.secondary_errors if recorder else [],
                       measurement_scope='Training-process allocator counters and device-wide free/total at observation; process peak RSS; no tensor values. Peak counters are not reset. Timing includes diagnostic overhead.',
                           closed_inventory_pending=True)
            # Native stdout/stderr remain open here. A later process hashes closed files.
            dump(output / 'diagnostic_run_receipt.json', receipt)
        except Exception as secondary:
            print('Diagnostic receipt write failed: ' + type(secondary).__name__ + ': ' + str(secondary), file=sys.stderr)


def finalize(config_path, output, native_exit, preflight_exit=0):
    cfg = read(config_path)
    if preflight_exit == 0:
        require(native_exit is not None, 'A successful preflight must be followed by a closed native process')
        run_receipt = read(output / 'diagnostic_run_receipt.json')
        require(run_receipt['native_exit_code'] == native_exit, 'Native exit differs from closed run receipt')
    else:
        require(native_exit is None, 'Native process must not start after failed preflight')
        preflight_receipt = read(output / 'diagnostic_preflight_receipt.json')
        require(preflight_receipt['exit_code'] == preflight_exit, 'Preflight exit differs from its receipt')
        run_receipt = dict(last_completed_iteration=None, last_entered_after_step_iteration=None,
                           densify_call_count=0, memory_samples=0, secondary_errors=[],
                           provenance=preflight_receipt['provenance'])
    excluded = {'diagnostic_finalize_stdout.log', 'diagnostic_finalize_stderr.log',
                'diagnostic_finalize_exit_code.txt', 'diagnostic_receipt.json', 'diagnostic_closed_files_inventory.json'}
    # Only diagnostic files are read. Native model/checkpoint/PLY payloads are not inventoried.
    paths = [path for path in sorted(output.iterdir()) if path.is_file() and path.name.startswith('diagnostic_') and path.name not in excluded]
    inventory = dict(schema='GEOGS_DIAGNOSTIC_CLOSED_FILES_v1', scientific_verdict=None,
                     created_at_utc=utc(), files=[record(path) for path in paths],
                     exclusions=sorted(excluded), native_model_payloads_hashed=False)
    dump(output / 'diagnostic_closed_files_inventory.json', inventory)
    require(all(record(item['path']) == item for item in inventory['files']), 'Closed diagnostic evidence changed')
    complete = native_exit == 0 and run_receipt['last_completed_iteration'] == 8100
    measurements_complete = (complete and not run_receipt['secondary_errors']
                             and run_receipt['memory_samples'] >= 13 and run_receipt['densify_call_count'] >= 1)
    status = ('DIAGNOSTIC_OBSERVATION_COMPLETED' if measurements_complete else
              ('DIAGNOSTIC_OBSERVATION_PARTIAL' if complete else 'DIAGNOSTIC_FAILURE_PRESERVED'))
    result = dict(schema=cfg['schema'], status=status,
                  scientific_verdict=None, diagnostic_only=True, replaces_official_repeat=False,
                  interpretation=cfg['interpretation'], completed_at_utc=utc(), native_exit_code=native_exit,
                  last_completed_iteration=run_receipt['last_completed_iteration'],
                  last_entered_after_step_iteration=run_receipt['last_entered_after_step_iteration'],
                  densify_call_count=run_receipt['densify_call_count'], memory_samples=run_receipt['memory_samples'],
                  secondary_errors=run_receipt['secondary_errors'], provenance=run_receipt['provenance'],
                  measurements_complete=measurements_complete,
                  preflight_exit_code=preflight_exit,
                  run_receipt=record(output / 'diagnostic_run_receipt.json') if preflight_exit == 0 else None,
                  closed_inventory=record(output / 'diagnostic_closed_files_inventory.json'),
                  closed_file_hashes_verified=len(inventory['files']),
                  intentionally_unhashed_open_streams=['diagnostic_finalize_stdout.log', 'diagnostic_finalize_stderr.log'],
                  finalizer_code=record(__file__), configuration=record(config_path))
    dump(output / 'diagnostic_receipt.json', result)
    print(json.dumps({key: result[key] for key in ('status', 'native_exit_code', 'last_completed_iteration', 'closed_file_hashes_verified', 'scientific_verdict')}))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('preflight', 'run', 'finalize'), required=True)
    parser.add_argument('--config', type=Path, default=Path('/diagnostic/config.json'))
    parser.add_argument('--output', type=Path, default=Path('/output'))
    parser.add_argument('--native-exit', type=int)
    parser.add_argument('--preflight-exit', type=int, default=0)
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker execution is required')
    if args.mode == 'preflight':
        preflight(args.config, args.output)
        return 0
    if args.mode == 'run':
        run(args.config, args.output)
        return 0
    return finalize(args.config, args.output, args.native_exit, args.preflight_exit)


if __name__ == '__main__':
    raise SystemExit(main())
