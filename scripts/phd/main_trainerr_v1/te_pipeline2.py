"""Host driver v2 for the record-run key meshes (replaces te_pipeline mesh threads; trainings are done): N workers, mesh work folders on NVMe
(TE_FASTWORK, symlinked final_work; final.ply, scores and receipts stay in the payload), a family running in another container is never started twice.
usage: TE_FASTWORK=<dir> python3 te_pipeline2.py <workers> <run> [<run> ...]"""
import json, os, shutil, subprocess, sys, threading, time
from pathlib import Path
import launch as Lc
from te_pipeline import KEYS, note, model_dir, cont, must
FAST = Lc.FAST; LOCK = threading.Lock(); TAKEN = set()
def running(stem, fam):
    out = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True).stdout.split()
    return [n for n in out if n.endswith(f'-{stem}-{fam}') and n.startswith('jbgs-trainerr-gtj-')]
def done(run, name):
    site, prior, arm = Lc.RUNS[run]; stem = f'{site}__{prior}'; fam = f'tl_{arm}_{name}'
    return (Lc.O/'meshes'/f'{stem}__{fam}'/'score.json').exists() if name == '30000' else (Lc.O/'curves'/f'{run}__{name}.json').exists()
def key_job(run, name, gpu):
    site, prior, arm = Lc.RUNS[run]; stem = f'{site}__{prior}'; fam = f'tl_{arm}_{name}'; m = model_dir(run); t0 = time.monotonic()
    root = Lc.O/'gtj/meshes'/f'{stem}__{fam}'; wd = root/'final_work'; final = root/'final.ply'
    while running(stem, fam): time.sleep(60)
    if done(run, name): return
    if not final.exists():
        ply = m/'point_cloud/iteration_30000/point_cloud.ply' if name == '30000' else m.parent/'ply'/f'{name}.ply'
        if not ply.exists(): must(Lc.job('te_keyply.py', cont(m), name, gpu=gpu), f'ply {run} {name}')
        if not (Lc.O/'gtj/renders'/f'{stem}__{fam}'/'receipt.json').exists(): must(Lc.gtj('render', stem, fam, cont(ply), gpu), f'render {fam}')
        if not (wd/'binding.json').exists():
            fw = FAST/f'{stem}__{fam}'/'final_work'
            if wd.is_symlink() or wd.exists():
                if wd.is_symlink(): wd.unlink()
                else: shutil.move(str(wd), str(root/f'final_work_hdd_superseded_{int(time.time())}'))
            if fw.exists(): shutil.rmtree(fw)
            fw.mkdir(parents=True); root.mkdir(parents=True, exist_ok=True); os.symlink(fw, wd)
            must(Lc.gtj('prepare', stem, fam), 'prepare')
        if not (wd/'plan/plan.json').exists(): must(Lc.gtj('plan', stem, fam), 'plan')
        n = len(json.loads((wd/'plan/plan.json').read_text())['tiles'])
        for k in range(n):
            if not ((wd/'tiles'/f'tile{k}.npz').exists() and (wd/'tiles'/f'tile{k}.json').exists()): must(Lc.gtj(f'tile:{k}', stem, fam), f'tile {k}')
        if not (wd/'merged.json').exists():
            if Lc.gtj('merge', stem, fam): must(Lc.gtj('recover', stem, fam), f'merge+recover {fam}'); note(step='recovered', run=run, name=name)
        if not final.exists(): must(Lc.gtj('finish', stem, fam), 'finish')
    if name == '30000':
        must(Lc.gtj('score', stem, fam), 'score'); must(Lc.job('te_sets_tl.py', run), 'sets_tl'); must(Lc.job('te_compare.py', run), 'compare')
    else: must(Lc.job('te_measure.py', run, name), 'measure')
    Lc.gtj('clean', stem, fam)
    if wd.is_symlink():  # keep the small receipts in the payload, drop the NVMe work folder
        fw = Path(os.readlink(wd)); keep = root/'final_work_receipts'; keep.mkdir(exist_ok=True)
        for f in list(fw.glob('*.json'))+list((fw/'plan').glob('*.json')): shutil.copy2(f, keep/f.name)
        wd.unlink(); shutil.rmtree(fw.parent, ignore_errors=True)
    note(step='key_done', run=run, name=name, seconds=time.monotonic()-t0, driver='v2')
def worker(i, queue, gpu):
    while True:
        with LOCK:
            nxt = next(((r, n) for r, n in queue if (r, n) not in TAKEN and not done(r, n)), None)
            if nxt is None: return
            TAKEN.add(nxt)
        for attempt in [1, 2]:
            try: key_job(*nxt, gpu); break
            except RuntimeError as e: note(step='key_error', run=nxt[0], name=nxt[1], attempt=attempt, error=str(e), driver='v2')
def main(workers, *runs):
    queue = [(r, n) for r in runs for n in KEYS]; th = [threading.Thread(target=worker, args=(i, queue, i % 2)) for i in range(int(workers))]
    for t in th: t.start(); time.sleep(5)
    for t in th: t.join()
    note(step='pipeline2_done', runs=list(runs))
if __name__ == '__main__': main(*sys.argv[1:])
