import sys,os,json,time,subprocess,hashlib,threading
from pathlib import Path
from gpu_job import R,O,C,D,PH,now,dump,command,train
LOCK=threading.Lock()
def event(kind,**fields):
    with LOCK:
        p=O/'queue/addendum2/events.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('a') as f:f.write(json.dumps(dict(at=now(),event=kind,**fields),ensure_ascii=False)+'\n')

def cpu(tag,script,*args):
    cmd=['bash',str(R/'scripts/phd/main_gtjudge_v1/run_cpu.sh'),'add2-'+tag,script,*map(str,args)]
    for attempt in [1,2]:
        logfile=O/'logs'/f'add2-host-{tag}-attempt{attempt}.log'
        with logfile.open('w') as f:rc=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT).returncode
        if rc==0:return True
    event('CPU_ERROR',tag=tag,exit_code=rc)
    with (D/'issues.md').open('a') as f:f.write(f'- {now()}: 덧붙임2 {tag} 동일 설정 2회 오류({rc}); 로그 {logfile}. 다른 학습은 계속.\n')
    return False

def mesh(site,prior,family):
    root=O/'meshes'/f'{site}__{prior}__{family}';wd=root/'final_work'
    if (root/'final.json').exists():return True
    for step,sentinel in [('render',O/'renders'/f'{site}__{prior}__{family}'/'receipt.json'),('prepare',wd/'inputs/meta.json'),('plan',wd/'plan/layout.json')]:
        if not sentinel.exists() and not cpu(f'{site}-{prior}-{family}-{step}','add2_mesh.py',site,prior,family,step):return False
    for tile in json.loads((wd/'plan/layout.json').read_text())['tiles']:
        k=tile['k']
        if not (wd/'tiles'/f'tile{k}.json').exists() and not cpu(f'{site}-{prior}-{family}-tile{k}','add2_mesh.py',site,prior,family,f'tile:{k}'):return False
    for step in ['merge','finish']:
        if not cpu(f'{site}-{prior}-{family}-{step}','add2_mesh.py',site,prior,family,step):return False
    return True

def r26_command(gpu,name,script,args,site):
    return [x.replace('GeoGS-conf-guided-v1-r25:/source','GeoGS-conf-guided-v1-r26:/source') for x in command(gpu,name,script,args,site)]

def runtime_lock():
    p=C/'runtime.add2.lock.json'
    if p.exists():return
    source=R/'src/phd/forks/GeoGS-conf-guided-v1-r26';paths=[p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += [R/'scripts/phd/main_gtjudge_v1'/n for n in ['add2_train_entry.py','add2_prepare.py','add2_common.py']]
    dump(p,dict(at=now(),files={'/repo/'+str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},scientific_verdict=None))

def fix_train(gpu,site,prior):
    stem=f'{site}__{prior}';run=O/'runs'/site/f'fix_{prior}_s0';run.mkdir(parents=True,exist_ok=True)
    if (run/'receipt.json').exists():return json.loads((run/'receipt.json').read_text())
    runtime_lock();base=O/'addendum2/fix_inputs'
    with (O/'logs'/f'add2-initialize-{stem}.log').open('w') as log:
        rc=subprocess.run(r26_command(gpu,'jbgs-gtjudge-init-fix-'+stem,'add2_prepare.py',[site,prior,'initialize'],site),stdout=log,stderr=subprocess.STDOUT).returncode
    if rc:
        rec=dict(at=now(),site=site,prior=prior,arm='fix',status='NO_RESULT_UNIT_CHECK_FAILED',attempts=[],scientific_verdict=None);dump(run/'receipt.json',rec);return rec
    ready=json.loads((base/'ready'/f'{stem}.json').read_text());attempts=[]
    for attempt in [1,2]:
        root=run/f'attempt{attempt}';root.mkdir(exist_ok=True);model='/gtjudge/'+str((root/'model').relative_to(O))
        if (root/'receipt.json').exists():
            rec=json.loads((root/'receipt.json').read_text());attempts.append(rec)
            if rec['status'] in ['TRAINING_COMPLETE_30000','HEALTH_STOP']:break
            continue
        args=[site,prior,'-s',f'/p/fork_inputs/s61/{site}/scene_{prior}','-m',model,'--eval','-r','1','--data_device','cpu','--lod_depth_path','/p/fork_none','--da_depth_path','/p/fork_none','--stage_switch_iter','0','--lambda_lod_init','0','--lambda_lod_anchor','0','--lambda_da_depth','0','--jbgs_judgment','off','--jbgs_target','on','--jbgs_target_rev','r8','--jbgs_finaltrain','on','--jbgs_targets',ready['target'],'--jbgs_preserve_freespace','on','--jbgs_freespace_patches',f'/gtjudge/freespace_targets/{stem}.npz','--jbgs_capture_iterations','7000','15000','30000','--jbgs_target_dir',ready['stage1'],'--jbgs_target_lambda','.05','--jbgs_seed','0','--iterations','30000','--test_iterations','7000','15000','30000','--save_iterations','7000','15000','30000']
        cmd=r26_command(gpu,f'jbgs-gtjudge-{site}-{prior}-fix-a{attempt}','add2_train_entry.py',args,site);dump(root/'command.json',cmd);dump(root/'launch.json',dict(at=now(),gpu=gpu,site=site,prior=prior,arm='fix',scientific_verdict=None))
        start=time.monotonic()
        with (root/'train.log').open('w') as log:rc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
        stop=root/'model/target_monitor/STOP.json';health=json.loads(stop.read_text()) if stop.exists() else None
        status='TRAINING_COMPLETE_30000' if rc==0 and (root/'TRAINING_COMPLETE.json').exists() else 'HEALTH_STOP' if health else 'EXECUTION_ERROR'
        rec=dict(at=now(),attempt=attempt,status=status,model=model,exit_code=rc,seconds=time.monotonic()-start,health=health,scientific_verdict=None);dump(root/'receipt.json',rec);attempts.append(rec)
        if status!='EXECUTION_ERROR':break
    final=dict(at=now(),site=site,prior=prior,arm='fix',status=attempts[-1]['status'] if attempts[-1]['status']!='EXECUTION_ERROR' else 'NO_RESULT',attempts=attempts,scientific_verdict=None);dump(run/'receipt.json',final);return final
