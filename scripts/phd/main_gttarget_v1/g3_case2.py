"""Stage 3 (order 9, 7.3 table da, 8.4) added after the completeness check of 2026-11-20 (launch.py cpute):
  cells       : three-panel site figures (a6_case.draw through g3_case.py) for TRAINERR cells 1-3 and the unexplained points
  annex       : table da value for the B0 x airborne LiDAR annex (addendum 4 annex box ANNEX, the place of case_annex_under): mesh vertices in the box and those farther
                than 1 m from every GT dense point (the annex_under case rule), per arm -> table da_annex
Places of the new figures (each a fixed rule, computed here, plotted points stored in /gt/case/case_<name>.npz):
  cell1 : B0 x LoD2 case 2 (image depth error) GT rows within 4 m (xy) of the case-2 row with the most rows lost in any of the three arms within 2 m
  cell2 : R1 x airborne LiDAR case 2, the same rule
  cell3 : B0 x LoD2 case 4 (image depth missing) GT rows within 4 m (xy) of the case-4 row with the most GTT-base result points outside tau within 2 m (accuracy cell: red = surface
          farther than 0.5 m from GT within 1.5 m of the place)
  unexpl: the scene with the most unexplained lost points (order 8.4); unexplained points within 10 m (xy) of the one with the most unexplained neighbours within 2 m;
          the place = eligible GT rows within 0.5 m of those points (the points alone were too few for the view choice: fewer than 20 inside any view)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
import g3_case as GC
import numpy as np, json
from pathlib import Path
from scipy.spatial import cKDTree
K = GC.K; b = K.b; TITLE = GC.TITLE; GTJ = Path('/art/phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'); GTO = GC.GTO
TE_CELLS = json.loads(Path('/repo/configs/phd/main_trainerr_v1/trainerr_v1.json').read_text())['cells']

SC_KO = {'R1rep_b10__LoD2': 'R1 × LoD2', 'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B0_b10__LoD2': 'B0 × LoD2', 'B0_b10__ALS': 'B0 × 항공 LiDAR', 'B173nb_b10__ALS': 'B173 × 항공 LiDAR', 'B173nb_b10__LoD2': 'B173 × LoD2'}
def densest(X, m, r=2.):
    P = X[m]; c = np.array([len(q) for q in cKDTree(P).query_ball_point(P, r)]); return P[int(np.argmax(c))]
def a11(stem): return np.load(GTJ/'addendum11/final_data'/f'{stem}.npz')
def place(name):
    if name in ('cell1', 'cell2', 'cell3'):
        cs = TE_CELLS[name.replace('cell', 'c')]; stem = f"{cs['site']}__{cs['prior']}"; A = a11(stem); B = np.load(GTJ/'addendum12/distance_A1'/f'{stem}.npz'); X = A['reference__xyz'].astype('f8')
        m = (A['reference__case_id'] == cs['case_id']) & A['reference__eligible'].astype(bool)
        tg = np.load(GTO/'meshes'/f'{stem}__gtt_target/points.npz')['reference__within_tau1'].astype(bool); bs = np.load(GTO/'meshes'/f'{stem}__gtt_s0_base/points.npz')
        if cs['metric'] == 'completeness':
            lost = ((A['reference__judgment_mesh__within_tau1'] & ~A['reference__FINALTRAIN_30000__within_tau1']) | (A['reference__gt_judgment_mesh__within_tau1'] & ~B['reference__A1__within_tau1'])
                    | (tg & ~bs['reference__within_tau1'].astype(bool))).astype(bool)
            c = densest(X, m & lost)
        else:
            e = bs['result__eligible_new'].astype(bool) & (bs['result__case_id'] == cs['case_id']) & ~bs['result__within_tau1'].astype(bool); c = densest(bs['result__xyz'].astype('f8'), e)
        sel = m & (np.linalg.norm(X[:, :2]-c[:2], axis=1) <= 4.)
        return stem, X[sel], A['reference__normal'][sel].astype('f8'), A['reference__point_id'][sel], cs
    ss = ['R1rep_b10__ALS', 'R1rep_b10__LoD2', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B0_b10__ALS']; Z = {s: np.load(GTO/'ca'/f'causes_{s}_gtt_s0.npz') for s in ss}
    stem = max(ss, key=lambda s: int((Z[s]['unexplained'] & (Z[s]['group'] == 1)).sum())); z = Z[stem]; u = z['unexplained'] & (z['group'] == 1); X = z['xyz'].astype('f8')
    c = densest(X, u); U = X[u & (np.linalg.norm(X[:, :2]-c[:2], axis=1) <= 10.)]; A = a11(stem); G = A['reference__xyz'].astype('f8'); el = A['reference__eligible'].astype(bool)
    d, _ = cKDTree(U).query(G, distance_upper_bound=.5); sel = el & np.isfinite(d)   # too few unexplained points for a view: the place = eligible GT rows within 0.5 m of them
    return stem, G[sel], A['reference__normal'][sel].astype('f8'), A['reference__point_id'][sel], None

def cells():
    orig_case_def = b.case_def
    for name in (sys.argv[2:] or ['cell1', 'cell2', 'cell3', 'unexpl']):
        stem, X, N, pid, cs = place(name); wall = bool(np.mean(np.abs(N[:, 2]) < .5) >= .5)
        lab = (f"칸 {name[-1]} · {SC_KO[stem]} {cs['case_name']} {'완전성' if cs['metric'] == 'completeness' else '정확성'}" if cs else f"설명되지 않는 잃은 점 · {SC_KO[stem]}")
        cd = dict(stem=stem, title=lab, X=X, N=N, wall=wall, vplace=np.zeros(0, 'i8'), run='-', photo2=False, place_label='이 자리(참값 점)')
        b.case_def = lambda nm, cd=cd: cd
        acc = cs is not None and cs['metric'] == 'accuracy'
        meshes = [('본 방법 판', GC.ft_mesh(stem)), ('참값 목표 판 기준 추출', GC.gtt_mesh(stem, 'base')), ('참값 목표 판 가림 제외 추출', GC.gtt_mesh(stem, 'occl'))]
        K.CASES[name] = dict(cd=name, title=f'{TITLE} — {lab}: 본 방법 판 / 참값 목표 판 기준 추출 / 가림 제외 추출', meshes=meshes, missing=not acc, extra=1.5 if acc else 0., xray=False,
                             arrow='이 자리')
        GC.ROW['i'] = 0; K.draw(name); np.savez_compressed(GTO/'case'/f'place_{name}.npz', xyz=X, normal=N, point_id=pid)
        jp = K.FIG/f'case_{name}.json'; d = json.loads(jp.read_text()); d['place_rule'] = f'g3_case2.py docstring, place {name}'
        d['place_points'] = f'payload case/place_{name}.npz'; d['place_n'] = int(len(X)); jp.write_text(json.dumps(d, ensure_ascii=False, indent=1)+'\n')
        print('CASE2', name, stem, len(X), flush=True)
    b.case_def = orig_case_def

def annex():
    sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1'); from gt_common import table, TITLE as T_
    bx = b.ANNEX; G = np.load(GTJ/'reference/B0_b10/dense.npz')['xyz'].astype('f8'); tree = cKDTree(G); rows = []
    for arm, p in [('본 방법 판(FINALTRAIN)', GC.ft_mesh('B0_b10__ALS')), ('패치 다수결 판(A-1)', GTJ/'meshes/B0_b10__ALS__A1/final.ply'),
                   ('참값 목표 판 기준 추출', GC.gtt_mesh('B0_b10__ALS', 'base')), ('참값 목표 판 가림 제외 추출', GC.gtt_mesh('B0_b10__ALS', 'occl')),
                   ('참값 목표 판 중앙 깊이 추출', GC.gtt_mesh('B0_b10__ALS', 'median_depth')), ('참값 목표 판 둘 다 추출', GC.gtt_mesh('B0_b10__ALS', 'occl_median'))]:
        V, F = b.mesh(p); inb = (V[:, 0] >= bx['x'][0]) & (V[:, 0] <= bx['x'][1]) & (V[:, 1] >= bx['y'][0]) & (V[:, 1] <= bx['y'][1]) & (V[:, 2] >= bx['z'][0]) & (V[:, 2] <= bx['z'][1])
        d, _ = tree.query(V[inb]); far = d > 1.
        fm = inb[F].all(1); Vf = V[F[fm]]; area = .5*np.linalg.norm(np.cross(Vf[:, 1]-Vf[:, 0], Vf[:, 2]-Vf[:, 0]), axis=1); cen = Vf.mean(1); dc, _ = tree.query(cen)
        rows.append(dict(title=T_, place='B0 × 항공 LiDAR 별채 상자(덧붙임 4 ANNEX)', arm=arm, mesh=str(p).replace('/art/phase-payloads/phd', 'payload'), vertices_in_box=int(inb.sum()),
                         vertices_farther_1m=int(far.sum()), vertices_farther_1m_pct=round(100*float(far.mean()), 3) if inb.any() else None,
                         area_in_box_m2=round(float(area.sum()), 3), area_farther_1m_m2=round(float(area[dc > 1.].sum()), 3), small='n<30' if inb.sum() < 30 else ''))
    table('da_annex', rows); print('ANNEX', rows, flush=True)

if __name__ == '__main__':
    {'cells': cells, 'annex': annex}[sys.argv[1]]()
