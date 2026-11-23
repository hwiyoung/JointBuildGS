"""Host orchestration (docker only) for PHD-MAIN-DEPTHFIX-v1. Images and mounts follow PRESCRIBE-v1 / FINALTRAIN-v1 launch.
  cpu <script> [args]      : CPU container
  cpulock <script> [args]  : CPU container, /cfg writable (lock files only)
  gpu <n> <script> [args]  : GPU container (fork r23 at /source)
  train <arm> <stem> <seed> <gpu> [stop_after] [run] : one training run (configs depthfix_v1.json 'arms')
Writes only: payload main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1 (/df), docs/experiments/phd/main_depthfix_v1 (/docs),
configs/phd/main_depthfix_v1 (/cfg, lock only). Everything else read-only."""
import datetime as dt, json, os, re, subprocess, sys, time
from pathlib import Path
R = Path(__file__).resolve().parents[3]; ART = R.parent/'JointBuildGS-artifacts'; PH = ART/'phase-payloads/phd'
O = PH/'main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'; C = R/'configs/phd/main_depthfix_v1'; D = R/'docs/experiments/phd/main_depthfix_v1'
GPU_IMAGE = 'sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'
CPU_IMAGE = 'sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
FORK = 'GeoGS-conf-guided-v1-r23'
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p, v): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=1)+'\n')

def command(name, script, args=(), gpu=None, cpus=16, memory='48g', split_site=None, cfg_rw=False, env=()):
    image = GPU_IMAGE if gpu is not None else CPU_IMAGE
    cmd = ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', str(cpus), '--memory', memory, '--memory-swap', memory, '--shm-size', '4g']
    cmd += ['--gpus', f'device={gpu}'] if gpu is not None else ['--runtime', 'runc', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES=']
    envs = ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', f'OMP_NUM_THREADS={4 if gpu is not None else min(cpus, 16)}', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
            'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True', 'TMPDIR=/df/tmp', 'MPLCONFIGDIR=/df/tmp/mpl', 'XDG_CACHE_HOME=/df/tmp/cache',
            'TORCH_HOME=/weights/torch', 'TZ=Asia/Seoul', *env]
    if split_site: envs.append(f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{split_site}/split.json')
    for e in envs: cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'), (O, '/df', 'rw'),
              (C, '/cfg', 'rw' if cfg_rw else 'ro'), (D, '/docs', 'rw'), (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1', '/p', 'ro'),
              (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1', '/s0', 'ro'),
              (R/'src/phd/forks'/FORK, '/source', 'ro'), (PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights', '/weights', 'ro'),
              (Path('/usr/share/fonts/opentype/noto'), '/fonts', 'ro')]
    for s, d, m in mounts: cmd += ['-v', f'{s}:{d}:{m}']
    pre = 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; ' if gpu is not None else ''
    return cmd + ['-w', '/source' if gpu is not None else '/df', '--entrypoint', '/bin/bash', image, '-c',
                  pre+'exec python -B -u "/repo/scripts/phd/main_depthfix_v1/$0" "$@"', script, *args]

def run(cmd, log):
    log.parent.mkdir(parents=True, exist_ok=True); t = time.monotonic()
    with log.open('x') as f: rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    return rc, time.monotonic()-t

def job(script, *args, gpu=None, cpus=16, memory='48g', cfg_rw=False):
    stem = Path(script).stem
    name = re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-depthfix-{stem}-{"-".join(args)}'[:120])
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S_%f")}_{stem}_{"_".join(args)[:60].replace("/", "_")}.log'
    rc, s = run(command(name, script, list(args), gpu=gpu, cpus=cpus, memory=memory, cfg_rw=cfg_rw), log); print(script, args, rc, round(s), log, flush=True)
    with (O/'logs/jobs.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), script=script, args=list(args), gpu=gpu, exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'cpu': sys.exit(job(a[1], *a[2:]))
    if a[0] == 'cpubig': sys.exit(job(a[1], *a[2:], cpus=32, memory='56g'))
    if a[0] == 'cpulock': sys.exit(job(a[1], *a[2:], cfg_rw=True, cpus=2, memory='4g'))
    if a[0] == 'gpu': sys.exit(job(a[2], *a[3:], gpu=int(a[1]), cpus=8, memory='40g'))
    if a[0] == 'train':
        import df_train; sys.exit(df_train.train(*a[1:]))
    raise SystemExit(f'unknown {a}')
