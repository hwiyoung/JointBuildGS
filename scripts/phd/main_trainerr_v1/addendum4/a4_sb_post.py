"""Host driver after each follow-up record run (addendum4_c.json): waits for its receipt, then the analysis that run fills.
  sb1 / sb2 (B0, 6,000, signed)  : work na occlusion at 3000_pre_reset and 3500 (GPU) + summarize (groups, signed opacity gradients)
  sb5 (R1 x ALS, 30,000, signed) : work ga 2.3 position gradients by loss over all windows (CPU)
  sb3 / sb4 (LoD2, 30,000 scene) : plies + meshes at the work-ba stages (one mesh worker per driver: two drivers = at most two tiles, issues.md),
                                   work ra draw (GPU) + tables, work ba figures of the work-ma clusters 1-3
usage: TE_FASTWORK=<dir> python3 a4_sb_post.py <run> <gpu>"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import a4_launch as A, a4_mesh as M
SITE = {'sb1_B0_LoD2_record6000': 'B0_b10', 'sb2_B0_ALS_record6000': 'B0_b10', 'sb3_R1_LoD2_record': 'R1rep_b10', 'sb4_B173_LoD2_record': 'B173nb_b10', 'sb5_R1_ALS_record_signed': 'R1rep_b10'}
def gpu_idle(gpu):
    """wait until no addendum-4 training is running on this GPU (launch.json without receipt) and >= 14 GiB is free, so a follow-up GPU step never shares a GPU with a training"""
    import subprocess
    while True:
        busy = any(json.loads(l.read_text()).get('gpu') == gpu and not (l.parent/'receipt.json').exists() for l in (A.A4O/'runs').glob('*/*/attempt1/launch.json'))
        q = subprocess.run(['nvidia-smi', '-i', str(gpu), '--query-gpu=memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.strip()
        if not busy and q and int(q) >= 14*1024: return
        time.sleep(60)
STAGES = ['1000', '3000_pre_reset', '5000', '7000', '15000', '30000']
def post(run, gpu):
    site = SITE[run]; root = A.A4O/'runs'/site/run/'attempt1'
    while not (root/'receipt.json').exists(): time.sleep(60)
    rec = json.loads((root/'receipt.json').read_text()); M.note(step='sb_receipt', run=run, status=rec['status'], seconds=rec.get('seconds'))
    if rec['status'] != 'COMPLETED': return
    t0 = time.monotonic()
    def gjob(*a, **k): gpu_idle(gpu); return A.job(*a, gpu=gpu, **k)   # every GPU step waits for an idle GPU
    if run in ('sb1_B0_LoD2_record6000', 'sb2_B0_ALS_record6000'):
        for st in ['3000_pre_reset', '3500']: M.must(gjob('addendum4/a4_na.py', 'occl', run, st), f'na occl {run} {st}')
        M.must(A.job('addendum4/a4_na.py', 'summarize', run, cpus=16, memory='60g'), f'na summarize {run}')
    elif run == 'sb5_R1_ALS_record_signed':
        M.must(A.job('addendum4/a4_ga.py', 'grads', run, cpus=16, memory='60g'), 'ga grads sb5')
    else:
        short = run[:3]; stem = {'sb3': 'R1rep_b10__LoD2', 'sb4': 'B173nb_b10__LoD2'}[short]; rk = {'sb3': 'R1', 'sb4': 'B173'}[short]
        M.must(gjob('addendum4/a4_keyply.py', f'/te/addendum4/runs/{site}/{run}/attempt1/model', run, *STAGES), f'plies {run}')
        gpu_idle(gpu); M.main(1, *[f'{stem}:{short}_{st}:/te/ply/{run}/{st}.ply:{gpu}' for st in STAGES])   # /te = addendum4 payload in the gtj container
        M.must(gjob('addendum4/a4_ra.py', 'draw', stem), f'ra draw {stem}')
        cases = [f'ma_{rk}_{k}' for k in [1, 2, 3]]
        M.must(A.job('addendum4/a4_ba.py', 'case', *cases, cpus=16, memory='60g'), f'ba {rk}')   # CPU image (open3d)
        M.must(A.job('addendum4/a4_ba.py', 'summary', *cases, cpus=8, memory='20g'), f'ba summary {rk}')
    M.note(step='sb_post_done', run=run, seconds=time.monotonic()-t0)
if __name__ == '__main__': post(sys.argv[1], int(sys.argv[2]))
