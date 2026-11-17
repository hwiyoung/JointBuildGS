"""PHD-MAIN-JUDGEABL-v1 공통. 학습 없음, 새 광도 점수 없음, CPU만. scientific_verdict: null.
JUDGECHECK-v2(JC)·JUDGEPROBE-v1(JP)·JUDGEAPPLY-v1(JA)의 저장된 값만 읽는다. JC 판정 함수(jc2_judge)와 JP 공통 함수를 옮겨 쓴다."""
import importlib.util, json, sys
from pathlib import Path
import numpy as np
_spec = importlib.util.spec_from_file_location('jpcommon', '/repo/scripts/phd/main_judgeprobe_v1/common.py')
JPC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(JPC)
J = JPC.J
from_jp = ['now', 'sha', 'jsafe', 'dump', 'loadz', 'savez', 'wq', 'plane_distance', 'Timer', 'REGIONS', 'CASE', 'MATCH', 'PLACE', 'JUD']
for _k in from_jp: globals()[_k] = getattr(JPC, _k)
C, D, O, R = Path('/cfg'), Path('/docs'), Path('/out'), Path('/repo')
PH = Path('/art/phase-payloads/phd')
JC = PH/'main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2'
JP = PH/'main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1'
JA = PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
SITES = ['B0_b10', 'B173nb_b10', 'R1rep_b10']
CASES = [0, 1, 2, 4]
SEED_T = 20261112
def cfg():
    lock = json.loads((C/'judgeabl_v1.lock.json').read_text()); assert sha(C/'judgeabl_v1.json') == lock['config_sha256'], 'config changed after lock'
    return json.loads((C/'judgeabl_v1.json').read_text())
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def nmad_w(x, w):
    m = wq(x, w, .5); return m, 1.4826*wq(np.abs(x - m), w, .5)
