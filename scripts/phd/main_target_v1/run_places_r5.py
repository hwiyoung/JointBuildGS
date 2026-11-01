"""Serial bounded CPU jobs; retain each execution receipt and stop on errors."""
import subprocess,json,os,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
jobs=[('development','LoD2'),('holdout','ALS'),('holdout','LoD2'),('experiment','ALS'),('experiment','LoD2')]
for split,prior in jobs:
 root=O/'r5/commands'/f'places_{split}_{prior}';root.mkdir(parents=True,exist_ok=False);env=dict(os.environ,TARGET_LANE='r5places',MEM='12',CPUS='4')
 cmd=['bash',str(R/'scripts/phd/main_target_v1/run_cpu.sh'),f'places-{split}-{prior}-r5','stratify_r5.py',split,prior];start=time.time()
 with (root/'run.log').open('x') as f:rc=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 (root/'receipt.json').write_text(json.dumps(dict(exit_code=rc,seconds=time.time()-start,scientific_verdict=None),indent=2)+'\n')
 print(split,prior,rc,flush=True)
 if rc:raise SystemExit(rc)
