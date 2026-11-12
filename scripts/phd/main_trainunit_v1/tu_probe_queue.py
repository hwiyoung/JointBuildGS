"""Addendum 5-7 probe runs (원인 확인): probe0/probe1 ALS, seed 0, stop right after iteration 15,000.

A probe starts only on a GPU with no other compute process (TRAINERR priority) and with host MemAvailable >= START_GB.
While it runs (followed by the container state, not only the docker client: the client can lose the container under host
memory pressure), host MemAvailable is checked every 10 s; below FLOOR_GB this task's container is killed first
(HOST_GUARD_STOP) and the probe goes back to the queue (at most MAX_GUARD times). After PROBE_STOP.json the container gets
180 s to exit, then is killed (recorded). A GPU memory stop (binning guard / CUDA OOM) is a result, not retried; any other
execution error gets one retry with the same command.

  nohup python3 tu_probe_queue.py <gpu> &
"""
import json
import subprocess
import sys
import time

from tu_host import TU, command, dump, gpu_busy, issue, now, progress, train_args

ORDER = ['probe1', 'probe0']   # longest expected first; probe2 not run (addendum 6)
FLOOR_GB, START_GB, MAX_GUARD = 20, 45, 3


def avail_gb():
    for line in open('/proc/meminfo'):
        if line.startswith('MemAvailable'):
            return int(line.split()[1]) / 1048576
    return 0.


