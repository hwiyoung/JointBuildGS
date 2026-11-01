"""Host read-only GPU diagnostics using existing resource ownership locks."""
import fcntl,json,subprocess,sys,time,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[3];P=R.parent/'JointBuildGS-artifacts/phase-payloads/phd';O=P/'main_target_v1/PHD-MAIN-TARGET-v1'
def main():
    gpu,script,*args=sys.argv[1:];key='_'.join([Path(script).stem]+args);root=O/'r7/commands'/key;root.mkdir(parents=True,exist_ok=False)
    allowed={'/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'}
    candidates=[gpu]+[g for g in ['0','1'] if g!=gpu] if script=='max_contributor_r7.py' else [gpu]
    lock=None
    while lock is None:
        for candidate in candidates:
            handle=(P/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{candidate}.lock').open('r')
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:handle.close();continue
            active=subprocess.check_output(['nvidia-smi','-i',candidate,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
            if any(v.strip() and v.strip() not in allowed for v in active.splitlines()):handle.close();continue
            lock=handle;gpu=candidate;break
        if lock is None:time.sleep(5)
    old=json.loads((O/'r6/runs/tg_B173nb_b10_ALS_s0_r6/command.json').read_text());cmd=old[:old.index('/repo/scripts/phd/main_target_v1/train_entry_r6.py')]
    cmd[cmd.index('--name')+1]='jbgs-target-r7-'+key;cmd[cmd.index('--gpus')+1]='device='+gpu
    fork='GeoGS-conf-guided-v1-r15' if script=='render_baseline7k_r7.py' else 'GeoGS-conf-guided-v1-r21'
    cmd=[x.replace('GeoGS-conf-guided-v1-r20',fork) for x in cmd]
    cmd+=['/repo/scripts/phd/main_target_v1/'+script]+args
    (root/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');(root/'code_sha256.json').write_text(json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*r7.py')},indent=2)+'\n')
    start=time.time()
    with (root/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    (root/'receipt.json').write_text(json.dumps(dict(exit_code=rc,seconds=time.time()-start,optimization_steps=0,scientific_verdict=None),indent=2)+'\n');print(key,rc,flush=True);raise SystemExit(rc)
if __name__=='__main__':main()
