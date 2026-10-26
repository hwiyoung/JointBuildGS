"""Host stdlib Docker orchestrator; all project computation runs inside r16's image.

Each lane handles one GPU. A case runs r16 then r17 on the same GPU. The probe
exits inside Judgment construction, before any optimizer step. No training.
"""
import concurrent.futures
import argparse
import datetime
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'scripts/phd/main_fixtest_v1'))
import ft_plan as P

OUT=P.PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1'
P.FT=OUT
P.SRC['r17']=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r17'
P.IMG='jointbuildgs:geogs-conf-guided-v1'
ATTEMPT='current'

def case(site,prior,gpu):
    base=P.S3/'runs'/site/f'nojudge_{prior}_s0/model'
    ply=base/'point_cloud/iteration_15000/point_cloud.ply';ref=base/'monitor/init_points.npz'
    source='stage3 nojudge 15000'
    if not ply.is_file() or not ref.is_file():
        ply,ref=P.ckpt_of(site,prior,0);source='stage1 15000 fallback'
    assert ply.is_file() and ref.is_file()
    for revision in ['r16','r17']:
        tag=f'{revision}_{site}_{prior}'
        dest=OUT/'checks'/ATTEMPT/tag
        if dest.exists():raise RuntimeError(f'refuse rerun/overwrite {dest}')
        dest.mkdir(parents=True)
        args=P.train_args(site,prior,f'/o/checks/{ATTEMPT}/{tag}/model',sw_off=['judgment'],schedule=P.SP.SCHEDULE_PROBE)
        entry=['/repo/scripts/phd/main_losstrain_v1/probe_current.py','--probe_out',f'/o/checks/{ATTEMPT}/{tag}/probe',
            '--probe_ply',P.to_container(ply),'--probe_ref_init',P.to_container(ref),'--probe_iteration','15000','--',*args,*P.RECORDS]
        command=P.docker('jbgs-lt-check-'+tag.lower().replace('_','-'),gpu,revision,site,entry)
        command[2:2]=['--memory','48g']
        start=time.monotonic();stamp=datetime.datetime.now().astimezone().isoformat()
        (dest/'command.json').write_text(json.dumps(command,indent=1)+'\n')
        with (dest/'run.log').open('w') as log:
            rc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
        receipt=dict(tag=tag,gpu=gpu,exit_code=rc,started_at=stamp,seconds=time.monotonic()-start,
            checkpoint_source=source,checkpoint_path=str(ply),checkpoint_sha256=hashlib.sha256(ply.read_bytes()).hexdigest(),
            command=command,optimizer_steps=0,scientific_verdict=None)
        (dest/'receipt.json').write_text(json.dumps(receipt,indent=1)+'\n')
        print(tag,'rc',rc,'seconds',round(receipt['seconds'],1),flush=True)
        if rc:raise RuntimeError(f'EXECUTION_STOP: {tag}; see {dest}/run.log')
    subprocess.run(['bash',str(REPO/'scripts/phd/main_losstrain_v1/run_cpu.sh'),
        'comparecurrent','compare_current.py','--attempt',ATTEMPT,'--site',site,'--prior',prior],check=True)

def lane(gpu,units):
    for site,prior in units:case(site,prior,gpu)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',required=True)
    ap.add_argument('--gpus',type=int,nargs='+',default=[0]);ap.add_argument('--first',default='B173nb_b10/ALS')
    a=ap.parse_args();ATTEMPT=a.attempt
    assert ATTEMPT=='current_direct_v1','each new attempt must have an explicitly named output directory'
    gate=json.loads((OUT/'direct_stage1_v1/gates.json').read_text())
    assert gate['gate']=='PASS','amended direct rules gates must pass'
    dest=OUT/'checks'/ATTEMPT;assert not dest.exists();dest.mkdir()
    (dest/'resume.json').write_text(json.dumps(dict(
        authority='user 2026-10-26 17:00 amendment; both replacement gates PASS',
        historical_stop='checks/STOP.json retained, superseded only for patch correspondence',
        gate_sha256=hashlib.sha256((OUT/'direct_stage1_v1/gates.json').read_bytes()).hexdigest(),
        gpus=a.gpus,optimizer_steps=0,scientific_verdict=None),indent=2)+'\n')
    units=sorted(P.UNITS6,key=lambda u: '/'.join(u)!=a.first)
    with concurrent.futures.ThreadPoolExecutor(len(a.gpus)) as pool:
        jobs=[pool.submit(lane,gpu,units[i::len(a.gpus)]) for i,gpu in enumerate(a.gpus)]
        for job in jobs:job.result()
