"""Prepare model-only fate readouts while the unchanged TSDF gate waits.

Uses the same serial CPU wrapper/TSDF lock and existing classifications.
The priority mesh driver reuses these completed outputs when it reaches them.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime

REPO=Path(__file__).resolve().parents[3]
OUT=REPO.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1'
ROOT=OUT/'checks/analysis_delivery_priority_v1'


def main():
    rows=[]
    for variant in ['lt_fixgt','lt_dyngt','lt_dynsoft','lt_dynnow']:
        result=variant+'_ALS_s0'
        for script,folder in [('fates.py','fates'),('split_fate_cells.py','fate_cell_split')]:
            destination=OUT/folder/'B0_b10'/('ALS__'+result+'.json')
            if destination.exists():
                assert json.loads(destination.read_text())['status']=='PASS'
                rows.append(dict(result=result,step=script,reused=str(destination)))
                continue
            tag='precompute-'+variant+'-'+folder
            command=['bash',str(REPO/'scripts/phd/main_losstrain_v1/run_cpu.sh'),tag,
                     script,'B0_b10','ALS',result]
            with (ROOT/(tag+'.log')).open('x') as log:
                rc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
            rows.append(dict(result=result,step=script,exit_code=rc,command=command))
            status=dict(at=datetime.now().astimezone().isoformat(),status='RUNNING' if rc==0 else 'ERROR',
                        steps=rows,scientific_verdict=None)
            (ROOT/'fate_precompute.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
            assert rc==0 and destination.exists()
    status=dict(at=datetime.now().astimezone().isoformat(),status='PASS',steps=rows,
                same_scoring_and_shared_tsdf_lock=True,scientific_verdict=None)
    (ROOT/'fate_precompute.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    print('B0 ALS four fate readouts complete',flush=True)


if __name__=='__main__':main()
