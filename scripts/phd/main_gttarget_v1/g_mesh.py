"""Host mesh driver (TRAINERR addendum3 a3_mesh.job rule): render -> NVMe work folder (GT_FASTWORK, symlinked final_work) -> prepare, plan,
tiles, merge (+recover), finish -> te_mesh score -> clean. Outputs: O/gtj/meshes/<key>/final.ply, O/meshes/<key>/{points.npz, score.json}.
usage: GT_FASTWORK=<dir> python3 g_mesh.py <workers> <stem>:<family>:<render>[:<arg>...] ...
  render = target            -> g1_render_target.py <stem> <family> (CPU, gtj container)
  render = model:<gpu>:<ply>:<variant> -> g3_render_model.py <stem> <family> <ply> <variant> (GPU, gtj container)"""
import json, os, shutil, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location('gtt_launch', Path(__file__).resolve().parent/'launch.py'); A = importlib.util.module_from_spec(spec); spec.loader.exec_module(A)
FAST = A.FAST; LOCK = threading.Lock(); TAKEN = set(); SH = A.O/'gtj'
def note(**k):
    with (A.O/'logs/mesh_pipeline.jsonl').open('a') as f: f.write(json.dumps(dict(at=A.now(), **k), ensure_ascii=False)+'\n')
def must(rc, what):
    if rc: raise RuntimeError(f'{what} exit {rc}')
def views(site):
    dst = SH/'views'/f'{site}.json'
    if dst.exists(): return
    src = A.PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/views'/f'{site}.json'
    dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst); note(step='views', site=site, source=str(src))
def job(spec_):
    q = spec_.split(':'); stem, fam, kind = q[0], q[1], q[2]; key = f'{stem}__{fam}'
    root = SH/'meshes'/key; wd = root/'final_work'; final = root/'final.ply'; t0 = time.monotonic()
    if (A.O/'meshes'/key/'score.json').exists(): return
    if not (SH/'scenes'/stem/'rows.npz').exists(): must(A.gtj('shadow', stem, '-'), 'shadow')
    views(stem.split('__')[0])
    if not final.exists():
        if not (SH/'renders'/key/'receipt.json').exists():
            if kind == 'target': must(A.gtjscript('g1_render_target.py', [stem, fam]), f'render {key}')
            else: gpu, ply, variant = q[3], q[4], q[5]; must(A.gtjscript('g3_render_model.py', [stem, fam, ply, variant], int(gpu)), f'render {key}')
        if not (wd/'binding.json').exists():
            fw = FAST/key/'final_work'
            if wd.is_symlink(): wd.unlink()
            elif wd.exists(): shutil.move(str(wd), str(root/f'final_work_hdd_superseded_{int(time.time())}'))
            if fw.exists(): shutil.rmtree(fw)
            fw.mkdir(parents=True); root.mkdir(parents=True, exist_ok=True); os.symlink(fw, wd)
            must(A.gtj('prepare', stem, fam), 'prepare')
        if not (wd/'plan/plan.json').exists(): must(A.gtj('plan', stem, fam), 'plan')
        n = len(json.loads((wd/'plan/plan.json').read_text())['tiles'])
        for k in range(n):
            if not ((wd/'tiles'/f'tile{k}.npz').exists() and (wd/'tiles'/f'tile{k}.json').exists()): must(A.gtj(f'tile:{k}', stem, fam), f'tile {k}')
        if not (wd/'merged.json').exists():
            if A.gtj('merge', stem, fam): must(A.gtj('recover', stem, fam), f'merge+recover {fam}'); note(step='recovered', stem=stem, family=fam)
        if not final.exists(): must(A.gtj('finish', stem, fam), 'finish')
    must(A.gtj('score', stem, fam), 'score'); A.gtj('clean', stem, fam)
    if wd.is_symlink():
        fw = Path(os.readlink(wd)); keep = root/'final_work_receipts'; keep.mkdir(exist_ok=True)
        for f in list(fw.glob('*.json'))+list((fw/'plan').glob('*.json')): shutil.copy2(f, keep/f.name)
        wd.unlink(); shutil.rmtree(fw.parent, ignore_errors=True)
    note(step='mesh_done', key=key, seconds=time.monotonic()-t0)
def worker(queue):
    while True:
        with LOCK:
            nxt = next((q for q in queue if q not in TAKEN), None)
            if nxt is None: return
            TAKEN.add(nxt)
        for attempt in [1, 2]:
            try: job(nxt); break
            except RuntimeError as e: note(step='mesh_error', job=nxt, attempt=attempt, error=str(e))
def main(workers, *jobs):
    assert FAST is not None, 'GT_FASTWORK required (NVMe)'
    th = [threading.Thread(target=worker, args=(list(jobs),)) for _ in range(int(workers))]
    for t in th: t.start(); time.sleep(5)
    for t in th: t.join()
    note(step='g_mesh_done', jobs=list(jobs))
if __name__ == '__main__': main(*sys.argv[1:])
