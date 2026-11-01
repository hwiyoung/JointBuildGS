"""Host stdlib: build each unit's seeds/maps after its immutable judgments exist."""
import json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
def main():
    # Remaining six runs are prepared only after both pilot gates pass.
    for site in ['B173nb_b10']:
        while not all((O/'r7/targets'/f'{site}_{p}.json').exists() or ((O/'r7/targets'/f'{site}_{p}.npz').exists() and (O/'r7/stage0'/f'{site}_{p}.json').exists()) for p in ['ALS','LoD2']):time.sleep(5)
        for kind in ['seeds','maps']:
            tag=f'prepare-{kind}-r7-{site}';env=dict(os.environ,IMG='jointbuildgs:geogs-conf-guided-v1',TARGET_LANE='r7-prepare',MEM='12')
            with (O/'r7'/f'{tag}.log').open('x') as f:r=subprocess.run(['bash',str(R/'scripts/phd/main_target_v1/run_cpu.sh'),tag,f'prepare_{kind}_r7.py',site],env=env,stdout=f,stderr=subprocess.STDOUT)
            (O/'r7'/f'{tag}.json').write_text(json.dumps(dict(exit_code=r.returncode,scientific_verdict=None))+'\n')
            if r.returncode:raise SystemExit(r.returncode)
        print('PREPARED_R7',site,flush=True)
if __name__=='__main__':main()
