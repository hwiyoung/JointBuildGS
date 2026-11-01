"""Independent current-mesh verification for r7 future and r8 checkpoints."""
import time
from run_pilot_r8 import OUT
from readout_resources_r2 import cpu
def main():
    pending=[('r7','LoD2',it) for it in [15000,30000]]+[('r8',p,it) for it in [7000,15000,30000] for p in ['ALS','LoD2']]
    while pending:
        worked=False
        for rev,prior,it in pending.copy():
            run=OUT/('r8/runs' if rev=='r8' else 'r7_continue/lod2_retry/runs')/f'tg_B173nb_b10_{prior}_s0_{rev}';score=run/f'post{it}/score.json';attr=run/f'post{it}/origin_attribution.npz'
            if rev=='r8' and (OUT/'r8'/f'STOP_{prior}.json').exists() and not (run/f'model/point_cloud/iteration_{it}/point_cloud.ply').exists():
                print('UNAVAILABLE_AFTER_INDEPENDENT_STOP',rev,prior,it,flush=True);pending.remove((rev,prior,it));worked=True;continue
            if not score.exists() or not attr.exists():continue
            if not (run/f'verification_post{it}.json').exists():cpu('postverify-'+rev+'-'+prior+'-'+str(it),'verify_post_checkpoint.py',[rev,prior,str(it)],heavy=True)
            pending.remove((rev,prior,it));worked=True;break
        if not worked:time.sleep(5)
    print('ALL_NEW_CURRENT_MESH_RAYS_VERIFIED',flush=True)
if __name__=='__main__':main()
