"""Own an idle GPU only for the explicit read-only saved-model renderer."""
import fcntl,json,subprocess,sys,time
from run_pilot_r7 import REPO,PH,OUT,stamp,dump
def main():
 gpu=sys.argv[1];family=sys.argv[2];assert family in ['r8','base'];assert gpu in ['0','1'];dest=OUT/'r8_recorded_continue/heavy';dest.mkdir(exist_ok=True)
 handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not x.strip() or x.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for x in active.splitlines()),'GPU_BUSY'
 old=json.loads((OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/command.json').read_text());cmd=old[:old.index('/repo/scripts/phd/main_target_v1/train_entry_r8.py')];cmd[cmd.index('--name')+1]='jbgs-heavy-'+family;cmd[cmd.index('--gpus')+1]='device='+gpu
 if family=='base':cmd=[x.replace('GeoGS-conf-guided-v1-r22:/source','GeoGS-conf-guided-v1-r15:/source') for x in cmd]
 cmd+=['/repo/scripts/phd/main_target_v1/r8_heavy_render.py',family];dump(dest/(family+'_command.json'),cmd);start=time.time()
 with (dest/(family+'_render.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(dest/(family+'_receipt.json'),dict(at=stamp(),exit_code=rc,seconds=time.time()-start,optimization_steps=0,scientific_verdict=None));raise SystemExit(rc)
if __name__=='__main__':main()
