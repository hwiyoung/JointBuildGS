"""Bounded batches of the authorized 30k trainings; one run per GPU, serial TSDF.

Invoke first, then remaining only after the interim receipt, then optional only
after 24 completed trainings without a new stop. Never retries except one OOM.
"""
import argparse
import concurrent.futures
import json
import subprocess
import threading
import time
from pathlib import Path
import train_calibration as C
P=C.P;OUT=C.OUT;REPO=C.REPO;save=C.save;sha=C.sha;now=C.now
STOP=threading.Event();TSDF=threading.Lock()
MODES={'lt_fixgt':('fixed','gt'),'lt_dyngt':('dynamic','gt'),'lt_dynsoft':('dynamic','soft'),'lt_dynnow':('dynamic','now'),'lt_fixnow':('fixed','now')}

def runs_for(batch):
    first=[dict(site='B173nb_b10',prior='ALS',variant=v) for v in list(MODES)[:4]]
    if batch=='first':return first
    remaining=[dict(site=s,prior=p,variant=v) for s,p in P.UNITS6 for v in list(MODES)[:4] if (s,p)!=('B173nb_b10','ALS')]
    if batch=='remaining':return remaining
    return [dict(site=s,prior=p,variant='lt_fixnow') for s,p in P.UNITS6]

def root_of(r):return OUT/'runs'/r['site']/(r['variant']+'_'+r['prior']+'_s0')

def gates(batch):
    C.gates()
    selection=json.loads((OUT/'checks/lambda_selection.json').read_text());assert selection['status']=='PASS'
    cfg=json.loads((REPO/'configs/phd/main_losstrain_v1/losstrain_v1.json').read_text())
    assert cfg['lambda_selection']['selected_lambda']==selection['selected_lambda']
    assert (OUT/'checks/preparation_commit.json').is_file(),'preparation report must be committed first'
    assert not (OUT/'checks/full_STOP.json').exists()
    if batch in ['remaining','optional']:
        assert json.loads((OUT/'checks/interim.json').read_text())['status']=='PASS'
        assert all((root_of(r)/'post_PASS.json').exists() for r in runs_for('first'))
    if batch=='optional':
        assert all((root_of(r)/'post_PASS.json').exists() for r in runs_for('remaining'))
    return selection['selected_lambda']

def mark_stop(run,attempt,reason):
    STOP.set();save(OUT/'checks/full_STOP.json',dict(run=run,attempt=attempt,reason=reason,at=now(),scientific_verdict=None))

def post(r,gpu,unit):
    # Both normal and virtual TSDF extraction use the same process-wide lock.
    for mode in ['post','run']:
        entry=['/repo/scripts/phd/main_losstrain_v1/gpu_post.py',mode,r['site'],unit.name,r['prior']]
        command=P.docker('jbgs-lt-post-'+str(gpu),gpu,'r17',r['site'],entry)
        image=command.index(P.IMG)
        command[image:image]=['-v',f'{P.S0}:/s0:ro','-v',f'{P.DR}:/dr:ro',
            '-v',f'{OUT}/runs:/out/stage1','-v',f'{P.S1}/defs:/out/defs:ro']
        command[2:2]=['--memory','48g'];save(unit/(mode+'_command.json'),command)
        for attempt in [0,1]:
            waited=time.monotonic();logpath=unit/f'{mode}_attempt_{attempt}.log'
            with TSDF:
                wait=time.monotonic()-waited;start=time.monotonic()
                with logpath.open('w') as log:rc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
            save(unit/f'{mode}_attempt_{attempt}_receipt.json',dict(exit_code=rc,seconds=time.monotonic()-start,tsdf_queue_seconds=wait,at=now(),scientific_verdict=None))
            if not rc:break
            oom='out of memory' in logpath.read_text().lower()
            if oom and attempt==0:
                folder=unit/('post' if mode=='post' else 'gpu')
                if folder.exists():folder.rename(unit/(folder.name+'_attempt_0_oom'))
                error_record=unit/(mode+'_oom.json')
                if error_record.exists():error_record.rename(unit/(mode+'_oom_attempt_0.json'))
                continue
            mark_stop(r,attempt,'postprocessing '+mode+(' OOM twice: NO RESULT' if oom else ' execution error'));return False
    save(unit/'post_PASS.json',dict(at=now(),scientific_verdict=None));return True

def run(r,gpu,lam):
    if STOP.is_set():return
    unit=root_of(r);unit.mkdir(parents=True,exist_ok=False)
    for attempt in [0,1]:
        sub=unit/f'attempt_{attempt}';sub.mkdir()
        mode,vprior=MODES[r['variant']]
        args=P.train_args(r['site'],r['prior'],P.to_container(sub/'model'),sw_off=['judgment'])
        args+=['--jbgs_sw_depth_loss',mode,'--jbgs_vfile_dir',f"/o/direct_stage1_v2/{r['site']}__{r['prior']}",
            '--jbgs_vfile_vprior',vprior,'--jbgs_depth_lambda',str(lam),'--jbgs_lt_monitor','1',*P.RECORDS]
        command=P.docker('jbgs-lt-full-'+str(gpu),gpu,'r17',r['site'],['train.py',*args]);command[2:2]=['--memory','48g']
        save(sub/'command.json',command);start=time.monotonic();stamp=now();peak=0.
        with (sub/'run.log').open('w') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            while process.poll() is None:
                q=subprocess.run(['nvidia-smi','-i',str(gpu),'--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
                try:peak=max(peak,float(q.stdout.strip()))
                except ValueError:pass
                time.sleep(5)
        rc=process.returncode
        save(sub/'receipt.json',dict(run=r,gpu=gpu,attempt=attempt,exit_code=rc,started_at=stamp,finished_at=now(),seconds=time.monotonic()-start,
            lambda_depth=lam,gpu_peak_total_MiB=peak,config_sha256=sha(REPO/'configs/phd/main_losstrain_v1/losstrain_v1.json'),
            source_sha256={f:sha(P.SRC['r17']/f) for f in ['train.py','jbgs_judgment.py']},scientific_verdict=None))
        print(unit.name,'training exit',rc,flush=True)
        if rc:
            oom=(sub/'model/monitor/oom_record.json').exists() or 'out of memory' in (sub/'run.log').read_text().lower()
            if oom and attempt==0:continue
            mark_stop(r,attempt,'OOM twice: NO RESULT' if oom else 'execution or health error');return
        assert (sub/'model/point_cloud/iteration_30000/point_cloud.ply').is_file()
        save(unit/'PASS.json',dict(attempt=attempt,model=str(sub/'model'),at=now(),scientific_verdict=None))
        post(r,gpu,unit);return

def lane(gpu,runs,lam):
    for r in runs:run(r,gpu,lam)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('batch',choices=['first','remaining','optional']);a=ap.parse_args()
    lam=gates(a.batch);runs=runs_for(a.batch)
    start=OUT/f'checks/batch_{a.batch}_start.json';assert not start.exists()
    save(start,dict(at=now(),runs=runs,lambda_depth=lam,scientific_verdict=None))
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        for f in [pool.submit(lane,g,runs[g::2],lam) for g in [0,1]]:f.result()
    if STOP.is_set():raise SystemExit('full batch stopped; checks/full_STOP.json')
    assert all((root_of(r)/'post_PASS.json').exists() for r in runs)
    save(OUT/f'checks/batch_{a.batch}_PASS.json',dict(at=now(),completed=len(runs),scientific_verdict=None))
