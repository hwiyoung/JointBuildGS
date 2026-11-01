"""Host stdlib, serial two baseline runs on one GPU; historical source read-only."""
import datetime as dt,fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R.parent/'JointBuildGS-artifacts';PH=A/'phase-payloads/phd';O=PH/'main_target_v1/PHD-MAIN-TARGET-v1';C=R/'configs/phd/main_target_v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
    gpu=sys.argv[1];cfg=json.loads((C/'baseline7k.r7.json').read_text());assert sha(C/'baseline7k.r7.json')==json.loads((C/'baseline7k.r7.lock.json').read_text())['sha256']
    for p,h in cfg['source_files'].items():assert sha(R/p)==h,p
    for row in cfg['rows']:
        lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
        busy=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
        assert not any(n.strip() and n.strip() not in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for n in busy.splitlines()),busy
        root=O/'r7/baselines'/row['name'];root.mkdir(exist_ok=False);name=f'jbgs-target-r7-base7k-{row["prior"]}'
        cmd=['docker','run','--rm','--read-only','--network','none','--name',name,'--gpus',f'device={gpu}','--user',f'{os.getuid()}:{os.getgid()}','--cpus','8','--memory','32g','--memory-swap','32g','--shm-size','8g']
        for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=8','JBGS_SPLIT_JSON=/p/fork_inputs/s61/B173nb_b10/split.json','PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True','MPLCONFIGDIR=/out/tmp/mpl','XDG_CACHE_HOME=/out/tmp/cache','TMPDIR=/out/tmp','TORCH_HOME=/weights/torch','TZ=Asia/Seoul']:cmd+=['-e',e]
        for src,dst,mode in [(R,'/repo','ro'),(A,'/artifacts/JointBuildGS','ro'),(PH,'/ph','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/p','ro'),(Path(row['source']),'/source','ro'),(O,'/out','rw'),(PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights','/weights','ro')]:cmd+=['-v',f'{src}:{dst}:{mode}']
        image=subprocess.check_output(['docker','image','inspect','-f','{{.Id}}',row['image']],text=True).strip();assert image==row['image_id']
        cmd+=['-w','/source','--entrypoint','python',row['image'],'-B','-u','train.py',*row['args']]
        dump(root/'launch.json',dict(at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),row=row,command=cmd,config_sha256=sha(C/'baseline7k.r7.json'),scientific_verdict=None))
        start=time.time()
        with (root/'train.log').open('x') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
        ok=r.returncode==0 and (root/'model/point_cloud/iteration_7000/point_cloud.ply').exists()
        dump(root/'receipt.json',dict(at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),exit_code=r.returncode,seconds=time.time()-start,status='COMPLETE_7000' if ok else 'STOP_EXECUTION',scientific_verdict=None))
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close();print(row['name'],r.returncode,flush=True)
        if not ok:raise SystemExit(r.returncode or 1)
if __name__=='__main__':main()
