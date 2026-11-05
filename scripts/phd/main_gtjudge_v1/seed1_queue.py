"""Optional four exact-parent seed-1 repeats after all 12 diagnostic arms finish."""
import sys,json,subprocess,hashlib,time,concurrent.futures,threading
from pathlib import Path
from gpu_job import R,PH,O,C,D,command,dump,now
from cpu_queue import cpu,mesh
from publish_add1 import sha,csvwrite
SITE='B173nb_b10';post_lock=threading.Lock()
def freeze():
    path=C/'seed1.add1.lock.json'
    if path.exists():return
    files={}
    for fork in ['r23','r15']:
        for p in (R/'src/phd/forks'/('GeoGS-conf-guided-v1-'+fork)).rglob('*.py'):files['/repo/'+str(p.relative_to(R))]=sha(p)
    for name in ['seed1_entry.py','seed1_monitor.py','seed1_queue.py']:
        p=R/'scripts/phd/main_gtjudge_v1'/name;files['/repo/'+str(p.relative_to(R))]=sha(p)
    dump(path,dict(at=now(),seed=1,files=files,scientific_verdict=None))
def replay(gpu,prior,family):
    name=f'seed1_{family}_{prior}';run=O/'runs'/SITE/name;run.mkdir(parents=True,exist_ok=True)
    if (run/'receipt.json').exists():return json.loads((run/'receipt.json').read_text())
    parent=PH/('main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1' if family=='ft' else 'main_stage3_v1/PHD-MAIN-STAGE3-v1')/'runs'/SITE/(f'ft_{prior}_s0' if family=='ft' else f'nojudge_{prior}_s0')
    src=parent/'attempt1/command.json' if family=='ft' else parent/'receipt.json'
    original=json.loads(src.read_text());original=original if family=='ft' else original['command'];args=original[original.index('-s'):];args[args.index('--jbgs_seed')+1]='1'
    if family=='ft':args[args.index('--jbgs_target_dir')+1]=f'/art/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1/{SITE}__{prior}'
    else:
        for flag in ['--save_iterations','--jbgs_snapshot_iterations']:
            i=args.index(flag)+1;j=i
            while j<len(args) and not args[j].startswith('--'):j+=1
            args[i:j]=list(map(str,sorted(set(map(int,args[i:j]))|{7000,15000,30000})))
    attempts=[]
    for attempt in [1,2]:
        root=run/f'attempt{attempt}';root.mkdir(exist_ok=True);model='/gtjudge/'+str((root/'model').relative_to(O));args[args.index('-m')+1]=model
        cmd=command(gpu,'jbgs-gtjudge-'+name+'-a'+str(attempt),'seed1_entry.py',[family,*args],SITE)
        fork='r23' if family=='ft' else 'r15';cmd=[x.replace('GeoGS-conf-guided-v1-r25:/source:ro','GeoGS-conf-guided-v1-'+fork+':/source:ro') for x in cmd]
        dump(root/'command.json',cmd);dump(root/'parent.json',dict(path=str(src),sha256=sha(src),changes=['seed=1','output path','state saves 7000/15000/30000','read-only health hook for baseline'],scientific_verdict=None));start=time.monotonic()
        with (root/'train.log').open('w') as log:rc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
        stop=root/'model/target_monitor/STOP.json';status='TRAINING_COMPLETE_30000' if rc==0 and (root/'TRAINING_COMPLETE.json').exists() else 'HEALTH_STOP' if stop.exists() else 'EXECUTION_ERROR'
        rec=dict(at=now(),attempt=attempt,status=status,model=model,seconds=time.monotonic()-start,exit_code=rc,scientific_verdict=None);dump(root/'receipt.json',rec);attempts.append(rec)
        if status!='EXECUTION_ERROR':break
    rec=dict(site=SITE,prior=prior,family=family,seed=1,status=attempts[-1]['status'],attempts=attempts,scientific_verdict=None);dump(run/'receipt.json',rec)
    if rec['status']=='TRAINING_COMPLETE_30000':
        method='seed1_'+family;ply=attempts[-1]['model']+'/point_cloud/iteration_30000/point_cloud.ply'
        for attempt in [1,2]:
            with (O/'logs'/f'render-{name}-{attempt}.log').open('w') as log:rc=subprocess.run(command(gpu,'jbgs-gtjudge-render-'+name,'mesh_job.py',[SITE,prior,method,'render',ply],SITE),stdout=log,stderr=subprocess.STDOUT).returncode
            if rc==0:break
        if rc==0:
            with post_lock:
                if mesh(SITE,prior,method):cpu('score-'+name,'score_new.py',SITE,prior,method);cpu('metrics-'+name,'collect.py',SITE,prior)
    return rec
def main():
    freeze();gpurows=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid','--format=csv,noheader'],text=True).splitlines()
    busy=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True).splitlines();free=[int(r.split(',')[0]) for r in gpurows if r.split(',')[1].strip() not in busy]
    if not free:dump(O/'queue/stage4.json',dict(status='OPTIONAL_SKIPPED_GPU_BUSY',scientific_verdict=None));return
    def lane(gpu,prior):return [replay(gpu,prior,family) for family in ['ft','base']]
    if len(free)>=2:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=[f.result() for f in [pool.submit(lane,free[0],'ALS'),pool.submit(lane,free[1],'LoD2')]]
    else:results=[lane(free[0],p) for p in ['ALS','LoD2']]
    combined=[]
    for prior in ['ALS','LoD2']:
        p=D/'tables/stage1'/f'{SITE}__{prior}_metrics.json'
        if p.exists():combined += [r for r in json.loads(p.read_text())['rows'] if r['method'] in ['FINALTRAIN_30000','baseline_30000','seed1_ft','seed1_base']]
    csvwrite(D/'tables/stage4/seed_comparison.csv',combined);dump(O/'queue/stage4.json',dict(status='FINISHED',runs=results,scientific_verdict=None))
if __name__=='__main__':main()
