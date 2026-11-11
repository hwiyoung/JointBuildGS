"""Host orchestration (docker commands) for PHD-MAIN-TRAINLOG-v1. Adapted from FINALTRAIN/RELEASE gpu_job.py."""
import datetime as dt, json, os, subprocess, sys, time
from pathlib import Path
R = Path(__file__).resolve().parents[3]; ART = R.parent/'JointBuildGS-artifacts'; PH = ART/'phase-payloads/phd'
O = PH/'main_trainlog_v1/PHD-MAIN-TRAINLOG-v1'; C = R/'configs/phd/main_trainlog_v1'; D = R/'docs/experiments/phd/main_trainlog_v1'
GPU_IMAGE = 'sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'
CPU_IMAGE = 'sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
SITE = 'B173nb_b10'; PRIOR = 'ALS'
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p, v): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')
def command(name, script, args=(), gpu=None, fork='GeoGS-conf-guided-v1-r27', env=(), cpus=8, memory='40g', image=None):
    image = image or (GPU_IMAGE if gpu is not None else CPU_IMAGE)
    cmd = ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', str(cpus), '--memory', memory, '--memory-swap', memory, '--shm-size', '4g']
    cmd += ['--gpus', f'device={gpu}'] if gpu is not None else ['--runtime', 'runc', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES=']
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=4', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
              'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True', f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{SITE}/split.json',
              'TMPDIR=/tl/tmp', 'MPLCONFIGDIR=/tl/tmp/mpl', 'XDG_CACHE_HOME=/tl/tmp/cache', 'TORCH_HOME=/weights/torch', 'TZ=Asia/Seoul', *env]:
        cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'), (O, '/tl', 'rw'), (C, '/cfg', 'rw' if script in ['freeze.py', 'seal_runtime.py'] else 'ro'), (D, '/docs', 'rw'),
              (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1', '/p', 'ro'), (PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1', '/s0', 'ro'),
              (R/'src/phd/forks'/fork, '/source', 'ro'), (PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights', '/weights', 'ro')]
    for s, d, m in mounts: cmd += ['-v', f'{s}:{d}:{m}']
    pre = 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; ' if gpu is not None else ''
    return cmd + ['-w', '/source', '--entrypoint', '/bin/bash', image, '-c', pre+'exec python -B -u "/repo/scripts/phd/main_trainlog_v1/$0" "$@"', script, *args]
def train_args(model, iterations=30000, extra=()):
    return [SITE, PRIOR, '-s', f'/p/fork_inputs/s61/{SITE}/scene_{PRIOR}', '-m', model, '--eval', '-r', '1', '--data_device', 'cpu',
            '--lod_depth_path', '/p/fork_none', '--da_depth_path', '/p/fork_none', '--stage_switch_iter', '0', '--lambda_lod_init', '0', '--lambda_lod_anchor', '0', '--lambda_da_depth', '0',
            '--jbgs_judgment', 'off', '--jbgs_target', 'on', '--jbgs_target_rev', 'r8', '--jbgs_finaltrain', 'on',
            '--jbgs_target_dir', f'/art/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1/{SITE}__{PRIOR}',
            '--jbgs_target_lambda', '.05', '--jbgs_seed', '0', '--iterations', str(iterations), *extra]
def run(cmd, log):
    log.parent.mkdir(parents=True, exist_ok=True); t = time.monotonic()
    with log.open('x') as f: rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    return rc, time.monotonic()-t
PROBES = {'r23': ('GeoGS-conf-guided-v1-r23', None, ()), 'r27_off_a': ('GeoGS-conf-guided-v1-r27', 'off', ()), 'r27_off_b': ('GeoGS-conf-guided-v1-r27', 'off', ()),
          'r27_on_a': ('GeoGS-conf-guided-v1-r27', 'on', ()), 'r27_on_b': ('GeoGS-conf-guided-v1-r27', 'on', ('JBGS_TRAINLOG_SELFCHECK=1',)),
          'r27_off_c': ('GeoGS-conf-guided-v1-r27', 'off', ()), 'r27_off_d': ('GeoGS-conf-guided-v1-r27', 'off', ()),
          'r23_b': ('GeoGS-conf-guided-v1-r23', None, ()), 'r23_c': ('GeoGS-conf-guided-v1-r23', None, ()), 'r23_d': ('GeoGS-conf-guided-v1-r23', None, ()),
          'r27_on_c': ('GeoGS-conf-guided-v1-r27', 'on', ()), 'r27_on_d': ('GeoGS-conf-guided-v1-r27', 'on', ('JBGS_TRAINLOG_SELFCHECK=1',))}
def probe(labels):
    cfgp = O/'probe/trainlog_probe.json'
    if not cfgp.exists():
        c = json.loads((C/'trainlog_v1.json').read_text()); tl = dict(c['training_log']); tl['save_iterations'] = list(range(0, 301, 50))
        dump(cfgp, dict(training_log=tl, scope=c['scope'], coordinates=c['coordinates'], note='unit-check schedule only; derived from trainlog_v1.json'))
    for label in labels:
        fork, switch, env = PROBES[label]; root = O/'probe'/label; root.mkdir(parents=True, exist_ok=False)
        extra = ['--densify_from_iter', '100', '--opacity_reset_interval', '200', '--jbgs_capture_iterations', '100', '200', '300',
                 '--test_iterations', '300', '--save_iterations', '300']
        if switch: extra += ['--jbgs_trainlog', switch]
        env = list(env) + ['JBGS_TRAINLOG_CONFIG=/tl/probe/trainlog_probe.json']
        cmd = command(f'jbgs-trainlog-probe-{label}', 'train_entry.py', train_args(f'/tl/probe/{label}/model', 300, extra), gpu=0, fork=fork, env=env)
        dump(root/'command.json', cmd); rc, s = run(cmd, root/'train.log')
        dump(root/'receipt.json', dict(at=now(), label=label, exit_code=rc, seconds=s, scientific_verdict=None)); print(label, rc, round(s), flush=True)
        if rc: raise SystemExit(f'probe {label} failed')
def train(gpu=0):
    root = O/'runs'/SITE/'tl_B173nb_b10_ALS_s0'/'attempt1'; root.mkdir(parents=True, exist_ok=False)
    extra = ['--jbgs_capture_iterations', '7000', '15000', '30000', '--test_iterations', '7000', '15000', '30000', '--save_iterations', '7000', '15000', '30000', '--jbgs_trainlog', 'on']
    model = '/tl/'+str((root/'model').relative_to(O))
    cmd = command('jbgs-trainlog-B173nb_b10-ALS-a1', 'train_entry.py', train_args(model, 30000, extra), gpu=int(gpu),
                  env=['JBGS_TRAINLOG_CONFIG=/cfg/trainlog_v1.json', 'TRAINLOG_REQUIRE_RUNTIME=1'])
    dump(root/'command.json', cmd); dump(root/'launch.json', dict(at=now(), gpu=int(gpu), scientific_verdict=None))
    rc, s = run(cmd, root/'train.log')
    dump(root/'receipt.json', dict(at=now(), exit_code=rc, seconds=s, status='COMPLETED_30000' if rc == 0 and (root/'TRAINING_COMPLETE.json').exists() else 'ERROR', scientific_verdict=None))
def job(kind, script, *args, gpu=None, name=None, fork='GeoGS-conf-guided-v1-r27', cpus=8, memory='40g'):
    name = name or f'jbgs-trainlog-{kind}-{Path(script).stem}'
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}_{Path(script).stem}_{"_".join(args)[:60]}.log'
    cmd = command(name, script, list(args), gpu=gpu, fork=fork, cpus=cpus, memory=memory, image=GPU_IMAGE if kind == 'torch' else None)
    rc, s = run(cmd, log); print(script, args, rc, round(s), log, flush=True); return rc

