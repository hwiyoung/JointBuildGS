"""Host-only dependency orchestration; all numerical work runs in containers."""
import json,os,subprocess,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
OUT=REPO.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
S=REPO/'scripts/phd/main_target_v1'


def execute(tag,script,args=(),image='jointbuildgs:dev',memory='12'):
    env=dict(os.environ,TARGET_LANE='r2-chain',IMG=image,MEM=memory,CPUS='4')
    subprocess.run(['bash',str(S/'run_cpu.sh'),tag,script,*args],cwd=REPO,env=env,check=True)


def main():
    for p in [OUT/'r2/stage0/core_stats/complete.json',OUT/'holdout/r2/core_stats/complete.json']:
        while not p.exists():time.sleep(2)
    steps=[('t2-r2','t2_r2.py',()),('targets-r2','experiment_targets_r2.py',()),
           ('targets-deferred-r2','experiment_targets_r2.py',('--deferred',)),
           ('census-r2','judgment_census_r2.py',()),('verify-stage0-r2','verify_stage0_r2.py',()),
           ('report-stage0-r2','report_stage0_r2.py',())]
    for tag,script,args in steps:
        print('BEGIN',tag,flush=True);execute(tag,script,args)
    execute('maps-r2','prepare_maps_r2.py',image='jointbuildgs:geogs-conf-guided-v1',memory='12')
    execute('representative-pixels-r2','verify_representative_pixels_r2.py',memory='4')
    print('STAGE0_AND_MAPS_COMPLETE',flush=True)


if __name__=='__main__':main()
