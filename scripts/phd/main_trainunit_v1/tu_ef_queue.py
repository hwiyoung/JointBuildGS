"""Addendum 12 runs (CityGaussianV2 elongation filter): B0ef (FINALTRAIN B0 ALS seed 0, full 30,000), cell0ef, probe3ef, probe4ef
(stop right after 15,000). Same queue rules as tu_probe_queue.py: start only on a GPU with no other compute process (TRAINERR
priority) and host MemAvailable >= START_GB; follow the container state; host guard kills this task's container below FLOOR_GB and
returns the run to the queue (at most MAX_GUARD times); GPU memory stop is a result; execution error gets one retry.

  nohup python3 tu_ef_queue.py <gpu> &
"""
import json
import subprocess
import sys
import time

from tu_host import FT, TU, command, dump, gpu_busy, issue, now, progress, train_args

ORDER = ['B0ef_ALS_s0', 'cell0ef_ALS_s0', 'probe3ef_ALS_s0', 'probe4ef_ALS_s0', 'B0ef_ALS_s1']   # longest expected first; addendum 13 last
JOBS = {
    'B0ef_ALS_s0': dict(scene='/p/fork_inputs/s61/B0_b10/scene_ALS', split='/p/fork_inputs/s61/B0_b10/split.json', target='/ft/stage1/B0_b10__ALS',
                        ready=FT / 'stage1/B0_b10__ALS/ready.json', memory='40g'),
    'cell0ef_ALS_s0': dict(scene='/tu/scenes/cell0/scene_ALS', split='/tu/scenes/cell0/split.json', target='/tu/stage1/cell0__ALS',
                           ready=TU / 'stage1/cell0__ALS/ready.json', memory='48g'),
    'probe3ef_ALS_s0': dict(scene='/tu/scenes/probe3/scene_ALS', split='/tu/scenes/probe3/split.json', target='/tu/stage1/probe3__ALS',
                            ready=TU / 'stage1/probe3__ALS/ready.json', memory='48g'),
    'probe4ef_ALS_s0': dict(scene='/tu/scenes/probe4/scene_ALS', split='/tu/scenes/probe4/split.json', target='/tu/stage1/probe4__ALS',
                            ready=TU / 'stage1/probe4__ALS/ready.json', memory='48g'),
    # addendum 13: B0ef with seed 1
    'B0ef_ALS_s1': dict(scene='/p/fork_inputs/s61/B0_b10/scene_ALS', split='/p/fork_inputs/s61/B0_b10/split.json', target='/ft/stage1/B0_b10__ALS',
                        ready=FT / 'stage1/B0_b10__ALS/ready.json', memory='40g', seed=1),
}
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


def attempt(gpu, name, run, a):
    j = JOBS[name]
    root = run / f'attempt{a}'
    root.mkdir()
    model = '/tu/' + str((root / 'model').relative_to(TU))
    args = [name, *train_args(j['scene'], model, j['target'], j.get('seed', 0), 30000)]
    cname = f'jbgs-trainunit-{name.replace("_", "-").lower()}-a{a}'
    cmd = command(gpu, cname, 'tu_train_entry.py', args, j['split'], j['memory'])
    dump(root / 'command.json', cmd)
    dump(root / 'launch.json', dict(at=now().isoformat(), gpu=gpu, name=name, attempt=a, addendum=13 if name == 'B0ef_ALS_s1' else 12, seed=j.get('seed', 0),
                                   nvidia_smi_compute_apps=gpu_busy(gpu), host_available_GiB=avail_gb(), scientific_verdict=None))
    progress(f'{name} 시도 {a} 시작, GPU {gpu} (덧붙임 12, 길쭉함 필터)')
    start = time.monotonic()
    guard = None
    client_lost = False
    min_avail = avail_gb()
    with (root / 'train.log').open('x') as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        time.sleep(20)
        stop_seen = killed_after_stop = None
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
    elif (root / 'TRAINING_COMPLETE.json').exists():
        st = 'TRAINING_COMPLETE'
    elif guard:
        st = 'HOST_GUARD_STOP'
    elif 'BINNING_GUARD' in etext or 'out of memory' in etext.lower():
        st = 'GPU_MEMORY_STOP'
    elif (root / 'model/target_monitor/STOP.json').exists() or 'HEALTH_STOP' in etext:
        st = 'HEALTH_STOP'
    else:
        st = 'EXECUTION_ERROR'
    trace = root / 'model/jbgs_trace.jsonl'
    last = json.loads(trace.read_text().strip().splitlines()[-1]) if trace.exists() and trace.read_text().strip() else None
    rec = dict(at=now().isoformat(), attempt=a, gpu=gpu, exit_code=rc, docker_client_lost_container=client_lost, seconds=sec, status=st,
               error=err, last_trace=last, host_guard=guard, killed_after_probe_stop=killed_after_stop, min_host_available_GiB=min_avail,
               model=model, addendum=12, scientific_verdict=None)
    dump(root / 'receipt.json', rec)
    progress(f'{name} 시도 {a} 끝: {st}, {sec/3600:.2f}시간' + (f', 오류 {etext[:160]}' if etext else '')
             + (f', 호스트 가용 {guard["available_GiB"]:.1f} GB로 멈춤(다시 대기열로)' if guard else ''))
    return rec


def run_one(gpu, name):
    run = TU / 'runs/ef' / name
    recs, errors = [], 0
    while True:
        rec = attempt(gpu, name, run, next_attempt(run))
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
    dump(run / 'receipt.json', dict(at=now().isoformat(), name=name, status=final, attempts=attempts, host_guard_stops=guards, addendum=12,
                                   scientific_verdict=None))
    if st == 'HOST_GUARD_STOP' and guards < MAX_GUARD:
        (run / 'claim').rmdir()
        return
    if final in ('NO_RESULT', 'HOST_GUARD_STOP', 'GPU_MEMORY_STOP', 'HEALTH_STOP'):
        issue(f'{name}: {final}. 마지막 기록 {attempts[-1].get("last_trace")}, 오류 {attempts[-1].get("error")}, 보호 {attempts[-1].get("host_guard")}')


def main(gpu):
    gpu = int(gpu)
    progress(f'덧붙임 12 대기열 시작 GPU {gpu}.')
    while True:
        if (TU / 'control' / f'EF_STOP_{gpu}').exists():
            progress(f'덧붙임 12 대기열 GPU {gpu} 멈춤 파일로 끝.')
            return
        todo = [n for n in ORDER if JOBS[n]['ready'].exists() and not (TU / 'runs/ef' / n / 'claim').exists()]
        if not todo:
            progress(f'덧붙임 12 대기열 GPU {gpu}: 남은 판 없음, 끝.')
            return
        if gpu_busy(gpu) or avail_gb() < START_GB:
            time.sleep(60)
            continue
        n = todo[0]
        if not claim(TU / 'runs/ef' / n):
            continue
        try:
            run_one(gpu, n)
        except Exception as e:
            issue(f'덧붙임 12 대기열 GPU {gpu} {n} 실행기 오류: {type(e).__name__}: {e}')


if __name__ == '__main__':
    main(sys.argv[1])
