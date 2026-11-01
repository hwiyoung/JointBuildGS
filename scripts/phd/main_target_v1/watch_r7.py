"""Serialize shared TSDF work; baseline gates precede pilot gates."""
import fcntl,json,os,subprocess,time
from pathlib import Path
from run_pilot_r7 import OUT,PH,REPO,stamp,dump,stop_both
S=REPO/'scripts/phd/main_target_v1';R=OUT/'r7'
def call(tag,args):
    env=dict(os.environ,TARGET_LANE='r7-mesh',IMG='jointbuildgs:geogs-conf-guided-v1',MEM='40',CPUS='8')
    with (R/(tag+'_driver.log')).open('x') as f:rc=subprocess.run(['bash',str(S/'run_cpu.sh'),tag,*args],env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    dump(R/(tag+'_receipt.json'),dict(at=stamp(),exit_code=rc,scientific_verdict=None))
    if rc:stop_both(dict(reason='postprocessing_execution_error',tag=tag,exit_code=rc));raise RuntimeError((tag,rc))
def main():
    for baseline in [True,False]:
        for prior in ['ALS','LoD2']:
            name=f'base7k_B173nb_b10_{prior}_s0' if baseline else f'tg_B173nb_b10_{prior}_s0_r7';root=R/('baselines' if baseline else 'runs')/name
            while not (root/'model/check7000/coverage.json').exists() or not (R/'targets'/f'B173nb_b10_{prior}.npz').exists():time.sleep(5)
            if not baseline:
                while not (root/'model/jbgs_complete/iteration_7000/receipt.json').exists():time.sleep(5)
            lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
            while int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))/1024**2<48:time.sleep(5)
            call(('base7k' if baseline else 'post7000')+'-r7-'+prior,['post7000_r7.py','run','B173nb_b10',prior]+(['--baseline'] if baseline else []));lock.close()
            if (R/'STOP_BOTH.json').exists():stop_both('r7 geometry stop')
            dump(R/'watch_status.json',dict(at=stamp(),last_completed=name,scientific_verdict=None))
    print('R7_POST_COMPLETE',flush=True)
if __name__=='__main__':main()
