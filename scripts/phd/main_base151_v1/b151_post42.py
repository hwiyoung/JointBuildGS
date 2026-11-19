#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 4.2 driver (host, stdlib + docker): the mesh units of every finished cell model, then the 151-building scores.

  python3 b151_post42.py unit <run> <unit>        # job -> render (GPU 1 when >= 10 GiB free) -> mesh -> score (both priors for 2DGS)
  python3 b151_post42.py gather <run>             # rows / samples per prior when every unit of the run is scored
  nohup python3 b151_post42.py watch [workers] > OUT/logs/post42.log 2>&1 &   # all runs, cells as they finish; <= workers units at once
Memory: a mesh tile step starts only when host MemAvailable >= 40 GB; the containers are named jbgs-b151-post-* (stopped first by the
training queue's host guard at < 25 GB). scientific_verdict: null
"""
import concurrent.futures
import json
import sys
import threading
import time
from pathlib import Path

from b151_host import C, OUT, avail_gb, dump, gpu_free_mib, issue, now, progress
from b151_post41 import M, gt_cpu, render_cmd, sh

GPU_LOCK = threading.Lock()


def lay():
    return json.loads((M / 'units/layout.json').read_text())['units']


def cell_done(run, k):
    p = OUT / 'runs' / run / f'cell{k}' / 'receipt.json'
    return p.exists() and json.loads(p.read_text())['status'] == 'TRAINING_COMPLETE'


def priors_of(run):
    m = run.split('_')[1]
    return ('ALS', ['ALS', 'LoD2']) if m == '2DGS' else (run.split('_')[2], [run.split('_')[2]])


def unit(run, uname):
    t0 = time.monotonic()
    key_prior, score_priors = priors_of(run)
    key = f'{uname}__{key_prior}__{run}'
    tag = key.replace('_', '-').lower()
    log = OUT / 'logs' / 'post42' / f'{key}.log'
    if run.split('_')[1] == 'LGDM':   # depth composite in place of the render (user decision 2026-11-19)
        if not (M / 'renders' / key / 'receipt.json').exists():
            if not sh(gt_cpu(f'{tag}-lgdm', '/b151s/b151_lgdm_renders.py', 'unit', run, uname, cpus='4', mem='16g'), log):
                return False
    elif not (M / 'jobs' / f'{key}.json').exists():
        if not sh(gt_cpu(f'{tag}-job', '/b151s/b151_units.py', 'job', run, uname, cpus='2', mem='4g'), log):
            return False
    if not (M / 'renders' / key / 'receipt.json').exists():
        with GPU_LOCK:
            while gpu_free_mib() < 10 * 1024:
                time.sleep(120)
            if not sh(render_cmd(run.split('_')[1], key), log):
                return False
    t1 = time.monotonic()
    root = M / 'meshes' / key
    wd = root / 'final_work'
    if not (root / 'final.json').exists():
        for step in ['prepare', 'plan']:
            if step == 'prepare' and (wd / 'inputs/meta.json').exists():
                continue
            if step == 'plan' and (wd / 'plan/layout.json').exists():
                continue
            if not sh(gt_cpu(f'{tag}-{step}', '/b151s/b151_units.py', 'mesh', key, step, cpus='6', mem='24g'), log):
                return False
        for tile in json.loads((wd / 'plan/layout.json').read_text())['tiles']:
            k = tile['k']
            if (wd / 'tiles' / f'tile{k}.json').exists():
                continue
            while avail_gb() < 40:
                time.sleep(120)
            if not sh(gt_cpu(f'{tag}-t{k}', '/b151s/b151_units.py', 'mesh', key, f'tile:{k}', cpus='6', mem='24g'), log):
                return False
        for step in ['merge', 'finish']:
            if not sh(gt_cpu(f'{tag}-{step}', '/b151s/b151_units.py', 'mesh', key, step, cpus='6', mem='32g'), log):
                return False
    t2 = time.monotonic()
    for prior in score_priors:
        if not (M / 'score151' / f'{run}__{prior}' / f'{uname}.npz').exists():
            if not sh(gt_cpu(f'{tag}-s-{prior.lower()}', '/b151s/b151_score151.py', 'unit', run, prior, uname, cpus='6', mem='24g'), log):
                return False
    t3 = time.monotonic()
    dump(OUT / 'post42' / run / f'{uname}_timing.json', dict(at=now().isoformat(), run=run, unit=uname, render_seconds=t1 - t0, mesh_seconds=t2 - t1,
                                                           score_seconds=t3 - t2, scientific_verdict=None))
    return True


def gather(run):
    _, priors = priors_of(run)
    ok = True
    for prior in priors:
        ok &= sh(gt_cpu(f'gather-{run}-{prior}'.replace('_', '-').lower(), '/b151s/b151_score151.py', 'gather', run, prior, cpus='4', mem='32g'),
                 OUT / 'logs' / 'post42' / f'gather_{run}_{prior}.log')
    dump(OUT / 'post42' / run / 'done42.json', dict(at=now().isoformat(), run=run, ok=bool(ok), scientific_verdict=None))
    progress(f'4.2 {run}: 단위 32개 채점 모음 {"끝" if ok else "실패"}')
    return ok


def watch(workers='2', which='gs'):
    c = json.loads((C / 'base151_v1.json').read_text())
    if which == 'lgdm':   # LGDM runs: no training, every unit at once
        c = dict(c, training_order=['b151_LGDM_ALS', 'b151_LGDM_LoD2'])
    done, failed = set(), set()
    with concurrent.futures.ThreadPoolExecutor(int(workers)) as pool:
        running = {}
        while True:
            for fut, item in list(running.items()):
                if fut.done():
                    del running[fut]
                    (done if fut.result() else failed).add(item)
                    if item in failed:
                        issue(f'4.2 단위 실패: {item}')
            for run in c['training_order']:
                if (OUT / 'post42' / run / 'done42.json').exists():
                    continue
                units = lay()
                for u in units:
                    item = (run, u['unit'])
                    if item in done or item in failed or item in running.values() or len(running) >= int(workers):
                        continue
                    if which == 'lgdm' or cell_done(run, u['cell']):
                        running[pool.submit(unit, run, u['unit'])] = item
                if all((run, u['unit']) in done for u in units):
                    gather(run)
            if (OUT / 'control/POST_STOP').exists():
                return
            if all((OUT / 'post42' / r / 'done42.json').exists() for r in c['training_order']) and not running:
                return
            time.sleep(120)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'unit':
        print(unit(a[1], a[2]))
    elif a[0] == 'gather':
        gather(a[1])
    elif a[0] == 'watch':
        watch(*a[1:])
