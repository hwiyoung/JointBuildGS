"""Scoped host orchestration adapted from FINALTRAIN gpu_job.py."""
import datetime as dt,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];ART=R.parent/'JointBuildGS-artifacts';PH=ART/'phase-payloads/phd'
O=PH/'main_release_v1/PHD-MAIN-RELEASE-v1';C=R/'configs/phd/main_release_v1';D=R/'docs/experiments/phd/main_release_v1'
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def command(gpu,name,script,args=(),fork='GeoGS-conf-guided-v1-r24',site='R1rep_b10'):
    cfg=json.loads((C/'release_v1.json').read_text());image=cfg['docker_images']['jointbuildgs:geogs-conf-guided-v1']
    cmd=['docker','run','--rm','--read-only','--network','none','--name',name,'--gpus',f'device={gpu}',
      '--user',f'{os.getuid()}:{os.getgid()}','--cpus','8','--memory','40g','--memory-swap','40g','--shm-size','4g']
    for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=4','OPENBLAS_NUM_THREADS=1',
      'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True',f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{site}/split.json',
      'TMPDIR=/release/tmp','MPLCONFIGDIR=/release/tmp/mpl','XDG_CACHE_HOME=/release/tmp/cache','TORCH_HOME=/weights/torch','TZ=Asia/Seoul']:
        cmd+=['-e',e]
    mounts=[(R,'/repo','ro'),(ART,'/art','ro'),(ART,'/artifacts/JointBuildGS','ro'),(PH,'/ph','ro'),
      (PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1','/out','ro'),(O,'/release','rw'),(C,'/cfg','ro'),(D,'/docs','rw'),
      (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/p','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0','ro'),
      (R/'src/phd/forks'/fork,'/source','ro'),(PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights','/weights','ro')]
    for src,dst,mode in mounts:cmd+=['-v',f'{src}:{dst}:{mode}']
    if script in ['unit_probe.py','unit_rules.py']:cmd+=['-e','CUBLAS_WORKSPACE_CONFIG=:4096:8']
    return cmd+['-w','/source','--entrypoint','python',image,'-B','-u',f'/repo/scripts/phd/main_release_v1/{script}',*args]
def probe():
    for label,fork in [('r23','GeoGS-conf-guided-v1-r23'),('r24_off','GeoGS-conf-guided-v1-r24'),('r24_on','GeoGS-conf-guided-v1-r24')]:
        subprocess.run(command(0,'jbgs-release-probe-'+label,'unit_probe.py',[label],fork=fork),check=True)
    subprocess.run(command(0,'jbgs-release-unit','unit_rules.py'),check=True)
def train(gpu,site,prior,rule='release',stage=2):
    stage=int(stage);assert {'0':'ALS','1':'LoD2'}[str(gpu)]==prior
    assert json.loads((O/'verification/unit_default.json').read_text())['status']=='PASS'
    if stage==3:
        assert json.loads((O/'verification/unit_rules.json').read_text())['status']=='PASS'
        gate=json.loads((D/'단계3_판정.json').read_text());assert gate['stage3_authorized'] is True
        subprocess.run(['git','ls-files','--error-unmatch','docs/experiments/phd/main_release_v1/단계3_판정.json'],cwd=R,check=True,stdout=subprocess.DEVNULL)
    name=f'rlog_{prior}_s0' if stage==2 else f'rl_{rule}_{prior}_s0';run=O/'runs'/site/name;run.mkdir(parents=True,exist_ok=False)
    stop=15000 if stage==2 else 30000;attempts=[]
    for attempt in [1,2]:
        root=run/f'attempt{attempt}';root.mkdir();model='/release/'+str((root/'model').relative_to(O))
        args=[site,prior,'-s',f'/p/fork_inputs/s61/{site}/scene_{prior}','-m',model,'--eval','-r','1','--data_device','cpu',
          '--lod_depth_path','/p/fork_none','--da_depth_path','/p/fork_none','--stage_switch_iter','0','--lambda_lod_init','0','--lambda_lod_anchor','0','--lambda_da_depth','0',
          '--jbgs_judgment','off','--jbgs_target','on','--jbgs_target_rev','r8','--jbgs_finaltrain','on',
          '--jbgs_release_rule',rule,'--jbgs_release_log','on','--jbgs_capture_iterations','7000','15000','30000',
          '--jbgs_target_dir',f'/art/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1/{site}__{prior}',
          '--jbgs_target_lambda','.05','--jbgs_seed','0','--iterations','30000','--jbgs_stop_after',str(stop),
          '--test_iterations','7000','15000','30000','--save_iterations','7000','15000','30000']
        cmd=command(gpu,f'jbgs-release-{site}-{name}-a{attempt}','train_entry.py',args,site=site)
        dump(root/'command.json',cmd);dump(root/'launch.json',dict(at=now(),gpu=gpu,stage=stage,site=site,prior=prior,rule=rule,scientific_verdict=None));start=time.monotonic()
        with (root/'train.log').open('x') as log:rc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
        hp=root/'model/target_monitor/STOP.json';health=json.loads(hp.read_text()) if hp.exists() else None
        status=f'COMPLETED_{stop}' if rc==0 and (root/'TRAINING_COMPLETE.json').exists() else ('HEALTH_STOP' if health else 'EXECUTION_ERROR')
        rec=dict(at=now(),attempt=attempt,exit_code=rc,seconds=time.monotonic()-start,status=status,health=health,model=model,scientific_verdict=None)
        dump(root/'receipt.json',rec);attempts.append(rec)
        if status!='EXECUTION_ERROR':break
    dump(run/'receipt.json',dict(at=now(),site=site,prior=prior,rule=rule,stage=stage,status=attempts[-1]['status'] if attempts[-1]['status']!='EXECUTION_ERROR' else 'NO_RESULT',attempts=attempts,scientific_verdict=None))
if __name__=='__main__':
    if sys.argv[1]=='probe':probe()
    else:train(*sys.argv[2:])
