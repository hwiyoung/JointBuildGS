"""Host driver for work ra: per (stem, variant) the ra render (gtj container, GPU) then the unchanged mesh + score pipeline (a3_mesh.job, NVMe work folder).
usage: TE_FASTWORK=<dir> python3 a3_ra.py <workers> <stem>:<variant> [...]"""
import sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import a3_launch as A, a3_mesh as M
LOCK = threading.Lock(); TAKEN = set()
def one(job, gpu):
    stem, variant = job.split(':'); fam = f'ra_{variant}'; key = f'{stem}__{fam}'
    if (A.A3O/'meshes'/key/'score.json').exists(): return
    if not (M.SH/'scenes'/stem/'rows.npz').exists(): M.must(A.gtj('shadow', stem, '-'), 'shadow')
    M.views(stem.split('__')[0])
    if not (M.SH/'renders'/key/'receipt.json').exists(): M.must(A.gtjscript('addendum3/a3_ra_render.py', [stem, variant], gpu), f'ra render {key}')
    M.job(stem, fam, 'unused', gpu)
def worker(i, jobs):
    while True:
        with LOCK:
            nxt = next((j for j in jobs if j not in TAKEN), None)
            if nxt is None: return
            TAKEN.add(nxt)
        for attempt in [1, 2]:
            try: one(nxt, i % 2); break
            except RuntimeError as e: M.note(step='ra_error', job=nxt, attempt=attempt, error=str(e))
def main(workers, *jobs):
    assert A.FAST is not None
    th = [threading.Thread(target=worker, args=(i, list(jobs))) for i in range(int(workers))]
    for t in th: t.start(); time.sleep(5)
    for t in th: t.join()
    M.note(step='a3_ra_done', jobs=list(jobs))
if __name__ == '__main__': main(*sys.argv[1:])
