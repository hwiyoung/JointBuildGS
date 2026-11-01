"""Host-only queue: immutable prepared inputs -> CPU verification -> no-training GPU gate."""
import concurrent.futures as futures
import datetime as dt
import json,os,subprocess,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
OUT=REPO.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
QUEUE=OUT/'r2/preflight_queue';SCRIPTS=REPO/'scripts/phd/main_target_v1'
ENTRIES=[('B173nb_b10','ALS'),('B173nb_b10','LoD2'),('R1rep_b10','LoD2'),('B0_b10','LoD2')]

def stamp():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def run_one(site,prior,gpu):
    root=QUEUE/f'{site}_{prior}';root.mkdir(exist_ok=False)
    env=dict(os.environ,TARGET_LANE=f'preflight-inputs-{site}-{prior}',IMG='jointbuildgs:geogs-conf-guided-v1',MEM='12',CPUS='4')
    commands=[]
    for mode in ['prepare','verify']:
        commands.append(['bash',str(SCRIPTS/'run_cpu.sh'),f'{mode}-{site}-{prior}-r2','stage1_one_prior_r2.py',mode,site,prior])
    commands.append(['python',str(SCRIPTS/'run_gpu_preflight_r2.py'),str(gpu),site,prior])
    dump(root/'commands.json',commands);t=time.time()
    with (root/'run.log').open('x') as log:
        for index,command in enumerate(commands):
            rc=subprocess.run(command,cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
            if rc:
                result=dict(at=stamp(),status='STOP_EXECUTION_ERROR',step=index,exit_code=rc,training_steps=0,scientific_verdict=None)
                dump(root/'receipt.json',result);return result
        initial=json.loads((OUT/'r2/preflight'/f'{site}_{prior}'/'initial_render.json').read_text())
        diagnostic_rc=None
        if initial['status']!='PASS':
            command=['python',str(SCRIPTS/'run_gpu_preflight_r2.py'),str(gpu),site,prior,'diagnose']
            dump(root/'diagnostic_command.json',command)
            diagnostic_rc=subprocess.run(command,cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
        result=dict(at=stamp(),site=site,prior=prior,gpu=gpu,status=initial['status'],median_m=initial['pooled_median_m'],
            diagnostic_exit_code=diagnostic_rc,seconds=time.time()-t,training_steps=0,scientific_verdict=None)
        dump(root/'receipt.json',result);return result

def main():
    QUEUE.mkdir(exist_ok=False)
    pending=list(ENTRIES);running={};completed=[]
    with futures.ThreadPoolExecutor(max_workers=2) as executor:
        while pending or running:
            for future,(gpu,entry) in list(running.items()):
                if future.done():
                    result=future.result();completed.append(result);del running[future]
                    print('PREFLIGHT_QUEUE_COMPLETE',entry,result,flush=True)
            free=[g for g in [0,1] if g not in [v[0] for v in running.values()]]
            for entry in list(pending):
                if not free:break
                site,prior=entry
                if not (OUT/'r2/background'/site/prior/'receipt.json').exists():continue
                assert (OUT/'r2/stage1'/f'{site}_{prior}'/'maps/index.json').exists()
                gpu=free.pop(0);running[executor.submit(run_one,site,prior,gpu)]=(gpu,entry);pending.remove(entry)
                print('PREFLIGHT_QUEUE_START',entry,gpu,flush=True)
            dump(QUEUE/'status.json',dict(at=stamp(),pending=pending,running=[dict(gpu=g,entry=e) for g,e in running.values()],
                completed=completed,training_steps=0,scientific_verdict=None))
            if pending or running:time.sleep(10)
    print('PREFLIGHT_QUEUE_FINISHED',flush=True)

if __name__=='__main__':main()
