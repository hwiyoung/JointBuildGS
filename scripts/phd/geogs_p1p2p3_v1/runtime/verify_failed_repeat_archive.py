"""Docker CPU-only exact failed-repeat preservation; never deserialize model payloads.

The CLI checks immutable operational pins before calling the separately testable
byte/metadata functions. It can neither rename a directory nor launch training.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
TASK = '/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1'
PINS = {
    'P1': ('9f4438bbd0e91c3286b4f9cc7af2add51cc5b2a84972c5340db89a4c69d7a1e1',
           'aaf4905e4688ef4a04dfb8b2b3e53d8415d310d758190f40f95f82dbb4a83931',
           '3257b3604f630a64948606605c3ae46f2e22d4d5829b5ad49a7d46b342a42112',
           'c08a39aa2deb81b26dd4dd75d0be9e6bb5e150db503f9d422a05423388679274',
           '4af6cd7db3456fe155080dfa20b70d9f906b45103adaf7468d128ef0686a657a'),
    'P2': ('0383f1b4abc82cf2cf46381f8e03b43d3f359735c7b96f92bf1d740ad3306d31',
           '750050331dba791496fd818a1ce211afb408b3e61405953aeb67898aeae933da',
           '6493c602332144510526a54f31700c28cb31eb648250e690d6528fcffe5162a2',
           '91bc9ad74b115c37d4ae35ec4eb197832e730be165d36f52ebe4bb291f1ebcfd',
           '0f2559c2637cd394cba36dd08dbf1bf7ba29a948acbf1a82c868b1917feecc0a')}
PIN_KEYS = ('failed_receipt_sha256', 'failed_invocation_sha256', 'input_manifest_sha256',
            'anchor_checkpoint_sha256', 'anchor_gate_sha256')
ENVIRONMENT = dict(LD_PRELOAD='/opt/geogs/lib/libstdc++.so.6',
    LD_LIBRARY_PATH='/opt/geogs/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64',
    TORCH_HOME='/weights/torch', OMP_NUM_THREADS='8',
    PYTORCH_CUDA_ALLOC_CONF='backend:native,max_split_size_mb:128', JBGS_RUNTIME_REVISION='allocator_v2')


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def record(path):
    path = Path(path)
    return dict(path=path.name, bytes=path.stat().st_size, sha256=sha(path))


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def validate_config(cfg):
    expected = dict(schema='GEOGS_NATIVE_REPEAT_OPERATIONAL_RETRY_v1', task_id='PHD-GEOGS-P1P2P3-v1',
        task_root=TASK, scientific_verdict=None, repeat_id='native_repeat_1', condition='D005_Pnative',
        maximum_additional_attempts_per_region=1, runtime_image_id=IMAGE,
        scientific_config_sha256='b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4',
        runtime_layout_sha256='28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5',
        repeat_contract_sha256='3c62494f13de96dba33b1c36cbadf58e555305fee01ce641dd41f560bdfacafc',
        scientific_controls_changed=False, source_bytes_changed=False, input_bytes_changed=False,
        seed=0, allocator=ENVIRONMENT['PYTORCH_CUDA_ALLOC_CONF'], environment=ENVIRONMENT)
    require(all(cfg.get(key) == value for key, value in expected.items()), 'Operational/scientific contract changed')
    require(set(cfg['targets']) == set(PINS), 'Only original P1/P2 failures are authorized')
    for region, values in PINS.items():
        target = cfg['targets'][region]
        require(tuple(target.get(key) for key in PIN_KEYS) == values, 'Original failure/anchor/input pins changed')
        require(target['relative_directory'] == f'native_repeat_allocator_v2/{region}/D005_Pnative'
                and target['gpu_lock_index'] == {'P1': 0, 'P2': 1}[region], 'Exact target/GPU lock changed')


def mapping(cfg, region, source_host, archive_host):
    require(region in cfg['targets'], 'Region outside exact archive scope')
    source, archive = Path(source_host), Path(archive_host)
    require(source.is_absolute() and archive.is_absolute() and '..' not in source.parts + archive.parts,
            'Host paths must be absolute and normalized')
    require(str(source) == cfg['task_root'] + '/' + cfg['targets'][region]['relative_directory'], 'Source target changed')
    prefix = Path(cfg['task_root']) / 'runtime/native_repeat_retry_v1' / region
    require(archive.is_relative_to(prefix), 'Archive escapes operational region')
    parts = archive.relative_to(prefix).parts
    require(len(parts) == 2 and re.fullmatch(r'attempt\.[A-Za-z0-9]{6}', parts[0])
            and parts[1] == 'preserved_failed_run', 'Archive must be a fresh exact attempt destination')
    return dict(region=region, source_host_path=str(source), archive_host_path=str(archive),
                source_relative_directory=cfg['targets'][region]['relative_directory'],
                original_relative_paths_unchanged=True,
                resolution_rule='A former source-relative path resolves under archive_host_path with the identical suffix')


def tree_manifest(root):
    """All file bytes and directory membership; no checkpoint/PLY/trace parsing."""
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'Failed/archive root must be a real directory')
    device = root.stat().st_dev
    files, directories, empty = [], [], []
    forbidden = {'render_receipt.json', 'metrics_receipt.json', 'auxiliary_receipt.json',
                 'complete.json', 'completion.json', 'job_complete.json', 'results.json', 'per_view.json'}
    for parent, names, filenames in os.walk(root, followlinks=False):
        names.sort()
        filenames.sort()
        parent = Path(parent)
        relative = parent.relative_to(root).as_posix()
        directories.append(dict(path=relative, mode=stat.S_IMODE(parent.lstat().st_mode)))
        if not names and not filenames:
            empty.append(relative)
        for name in names + filenames:
            path = parent / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            require(not stat.S_ISLNK(info.st_mode), 'Symlink prohibited: ' + rel)
            require(info.st_dev == device, 'Nested filesystem prohibited: ' + rel)
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), 'Special file prohibited: ' + rel)
            require(not any('30000' in component for component in path.relative_to(root).parts)
                    and name not in forbidden and rel not in ('model/train', 'model/test'),
                    'Final/completed artifact evidence prohibits archive: ' + rel)
            if stat.S_ISREG(info.st_mode):
                digest = sha(path)
                after = path.stat()
                require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
                        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'File changed while hashing: ' + rel)
                files.append(dict(path=rel, bytes=info.st_size, sha256=digest, mode=stat.S_IMODE(info.st_mode)))
    return dict(schema='GEOGS_FAILED_REPEAT_TREE_v1', scientific_verdict=None,
                files=sorted(files, key=lambda row: row['path']), directories=sorted(directories, key=lambda row: row['path']),
                empty_directories=sorted(empty), file_count=len(files), total_bytes=sum(row['bytes'] for row in files),
                symlinks_allowed=False, model_contents_deserialized=False, quality_assessed=False)


def validate_failure(root, cfg, region):
    target = cfg['targets'][region]
    receipt_path, invocation_path = Path(root) / 'train_receipt.json', Path(root) / 'train_invocation.json'
    require(not receipt_path.is_symlink() and not invocation_path.is_symlink(), 'Receipt/invocation symlink prohibited')
    require(sha(receipt_path) == target['failed_receipt_sha256'], 'Only the exact original failed receipt is eligible; no repeated retry')
    require(sha(invocation_path) == target['failed_invocation_sha256'], 'Only the exact original failed invocation is eligible')
    receipt, invocation = read(receipt_path), read(invocation_path)
    expected = dict(task_id=cfg['task_id'], region=region, condition=cfg['condition'], phase='train',
        repeat_id=cfg['repeat_id'], supplemental_only=True, training_start_iteration=8000,
        config_sha256=cfg['scientific_config_sha256'], runtime_layout_sha256=cfg['runtime_layout_sha256'],
        repeat_contract_sha256=cfg['repeat_contract_sha256'], runtime_image_id=cfg['runtime_image_id'],
        runtime_revision='allocator_v2', input_manifest_sha256=target['input_manifest_sha256'],
        repeat_anchor_checkpoint_sha256=target['anchor_checkpoint_sha256'],
        repeat_anchor_gate_sha256=target['anchor_gate_sha256'], scientific_verdict=None,
        prior_initialization_and_anchor_retained=True, image_only=False, environment=cfg['environment'])
    for value in (receipt, invocation):
        require(all(value.get(key) == wanted for key, wanted in expected.items()), 'Failure invocation/receipt identity differs')
    require(receipt['status'] == 'FAIL' and receipt['native_exit_code'] == 1 and receipt['validated_exit_code'] == 1,
            'Only original native1/validated1 failed training may be archived')
    require(all(receipt.get(key) == value for key, value in invocation.items()), 'Failed receipt differs from its invocation')
    require(type(receipt['wall_seconds']) in (float, int) and math.isfinite(receipt['wall_seconds'])
            and receipt['wall_seconds'] >= 0 and type(receipt['child_peak_rss_bytes']) is int
            and receipt['child_peak_rss_bytes'] >= 0, 'Failed driver cost is invalid')
    require(len(invocation['implementation_hashes']) == 45, 'Expected the pinned 45-file scientific implementation identity')
    return receipt


def checked(root, item):
    require(Path(item['path']).name == item['path'], 'Metadata path escapes evidence directory')
    require(record(Path(root) / item['path']) == item, 'Closed evidence hash/bytes changed: ' + item['path'])


def preflight(root, evidence, config_path, cfg, region, source_host, archive_host):
    evidence = Path(evidence)
    target_mapping = mapping(cfg, region, source_host, archive_host)
    receipt = validate_failure(root, cfg, region)
    manifest = tree_manifest(root)
    dump(evidence / 'before_manifest.json', manifest)
    review = dict(schema='GEOGS_EXACT_FAILED_REPEAT_RETENTION_REVIEW_v1', status='EXACT_FAILED_DIRECTORY_ONLY',
        scientific_verdict=None, mapping=target_mapping, operation='One same-filesystem administrative mv -T -n; no deletion',
        retention='Preserve all file bytes and paths, all directories including empty directories, and permission modes',
        admission=cfg['targets'][region], other_payloads_authorized=False, retry_launched=False,
        original_failure_remains_reportable=True, interpretation=cfg['interpretation'])
    dump(evidence / 'retention_review.json', review)
    cost = dict(region=region, condition=cfg['condition'], repeat_id=cfg['repeat_id'],
        cost_category='ORIGINAL_FAILED_REPEAT_DRIVER_ATTEMPT', status=receipt['status'],
        native_exit_code=receipt['native_exit_code'], wall_seconds=receipt['wall_seconds'],
        child_peak_rss_bytes=receipt['child_peak_rss_bytes'], scientific_verdict='',
        measurement_scope='Original regional driver interval; RUSAGE_CHILDREN maximum RSS, not simultaneous process-tree sum',
        additive_to_completed_run_phase_times=False, include_separately_in_total_resource_reporting=True,
        old_receipt_host_path=source_host + '/train_receipt.json', archived_receipt_host_path=archive_host + '/train_receipt.json',
        source_receipt_sha256=cfg['targets'][region]['failed_receipt_sha256'], interpretation=cfg['interpretation'])
    with (evidence / 'failed_attempt_cost.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cost))
        writer.writeheader()
        writer.writerow(cost)
    result = dict(schema='GEOGS_FAILED_REPEAT_ARCHIVE_PREFLIGHT_v1', status='PASS_EXACT_FAILURE_READY_FOR_SINGLE_MOVE',
        scientific_verdict=None, checked_at_utc=utc(), mapping=target_mapping,
        configuration=record(config_path), verifier=record(__file__), before_manifest=record(evidence / 'before_manifest.json'),
        retention_review=record(evidence / 'retention_review.json'), failed_attempt_cost=record(evidence / 'failed_attempt_cost.csv'),
        failed_receipt_sha256=cfg['targets'][region]['failed_receipt_sha256'],
        failed_invocation_sha256=cfg['targets'][region]['failed_invocation_sha256'],
        root_identity=dict(device=Path(root).stat().st_dev, inode=Path(root).stat().st_ino),
        moved=False, retry_launched=False, source_relative_paths_unchanged=True)
    dump(evidence / 'preflight_receipt.json', result)
    return result


def post(root, evidence, config_path, cfg, region, source_host, archive_host):
    evidence = Path(evidence)
    before = read(evidence / 'preflight_receipt.json')
    require(before['status'] == 'PASS_EXACT_FAILURE_READY_FOR_SINGLE_MOVE' and before['scientific_verdict'] is None,
            'A successful preflight is required')
    require(before['configuration'] == record(config_path) and before['verifier'] == record(__file__),
            'Config/verifier changed after preflight')
    require(before['mapping'] == mapping(cfg, region, source_host, archive_host), 'Source/archive mapping changed')
    for key in ('before_manifest', 'retention_review', 'failed_attempt_cost'):
        checked(evidence, before[key])
    require((evidence / 'mv_exit_code.txt').read_text().strip() == '0'
            and (evidence / 'source_absence_postcheck.txt').read_text() == 'PASS_SOURCE_ABSENT\n',
            'Host move/source-absence postcheck is missing')
    validate_failure(root, cfg, region)
    after = tree_manifest(root)
    require(after == read(evidence / 'before_manifest.json'), 'Archive files/bytes/modes/directories differ from preflight')
    require(before['root_identity'] == dict(device=Path(root).stat().st_dev, inode=Path(root).stat().st_ino),
            'Same-filesystem directory identity changed')
    dump(evidence / 'after_manifest.json', after)
    excluded = {'post_stdout.log', 'post_stderr.log', 'post_exit_code.txt', 'archive_receipt.json', 'closed_metadata_inventory.json'}
    files = [record(path) for path in sorted(evidence.iterdir()) if path.is_file() and path.name not in excluded]
    require(not any(path.is_symlink() for path in evidence.iterdir()), 'Evidence symlink prohibited')
    inventory = dict(schema='GEOGS_CLOSED_ARCHIVE_METADATA_v1', scientific_verdict=None, files=files,
                     exclusions=sorted(excluded), archive_payloads_in_this_inventory=False)
    dump(evidence / 'closed_metadata_inventory.json', inventory)
    for item in files:
        checked(evidence, item)
    result = dict(schema='GEOGS_FAILED_REPEAT_ARCHIVE_RECEIPT_v1', status='PASS_ORIGINAL_FAILURE_ARCHIVED_BYTE_IDENTICALLY',
        scientific_verdict=None, completed_at_utc=utc(), mapping=before['mapping'],
        before_manifest=record(evidence / 'before_manifest.json'), after_manifest=record(evidence / 'after_manifest.json'),
        closed_metadata_inventory=record(evidence / 'closed_metadata_inventory.json'),
        closed_metadata_files_verified=len(files), file_count=after['file_count'], total_bytes=after['total_bytes'],
        empty_directories=after['empty_directories'], same_directory_inode_verified=True,
        original_failure_remains_reportable=True, retry_launched=False, maximum_additional_attempts=1,
        interpretation=cfg['interpretation'], source_absence_evidence='Host mv/source-absence checks, bound in closed metadata inventory',
        limitation='Exact failed-directory byte preservation only; no UAS, quality, service, backup or completed-retry claim')
    dump(evidence / 'archive_receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('preflight', 'post'), required=True)
    parser.add_argument('--region', choices=('P1', 'P2'), required=True)
    parser.add_argument('--config', type=Path, default=Path('/evidence/config.json'))
    parser.add_argument('--source-host', required=True)
    parser.add_argument('--archive-host', required=True)
    args = parser.parse_args()
    require(Path('/.dockerenv').exists() and not Path('/reference').exists() and not Path('/artifacts/JointBuildGS').exists(),
            'Scoped CPU Docker execution required')
    cfg = read(args.config)
    validate_config(cfg)
    require(os.environ.get('JBGS_ARCHIVE_RUNTIME_IMAGE_ID') == IMAGE, 'Pinned CPU runtime image required')
    try:
        function = preflight if args.mode == 'preflight' else post
        result = function(Path('/failed'), Path('/evidence'), args.config, cfg, args.region, args.source_host, args.archive_host)
        print(json.dumps(dict(status=result['status'], region=args.region, scientific_verdict=None)))
    except Exception as error:
        dump(Path('/evidence') / (args.mode + '_failure_receipt.json'),
             dict(status='FAIL', scientific_verdict=None, error=repr(error), mode=args.mode, region=args.region,
                  checked_at_utc=utc(), verifier=record(__file__)))
        raise


if __name__ == '__main__':
    main()
