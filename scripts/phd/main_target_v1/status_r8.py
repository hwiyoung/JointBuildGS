"""Compact read-only status for the ongoing authorized experiment and scoring."""
import json
from run_pilot_r8 import OUT,stamp

def read(p):return json.loads(p.read_text())

def main():
    rows=[]
    for prior in ['ALS','LoD2']:
        run=OUT/'r8/runs'/f'tg_B173nb_b10_{prior}_s0_r8';model=run/'model'
        curve=model/'target_monitor/curve.jsonl';row=dict(prior=prior)
        if curve.exists():
            value=json.loads(curve.read_text().splitlines()[-1])
            row.update({k:value[k] for k in ['iteration','gaussians','tags','prior_opacity_median']})
        row['training']=read(run/'receipt.json') if (run/'receipt.json').exists() else 'RUNNING_OR_WAITING'
        stop=OUT/'r8'/f'STOP_{prior}.json';row['stop']=read(stop) if stop.exists() else None
        row['checkpoints']=[]
        for it in [7000,15000,30000]:
            cp=dict(iteration=it,complete_state=(model/f'jbgs_complete/iteration_{it}/receipt.json').exists())
            coverage=model/f'check{it}/coverage.json'
            if coverage.exists():cp['target_fraction']=read(coverage)['fraction']
            for key,path in [('current_score',run/f'post{it}/score.json'),('final_mesh',OUT/f'r8/meshes/r8_{prior}_{it}/receipt.json'),('diagnostic',OUT/f'r8/failures/{prior}_{it}/summary.json'),('report',run/f'report{it}.json')]:cp[key]=path.exists()
            cp['axes_verified']=[kind for kind in ['current','final'] if (OUT/f'r8/scoring/r8_{prior}_{it}/{kind}/verification.json').exists()]
            row['checkpoints'].append(cp)
        rows.append(row)
    scorecounts={revision:dict(scored=len(list((OUT/revision/'scoring').glob('*/*/values.json'))),verified=len(list((OUT/revision/'scoring').glob('*/*/verification.json')))) for revision in ['r7_continue','r8']}
    active_logs=['r8/cpu_queue_r3.log','r8/gpu_queue.log','r8/report_queue.log','r8/post_verification_queue_r2.log','r7_continue/measurement_queue_r2.log','r7_continue/lod2_readout_queue_r2.log','r7_continue/verify_scores_queue.log']
    errors={name:(OUT/name).read_text()[-2000:] for name in active_logs if (OUT/name).exists() and 'Traceback' in (OUT/name).read_text()}
    print(json.dumps(dict(at=stamp(),r8=rows,scores=scorecounts,queue_errors=errors,scientific_verdict=None),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
