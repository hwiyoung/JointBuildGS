"""Host read-only GPU diagnostics using existing resource ownership locks."""
import fcntl,json,subprocess,sys,time,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[3];P=R.parent/'JointBuildGS-artifacts/phase-payloads/phd';O=P/'main_target_v1/PHD-MAIN-TARGET-v1'
def main():
    gpu,script,*args=sys.argv[1:];key='_'.join([Path(script).stem]+args);root=O/'r5/commands'/key;root.mkdir(parents=True,exist_ok=False)
    lock=(P/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
    active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
    if any(s.strip() and s.strip() not in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for s in active.splitlines()):raise SystemExit('GPU_BUSY')
    old=json.loads((O/'r4n/runs/tg_B173nb_b10_ALS_s0/command.json').read_text());cmd=old[:old.index('/repo/scripts/phd/main_target_v1/train_entry_r4n.py')]
    cmd[cmd.index('--name')+1]='jbgs-target-r5-'+key;cmd[cmd.index('--gpus')+1]='device='+gpu
    cmd+=['/repo/scripts/phd/main_target_v1/'+script]+args
    (root/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');(root/'code_sha256.json').write_text(json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*r5.py')},indent=2)+'\n')
    start=time.time()
    with (root/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    (root/'receipt.json').write_text(json.dumps(dict(exit_code=rc,seconds=time.time()-start,optimization_steps=0,scientific_verdict=None),indent=2)+'\n');print(key,rc,flush=True);raise SystemExit(rc)
if __name__=='__main__':main()
