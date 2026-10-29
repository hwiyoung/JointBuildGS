"""Host stdlib scheduler: existing training terminal evidence plus idle GPU only."""
import fcntl,json,subprocess,time
from datetime import datetime
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
PH=REPO.parent/'JointBuildGS-artifacts/phase-payloads/phd'
OUT=PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1'
DOC=REPO/'docs/experiments/phd/main_meshpatch_v1/interview_v2'
S=REPO/'scripts/phd/main_meshpatch_v1'
def read(p):return json.loads(p.read_text()) if p.exists() else {}
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def update(state,**kw):save(OUT/'interview_v2/gpu_scheduler.json',dict(at=datetime.now().astimezone().isoformat(),status=state,scientific_verdict=None,**kw))
def cpu(tag,*args):return subprocess.run(['bash',str(S/'run_cpu.sh'),tag,*args],cwd=REPO).returncode

def main():
    lock=(OUT/'interview_v2/gpu_scheduler.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    while True:
        if not (OUT/'interview_v2/cpu_queue_finished.json').exists():update('WAIT_PRIORITY_CPU');time.sleep(30);continue
        if read(DOC/'checks/virtual_baseline.json').get('status')!='PASS':update('STOP_BASELINE_UNVERIFIED');return
        cfg=read(REPO/'configs/phd/main_meshpatch_v1/interview_gpu_v1.json')
        far=PH/'main_farpull_v1/PHD-MAIN-FARPULL-v1/runs'
        pending=[n for n in cfg['training_terminal_sources'] if not any((far/n/f).exists() for f in ['PASS.json','STOP_final.json'])]
        if pending:update('WAIT_FARPULL_TRAINING',runs=pending);time.sleep(30);continue
        break
    for row in cfg['targets']:
        if row['existing_mesh']:continue
        short={'B0_b10':'b0','B173nb_b10':'b173','R1rep_b10':'r1'}[row['site']]
        tag=f"virtual-{short}-{row['prefix']}"
        if read(DOC/'status'/(tag+'.json')).get('status')=='PASS':continue
        if read(DOC/'status'/(f"gpu-{short}-{row['prefix']}.json")).get('status')=='FAILED':continue
        while True:
            update('WAIT_OR_RUN_GPU',site=row['site'],prefix=row['prefix'])
            rc=subprocess.run(['bash',str(S/'run_interview_gpu.sh'),row['site'],row['prefix']],cwd=REPO).returncode
            if rc==75:time.sleep(30);continue
            break
        if rc:
            save(DOC/'status'/(f"gpu-{short}-{row['prefix']}.json"),dict(status='FAILED',exit_code=rc,reason='GPU extraction failed or memory guard stopped; no automatic identical retry',scientific_verdict=None))
            with (REPO/'docs/experiments/phd/main_meshpatch_v1/issues.md').open('a') as f:f.write(f"\n- {datetime.now().astimezone().isoformat()} 덧붙임 2 GPU {row['site']} {row['prefix']}: exit {rc}; 상태와 실행 로그 보존.\n")
            continue
        cpu('interview-'+tag,'--large','interview_guard.py',tag,'interview_virtual.py',row['site'],row['prefix'])
        cpu('interview-validation-gpu','interview_validate.py')
        cpu('interview-package-gpu','interview_delivery.py','--package')
    update('FINISHED_ATTEMPTS')
    cpu('interview-package-gpu-final','interview_delivery.py','--package')

if __name__=='__main__':main()
