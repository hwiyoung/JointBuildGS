"""Finish the current training, then hand the serial queue to validated tiled TSDF.
Host stdlib only. No active training is terminated or restarted.
"""
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import continue_resource_v1 as Q


def main():
    root = Q.ROOT
    check = Q.OUT / 'checks/tiled_post_v1'
    assert Q.read(check / 'validation.json')['status'] == 'PASS'
    assert Q.read(root / 'training_STOP.json')['status'] == 'OPERATIONAL_QUEUE_HANDOFF'
    with (root / 'orchestrator.lock').open('a') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                Q.save(check / 'handoff_state.json', dict(at=Q.F.now(), status='WAITING_FOR_INFLIGHT_TRAINING', scientific_verdict=None))
                time.sleep(10)
        state = Q.read(root / 'state.json')
        assert not state['gpu_jobs'] and state['cpu_measurement'] is None
        stop = Q.read(root / 'post_STOP.json')
        assert stop['stage'] == 'post' and stop['attempt'] == 3
        unit = Q.F.root_of(stop['run'])
        cancellation = Q.read(unit / 'post_attempt_3_CANCELLED.json')
        assert cancellation['status'] == 'CANCELLED_BEFORE_COMPUTATION'
        assert (unit / 'post_attempt_3.log').stat().st_size == 0
        assert not stop['receipt']['resource_failure']
        assert set(state['stops']) == {'training_STOP.json', 'post_STOP.json'}
        history = root / 'history/epoch_3'
        history.mkdir(exist_ok=False)
        for name in ['training_STOP.json', 'post_STOP.json', 'state.json', 'reporter_state.json']:
            path = root / name
            if path.exists():
                shutil.copy2(path, history / name)
        for name in ['training_STOP.json', 'post_STOP.json']:
            assert (root / name).read_bytes() == (history / name).read_bytes()
            (root / name).unlink()
        completed = sum((Q.F.root_of(r) / 'PASS.json').exists() for r in Q.RUNS)
        health = sum((Q.F.root_of(r) / 'training_health_STOP.json').exists() for r in Q.RUNS)
        Q.save(root / 'resume_epoch_4.json', dict(status='AUTHORIZED_EXISTING_ORDER', at=Q.F.now(),
            authority='User requested a memory remedy. Actual-input geometry, colours, triangle order and existing scoring equivalence passed; loss, arms and training settings unchanged.',
            validation_sha256=Q.F.sha(check / 'validation.json'), completed_models=completed,
            health_stopped_arms=health, admit_post_before_new_training=True, remove_or_add_arm=False,
            loss_scoring_training_settings_and_stop_thresholds_unchanged=True,
            operational_cancellation=str(unit / 'post_attempt_3_CANCELLED.json'), scientific_verdict=None))
        Q.validate(4)
    command = [sys.executable, '-u', str(Path(Q.__file__).resolve()), '--resume-epoch', '4']
    with (root / 'orchestrator_epoch_4.log').open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    Q.save(root / 'orchestrator_epoch_4_launch.json', dict(at=Q.F.now(), pid=process.pid, command=command,
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Q.REPO, text=True).strip(), scientific_verdict=None))
    Q.save(check / 'handoff_state.json', dict(at=Q.F.now(), status='RESUMED_EPOCH_4', pid=process.pid, scientific_verdict=None))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        Q.save(Q.OUT / 'checks/tiled_post_v1/handoff_error.json', dict(at=Q.F.now(), error=repr(error), scientific_verdict=None))
        raise
