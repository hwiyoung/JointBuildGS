"""Host driver after each work-ba training (order 7): waits for its receipt, then plies (a3_keyply, GPU), meshes + scores (a3_mesh, NVMe),
work-ga tracking of ba1/ba2 (a3_ga run), ba3 annex tracking; finally a3_ba tables and figures.
usage: TE_FASTWORK=<dir> python3 a3_ba_post.py <run> [<run> ...]"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import a3_launch as A, a3_mesh as M
SHORT = {'ba1_B0_LoD2_nonormal': ('ba1', 'B0_b10__LoD2', ['7000', '10000', '15000', '30000']), 'ba2_B0_LoD2_noreset': ('ba2', 'B0_b10__LoD2', ['7000', '10000', '15000', '30000']),
         'ba3_B0_ALS_record': ('ba3', 'B0_b10__ALS', ['30000'])}
def post(run):
    short, stem, its = SHORT[run]; root = A.A3O/'runs/B0_b10'/run/'attempt1'
    while not (root/'receipt.json').exists(): time.sleep(60)
    rec = json.loads((root/'receipt.json').read_text()); M.note(step='ba_receipt', run=run, status=rec['status'])
    if rec['status'] != 'COMPLETED_30000': return
    model = f'/te/addendum3/runs/B0_b10/{run}/attempt1/model'
    if short == 'ba3': plies = {'30000': f'/te/runs/B0_b10/{run}/attempt1/model/point_cloud/iteration_30000/point_cloud.ply'}   # gtj container: /te = addendum3
    else:
        M.must(A.job('addendum3/a3_keyply.py', model, run, *its, gpu=0), f'plies {run}'); plies = {it: f'/te/ply/{run}/{it}.ply' for it in its}
    jobs = [f'{stem}:{short}_{it}:{p}:{i % 2}' for i, (it, p) in enumerate(plies.items())]
    M.main(2, *jobs)
    if short == 'ba3': A.job('addendum3/a3_ba.py', 'annex')
    else: A.job('addendum3/a3_ga.py', 'run', run, cpus=16, memory='60g')
    A.job('addendum3/a3_ba.py', 'tables'); A.job('addendum3/a3_ba.py', 'figures'); M.note(step='ba_post_done', run=run)
if __name__ == '__main__':
    for r in sys.argv[1:]: post(r)
