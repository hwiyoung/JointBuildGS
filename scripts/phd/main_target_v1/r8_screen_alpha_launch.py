"""Idle-GPU read-only buffer capture; no training entry point."""
import fcntl,json,subprocess,time
from run_pilot_r7 import REPO,PH,OUT,stamp,dump
def main():
 gpu='0';dest=OUT/'r8_screen_prune';handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/photo_gpu_0.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not x.strip() or x.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for x in active.splitlines()),'GPU_BUSY'
 old=json.loads((OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/command.json').read_text());cmd=old[:old.index('/repo/scripts/phd/main_target_v1/train_entry_r8.py')];cmd[cmd.index('--name')+1]='jbgs-screen-alpha';cmd[cmd.index('--gpus')+1]='device='+gpu
 cmd+=['/repo/scripts/phd/main_target_v1/r8_screen_alpha_export.py'];dump(dest/'alpha_command.json',cmd);start=time.time()
 with (dest/'alpha_export.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(dest/'alpha_gpu_receipt.json',dict(at=stamp(),exit_code=rc,seconds=time.time()-start,optimization_steps=0,scientific_verdict=None));raise SystemExit(rc)
if __name__=='__main__':main()
