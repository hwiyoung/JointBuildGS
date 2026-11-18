#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1: a short GPU test of one method on one cell between two queue cells (host, stdlib).
Holds the queue with control/HOLD_GPU_smoke_<run>, waits until no training container of this task, no DA3 container and no other
HOLD_GPU file, then runs the queue's own command for (run, cell) with --iterations <n> into OUT/tests/smoke_<run>/a<k>, and releases.
  nohup python3 b151_smoke.py <run> <cell> <iterations> > OUT/logs/smoke_<run>.log 2>&1 &
scientific_verdict: null"""
import subprocess, sys, time
from b151_host import OUT, cfg, command, dump, gpu_free_mib, method_spec, now, progress
run, k, iters = sys.argv[1], int(sys.argv[2]), sys.argv[3]
hold = OUT / 'control' / f'HOLD_GPU_smoke_{run}'
hold.touch()
busy = lambda: any(n.startswith(('jbgs-b151-train-', 'jbgs-b151-da3-')) for n in subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True).stdout.split())
while busy() or [p for p in (OUT / 'control').glob('HOLD_GPU*') if p != hold]:
    time.sleep(20)
spec = method_spec(cfg(), run)
T = OUT / 'tests' / f'smoke_{run}'
n = len(list(T.glob('a*'))) + 1 if T.exists() else 1
adir = T / f'a{n}'
adir.mkdir(parents=True)
free = gpu_free_mib()
name, cmd = command(spec, k, adir, (free - 2048) / 1024)
cmd += ['--iterations', iters]
dump(adir / 'launch.json', dict(at=now().isoformat(), run=run, cell=k, iterations=int(iters), gpu_free_MiB=free, command=cmd, scientific_verdict=None))
t0 = time.time()
rc = subprocess.run(cmd, stdout=open(adir / 'train.log', 'w'), stderr=subprocess.STDOUT).returncode
hold.unlink()
progress(f'GPU 시험 {run} 칸 {k} {iters}회: 종료 코드 {rc}, {time.time() - t0:.0f} s (tests/smoke_{run}/a{n})')
print(now().isoformat(), 'done', rc, flush=True)