def running(cname):
    r = subprocess.run(['docker', 'inspect', '-f', '{{.State.Running}}', cname], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == 'true'


def claim(run):
    try:
        (run / 'claim').mkdir(parents=True, exist_ok=False)
        return True
    except FileExistsError:
        return False


def next_attempt(run):
    return 1 + max([int(p.name[7:]) for p in run.glob('attempt*') if p.name[7:].isdigit()] + [0])


def attempt(gpu, unit, run, a):
    name = f'{unit}_ALS_s0'
    root = run / f'attempt{a}'
    root.mkdir()
    model = '/tu/' + str((root / 'model').relative_to(TU))
    args = [name, *train_args(f'/tu/scenes/{unit}/scene_ALS', model, f'/tu/stage1/{unit}__ALS', 0, 30000)]
    cname = f'jbgs-trainunit-{name.replace("_", "-").lower()}-a{a}'
    cmd = command(gpu, cname, 'tu_train_entry.py', args, f'/tu/scenes/{unit}/split.json', '48g')
    dump(root / 'command.json', cmd)
    dump(root / 'launch.json', dict(at=now().isoformat(), gpu=gpu, unit=unit, attempt=a, addendum=5,
                                   nvidia_smi_compute_apps=gpu_busy(gpu), host_available_GiB=avail_gb(), scientific_verdict=None))
    progress(f'{name} 시도 {a} 시작, GPU {gpu} (덧붙임 5, 15,000회에서 멈춤)')
    start = time.monotonic()
    guard = killed_after_stop = None
    client_lost = False
    min_avail = avail_gb()
    with (root / 'train.log').open('x') as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        time.sleep(20)
        stop_seen = None
        while proc.poll() is None or running(cname):
            if proc.poll() is not None:
                client_lost = True
            time.sleep(10)
            av = avail_gb()
            min_avail = min(min_avail, av)
            if av < FLOOR_GB and guard is None:
                guard = dict(at=now().isoformat(), available_GiB=av, floor_GiB=FLOOR_GB)
                subprocess.run(['docker', 'kill', cname], capture_output=True)
            if (root / 'PROBE_STOP.json').exists():
                stop_seen = stop_seen or time.monotonic()
                if time.monotonic() - stop_seen > 180 and killed_after_stop is None:
                    killed_after_stop = now().isoformat()
                    subprocess.run(['docker', 'kill', cname], capture_output=True)
        rc = proc.returncode
    sec = time.monotonic() - start
    err = json.loads((root / 'ERROR.json').read_text()) if (root / 'ERROR.json').exists() else None
    etext = (err or {}).get('error', '')
    if (root / 'PROBE_STOP.json').exists():
        st = 'PROBE_STOP_15000'
    elif guard:
        st = 'HOST_GUARD_STOP'
    elif 'BINNING_GUARD' in etext or 'out of memory' in etext.lower():
        st = 'GPU_MEMORY_STOP'
    elif (root / 'model/target_monitor/STOP.json').exists():
        st = 'HEALTH_STOP'
    else:
        st = 'EXECUTION_ERROR'
    trace = root / 'model/jbgs_trace.jsonl'
    last = json.loads(trace.read_text().strip().splitlines()[-1]) if trace.exists() and trace.read_text().strip() else None
    rec = dict(at=now().isoformat(), attempt=a, gpu=gpu, exit_code=rc, docker_client_lost_container=client_lost, seconds=sec, status=st,
               error=err, last_trace=last, host_guard=guard, killed_after_probe_stop=killed_after_stop, min_host_available_GiB=min_avail,
               model=model, addendum=5, scientific_verdict=None)
    dump(root / 'receipt.json', rec)
    progress(f'{name} 시도 {a} 끝: {st}, {sec/3600:.2f}시간' + (f', 오류 {etext[:160]}' if etext else '')
             + (f', 호스트 가용 {guard["available_GiB"]:.1f} GB로 멈춤(다시 대기열로)' if guard else ''))
    return rec


def run_one(gpu, unit):
    run = TU / 'runs/probes' / f'{unit}_ALS_s0'
    recs = []
    errors = 0
    while True:
        rec = attempt(gpu, unit, run, next_attempt(run))
        recs.append(rec)
        if rec['status'] == 'EXECUTION_ERROR':
            errors += 1
            if errors < 2:
                continue
        break
    old = json.loads((run / 'receipt.json').read_text())['attempts'] if (run / 'receipt.json').exists() else []
    attempts = old + recs
    st = recs[-1]['status']
    guards = sum(r['status'] == 'HOST_GUARD_STOP' for r in attempts)
    final = 'NO_RESULT' if st == 'EXECUTION_ERROR' else st
    dump(run / 'receipt.json', dict(at=now().isoformat(), name=f'{unit}_ALS_s0', status=final, attempts=attempts, host_guard_stops=guards,
                                   addendum=5, scientific_verdict=None))
    if st == 'HOST_GUARD_STOP' and guards < MAX_GUARD:
        (run / 'claim').rmdir()   # back to the queue; starts again from iteration 0 when the host has room
        return
    if final in ('NO_RESULT', 'HOST_GUARD_STOP', 'GPU_MEMORY_STOP', 'HEALTH_STOP'):
        issue(f'{unit}_ALS_s0: {final}. 마지막 기록 {attempts[-1].get("last_trace")}, 오류 {attempts[-1].get("error")}, 보호 {attempts[-1].get("host_guard")}')


def main(gpu):
    gpu = int(gpu)
    progress(f'덧붙임 5 원인 확인 대기열 시작 GPU {gpu}.')
    while True:
        if (TU / 'control' / f'PROBES_STOP_{gpu}').exists():
            progress(f'덧붙임 5 대기열 GPU {gpu} 멈춤 파일로 끝.')
            return
        todo = [u for u in ORDER if (TU / 'stage1' / f'{u}__ALS' / 'ready.json').exists()
                and not (TU / 'runs/probes' / f'{u}_ALS_s0' / 'claim').exists()]
        waiting = [u for u in ORDER if not (TU / 'stage1' / f'{u}__ALS' / 'ready.json').exists()]
        if not todo and not waiting:
            progress(f'덧붙임 5 대기열 GPU {gpu}: 남은 판 없음, 끝.')
            return
        if not todo or gpu_busy(gpu) or avail_gb() < START_GB:
            time.sleep(60)
            continue
        u = todo[0]
        run = TU / 'runs/probes' / f'{u}_ALS_s0'
        if not claim(run):
            continue
        try:
            run_one(gpu, u)
        except Exception as e:
            issue(f'덧붙임 5 대기열 GPU {gpu} {u} 실행기 오류: {type(e).__name__}: {e}')


if __name__ == '__main__':
    main(sys.argv[1])
