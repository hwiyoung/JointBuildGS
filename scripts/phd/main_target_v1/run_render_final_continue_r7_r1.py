"""Host GPU ownership for read-only final-mesh render, without training commands."""
import sys,json,fcntl,subprocess,time,hashlib
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump
def main():
 gpu,key=sys.argv[1:3];h=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(h,fcntl.LOCK_EX);active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not x.strip() or x.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for x in active.splitlines()),'GPU_BUSY'
 cfg=json.loads((CFG/'scoring_continue_r7.json').read_text());row=next(r for r in cfg['rows'] if r['key']==key);assert not row['existing_virtual'];root=OUT/'r7_continue/mesh_commands_r1'/key;root.mkdir(parents=True,exist_ok=False)
 old=json.loads((OUT/'r7/runs/tg_B173nb_b10_ALS_s0_r7/command.json').read_text());cmd=old[:old.index('/repo/scripts/phd/main_target_v1/train_entry_r7.py')];cmd[cmd.index('--name')+1]='jbgs-target-final-'+key;cmd[cmd.index('--gpus')+1]='device='+gpu;cmd+=['/repo/scripts/phd/main_target_v1/render_final_continue_r7_r1.py',key];dump(root/'command.json',cmd);dump(root/'source.json',dict(at=stamp(),script_sha256=hashlib.sha256((REPO/'scripts/phd/main_target_v1/render_final_continue_r7_r1.py').read_bytes()).hexdigest(),optimization_steps=0));start=time.time()
 with (root/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(root/'receipt.json',dict(exit_code=rc,seconds=time.time()-start,scientific_verdict=None));print(key,rc,flush=True);raise SystemExit(rc)
if __name__=='__main__':main()
