"""Second mesh worker beside a running g_mesh.py whose other worker thread died (2026-11-20 00:07, log-name FileExistsError). Same job() as g_mesh.py.
Order: the main process walks the job list forward; this helper walks it backward. Job k is taken only if it has no score and
 (a) the main process has passed it without starting it (k < j, no render folder: the dead thread's job), or (b) k >= j+3, j = the main process's
 furthest started job (render folder exists), so the two never run one job at once. usage: GT_FASTWORK=<dir> python3 g3_mesh_helper.py <job> ... (the main job list)"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import g_mesh as G
def key(s): q = s.split(':'); return f'{q[0]}__{q[1]}'
def done(s): return (G.A.O/'meshes'/key(s)/'score.json').exists()
def started(s): return (G.SH/'renders'/key(s)).exists()
def main(jobs):
    mine = set()
    while True:
        j = max([i for i, s in enumerate(jobs) if started(s) and s not in mine], default=-1)
        cand = [k for k in range(len(jobs)-1, -1, -1) if not done(jobs[k]) and jobs[k] not in mine and ((k < j and not started(jobs[k])) or k >= j+3)]
        if not cand:
            if all(done(s) for s in jobs) or not any(k >= j+3 or (k < j and not started(jobs[k])) for k in range(len(jobs)) if not done(jobs[k]) and jobs[k] not in mine): break
            time.sleep(60); continue
        s = jobs[cand[0]]; mine.add(s); G.note(step='helper_take', job=s, main_index=j, index=cand[0])
        for attempt in [1, 2]:
            try: G.job(s); break
            except RuntimeError as e: G.note(step='mesh_error', job=s, attempt=attempt, error=str(e), helper=True)
    G.note(step='helper_done', jobs=sorted(mine))
if __name__ == '__main__':
    assert G.FAST is not None; main(sys.argv[1:])
