"""Host driver for work ra (order 6.1): per job the a6_ra_render.py render (gtj container, GPU) then the unchanged addendum3 mesh + score pipeline
(a3_mesh.job), redirected to the addendum6 payload (shadow addendum6/gtj, /te = addendum6, logs addendum6/logs, /source = r31).
usage: TE_FASTWORK=<dir> python3 a6_ra.py <workers> <stem>:<family>:<ply container path>:<variant> [...]"""
import sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addendum3'))
import a3_launch as A
A.A3O = A.O/'addendum6'; A.LOGS = A.A3O/'logs'; A.FORK = 'GeoGS-conf-guided-v1-r31'; A.LOGS.mkdir(parents=True, exist_ok=True)
import a3_mesh as M
M.SH = A.A3O/'gtj'
LOCK = threading.Lock(); TAKEN = set(); GPUS = [1, 0]

def one(job, gpu):
    stem, fam, ply, variant = job.split(':'); key = f'{stem}__{fam}'
    if (A.A3O/'meshes'/key/'score.json').exists(): return
    if not (M.SH/'scenes'/stem/'rows.npz').exists(): M.must(A.gtj('shadow', stem, '-'), 'shadow')
    M.views(stem.split('__')[0])
    if not (M.SH/'renders'/key/'receipt.json').exists(): M.must(A.gtjscript('addendum6/a6_ra_render.py', [stem, fam, ply, variant], gpu), f'ra6 render {key}')
    M.job(stem, fam, 'unused', gpu)

def worker(i, jobs):
    while True:
        with LOCK:
            nxt = next((j for j in jobs if j not in TAKEN), None)
            if nxt is None: return
            TAKEN.add(nxt)
        for attempt in [1, 2]:
            try: one(nxt, GPUS[i % len(GPUS)]); break
            except RuntimeError as e: M.note(step='ra6_error', job=nxt, attempt=attempt, error=str(e))

def main(workers, *jobs):
    assert A.FAST is not None
    th = [threading.Thread(target=worker, args=(i, list(jobs))) for i in range(int(workers))]
    for t in th: t.start(); time.sleep(5)
    for t in th: t.join()
    M.note(step='a6_ra_done', jobs=list(jobs))

if __name__ == '__main__': main(*sys.argv[1:])
