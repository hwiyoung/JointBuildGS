"""Host GPU ownership for saved-state diagnostics only."""
import fcntl,json,subprocess,sys,time
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump
def main():
    gpu=sys.argv[1];assert gpu in ['0','1'];root=OUT/'r8_recorded_continue'
    assert (root/'STOP_LoD2.json').exists()
    handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
    active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
    assert all(not x.strip() or x.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for x in active.splitlines()),'GPU_BUSY'
    old=json.loads((OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/command.json').read_text());cmd=old[:old.index('/repo/scripts/phd/main_target_v1/train_entry_r8.py')]
    cmd[cmd.index('--name')+1]='jbgs-target-record-stop-render';cmd[cmd.index('--gpus')+1]='device='+gpu
    cmd+=['/repo/scripts/phd/main_target_v1/r8_record_stop_render.py']
    dest=root/'stop_diagnostic';dump(dest/'render_command.json',cmd);start=time.time()
    with (dest/'render.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    dump(dest/'render_receipt.json',dict(at=stamp(),exit_code=rc,seconds=time.time()-start,optimization_steps=0,scientific_verdict=None));raise SystemExit(rc)
if __name__=='__main__':main()
