"""Checkpoint-first CPU readout queue; geometry values never stop training."""
import json,subprocess,sys,time
from run_pilot_r8 import OUT,REPO,CFG,dump,stamp
from readout_resources_r2 import cpu
def main():
    rows=json.loads((CFG/'scoring_r8.json').read_text())['rows'];rows.sort(key=lambda r:(r['iteration'],r['prior']))
    while True:
        worked=False
        for r in rows:
            prior,it,key=r['prior'],r['iteration'],r['key'];run=OUT/'r8/runs'/f'tg_B173nb_b10_{prior}_s0_r8';model=run/'model'
            if not (model/f'check{it}/coverage.json').exists():continue
            actions=[(run/f'verification{it}.json','verify_checkpoint_r8.py',[prior,str(it)],False),
                (run/f'post{it}/score.json','post_r8.py',['run',key],True),
                (OUT/'r8/movement'/f'{prior}_{it}/summary.json','movement_r8.py',[prior,str(it)],False)]
            if (OUT/'r8/failures'/f'{prior}_{it}/summary.json').exists():actions.append((run/f'origin_ratio_{it}.json','origin_ratio_r8.py',[prior,str(it)],False))
            if (OUT/'r8/meshes'/key/'render/receipt.json').exists():actions.append((OUT/'r8/meshes'/key/'receipt.json','fuse_final_r8.py',[key],True))
            for result,script,args,heavy in actions:
                if not result.exists():cpu('r8-'+PathStem(script)+'-'+prior+'-'+str(it),script,args,heavy=heavy);worked=True;break
            if worked:break
        if worked:continue
        for r in rows:
            key=r['key'];run=OUT/'r8/runs'/r['name']
            for kind in ['current','final']:
                mesh=run/f'post{r["iteration"]}/merged.ply' if kind=='current' else OUT/'r8/meshes'/key/'final.ply';dest=OUT/'r8/scoring'/key/kind
                if not mesh.exists():continue
                if not (dest/'values.json').exists():subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_axes_r8_resources_r2.sh'),key,kind],check=True);worked=True;break
                fig=REPO/'docs/experiments/phd/main_target_v1/figures'/f'r8_{key}_{kind}_cells.json'
                if not fig.exists():cpu('fig-'+key+'-'+kind,'figures_r8.py',[key,kind]);worked=True;break
                if not (dest/'verification.json').exists():subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_verify_scores_r8.sh'),key,kind],check=True);worked=True;break
            if worked:break
        done=sum((OUT/'r8/scoring'/r['key']/k/'verification.json').exists() for r in rows for k in ['current','final'])
        dump(OUT/'r8/measurement_progress.json',dict(at=stamp(),verified=done,planned=12,scientific_verdict=None))
        if done==12:print('R8_ALL_12_MESHES_VERIFIED',flush=True);return
        if not worked:time.sleep(5)
def PathStem(name):return name.removesuffix('.py').replace('_','-')
if __name__=='__main__':main()
