"""Idempotent continuation of pending LoD2 readouts with the smaller CPU memory cap."""
import json,time,subprocess,sys
from run_pilot_r7 import REPO,OUT
from readout_resources_r2 import cpu
def main():
    run=OUT/'r7_continue/lod2_retry/runs/tg_B173nb_b10_LoD2_s0_r7';model=run/'model';root=OUT/'r7_continue';prior='LoD2'
    for it in [15000,30000]:
        key=f'r7_LoD2_{it}'
        while not (model/f'check{it}/coverage.json').exists():
            if (root/'lod2_retry/STOP_LoD2.json').exists():return
            time.sleep(5)
        if not (run/f'verification{it}.json').exists():cpu('verify-lod2-'+str(it),'verify_continue_r7_lod2.py',[prior,str(it)])
        if not (root/'meshes'/key/'render/receipt.json').exists():subprocess.run([sys.executable,str(REPO/'scripts/phd/main_target_v1/run_render_final_continue_r7_lod2.py'),'0',key],check=True)
        if not (root/'failures'/f'{prior}_{it}/summary.json').exists():subprocess.run([sys.executable,str(REPO/'scripts/phd/main_target_v1/run_diagnostic_continue_r7.py'),'0','max_contributor_continue_r7_lod2.py',prior,str(it)],check=True)
        for marker,script in [(run/f'origin_ratio_{it}.json','origin_ratio_continue_r7_lod2.py'),(root/'movement'/f'{prior}_{it}/summary.json','movement_continue_r7_lod2.py')]:
            if not marker.exists():cpu('lod2-'+script.split('_')[0]+'-'+str(it),script,[prior,str(it)])
        if not (run/f'post{it}/score.json').exists():cpu('post-lod2-'+str(it),'post_continue_r7_lod2.py',['run',key],heavy=True)
        if not (root/'meshes'/key/'receipt.json').exists():cpu('fuse-lod2-'+str(it),'fuse_final_continue_r7_lod2.py',[key],heavy=True)
        for kind in ['current','final']:
            if not (root/'scoring'/key/kind/'values.json').exists():subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_axes_continue_r7_lod2_resources_r2.sh'),key,kind],check=True)
            fig=REPO/'docs/experiments/phd/main_target_v1/figures'/f'continue_r7_{key}_{kind}_cells.json'
            if not fig.exists():cpu('fig-'+key+'-'+kind,'figures_continue_r7.py',[key,kind])
    cpu('full-state-lod2-final','verify_full_state_continue_r7_lod2.py',[prior]);cpu('fig-lod2-checkpoints','report_checkpoint_continue_r7_lod2.py',[prior]);cpu('detail-lod2-final','report_detail_continue_r7.py',[prior]);print('LOD2_ALL_READOUTS_COMPLETE',flush=True)
if __name__=='__main__':main()
