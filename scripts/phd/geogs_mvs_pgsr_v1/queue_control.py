"""CPU-only sealing of completed preflights and exact background run membership."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def resolve_run_path(host_path, host_task, mounted_task):
    """Normalize host lexical paths and prevent symlink escape on the mount."""
    host_path = Path(os.path.normpath(host_path))
    host_task = Path(os.path.normpath(host_task))
    if not host_path.is_absolute() or not host_task.is_absolute():
        raise ValueError('Queue entries must use absolute host paths')
    relative = host_path.relative_to(host_task)
    mounted_task = Path(mounted_task).resolve(strict=True)
    root = (mounted_task / relative).resolve(strict=True)
    if not root.is_relative_to(mounted_task) or root == mounted_task:
        raise ValueError('Run path escapes the task payload')
    return root, relative


def verify_complete_payload(root, receipt, config):
    """A PASS label alone cannot seal missing or changed model payloads."""
    expected_iteration = (config['preflight']['stop_after'] if receipt['phase'] == 'preflight'
                          else config['final_iteration'])
    if receipt.get('final_iteration') != expected_iteration or receipt.get('scientific_verdict') is not None:
        raise ValueError('Run endpoint or scientific-verdict field differs')
    complete_relative = Path('model/jbgs_complete') / f'iteration_{expected_iteration}'
    complete = root / complete_relative
    metadata_path = complete / 'receipt.json'
    if sha(metadata_path) != receipt.get('complete_state_receipt_sha256'):
        raise ValueError('Complete-state producer receipt changed')
    metadata = json.loads(metadata_path.read_text())
    if (metadata != receipt.get('complete_state_receipt')
            or metadata.get('schema') != 'JBGS_GEOGS_COMPLETE_STATE_v1'
            or metadata.get('iteration') != expected_iteration
            or metadata.get('after_protection_registration') is not True
            or metadata.get('scientific_verdict') is not None):
        raise ValueError('Complete-state producer metadata differs')
    outputs = receipt.get('verified_outputs', [])
    by_path = {item['path']: item for item in outputs}
    expected_paths = {str(complete_relative / name) for name in ('checkpoint.pth', 'point_cloud.ply')}
    if len(outputs) != len(by_path) or set(by_path) != expected_paths:
        raise ValueError('Complete-state output membership differs')
    for name, key in (('checkpoint.pth', 'checkpoint_sha256'), ('point_cloud.ply', 'ply_sha256')):
        path = (complete / name).resolve(strict=True)
        if not path.is_relative_to(root.resolve(strict=True)):
            raise ValueError('Complete-state payload escapes its run')
        entry = by_path[str(complete_relative / name)]
        actual_sha, actual_size = sha(path), path.stat().st_size
        if (not actual_size or actual_sha != metadata[key] or actual_sha != entry['sha256']
                or actual_size != entry['bytes']):
            raise ValueError('Complete-state model payload changed: ' + name)


def validate_finalizer_ready(task, host_task, repo, host_repo):
    task, repo = Path(task), Path(repo)
    marker_path = task / 'finalization_ready_v1.json'
    marker = json.loads(marker_path.read_text())
    config_path = task / 'inputs_v2/experiment.json'
    config = json.loads(config_path.read_text())
    source_path = task / 'sources/GeoGS-mvs-pgsr-v1/mvs_pgsr_source_provenance.json'
    if (marker.get('schema') != 'JBGS_MVS_PGSR_FINALIZATION_READY_v1'
            or marker.get('status') != 'PASS' or marker.get('task_id') != config['task_id']
            or marker.get('scientific_verdict', 'missing') is not None
            or marker.get('config_sha256') != sha(config_path)
            or marker.get('source_provenance_sha256') != sha(source_path)):
        raise ValueError('Finalizer readiness marker differs from the frozen experiment')
    files = marker.get('files', {})
    if not {'finalize.py', 'finalize.sh', 'frozen_plan'} <= set(files):
        raise ValueError('Finalizer code and frozen plan must all be bound')
    verified = {}
    for name, entry in files.items():
        host_path = Path(os.path.normpath(entry['path']))
        if host_path.is_relative_to(Path(os.path.normpath(host_task))):
            path, _ = resolve_run_path(str(host_path), host_task, task)
        else:
            path, _ = resolve_run_path(str(host_path), host_repo, repo)
        if sha(path) != entry['sha256']:
            raise ValueError('Frozen finalizer input changed: ' + name)
        if name in ('finalize.py', 'finalize.sh') and path != (repo / 'scripts/phd/geogs_mvs_pgsr_v1' / name).resolve():
            raise ValueError('Unexpected finalizer script path: ' + name)
        verified[name] = {'path': str(host_path), 'sha256': sha(path)}
    plan_directory = str(Path(verified['frozen_plan']['path']).parent)
    if ('frozen_plan_directory' in marker
            and os.path.normpath(marker['frozen_plan_directory']) != plan_directory):
        raise ValueError('Frozen plan directory differs from its bound manifest')
    return {'task_id': config['task_id'], 'action': 'finalizer-ready', 'status': 'PASS',
            'marker_sha256': sha(marker_path), 'verified_files': verified,
            'frozen_plan_directory': plan_directory,
            'scientific_verdict': None}


def validate_finalization_completion(task, host_task):
    task = Path(task)
    receipt_path = task / 'evaluation/finalization_receipt_v1.json'
    receipt = json.loads(receipt_path.read_text())
    required_counts = {'new_training_runs': 12, 'historical_controls': 6,
                       'raw_and_post_surfaces_scored': 36}
    if (receipt.get('status') != 'PASS'
            or receipt.get('run_index_sha256') != sha(task / 'run_index_v1.json')
            or receipt.get('same_reference_ids_verified') is not True
            or receipt.get('scientific_verdict', 'missing') is not None
            or any(type(receipt.get(key)) is not int or receipt[key] != expected
                   for key, expected in required_counts.items())):
        raise ValueError('Finalization has not completed the exact required comparison')
    report = Path(receipt['report_path'])
    if not report.is_absolute():
        report = task / report
    elif report.is_relative_to(Path('/task')):
        report = task / report.relative_to('/task')
    else:
        report, _ = resolve_run_path(str(report), host_task, task)
    report = report.resolve(strict=True)
    if not report.is_relative_to(task.resolve(strict=True)) or not report.is_file() or report.stat().st_size == 0:
        raise ValueError('Completed nonempty report is missing from the task payload')
    return {'action': 'completion', 'status': 'PASS',
            'finalization_receipt_sha256': sha(receipt_path),
            'run_index_sha256': receipt['run_index_sha256'], 'report_sha256': sha(report),
            'report_path': str(report), **required_counts, 'scientific_verdict': None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--list', type=Path)
    parser.add_argument('--action', choices=('gate', 'index', 'finalizer-ready', 'completion'), required=True)
    parser.add_argument('--host-task', required=True)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--host-repo')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    if args.action in ('finalizer-ready', 'completion'):
        if args.action == 'finalizer-ready':
            if args.repo is None or args.host_repo is None:
                raise ValueError('Finalizer validation requires the mounted and host repo roots')
            result = validate_finalizer_ready(args.task, args.host_task, args.repo, args.host_repo)
        else:
            result = validate_finalization_completion(args.task, args.host_task)
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        if args.action == 'finalizer-ready':
            print(result['frozen_plan_directory'])
        print(json.dumps({'action': args.action, 'status': 'PASS'}))
        return
    if args.list is None:
        raise ValueError('Gate/index sealing requires an exact run list')
    cfg_path = args.task / 'inputs_v2/experiment.json'
    config = json.loads(cfg_path.read_text())
    source = args.task / 'sources/GeoGS-mvs-pgsr-v1/mvs_pgsr_source_provenance.json'
    bindings = {region: sha(args.task / 'inputs_v2' / region / 'bindings.json') for region in config['regions']}
    rows = []
    for line in args.list.read_text().splitlines():
        root, relative = resolve_run_path(line, args.host_task, args.task)
        receipt = json.loads((root / 'receipt.json').read_text())
        if (receipt['status'] != 'PASS' or not receipt['completed']
                or receipt['config_sha256'] != sha(cfg_path)
                or receipt['source_provenance_sha256'] != sha(source)
                or receipt['binding_sha256'] != bindings[receipt['region']]):
            raise ValueError('Run is not a completed matching source/config result: ' + line)
        if receipt['phase'] != ('preflight' if args.action == 'gate' else 'train'):
            raise ValueError('Wrong phase receipt')
        if relative.parts[:3] != (receipt['phase'], receipt['region'], f"{receipt['mode']}_{receipt['prior']:g}"):
            raise ValueError('Run directory disagrees with recorded condition')
        verify_complete_payload(root, receipt, config)
        rows.append({'region': receipt['region'], 'mode': receipt['mode'], 'prior': receipt['prior'],
                     'output_directory': os.path.normpath(line), 'receipt_sha256': sha(root / 'receipt.json')})
    priors = [0.005] if args.action == 'gate' else config['prior_weights']
    expected = {(region, mode, prior) for region in config['regions'] for mode in config['modes'] for prior in priors}
    actual = {(row['region'], row['mode'], row['prior']) for row in rows}
    if len(rows) != len(actual) or actual != expected:
        raise ValueError('Exact completed matrix membership differs')
    result = {'task_id': config['task_id'], 'action': args.action, 'status': 'PASS',
              'config_sha256': sha(cfg_path), 'source_provenance_sha256': sha(source),
              'inputs': bindings, 'runs': rows, 'scientific_verdict': None}
    if args.action == 'gate' and args.output.exists():
        # A detached supervisor may disappear after its Docker gate completes.
        # Reuse only after the complete payload audit above and exact equality;
        # an existing gate never bypasses validation or gets overwritten.
        if json.loads(args.output.read_text()) != result:
            raise ValueError('Existing execution gate differs from reverified inputs')
    else:
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2)
    print(json.dumps({'action': args.action, 'status': 'PASS', 'count': len(rows)}))


if __name__ == '__main__':
    main()
