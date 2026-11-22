"""Host launcher (docker only, CPU only) for PHD-MAIN-TARGETPATH-v1. Modelled on scripts/phd/main_wrongtarget_v1/launch.py.
  cpu <script> [args]   : run /repo/scripts/phd/main_targetpath_v1/<script> in the CPU image (no GPU, no network, read-only root)
Read-only: repo (/repo), artifacts (/art), fonts (/fonts). Writes only: payload main_targetpath_v1/PHD-MAIN-TARGETPATH-v1 (/tp)
and docs/experiments/phd/main_targetpath_v1 (/docs). No GPU is used so the running trainings are not slowed on the GPUs.
env TP_CPUS (default 24) and TP_MEM (default 40g) set the container limits."""
import datetime as dt, json, os, re, subprocess, sys, time
from pathlib import Path
R = Path(__file__).resolve().parents[3]; CODE = R.parent; ART = CODE/'JointBuildGS-artifacts'; PH = ART/'phase-payloads/phd'
O = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'; D = R/'docs/experiments/phd/main_targetpath_v1'
CPU_IMAGE = 'sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def command(name, script, args=(), cpus=24, memory='40g'):
    cmd = ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', str(cpus), '--memory', memory, '--memory-swap', memory, '--shm-size', '4g',
           '--runtime', 'runc', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES=']
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=1', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
              f'TP_WORKERS={cpus}', 'TMPDIR=/tp/tmp', 'MPLCONFIGDIR=/tp/tmp/mpl', 'XDG_CACHE_HOME=/tp/tmp/cache', 'TZ=Asia/Seoul']: cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (O, '/tp', 'rw'), (D, '/docs', 'rw'), (Path('/usr/share/fonts/opentype/noto'), '/fonts', 'ro')]
    for s, d, m in mounts: cmd += ['-v', f'{s}:{d}:{m}']
    return cmd + ['-w', '/tp', '--entrypoint', '/bin/bash', CPU_IMAGE, '-c', 'exec python -B -u "/repo/scripts/phd/main_targetpath_v1/$0" "$@"', script, *args]

def job(script, *args):
    (O/'tmp/mpl').mkdir(parents=True, exist_ok=True); (O/'logs').mkdir(parents=True, exist_ok=True)
    cpus = int(os.environ.get('TP_CPUS', 24)); mem = os.environ.get('TP_MEM', '40g')
    stem = Path(script).stem; name = re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-targetpath-{stem}-{"-".join(args)}-{os.getpid()}'[:120])
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S_%f")}_{stem}_{"_".join(args)[:60].replace("/", "_")}.log'
    cmd = command(name, script, list(args), cpus, mem); t0 = now(); t = time.monotonic()
    with log.open('x') as f:
        f.write('# ' + json.dumps(cmd) + '\n'); f.flush(); rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    s = time.monotonic()-t; print(script, args, rc, round(s), log, flush=True)
    with (O/'logs/jobs.jsonl').open('a') as f: f.write(json.dumps(dict(started=t0, ended=now(), script=script, args=list(args), command=cmd, exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'cpu': sys.exit(job(a[1], *a[2:]))
    raise SystemExit(f'unknown {a}')
