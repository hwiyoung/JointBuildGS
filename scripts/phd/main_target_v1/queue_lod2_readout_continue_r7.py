"""Requested 15k/30k readouts of the independent LoD2 retry; no training starts here."""
import json,time,subprocess,sys,os
from run_pilot_r7 import REPO,PH,OUT,CFG
from queue_measure_continue_r7 import cpu

def main():
 model=OUT/'r7_continue/lod2_retry/runs/tg_B173nb_b10_LoD2_s0_r7/model';root=OUT/'r7_continue';prior='LoD2'
 for it in [15000,30000]:
  key=f'r7_LoD2_{it}'
  while not (model/f'check{it}/coverage.json').exists():
   if (root/'lod2_retry/STOP_LoD2.json').exists():print('LOD2_STOP_READOUT_NOT_REACHED',it,flush=True);return
   time.sleep(5)
  cpu('verify-lod2-'+str(it),'verify_continue_r7_lod2.py',[prior,str(it)])
  # The other GPU is used only under its shared ownership lock.
  subprocess.run([sys.executable,str(REPO/'scripts/phd/main_target_v1/run_render_final_continue_r7_lod2.py'),'0',key],check=True)
  subprocess.run([sys.executable,str(REPO/'scripts/phd/main_target_v1/run_diagnostic_continue_r7.py'),'0','max_contributor_continue_r7_lod2.py',prior,str(it)],check=True)
  cpu('ratio-lod2-'+str(it),'origin_ratio_continue_r7_lod2.py',[prior,str(it)])
  cpu('move-lod2-'+str(it),'movement_continue_r7_lod2.py',[prior,str(it)])
  cpu('post-lod2-'+str(it),'post_continue_r7_lod2.py',['run',key],heavy=True)
  cpu('fuse-lod2-'+str(it),'fuse_final_continue_r7_lod2.py',[key],heavy=True)
  for kind in ['current','final']:
   subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_axes_continue_r7_lod2.sh'),key,kind],check=True)
   cpu('fig-'+key+'-'+kind,'figures_continue_r7.py',[key,kind])
 cpu('full-state-lod2-final','verify_full_state_continue_r7_lod2.py',[prior]);cpu('fig-lod2-checkpoints','report_checkpoint_continue_r7_lod2.py',[prior]);print('LOD2_ALL_READOUTS_COMPLETE',flush=True)
if __name__=='__main__':main()
