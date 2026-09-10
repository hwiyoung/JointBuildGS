"""One additive repair of startup-only missing rg in the systemd PATH."""
import argparse,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
    if not ok:raise ValueError(msg)
def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--host-repo',type=Path,required=True);p.add_argument('--state',type=Path,required=True);a=p.parse_args()
    require(Path('/.dockerenv').exists(),'Docker required');started=datetime.now(timezone.utc).isoformat()
    guard=a.state/'executing_source_sha256.txt';original=guard.read_bytes();old={}
    for line in original.decode().splitlines():
        digest,name=line.split('  ',1);path=Path(name);relative=path.relative_to(a.host_repo)
        require('..' not in relative.parts and sha(a.repo/relative)==digest,'Previously guarded source changed');old[name]=digest
    groups={'parent_analysis_helpers':[x for x in (a.repo/'scripts/phd/geogs_p1p2p3_v1').rglob('*') if x.is_file() and x.suffix in ['.py','.sh']],
            'review_3d_app':[x for x in (a.repo/'src/apps/local_complementary_3d_v2').rglob('*') if x.is_file()]}
    require(all(groups.values()),'Expected nonempty omitted source groups')
    extended=dict(old);added=[]
    for group,paths in groups.items():
        for path in paths:
            host=str(a.host_repo/path.relative_to(a.repo));digest=sha(path)
            require(host not in extended or extended[host]==digest,'Source changed while repairing')
            if host not in extended:added.append(dict(group=group,path=host,sha256=digest))
            extended[host]=digest
    require(added,'Repair already applied or wrong original guard')
    events=(a.state/'events.log').read_bytes();marker=a.state/'exit_code.txt'
    require(marker.read_text().strip()=='127' and b'ERROR exit=127' in events,'Expected startup subshell failure marker')
    require(b'ERROR' not in events.splitlines()[-1],'Worker has a new failure; investigate before repair')
    require(guard.read_bytes()==original,'Guard changed concurrently')
    repair=a.state/'source_guard_repair_v2_1';repair.mkdir(exist_ok=False)
    (repair/'executing_source_sha256.initial.txt').write_bytes(original)
    (repair/'events_before_repair.log').write_bytes(events)
    (repair/'repair_automation_guard_v2_1.py').write_bytes(Path(__file__).read_bytes())
    new=''.join(f'{digest}  {name}\n' for name,digest in sorted(extended.items()))
    staged=repair/'executing_source_sha256.repaired.txt';staged.write_text(new)
    for name,digest in extended.items():require(sha(a.repo/Path(name).relative_to(a.host_repo))==digest,'Source changed during final guard validation')
    temporary=a.state/'executing_source_sha256.repair.tmp';temporary.write_text(new);os.replace(temporary,guard)
    # This marker came from failed startup process substitutions, not the still
    # running coordinator's exit. Keep its exact bytes in the repair evidence.
    marker.rename(repair/'initialization_subshell_exit_code.txt')
    receipt=dict(status='PASS_ADDITIVE_SOURCE_GUARD_REPAIR',scientific_verdict=None,started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),
        reason='systemd PATH lacked Codex-bundled rg; startup process substitutions failed while coordinator continued',
        previously_guarded_file_count=len(old),guarded_file_count=len(extended),added_files=added,
        original_guard_sha256=hashlib.sha256(original).hexdigest(),repaired_guard_sha256=sha(guard),
        source_code_modified=False,training_policy_modified=False,processes_stopped=False,
        coverage_limitation='Added files are guarded from this repair onward; no retroactive startup attestation')
    (repair/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    with (a.state/'events.log').open('a') as f:f.write(datetime.now(timezone.utc).isoformat()+' SOURCE_GUARD_REPAIR_PASS added_files='+str(len(added))+' existing_sources_unchanged=true; no process stopped\n')
    print(json.dumps(dict(status=receipt['status'],added_files=len(added),guarded_files=len(extended),receipt=str(repair/'receipt.json'),scientific_verdict=None)))
if __name__=='__main__':main()
