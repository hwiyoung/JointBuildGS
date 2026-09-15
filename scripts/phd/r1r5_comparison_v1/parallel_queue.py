"""Adopt a live Docker stage and distribute untouched conditions across two GPUs.

Only the old Python scheduler is paused. Its running container finishes normally;
the old scheduler is retired after that container exits. No checkpoint restart or
training change is involved. One writer owns the combined status file.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
import traceback

from run_queue import Queue, TRAIN_IMAGE, atomic, read


class MemorySlots:
    """FIFO admissions: two 32 GiB jobs, or one 56 GiB extraction."""
    def __init__(self, budget=64, adopted=32):
        self.budget = budget
        self.used = adopted
        self.pending = []
        self.cv = threading.Condition()

    def acquire(self, amount):
        if amount > self.budget:
            raise ValueError('Job exceeds total memory reservation')
        token = object()
        with self.cv:
            self.pending.append(token)
            while self.pending[0] is not token or self.used + amount > self.budget:
                self.cv.wait()
            self.pending.pop(0)
            self.used += amount
            self.cv.notify_all()

    def release(self, amount):
        with self.cv:
            self.used -= amount
            assert self.used >= 0
            self.cv.notify_all()


class Worker(Queue):
    def __init__(self, manager, gpu):
        super().__init__(manager.root)
        self.manager = manager
        self.gpu = str(gpu)
        self.driver = manager.folder / 'source'

    def status(self, state, **kw):
        self.manager.update(self, state, **kw)

    def docker(self, label, out, mounts, image, argv, **kw):
        amount = kw.get('ram', 12)
        self.job = label
        self.status('WAITING_RESERVATION')
        self.manager.memory.acquire(amount)
        try:
            if image == TRAIN_IMAGE and kw.get('gpu'):
                kw['env'] = {**kw.get('env', {}),
                             'PYTORCH_CUDA_ALLOC_CONF': 'backend:cudaMallocAsync',
                             'JBGS_CUDA_ALLOCATOR_OVERRIDE': 'backend:cudaMallocAsync'}
            return super().docker(label, out, mounts, image, argv, **kw)
        finally:
            self.manager.memory.release(amount)

    def run_condition(self, region, branch):
        self.region = region
        try:
            if branch == 'da3':
                self.da3(region)
            else:
                assert read(self.root / region / 'masks/receipt.json')['status'] == 'PASS'
            self.refinement(region, branch)
        except Exception:
            self.manager.fail(self, branch, traceback.format_exc())

    def run(self, adopt=False):
        try:
            if adopt:
                self.manager.finish_adopted(self)
            while True:
                try:
                    region, branch = self.manager.pending.get_nowait()
                except queue.Empty:
                    break
                self.run_condition(region, branch)
            self.region = self.job = None
            self.status('COMPLETE')
        except Exception:
            self.manager.fail(self, 'scheduler', traceback.format_exc())
            self.status('FAILED')


class Manager:
    def __init__(self, root, folder):
        self.root = Path(root).resolve()
        self.folder = Path(folder).resolve()
        self.plan = read(self.folder / 'plan.json')
        self.previous = read(self.folder / 'previous_status.json')
        self.failures = list(self.previous.get('failures', []))
        self.lock = threading.RLock()
        self.memory = MemorySlots()
        self.workers = {}
        self.rows = {}
        self.pending = queue.Queue()
        for condition in self.plan['pending']:
            self.pending.put(condition)
        self.state = 'RUNNING'

    def update(self, worker, state, **kw):
        with self.lock:
            self.rows[worker.gpu] = dict(gpu=worker.gpu, state=state,
                region=worker.region, job=worker.job, **kw)
            active = [v for v in self.rows.values() if v['region']]
            combined = dict(state=self.state,
                region=' | '.join(f"GPU{x['gpu']} {x['region']}" for x in active) or None,
                job=' | '.join(str(x['job']) for x in active) or None,
                workers=list(self.rows.values()),
                jobs=self.previous['jobs'] + [r for w in self.workers.values() for r in w.records],
                failures=self.failures, updated_unix=time.time(), scientific_verdict=None,
                parallel_run=str(self.folder.relative_to(self.root)),
                pending_conditions=self.pending.qsize(), memory_reservation_gib=self.memory.used)
            atomic(self.folder / 'status.json', combined)
            atomic(self.root / 'execution/status.json', combined)

    def fail(self, worker, branch, error):
        with self.lock:
            failure = dict(region=worker.region, branch=branch, job=worker.job,
                           gpu=worker.gpu, error=error)
            self.failures.append(failure)
            atomic(self.folder / f'{worker.region}_{branch}_failure.json',
                   dict(**failure, scientific_verdict=None))
            self.update(worker, 'CONDITION_FAILED')

    def container_running(self):
        p = subprocess.run(['docker', 'inspect', self.plan['container_id'],
                            '--format', '{{.State.Running}}'], text=True, capture_output=True)
        if p.returncode:
            if 'No such' in p.stderr:
                return False  # --rm removes the completed adopted container.
            raise RuntimeError(p.stderr)
        return p.stdout.strip() == 'true'

    def takeover(self):
        plan = self.plan
        pid = plan['scheduler_pid']
        live = read(self.root / 'execution/status.json')
        assert (live['state'], live['region'], live['job']) == ('RUNNING', 'R3', 'da3')
        assert Path(f'/proc/{pid}/stat').read_text().split()[21] == plan['scheduler_start_ticks']
        assert self.container_running()
        assert subprocess.check_output(['systemctl', '--user', 'show', plan['old_unit'],
            '-p', 'MainPID', '--value'], text=True).strip() == str(pid)
        os.kill(pid, signal.SIGSTOP)  # Deliberately NOT killpg/systemctl --kill-whom=all.
        try:
            for _ in range(100):
                if Path(f'/proc/{pid}/stat').read_text().split()[2] == 'T':
                    break
                time.sleep(.01)
            assert Path(f'/proc/{pid}/stat').read_text().split()[2] == 'T'
            assert self.container_running()
            paused = read(self.root / 'execution/status.json')
            assert (paused['region'], paused['job']) == ('R3', 'da3')
            assert paused['jobs'] == self.previous['jobs']
            atomic(self.folder / 'handoff.json', dict(status='ADOPTED_RUNNING_CONTAINER',
                old_scheduler_paused=True, old_scheduler_pid=pid,
                container_id=plan['container_id'], stage='R3/da3',
                training_restarted=False, time_unix=time.time(), scientific_verdict=None))
        except Exception:
            os.kill(pid, signal.SIGCONT)
            raise

    def finish_adopted(self, worker):
        worker.region, worker.job = 'R3', 'da3'
        worker.status('RUNNING_ADOPTED')
        with (self.folder / 'adopted_gpu1.csv').open('x') as usage:
            while self.container_running():
                subprocess.run(['nvidia-smi', '-i', '1',
                    '--query-gpu=timestamp,uuid,memory.used,utilization.gpu',
                    '--format=csv,noheader'], stdout=usage, stderr=subprocess.DEVNULL)
                usage.flush()
                worker.status('RUNNING_ADOPTED')
                time.sleep(10)
        # The Docker workload is finished before its old scheduler is retired.
        self.memory.release(32)
        try:
            receipt = read(self.root / 'R3/da3/receipt.json')
        except Exception:
            receipt = dict(status='FAIL', exit_code=None, error=traceback.format_exc())
        passed = receipt['status'] == 'PASS'
        worker.records.append(dict(region='R3', job='da3', output='R3/da3',
            status='PASS' if passed else 'FAILED', exit_code=receipt.get('exit_code'),
            seconds=time.time() - self.plan['adopted_started_unix'], adopted=True))
        subprocess.run(['systemctl', '--user', 'kill', '--kill-who=main', '--signal=SIGKILL',
                        self.plan['old_unit']], check=True)
        atomic(self.folder / 'retirement.json', dict(status='OLD_SCHEDULER_SUPERSEDED',
            container_finished=True, stage_receipt_status=receipt['status'],
            time_unix=time.time(), scientific_verdict=None))
        if passed:
            try:
                worker.stage('R3', 'extract_da3', 'extract', 'da3', 30000,
                             trained=self.root / 'R3/da3')
            except Exception:
                self.fail(worker, 'da3', traceback.format_exc())
        else:
            self.fail(worker, 'da3', json.dumps(receipt, ensure_ascii=False))

    def run(self):
        lockfile = (self.root / 'execution/parallel_scheduler.lock').open('a')
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, digest in read(self.folder / 'source_hashes.json').items():
            assert hashlib.sha256((self.folder / 'source' / name).read_bytes()).hexdigest() == digest
        self.takeover()
        self.workers = {str(g): Worker(self, g) for g in [0, 1]}
        threads = [threading.Thread(target=w.run, kwargs={'adopt': g == '1'}, name='gpu'+g)
                   for g, w in self.workers.items()]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.state = 'COMPLETE_WITH_FAILURES' if self.failures else 'COMPLETE'
        self.update(self.workers['0'], 'COMPLETE')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('attempt')
    ap.add_argument('parallel_run')
    args = ap.parse_args()
    manager = Manager(args.attempt, args.parallel_run)
    try:
        manager.run()
    except Exception:
        atomic(manager.folder / 'scheduler_failure.json', dict(status='FAILED',
            error=traceback.format_exc(), scientific_verdict=None))
        raise
