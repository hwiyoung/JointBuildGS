"""Operational handoff: finish inflight training, then deliver eight scored arms.

Host standard-library orchestration; existing scientific commands run in Docker.
Only this driver's two temporary admission markers may be archived and cleared.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import continue_resource_v1 as Q

ROOT = Q.OUT / 'checks/analysis_delivery_priority_v1'
CONFIG = Q.REPO / 'configs/phd/main_losstrain_v1/analysis_delivery_priority_v1.json'
MARKERS = ['training_STOP.json', 'post_STOP.json']
STATUS = 'OPERATIONAL_ANALYSIS_DELIVERY_HANDOFF'


def record(status, **data):
    Q.save(ROOT / 'state.json', dict(at=Q.F.now(), status=status, **data, scientific_verdict=None))


def request():
    ROOT.mkdir(parents=True, exist_ok=True)
    assert not any((Q.ROOT / n).exists() for n in MARKERS + ['measure_STOP.json'])
    state = Q.read(Q.ROOT / 'state.json')
    assert not any(v['kind'] != 'training' for v in state['gpu_jobs'].values())
    assert state['cpu_measurement'] is None
    event = dict(at=Q.F.now(), status=STATUS, owner='analysis_delivery_priority_v1',
                 authority=Q.read(CONFIG)['authority'], training_stop_increment=0,
                 running_jobs_untouched=state['gpu_jobs'], scientific_verdict=None)
    Q.save(ROOT / 'request.json', event)
    for name in MARKERS:
        with (Q.ROOT / name).open('x') as f:
            json.dump(event, f, ensure_ascii=False, indent=2)
            f.write('\n')
    record('WAITING_FOR_INFLIGHT_TRAINING', running_jobs=state['gpu_jobs'])


def cpu(tag, script, *args, reuse=None):
    if reuse is not None and reuse.exists():
        assert Q.read(reuse).get('status', 'PASS') == 'PASS'
        return dict(reused=str(reuse), sha256=Q.F.sha(reuse))
    log = ROOT / (tag + '.log')
    assert not log.exists(), f'preserve previous log before retry: {log}'
    command = ['bash', str(Q.REPO / 'scripts/phd/main_losstrain_v1/run_cpu.sh'),
               'analysis-' + tag, script, *args]
    started = time.monotonic()
    with log.open('x') as f:
        rc = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT).returncode
    result = dict(command=command, exit_code=rc, seconds=time.monotonic()-started, log=str(log))
    Q.save(ROOT / (tag + '.json'), result)
    assert rc == 0, f'{script} failed; inspect {log}'
    return result


def wait_memory():
    stable = None
    while True:
        available = Q.memory_available_gib()
        minimum=Q.policy_for(Q.OUT)['host_available_GiB']
        if available < minimum:
            stable = None
        elif stable is None:
            stable = time.monotonic()
        seconds = 0 if stable is None else time.monotonic()-stable
        record('WAITING_FOR_POST_MEMORY', available_GiB=available, required_GiB=minimum, stable_seconds=seconds)
        if seconds >= 60:
            return
        time.sleep(5)


def run(resume_readout=False):
    cfg = Q.read(CONFIG)
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'driver.lock').open('a') as driver, (Q.ROOT / 'orchestrator.lock').open('a') as lock:
        fcntl.flock(driver, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert Q.read(ROOT / 'request.json')['status'] == STATUS
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                record('WAITING_FOR_INFLIGHT_TRAINING', running_jobs=Q.read(Q.ROOT / 'state.json')['gpu_jobs'])
                time.sleep(10)
        state = Q.read(Q.ROOT / 'state.json')
        assert not state['gpu_jobs'] and state['cpu_measurement'] is None
        history = Q.ROOT / 'history/epoch_4_analysis_handoff'
        if resume_readout:
            assert history.exists() and state['status']=='PRIORITY_ANALYSIS_DELIVERY'
            assert state['priority_driver']==str(ROOT/'state.json')
            assert not list(Q.ROOT.glob('*_STOP.json')), 'preserve any new error'
            assert not state['stops']
            old=Q.ROOT/'validation_epoch_5.json'
            if old.exists():
                archived=ROOT/('validation_before_resume_'+Q.F.sha(old)[:12]+'.json')
                if not archived.exists():shutil.copy2(old,archived)
            Q.validate(5)
        else:
            assert set(state['stops']) == set(MARKERS)
            for name in MARKERS:
                assert Q.read(Q.ROOT / name) == Q.read(ROOT / 'request.json'), 'a new error must remain stopped'
            Q.validate(5)
            history.mkdir(exist_ok=False)
            for name in [*MARKERS, 'state.json', 'reporter_state.json']:
                if (Q.ROOT / name).exists():
                    shutil.copy2(Q.ROOT / name, history / name)
            for name in MARKERS:
                assert (Q.ROOT / name).read_bytes() == (history / name).read_bytes()
                (Q.ROOT / name).unlink()
        record('PROCESSING_PRIORITY_READOUT', completed_training_reused=state['training_complete'])
        Q.save(Q.ROOT / 'state.json', dict(**{k:v for k,v in state.items() if k not in ['at','status','stops','priority_driver']},
               at=Q.F.now(), status='PRIORITY_ANALYSIS_DELIVERY', stops=[], priority_driver=str(ROOT/'state.json')))
        site, prior = cfg['new_readout_site'], cfg['prior']
        cpu('nojudge-cells', 'split_fate_cells.py', site, prior, 'nojudge_ALS_s0',
            reuse=Q.OUT/'fate_cell_split'/site/'ALS__nojudge_ALS_s0.json')
        for variant in cfg['variants']:
            r = dict(site=site, prior=prior, variant=variant)
            unit = Q.F.root_of(r)
            assert (unit / 'PASS.json').exists()
            while not (unit / 'post_stage_PASS.json').exists():
                wait_memory()
                record('MAIN_MESH_RUNNING', run=r)
                assert Q.next_post_mode(unit) == 'post'
                if not Q.post_one(r, 0):
                    raise RuntimeError('Postprocessing reached preserved stop; no further retry')
            result = unit.name
            record('CORE_SCORING', run=r)
            cpu(variant+'-mesh', 'mesh_score.py', '--site', site, '--prior', prior, '--result', result,
                reuse=Q.OUT/'patch_z'/f'{site}__{prior}__{result}.json')
            cpu(variant+'-fates', 'fates.py', site, prior, result,
                reuse=Q.OUT/'fates'/site/f'{prior}__{result}.json')
            cpu(variant+'-cells', 'split_fate_cells.py', site, prior, result,
                reuse=Q.OUT/'fate_cell_split'/site/f'{prior}__{result}.json')
            Q.save(ROOT/(variant+'_core_PASS.json'), dict(at=Q.F.now(), run=r, scientific_verdict=None))
        for script in ['runtime_report.py', 'patch_tables.py', 'side_tables.py', 'comparison_tables.py',
                       'fate_tables.py', 'photo_tables.py', 'monitor_tables.py']:
            cpu(Path(script).stem, script)
        cpu('B0-figures', 'result_figures.py', '--site', site, '--prior', prior)
        cpu('eight-report', 'eight_arm_report.py')
        record('READY_FOR_VISUAL_REVIEW', trained_scored_arms=8,
               release_requires='verified eight-arm report, visual review and delivered archive receipt')
        while not (ROOT/'release.json').exists():
            time.sleep(10)
        release = Q.read(ROOT/'release.json')
        assert release['status'] == 'VERIFIED_HANDOVER_READY' and release['scored_arms'] == 8
        assert Q.F.sha(Path(release['archive'])) == release['archive_sha256']
        Q.save(Q.ROOT/'resume_epoch_5.json', dict(status='AUTHORIZED_EXISTING_ORDER', at=Q.F.now(),
               authority=cfg['authority'], admit_post_before_new_training=False,
               priority_training=cfg['next_training_priority'], analysis_delivery=str(ROOT/'release.json'),
               loss_scoring_arms_training_settings_unchanged=True, scientific_verdict=None))
        Q.save(Q.ROOT/'next_analysis_priority.json',dict(enabled=True,**cfg['next_training_priority'],
               authority=cfg['authority'],sequence='finish four R1 ALS trainings, then their post and scoring before unrelated new work',
               training_settings_and_arm_membership_unchanged=True,scientific_verdict=None))
    command = [sys.executable, '-u', str(Path(Q.__file__).resolve()), '--resume-epoch', '5']
    with (Q.ROOT/'orchestrator_epoch_5.log').open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
    Q.save(Q.ROOT/'orchestrator_epoch_5_launch.json', dict(at=Q.F.now(), pid=process.pid, command=command,
           commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Q.REPO,text=True).strip(),scientific_verdict=None))
    record('DELIVERED_AND_RESUMED', pid=process.pid, release=release)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--request', action='store_true')
    ap.add_argument('--resume-readout', action='store_true')
    args = ap.parse_args()
    if args.request:
        request()
    else:
        try:
            run(resume_readout=args.resume_readout)
        except Exception as error:
            record('ERROR', error=repr(error))
            raise
