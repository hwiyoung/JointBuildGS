"""Document read-only source mounts and the before/after workspace path boundary."""
from common import *
allowed=['configs/phd/main_recount_v1/','scripts/phd/main_recount_v1/','docs/experiments/phd/main_recount_v1/']
def outside(line):return not any(p in line for p in allowed)
before=(D/'provenance/workspace_before.txt').read_text().splitlines()
after=(D/'provenance/workspace_after.txt').read_text().splitlines()
b=set(filter(outside,before));a=set(filter(outside,after))
new=sorted(a-b);removed=sorted(b-a)
source_changes=[]
for r in json.loads((D/'provenance/inputs.lock.json').read_text())['sources']:
    # The container mounts all prior payloads read-only. Verify the smaller
    # Git-owned source/config/table files against their pre-calculation hashes.
    if r['path'].startswith('/repo/') and sha(r['path'])!=r['sha256']:source_changes.append(r['path'])
dump(D/'provenance/write_boundary.json',dict(at=now(),new_paths_outside_scope=new,changed_prior_tracked_paths=source_changes,
    preexisting_status_entries_removed_or_changed=removed,preexisting_outside_status_entries=len(b),
    status_only_limit='before/after status comparison does not prove unchanged bytes of unrelated pre-existing dirty files; all task writes use scoped tools/mounts',
    prior_git_owned_inputs_sha256_match=not source_changes,allowed_repo_prefixes=allowed,
    artifact_root='PH/main_recount_v1/PHD-MAIN-RECOUNT-v1 = ../JointBuildGS-artifacts/phase-payloads/phd/main_recount_v1/PHD-MAIN-RECOUNT-v1',scientific_verdict=None))
assert not new and not removed and not source_changes
print('BOUNDARY_PASS',len(b),'pre-existing outside entries preserved')
