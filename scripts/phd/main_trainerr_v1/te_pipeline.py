"""Host driver (order 3, 5): record runs on one GPU in sequence and, in a parallel thread, each finished run's key-iteration meshes
(unchanged GTJUDGE/RESCORE recipe via te_mesh.py), 30000 full score, record-run sets, key-mesh measures, cleaning. Resume-aware.
usage: python3 te_pipeline.py <gpu> <run> [<run> ...]"""
import json, subprocess, sys, threading, time
from pathlib import Path
from launch import O, now, dump, job, gtj, train, RUNS
KEYS = ['30000', '0', '100', '300', '1000', '2000', '3000_pre_reset', '3000', '5000', '7000', '10000', '15000', '20000']
LOG = O/'logs/pipeline.jsonl'
def note(**kw):
    with LOG.open('a') as f: f.write(json.dumps(dict(at=now(), **kw))+'\n')
def model_dir(run):
    site = RUNS[run][0]
    for a in sorted((O/'runs'/site/run).glob('attempt*'), reverse=True):
        if (a/'TRAINING_COMPLETE.json').exists(): return a/'model'
def cont(p): return '/te/'+str(Path(p).relative_to(O))
def must(rc, what):
    if rc: raise RuntimeError(what)
def key_job(run, name, gpu):
    site, prior, arm = RUNS[run]; stem = f'{site}__{prior}'; fam = f'tl_{arm}_{name}'; m = model_dir(run); t0 = time.monotonic()
    wd = O/'gtj/meshes'/f'{stem}__{fam}'/'final_work'; final = O/'gtj/meshes'/f'{stem}__{fam}'/'final.ply'
    done = (O/'meshes'/f'{stem}__{fam}'/'score.json').exists() if name == '30000' else (O/'curves'/f'{run}__{name}.json').exists()
    if done: return
    if not final.exists():
        ply = m/'point_cloud/iteration_30000/point_cloud.ply' if name == '30000' else m.parent/'ply'/f'{name}.ply'
        if not ply.exists(): must(job('te_keyply.py', cont(m), name, gpu=gpu), f'ply {run} {name}')
        if not (O/'gtj/renders'/f'{stem}__{fam}'/'receipt.json').exists(): must(gtj('render', stem, fam, cont(ply), gpu), f'render {fam}')
        if not (wd/'binding.json').exists(): must(gtj('prepare', stem, fam), 'prepare')
        if not (wd/'plan/plan.json').exists(): must(gtj('plan', stem, fam), 'plan')
        n = len(json.loads((wd/'plan/plan.json').read_text())['tiles'])
        for k in range(n):
            if not ((wd/'tiles'/f'tile{k}.npz').exists() and (wd/'tiles'/f'tile{k}.json').exists()): must(gtj(f'tile:{k}', stem, fam), f'tile {k}')
        if not (wd/'merged.json').exists():
            if gtj('merge', stem, fam): must(gtj('recover', stem, fam), f'merge+recover {fam}'); note(step='recovered', run=run, name=name)
        if not final.exists(): must(gtj('finish', stem, fam), 'finish')
    if name == '30000':
        must(gtj('score', stem, fam), 'score'); must(job('te_sets_tl.py', run), 'sets_tl')
    else: must(job('te_measure.py', run, name), 'measure')
    gtj('clean', stem, fam); note(step='key_done', run=run, name=name, seconds=time.monotonic()-t0)
def meshes(run, gpu):
    for name in KEYS:
        for attempt in [1, 2]:
            try: key_job(run, name, gpu); break
            except RuntimeError as e: note(step='key_error', run=run, name=name, attempt=attempt, error=str(e))
    note(step='meshes_done', run=run)
def main(gpu, *runs):
    gpu = int(gpu); ths = []
    for run in runs:
        if model_dir(run) is None:
            rc = train(run, gpu, 1); note(step='train', run=run, attempt=1, rc=rc)
            if rc and model_dir(run) is None: rc = train(run, gpu, 2); note(step='train', run=run, attempt=2, rc=rc)
        if model_dir(run) is None: note(step='no_result', run=run); continue
        if ths: ths[-1].join()  # at most one mesh worker per GPU driver (the next run trained meanwhile)
        th = threading.Thread(target=meshes, args=(run, gpu)); th.start(); ths.append(th)
    for th in ths: th.join()
    note(step='pipeline_done', gpu=gpu, runs=list(runs))
if __name__ == '__main__': main(*sys.argv[1:])
