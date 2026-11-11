"""Host orchestration (docker) for PHD-MAIN-TRAINERR-v1. Adapted from TRAINLOG launch.py (same images and mounts).
  cpu <script> [args]             : CPU container, task mounts
  gpu <gpu> <script> [args]       : GPU container (fork r28 by default)
  gpufork <gpu> <fork> <script> ...: GPU container with another fork at /source
  gtj <step> <stem> <family> [ply] [gpu]: GTJUDGE/RESCORE mesh+score code with a task-local shadow /gtjudge (TRAINLOG meshcmd)"""
import datetime as dt, json, os, subprocess, sys, time
from pathlib import Path
R = Path(__file__).resolve().parents[3]; ART = R.parent/'JointBuildGS-artifacts'; PH = ART/'phase-payloads/phd'
O = PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1'; C = R/'configs/phd/main_trainerr_v1'; D = R/'docs/experiments/phd/main_trainerr_v1'
GPU_IMAGE = 'sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'
CPU_IMAGE = 'sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
FORK = 'GeoGS-conf-guided-v1-r28'
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p, v): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=1)+'\n')

def command(name, script, args=(), gpu=None, fork=FORK, env=(), cpus=8, memory='40g', split_site=None, cfg_rw=False):
    image = GPU_IMAGE if gpu is not None else CPU_IMAGE
    cmd = ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', str(cpus), '--memory', memory, '--memory-swap', memory, '--shm-size', '4g']
    cmd += ['--gpus', f'device={gpu}'] if gpu is not None else ['--runtime', 'runc', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES=']
    envs = ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=8', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
            'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True', 'TMPDIR=/te/tmp', 'MPLCONFIGDIR=/te/tmp/mpl', 'XDG_CACHE_HOME=/te/tmp/cache',
            'TORCH_HOME=/weights/torch', 'TZ=Asia/Seoul', *env]
    if split_site: envs.append(f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{split_site}/split.json')
    for e in envs: cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'), (O, '/te', 'rw'),
              (C, '/cfg', 'rw' if cfg_rw else 'ro'), (D, '/docs', 'rw'), (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1', '/p', 'ro'),
              (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1', '/s0', 'ro'), (R/'src/phd/forks'/fork, '/source', 'ro'),
              (PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights', '/weights', 'ro'), (Path('/usr/share/fonts/opentype/noto'), '/fonts', 'ro')]
    for s, d, m in mounts: cmd += ['-v', f'{s}:{d}:{m}']
    pre = 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; ' if gpu is not None else ''
    return cmd + ['-w', '/source' if gpu is not None else '/te', '--entrypoint', '/bin/bash', image, '-c',
                  pre+'exec python -B -u "/repo/scripts/phd/main_trainerr_v1/$0" "$@"', script, *args]

def gtjcmd(step, stem, family, ply='', gpu=None, name=None):
    """GTJUDGE/RESCORE mesh + score code; /gtjudge = O/gtj (rw shadow, inputs symlinked read-only)."""
    sh = O/'gtj'; sh.mkdir(exist_ok=True); (O/'gtj_docs').mkdir(exist_ok=True)
    image = GPU_IMAGE if gpu is not None else CPU_IMAGE
    name = name or f'jbgs-trainerr-gtj-{step.replace(":", "")}-{stem}-{family}'[:120]
    cmd = ['nice', '-n', '19', 'docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', '12', '--memory', '40g', '--memory-swap', '40g', '--shm-size', '4g']
    cmd += ['--gpus', f'device={gpu}'] if gpu is not None else ['--runtime', 'runc', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES=']
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=8', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1', 'TMPDIR=/gtjudge/tmp',
              'MPLCONFIGDIR=/gtjudge/tmp/mpl', 'XDG_CACHE_HOME=/gtjudge/tmp/cache', 'TZ=Asia/Seoul', 'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True']:
        cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'), (PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1', '/out', 'ro'),
              (PH/'main_release_v1/PHD-MAIN-RELEASE-v1', '/release', 'ro'), (sh, '/gtjudge', 'rw'), (R/'configs/phd/main_gtjudge_v1', '/cfg', 'ro'),
              (O/'gtj_docs', '/docs', 'rw'), (O, '/te', 'rw'), (R/'src/phd/forks'/FORK, '/source', 'ro'), (Path('/usr/share/fonts/opentype/noto'), '/fonts', 'ro')]
    for s_, d, m in mounts: cmd += ['-v', f'{s_}:{d}:{m}']
    pre = 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; ' if gpu is not None else ''
    args = [a for a in [step, stem, family, ply] if a]
    return cmd + ['-w', '/source' if gpu is not None else '/gtjudge', '--entrypoint', '/bin/bash', image, '-c',
                  pre+'exec python -B -u /repo/scripts/phd/main_trainerr_v1/te_mesh.py "$@"', 'te_mesh', *args]

def run(cmd, log):
    log.parent.mkdir(parents=True, exist_ok=True); t = time.monotonic()
    with log.open('x') as f: rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    return rc, time.monotonic()-t

def job(script, *args, gpu=None, fork=FORK, name=None, cpus=8, memory='40g', env=(), split_site=None, cfg_rw=False):
    stem = Path(script).stem; name = name or f'jbgs-trainerr-{stem}-{"-".join(args)}'[:120].replace(':', '').replace('/', '_')
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}_{stem}_{"_".join(args)[:60].replace("/", "_")}.log'
    cmd = command(name, script, list(args), gpu=gpu, fork=fork, cpus=cpus, memory=memory, env=env, split_site=split_site, cfg_rw=cfg_rw)
    rc, s = run(cmd, log); print(script, args, rc, round(s), log, flush=True)
    with (O/'logs/jobs.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), script=script, args=list(args), gpu=gpu, fork=fork, exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

def gtj(step, stem, family, ply='', gpu=None):
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}_gtj_{step.replace(":", "")}_{stem}_{family}.log'
    rc, s = run(gtjcmd(step, stem, family, ply, gpu), log); print('gtj', step, stem, family, rc, round(s), flush=True)
    with (O/'logs/mesh_timing.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), step=step, stem=stem, family=family, exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

ARTC = '/art/phase-payloads/phd'
def train_args(site, prior, arm, model, iterations, extra=()):
    stem = f'{site}__{prior}'
    root = f'{ARTC}/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1/{stem}' if arm == 'own' else f'{ARTC}/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/stage1/{stem}'
    a = [site, prior, arm, '-s', f'/p/fork_inputs/s61/{site}/scene_{prior}', '-m', model, '--eval', '-r', '1', '--data_device', 'cpu',
         '--lod_depth_path', '/p/fork_none', '--da_depth_path', '/p/fork_none', '--stage_switch_iter', '0', '--lambda_lod_init', '0', '--lambda_lod_anchor', '0', '--lambda_da_depth', '0',
         '--jbgs_judgment', 'off', '--jbgs_target', 'on', '--jbgs_target_rev', 'r8', '--jbgs_finaltrain', 'on']
    if arm == 'gt': a += ['--jbgs_targets', f'{ARTC}/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/targets_gt/{stem}.npz', '--jbgs_preserve_freespace', 'off']
    return a + ['--jbgs_target_dir', root, '--jbgs_target_lambda', '.05', '--jbgs_seed', '0', '--iterations', str(iterations), *extra]
PSITE, PPRIOR = 'R1rep_b10', 'ALS'
PROBES = {'r23_a': ('GeoGS-conf-guided-v1-r23', 'own', 'off', ()), 'r23_b': ('GeoGS-conf-guided-v1-r23', 'own', 'off', ()),
          'r28off_a': (FORK, 'own', 'off', ()), 'r28off_b': (FORK, 'own', 'off', ()),
          'r28on_a': (FORK, 'own', 'on', ()), 'r28on_b': (FORK, 'own', 'on', ('JBGS_TRAINLOG_SELFCHECK=1',)),
          'r25gt_a': ('GeoGS-conf-guided-v1-r25', 'gt', 'off', ()), 'r25gt_b': ('GeoGS-conf-guided-v1-r25', 'gt', 'off', ()),
          'r28gt_a': (FORK, 'gt', 'off', ()), 'r28gt_b': (FORK, 'gt', 'off', ()),
          'r23_c': ('GeoGS-conf-guided-v1-r23', 'own', 'off', ()), 'r23_d': ('GeoGS-conf-guided-v1-r23', 'own', 'off', ()), 'r28off_c': (FORK, 'own', 'off', ()), 'r28off_d': (FORK, 'own', 'off', ()),
          'r25gt_c': ('GeoGS-conf-guided-v1-r25', 'gt', 'off', ()), 'r25gt_d': ('GeoGS-conf-guided-v1-r25', 'gt', 'off', ()), 'r28gt_c': (FORK, 'gt', 'off', ()), 'r28gt_d': (FORK, 'gt', 'off', ())}
def probe(gpu, labels):
    for label in labels:
        fork, arm, switch, env = PROBES[label]; root = O/'probe'/label; root.mkdir(parents=True, exist_ok=False)
        extra = ['--densify_from_iter', '100', '--opacity_reset_interval', '200', '--jbgs_capture_iterations', '100', '200', '300', '--test_iterations', '300', '--save_iterations', '300']
        if switch == 'on': extra += ['--jbgs_trainlog', 'on', '--jbgs_trainlog_region', f'/te/region/{PSITE}__{PPRIOR}.json', '--jbgs_trainlog_grads', 'on']
        env = list(env) + ['JBGS_TRAINLOG_CONFIG=/cfg/trainlog_probe.json']
        cmd = command(f'jbgs-trainerr-probe-{label}', 'te_train_entry.py', train_args(PSITE, PPRIOR, arm, f'/te/probe/{label}/model', 300, extra), gpu=int(gpu), fork=fork, env=env, split_site=PSITE)
        dump(root/'command.json', cmd); rc, s = run(cmd, root/'train.log')
        dump(root/'receipt.json', dict(at=now(), label=label, exit_code=rc, seconds=s, scientific_verdict=None)); print(label, rc, round(s), flush=True)

RUNS = {'tl_R1_ALS_gt': ('R1rep_b10', 'ALS', 'gt'), 'tl_B0_LoD2_gt': ('B0_b10', 'LoD2', 'gt'), 'tl_R1_ALS_own': ('R1rep_b10', 'ALS', 'own'), 'tl_B0_LoD2_own': ('B0_b10', 'LoD2', 'own')}
def train(run, gpu, attempt=1, extra_switch=None):
    """record run (order 3.1) or confirm run (6.2: run name cf_..., extra_switch = '--jbgs_bind_background' etc., logging off)."""
    if run.startswith('cf_'):  # cf_<site>_<prior>_<own|gt>_<bindbg|rebind|reassign>_s0, site = e.g. B0_b10
        q = run.split('_'); site, prior, arm = q[1]+'_'+q[2], q[3], q[4]
    else: site, prior, arm = RUNS[run]
    stem = f'{site}__{prior}'; root = O/'runs'/site/run/f'attempt{attempt}'; root.mkdir(parents=True, exist_ok=False); model = f'/te/runs/{site}/{run}/attempt{attempt}/model'
    extra = ['--jbgs_capture_iterations', '7000', '15000', '30000', '--test_iterations', '7000', '15000', '30000', '--save_iterations', '7000', '15000', '30000']
    if run.startswith('tl_'): extra += ['--jbgs_trainlog', 'on', '--jbgs_trainlog_region', f'/te/region/{stem}.json', '--jbgs_trainlog_grads', 'on']
    if extra_switch: extra += [extra_switch, 'on']
    cmd = command(f'jbgs-trainerr-{run}-a{attempt}', 'te_train_entry.py', train_args(site, prior, arm, model, 30000, extra), gpu=int(gpu), env=['JBGS_TRAINLOG_CONFIG=/cfg/trainlog_te.json', 'TE_REQUIRE_RUNTIME=1'], split_site=site)
    dump(root/'command.json', cmd); dump(root/'launch.json', dict(at=now(), gpu=int(gpu), run=run, scientific_verdict=None))
    rc, s = run_(cmd, root/'train.log')
    dump(root/'receipt.json', dict(at=now(), exit_code=rc, seconds=s, status='COMPLETED_30000' if rc == 0 and (root/'TRAINING_COMPLETE.json').exists() else 'ERROR', scientific_verdict=None))
    return rc
run_ = run

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'cpu': sys.exit(job(a[1], *a[2:]))
    if a[0] == 'cpulock': sys.exit(job(a[1], *a[2:], cfg_rw=True))
    if a[0] == 'cpubig': sys.exit(job(a[1], *a[2:], cpus=16, memory='60g'))
    if a[0] == 'gpu': sys.exit(job(a[2], *a[3:], gpu=int(a[1])))
    if a[0] == 'gpufork': sys.exit(job(a[3], *a[4:], gpu=int(a[1]), fork=a[2], name=f'jbgs-trainerr-gpufork-{a[2][-3:]}-{Path(a[3]).stem}-{"-".join(a[4:])}'[:120]))
    if a[0] == 'train': sys.exit(train(a[1], a[2], int(a[3]) if len(a) > 3 else 1, a[4] if len(a) > 4 else None))
    if a[0] == 'probe': sys.exit(probe(a[1], a[2:]))
    if a[0] == 'gtj': sys.exit(gtj(a[1], a[2], a[3], a[4] if len(a) > 4 and a[4] != '-' else '', int(a[5]) if len(a) > 5 else None))
    raise SystemExit(f'unknown {a}')
