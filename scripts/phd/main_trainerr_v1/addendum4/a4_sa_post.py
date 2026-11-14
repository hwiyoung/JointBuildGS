"""Host driver after each work-sa training (order 8): waits for its receipt, plies (a4_keyply, GPU), meshes + scores (a4_mesh, NVMe), then a4_sa_values.
usage: TE_FASTWORK=<dir> python3 a4_sa_post.py <run> [<run> ...]"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import a4_launch as A, a4_mesh as M
SHORT = {'sa2_B0_LoD2_occlmask': ('sa2', 'B0_b10', 'B0_b10__LoD2'), 'sa3_B173_ALS_nojudge': ('sa3', 'B173nb_b10', 'B173nb_b10__ALS')}
ITS = ['7000', '10000', '15000', '30000']
def post(run, gpu):
    short, site, stem = SHORT[run]; root = A.A4O/'runs'/site/run/'attempt1'
    while not (root/'receipt.json').exists(): time.sleep(60)
    rec = json.loads((root/'receipt.json').read_text()); M.note(step='sa_receipt', run=run, status=rec['status'])
    if rec['status'] != 'COMPLETED': return
    M.must(A.job('addendum4/a4_keyply.py', f'/te/addendum4/runs/{site}/{run}/attempt1/model', run, *ITS, gpu=gpu), f'plies {run}')
    M.main(2, *[f'{stem}:{short}_{it}:/te/ply/{run}/{it}.ply:{gpu}' for it in ITS])
    A.job('addendum4/a4_sa_values.py', short, cpus=16, memory='60g'); M.note(step='sa_post_done', run=run)
if __name__ == '__main__': post(sys.argv[1], int(sys.argv[2]))
