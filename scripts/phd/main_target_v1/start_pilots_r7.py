"""Host coordination of completed CPU prerequisites and the two authorized r7 pilots."""
import json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1';S=R/'scripts/phd/main_target_v1'
def ready():
    required=[O/'r7/targets'/f'{site}_{p}.npz' for site in ['B0_b10','B173nb_b10','B173_b0','R1rep_b10'] for p in ['ALS','LoD2']]
    required += [O/root/f'{p}.complete.json' for root in ['r7/stage0/development','holdout/r7/stage0'] for p in ['ALS','LoD2']]
    required += [O/'r7/stage1'/f'B173nb_b10_{p}/maps/index.json' for p in ['ALS','LoD2']]
    required += [O/'r7/baselines'/f'base7k_B173nb_b10_{p}_s0/model/check7000/coverage.json' for p in ['ALS','LoD2']]
    required += [R/'docs/experiments/phd/main_target_v1/tables/disappearance_areas_r7.json']
    required += [O/'r7/stage0'/f'{site}_{p}.json' for site in ['B0_b10','B173nb_b10','B173_b0','R1rep_b10'] for p in ['ALS','LoD2']]
    required += [O/'r7/verification/unit.json',O/'r7/verification/baseline_source.json']
    return all(p.exists() for p in required)
def call(name):
    receipt=O/'r7'/f'{name}_receipt.json'
    if receipt.exists():
        if json.loads(receipt.read_text())['exit_code']==0:return
        for suffix in ['_receipt.json','_driver.log']:
            old=O/'r7'/(name+suffix);dest=old.with_name(name+'_failed_1'+suffix);assert not dest.exists();old.rename(dest)
    env=dict(os.environ,TARGET_LANE='r7-preflight',IMG='jointbuildgs:geogs-conf-guided-v1',MEM='12')
    with (O/'r7'/f'{name}_driver.log').open('x') as f:r=subprocess.run(['bash',str(S/'run_cpu.sh'),name.replace('_','-'),name+'.py'],env=env,stdout=f,stderr=subprocess.STDOUT)
    (O/'r7'/f'{name}_receipt.json').write_text(json.dumps(dict(exit_code=r.returncode,scientific_verdict=None))+'\n')
    if r.returncode:raise SystemExit(r.returncode)
def main():
    while not ready():
        if (O/'r7/STOP_BOTH.json').exists():raise SystemExit('prior r7 execution stop')
        time.sleep(5)
    call('verify_disappearance_r7');call('accuracy_disappearance_r7');call('verify_runtime_r7')
    assert json.loads((O/'r7/verification/unit.json').read_text())['status']=='PASS_R7_UNIT'
    children=[]
    for gpu,prior in [('0','ALS'),('1','LoD2')]:
        f=(O/'r7'/f'pilot_{prior}_driver.log').open('x');proc=subprocess.Popen([sys.executable,'-u',str(S/'run_pilot_r7.py'),gpu,prior],stdout=f,stderr=subprocess.STDOUT);children.append((prior,proc,f))
    for prior,proc,f in children:
        rc=proc.wait();f.close();print('R7_PILOT_TERMINAL',prior,rc,flush=True)
if __name__=='__main__':main()
