"""Produce checkpoint figures and full-state audits when complete source files exist."""
import subprocess,sys,time,json
from run_pilot_r8 import OUT,REPO
from queue_measure_continue_r7 import cpu
def main():
    pending=[(p,it) for it in [7000,15000,30000] for p in ['ALS','LoD2']]
    while pending:
        worked=False
        for prior,it in pending.copy():
            run=OUT/'r8/runs'/f'tg_B173nb_b10_{prior}_s0_r8';check=run/f'model/check{it}/coverage.json'
            if not check.exists():
                if (OUT/'r8'/f'STOP_{prior}.json').exists():pending.remove((prior,it))
                continue
            required=[run/f'verification{it}.json',run/f'post{it}/score.json',run/f'origin_ratio_{it}.json',OUT/'r8/movement'/f'{prior}_{it}/summary.json',run/f'model/jbgs_complete/iteration_{it}/receipt.json']
            if not all(x.exists() for x in required):continue
            for marker,script in [(run/f'diagnostics_report{it}.json','report_diagnostics_r8.py'),(run/f'report{it}.json','report_checkpoint_r8.py')]:
                if not marker.exists():cpu('r8-report-'+prior+'-'+str(it)+'-'+script.split('_')[1],script,[prior,str(it)])
            cpu('r8-state-'+prior+'-'+str(it),'verify_full_state_r8.py',[prior]);pending.remove((prior,it));worked=True;break
        if not worked:time.sleep(5)
    print('R8_ALL_AVAILABLE_CHECKPOINT_REPORTS_COMPLETE',flush=True)
if __name__=='__main__':main()
