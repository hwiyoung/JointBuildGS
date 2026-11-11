"""Container entry: verify the TRAINUNIT lock, install the FINALTRAIN renderer, run the unchanged r23 train.py.

Only two host-side controls are added around the unchanged jbgs_state.after_step hook:
  - at iteration 500 the locked time rule (projected = factor x elapsed) may stop the run (no state needed);
  - a stop file (deadline) makes the unchanged capture code write a complete state at the next multiple of 100, then stop.
Neither control changes any value used by the optimisation.
"""
import datetime as dt
import hashlib
import importlib.util
import json
import runpy
import sys
import time
from pathlib import Path

C = Path('/repo/configs/phd/main_trainunit_v1')
FTC = Path('/repo/configs/phd/main_finaltrain_v1/finaltrain_v1.json')
KST = dt.timezone(dt.timedelta(hours=9))


def now():
    return dt.datetime.now(KST)


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def dump(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    run_name = sys.argv[1]
    lock = json.loads((C / 'trainunit_v1.initial.lock.json').read_text())
    assert sha(C / 'trainunit_v1.json') == lock['config_sha256'], 'TRAINUNIT config changed after lock'
    cfg = json.loads((C / 'trainunit_v1.json').read_text())
    deadline = dt.datetime.fromisoformat(cfg['gpu']['deadline'])
    factor = 147.1
    argv = sys.argv[2:]
    model = Path(argv[argv.index('-m') + 1])
    assert not model.exists(), model
    control = Path(argv[argv.index('--jbgs_target_dir') + 1])
    stopfile = Path('/tu/control') / f'STOP_{run_name}'
    root = model.parent

    ft = json.loads(FTC.read_text())['renderer']
    import torch
    import diff_surfel_rasterization as raster
    assert sha(ft['path']) == ft['sha256']
    spec = importlib.util.spec_from_file_location('jbgs_rfix_speed_target', ft['path'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.jbgs_set_guard(ft['binning_guard_fraction'])
    raster._C = module

    sys.path.insert(0, '/source')
    import jbgs_state
    original = jbgs_state.after_step
    state = dict(checked500=False, stop_capture=None)

    def after_step(env):
        it = env['iteration']
        args = env['args']
        if it == 501 and not state['checked500']:
            # same clock as the locked factor: target_monitor/curve.jsonl elapsed_seconds at iteration 500
            state['checked500'] = True
            rows = [json.loads(l) for l in (model / 'target_monitor/curve.jsonl').read_text().splitlines() if l.strip()]
            elapsed = next(r['elapsed_seconds'] for r in rows if r['iteration'] == 500)
            total_iter = args.iterations
            projected = factor * elapsed * (total_iter / 30000.0)
            end = now() + dt.timedelta(seconds=projected - elapsed)
            rec = dict(at=now().isoformat(), iteration=500, elapsed_seconds=elapsed, clock='target_monitor curve.jsonl elapsed_seconds',
                       factor=factor, projected_total_seconds=projected, projected_end=end.isoformat(), deadline=deadline.isoformat(),
                       gaussians=len(env['gaussians'].get_xyz),
                       peak_reserved_bytes=torch.cuda.max_memory_reserved(), scientific_verdict=None)
            dump(root / 'time_check_500.json', rec)
            if end > deadline:
                rec['status'] = 'TIME_STOP_500'
                dump(root / 'TIME_STOP.json', rec)
                print('TRAINUNIT_TIME_STOP', json.dumps(rec), flush=True)
                original(env)
                return True
        if state['stop_capture'] is None and it % 100 == 0 and stopfile.exists():
            state['stop_capture'] = it
            if it not in args.jbgs_capture_iterations:
                args.jbgs_capture_iterations = list(args.jbgs_capture_iterations) + [it]
            dump(root / 'DEADLINE_STOP.json', dict(at=now().isoformat(), iteration=it, gaussians=len(env['gaussians'].get_xyz),
                 complete_state=f'model/jbgs_complete/iteration_{it}', peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                 scientific_verdict=None))
            original(env)
            print('TRAINUNIT_DEADLINE_STOP', it, flush=True)
            return True
        return original(env)

    jbgs_state.after_step = after_step
    dump(root / 'input_binding.json', dict(at=now().isoformat(), run=run_name, config_sha256=lock['config_sha256'],
         renderer=ft, target_dir=str(control), argv=argv, scientific_verdict=None))
    sys.argv = ['/source/train.py'] + argv
    try:
        runpy.run_path('/source/train.py', run_name='__main__')
    except Exception as e:
        text = f'{type(e).__name__}: {e}'
        dump(root / 'ERROR.json', dict(at=now().isoformat(), error=text[:4000], oom='out of memory' in text.lower(),
             peak_reserved_bytes=torch.cuda.max_memory_reserved(), peak_allocated_bytes=torch.cuda.max_memory_allocated(),
             scientific_verdict=None))
        raise
    final = args_iterations(argv)
    if (model / f'jbgs_complete/iteration_{final}/checkpoint.pth').is_file() and (model / f'point_cloud/iteration_{final}/point_cloud.ply').is_file():
        dump(root / 'TRAINING_COMPLETE.json', dict(at=now().isoformat(), iteration=final, scientific_verdict=None))


def args_iterations(argv):
    return int(argv[argv.index('--iterations') + 1])


if __name__ == '__main__':
    main()
