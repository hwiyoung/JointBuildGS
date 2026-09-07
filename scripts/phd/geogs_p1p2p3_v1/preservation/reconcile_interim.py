"""Reconcile metadata representation differences without replacing raw evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import yaml


repo, out = Path('/repo'), Path('/out')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=/repo', '-C', str(repo), *args])


def parse_service(line):
    identifier, name, image, remainder = line.split(maxsplit=3)
    port_match = re.search(r'(?:\d+\.\d+\.\d+\.\d+:|\[::\]:|\d+/tcp|\d+/udp)', remainder)
    ports = remainder[port_match.start():] if port_match else ''
    return dict(id=identifier, name=name, image_descriptor=image,
                running=remainder.startswith('Up '),
                ports=sorted(item.strip() for item in ports.split(',') if item.strip()),
                raw_line=line)


raw_path = out / 'interim_allocator_v2.json'
raw = json.loads(raw_path.read_text())
old_services = [parse_service(line) for line in (out / 'services_before.txt').read_text().splitlines()]
current_services = [parse_service(line) for line in (out / 'services_interim_allocator_v2_default_format.txt').read_text().splitlines()]
current_by_id = {row['id']: row for row in current_services}
services = []
for old in old_services:
    current = current_by_id.get(old['id'])
    fields = ['id', 'name', 'image_descriptor', 'ports', 'running']
    equal = {field: current is not None and old[field] == current[field] for field in fields}
    services.append(dict(baseline=old, current=current, field_matches=equal,
                         status='PASS_CURRENT_IDENTITY' if all(equal.values()) else 'DIFFERENCE_REQUIRES_REVIEW'))

representation = []
for row in raw['services']:
    if row['status'] == 'PASS_IDENTITY':
        continue
    identifier = row['baseline_id']
    current = current_by_id.get(identifier)
    representation.append(dict(
        baseline_id=identifier, baseline_descriptor=row['baseline_image_descriptor'],
        no_trunc_descriptor=row['current']['Image'] if row['current'] else None,
        current_default_descriptor=current['image_descriptor'] if current else None,
        exact_default_descriptor_match=current is not None and current['image_descriptor'] == row['baseline_image_descriptor'],
        explanation='Different Docker ps formatting; full no-trunc descriptor and original raw flag retained.'))

symlink_name = 'src/apps/experiment_dashboard/_shared/build'
symlink_path = repo / symlink_name
head_link_target = git('show', 'HEAD:' + symlink_name).decode()
current_link_target = os.readlink(symlink_path)
symlink = dict(path=symlink_name, head_entry=git('ls-tree', 'HEAD', symlink_name).decode().strip(),
               head_target=head_link_target, current_target=current_link_target,
               status='PASS_HEAD_SYMLINK_TARGET' if head_link_target == current_link_target else 'CHANGED_TARGET',
               baseline_limitation='workspace_before.json includes only is_file paths; this tracked directory symlink was omitted.')
unknown_name = 'docs/experiments/phd/thesis_topic_v1/05_METHOD_STRUCTURE_CANDIDATE_ko_v1.md'
unknown_path = repo / unknown_name
stat = unknown_path.lstat()
unknown = dict(path=unknown_name, bytes=stat.st_size, mtime_ns=stat.st_mtime_ns,
               git_status=git('status', '--short', '--', unknown_name).decode().strip(),
               status='NEW_OBSERVED_OUTSIDE_TASK_PROVENANCE_UNKNOWN', content_read=False,
               action='Preserved untouched; no attribution to any person, agent or task.')

layout_repo = repo / 'configs/phd/geogs_p1p2p3_v1/runtime_layout_allocator_v2.json'
layout_external = Path('/layout_external.json')
layout = json.loads(layout_repo.read_text())
manifest = yaml.safe_load((repo / 'artifacts/manifests/geogs_p1p2p3_v1.yaml').read_text())
checks = {
    'layout_bytes_identical': digest(layout_repo) == digest(layout_external),
    'scientific_config_matches': digest(repo / 'configs/phd/geogs_p1p2p3_v1/experiment_v1.json') == layout['scientific_config_sha256'],
    'runs_directory_matches': manifest['outputs']['regions'] == layout['runs_directory'],
    'parity_directory_matches': manifest['outputs']['exact_anchor_validation'] == layout['parity_directory'],
    'queue_directory_matches': manifest['outputs']['queue'] == layout['queue_directory'],
    'p1_anchor_matches': manifest['outputs']['p1_shared_anchor'] == layout['anchors']['P1']['checkpoint_directory'],
    'p2_anchor_matches': manifest['outputs']['p2_shared_anchor_expected'] == layout['anchors']['P2']['checkpoint_directory'],
    'p3_anchor_matches': manifest['outputs']['p3_shared_anchor_expected'] == layout['anchors']['P3']['checkpoint_directory'],
    'allocator_matches': manifest['runtime']['allocator'] == layout['allocator'],
    'revision_matches': manifest['runtime']['layout_revision'] == layout['revision'],
    'two_failed_attempts_explicit': manifest['preserved_failed_attempts'] == ['runs/P1/D005_Pnative', 'runs/P1/D0005_Pnative'],
    'null_verdict_preserved': manifest['scientific_verdict'] is None and layout['scientific_verdict'] is None,
    'no_recovery_success_claim': manifest['runtime_interpretation']['successful_recovery_claim'] is False,
}
failures = [key for key, value in checks.items() if not value]
passed = (not failures and all(row['status'] == 'PASS_CURRENT_IDENTITY' for row in services)
          and symlink['status'] == 'PASS_HEAD_SYMLINK_TARGET'
          and not raw['preexisting_changed_files'] and not raw['preexisting_missing_files']
          and raw['head']['unchanged'] and raw['tracked_dirty_status']['unchanged'])
report = dict(schema='geogs_preservation_interim_reconciliation_v1', scientific_verdict=None,
              checked_at_utc=datetime.now(timezone.utc).isoformat(),
              status='PARTIAL_SOURCE_AND_SERVICE_IDENTITIES_PASS_PAYLOAD_BYTES_DEFERRED' if passed else 'DIFFERENCES_REQUIRING_REVIEW',
              raw_report_path='preservation/interim_allocator_v2.json', raw_report_sha256=digest(raw_path),
              raw_report_status_unchanged=raw['status'], source_script_sha256=digest(__file__),
              current_default_service_snapshot_sha256=digest(out / 'services_interim_allocator_v2_default_format.txt'),
              workspace_summary=raw['summary'],
              service_summary=dict(baseline=len(services), current_identity_pass=sum(row['status'] == 'PASS_CURRENT_IDENTITY' for row in services)),
              services=services, descriptor_representation_findings=representation,
              baseline_snapshot_omitted_symlink=symlink, new_observed_outside_scope=unknown,
              runtime_layout=dict(sha256=digest(layout_repo), contract=layout, checks=checks, failures=failures),
              limitations=[
                  '3126 baseline entries have only existence and size checks; opaque payload hashes await candidate seal. No UAS payload read.',
                  'Service identity is observed currently. Baseline lacks immutable image IDs and restart timestamps, so no never-restarted claim is possible.',
                  'The original no-trunc service differences and outside-task path observations remain in the raw report unchanged.',
                  'Unknown new document preserved untouched; its provenance is unknown and no attribution is made.',
                  'This is an interim preservation and path-contract check, not backup durability, experiment completion or scientific validation.'])
with (out / 'interim_allocator_v2_reconciliation.json').open('x') as stream:
    json.dump(report, stream, indent=2, ensure_ascii=False)
print(json.dumps({key: report[key] for key in ['status', 'service_summary', 'new_observed_outside_scope', 'runtime_layout']}, ensure_ascii=False))
assert passed, report['status']
