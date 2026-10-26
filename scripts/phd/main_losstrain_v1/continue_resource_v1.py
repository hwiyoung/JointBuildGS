"""Authorized 24-arm continuation: independent GPU training and serial post/score.
Host stdlib orchestrator only; all project computation remains in Docker.
Historical STOP files are immutable. Resource failures are not training stops.
"""
import argparse
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import train_full as F
from post_admission import memory_available_gib

P,OUT,REPO=F.P,F.OUT,F.REPO
ROOT=OUT/'checks/resource_resume_v1'
RUNS=F.runs_for('first')+F.runs_for('remaining')

def save(p,d):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n');temp.replace(p)

def read(p,default=None):return json.loads(p.read_text()) if p.exists() else default

def training_args(r,model,lam):
    mode,validity=F.MODES[r['variant']];key=r['site']+'__'+r['prior']
    return P.train_args(r['site'],r['prior'],model,sw_off=['judgment'])+[
        '--jbgs_sw_depth_loss',mode,'--jbgs_vfile_dir','/o/direct_stage1_v2/'+key,
        '--jbgs_vfile_vprior',validity,'--jbgs_depth_lambda',str(lam),
        '--jbgs_lt_monitor','1','--jbgs_lt_monitor_v2','1',
        '--jbgs_lt_nojudge_inventory','/o/checks/monitor_v2/nojudge/'+key+'.json',
        '--jbgs_lt_diagnostic_cells','/o/direct_stage1_v2/'+key+'/evaluation.npz',*P.RECORDS]

def binding():
    return dict(source_sha256={p:F.sha(P.SRC['r17']/p) for p in ['train.py','jbgs_judgment.py']},
        config_sha256=F.sha(REPO/'configs/phd/main_losstrain_v1/losstrain_v1.json'))

