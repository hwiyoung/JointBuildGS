"""Use the original baseline fork and existing GPU ownership lock for inference only."""
import fcntl,subprocess,json,hashlib,time,sys
from pathlib import Path
from run_pilot_r8 import REPO,PH,OUT,stamp,dump


def main():
    prior=sys.argv[1];gpu='0'
    handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r')
    fcntl.flock(handle,fcntl.LOCK_EX)
    active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
    allowed={'/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'}
    assert not any(x.strip() and x.strip() not in allowed for x in active.splitlines())
    launch=json.loads((OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0/launch.json').read_text())
    old=launch['command']; cmd=old[:old.index('train.py')]
    cmd[cmd.index('--name')+1]='jbgs-target-baseline-origin-r8-'+prior
    cmd[cmd.index('--gpus')+1]='device='+gpu
    cmd+=['/repo/scripts/phd/main_target_v1/baseline_origin_r8.py',prior]
    cmd[cmd.index('-w'):cmd.index('-w')]=['-v',str(REPO/'configs/phd/main_target_v1')+':/cfg:ro',
                                           '-v',str(REPO.parent/'JointBuildGS-artifacts')+':/art:ro']
    root=OUT/'r8/commands'/('baseline_origin_'+prior);root.mkdir(parents=True,exist_ok=False)
    dump(root/'command.json',cmd);start=time.time()
    with (root/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    dump(root/'receipt.json',dict(at=stamp(),exit_code=rc,seconds=time.time()-start,optimization_steps=0,scientific_verdict=None))
    print('BASELINE_ORIGIN_GPU_EXIT',prior,rc,flush=True);raise SystemExit(rc)


if __name__=='__main__':main()
