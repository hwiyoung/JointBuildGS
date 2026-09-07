"""Freeze a resource-only retry before training; preserve its failed parent."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import time

FINAL_POLICY_SHA = 'edf3f4312c622059a3506c6ca1c07d2b1c90e234fb672cc592ea3ea7e28f5a9a'
SCIENCE_CONFIG_SHA = '42c741c8682a7830bd53cde3add9a93b41030f1dcb718b9e2f23d78389834c13'
PREDECESSORS = {'P1': 'no_anchor_sfm_memory_recovery_v2',
                'P2': 'no_anchor_sfm_memory_recovery_P2_v2',
                'P3': 'no_anchor_sfm_memory_recovery_P3_v3'}
RETRY_ATTEMPTS = {region: 'no_anchor_sfm_gradient_memory_v3_' + region for region in PREDECESSORS}
RESOURCE_FAILURE_MARKERS = ('torch.cuda.OutOfMemoryError', 'CUDA error: out of memory',
                            'PINNED_HOST_BUDGET_EXCEEDED', '_ArrayMemoryError', 'MemoryError:',
                            'std::bad_alloc', "DefaultCPUAllocator: can't allocate memory")
V3_VERIFIER_SHA = 'e2af28956361a4f645a29ff1d582826f465e2c6adf4486779a90d660391e6fd1'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def task_path(task, relative):
    value = Path(relative)
    if value.is_absolute() or '..' in value.parts:
        raise ValueError('Expected contained task-relative evidence')
    result = task / value
    if not result.resolve().is_relative_to(task.resolve()):
        raise ValueError('Task-relative evidence resolves outside task')
    return result


def source_map(source):
    return {str(path.relative_to(source)): sha(path) for path in sorted(source.rglob('*.py'))
            if '.git' not in path.parts and '__pycache__' not in path.parts}


def validate_runtime(source, runtime, validation):
    """Validation may be reused across directories only for identical code bytes."""
    if (runtime.get('status') != 'PASS_MEMORY_RECOVERY_RUNTIME_PREPARED'
            or runtime.get('science_config_unchanged') is not True
            or 'scientific_verdict' not in runtime or 'scientific_verdict' not in validation
            or runtime.get('scientific_verdict') is not None
            or validation.get('scientific_verdict') is not None):
        raise ValueError('Memory runtime preparation/validation identity incomplete')
    actual = source_map(source)
    if not actual or actual != runtime.get('destination_python_sha256'):
        raise ValueError('Prepared source membership or hash differs from runtime receipt')
    version = runtime.get('storage_version', 1)
    if version == 1:
        hashes = validation.get('source_sha256', {})
        if (validation.get('status') != 'PASS_CUDA_TOY_EQUIVALENCE'
                or validation.get('prepared_train_sha256') != actual.get('train.py')
                or not runtime.get('adapter_source_sha256') or not runtime.get('script_sha256')
                or hashes.get('memory_adapter.py') != runtime.get('adapter_source_sha256')
                or hashes.get('prepare_runtime.py') != runtime.get('script_sha256')):
            raise ValueError('Small CUDA equivalence fixture not bound to prepared source')
    elif version == 2 and runtime.get('resource_recovery_version') == 3:
        hashes = validation.get('validation_sources_sha256', {})
        added = runtime.get('added_module_source_sha256', {})
        expected = {'prepare_runtime.py': runtime.get('script_sha256'),
                    'runtime_adapter.py': runtime.get('adapter_source_sha256'),
                    'stream_ply.py': added.get('jbgs_stream_ply.py')}
        parent_path = source / 'jbgs_memory_recovery_v2_receipt.json'
        parent = json.loads(parent_path.read_text())
        parent_map = runtime.get('v2_destination_python_sha256')
        changed = sorted(key for key in set(actual) | set(parent_map or {})
                         if actual.get(key) != (parent_map or {}).get(key))
        if (validation.get('status') != 'PASS_CUDA_RUNTIME_FIXTURE'
                or validation.get('resource_recovery_version') != 3
                or validation.get('storage_version') != 2 or validation.get('device') != 'cuda:0'
                or validation.get('synthetic_optimizer_steps') != 8
                or not isinstance(validation.get('maximum_cuda_allocated_bytes'), int)
                or not 0 < validation['maximum_cuda_allocated_bytes'] <= (64 << 20)
                or validation.get('prepared_source_python_sha256') != actual
                or validation.get('early_gradient_release_verified') is not True
                or validation.get('ply_serialization_byte_equal') is not True
                or any(not value or hashes.get(key) != value for key, value in expected.items())
                or hashes.get('verify_runtime.py') != V3_VERIFIER_SHA
                or actual.get('jbgs_memory_recovery.py') != expected['runtime_adapter.py']
                or any(actual.get(key) != value for key, value in added.items())
                or sha(parent_path) != runtime.get('v2_runtime_receipt_sha256')
                or parent.get('status') != 'PASS_MEMORY_RECOVERY_RUNTIME_PREPARED'
                or parent.get('storage_version') != 2 or parent.get('resource_recovery_version') is not None
                or parent.get('destination_python_sha256') != parent_map
                or parent.get('original_source_python_sha256') != runtime.get('original_source_python_sha256')
                or changed != ['jbgs_memory_recovery.py', 'jbgs_memory_recovery_v2_base.py', 'jbgs_stream_ply.py']
                or actual.get('jbgs_memory_recovery_v2_base.py') != parent_map.get('jbgs_memory_recovery.py')
                or runtime.get('train_py_identical_to_memory_recovery_v2') is not True
                or runtime.get('early_parameter_gradient_release') is not True
                or runtime.get('stream_ply') is not True
                or runtime.get('checkpoint_resume_supported') is not False):
            raise ValueError('v3 source, native arithmetic preservation or CUDA/PLY proof mismatch')
    elif version == 2 and runtime.get('resource_recovery_version') is None:
        hashes = validation.get('validation_sources_sha256', {})
        added = runtime.get('added_module_source_sha256', {})
        expected = {'prepare_runtime.py': runtime.get('script_sha256'),
                    'runtime_adapter.py': runtime.get('adapter_source_sha256'),
                    'pinned_storage.py': added.get('jbgs_pinned_storage.py')}
        if (validation.get('status') != 'PASS_CUDA_RUNTIME_FIXTURE'
                or validation.get('prepared_source_python_sha256') != actual
                or any(not value or hashes.get(key) != value for key, value in expected.items())
                or actual.get('jbgs_memory_recovery.py') != expected['runtime_adapter.py']
                or actual.get('jbgs_pinned_storage.py') != expected['pinned_storage.py']
                or any(actual.get(key) != value for key, value in added.items())):
            raise ValueError('v2 CUDA runtime fixture/source proof mismatch')
        # prepared_amendment_sha256 is recorded, not equated: changing only the
        # preparation source/destination path can legitimately change that hash.
    else:
        raise ValueError('Unsupported memory storage version')
    return version, actual


def validate_final_policy(path, expected_sha, region, attempt, predecessor, config_sha):
    if expected_sha != FINAL_POLICY_SHA or sha(path) != FINAL_POLICY_SHA:
        raise ValueError('Final retry policy is not the frozen finite policy')
    policy = json.loads(path.read_text())
    if (policy.get('schema') != 'GEOGS_SFM_FINAL_RESOURCE_RETRY_POLICY_v1'
            or 'scientific_verdict' not in policy or policy['scientific_verdict'] is not None
            or config_sha != SCIENCE_CONFIG_SHA
            or policy.get('selected_predecessors') != PREDECESSORS
            or policy.get('retry_attempts') != RETRY_ATTEMPTS
            or attempt != RETRY_ATTEMPTS[region] or predecessor != PREDECESSORS[region]
            or policy.get('maximum_additional_fresh_training_attempts_per_region') != 1
            or policy.get('runtime_identity') != {'resource_recovery_version': 3, 'storage_version': 2}
            or policy.get('fresh_initialization_only') is not True
            or policy.get('checkpoint_resume_allowed') is not False
            or policy.get('science_parameters_changed') is not False
            or policy.get('capture_iterations') != [1, 8000, 15000, 22000, 30000]):
        raise ValueError('Final resource retry policy controls differ')
    return policy


def evidence_record(path, task):
    return dict(path=str(path.relative_to(task)), bytes=path.stat().st_size, sha256=sha(path))


def validate_predecessor(receipt, first, log, amendment, region, config_sha, predecessor, *, cgroup_oom=False):
    command = receipt.get('command', [])
    times = [receipt.get(key) for key in ('started_unix', 'finished_unix', 'wall_seconds')]
    if (any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
            for value in times) or times[1] <= times[0] or times[2] <= 0):
        raise ValueError('Predecessor has no valid closed training time scope')
    if (receipt.get('status') != 'FAIL' or receipt.get('native_exit_code') not in (1, -9)
            or receipt.get('validated_exit_code') != receipt.get('native_exit_code')
            or receipt.get('region') != region or receipt.get('phase') != 'train'
            or receipt.get('iteration') is not None
            or receipt.get('condition_id') != 'SFM_noanchor_D005_Pnative'
            or 'scientific_verdict' not in receipt or receipt['scientific_verdict'] is not None
            or receipt.get('config_sha256') != config_sha
            or receipt.get('attempt_id') != predecessor
            or amendment.get('attempt_id') != predecessor or amendment.get('region') != region
            or amendment.get('storage_version') != 2 or amendment.get('resource_recovery_version') is not None
            or amendment.get('original_config_sha256') != config_sha
            or amendment.get('scientific_verdict') is not None
            or amendment.get('status') != 'SEALED_BEFORE_RETRY'
            or first.get('status') != 'PASS_FIRST_STEP_DIRECT_REFINEMENT'
            or first.get('iteration') != 1 or first.get('anchor_iterations_executed') != 0
            or first.get('pretrained_optimizer_loaded') is not False
            or first.get('scientific_verdict') is not None
            or '--jbgs_resume_full' in command or '--start_checkpoint' in command
            or not (any(marker in log for marker in RESOURCE_FAILURE_MARKERS) or cgroup_oom)):
        raise ValueError('Selected predecessor is not a closed fresh training resource failure')


def validate_cgroup_failure(proof, texts, receipt, receipt_sha, region, predecessor):
    """Require observed kernel/cgroup and container identity; SIGKILL alone is insufficient."""
    container = proof.get('container_id', '')
    victim = proof.get('victim_pid')
    kernel, inspect = texts.get('kernel_journal', ''), texts.get('docker_inspect', '')
    inspect_command = texts.get('docker_inspect_command', inspect)
    if (proof.get('schema') != 'GEOGS_NATIVE_RESOURCE_FAILURE_v1'
            or 'scientific_verdict' not in proof or proof['scientific_verdict'] is not None
            or proof.get('region') != region or proof.get('condition_id') != 'SFM_noanchor_D005_Pnative'
            or proof.get('native_exit_code') != -9 or receipt.get('native_exit_code') != -9
            or proof.get('cause') != 'CGROUP_OOM_KILL' or proof.get('kernel_oom_confirmed') is not True
            or proof.get('producer_receipt_sha256') != receipt_sha
            or not isinstance(container, str) or len(container) != 64
            or any(char not in '0123456789abcdef' for char in container)
            or not isinstance(victim, int) or isinstance(victim, bool) or victim <= 0
            or proof.get('limit_bytes') != 32 << 30
            or proof.get('cgroup_path') != '/system.slice/docker-' + container + '.scope'
            or set(texts) not in ({'kernel_journal', 'docker_inspect'},
                                 {'kernel_journal', 'docker_inspect', 'docker_inspect_command'})
            or 'constraint=CONSTRAINT_MEMCG' not in kernel
            or proof['cgroup_path'] not in kernel
            or ('task=python,pid=' + str(victim) + ',') not in kernel
            or ('Memory cgroup out of memory: Killed process ' + str(victim) + ' (python)') not in kernel
            or 'memory: usage 33554432kB, limit 33554432kB' not in kernel
            or container not in inspect
            or ('jbgs-geogs-' + predecessor + '-' + region + '-train') not in inspect_command):
        raise ValueError('SIGKILL lacks bound kernel cgroup OOM and predecessor container proof')
    return True


def bundle_filename(key):
    if key == 'predecessor_native_log':
        return key + '.log'
    return key + ('.txt' if key.startswith('resource_evidence_') else '.json')


def final_retry_evidence(task, relative, policy_relative, policy_sha, region, attempt, config_sha,
                         resource_failure_relative=None):
    policy_path = task_path(task, policy_relative)
    validate_final_policy(policy_path, policy_sha, region, attempt, relative, config_sha)
    folder = task_path(task, relative)
    run = folder / 'runs' / region / 'SFM_noanchor_D005_Pnative'
    paths = {'policy': policy_path, 'predecessor_training_receipt': run / 'receipt.json',
             'predecessor_native_log': run / 'native.log',
             'predecessor_amendment': folder / 'amendment.json',
             'predecessor_first_step': run / 'model/jbgs_no_anchor/first_step.json'}
    receipt, amendment, first = [json.loads(paths[key].read_text()) for key in
                               ('predecessor_training_receipt', 'predecessor_amendment', 'predecessor_first_step')]
    cgroup_oom, resource_records = False, []
    if resource_failure_relative is not None:
        path = task_path(task, resource_failure_relative)
        proof = json.loads(path.read_text())
        texts = {}
        for row in proof.get('evidence', []):
            role = row.get('role')
            evidence = task_path(task, row['path'])
            if evidence.stat().st_size != row.get('bytes') or sha(evidence) != row.get('sha256'):
                raise ValueError('Cgroup evidence source changed')
            if role not in ('kernel_journal', 'docker_inspect', 'docker_inspect_command'):
                continue  # Retain other observations in the linked receipt; they do not prove OOM.
            if role in texts:
                raise ValueError('Duplicate cgroup cause evidence role')
            paths['resource_evidence_' + role] = evidence
            texts[role] = evidence.read_text()
            resource_records.append(dict(role=role, **evidence_record(evidence, task)))
        cgroup_oom = validate_cgroup_failure(proof, texts, receipt, sha(paths['predecessor_training_receipt']),
                                            region, relative)
        paths['predecessor_resource_failure'] = path
    validate_predecessor(receipt, first, paths['predecessor_native_log'].read_text(), amendment,
                         region, config_sha, relative, cgroup_oom=cgroup_oom)
    if (sha(folder / 'config.json') != config_sha
            or receipt.get('memory_recovery_amendment_sha256') != sha(paths['predecessor_amendment'])
            or receipt.get('memory_recovery_amendment_path') != relative + '/amendment.json'):
        raise ValueError('Predecessor amendment/configuration binding differs')
    result = {key: evidence_record(path, task) for key, path in paths.items()}
    for key in ('resource_evidence_kernel_journal', 'resource_evidence_docker_inspect', 'resource_evidence_docker_inspect_command'):
        result.pop(key, None)
    if resource_records:
        result['resource_failure_evidence'] = resource_records
    result.update(region=region, predecessor_attempt_id=relative, attempt_index=1, max_attempts=1,
                  resource_recovery_version=3, storage_version=2, fresh_only=True, resume=False,
                  automatic_further_retry=False, quality_assessed=False)
    return result, paths, amendment


def inherited_history(task, amendment, region, config_sha, selected, original_receipt, original_log):
    if (amendment.get('original_failed_run_receipt') != original_receipt
            or amendment.get('original_failed_log') != original_log):
        raise ValueError('Predecessor lost the original training failure lineage')
    relatives = []
    for item in amendment.get('prior_resource_attempts', []):
        rec = item['receipt']
        path = task_path(task, rec['path'])
        if sha(path) != rec['sha256'] or sha(task_path(task, item['stop_intent']['path'])) != item['stop_intent']['sha256']:
            raise ValueError('Inherited intentional-stop evidence changed')
        relatives.append(str(Path(rec['path']).parents[3]))
    history = prior_attempts(task, relatives, region, config_sha, selected)
    if history != amendment.get('prior_resource_attempts', []):
        raise ValueError('Inherited intentional-stop metadata differs')
    initial = amendment.get('prior_initialization_failure')
    if initial is not None:
        relative = str(Path(initial['receipt']['path']).parents[3])
        checked = prior_initialization_failure(task, relative, region, config_sha, selected)
        if checked != initial:
            raise ValueError('Inherited initialization failure evidence differs')
    return history, initial


def prior_attempts(task, relatives, region, config_sha, selected):
    result, seen = [], set()
    for relative in relatives:
        folder = task_path(task, relative)
        if folder.resolve() == selected.resolve() or folder.resolve() in seen:
            raise ValueError('Prior attempt must be distinct and not repeated')
        seen.add(folder.resolve())
        run = folder / 'runs' / region / 'SFM_noanchor_D005_Pnative'
        receipt_path, stop_path = run / 'receipt.json', run / 'stop_intent.json'
        receipt, stop = (json.loads(path.read_text()) for path in (receipt_path, stop_path))
        if (receipt.get('status') != 'FAIL' or receipt.get('native_exit_code') != -15
                or receipt.get('region') != region or receipt.get('phase') != 'train'
                or receipt.get('condition_id') != 'SFM_noanchor_D005_Pnative'
                or 'scientific_verdict' not in receipt or 'scientific_verdict' not in stop
                or receipt.get('scientific_verdict') is not None
                or receipt.get('config_sha256') != config_sha
                or sha(folder / 'config.json') != config_sha
                or stop.get('cause') != 'RESOURCE_TRANSFER_OPTIMIZATION'
                or stop.get('region') != region or stop.get('scientific_verdict') is not None):
            raise ValueError('Prior attempt is not a matching intentional resource stop')
        result.append(dict(receipt=dict(path=str(receipt_path.relative_to(task)), sha256=sha(receipt_path)),
                           stop_intent=dict(path=str(stop_path.relative_to(task)), sha256=sha(stop_path)),
                           classification='INTENTIONAL_RESOURCE_TRANSFER_REPLACEMENT',
                           counted_as_cuda_oom=False, quality_assessed=False))
    return result


def prior_initialization_failure(task, relative, region, config_sha, selected):
    if relative is None:
        return None
    folder = task_path(task, relative)
    if folder.resolve() == selected.resolve():
        raise ValueError('Prior initialization failure must be a distinct attempt')
    run = folder / 'runs' / region / 'SFM_noanchor_D005_Pnative'
    receipt_path, log_path = run / 'receipt.json', run / 'native.log'
    receipt = json.loads(receipt_path.read_text())
    first = run / 'model/jbgs_no_anchor/first_step.json'
    if (receipt.get('status') != 'FAIL' or receipt.get('native_exit_code') != 1
            or receipt.get('region') != region or receipt.get('phase') != 'train'
            or receipt.get('condition_id') != 'SFM_noanchor_D005_Pnative'
            or 'scientific_verdict' not in receipt or receipt.get('scientific_verdict') is not None
            or receipt.get('config_sha256') != config_sha or sha(folder / 'config.json') != config_sha
            or 'CUDA error: out of memory' not in log_path.read_text()
            or first.exists() or first.is_symlink()):
        raise ValueError('Prior attempt is not the recorded pre-first-step CUDA initialization failure')
    return dict(receipt=dict(path=str(receipt_path.relative_to(task)), sha256=sha(receipt_path)),
                log=dict(path=str(log_path.relative_to(task)), sha256=sha(log_path)),
                cause='RESOURCE_SCHEDULING_ERROR')


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--task', type=Path, required=True)
    p.add_argument('--experiment', type=Path, required=True)
    p.add_argument('--task-relative', required=True)
    p.add_argument('--region', choices=['P1', 'P2', 'P3'], required=True)
    p.add_argument('--validation-relative')
    p.add_argument('--prior-resource-attempt', action='append', default=[],
                   help='Task-relative root of an earlier intentionally stopped attempt')
    p.add_argument('--additional-capture-iteration', action='append', type=int, default=[],
                   choices=[8000, 15000], help='Additional complete-state capture; v2 only')
    p.add_argument('--prior-initialization-failure',
                   help='Task-relative root of the previous scheduling-caused CUDA initialization failure')
    p.add_argument('--predecessor-attempt', help='Fixed selected failed storage-v2 predecessor; resource v3 only')
    p.add_argument('--final-retry-policy', help='Frozen task-relative finite retry policy; resource v3 only')
    p.add_argument('--final-retry-policy-sha256')
    p.add_argument('--predecessor-resource-failure',
                   help='Optional task-relative kernel/Docker cgroup OOM proof for native SIGKILL')
    a = p.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    if Path(a.task_relative).name != a.task_relative:
        raise ValueError('Simple attempt directory required')
    parent = a.task / 'no_anchor_sfm_v1'
    failed = parent / 'runs' / a.region / 'SFM_noanchor_D005_Pnative'
    receipt = json.loads((failed / 'receipt.json').read_text())
    if receipt['status'] != 'FAIL' or receipt['region'] != a.region or 'torch.cuda.OutOfMemoryError' not in (failed / 'native.log').read_text():
        raise ValueError('Expected recorded native training CUDA OOM')
    config_sha = sha(parent / 'config.json')
    if sha(a.experiment / 'config.json') != config_sha:
        raise ValueError('Scientific configuration changed')
    runtime_path = a.experiment / 'source/jbgs_memory_recovery_receipt.json'
    runtime = json.loads(runtime_path.read_text())
    validation_relative = a.validation_relative or a.task_relative + '/validation/equivalence_v2/cuda.json'
    validation_path = task_path(a.task, validation_relative)
    validation = json.loads(validation_path.read_text())
    storage_version, prepared_source = validate_runtime(a.experiment / 'source', runtime, validation)
    captures = sorted(a.additional_capture_iteration)
    if len(captures) != len(set(captures)) or (captures and storage_version != 2):
        raise ValueError('Additional captures must be unique and use storage version2')
    history = prior_attempts(a.task, a.prior_resource_attempt, a.region, config_sha, a.experiment)
    initial_failure = prior_initialization_failure(
        a.task, a.prior_initialization_failure, a.region, config_sha, a.experiment)
    final_retry, final_paths = None, {}
    original_receipt = dict(path=str((failed / 'receipt.json').relative_to(a.task)), sha256=sha(failed / 'receipt.json'))
    original_log = dict(path=str((failed / 'native.log').relative_to(a.task)), sha256=sha(failed / 'native.log'))
    if runtime.get('resource_recovery_version') == 3:
        if (not all((a.predecessor_attempt, a.final_retry_policy, a.final_retry_policy_sha256))
                or a.prior_resource_attempt or a.prior_initialization_failure or captures != [8000, 15000]
                or (a.experiment / 'runs').exists()):
            raise ValueError('v3 needs one unstarted attempt, fixed policy/predecessor and inherited history')
        final_retry, final_paths, predecessor_amendment = final_retry_evidence(
            a.task, a.predecessor_attempt, a.final_retry_policy, a.final_retry_policy_sha256,
            a.region, a.task_relative, config_sha, a.predecessor_resource_failure)
        history, initial_failure = inherited_history(a.task, predecessor_amendment, a.region, config_sha,
                                                     a.experiment, original_receipt, original_log)
        final_paths['runtime_validation'] = validation_path
    elif any((a.predecessor_attempt, a.final_retry_policy, a.final_retry_policy_sha256, a.predecessor_resource_failure)):
        raise ValueError('Final resource retry fields cannot be used for an older runtime')
    old_input, new_input = parent / 'inputs' / a.region, a.experiment / 'inputs' / a.region
    input_files = {}
    old_names = {str(x.relative_to(old_input)) for x in old_input.rglob('*') if x.is_file() or x.is_symlink()}
    new_names = {str(x.relative_to(new_input)) for x in new_input.rglob('*') if x.is_file() or x.is_symlink()}
    if old_names != new_names:
        raise ValueError('Copied SfM input membership differs')
    for name in sorted(old_names):
        left, right = old_input / name, new_input / name
        if left.is_symlink():
            if not right.is_symlink() or left.readlink() != right.readlink():
                raise ValueError('Copied frozen-input link differs')
            input_files[name] = {'symlink_target': str(left.readlink())}
        else:
            digest = sha(left)
            if sha(right) != digest:
                raise ValueError('Copied SfM input bytes differ')
            input_files[name] = {'sha256': digest}
    result = dict(schema='GEOGS_SFM_NO_ANCHOR_RESOURCE_AMENDMENT_v1',
        status='SEALED_BEFORE_RETRY', scientific_verdict=None, region=a.region,
        attempt_id=a.task_relative, task_relative_path=a.task_relative + '/amendment.json',
        created_unix=time.time(), original_config_sha256=config_sha,
        arithmetic_or_scientific_controls_changed=False,
        original_failed_run_receipt=original_receipt,
        original_failed_log=original_log,
        memory_placement_changes=runtime['changes'], runtime_receipt_sha256=sha(runtime_path),
        runtime_receipt_path=a.task_relative + '/source/jbgs_memory_recovery_receipt.json',
        storage_version=storage_version, prepared_source_python_sha256=prepared_source,
        validation=dict(path=validation_relative, sha256=sha(validation_path),
                        reuse_of_identical_runtime_fixture=bool(a.validation_relative),
                        source_content_verified=True,
                        prepared_runtime_receipt_sha256=validation.get('prepared_amendment_sha256')),
        prior_resource_attempts=history, additional_capture_iterations=captures,
        additional_capture_scope=('Complete-state serialization only; no optimizer update, loss, '
                                  'densification or training length change. Its time/memory cost is measured.'
                                  if captures else None),
        copied_sfm_input_files=input_files, training_started=False, reference_used=False,
        limits=['Tiny CUDA equality does not establish whole-trajectory bitwise equality or completion.',
                'CPU/GPU transfer changes runtime cost; report recovery timing separately.'],
        script_sha256=sha(Path(__file__)))
    if initial_failure is not None:
        result['prior_initialization_failure'] = initial_failure
    if final_retry is not None:
        result.update(resource_recovery_version=3, final_resource_retry=final_retry)
        bundle = a.experiment / 'final_retry_evidence'
        bundle.mkdir(exist_ok=False)
        copied = {}
        for key, path in final_paths.items():
            filename = bundle_filename(key)
            target = bundle / filename
            shutil.copyfile(path, target)
            copied[key] = dict(filename=filename, bytes=target.stat().st_size, sha256=sha(target))
            if copied[key]['sha256'] != sha(path):
                raise ValueError('Final retry evidence changed while copying')
        result['final_retry_evidence_bundle'] = copied
    with (a.experiment / 'amendment.json').open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'region': a.region, 'attempt': a.task_relative}))


if __name__ == '__main__':
    main()
