"""Inference-only r8 checkpoint readouts on either GPU when its owner releases it."""
import json,sys,subprocess,time
from run_pilot_r8 import OUT,REPO
def main():
    pending=[(prior,it) for it in [7000,15000,30000] for prior in ['ALS','LoD2']]
    while pending:
        worked=False
        for prior,it in pending.copy():
            model=OUT/'r8/runs'/f'tg_B173nb_b10_{prior}_s0_r8/model';coverage=model/f'check{it}/coverage.json'
            if not coverage.exists():
                if (OUT/'r8'/f'STOP_{prior}.json').exists():pending.remove((prior,it))
                continue
            key=f'r8_{prior}_{it}'
            for script,args,result in [('render_final_r8.py',[key],OUT/'r8/meshes'/key/'render/receipt.json'),('max_contributor_r8.py',[prior,str(it)],OUT/'r8/failures'/f'{prior}_{it}/summary.json')]:
                if not result.exists():subprocess.run([sys.executable,str(REPO/'scripts/phd/main_target_v1/run_diagnostic_r8.py'),'0',script]+args,check=True)
            pending.remove((prior,it));worked=True;break
        if not worked:time.sleep(5)
    print('R8_ALL_AVAILABLE_GPU_READOUTS_COMPLETE',flush=True)
if __name__=='__main__':main()
