"""Host Docker command construction; no project dependency executes on host."""
import json,os,subprocess,sys,time,hashlib,datetime as dt
from pathlib import Path
R=Path(__file__).resolve().parents[3];ART=R.parent/'JointBuildGS-artifacts';PH=ART/'phase-payloads/phd'
O=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1';C=R/'configs/phd/main_finaltrain_v1';D=R/'docs/experiments/phd/main_finaltrain_v1'
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def command(gpu,name,script,args=(),fork='GeoGS-conf-guided-v1-r23',site='B173nb_b10'):
    cfg=json.loads((C/'finaltrain_v1.json').read_text());image=cfg['docker_images']['jointbuildgs:geogs-conf-guided-v1']
    cmd=['docker','run','--rm','--read-only','--network','none','--name',name,'--gpus',f'device={gpu}',
         '--user',f'{os.getuid()}:{os.getgid()}','--cpus','8','--memory','40g','--memory-swap','40g','--shm-size','4g']
    for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=4','OPENBLAS_NUM_THREADS=1',
              'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True',f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{site}/split.json',
              'TMPDIR=/out/tmp','MPLCONFIGDIR=/out/tmp/mpl','XDG_CACHE_HOME=/out/tmp/cache','TORCH_HOME=/weights/torch','TZ=Asia/Seoul']:
        cmd+=['-e',e]
    mounts=[(R,'/repo','ro'),(ART,'/art','ro'),(ART,'/artifacts/JointBuildGS','ro'),(PH,'/ph','ro'),(O,'/out','rw'),(C,'/cfg','ro'),(D,'/docs','rw'),
            (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/p','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0','ro'),
            (R/'src/phd/forks'/fork,'/source','ro'),(PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights','/weights','ro')]
    for src,dst,mode in mounts:cmd+=['-v',f'{src}:{dst}:{mode}']
    return cmd+['-w','/source','--entrypoint','python',image,'-B','-u',f'/repo/scripts/phd/main_finaltrain_v1/{script}',*args]

def main():
    mode=sys.argv[1]
    if mode=='probe':
        for label,fork in [('r22','GeoGS-conf-guided-v1-r22'),('r23_off','GeoGS-conf-guided-v1-r23')]:
            subprocess.run(command(0,'jbgs-finaltrain-probe-'+label,'probe_default.py',[label],fork=fork),check=True)
        subprocess.run(command(0,'jbgs-finaltrain-probe-verify','verify_default.py'),check=True)
    elif mode=='train':train(*sys.argv[2:])
    else:raise ValueError(mode)

def train(gpu,site,prior):
    assert {'0':'ALS','1':'LoD2'}[str(gpu)]==prior
    stem=f'{site}__{prior}';run=O/'runs'/site/f'ft_{prior}_s0';run.mkdir(parents=True,exist_ok=False)
    for name in ['unit_math.json','unit_default.json']:
        assert json.loads((O/'verification'/name).read_text())['status']=='PASS'
    for p in ['ALS','LoD2']:
        assert json.loads((O/'verification'/f'inputs_{site}__{p}.json').read_text())['status']=='PASS'
    if site!='B173nb_b10':
        for p in ['ALS','LoD2']:assert (O/'delivery'/f'B173nb_b10__{p}.json').is_file()
    attempts=[]
    for attempt in [1,2]:
        root=run/f'attempt{attempt}';root.mkdir();model='/out/'+str((root/'model').relative_to(O))
        args=[site,prior,'-s',f'/p/fork_inputs/s61/{site}/scene_{prior}','-m',model,'--eval','-r','1','--data_device','cpu',
            '--lod_depth_path','/p/fork_none','--da_depth_path','/p/fork_none','--stage_switch_iter','0',
            '--lambda_lod_init','0','--lambda_lod_anchor','0','--lambda_da_depth','0','--jbgs_judgment','off',
            '--jbgs_target','on','--jbgs_target_rev','r8','--jbgs_finaltrain','on',
            '--jbgs_capture_iterations','7000','15000','30000','--jbgs_target_dir',f'/out/stage1/{stem}',
            '--jbgs_target_lambda','.05','--jbgs_seed','0','--iterations','30000','--test_iterations','7000','15000','30000',
            '--save_iterations','7000','15000','30000']
        cmd=command(gpu,f'jbgs-finaltrain-{site}-{prior}-a{attempt}','train_entry.py',args,site=site)
        dump(root/'command.json',cmd);dump(root/'launch.json',dict(at=now(),gpu=gpu,site=site,prior=prior,attempt=attempt,scientific_verdict=None));start=time.monotonic()
        with (root/'train.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
        stop=root/'model/target_monitor/STOP.json';health=json.loads(stop.read_text()) if stop.exists() else None
        status='TRAINING_COMPLETE_30000' if rc==0 and (root/'TRAINING_COMPLETE.json').exists() else ('HEALTH_STOP' if health else 'EXECUTION_ERROR')
        receipt=dict(at=now(),attempt=attempt,exit_code=rc,seconds=time.monotonic()-start,status=status,health=health,model=model,scientific_verdict=None)
        dump(root/'receipt.json',receipt);attempts.append(receipt)
        if status in ['TRAINING_COMPLETE_30000','HEALTH_STOP']:break
    final=dict(at=now(),site=site,prior=prior,status=attempts[-1]['status'] if attempts[-1]['status']!='EXECUTION_ERROR' else 'NO_RESULT',attempts=attempts,scientific_verdict=None)
    dump(run/'receipt.json',final);print(json.dumps(final,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
