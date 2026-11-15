"""Host driver after each follow-up record run (addendum4_c.json): waits for its receipt, then the analysis that run fills.
  sb1 / sb2 (B0, 6,000, signed)  : work na occlusion at 3000_pre_reset and 3500 (GPU) + summarize (groups, signed opacity gradients)
  sb5 (R1 x ALS, 30,000, signed) : work ga 2.3 position gradients by loss over all windows (CPU)
  sb3 / sb4 (LoD2, 30,000 scene) : plies + meshes at the work-ba stages (one mesh worker per driver: two drivers = at most two tiles, issues.md),
                                   work ra draw (GPU) + tables, work ba figures of the work-ma clusters 1-3
usage: TE_FASTWORK=<dir> python3 a4_sb_post.py <run> [<gpu, unused: GPU steps take an idle GPU>]"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import a4_launch as A, a4_mesh as M
SITE = {'sb1_B0_LoD2_record6000': 'B0_b10', 'sb2_B0_ALS_record6000': 'B0_b10', 'sb3_R1_LoD2_record': 'R1rep_b10', 'sb4_B173_LoD2_record': 'B173nb_b10', 'sb5_R1_ALS_record_signed': 'R1rep_b10', 'sb4b_B173_LoD2_record_nocheck': 'B173nb_b10'}
def idle_gpu():
    """first GPU with no addendum-4 training running on it (launch.json without TRAINING_COMPLETE / receipt) and >= 14 GiB free; waits until one exists,
    so a follow-up GPU step never shares a GPU with a training"""
    import subprocess
    while True:
        busy = {json.loads(l.read_text()).get('gpu') for l in (A.A4O/'runs').glob('*/*/attempt1/launch.json')
                if not ((l.parent/'receipt.json').exists() or (l.parent/'TRAINING_COMPLETE.json').exists())}
        q = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.split('\n')
        free = [int(i) for i, f in (x.split(', ') for x in q if x.strip()) if int(f) >= 14*1024 and int(i) not in busy]
        if free: return free[0]
        time.sleep(60)
def finished(root, run):
    """the queue writes receipt.json only after it has started every run; a run is finished when TRAINING_COMPLETE.json exists and its container has exited"""
    import subprocess
    if (root/'receipt.json').exists(): return json.loads((root/'receipt.json').read_text())['status']
    up = subprocess.run(['docker', 'ps', '-q', '-f', f'name=^jbgs-te-a4-{run}$'], capture_output=True, text=True).stdout.strip()
    if up: return None
    if (root/'TRAINING_COMPLETE.json').exists(): return 'COMPLETED'
    lg = root/'train.log'   # not started yet, or just starting (container not listed yet): wait; exited without completion for 5 min: error
    return 'ERROR' if lg.exists() and time.time()-lg.stat().st_mtime > 300 else None
STAGES = ['1000', '3000_pre_reset', '5000', '7000', '15000', '30000']
def post(run, gpu):
    site = SITE[run]; root = A.A4O/'runs'/site/run/'attempt1'
    while (st := finished(root, run)) is None: time.sleep(60)
    M.note(step='sb_receipt', run=run, status=st)
    if st != 'COMPLETED': return
    t0 = time.monotonic()
    def gjob(*a, **k): return A.job(*a, gpu=idle_gpu(), **k)   # every GPU step takes an idle GPU
    if run in ('sb1_B0_LoD2_record6000', 'sb2_B0_ALS_record6000'):
        for st in ['3000_pre_reset', '3500']: M.must(gjob('addendum4/a4_na.py', 'occl', run, st), f'na occl {run} {st}')
        M.must(A.job('addendum4/a4_na.py', 'summarize', run, cpus=16, memory='60g'), f'na summarize {run}')
    elif run == 'sb5_R1_ALS_record_signed':
        M.must(A.job('addendum4/a4_ga.py', 'grads', run, cpus=16, memory='60g'), 'ga grads sb5')
    else:
        short = run[:3]; stem = {'sb3': 'R1rep_b10__LoD2', 'sb4': 'B173nb_b10__LoD2'}[short]; rk = {'sb3': 'R1', 'sb4': 'B173'}[short]
        M.must(gjob('addendum4/a4_keyply.py', f'/te/addendum4/runs/{site}/{run}/attempt1/model', run, *STAGES), f'plies {run}')
        g = idle_gpu(); M.main(1, *[f'{stem}:{short}_{st}:/te/ply/{run}/{st}.ply:{g}' for st in STAGES])   # /te = addendum4 payload in the gtj container
        M.must(gjob('addendum4/a4_ra.py', 'draw', stem), f'ra draw {stem}')
        cases = [f'ma_{rk}_{k}' for k in [1, 2, 3]]
        M.must(A.job('addendum4/a4_ba.py', 'case', *cases, cpus=16, memory='60g'), f'ba {rk}')   # CPU image (open3d)
        M.must(A.job('addendum4/a4_ba.py', 'summary', *cases, cpus=8, memory='20g'), f'ba summary {rk}')
    M.note(step='sb_post_done', run=run, seconds=time.monotonic()-t0)
if __name__ == '__main__': post(sys.argv[1], None)
