"""Host stdlib driver: read the completed meshes before unrelated GPU readouts.

Every project computation uses the existing Docker CPU wrapper and scoring code.
This does not create measure_PASS or claim completion of the remaining axes work.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime

REPO = Path(__file__).resolve().parents[3]
OUT = REPO.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1'
SCRIPTS = Path(__file__).resolve().parent
ROOT = OUT/'checks/requested_interim_readout_v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ROOT.mkdir(exist_ok=True)
    with (ROOT/'driver.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        cfgpath = REPO/'configs/phd/main_losstrain_v1/requested_interim_readout_v1.json'
        cfg = json.loads(cfgpath.read_text())
        site, prior = cfg['site'], cfg['prior']
        inputs, steps = [], []
        for variant in cfg['variants']:
            result = f'{variant}_{prior}_s0'
            unit = OUT/'runs'/site/result
            for name in ['PASS.json', 'post_stage_PASS.json']:
                p = unit/name
                assert p.exists(), f'incomplete input: {p}'
                inputs.append(dict(path=str(p), sha256=sha(p)))
        record = dict(task_id=cfg['task_id'], started_at=datetime.now().astimezone().isoformat(),
                      config_sha256=sha(cfgpath), inputs=inputs, steps=steps,
                      commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                      driver_sha256=sha(__file__), scientific_verdict=None)

        def save(status):
            record.update(status=status, at=datetime.now().astimezone().isoformat())
            tmp = ROOT/'state.tmp'
            tmp.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            tmp.replace(ROOT/'state.json')

        def cpu(tag, script, *args, reuse=None):
            if reuse is not None and reuse.exists():
                assert json.loads(reuse.read_text()).get('status') == 'PASS'
                steps.append(dict(step=tag,reused=str(reuse),sha256=sha(reuse)))
                save('RUNNING')
                return
            cmd=['bash',str(SCRIPTS/'run_cpu.sh'),'requested-'+tag,script,*args]
            started=time.monotonic()
            log=ROOT/(tag+'.log')
            with log.open('a') as f:
                rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
            steps.append(dict(step=tag,command=cmd,exit_code=rc,seconds=time.monotonic()-started,log=str(log)))
            save('RUNNING' if rc==0 else 'ERROR')
            if rc:raise RuntimeError(f'{tag} exit {rc}; inspect {log}')

        save('RUNNING')
        for variant in cfg['variants']:
            result=f'{variant}_{prior}_s0'
            cpu(variant+'-mesh','mesh_score.py','--site',site,'--prior',prior,'--result',result,
                reuse=OUT/'patch_z'/f'{site}__{prior}__{result}.json')
            cpu(variant+'-fates','fates.py',site,prior,result,
                reuse=OUT/'fates'/site/f'{prior}__{result}.json')
            cpu(variant+'-cells','split_fate_cells.py',site,prior,result,
                reuse=OUT/'fate_cell_split'/site/f'{prior}__{result}.json')
        for script in ['runtime_report.py','patch_tables.py','side_tables.py','comparison_tables.py',
                       'fate_tables.py','photo_tables.py']:
            cpu(Path(script).stem,script)
        cpu('maps','result_figures.py','--site',site,'--prior',prior)
        cpu('section','sections.py','--site',site,'--prior',prior)
        cpu('render','render_figure.py','--prior',prior)
        cpu('interim','interim_report.py')
        save('READY_FOR_VISUAL_REVIEW')
        print('Requested interim ready for visual review; other post/axes work remains.',flush=True)


if __name__ == '__main__':
    main()
