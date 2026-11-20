"""Host orchestration (docker only) for PHD-MAIN-GTTARGET-v1. Images and mounts follow TRAINERR launch.py.
  cpu <script> [args]          : CPU container (16 CPU, 48 GB)
  cpulock <script> [args]      : CPU container with /cfg writable (config lock only)
  gpu <gpu> <script> [args]    : GPU container, fork r28 at /source
  train <run> <gpu>            : training run (gttarget.json 'runs'), TRAINLOG on
Writes only: payload main_gttarget_v1/PHD-MAIN-GTTARGET-v1 (/gt), docs/experiments/phd/main_gttarget_v1 (/docs), configs/phd/main_gttarget_v1 (/cfg, lock)."""
import datetime as dt, json, os, re, subprocess, sys, time
from pathlib import Path
R = Path(__file__).resolve().parents[3]; ART = R.parent/'JointBuildGS-artifacts'; PH = ART/'phase-payloads/phd'
O = PH/'main_gttarget_v1/PHD-MAIN-GTTARGET-v1'; C = R/'configs/phd/main_gttarget_v1'; D = R/'docs/experiments/phd/main_gttarget_v1'
GPU_IMAGE = 'sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'
CPU_IMAGE = 'sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
FORK = 'GeoGS-conf-guided-v1-r28'
FAST = Path(os.environ['GT_FASTWORK']) if os.environ.get('GT_FASTWORK') else None
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p, v): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=1)+'\n')

