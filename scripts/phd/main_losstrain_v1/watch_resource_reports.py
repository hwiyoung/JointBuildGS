"""Refresh durable observations and the first-batch interim as results arrive.
Never trains, changes scores, approves a figure, or clears a stop. Docker readouts
share the TSDF memory lock. A completed interim awaits actual visual inspection.
"""
import fcntl,json,subprocess,time
from pathlib import Path
import train_full as F
from post_admission import memory_available_gib
from continue_resource_v1 import ROOT,RUNS,save,read
SCRIPTS=F.REPO/'scripts/phd/main_losstrain_v1'
DOC=F.REPO/'docs/experiments/phd/main_losstrain_v1'

def cpu(tag,script,*args):
    cmd=['bash',str(SCRIPTS/'run_cpu.sh'),tag,script,*args]
    log=ROOT/(tag+'.log')
    with log.open('a') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    if rc:raise RuntimeError(f'{script} exit {rc}; {log}')

def refresh():
    for script in ['runtime_report.py','patch_tables.py','side_tables.py','comparison_tables.py',
            'fate_tables.py','photo_tables.py','monitor_tables.py','interim_report.py','report.py']:
        cpu('resume-'+Path(script).stem,script)

def main():
    with (ROOT/'reporter.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        save(ROOT/'reporter_start.json',dict(at=F.now(),scientific_verdict=None))
        previous=None
        while True:
            state=read(ROOT/'state.json',{});done=[r for r in RUNS if (F.root_of(r)/'PASS.json').exists()]
            if memory_available_gib()>=16:
                for r in done:
                    unit=F.root_of(r);site=r['site'];prior=r['prior'];result=unit.name
                    if not (F.OUT/'opacity_saved'/site/result/'30000.json').exists():
                        cpu('resume-saved-'+site.lower()+'-'+result.lower(),'saved_opacity.py','--site',site,'--prior',prior,'--result',result)
            first_ready=all((F.root_of(r)/'measure_PASS.json').exists() for r in RUNS[:4])
            if first_ready and not (ROOT/'interim_report_generated.json').exists():
                cpu('resume-first-figures','result_figures.py','--site','B173nb_b10','--prior','ALS')
                cpu('resume-first-section','sections.py','--site','B173nb_b10','--prior','ALS')
                cpu('resume-first-render','render_figure.py','--prior','ALS')
                refresh()
                save(ROOT/'interim_report_generated.json',dict(at=F.now(),status='READY_FOR_VISUAL_REVIEW',
                    report=str(DOC/'중간보고_v1.md'),report_sha256=F.sha(DOC/'중간보고_v1.md'),
                    first_four_scored=True,cell_0_and_cell_2_separate=True,visual_review='PENDING',scientific_verdict=None))
            signature=[state.get(k) for k in ['training_complete','post_complete','measurement_complete','stops']]
            if signature!=previous:refresh();previous=signature
            save(ROOT/'reporter_state.json',dict(at=F.now(),observed=signature,first_four_scored=first_ready,
                interim_generated=(ROOT/'interim_report_generated.json').exists(),scientific_verdict=None))
            if (ROOT/'PASS.json').exists():return
            if state.get('stops') and not state.get('gpu_jobs') and state.get('cpu_measurement') is None:return
            time.sleep(30)

if __name__=='__main__':
    try:main()
    except Exception as e:
        save(ROOT/'reporter_error.json',dict(at=F.now(),error=repr(e),scientific_verdict=None));raise
