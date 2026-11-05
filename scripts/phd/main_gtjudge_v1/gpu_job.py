"""FINALTRAIN Docker launch and one same-settings retry, with the new target flags."""
import json,os,subprocess,sys,time,datetime as dt
from pathlib import Path
R=Path(__file__).resolve().parents[3];ART=R.parent/'JointBuildGS-artifacts';PH=ART/'phase-payloads/phd'
O=PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1';C=R/'configs/phd/main_gtjudge_v1';D=R/'docs/experiments/phd/main_gtjudge_v1'
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def command(gpu,name,script,args=(),site='R1rep_b10'):
    config=json.loads((C/'gtjudge_v1.json').read_text());image=config['docker_images']['jointbuildgs:geogs-conf-guided-v1']
    cmd=['docker','run','--rm','--read-only','--network','none','--name',name,'--gpus',f'device={gpu}',
        '--user',f'{os.getuid()}:{os.getgid()}','--cpus','8','--memory','40g','--memory-swap','40g','--shm-size','4g']
    for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=4','OPENBLAS_NUM_THREADS=1',
        'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True',f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{site}/split.json',
        'TMPDIR=/gtjudge/tmp','MPLCONFIGDIR=/gtjudge/tmp/mpl','XDG_CACHE_HOME=/gtjudge/tmp/cache','TORCH_HOME=/weights/torch','TZ=Asia/Seoul']:
        cmd+=['-e',e]
    mounts=[(R,'/repo','ro'),(ART,'/art','ro'),(ART,'/artifacts/JointBuildGS','ro'),(PH,'/ph','ro'),
        (PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1','/out','ro'),(O,'/gtjudge','rw'),(C,'/cfg','rw'),(D,'/docs','rw'),
        (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/p','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0','ro'),
        (R/'src/phd/forks/GeoGS-conf-guided-v1-r25','/source','ro'),
        (PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights','/weights','ro')]
    for src,dst,mode in mounts:cmd+=['-v',f'{src}:{dst}:{mode}']
    return cmd+['-w','/source','--entrypoint','python',image,'-B','-u',f'/repo/scripts/phd/main_gtjudge_v1/{script}',*map(str,args)]

def train(gpu,site,prior,arm):
    stem=f'{site}__{prior}';name=f'{"gt" if arm=="A1" else "gtfs"}_{prior}_s0';run=O/'runs'/site/name
    if (run/'receipt.json').exists():return json.loads((run/'receipt.json').read_text())
    run.mkdir(parents=True,exist_ok=True)
    preflight=O/'verification'/f'loaded_{stem}.json'
    if not preflight.exists():
        with (O/'logs'/f'initialize-{stem}.log').open('w') as log:
            rc=subprocess.run(command(gpu,'jbgs-gtjudge-init-'+stem,'initialize_gt.py',[site,prior],site),stdout=log,stderr=subprocess.STDOUT).returncode
        if rc:
            rec=dict(at=now(),site=site,prior=prior,arm=arm,status='NO_RESULT_UNIT_CHECK_FAILED',scientific_verdict=None)
            dump(run/'receipt.json',rec);return rec
    assert json.loads(preflight.read_text())['status']=='PASS'
    attempts=[]
    for attempt in [1,2]:
        root=run/f'attempt{attempt}';root.mkdir(exist_ok=True);model='/gtjudge/'+str((root/'model').relative_to(O))
        if (root/'receipt.json').exists():
            receipt=json.loads((root/'receipt.json').read_text());attempts.append(receipt)
            if receipt['status'] in ['TRAINING_COMPLETE_30000','HEALTH_STOP']:break
            continue
        args=[site,prior,'-s',f'/p/fork_inputs/s61/{site}/scene_{prior}','-m',model,'--eval','-r','1','--data_device','cpu',
            '--lod_depth_path','/p/fork_none','--da_depth_path','/p/fork_none','--stage_switch_iter','0',
            '--lambda_lod_init','0','--lambda_lod_anchor','0','--lambda_da_depth','0','--jbgs_judgment','off',
            '--jbgs_target','on','--jbgs_target_rev','r8','--jbgs_finaltrain','on','--jbgs_targets',f'/gtjudge/targets_gt/{stem}.npz',
            '--jbgs_preserve_freespace','on' if arm=='A2' else 'off',
            '--jbgs_capture_iterations','7000','15000','30000','--jbgs_target_dir',f'/gtjudge/stage1/{stem}',
            '--jbgs_target_lambda','.05','--jbgs_seed','0','--iterations','30000','--test_iterations','7000','15000','30000',
            '--save_iterations','7000','15000','30000']
        cmd=command(gpu,f'jbgs-gtjudge-{site}-{prior}-{arm}-a{attempt}','train_entry.py',args,site)
        dump(root/'command.json',cmd);dump(root/'launch.json',dict(at=now(),gpu=gpu,site=site,prior=prior,arm=arm,scientific_verdict=None))
        start=time.monotonic()
        with (root/'train.log').open('w') as log:rc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
        stop=root/'model/target_monitor/STOP.json';health=json.loads(stop.read_text()) if stop.exists() else None
        status='TRAINING_COMPLETE_30000' if rc==0 and (root/'TRAINING_COMPLETE.json').exists() else 'HEALTH_STOP' if health else 'EXECUTION_ERROR'
        receipt=dict(at=now(),attempt=attempt,status=status,model=model,exit_code=rc,seconds=time.monotonic()-start,health=health,scientific_verdict=None)
        dump(root/'receipt.json',receipt);attempts.append(receipt)
        if status in ['TRAINING_COMPLETE_30000','HEALTH_STOP']:break
    final=dict(at=now(),site=site,prior=prior,arm=arm,status=attempts[-1]['status'] if attempts[-1]['status']!='EXECUTION_ERROR' else 'NO_RESULT',attempts=attempts,scientific_verdict=None)
    dump(run/'receipt.json',final);return final
if __name__=='__main__':print(json.dumps(train(*sys.argv[1:]),ensure_ascii=False))