def train(r,gpu,lam):
    unit=F.root_of(r);assert not unit.exists(),f'refuse repeat training {unit}'
    sub=unit/'attempt_0';sub.mkdir(parents=True)
    command=P.docker('jbgs-lt-resume-train-'+str(gpu),gpu,'r17',r['site'],['train.py',*training_args(r,P.to_container(sub/'model'),lam)])
    command[2:2]=['--memory','48g'];bound=binding()
    save(sub/'start_binding.json',dict(**bound,at=F.now(),scientific_verdict=None));save(sub/'command.json',command)
    start=time.monotonic();stamp=F.now();peak=0.
    with (sub/'run.log').open('w') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        while process.poll() is None:
            q=subprocess.run(['nvidia-smi','-i',str(gpu),'--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
            try:peak=max(peak,float(q.stdout.strip()))
            except ValueError:pass
            time.sleep(5)
    rc=process.returncode
    save(sub/'receipt.json',dict(run=r,gpu=gpu,attempt=0,exit_code=rc,started_at=stamp,finished_at=F.now(),
        seconds=time.monotonic()-start,gpu_peak_total_MiB=peak,lambda_depth=lam,**bound,scientific_verdict=None))
    if rc:
        save(ROOT/'training_STOP.json',dict(at=F.now(),run=r,exit_code=rc,attempt=0,reason='training execution/health error',scientific_verdict=None))
        return False
    assert (sub/'model/point_cloud/iteration_30000/point_cloud.ply').is_file()
    save(unit/'PASS.json',dict(attempt=0,model=str(sub/'model'),at=F.now(),monitor_policy='v2',scientific_verdict=None))
    print('TRAIN PASS',r,flush=True);return True

def next_post_mode(unit):
    if (unit/'post_PASS.json').exists():return None
    return 'run' if (unit/'post_stage_PASS.json').exists() else 'post'

def next_attempt(unit,mode):
    paths=list(unit.glob(mode+'_attempt_*_receipt.json'))
    return 1+max((int(p.name.split('_attempt_')[1].split('_')[0]) for p in paths),default=-1)

def resource_evidence(command,rc,log,cidfile,start_epoch):
    cid=cidfile.read_text().strip() if cidfile.exists() else None
    ev=''
    if cid:
        ev=subprocess.run(['docker','events','--since',str(int(start_epoch)-1),'--until',str(int(time.time())+1),
            '--filter','container='+cid,'--format','{{json .}}'],capture_output=True,text=True).stdout
    logtext=log.read_text(errors='replace')
    oom_event=any(json.loads(s).get('Action')=='oom' for s in ev.splitlines() if s.strip())
    kernel=subprocess.run(['journalctl','-k','--since','@'+str(int(start_epoch)), '--no-pager'],capture_output=True,text=True).stdout if rc else ''
    lines=[x for x in kernel.splitlines() if cid and cid in x]
    resource=bool(oom_event or any(s in logtext.lower() for s in ['out of memory','cannot allocate memory','no space left on device']) or (rc==137 and lines))
    return dict(resource_failure=resource,container_id=cid,docker_events=[json.loads(s) for s in ev.splitlines() if s.strip()],
        kernel_container_lines=lines,classification='RESOURCE' if resource else 'EXECUTION' if rc else 'PASS')

def post_one(r,gpu):
    unit=F.root_of(r);mode=next_post_mode(unit);attempt=next_attempt(unit,mode)
    log=unit/f'{mode}_attempt_{attempt}.log';assert not log.exists()
    folder=unit/('post' if mode=='post' else 'gpu')
    if folder.exists():
        preserved=unit/(folder.name+f'_before_resource_attempt_{attempt}')
        assert not preserved.exists();folder.rename(preserved)
    for name in [mode+'_oom.json',mode+'_resource_admission.json']:
        p=unit/name
        if p.exists():p.rename(unit/(p.stem+f'_before_attempt_{attempt}'+p.suffix))
    entry=['/repo/scripts/phd/main_losstrain_v1/gpu_post.py',mode,r['site'],unit.name,r['prior']]
    command=P.docker('jbgs-lt-resume-post-'+str(gpu),gpu,'r17',r['site'],entry);idx=command.index(P.IMG)
    command[idx:idx]=['-v',f'{P.S0}:/s0:ro','-v',f'{P.DR}:/dr:ro','-v',f'{OUT}/runs:/out/stage1','-v',f'{P.S1}/defs:/out/defs:ro']
    cidfile=unit/f'{mode}_attempt_{attempt}.cid';assert not cidfile.exists()
    command[2:2]=['--memory','48g','--cidfile',str(cidfile)]
    save(unit/f'{mode}_attempt_{attempt}_command.json',command)
    with (OUT/'checks/tsdf.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        start=time.monotonic();epoch=time.time()
        with log.open('w') as f:rc=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT).returncode
    evidence=resource_evidence(command,rc,log,cidfile,epoch)
    receipt=dict(exit_code=rc,seconds=time.monotonic()-start,at=F.now(),policy='resource_resume_v1',
        memory_limit_GiB=48,admission_available_GiB=64,admission_stable_seconds=60,**evidence,scientific_verdict=None)
    save(unit/f'{mode}_attempt_{attempt}_receipt.json',receipt)
    if rc:
        records=[read(p) for p in unit.glob(mode+'_attempt_*_receipt.json')]
        failures=sum(x.get('policy')=='resource_resume_v1' and x['exit_code']!=0 for x in records)
        final=not evidence['resource_failure'] or failures>=3
        event=dict(at=F.now(),run=r,stage=mode,attempt=attempt,failures_under_same_memory_policy=failures,
            autonomous_retries_used=max(0,failures-1),training_stop_increment=0,final=final,receipt=receipt,scientific_verdict=None)
        save(unit/f'{mode}_resource_failure_{attempt}.json',event)
        if final:save(ROOT/'post_STOP.json',event)
        print('POST FAIL',r,mode,attempt,evidence['classification'],flush=True)
        return not final
    save(unit/(mode+'_stage_PASS.json'),dict(at=F.now(),attempt=attempt,policy='resource_resume_v1',scientific_verdict=None))
    if mode=='run':save(unit/'post_PASS.json',dict(at=F.now(),policy='resource_resume_v1',scientific_verdict=None))
    print('POST PASS',r,mode,attempt,flush=True);return True

def measure(r):
    unit=F.root_of(r)
    command=['python3',str(REPO/'scripts/phd/main_losstrain_v1/measure_run.py'),r['site'],r['prior'],unit.name]
    tag=(r['site']+'-'+r['prior']+'-'+unit.name).lower().replace('_','-')
    for attempt in range(3):
        start=time.time();log=unit/f'measure_resource_resume_{attempt}.log'
        assert not log.exists()
        if attempt:
            history=unit/f'measure_before_resource_retry_{attempt}';history.mkdir()
            for p in [*unit.glob('measure_*.log'),unit/'measure_progress.json']:
                if p.exists() and p!=log:p.rename(history/p.name)
        with log.open('w') as f:rc=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT).returncode
        if rc==0:return True
        events=[]
        for name in ['jbgs-lt-'+tag+'-mesh','jbgs-lt-'+tag+'-fates','jbgs-lt-axes-'+tag+'-axes']:
            text=subprocess.run(['docker','events','--since',str(int(start)-1),'--until',str(int(time.time())+1),
                '--filter','container='+name,'--format','{{json .}}'],capture_output=True,text=True).stdout
            events.extend(json.loads(x) for x in text.splitlines() if x.strip())
        logs=log.read_text(errors='replace')+'\n'+'\n'.join(p.read_text(errors='replace') for p in unit.glob('measure_*.log'))
        resource=any(x.get('Action')=='oom' for x in events) or any(x in logs.lower() for x in ['out of memory','cannot allocate memory','no space left on device'])
        event=dict(at=F.now(),run=r,attempt=attempt,exit_code=rc,resource_failure=resource,docker_events=events,
            training_stop_increment=0,scientific_verdict=None)
        save(unit/f'measure_resource_failure_{attempt}.json',event)
        if not resource or attempt==2:
            save(ROOT/'measure_STOP.json',event);return False
        # Repeat only under the approved resource condition; no score/settings change.
        stable=None
        while True:
            if memory_available_gib()<64:stable=None
            elif stable is None:stable=time.monotonic()
            if stable is not None and time.monotonic()-stable>=60:break
            time.sleep(10)
    return False

def validate():
    F.C.gates();a=read(ROOT/'approval.json');assert a['status']=='AUTHORIZED'
    assert len(RUNS)==24 and len({str(F.root_of(r)) for r in RUNS})==24
    old=read(OUT/'runs/B173nb_b10/lt_dyngt_ALS_s0/attempt_3/command.json')
    k=old.index('train.py');oldargs=old[k+1:]
    sample=dict(site='B173nb_b10',prior='ALS',variant='lt_dyngt')
    assert oldargs==training_args(sample,oldargs[oldargs.index('--model_path')+1] if '--model_path' in oldargs else oldargs[oldargs.index('-m')+1],.0025)
    ref=read(OUT/'checks/monitor_v2/camera_fix/validation.json')
    assert ref['status']=='PASS'
    assert all(F.sha(P.SRC['r17']/p)==h for p,h in ref['source_sha256'].items())
    for r in RUNS:
        unit=F.root_of(r)
        assert not unit.exists() or (unit/'PASS.json').exists(),str(unit)
    result=dict(status='PASS',at=F.now(),training_arguments_identical=True,r17_source_unchanged=True,
        required_runs=24,completed_training_reused=sum((F.root_of(r)/'PASS.json').exists() for r in RUNS),
        post_minimum_available_GiB=64,post_stable_seconds=60,resource_retries=2,scientific_verdict=None)
    save(ROOT/'validation.json',result);print(json.dumps(result),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--validate-only',action='store_true');a=ap.parse_args()
    if a.validate_only:validate();return
    assert read(ROOT/'validation.json')['status']=='PASS' and (ROOT/'commit.json').exists()
    with (ROOT/'orchestrator.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (ROOT/'start.json').exists(),'do not double launch'
        save(ROOT/'start.json',dict(at=F.now(),pid=os.getpid(),runs=RUNS,scientific_verdict=None))
        pending=[r for r in RUNS if not (F.root_of(r)/'PASS.json').exists()]
        futures={};cpu=None;stable_since=None
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            while True:
                for gpu,item in list(futures.items()):
                    future,kind,r=item
                    if future.done():
                        try:future.result()
                        except Exception as e:
                            save(ROOT/(kind+'_STOP.json'),dict(at=F.now(),run=r,error=repr(e),scientific_verdict=None))
                        del futures[gpu]
                if cpu and cpu[0].done():
                    try:cpu[0].result()
                    except Exception as e:save(ROOT/'measure_STOP.json',dict(at=F.now(),error=repr(e),scientific_verdict=None))
                    cpu=None
                mem=memory_available_gib()
                if mem<64:stable_since=None
                elif stable_since is None:stable_since=time.monotonic()
                stable=0 if stable_since is None else time.monotonic()-stable_since
                post_active=any(x[1]=='post' for x in futures.values())
                post_pending=[r for r in RUNS if (F.root_of(r)/'PASS.json').exists() and not (F.root_of(r)/'post_PASS.json').exists()]
                for gpu in [0,1]:
                    if gpu in futures:continue
                    if post_pending and not post_active and cpu is None and stable>=60 and not (ROOT/'post_STOP.json').exists():
                        r=post_pending[0];futures[gpu]=(pool.submit(post_one,r,gpu),'post',r);post_active=True;stable_since=None
                    elif pending and not (ROOT/'training_STOP.json').exists():
                        r=pending.pop(0);futures[gpu]=(pool.submit(train,r,gpu,.0025),'training',r)
                measurable=[r for r in RUNS if (F.root_of(r)/'post_PASS.json').exists() and not (F.root_of(r)/'measure_PASS.json').exists()]
                if cpu is None and measurable and not post_active and not (ROOT/'measure_STOP.json').exists():
                    r=measurable[0];cpu=(pool.submit(measure,r),r)
                counts=dict(training_complete=sum((F.root_of(r)/'PASS.json').exists() for r in RUNS),
                    post_complete=sum((F.root_of(r)/'post_PASS.json').exists() for r in RUNS),
                    measurement_complete=sum((F.root_of(r)/'measure_PASS.json').exists() for r in RUNS))
                stops=[p.name for p in ROOT.glob('*_STOP.json')]
                save(ROOT/'state.json',dict(at=F.now(),status='NEEDS_ATTENTION' if stops else 'RUNNING',**counts,
                    gpu_jobs={str(g):dict(kind=x[1],run=x[2]) for g,x in futures.items()},cpu_measurement=cpu[1] if cpu else None,
                    available_GiB=mem,required_post_GiB=64,stable_seconds=stable,stops=stops,pending_trainings=len(pending),scientific_verdict=None))
                if all((F.root_of(r)/'measure_PASS.json').exists() for r in RUNS[:4]) and not (ROOT/'interim_ready.json').exists():
                    save(ROOT/'interim_ready.json',dict(at=F.now(),status='READY_FOR_REPORT',scientific_verdict=None))
                if counts['measurement_complete']==24:
                    save(ROOT/'PASS.json',dict(at=F.now(),**counts,scientific_verdict=None));break
                if stops and not futures and cpu is None and (not pending or (ROOT/'training_STOP.json').exists()):break
                time.sleep(5)

if __name__=='__main__':main()
