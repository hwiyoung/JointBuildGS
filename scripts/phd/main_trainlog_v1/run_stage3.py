"""Host driver for stage 3 while/after training: renders of every saved state, key-iteration meshes + scores + lineage.
GPU steps run on GPU 1 one at a time (lock); CPU mesh steps run in two worker threads. Waits for states to appear."""
import json, subprocess, sys, threading, time
from pathlib import Path
from launch import O, now, mesh, job
RUNM = O/'runs/B173nb_b10/tl_B173nb_b10_ALS_s0/attempt2/model'; GPU = 1; LOCK = threading.Lock(); LOG = O/'logs/stage3_driver.jsonl'
KEY = [0, 100, 300, 1000, 2000, 3000, 5000, 7000, 10000, 15000, 20000, 30000]
def note(**kw):
    with LOG.open('a') as f: f.write(json.dumps(dict(at=now(), **kw))+'\n')
def saved():
    p = RUNM/'trainlog/saves.jsonl'
    return [json.loads(l)['name'] for l in p.read_text().splitlines()] if p.exists() else []
def finished(): return (RUNM.parent/'receipt.json').exists()
def gpu(script, *args):
    with LOCK:
        t = time.monotonic(); rc = job('gpu', script, *args, gpu=GPU, name=f'jbgs-trainlog-s3-{Path(script).stem}-{"-".join(args)[:40]}'); note(step=script, args=list(args), rc=rc, seconds=time.monotonic()-t)
        if rc: raise SystemExit(f'{script} {args} failed')
def gpumesh(name, ply):
    with LOCK:
        t = time.monotonic(); mesh('render', f'tl_{name}', ply, gpu=GPU); note(step='mesh_render', name=name, seconds=time.monotonic()-t)
def key_job(it):
    name = str(it)
    while name not in saved():
        if finished() and name not in saved(): note(step='missing_state', name=name); return
        time.sleep(60)
    if not (O/'ply'/f'{name}.ply').exists(): gpu('lineage_key.py', 'ply', name)
    fam = f'tl_{name}'; t0 = time.monotonic()
    if not (O/'meshes'/fam/'score.json').exists():
        gpumesh(name, f'/tl/ply/{name}.ply'); t1 = time.monotonic()
        for st in ['prepare', 'plan']: mesh(st, fam)
        n = len(json.loads((O/'gtj/meshes'/f'B173nb_b10__ALS__{fam}'/'final_work/plan/plan.json').read_text())['tiles'])
        for k in range(n): mesh(f'tile:{k}', fam)
        for st in ['merge', 'finish', 'score']: mesh(st, fam)
        note(step='mesh_done', name=name, seconds_total=time.monotonic()-t0, seconds_cpu=time.monotonic()-t1)
    if not (O/'lineage'/f'{name}.json').exists(): gpu('lineage_key.py', 'lineage', name)
def render_loop():
    done = set()
    while True:
        names = [n for n in saved() if n not in done and not (O/'renders'/n/'render.json').exists()]
        if names:
            gpu('render_states.py', *names[:8]); done |= set(names[:8]); continue
        if finished() and not [n for n in saved() if not (O/'renders'/n/'render.json').exists()]: break
        time.sleep(60)
    note(step='renders_done')
def worker(items):
    for it in items:
        try: key_job(it)
        except SystemExit as e: note(step='error', item=it, error=str(e))
if __name__ == '__main__':
    keys = [int(x) for x in sys.argv[1:]] or KEY
    th = [threading.Thread(target=render_loop), threading.Thread(target=worker, args=(keys[0::2],)), threading.Thread(target=worker, args=(keys[1::2],))]
    for t in th: t.start()
    for t in th: t.join()
    note(step='stage3_driver_done')
