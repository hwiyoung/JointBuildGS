"""Resume only the two ENOSPC-interrupted arms, using their one allowed retry."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from gpu_job import O, R, D, train, dump, now
from add2_host import event
from add2_queue import render


def main(gpu, arm):
    site, prior = 'B0_b10', 'LoD2'
    name = 'gt_LoD2_s0' if arm == 'A1' else 'gtfs_LoD2_s0'
    run = O / 'runs' / site / name
    audit = O / 'queue/recovery_20261106' / name
    audit.mkdir(parents=True, exist_ok=True)
    first = run / 'attempt1'
    receipt = first / 'receipt.json'
    assert not (run / 'receipt.json').exists()
    assert not (run / 'attempt2').exists(), 'one retry already exists'
    assert receipt.exists() and receipt.stat().st_size == 0
    assert not (first / 'TRAINING_COMPLETE.json').exists()
    assert not (first / 'model/target_monitor/STOP.json').exists()
    with (first / 'train.log').open('rb') as stream:
        stream.seek(max(0, (first / 'train.log').stat().st_size - 16384))
        tail = stream.read()
    assert b'No space left on device' in tail
    (audit / 'original_empty_receipt.bin').write_bytes(receipt.read_bytes())
    dump(audit / 'recovery.json', dict(
        at=now(), reason='ENOSPC interrupted training and left an empty receipt',
        original_receipt_sha256=hashlib.sha256(b'').hexdigest(),
        original_launch=json.loads((first / 'launch.json').read_text()),
        log_tail_sha256=hashlib.sha256(tail).hexdigest(),
        action='record failed attempt1; unchanged gpu_job.train executes attempt2',
        settings_changed=False, scientific_verdict=None))
    dump(receipt, dict(at=now(), attempt=1, status='EXECUTION_ERROR',
        model='/gtjudge/' + str((first / 'model').relative_to(O)),
        exit_code=None, seconds=None, health=None,
        recovered_from='empty receipt and ENOSPC traceback; original exit code unavailable',
        scientific_verdict=None))
    with (D / 'issues.md').open('a') as stream:
        stream.write(f'- {now()}: B0 LoD2 {arm} attempt1은 ENOSPC로 중단되고 receipt가 0바이트로 남음. '
                     '빈 원본을 별도 보존하고 실행 오류 기록을 복구; 동일 설정의 허용된 attempt2를 실행한다.\n')
    stop = threading.Event()

    def health_event():
        path = run / 'attempt2/model/target_monitor/health_7000.json'
        while not stop.wait(60):
            if path.exists():
                event('HEALTH_7000', path=str(path), value=json.loads(path.read_text()))
                return

    threading.Thread(target=health_event, daemon=True).start()
    event('TRAINING_STARTED', gpu=int(gpu), job=[site, prior, arm], recovery=True)
    result = train(int(gpu), site, prior, arm)
    stop.set()
    event('TRAINING_FINISHED', gpu=int(gpu), job=[site, prior, arm],
          status=result['status'], recovery=True)
    rendered = render(int(gpu), (site, prior, arm), result)
    dump(audit / 'training_done.json', dict(at=now(), status=result['status'],
        rendered=rendered, scientific_verdict=None))
    # Each completed arm invokes the same recovery postprocessor in a new process.
    # A filesystem lock serializes it with the outstanding CPU work.
    subprocess.run([sys.executable, str(R / 'scripts/phd/main_gtjudge_v1/recovery_post.py'),
                    site, prior, arm], cwd=R, check=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
