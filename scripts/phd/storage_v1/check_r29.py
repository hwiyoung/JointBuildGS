#!/usr/bin/env python3
"""PHD-STORAGE-v1: r29 (storage rules only) vs r28 check on the TRAINERR small example. Host driver, standard library only.

Waits until one GPU has no compute process (running training is never interrupted), then in that GPU, one job at a time:
  1. replay_r28 / replay_r29 : TRAINERR te_replay.py 'dump' with /source = r28, then r29 (start = TRAINERR probe r28off_a
                               complete state at 200, real R1rep_b10 x ALS scene and targets, deterministic, 300 iterations)
  2. replay compare          : gaussian count, tags (target_tag), bound patches (target_index), position, scale, opacity,
                               Adam and density statistics byte-equal (te_replay PARTS)
  3. run_r29_default         : real 300-iteration training, r29 with no save/capture arguments -> saved-file list
  4. run_r29_caps / run_r28_caps : real 300-iteration training with capture 100 200 300 (TRAINERR probe arguments)
                               -> r29 keeps checkpoint.pth only at 300 (removed.json at 100, 200); r28 keeps all three
Outputs: payload /te = phase-payloads/phd/storage_v1/PHD-STORAGE-v1, summary verification/check_r29.json.
Real-training gaussians are reported but not compared byte by byte: TRAINERR rule B shows two identical-setting GPU
runs already differ (bound counts 1-16 apart at 100 iterations); byte equality is tested by the deterministic replay."""
import datetime as dt, json, os, subprocess, sys, time
from pathlib import Path

R = Path(__file__).resolve().parents[3]; ART = R.parent/'JointBuildGS-artifacts'; PH = ART/'phase-payloads/phd'
O = PH/'storage_v1/PHD-STORAGE-v1'; TE = PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1'
TE_CFG = R/'configs/phd/main_trainerr_v1'
GPU_IMAGE = 'sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'
SITE, PRIOR = 'R1rep_b10', 'ALS'; STEM = f'{SITE}__{PRIOR}'
R28, R29 = 'GeoGS-conf-guided-v1-r28', 'GeoGS-conf-guided-v1-r29'
SMALL = ['--densify_from_iter', '100', '--opacity_reset_interval', '200', '--test_iterations', '300']
CAPS = ['--jbgs_capture_iterations', '100', '200', '300', '--save_iterations', '300']


def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def dump(p, v): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=1)+'\n')


def free_gpu():
    q = lambda a: subprocess.run(['nvidia-smi', f'--query-{a}', '--format=csv,noheader'], capture_output=True, text=True).stdout.split('\n')
    gpus = [l.split(', ') for l in q('gpu=index,uuid') if l.strip()]
    busy = {l.strip() for l in q('compute-apps=gpu_uuid') if l.strip()}
    for idx, uuid in gpus:
        if uuid not in busy: return int(idx)
    return None


