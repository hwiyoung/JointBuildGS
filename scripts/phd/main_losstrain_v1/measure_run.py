"""Host orchestration of one finished arm's required CPU measurements in Docker."""
import argparse
import subprocess
import time
import json
from pathlib import Path
import train_calibration as C

def main():
    ap=argparse.ArgumentParser();ap.add_argument('site');ap.add_argument('prior');ap.add_argument('result');a=ap.parse_args()
    assert a.result.startswith('lt_') and not a.result.startswith('lt_cal_')
    unit=C.OUT/'runs'/a.site/a.result;assert (unit/'post_PASS.json').exists()
    tag=(a.site+'-'+a.prior+'-'+a.result).lower().replace('_','-')
    calls=[('mesh',C.REPO/'scripts/phd/main_losstrain_v1/run_cpu.sh',
            ['mesh_score.py','--site',a.site,'--prior',a.prior,'--result',a.result],C.OUT/'patch_z'/f'{a.site}__{a.prior}__{a.result}.json'),
        ('fates',C.REPO/'scripts/phd/main_losstrain_v1/run_cpu.sh',
            ['fates.py',a.site,a.prior,a.result],C.OUT/'fates'/a.site/f'{a.prior}__{a.result}.json'),
        ('axes',C.REPO/'scripts/phd/main_losstrain_v1/run_axes.sh',
            ['axes_measure.py',a.site,a.prior,a.result],C.REPO/'docs/experiments/phd/main_losstrain_v1/tables/axes'/f'{a.site}__{a.prior}__{a.result}.json')]
    receipts=[]
    for name,script,args,dest in calls:
        if dest.exists():
            data=json.loads(dest.read_text());assert data.get('status','PASS')=='PASS'
            receipts.append(dict(step=name,reuse_own_completed=True,path=str(dest),sha256=C.sha(dest)));continue
        cmd=['bash',str(script),tag+'-'+name,*args];start=time.monotonic()
        with (unit/('measure_'+name+'.log')).open('w') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
        row=dict(step=name,exit_code=rc,seconds=time.monotonic()-start,command=cmd,path=str(dest));receipts.append(row)
        C.save(unit/'measure_progress.json',dict(steps=receipts,scientific_verdict=None))
        assert rc==0 and dest.exists(),name+' measurement failed; see run log'
        assert json.loads(dest.read_text()).get('status','PASS')=='PASS'
        print(a.site,a.prior,a.result,name,'PASS',flush=True)
    C.save(unit/'measure_PASS.json',dict(at=C.now(),steps=receipts,scientific_verdict=None))

if __name__=='__main__':main()
