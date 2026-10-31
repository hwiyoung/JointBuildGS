"""Host stdlib orchestration, task-owned outputs; project computation in Docker."""
import fcntl,json,os,subprocess,sys,time,hashlib
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];ART=REPO.parent/'JointBuildGS-artifacts';PH=ART/'phase-payloads/phd'
OUT=PH/'main_target_v1/PHD-MAIN-TARGET-v1';IMG='jointbuildgs:geogs-conf-guided-v1'

def main():
    gpu,site,prior=sys.argv[1:4];mode=sys.argv[4] if len(sys.argv)>4 else 'preflight'
    assert mode in ['preflight','diagnose','decompose']
    # Existing cross-task lock opened read-only; contents and permissions unchanged.
    shared=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r')
    fcntl.flock(shared,fcntl.LOCK_EX)
    active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
    if any(x.strip() and x.strip() not in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for x in active.splitlines()):raise SystemExit('GPU_BUSY')
    dest=OUT/(mode+'_commands')/f'{site}_{prior}';dest.mkdir(parents=True,exist_ok=False)
    cmd=['docker','run','--rm','--read-only','--network','none','--name',f'jbgs-target-preflight-{site}-{prior}',
         '--gpus',f'device={gpu}','--user',f'{os.getuid()}:{os.getgid()}','--cpus','6','--memory','24g','--memory-swap','24g','--shm-size','2g']
    for env in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=2','OPENBLAS_NUM_THREADS=2',
        'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True',f'JBGS_SPLIT_JSON=/s0/fork_inputs/s61/{site}/split.json',
        'TMPDIR=/out/tmp','MPLCONFIGDIR=/out/tmp/mpl','XDG_CACHE_HOME=/out/tmp/cache','TORCH_HOME=/weights/torch','TZ=Asia/Seoul']:
        cmd+=['-e',env]
    mounts=[(REPO,'/repo','ro'),(ART,'/art','ro'),(ART,'/artifacts/JointBuildGS','ro'),(PH,'/ph','ro'),(OUT,'/out','rw'),
        (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/p','ro'),
        (REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19','/source','ro'),(REPO/'configs/phd/main_target_v1','/cfg','ro'),
        (REPO/'docs/experiments/phd/main_target_v1','/docs','rw'),
        (PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights','/weights','ro')]
    for src,dst,mount_mode in mounts:cmd+=['-v',f'{src}:{dst}:{mount_mode}']
    script='diagnose' if mode=='decompose' else mode
    cmd+=['-w','/source','--entrypoint','python',IMG,'-B','-u',f'/repo/scripts/phd/main_target_v1/gpu_{script}.py',site,prior]
    if mode=='decompose':cmd+=['decompose']
    binding={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for root in [REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19',REPO/'scripts/phd/main_target_v1'] for p in root.rglob('*') if p.is_file()}
    (dest/'code_binding.json').write_text(json.dumps(binding,indent=2)+'\n');(dest/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    t=time.time()
    with (dest/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    (dest/'receipt.json').write_text(json.dumps(dict(exit_code=rc,seconds=time.time()-t,gpu=gpu,optimization_steps=0,
        image_id=subprocess.check_output(['docker','image','inspect','-f','{{.Id}}',IMG],text=True).strip(),scientific_verdict=None),indent=2)+'\n')
    print(dest,rc,flush=True);sys.exit(rc)

if __name__=='__main__':main()
