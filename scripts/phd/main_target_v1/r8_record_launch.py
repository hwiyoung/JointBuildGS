"""Host-only Docker orchestration; never retries training after a stop."""
import fcntl,json,subprocess,sys,time
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump
def main():
    mode,gpu=sys.argv[1:3];assert mode in ['verify','train'] and gpu in ['0','1']
    root=OUT/'r8_recorded_continue'
    handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
    active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
    assert all(not x.strip() or x.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for x in active.splitlines()),'GPU_BUSY'
    old=json.loads((OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/command.json').read_text())
    cut=old.index('/repo/scripts/phd/main_target_v1/train_entry_r8.py');cmd=old[:cut]
    cmd[cmd.index('--name')+1]='jbgs-target-record-r8-'+mode;cmd[cmd.index('--gpus')+1]='device='+gpu
    assert subprocess.check_output(['docker','image','inspect','-f','{{.Id}}','jointbuildgs:geogs-conf-guided-v1'],text=True).strip()=='sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'
    if mode=='verify':
        cmd=[x.replace('/main_target_v1:/cfg:ro','/main_target_v1:/cfg:rw') for x in cmd]
        cmd+=['/repo/scripts/phd/main_target_v1/r8_record_verify.py'];dest=root/'verification'
    else:
        assert not (root/'STOP_LoD2.json').exists()
        cfg=json.loads((CFG/'r8_record_continue.json').read_text());args=old[cut+3:]
        args[args.index('-m')+1]=cfg['model']
        for flag,key in [('--save_iterations','save_iterations'),('--jbgs_capture_iterations','capture_iterations')]:
            i=args.index(flag)+1;j=i
            while j<len(args) and not args[j].startswith('-'):j+=1
            args[i:j]=list(map(str,cfg[key]))
        args+=['--jbgs_resume_full',cfg['checkpoint']]
        cmd+=['/repo/scripts/phd/main_target_v1/r8_record_entry.py']+args;dest=root/'runs/tg_B173nb_b10_LoD2_s0_r8'
    dest.mkdir(parents=True,exist_ok=False);dump(dest/'command.json',cmd)
    start=time.time()
    with (dest/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    dump(dest/'launch_receipt.json',dict(at=stamp(),mode=mode,gpu=gpu,exit_code=rc,seconds=time.time()-start,automatic_retry=False,scientific_verdict=None))
    print(mode,rc,flush=True);raise SystemExit(rc)
if __name__=='__main__':main()