def command(name, script, args=(), gpu=None, fork=FORK, env=(), cpus=16, memory='48g', split_site=None, cfg_rw=False, te=False):
    image = GPU_IMAGE if gpu is not None else CPU_IMAGE
    cmd = ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', str(cpus), '--memory', memory, '--memory-swap', memory, '--shm-size', '4g']
    cmd += ['--gpus', f'device={gpu}'] if gpu is not None else ['--runtime', 'runc', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES=']
    envs = ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', f'OMP_NUM_THREADS={min(cpus, 16)}', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
            'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True', 'TMPDIR=/gt/tmp', 'MPLCONFIGDIR=/gt/tmp/mpl', 'XDG_CACHE_HOME=/gt/tmp/cache',
            'TORCH_HOME=/weights/torch', 'TZ=Asia/Seoul', *env]
    if split_site: envs.append(f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{split_site}/split.json')
    for e in envs: cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (O, '/gt', 'rw'),
              (C, '/cfg', 'rw' if cfg_rw else 'ro'), (D, '/docs', 'rw'), (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1', '/p', 'ro'),
              (R/'src/phd/forks'/fork, '/source', 'ro'), (PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights', '/weights', 'ro'),
              (Path('/usr/share/fonts/opentype/noto'), '/fonts', 'ro')]
    if te:  # stage-3 figures: TRAINERR addendum 6 figure code reads its own payload at /te and stage-0 images at /s0 (read only)
        mounts += [(PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1', '/te', 'ro'), (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1', '/s0', 'ro')]
    if FAST: mounts.append((FAST, str(FAST), 'rw'))
    for s, d, m in mounts: cmd += ['-v', f'{s}:{d}:{m}']
    pre = 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; ' if gpu is not None else ''
    return cmd + ['-w', '/source' if gpu is not None else '/gt', '--entrypoint', '/bin/bash', image, '-c',
                  pre+'exec python -B -u "/repo/scripts/phd/main_gttarget_v1/$0" "$@"', script, *args]

def run(cmd, log):
    log.parent.mkdir(parents=True, exist_ok=True); t = time.monotonic()
    with log.open('x') as f: rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    return rc, time.monotonic()-t

def job(script, *args, gpu=None, cpus=16, memory='48g', cfg_rw=False, env=(), split_site=None, te=False):
    stem = Path(script).stem
    name = re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-gttarget-{stem}-{"-".join(args)}'[:120])
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S_%f")}_{stem}_{"_".join(args)[:60].replace("/", "_")}.log'
    cmd = command(name, script, list(args), gpu=gpu, cpus=cpus, memory=memory, cfg_rw=cfg_rw, env=env, split_site=split_site, te=te)
    rc, s = run(cmd, log); print(script, args, rc, round(s), log, flush=True)
    with (O/'logs/jobs.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), script=script, args=list(args), gpu=gpu, exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

def train_args(stem, model, iterations, seed=0, extra=()):
    site, prior = stem.split('__')
    return [stem, '-s', f'/p/fork_inputs/s61/{site}/scene_{prior}', '-m', model, '--eval', '-r', '1', '--data_device', 'cpu',
            '--lod_depth_path', '/p/fork_none', '--da_depth_path', '/p/fork_none', '--stage_switch_iter', '0', '--lambda_lod_init', '0', '--lambda_lod_anchor', '0', '--lambda_da_depth', '0',
            '--jbgs_judgment', 'off', '--jbgs_target', 'on', '--jbgs_target_rev', 'r8', '--jbgs_finaltrain', 'on',
            '--jbgs_targets', f'/gt/targets/{stem}.npz', '--jbgs_preserve_freespace', 'off', '--jbgs_target_dir', f'/gt/stage1/{stem}',
            '--jbgs_target_lambda', '.05', '--jbgs_seed', str(seed), '--iterations', str(iterations),
            '--jbgs_trainlog', 'on', '--jbgs_trainlog_region', f'/gt/region/{stem}.json', *extra]
FULL = ['--jbgs_capture_iterations', '7000', '15000', '30000', '--test_iterations', '7000', '15000', '30000', '--save_iterations', '7000', '15000', '30000']
def train(stem, gpu, seed=0, iterations=30000, tag=None):
    """one stage-2 run; tag 'probe' = short loader/record probe (300 iterations, densify from 100, reset every 200)."""
    run = tag or f'gtt_s{seed}'; site = stem.split('__')[0]; root = O/'runs'/stem/run; root.mkdir(parents=True, exist_ok=False); model = f'/gt/runs/{stem}/{run}/model'
    extra = FULL if tag is None or tag.startswith('gtt_') else ['--densify_from_iter', '100', '--opacity_reset_interval', '200', '--jbgs_capture_iterations', '100', '200', '300', '--test_iterations', '300', '--save_iterations', '300']
    cmd = command(re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-gttarget-train-{stem}-{run}'), 'g2_train_entry.py', train_args(stem, model, iterations, seed, extra), gpu=int(gpu), cpus=8, memory='40g',
                  env=['JBGS_TRAINLOG_CONFIG=/cfg/trainlog_gtt.json'], split_site=site)
    dump(root/'command.json', cmd); dump(root/'launch.json', dict(at=now(), gpu=int(gpu), stem=stem, run=run, seed=seed, iterations=iterations, scientific_verdict=None))
    rc, s = run_(cmd, root/'train.log'); stop = root/'model/target_monitor/STOP.json'
    status = 'COMPLETED' if rc == 0 and (root/'TRAINING_COMPLETE.json').exists() else ('HEALTH_STOP' if stop.exists() else 'ERROR')
    rec = dict(at=now(), stem=stem, run=run, exit_code=rc, seconds=s, status=status, health=json.loads(stop.read_text()) if stop.exists() else None, scientific_verdict=None)
    dump(root/'receipt.json', rec); print(json.dumps(rec, ensure_ascii=False), flush=True); return rc
run_ = run

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'train': sys.exit(train(a[1], a[2], int(a[3]) if len(a) > 3 else 0, tag=a[4] if len(a) > 4 else None, iterations=300 if len(a) > 4 and not a[4].startswith('gtt_') else 30000))
    if a[0] == 'cpu': sys.exit(job(a[1], *a[2:]))
    if a[0] == 'cpute': sys.exit(job(a[1], *a[2:], te=True))
    if a[0] == 'cpulock': sys.exit(job(a[1], *a[2:], cfg_rw=True, cpus=2, memory='4g'))
    if a[0] == 'gpu': sys.exit(job(a[2], *a[3:], gpu=int(a[1]), cpus=8, memory='40g'))

# ---------- mesh + score (TRAINERR te_mesh.py with this task's shadow /gtjudge = O/gtj, /te = O) ----------
sys.path.insert(0, str(R/'scripts/phd/main_trainerr_v1'))
import launch as TL
def gtjcmd(step, stem, family, ply='', gpu=None, name=None, script=None, args=None):
    sh = O/'gtj'; sh.mkdir(parents=True, exist_ok=True); (O/'gtj_docs').mkdir(exist_ok=True)
    cmd = TL.gtjcmd(step, stem, family, ply, gpu, name=name or re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-gtt-gtj-{step.replace(":", "")}-{stem}-{family}')[:120])
    out = []; i = 0
    while i < len(cmd):
        if cmd[i] == '-v':
            s, d, m = cmd[i+1].rsplit(':', 2)
            if d == '/gtjudge': s = str(sh)
            elif d == '/docs': s = str(O/'gtj_docs')
            elif d == '/te': s = str(O)
            elif d == '/source': s = str(R/'src/phd/forks'/FORK)
            out += ['-v', f'{s}:{d}:{m}']; i += 2
        else: out.append(cmd[i]); i += 1
    j = out.index('--entrypoint'); out[j:j] = ['-v', f'{C}:/gtcfg:ro']
    if FAST and not any(x.startswith(f'{FAST}:') for x in out): out[j:j] = ['-v', f'{FAST}:{FAST}:rw']
    if script:  # another script of this task inside the gtj container
        i = out.index('-c'); pre = out[i+1].split('exec python')[0]
        out = out[:i+1]+[pre+f'exec python -B -u /repo/scripts/phd/main_gttarget_v1/{script} "$@"', Path(script).stem, *args]
    return out
def gtj(step, stem, family, ply='', gpu=None):
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S_%f")}_gtj_{step.replace(":", "")}_{stem}_{family}.log'
    rc, s = run(gtjcmd(step, stem, family, ply, gpu), log); print('gtj', step, stem, family, rc, round(s), flush=True)
    with (O/'logs/mesh_timing.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), step=step, stem=stem, family=family, exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc
def gtjscript(script, args, gpu=None):
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S_%f")}_gtjs_{Path(script).stem}_{"_".join(args)[:60].replace("/", "_")}.log'
    name = re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-gtt-gtjs-{Path(script).stem}-{"-".join(args)}')[:120]
    rc, s = run(gtjcmd('x', 'x', 'x', '', gpu, name=name, script=script, args=list(args)), log); print('gtjscript', script, args, rc, round(s), log, flush=True)
    with (O/'logs/jobs.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), script=script, args=list(args), gpu=gpu, container='gtj', exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'gtj': sys.exit(gtj(a[1], a[2], a[3], a[4] if len(a) > 4 and a[4] != '-' else '', int(a[5]) if len(a) > 5 else None))
    if a[0] == 'gtjscript': sys.exit(gtjscript(a[2], a[3:], int(a[1]) if a[1] != '-' else None))
    raise SystemExit(f'unknown {a}')
