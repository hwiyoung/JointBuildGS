"""Stage 3 (order 9) site figures: TRAINERR addendum 6 correction-1 figure code (a6_case.draw, unchanged, imported read only from /repo with its payload at /te)
with the meshes of each figure replaced by three rows (order 9): the method run (FINALTRAIN 30,000), the GT target run base extraction, the GT target run occl extraction.
Section panel: the blue target discs of the method row are the method targets (as in addendum 6); in the two GT target rows they are this run's GT patches
(O/targets/<stem>.npz: anchor = target, normal, radius = sqrt(area / pi), the target_discs.cpp rule).
usage (launch.py cpute): g3_case.py <name> [...]   names: visible_wall south_wall r1_wall1 floor_band annex_under floater
writes /docs/figures/case_<name>.png + .json and /gt/case/case_<name>.npz (plotted points and masks)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
import numpy as np
from pathlib import Path
import a6_case as K
TITLE = '참값 목표 판(진단용)'
GTO = Path('/gt'); RS = Path('/art/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1')
NAMES = {'visible_wall': ('visible_wall', 'B0 × LoD2 잘 보이는 벽 0–10 m', True, 0., False), 'south_wall': ('south_wall', 'B0 × LoD2 남쪽 끝 벽', False, 4., True),
         'r1_wall1': ('ma_R1_1', 'R1 × LoD2 1번 벽', True, 0., False), 'floor_band': ('floor_band', 'R1 × 항공 LiDAR 바닥 띠', True, 3., False),
         'annex_under': ('annex_under', 'B0 × 항공 LiDAR 별채', False, 1.5, True), 'edge_annex': ('edge_annex', 'B0 × LoD2 별채 평지붕 가장자리', True, 0., False), 'floater': ('floater', 'B173 × 항공 LiDAR 가장자리 뜬 면', False, 1., False)}
STEM = {'visible_wall': 'B0_b10__LoD2', 'south_wall': 'B0_b10__LoD2', 'r1_wall1': 'R1rep_b10__LoD2', 'floor_band': 'R1rep_b10__ALS', 'annex_under': 'B0_b10__ALS', 'edge_annex': 'B0_b10__LoD2', 'floater': 'B173nb_b10__ALS'}
ARROW = {'visible_wall': '벽', 'south_wall': '벽 뒤', 'r1_wall1': '벽', 'floor_band': '바닥 자리', 'annex_under': '별채 지붕 아래', 'edge_annex': '지붕 가장자리', 'floater': '뜬 면 자리'}
def ft_mesh(stem): return RS/('addendum3_stage1' if stem.startswith('B173') else 'addendum3_stage2')/'meshes'/f'{stem}__FINALTRAIN_30000/primary.ply'
def gtt_mesh(stem, v): return GTO/'gtj/meshes'/f'{stem}__gtt_s0_{v}/final.ply'

class GTTargets:
    def __init__(self, stem):
        with np.load(GTO/'targets'/f'{stem}.npz') as z: self.anchor = z['target'].astype('f8'); self.normal = z['normal'].astype('f8'); self.radius = np.sqrt(z['area'].astype('f8')/np.pi)

ORIG_T = K.Targets; ROW = {'i': 0}
_section = K.section
def section(ax, stem, *a, **k):
    K.Targets = ORIG_T if ROW['i'] == 0 else GTTargets; ROW['i'] += 1
    try: return _section(ax, stem, *a, **k)
    finally: K.Targets = ORIG_T
K.section = section
_ab = K.ab
def ab(ax, ua, va, crop):   # A / B labels clipped to the panel (the section line can leave the photo crop; addendum 6 drew the circles outside the panel)
    n0 = len(ax.texts); _ab(ax, ua, va, crop)
    for t in ax.texts[n0:]: t.set_clip_on(True)
K.ab = ab
K.FIG = Path('/docs/figures'); K.CS6 = GTO/'case'

def run(name):
    cd, place, missing, extra, xray = NAMES[name]; stem = STEM[name]
    meshes = [('본 방법 판', ft_mesh(stem)), ('참값 목표 판 기준 추출', gtt_mesh(stem, 'base')), ('참값 목표 판 가림 제외 추출', gtt_mesh(stem, 'occl'))]
    for lab, p in meshes: assert p.exists(), p
    K.CASES[name] = dict(cd=cd, title=f'{TITLE} — {place}: 본 방법 판 / 참값 목표 판 기준 추출 / 가림 제외 추출', meshes=meshes, missing=missing, extra=extra, xray=xray, arrow=ARROW[name])
    ROW['i'] = 0; K.draw(name)

if __name__ == '__main__':
    for nm in sys.argv[1:]: run(nm)
