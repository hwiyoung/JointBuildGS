"""Retire idle schedulers and seal a receipt-aware continuation, preserving outputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

def read(p):return json.loads(Path(p).read_text())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2))

ap=argparse.ArgumentParser();ap.add_argument('attempt',type=Path);a=ap.parse_args();root=a.attempt.resolve()
s=read(root/'execution/status.json');old=root/s['parallel_run'];unit=read(old/'plan.json')['unit']+'.service'
assert {r['gpu']:r['state'] for r in s['workers']}=={'1':'FAILED','0':'WAITING_RESOURCES'}
assert next(r for r in s['workers'] if r['gpu']=='0')['job']=='local_prior0'
assert not list((root/'R2/local_prior0').iterdir())
assert read(root/'R2/local_prior0_preflight/receipt.json')['status']=='PASS'
pid=int(subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True))
os.kill(pid,signal.SIGSTOP)
try:
    for _ in range(100):
        if Path(f'/proc/{pid}/stat').read_text().split()[2]=='T':break
        time.sleep(.01)
    assert Path(f'/proc/{pid}/stat').read_text().split()[2]=='T'
    ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
    containers=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True))
    active=[c['Id'] for c in containers if c['HostConfig'].get('DeviceRequests') and
            any(m['Destination']=='/output' and m['Source'].startswith(str(root)+'/') for m in c['Mounts'])]
    assert not active, active
    assert read(root/'R3/da3/receipt.json')['status']=='PASS'
    assert not (root/'R3/extract_da3').exists()
    folder=root/('parallel_recovery_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));folder.mkdir()
    shutil.copy2(root/'execution/status.json',folder/'previous_status.json')
    source=folder/'source';shutil.copytree(old/'source',source,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    here=Path(__file__).resolve().parent
    for name in ['parallel_queue.py','resume_parallel.py']:shutil.copy2(here/name,source/name)
    for name in ['phase.py','run_queue.py','train_observed.py','intervention.py']:
        assert (old/'source'/name).read_bytes()==(source/name).read_bytes()
    overrides=read(root/'execution/artifact_overrides.json')
    overrides.setdefault('R2',{})['local_prior0']=f'R2/local_prior0_{folder.name}'
    plan=dict(unit='jbgs-r1r5-'+folder.name.replace('_','-'),artifact_overrides=overrides,
        pending=[['R3','da3'],['R2','local_prior0'],['R5','da3'],['R3','local_prior0'],['R4','local_prior0'],['R5','local_prior0']],
        resolved_scheduler_failure='systemd requires --kill-who, not --kill-whom; completed R3 checkpoint retained',
        resource_gate_fix='GPU0 permits desktop-only utilization; free VRAM >=23000 MiB and no competing compute process required',
        previous_parallel_run=old.name,scientific_verdict=None)
    save(folder/'plan.json',plan)
    save(folder/'source_hashes.json',{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()})
    launch=['systemd-run','--user','--unit',plan['unit'],'--property=Type=exec','--property=RemainAfterExit=yes',
            '--setenv=PYTHONDONTWRITEBYTECODE=1','/usr/bin/python3',str(source/'resume_parallel.py'),str(root),str(folder)]
    save(folder/'launch.json',launch)
except Exception:
    os.kill(pid,signal.SIGCONT);raise
# Every task container is already finished; retire only the two idle scheduler mains.
for retiring in [unit,read(old/'plan.json')['old_unit']]:
    subprocess.run(['systemctl','--user','kill','--kill-who=main','--signal=SIGKILL',retiring],check=True)
save(folder/'retirement.json',dict(status='PASS_IDLE_SCHEDULER_RETIREMENT',active_training_containers=[],
    previous_scheduler_pid=pid,scientific_verdict=None))
temp=root/'execution/artifact_overrides.tmp';save(temp,overrides);temp.replace(root/'execution/artifact_overrides.json')
subprocess.run(launch,check=True)
print(folder)
