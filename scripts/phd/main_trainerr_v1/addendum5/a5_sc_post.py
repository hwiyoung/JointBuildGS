"""Host driver after each addendum-5 record run (addendum5_b.json): waits for its receipt, then the counts of works ga / na / da for its place.
usage: TE_FASTWORK=<dir> python3 a5_sc_post.py <run>"""
import json, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; A5 = Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainerr_v1/PHD-MAIN-TRAINERR-v1/addendum5')
SITE = {'sc1_B173_ALS_signed': 'B173nb_b10', 'sc2_R1_LoD2_signed': 'R1rep_b10', 'sc3_B0_ALS_signed': 'B0_b10', 'sc4_B0_LoD2_signed': 'B0_b10'}
PLACE = {'sc1_B173_ALS_signed': ('floater', 'x'), 'sc2_R1_LoD2_signed': ('r1_lod2_wall1', 'r1_lod2_wall_control'), 'sc3_B0_ALS_signed': ('annex_under', 'x'), 'sc4_B0_LoD2_signed': ('south_wall_behind', 'x')}
PIX = {'sc3_B0_ALS_signed': 'annex', 'sc4_B0_LoD2_signed': 'south'}
def sh(*a): print('RUN', a, flush=True); return subprocess.run(['python3', str(HERE/'a5_launch.py'), *a]).returncode
def gpu_free():
    q = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.split('\n')
    f = sorted(((int(m), int(i)) for i, m in (x.split(', ') for x in q if x.strip())), reverse=True); return str(f[0][1])
def main(run):
    root = A5/'runs'/SITE[run]/run/'attempt1'
    while not (root/'receipt.json').exists(): time.sleep(60)
    st = json.loads((root/'receipt.json').read_text())['status']; print('RECEIPT', run, st, flush=True)
    if st != 'COMPLETED': return
    pl, ct = PLACE[run]
    if run in PIX:
        for s in ['0', '1000', '3000_pre_reset', '5000', '7000', '10000', '15000', '30000']: sh('gpu', gpu_free(), 'addendum5/a5_pix.py', 'group', run, PIX[run], s)
    if run == 'sc4_B0_LoD2_signed':
        subprocess.run(['python3', str(HERE/'a5_mesh.py'), f'B0_b10__LoD2:sc4_30000:/te/runs/B0_b10/{run}/attempt1/model/point_cloud/iteration_30000/point_cloud.ply:{gpu_free()}'])
    if run == 'sc2_R1_LoD2_signed': sh('cpu', 'addendum5/a5_ga.py', 'coverage', run, pl, ct)
    for w in ['flows', 'resets']: sh('cpu', 'addendum5/a5_ga.py', w, run, pl, ct)
    sh('cpu', 'addendum5/a5_ga.py', 'seeds', run, pl, ct, '30000')
    sh('cpu', 'addendum5/a5_da.py', 'grads', run, pl, ct)
    for s in ['3000_pre_reset', '30000']:
        if sh('gpu', gpu_free(), 'addendum5/a5_na.py', 'pixels', run, s, pl, ct) == 0: sh('cpu', 'addendum5/a5_na.py', 'tables', run, s)
    print('SC_POST_DONE', run, flush=True)
if __name__ == '__main__': main(sys.argv[1])
