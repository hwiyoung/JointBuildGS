"""Finish interrupted posts once, serialized across the two training callbacks."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from gpu_job import O, R, D, now, dump
from add2_host import event

ROOT = O/'queue/recovery_20261106'
PENDING = [('R1rep_b10', 'ALS', 'fix'), ('R1rep_b10', 'LoD2', 'fix'),
           ('B173nb_b10', 'ALS', 'fix'), ('B0_b10', 'ALS', 'A2'),
           ('R1rep_b10', 'ALS', 'A2')]


def cpu(tag, script, *args):
    for attempt in [1, 2]:
        name = f'recovery-{os.getpid()}-{tag}-a{attempt}'
        command = ['bash', str(R/'scripts/phd/main_gtjudge_v1/run_cpu.sh'),
                   name, script, *map(str, args)]
        log = O/'logs'/(name+'.host.log')
        with log.open('w') as output:
            rc = subprocess.run(command, cwd=R, stdout=output, stderr=subprocess.STDOUT).returncode
        dump(ROOT/'steps'/(name+'.json'), dict(at=now(), command=command, exit_code=rc,
             log=str(log), scientific_verdict=None))
        if rc == 0:
            return
    raise RuntimeError(f'{tag}: same-settings retry failed; see {log}')


def mesh(site, prior, arm):
    stem = f'{site}__{prior}__{arm}'
    root = O/'meshes'/stem
    wd = root/'final_work'
    if (root/'final.json').exists():
        return
    assert (O/'renders'/stem/'receipt.json').exists(), 'render not complete'
    for step, sentinel in [('prepare', wd/'inputs/meta.json'), ('plan', wd/'plan/layout.json')]:
        if not sentinel.exists():
            cpu(stem+'-'+step, 'add2_mesh.py', site, prior, arm, step)
    for tile in json.loads((wd/'plan/layout.json').read_text())['tiles']:
        k = tile['k']
        if (wd/'tiles'/f'tile{k}.json').exists():
            continue
        partial = wd/'tiles'/f'tile{k}.npz'
        if partial.exists():
            saved = ROOT/'partial_files'/stem/partial.name
            saved.parent.mkdir(parents=True, exist_ok=True)
            assert not saved.exists(), 'partial already preserved; inspect new failure'
            partial.rename(saved)
            dump(saved.with_suffix('.json'), dict(at=now(), original_path=str(partial),
                preserved_path=str(saved), bytes=saved.stat().st_size,
                reason='tile NPZ without completion receipt after ENOSPC', scientific_verdict=None))
        cpu(stem+f'-tile{k}', 'add2_mesh.py', site, prior, arm, f'tile:{k}')
    if not (wd/'merged.json').exists():
        if arm == 'fix' and (site, prior) in [('R1rep_b10', 'LoD2'), ('B173nb_b10', 'ALS')]:
            cpu(stem+'-merge', 'recovery_merge.py', site, prior)
        else:
            cpu(stem+'-merge', 'add2_mesh.py', site, prior, arm, 'merge')
    cpu(stem+'-finish', 'add2_mesh.py', site, prior, arm, 'finish')


def post(site, prior, arm):
    stem = f'{site}__{prior}__{arm}'
    mark = O/'queue/addendum2/post'/(stem+'.json')
    if mark.exists():
        return
    family = 'fix' if arm == 'fix' else 'gt' if arm == 'A1' else 'gtfs'
    result = json.loads((O/'runs'/site/f'{family}_{prior}_s0/receipt.json').read_text())
    score = O/'scenes'/f'{site}__{prior}'/'distances'/f'{arm}.json'
    if result['status'] == 'TRAINING_COMPLETE_30000':
        mesh(site, prior, arm)
        if not score.exists():
            cpu(stem+'-score', 'score_new.py', site, prior, arm)
        cpu(stem+'-metrics', 'recovery_metrics.py', site, prior, arm)
        if arm == 'fix':
            detail = D/'tables/addendum2/fix'/f'{site}__{prior}_risks_and_strata.json'
            if not detail.exists():
                cpu(stem+'-details', 'add2_fix_results.py', site, prior)
            folder, infix = D/'figures/addendum2', 'fix'
            suffixes = ['section', 'preservation_maps', 'mesh_views']
            if (site, prior) == ('R1rep_b10', 'ALS'):
                suffixes.append('object_zoom')
        else:
            folder, infix = D/'figures', arm
            suffixes = ['section', 'preservation_maps', 'mesh_views']
        if not all((folder/f'{site}__{prior}_{infix}_{s}.png').exists() for s in suffixes):
            cpu(stem+'-figures', 'recovery_figures.py', site, prior, arm)
        # The requested one-time decode check; scientific/visual judgment is not inferred.
        cpu(stem+'-decode', 'recovery_verify.py', site, prior, arm)
    subprocess.run([sys.executable, str(R/'scripts/phd/main_gtjudge_v1/add2_publish.py'),
                    'run', site, prior, arm], cwd=R, check=True)
    record = dict(at=now(), training_status=result['status'], mesh_scored=score.exists(),
                  recovered=True, scientific_verdict=None)
    dump(mark, record)
    dump(ROOT/'post'/(stem+'.json'), record)
    event('POST_FINISHED', job=[site, prior, arm], recovery=True)


def main(*job):
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT/'cpu.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Adopt the one repair started interactively; never overlap heavy CPU jobs.
        active = subprocess.run(['docker', 'inspect', '--type', 'container', '--format', '{{.Id}}',
            'jbgs-gtjudge-recovery-merge-R1'], capture_output=True, text=True)
        if active.returncode == 0:
            subprocess.run(['docker', 'wait', active.stdout.strip()], capture_output=True, text=True)
        for task in [tuple(job)] if job else PENDING:
            event('RECOVERY_POST_STARTED', job=task)
            try:
                post(*task)
            except Exception as error:
                record = dict(at=now(), job=task, status='POSTPROCESSING_ERROR',
                              error=repr(error), traceback=traceback.format_exc(), scientific_verdict=None)
                dump(ROOT/'errors'/('__'.join(task)+'.json'), record)
                event('RECOVERY_POST_ERROR', **{k: v for k, v in record.items() if k != 'at'})
                with (D/'issues.md').open('a') as handle:
                    handle.write(f'- {now()}: 복구 후처리 {task}: {error!r}. 다른 작업은 계속; 실패 기록 queue/recovery_20261106/errors.\n')
                traceback.print_exc()
                # The ordered one-retry stop remains explicit. Do not leave the
                # bundle watcher waiting forever or treat missing metrics as zero.
                try:
                    subprocess.run([sys.executable, str(R/'scripts/phd/main_gtjudge_v1/add2_publish.py'),
                                    'run', *task], cwd=R, check=True)
                    s, p, a = task
                    family = 'fix' if a == 'fix' else 'gt' if a == 'A1' else 'gtfs'
                    training = json.loads((O/'runs'/s/f'{family}_{p}_s0/receipt.json').read_text())
                    dump(O/'queue/addendum2/post'/('__'.join(task)+'.json'),
                         dict(at=now(), status='NO_RESULT_POSTPROCESSING',
                              training_status=training['status'],
                              mesh_scored=(O/'scenes'/f'{s}__{p}'/'distances'/f'{a}.json').exists(),
                              figures_complete=False, error=repr(error), scientific_verdict=None))
                except Exception:
                    traceback.print_exc()
        dump(ROOT/('worker_'+str(os.getpid())+'.json'), dict(at=now(), status='WORKER_FINISHED',
             requested_job=job or PENDING, scientific_verdict=None))


if __name__ == '__main__':
    main(*sys.argv[1:])
