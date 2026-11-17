"""PHD-MAIN-TRAINERR-v1 addendum 6 helpers (addendum6.json, locked). Inherits addendum 5 (a5_common -> a4 -> a3 -> a2 -> a1 -> common)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
A6O = O/'addendum6'; A6D = D/'addendum6'
GROUP_KO = {0: '지킨 점', 1: '잃은 점', 2: '고친 점', 3: '목표도 결과도 틀린 점'}
SCENES6 = ['B0_b10__ALS', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B173nb_b10__LoD2', 'R1rep_b10__ALS', 'R1rep_b10__LoD2']

def cfg6():
    p = R/'configs/phd/main_trainerr_v1/addendum6.json'; assert sha(p) == json.loads(p.with_name('addendum6.lock.json').read_text())['config_sha256'], 'addendum6 config changed after lock'
    return json.loads(p.read_text())
def table6(name, rows): return table(name, rows, folder=A6D/'tables')
def progress6(s):
    with (A6D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def issue6(s):
    with (A6D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
