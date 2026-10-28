"""Host stdlib launcher for one explicitly authorized conditional r17 replay."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

def now():return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
def save(path,data):
    assert not path.exists(),path
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
ap=argparse.ArgumentParser();ap.add_argument('--gpu',type=int,choices=[0,1],required=True)
ap.add_argument('--run',choices=['fd_dynnow_ALS_s0','fd_current_ALS_s0'],required=True);ap.add_argument('--current-record-only-retry',action='store_true');a=ap.parse_args()
repo=Path(__file__).resolve().parents[3];ph=repo.parent/'JointBuildGS-artifacts/phase-payloads/phd'
lt=ph/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1';out=ph/'main_floatdiag_v1/PHD-MAIN-FLOATDIAG-v1'
planpath=repo/'configs/phd/main_floatdiag_v1/conditional_replays.json';plan=json.loads(planpath.read_text())
run=next(x for x in plan['runs'] if x['name']==a.run)
retry=a.current_record_only_retry
if retry:
    assert a.run=='fd_current_ALS_s0'
    authority=repo/'configs/phd/main_floatdiag_v1/current_retry_authorization.json'
    assert json.loads(authority.read_text())['allowed_retries']==1
    first=out/'runs/R1rep_b10'/a.run
    assert json.loads((first/'receipt.json').read_text())['status']=='STOP'
    run=dict(run,arguments=[x.replace('/fd_current_ALS_s0/','/fd_current_ALS_s0_record_only/') for x in run['arguments']])
assert (out/'packages/A1_delivered.json').exists(),'first visual bundle must be delivered before conditional training'
assert json.loads((repo/'docs/experiments/phd/main_floatdiag_v1/provenance/diagnostic_loss_adapter.json').read_text())['status']=='PASS'
assert json.loads((repo/'docs/experiments/phd/main_floatdiag_v1/provenance/replay_observer_check.json').read_text())['status']=='PASS'
with (lt/f'checks/photo_gpu_{a.gpu}.lock').open() as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    compute=subprocess.check_output(['nvidia-smi','-i',str(a.gpu),'--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True)
    active=[l for l in compute.splitlines() if l.split(', ',1)[-1] not in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg']]
    assert not active,'Protected compute activity: '+str(active)
    stable=0
    while stable<60:
        kb=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))
        available=kb/1024**2;stable=stable+5 if available>=56 else 0
        print(f'memory admission: {available:.2f} GiB, stable {stable}/60s',flush=True);time.sleep(5)
    run_name=a.run+'_record_only' if retry else a.run
    unit=out/'runs/R1rep_b10'/run_name;unit.mkdir(parents=True,exist_ok=False)
    original=json.loads(Path(plan['original_command']).read_text());command=original[:original.index('train.py')]
    command[command.index('--name')+1]='jbgs-floatdiag-'+run_name.replace('_','-')
    command[command.index('--gpus')+1]=f'device={a.gpu}'
    command[command.index('--memory')+1]='40g'
    command=[str(out)+':/o' if x==str(lt)+':/o' else x for x in command]
    assert str(out)+':/o' in command and str(lt)+':/o' not in command
    observer='replay_current_record_only.py' if retry else 'replay_observer.py'
    command+=['/repo/scripts/phd/main_floatdiag_v1/'+observer,*run['arguments']]
    source=repo/'src/phd/forks/GeoGS-conf-guided-v1-r17'
    save(unit/'START.json',dict(at=now(),command=command,plan_sha256=hashlib.sha256(planpath.read_bytes()).hexdigest(),
        source_sha256={p:hashlib.sha256((source/p).read_bytes()).hexdigest() for p in ['train.py','jbgs_judgment.py']},
        observer_sha256=hashlib.sha256((repo/'scripts/phd/main_floatdiag_v1/replay_observer.py').read_bytes()).hexdigest(),
        observer_scope='CPU-only bookkeeping; unchanged method arguments, tensors, optimizer, random state and health decisions; birth sidecar at exact save_ply state',
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
        memory_limit_GiB=40,memory_admission_GiB=available,scientific_verdict=None))
    if retry:save(unit/'POLICY_CHANGE.json',dict(authority=json.loads(authority.read_text()),wrapper_sha256=hashlib.sha256((repo/'scripts/phd/main_floatdiag_v1'/observer).read_bytes()).hexdigest(),original_stop_receipt=str(first/'receipt.json'),scientific_verdict=None))
    started=time.monotonic()
    with (unit/'run.log').open('w') as log:rc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
    if rc==0:assert (unit/'model/point_cloud/iteration_7000/point_cloud.ply').exists()
    text=(unit/'run.log').read_text();reason=next((line for line in reversed(text.splitlines()) if 'LOSSTRAIN_STOP:' in line),None)
    save(unit/'receipt.json',dict(at=now(),seconds=time.monotonic()-started,exit_code=rc,
        status='PASS' if rc==0 else 'STOP',health_reason=reason,scientific_verdict=None))
    print(a.run,'PASS' if rc==0 else 'STOP',reason,flush=True)
    raise SystemExit(rc)