def meshcmd(step, family='', ply='', gpu=None):
    """GTJUDGE/RESCORE mesh+score code with a task-local shadow /gtjudge (inputs symlinked read-only)."""
    sh = O/'gtj'; sh.mkdir(exist_ok=True); (O/'gtj_docs').mkdir(exist_ok=True)
    image = GPU_IMAGE if gpu is not None else CPU_IMAGE
    name = f'jbgs-trainlog-mesh-{step.replace(":", "")}-{family}'[:120]
    cmd = ['nice', '-n', '19', 'docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', '12', '--memory', '40g', '--memory-swap', '40g', '--shm-size', '4g']
    cmd += ['--gpus', f'device={gpu}'] if gpu is not None else ['--runtime', 'runc', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES=']
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=8', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1', 'TMPDIR=/gtjudge/tmp',
              'MPLCONFIGDIR=/gtjudge/tmp/mpl', 'XDG_CACHE_HOME=/gtjudge/tmp/cache', 'TZ=Asia/Seoul', 'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True']:
        cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'), (PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1', '/out', 'ro'),
              (PH/'main_release_v1/PHD-MAIN-RELEASE-v1', '/release', 'ro'), (sh, '/gtjudge', 'rw'), (R/'configs/phd/main_gtjudge_v1', '/cfg', 'ro'),
              (O/'gtj_docs', '/docs', 'rw'), (O, '/tl', 'rw'), (R/'src/phd/forks/GeoGS-conf-guided-v1-r27', '/source', 'ro'), (Path('/usr/share/fonts/opentype/noto'), '/fonts', 'ro')]
    for s_, d, m in mounts: cmd += ['-v', f'{s_}:{d}:{m}']
    pre = 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; ' if gpu is not None else ''
    args = [a for a in [step, family, ply] if a]
    return cmd + ['-w', '/source' if gpu is not None else '/gtjudge', '--entrypoint', '/bin/bash', image, '-c', pre+'exec python -B -u /repo/scripts/phd/main_trainlog_v1/tl_mesh.py "$@"', 'tl_mesh', *args]
