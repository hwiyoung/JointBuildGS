"""Host orchestration: one locked pilot per GPU; any prescribed stop terminates both pilots."""
import datetime as dt,fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];ART=REPO.parent/'JointBuildGS-artifacts';PH=ART/'phase-payloads/phd'
OUT=PH/'main_target_v1/PHD-MAIN-TARGET-v1';CFG=REPO/'configs/phd/main_target_v1';IMG='jointbuildgs:geogs-conf-guided-v1'
def stamp():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def stop_both(reason):
    dest=OUT/'r6/STOP_BOTH.json'
    try:
        with dest.open('x') as f:json.dump(dict(at=stamp(),reason=reason,scientific_verdict=None),f,indent=2)
    except FileExistsError:pass
    active=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
    for prior in ['ALS','LoD2']:
        name=f'jbgs-target-train-r6-B173nb_b10-{prior}'
        if name in active:subprocess.run(['docker','stop','--time','10',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def main():
    gpu,prior=sys.argv[1:3];site='B173nb_b10';assert prior in ['ALS','LoD2']
    shared=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(shared,fcntl.LOCK_EX)
    if (OUT/'r6/STOP_BOTH.json').exists():raise SystemExit('PRIOR_PILOT_STOP')
    active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
    if any(x.strip() and x.strip() not in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for x in active.splitlines()):raise SystemExit('GPU_BUSY')
    root=OUT/'r6/runs'/f'tg_{site}_{prior}_s0_r6';root.mkdir(parents=True,exist_ok=False)
    name=f'jbgs-target-train-r6-{site}-{prior}'
    cmd=['docker','run','--rm','--read-only','--network','none','--name',name,'--gpus',f'device={gpu}',
        '--user',f'{os.getuid()}:{os.getgid()}','--cpus','8','--memory','32g','--memory-swap','32g','--shm-size','4g']
    for env in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=4','OPENBLAS_NUM_THREADS=2',
        'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True',f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{site}/split.json',
        'TMPDIR=/out/tmp','MPLCONFIGDIR=/out/tmp/mpl','XDG_CACHE_HOME=/out/tmp/cache','TORCH_HOME=/weights/torch','TZ=Asia/Seoul']:
        cmd+=['-e',env]
    mounts=[(REPO,'/repo','ro'),(ART,'/art','ro'),(ART,'/artifacts/JointBuildGS','ro'),(PH,'/ph','ro'),(OUT,'/out','rw'),
        (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/p','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0','ro'),
        (REPO/'src/phd/forks/GeoGS-conf-guided-v1-r20','/source','ro'),(CFG,'/cfg','ro'),
        (PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights','/weights','ro')]
    for src,dst,mode in mounts:cmd+=['-v',f'{src}:{dst}:{mode}']
    model=f'/out/r6/runs/tg_{site}_{prior}_s0_r6/model'
    cmd+=['-w','/source','--entrypoint','python',IMG,'-B','-u','/repo/scripts/phd/main_target_v1/train_entry_r6.py',site,prior,
        '-s',f'/p/fork_inputs/s61/{site}/scene_{prior}','-m',model,'--eval','-r','1','--data_device','cpu',
        '--lod_depth_path','/p/fork_none','--da_depth_path','/p/fork_none','--stage_switch_iter','0',
        '--lambda_lod_init','0','--lambda_lod_anchor','0','--lambda_da_depth','0','--jbgs_judgment','off',
        '--jbgs_target','on','--jbgs_target_rev','r6','--jbgs_capture_iterations','7000','15000','30000','--jbgs_target_dir',f'/out/r2/stage1/{site}_{prior}','--jbgs_target_lambda','.05',
        '--jbgs_seed','0','--iterations','30000','--test_iterations','7000','15000','30000',
        '--save_iterations','6000','7000','15000','30000']
    dump(root/'command.json',cmd);dump(root/'launch.json',dict(at=stamp(),gpu=gpu,site=site,prior=prior,container=name,
        config_sha256=hashlib.sha256((CFG/'target_v1.r6.json').read_bytes()).hexdigest(),
        image_id=subprocess.check_output(['docker','image','inspect','-f','{{.Id}}',IMG],text=True).strip(),scientific_verdict=None))
    binding={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for parent in [REPO/'src/phd/forks/GeoGS-conf-guided-v1-r20',REPO/'scripts/phd/main_target_v1'] for p in parent.rglob('*') if p.is_file()}
    dump(root/'code_binding.json',binding);start=time.time()
    with (root/'train.log').open('x') as f:
        proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
        while proc.poll() is None:
            stop=root/'model/target_monitor/STOP.json'
            if stop.exists():stop_both(dict(arm=f'{site}_{prior}',health=json.loads(stop.read_text())))
            if (OUT/'r6/STOP_BOTH.json').exists():stop_both('existing joint stop')
            time.sleep(2)
        rc=proc.returncode
    if rc:stop_both(dict(arm=f'{site}_{prior}',execution_exit_code=rc))
    dump(root/'receipt.json',dict(at=stamp(),exit_code=rc,seconds=time.time()-start,
        status='TRAINING_COMPLETE_30000' if rc==0 else 'STOPPED',automatic_retry=False,scientific_verdict=None))
    print(root,rc,flush=True);raise SystemExit(rc)

if __name__=='__main__':main()
