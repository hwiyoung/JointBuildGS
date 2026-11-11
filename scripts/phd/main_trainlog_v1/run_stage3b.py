"""Resume-aware key worker (replaces run_stage3 workers A/B after the 15,000 collision risk). Every step is skipped when its
output exists; a running container for the same family/step is waited for, never duplicated."""
import json, subprocess, sys, threading, time
from pathlib import Path
from launch import O, now, mesh, job
import run_stage3 as S
GPU = 1; LOCK = threading.Lock()
def running(fam):
    out = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True).stdout.split()
    return [n for n in out if n.endswith('-'+fam) and n.startswith('jbgs-trainlog-mesh-')]
def wait_free(fam):
    while running(fam): time.sleep(30)
def gpu(script, *args):
    with LOCK:
        rc = job('gpu', script, *args, gpu=GPU, name=f'jbgs-trainlog-s3b-{Path(script).stem}-{"-".join(args)[:40]}'); S.note(step=script, args=list(args), rc=rc, driver='b')
        if rc: raise SystemExit(f'{script} {args} failed')
def key_job(name):
    fam = f'tl_{name}'; wd = O/'gtj/meshes'/f'B173nb_b10__ALS__{fam}'/'final_work'; t0 = time.monotonic(); wait_free(fam)
    if not (O/'ply'/f'{name}.ply').exists(): gpu('lineage_key.py', 'ply', name)
    if not (O/'meshes'/fam/'score.json').exists():
        if not (O/'gtj/renders'/f'B173nb_b10__ALS__{fam}'/'receipt.json').exists():
            with LOCK: mesh('render', fam, f'/tl/ply/{name}.ply', gpu=GPU)
        if not (wd/'binding.json').exists(): mesh('prepare', fam)
        if not (wd/'plan/plan.json').exists(): mesh('plan', fam)
        n = len(json.loads((wd/'plan/plan.json').read_text())['tiles'])
        for k in range(n):
            if not ((wd/'tiles'/f'tile{k}.npz').exists() and (wd/'tiles'/f'tile{k}.json').exists()): mesh(f'tile:{k}', fam)
        if not (wd/'merged.json').exists(): mesh('merge', fam)
        if not (O/'gtj/meshes'/f'B173nb_b10__ALS__{fam}'/'final.ply').exists(): mesh('finish', fam)
        mesh('score', fam)
    if not (O/'lineage'/f'{name}.json').exists(): gpu('lineage_key.py', 'lineage', name)
    S.note(step='mesh_done_b', name=name, seconds_total=time.monotonic()-t0)
def worker(items):
    for n in items:
        try: key_job(n)
        except SystemExit as e: S.note(step='error', item=n, error=str(e), driver='b')
if __name__ == '__main__':
    lists = [x.split(',') for x in sys.argv[1:]]
    th = [threading.Thread(target=worker, args=(l,)) for l in lists]
    for t in th: t.start()
    for t in th: t.join()
    S.note(step='stage3b_done', lists=lists)