def mesh(step, family='', ply='', gpu=None):
    log = O/'logs'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}_mesh_{step.replace(":", "")}_{family}.log'
    rc, s = run(meshcmd(step, family, ply, gpu), log); print('mesh', step, family, rc, round(s), flush=True)
    with (O/'logs/mesh_timing.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), step=step, family=family, exit_code=rc, seconds=s, log=str(log)))+'\n')
    if rc: raise SystemExit(f'mesh {step} {family} failed: {log}')
def mesh_all(family, ply, gpu=0):
    for st in ['render']: mesh(st, family, ply, gpu=gpu)
    for st in ['prepare', 'plan']: mesh(st, family)
    n = len(json.loads((O/'gtj/meshes'/f'B173nb_b10__ALS__{family}'/'final_work/plan/plan.json').read_text())['tiles'])
    for k in range(n): mesh(f'tile:{k}', family)
    for st in ['merge', 'finish', 'score']: mesh(st, family)
if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'probe': probe(a[1:] or list(PROBES))
    elif a[0] == 'train': train(*a[1:])
    elif a[0] in ['cpu', 'torch']: sys.exit(job(a[0], a[1], *a[2:]))
    elif a[0] == 'gpu': sys.exit(job('gpu', a[2], *a[3:], gpu=int(a[1])))
    elif a[0] == 'gpufork': sys.exit(job('gpu', a[3], *a[4:], gpu=int(a[1]), fork=a[2], name=f'jbgs-trainlog-gpufork-{a[2][-3:]}'))
    elif a[0] == 'mesh': mesh(a[1], *a[2:4], gpu=int(a[4]) if len(a) > 4 else None)
    elif a[0] == 'mesh_all': mesh_all(a[1], a[2], int(a[3]) if len(a) > 3 else 0)
