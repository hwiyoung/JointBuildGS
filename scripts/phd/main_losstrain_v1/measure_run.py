"""Host orchestration of one finished arm's required CPU measurements in Docker."""
import argparse
import subprocess
import time
import json
from pathlib import Path
import train_calibration as C

def main():
    ap=argparse.ArgumentParser();ap.add_argument('site');ap.add_argument('prior');ap.add_argument('result');ap.add_argument('--wait-post',action='store_true');ap.add_argument('--core-only',action='store_true');a=ap.parse_args()
    assert a.result.startswith('lt_') and not a.result.startswith('lt_cal_')
    unit=C.OUT/'runs'/a.site/a.result
    required_post='post_stage_PASS.json' if a.core_only else 'post_PASS.json'
    prefix='core_measure' if a.core_only else 'measure'
    while not (unit/required_post).exists():
        if not a.wait_post:raise RuntimeError('postprocessing not complete')
        failed=[p for p in unit.glob('*attempt_1_receipt.json') if json.loads(p.read_text()).get('exit_code')]
        if failed:raise RuntimeError('postprocessing stopped; no measurement: '+str(failed))
        time.sleep(5)
    tag=(a.site+'-'+a.prior+'-'+a.result).lower().replace('_','-')
    calls=[('mesh',C.REPO/'scripts/phd/main_losstrain_v1/run_cpu.sh',
            ['mesh_score.py','--site',a.site,'--prior',a.prior,'--result',a.result],C.OUT/'patch_z'/f'{a.site}__{a.prior}__{a.result}.json'),
        ('fates',C.REPO/'scripts/phd/main_losstrain_v1/run_cpu.sh',
            ['fates.py',a.site,a.prior,a.result],C.OUT/'fates'/a.site/f'{a.prior}__{a.result}.json'),
        ('fate-cells',C.REPO/'scripts/phd/main_losstrain_v1/run_cpu.sh',
            ['split_fate_cells.py',a.site,a.prior,a.result],C.OUT/'fate_cell_split'/a.site/f'{a.prior}__{a.result}.json'),
        ('axes',C.REPO/'scripts/phd/main_losstrain_v1/run_axes.sh',
            ['axes_measure.py',a.site,a.prior,a.result],C.REPO/'docs/experiments/phd/main_losstrain_v1/tables/axes'/f'{a.site}__{a.prior}__{a.result}.json')]
    if a.core_only:calls=[call for call in calls if call[0]!='axes']
    receipts=[]
    for name,script,args,dest in calls:
        if dest.exists():
            data=json.loads(dest.read_text());assert data.get('status','PASS')=='PASS'
            receipts.append(dict(step=name,reuse_own_completed=True,path=str(dest),sha256=C.sha(dest)));continue
        cmd=['bash',str(script),tag+'-'+name,*args];start=time.monotonic()
        with (unit/(prefix+'_'+name+'.log')).open('w') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
        row=dict(step=name,exit_code=rc,seconds=time.monotonic()-start,command=cmd,path=str(dest));receipts.append(row)
        C.save(unit/(prefix+'_progress.json'),dict(steps=receipts,scientific_verdict=None))
        assert rc==0 and dest.exists(),name+' measurement failed; see run log'
        assert json.loads(dest.read_text()).get('status','PASS')=='PASS'
        print(a.site,a.prior,a.result,name,'PASS',flush=True)
    C.save(unit/(prefix+'_PASS.json'),dict(at=C.now(),steps=receipts,core_only=a.core_only,scientific_verdict=None))

if __name__=='__main__':main()
