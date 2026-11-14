"""Host mesh driver for addendum 4 (TRAINERR te_pipeline2.py rule): render (GPU) -> NVMe work folder (TE_FASTWORK, symlinked final_work) ->
prepare, plan, tiles, merge (+recover), finish -> te_mesh score -> clean; final.ply, scores and receipts stay in payload addendum4/gtj and addendum4/meshes.
usage: TE_FASTWORK=<dir> python3 a3_mesh.py <workers> <stem>:<family>:<ply container path in the gtj container>:<gpu> [...]
The site view list in the shadow is copied first from the TRAINERR shadow (same sha256 as the TRAINLOG case shadow)."""
import json, os, shutil, subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import a4_launch as A
FAST = A.FAST; LOCK = threading.Lock(); TAKEN = set(); SH = A.A4O/'gtj'
def note(**k):
    with (A.LOGS/'mesh_pipeline.jsonl').open('a') as f: f.write(json.dumps(dict(at=A.now(), **k), ensure_ascii=False)+'\n')
def must(rc, what):
    if rc: raise RuntimeError(f'{what} exit {rc}')
def views(site, src=None):
    dst = SH/'views'/f'{site}.json'
    if dst.exists(): return
    src = Path(src) if src else A.O/'gtj/views'/f'{site}.json'
    if not src.exists(): src = A.PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/views'/f'{site}.json'   # GTJUDGE list (B173: 203 real views)
    dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst); note(step='views', site=site, source=str(src))
def job(stem, fam, ply, gpu):
    root = SH/'meshes'/f'{stem}__{fam}'; wd = root/'final_work'; final = root/'final.ply'; t0 = time.monotonic()
    if (A.A4O/'meshes'/f'{stem}__{fam}'/'score.json').exists(): return
    if not (SH/'scenes'/stem/'rows.npz').exists(): must(A.gtj('shadow', stem, '-'), 'shadow')
    views(stem.split('__')[0])
    if not final.exists():
        if not (SH/'renders'/f'{stem}__{fam}'/'receipt.json').exists(): must(A.gtj('render', stem, fam, ply, int(gpu)), f'render {fam}')
        if not (wd/'binding.json').exists():
            fw = FAST/f'{stem}__{fam}'/'final_work'
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
    note(step='mesh_done', stem=stem, family=fam, seconds=time.monotonic()-t0)
def worker(queue):
    while True:
        with LOCK:
            nxt = next((q for q in queue if q not in TAKEN), None)
            if nxt is None: return
            TAKEN.add(nxt)
        for attempt in [1, 2]:
            try: job(*nxt.split(':')); break
            except RuntimeError as e: note(step='mesh_error', job=nxt, attempt=attempt, error=str(e))
def main(workers, *jobs):
    assert FAST is not None, 'TE_FASTWORK required (NVMe)'
    th = [threading.Thread(target=worker, args=(list(jobs),)) for _ in range(int(workers))]
    for t in th: t.start(); time.sleep(5)
    for t in th: t.join()
    note(step='a4_mesh_done', jobs=list(jobs))
if __name__ == '__main__': main(*sys.argv[1:])
