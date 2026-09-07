"""Post-seal byte preservation and current service identity; never a backup claim."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

BASELINE_SHA = 'a4a4fa39cd375ebd6890a5b8fbba22ae2d71b42b6afef52609209a16963c84f8'
BASELINE_COUNT, DEFERRED_COUNT, SERVICE_COUNT = 6471, 3126, 62
IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
TASK_PREFIXES = ('configs/phd/geogs_p1p2p3_v1/', 'scripts/phd/geogs_p1p2p3_v1/',
                 'docs/experiments/phd/geogs_p1p2p3_v1/', 'src/apps/geogs_p1p2p3_v1/',
                 'tests/phd/geogs_p1p2p3_v1/')
TASK_EXACT = {'Dockerfile.geogs-v1', 'Dockerfile.geogs-compat-v1', 'Dockerfile.geogs-da3-v1',
              'artifacts/manifests/geogs_p1p2p3_v1.yaml', 'tests/phd/test_geogs_input_v1.py',
              'tests/phd/test_geogs_state_v1.py'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def record(root, path):
    return dict(path=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=sha(path))


def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory='+str(repo), '-C', str(repo), *args])


def safe_relative(value):
    path = Path(value)
    require(not path.is_absolute() and '..' not in path.parts and str(path) == value and value != '.',
            'Invalid preservation path: '+value)
    return path


def seal_gate(task, output, gate_factory=None):
    """No repository baseline payload is mounted while establishing this gate."""
    if gate_factory is None:
        from finalization_control import FinalizationGate
        gate_factory = FinalizationGate
    gate = gate_factory(task)
    seal, seal_sha = gate.candidate_seal()
    if hasattr(gate, 'resource'):
        from resource_support import seal_status
        expected_status = seal_status(gate.resource)
    else:
        expected_status = 'ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED'
    require(seal.get('status') == expected_status
            and seal.get('schema') == 'JBGS_GEOGS_CANDIDATES_SEALED_v2'
            and seal.get('reference_accessed') is False and seal.get('scientific_verdict') is None,
            'Actual resource-amended candidate seal required before deferred baseline hashes')
    rows = seal['files']
    require(rows and len({row['path'] for row in rows}) == len(rows), 'Missing or duplicate sealed producer inventory')
    for row in rows:
        path = task/safe_relative(row['path'])
        require(path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'Sealed producer bytes changed: '+row['path'])
    require(sha(task/'contracts/candidates_sealed_v1.json') == seal_sha, 'Candidate seal changed during verification')
    result = dict(schema='GEOGS_PRESERVATION_CANDIDATE_GATE_v1', status='PASS',
                  candidate_seal_sha256=seal_sha, candidate_seal_status=seal['status'],
                  verified_seal_file_count=len(rows), verified_seal_file_bytes=sum(row['bytes'] for row in rows),
                  candidate_count=len(seal['candidates']), extraction_inventory_count=len(seal['extraction_inventory']),
                  config_sha256=seal['config_sha256'], runtime_layout_sha256=seal['runtime_layout_sha256'],
                  repeat_contract_sha256=seal['repeat_contract_sha256'], resource_contract_sha256=seal['resource_contract_sha256'],
                  **{key:seal[key] for key in ('completion_contract_sha256', 'evaluation_scope') if key in seal},
                  scientific_verdict=None, baseline_payload_hashes_started=False,
                  checked_at_utc=datetime.now(timezone.utc).isoformat(), verifier_sha256=sha(__file__))
    dump(output/'candidate_seal_gate.json', result)
    return result


def require_gate(task, output):
    value = load(output/'candidate_seal_gate.json')
    require(value.get('schema') == 'GEOGS_PRESERVATION_CANDIDATE_GATE_v1' and value.get('status') == 'PASS'
            and value.get('scientific_verdict') is None and value.get('baseline_payload_hashes_started') is False
            and value.get('verified_seal_file_count', 0) > 0 and value.get('verifier_sha256') == sha(__file__),
            'Verified post-seal access gate is absent or belongs to different verifier bytes')
    path = task/'contracts/candidates_sealed_v1.json'
    require(sha(path) == value['candidate_seal_sha256'], 'Candidate seal changed after access gate')
    seal = load(path)
    expected_status = 'ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED'
    if value.get('completion_contract_sha256'):
        require(value.get('evaluation_scope') == 'PRIMARY18_SUPPLEMENTAL_INCOMPLETE'
                and sha(task/'contracts/evaluation_completion_v2.json') == value['completion_contract_sha256'],
                'Explicit primary18 completion contract changed after preservation gate')
        expected_status = 'PRIMARY18_CANDIDATES_SEALED_SUPPLEMENTAL_INCOMPLETE'
    require(seal.get('status') == value['candidate_seal_status'] == expected_status,
            'Candidate seal status is not the verified completed state')
    for key in ('config_sha256', 'runtime_layout_sha256', 'repeat_contract_sha256', 'resource_contract_sha256',
                'completion_contract_sha256', 'evaluation_scope'):
        require(seal.get(key) == value.get(key), 'Candidate seal access binding changed: '+key)
    return value


def hash_baseline(repo, baseline, expected_count, output):
    entries = baseline['files']
    require(len(entries) == expected_count and len({row['path'] for row in entries}) == len(entries),
            'Original baseline count or unique membership differs')
    rows = []
    # All original members are processed, including paths inside current task prefixes.
    with (output/'baseline_file_checks.jsonl').open('x') as stream:
        for original in entries:
            name = original['path']
            path = repo/safe_relative(name)
            row = dict(path=name, baseline_bytes=original['bytes'], baseline_sha256=original['sha256'])
            try:
                before = path.stat()
                require(stat.S_ISREG(before.st_mode), 'Not a regular readable file')
                digest = sha(path)
                after = path.stat()
                stable = (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) == (
                          after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns)
                row.update(current_bytes=after.st_size, current_sha256=digest, stable_during_hash=stable,
                           current_symlink_target=os.readlink(path) if path.is_symlink() else None,
                           status='PASS_BYTES' if stable and after.st_size == original['bytes'] and digest == original['sha256']
                           else 'CHANGED_BYTES_OR_DURING_CHECK')
            except (OSError, ValueError) as error:
                row.update(status='MISSING_OR_UNREADABLE', error=repr(error))
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False)+'\n')
            stream.flush()
    return rows


def reconcile_paths(repo, baseline, reconciliation, current_paths):
    old_link = reconciliation['baseline_snapshot_omitted_symlink']
    link = repo/safe_relative(old_link['path'])
    target = os.readlink(link) if link.is_symlink() else None
    head_target = git(repo, 'show', 'HEAD:'+old_link['path']).decode()
    head_entry = git(repo, 'ls-tree', 'HEAD', old_link['path']).decode().strip()
    symlink = dict(path=old_link['path'], current_target=target, head_target=head_target, head_entry=head_entry,
                   status='PASS_HEAD_SYMLINK_TARGET' if target == old_link['current_target'] == old_link['head_target'] == head_target
                   and head_entry == old_link['head_entry'] else 'DIFFERENCE_REQUIRES_REVIEW',
                   target_payload_followed=False, baseline_limitation=old_link['baseline_limitation'])
    old_unknown = reconciliation['new_observed_outside_scope']
    unknown_path = repo/safe_relative(old_unknown['path'])
    unknown = dict(path=old_unknown['path'], provenance='UNKNOWN', content_read=False,
                   limitation='No original content SHA exists; preservation evidence is metadata only.')
    try:
        info = unknown_path.lstat()
        unknown.update(bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                       git_status=git(repo, 'status', '--short', '--', old_unknown['path']).decode().strip())
        matched = stat.S_ISREG(info.st_mode) and all(unknown[key] == old_unknown[key] for key in ('bytes','mtime_ns','git_status'))
        unknown['status'] = 'PASS_OBSERVED_METADATA_ONLY' if matched else 'DIFFERENCE_REQUIRES_REVIEW'
    except OSError as error:
        unknown.update(status='MISSING_OR_UNREADABLE', error=repr(error))
    extras = sorted(current_paths-{row['path'] for row in baseline['files']})
    known = [name for name in extras if name in TASK_EXACT or any(name.startswith(prefix) for prefix in TASK_PREFIXES)]
    outside = [name for name in extras if name not in known and name not in (old_link['path'], old_unknown['path'])]
    return symlink, unknown, known, outside


def final_check(repo, task, output):
    gate = require_gate(task, output)  # Must precede all baseline content hashing.
    preservation = task/'preservation'
    baseline_path = preservation/'workspace_before.json'
    require(sha(baseline_path) == BASELINE_SHA, 'Original workspace snapshot changed')
    baseline = load(baseline_path)
    interim = load(preservation/'interim_allocator_v2.json')
    reconciliation = load(preservation/'interim_allocator_v2_reconciliation.json')
    require(interim['baseline_sha256'] == BASELINE_SHA and interim['summary']['baseline_files'] == BASELINE_COUNT
            and interim['summary']['metadata_only_pending_byte_checks'] == DEFERRED_COUNT
            and reconciliation['raw_report_sha256'] == sha(preservation/'interim_allocator_v2.json'),
            'Initial/interim/reconciliation preservation lineage differs')
    rows = hash_baseline(repo, baseline, BASELINE_COUNT, output)
    deferred = {row['path'] for row in interim['files'] if row.get('byte_check_deferred')}
    require(len(deferred) == DEFERRED_COUNT, 'Original deferred payload membership differs')
    deferred_hashed = sum(row['path'] in deferred and 'current_sha256' in row for row in rows)
    head = git(repo, 'rev-parse', 'HEAD').decode().strip()
    tracked_before = [line for line in (preservation/'status_before.txt').read_text().splitlines() if not line.startswith('??')]
    status_now = git(repo, 'status', '--short').decode()
    tracked_now = [line for line in status_now.splitlines() if not line.startswith('??')]
    current_patch = git(repo, 'diff', '--binary', 'HEAD')
    patch_matches = hashlib.sha256(current_patch).hexdigest() == sha(preservation/'tracked_before.patch')
    current_paths = {value.decode() for value in (set(git(repo, 'ls-files', '-z').split(b'\0')) |
                     set(git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0'))) if value}
    symlink, unknown, known_new, outside_new = reconcile_paths(repo, baseline, reconciliation, current_paths)
    service_command = [sys.executable, str(Path(__file__).with_name('verify_service_snapshot.py')),
                       '--baseline', str(preservation/'services_before.txt'),
                       '--current', str(output/'services_current_default.txt'), '--output', str(output/'service_receipt.json')]
    result = subprocess.run(service_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    with (output/'service_verifier.log').open('x') as stream:
        stream.write(result.stdout)
    services = load(output/'service_receipt.json')
    from verify_service_snapshot import parse
    current_services = [parse(line) for line in (output/'services_current_default.txt').read_text().splitlines() if line]
    old_ids = {row['baseline']['id'] for row in services['services']}
    extras = [row for row in current_services if row['id'] not in old_ids]
    checks = dict(all_baseline_bytes_unchanged=all(row['status']=='PASS_BYTES' for row in rows),
                  head_unchanged=head == baseline['head'], tracked_dirty_status_unchanged=tracked_before == tracked_now and len(tracked_before)==4,
                  tracked_dirty_patch_unchanged=patch_matches, omitted_symlink_unchanged=symlink['status']=='PASS_HEAD_SYMLINK_TARGET',
                  observed_unknown_metadata_unchanged=unknown['status']=='PASS_OBSERVED_METADATA_ONLY',
                  no_unreconciled_new_outside_task_paths=not outside_new,
                  baseline_services_current_identity=result.returncode == 0 and services['baseline_count']==SERVICE_COUNT
                  and services['identity_pass_count']==SERVICE_COUNT,
                  candidate_seal_unchanged=sha(task/'contracts/candidates_sealed_v1.json') == gate['candidate_seal_sha256'])
    baseline_records = [record(preservation, preservation/name) for name in ('workspace_before.json','status_before.txt','tracked_before.patch',
                        'services_before.txt','interim_allocator_v2.json','interim_allocator_v2_reconciliation.json')]
    evidence = [record(output,path) for path in sorted(output.rglob('*')) if path.is_file()
                and path.name not in ('verifier.log','final_receipt.json','exit_code.txt')]
    report = dict(schema='GEOGS_FINAL_PRESERVATION_v1', status='PASS_BASELINE_BYTES_AND_CURRENT_IDENTITIES' if all(checks.values()) else 'DIFFERENCES_REQUIRING_REVIEW',
                  scientific_verdict=None, checked_at_utc=datetime.now(timezone.utc).isoformat(), runtime_image_id=IMAGE,
                  checks=checks, candidate_seal_gate=gate, baseline_metadata=baseline_records,
                  summary=dict(baseline_files=len(rows), byte_checks_pass=sum(row['status']=='PASS_BYTES' for row in rows),
                               original_files_hashed=sum('current_sha256' in row for row in rows),
                               prior_deferred_payload_files=DEFERRED_COUNT, deferred_hashes_completed=deferred_hashed,
                               deferred_hashes_remaining=DEFERRED_COUNT-deferred_hashed,
                               baseline_services=services['baseline_count'], current_service_identity_pass=services['identity_pass_count'],
                               additional_current_containers=len(extras)),
                  head=dict(baseline=baseline['head'], current=head), tracked_dirty_status=dict(before=tracked_before,current=tracked_now),
                  baseline_file_checks=record(output,output/'baseline_file_checks.jsonl'),
                  baseline_snapshot_omitted_symlink=symlink, new_observed_outside_scope=unknown,
                  new_task_paths=known_new, unreconciled_new_paths_outside_task=outside_new,
                  services=services, services_not_in_baseline=extras, evidence=evidence,
                  limitations=['All 6471 original members compared to snapshot bytes; no current-task prefix exclusion applies to existing files.',
                               'The original snapshot itself excluded some task paths and directory symlinks; this does not expand its historical coverage.',
                               'Opaque byte hashing after a valid candidate seal does not decode or assess scientific payload quality.',
                               'Unknown new document has metadata-only evidence and no original content SHA; no authorship attribution.',
                               'Service ID/name/image descriptor/ports/running are current observations; no never-restarted, immutable-image, browser-health or service-data-byte claim.',
                               'No backup durability, complete external artifact preservation, evaluation quality or scientific verdict is established.'])
    dump(output/'final_receipt.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('gate','final'), required=True)
    parser.add_argument('--task', type=Path, default=Path('/task'))
    parser.add_argument('--repo', type=Path, default=Path('/repo'))
    parser.add_argument('--output', type=Path, default=Path('/out'))
    args = parser.parse_args()
    require(Path('/.dockerenv').exists() and not Path('/reference').exists(), 'Use isolated Docker preservation verification')
    if args.mode == 'gate':
        require(not args.repo.exists(), 'Seal access gate must run without a repository baseline mount')
    try:
        report = seal_gate(args.task,args.output) if args.mode=='gate' else final_check(args.repo,args.task,args.output)
        print(json.dumps(dict(status=report['status'], summary=report.get('summary')), ensure_ascii=False))
        return 0 if report['status'] in ('PASS','PASS_BASELINE_BYTES_AND_CURRENT_IDENTITIES') else 1
    except Exception as error:
        failure = dict(status='FAIL_CLOSED', phase=args.mode, error=repr(error), scientific_verdict=None,
                       verifier_sha256=sha(__file__), checked_at_utc=datetime.now(timezone.utc).isoformat())
        dump(args.output/(args.mode+'_failure_receipt.json'),failure)
        print(json.dumps(failure))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
