"""Host driver for stopped-pilot readout only, with the same GPU and source mounts."""
import fcntl,hashlib,json,subprocess,sys,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];PH=REPO.parent/'JointBuildGS-artifacts/phase-payloads/phd';OUT=PH/'main_target_v1/PHD-MAIN-TARGET-v1'
def main():
    prior=sys.argv[1];run=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0';launch=json.loads((run/'launch.json').read_text());gpu=launch['gpu']
    assert (run/'receipt.json').exists() and (OUT/'r4n/STOP_BOTH.json').exists()
    lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
    active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
    if any(s.strip() and s.strip() not in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for s in active.splitlines()):raise SystemExit('GPU_BUSY')
    root=OUT/'r4n/readout_completion_commands'/prior;root.mkdir(parents=True,exist_ok=False)
    old=json.loads((run/'command.json').read_text());cmd=old[:old.index('/repo/scripts/phd/main_target_v1/train_entry_r4n.py')]
    cmd[cmd.index('--name')+1]=f'jbgs-target-complete7000-r4n-{prior}'
    cmd+=['/repo/scripts/phd/main_target_v1/gpu_complete7000_r4n.py',prior]
    (root/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    binding={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in [REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19',Path(__file__).parent] for p in folder.rglob('*.py')}
    (root/'code_binding.json').write_text(json.dumps(binding,indent=2)+'\n');start=time.time()
    with (root/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    (root/'receipt.json').write_text(json.dumps(dict(exit_code=rc,seconds=time.time()-start,optimization_steps=0,scientific_verdict=None),indent=2)+'\n')
    print('READOUT_COMPLETION',prior,rc,flush=True);raise SystemExit(rc)

if __name__=='__main__':main()