def command(name, script, args, gpu, fork):
    cmd = ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', '8', '--memory', '40g', '--memory-swap', '40g', '--shm-size', '4g', '--gpus', f'device={gpu}']
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=8', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
              'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True', 'TMPDIR=/te/tmp', 'MPLCONFIGDIR=/te/tmp/mpl', 'XDG_CACHE_HOME=/te/tmp/cache',
              'TORCH_HOME=/weights/torch', 'TZ=Asia/Seoul', 'JBGS_TRAINLOG_CONFIG=/cfg/trainlog_probe.json',
              f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{SITE}/split.json']:
        cmd += ['-e', e]
    s0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'), (O, '/te', 'rw'),
              (TE/'probe', '/te/probe', 'ro'), (TE_CFG, '/cfg', 'ro'), (O/'docs_scratch', '/docs', 'rw'), (s0, '/p', 'ro'), (s0, '/s0', 'ro'),
              (R/'src/phd/forks'/fork, '/source', 'ro'), (PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights', '/weights', 'ro')]
    for src, dst, mode in mounts: cmd += ['-v', f'{src}:{dst}:{mode}']
    pre = 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; '
    return cmd + ['-w', '/source', '--entrypoint', '/bin/bash', GPU_IMAGE, '-c',
                  pre+'exec python -B -u "/repo/scripts/phd/main_trainerr_v1/$0" "$@"', script, *args]


def train_args(model, extra):
    root = f'/art/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1/{STEM}'
    return [SITE, PRIOR, 'own', '-s', f'/p/fork_inputs/s61/{SITE}/scene_{PRIOR}', '-m', model, '--eval', '-r', '1', '--data_device', 'cpu',
            '--lod_depth_path', '/p/fork_none', '--da_depth_path', '/p/fork_none', '--stage_switch_iter', '0', '--lambda_lod_init', '0',
            '--lambda_lod_anchor', '0', '--lambda_da_depth', '0', '--jbgs_judgment', 'off', '--jbgs_target', 'on', '--jbgs_target_rev', 'r8',
            '--jbgs_finaltrain', 'on', '--jbgs_target_dir', root, '--jbgs_target_lambda', '.05', '--jbgs_seed', '0', '--iterations', '300', *extra]


def run(label, script, args, gpu, fork):
    log = O/'logs'/f'{label}.log'; log.parent.mkdir(parents=True, exist_ok=True)
    cmd = command(f'jbgs-storage-{label}'.replace('_', '-'), script, args, gpu, fork); dump(O/'logs'/f'{label}.command.json', cmd)
    t = time.monotonic()
    with log.open('x') as f: rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    print(now(), label, 'exit', rc, round(time.monotonic()-t), flush=True)
    return dict(label=label, fork=fork, gpu=gpu, exit_code=rc, seconds=round(time.monotonic()-t, 1), log=str(log))


def files(model):
    out = []
    for p in sorted(model.rglob('*')):
        if p.is_file(): out.append(dict(path=str(p.relative_to(model)), bytes=p.stat().st_size))
    return out


def main():
    for d in ['tmp/mpl', 'tmp/cache', 'docs_scratch', 'logs', 'verification']: (O/d).mkdir(parents=True, exist_ok=True)
    res = dict(at_start=now(), jobs=[], scientific_verdict=None)
    def wait():  # before every job: a GPU with no compute process, so running training is never shared or interrupted
        while (g := free_gpu()) is None:
            print(now(), 'waiting for a free GPU', flush=True); time.sleep(300)
        return g
    res['jobs'].append(run('replay_r28', 'te_replay.py', ['dump', 'r28', 'own', 'r28off_a'], wait(), R28))
    res['jobs'].append(run('replay_r29', 'te_replay.py', ['dump', 'r29', 'own', 'r28off_a'], wait(), R29))
    res['jobs'].append(run('replay_compare', 'te_replay.py', ['compare', 'r28', 'r29'], wait(), R29))
    cmp_file = O/'verification/replay_compare_r28_r29.json'
    res['replay_compare'] = json.loads(cmp_file.read_text()) if cmp_file.exists() else None
    runs = {'run_r29_default': (R29, SMALL), 'run_r29_caps': (R29, SMALL+CAPS), 'run_r28_caps': (R28, SMALL+CAPS)}
    res['runs'] = {}
    for label, (fork, extra) in runs.items():
        job = run(label, 'te_train_entry.py', train_args(f'/te/{label}/model', extra), wait(), fork); res['jobs'].append(job)
        model = O/label/'model'
        receipts = {p.parent.name: json.loads(p.read_text()) for p in sorted((model/'jbgs_complete').glob('iteration_*/receipt.json'))}
        res['runs'][label] = dict(exit_code=job['exit_code'], files=files(model) if model.exists() else [],
                                  complete_states={k: dict(gaussians=v.get('gaussians'), checkpoint_kept=(model/'jbgs_complete'/k/'checkpoint.pth').exists(),
                                                           removed_json=(model/'jbgs_complete'/k/'removed.json').exists()) for k, v in receipts.items()})
    r29d, r29c, r28c = (res['runs'].get(k, {}) for k in runs)
    states = lambda r: r.get('complete_states', {})
    checks = {
        'replay_byte_equal': bool(res['replay_compare'] and res['replay_compare'].get('status') == 'PASS'),
        'r29_default_captures_only_final': sorted(states(r29d)) == ['iteration_300'],
        'r29_caps_keeps_last_checkpoint_only': {k: v['checkpoint_kept'] for k, v in states(r29c).items()} == {'iteration_100': False, 'iteration_200': False, 'iteration_300': True},
        'r28_caps_keeps_all_checkpoints': all(v['checkpoint_kept'] for v in states(r28c).values()) and len(states(r28c)) == 3,
        'all_exit_zero': all(j['exit_code'] == 0 for j in res['jobs'])}
    res.update(at_end=now(), checks=checks, status='PASS' if all(checks.values()) else 'FAIL')
    dump(O/'verification/check_r29.json', res); print(res['status'], checks, flush=True)
    return 0 if res['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
