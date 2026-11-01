"""Launch the second pilot as soon as its own inputs pass; serialize cached CPU mesh checks."""
import concurrent.futures,fcntl,json,os,subprocess,time,datetime as dt
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];PH=REPO.parent/'JointBuildGS-artifacts/phase-payloads/phd'
OUT=PH/'main_target_v1/PHD-MAIN-TARGET-v1';SCRIPT=REPO/'scripts/phd/main_target_v1'
def stamp():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def memory():
    return int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))/(1024**2)
def lod2():
    while not (OUT/'r2/verification/stage1_B173nb_b10_LoD2.json').exists():
        if (OUT/'r4/STOP_BOTH.json').exists():return 'NOT_STARTED_SHARED_STOP'
        time.sleep(3)
    with (OUT/'r4/pilot_LoD2_driver.log').open('x') as f:
        rc=subprocess.run(['python',str(SCRIPT/'run_pilot_r4.py'),'1','LoD2'],stdout=f,stderr=subprocess.STDOUT).returncode
    return dict(exit_code=rc)
def post(prior):
    lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
    while memory()<56:
        dump(OUT/'r4/post_wait.json',dict(at=stamp(),prior=prior,reason='MemAvailable below 56GiB',available_GiB=memory()))
        time.sleep(10)
    env=dict(os.environ,TARGET_LANE='r4-mesh',IMG='jointbuildgs:geogs-conf-guided-v1',MEM='40',CPUS='8')
    command=['bash',str(SCRIPT/'run_cpu.sh'),f'post7000-r4-{prior}','post7000_r4.py','run','B173nb_b10',prior]
    with (OUT/'r4'/f'post7000_{prior}_driver.log').open('x') as f:rc=subprocess.run(command,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    dump(OUT/'r4'/f'post7000_{prior}_receipt.json',dict(at=stamp(),exit_code=rc,scientific_verdict=None));return rc
def main():
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        second=pool.submit(lod2);done=set();working=None
        while len(done)<2:
            if working and working[1].done():
                prior,f=working;done.add(prior);print('POST_COMPLETE',prior,f.result(),flush=True);working=None
            for prior in ['ALS','LoD2']:
                if prior in done or working:continue
                model=OUT/'r4/runs'/f'tg_B173nb_b10_{prior}_s0/model'
                if (model/'check7000/coverage.json').exists():working=(prior,pool.submit(post,prior));print('POST_START',prior,flush=True)
                elif (OUT/'r4/STOP_BOTH.json').exists() and (prior=='ALS' or second.done()):
                    done.add(prior);print('NO_7000_MODEL',prior,flush=True)
            dump(OUT/'r4/continuation_status.json',dict(at=stamp(),post_done=sorted(done),post_running=working[0] if working else None,
                second_pilot_done=second.done(),joint_stop=(OUT/'r4/STOP_BOTH.json').exists(),scientific_verdict=None))
            if len(done)<2:time.sleep(5)
        print('SECOND_PILOT_RESULT',second.result(),flush=True)

if __name__=='__main__':main()
