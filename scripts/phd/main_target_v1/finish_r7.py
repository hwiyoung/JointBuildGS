"""Host coordinator for authorized checkpoint diagnostics and report preparation."""
import fcntl,json,os,subprocess,sys,time
from pathlib import Path
from run_pilot_r7 import OUT,PH,REPO,stamp,dump
S=REPO/'scripts/phd/main_target_v1';R=OUT/'r7'
def call(tag,args,mem='8'):
    env=dict(os.environ,TARGET_LANE='r7-finish',IMG='jointbuildgs:geogs-conf-guided-v1',MEM=mem,CPUS='4')
    with (R/(tag+'_driver.log')).open('x') as f:rc=subprocess.run(['bash',str(S/'run_cpu.sh'),tag,*args],env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    dump(R/(tag+'_receipt.json'),dict(at=stamp(),exit_code=rc,scientific_verdict=None))
    if rc:raise RuntimeError((tag,rc))
def wait_for(paths,training_required=False):
    while not all(p.exists() for p in paths):
        if training_required and (R/'STOP_BOTH.json').exists():
            runs=[R/'runs'/f'tg_B173nb_b10_{p}_s0_r7/receipt.json' for p in ['ALS','LoD2']]
            if all(p.exists() for p in runs):raise RuntimeError('Stopped before required checkpoint files: '+str([str(p) for p in paths if not p.exists()]))
        time.sleep(5)
def main():
    if '--stage0' in sys.argv:
        wait_for([R/'stage0/accuracy_complete.json',R/'verification/stage0.json'])
        call('stage0-figures-r7',['report_stage0_r7.py'],'8');call('stage0-tables-r7',['report_disappearance_tables_r7.py'],'4');return
    runs={p:R/'runs'/f'tg_B173nb_b10_{p}_s0_r7' for p in ['ALS','LoD2']}
    resume='--resume-post' in sys.argv
    wait_for([run/'model/target_monitor/snapshot_0.npz' for run in runs.values()],True)
    if not resume:call('initial-r7',['verify_initial_r7.py'],'8')
    wait_for([run/'model/jbgs_complete/iteration_7000/receipt.json' for run in runs.values()],True)
    children=[]
    for gpu,prior in ([] if resume else [('0','ALS'),('1','LoD2')]):
        f=(R/f'max-contributor-{prior}_driver.log').open('x');proc=subprocess.Popen([sys.executable,'-u',str(S/'run_diagnostic_gpu_r7.py'),gpu,'max_contributor_r7.py',prior],stdout=f,stderr=subprocess.STDOUT);children.append((prior,proc,f))
    if resume:
        for tag in ['initial-r7','movement-reference-r7']+[f'{kind}-r7-{p}' for kind in ['verify7000','movement'] for p in runs]:assert json.loads((R/(tag+'_receipt.json')).read_text())['exit_code']==0
        for prior in runs:assert json.loads((R/'commands'/f'max_contributor_r7_{prior}/receipt.json').read_text())['exit_code']==0
    else:
        for prior in runs:call('verify7000-r7-'+prior,['verify7000_r7.py',prior],'12')
        for prior in runs:call('movement-r7-'+prior,['report_movement_r7.py',prior],'12')
        call('movement-reference-r7',['report_reference_r7.py'],'8')
    wait_for([R/f'post7000-r7-{p}_receipt.json' for p in runs])
    for prior in runs:assert json.loads((R/f'post7000-r7-{prior}_receipt.json').read_text())['exit_code']==0
    lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
    for prior in runs:call('verify-post-r7-'+prior,['verify_post7000_r7.py',prior],'32')
    lock.close()
    for prior,proc,f in children:
        rc=proc.wait();f.close()
        if rc:raise RuntimeError(('max contributor',prior,rc))
    for prior in runs:
        call('verify-diagnostics-r7-'+prior,['verify_diagnostics_r7.py',prior],'12');call('origin-ratio-r7-'+prior,['origin_ratio_r7.py',prior],'8');call('full-state-r7-'+prior,['verify_full_state_r7.py',prior],'12')
    call('sections-r7',['report_section7000_r7.py'],'12');call('report-r7',['report_r7.py'],'12')
    dump(R/'reports_ready.json',dict(at=stamp(),status='READY_FOR_VISUAL_AND_DELIVERY_AUDIT',scientific_verdict=None));print('R7_REPORTS_READY',flush=True)
if __name__=='__main__':main()
