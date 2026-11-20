"""Stage 3 reference row (CPU): B173 x LoD2 has no 30,000 model (15,000 health stop 3 times: gtt_s0, gtt_s0_rerun1, gtt_s1). Earlier decision (issues.md 2026-11-20):
the gtt_s0_rerun1 15,000 model is extracted as a reference row (four variants). Not comparable with the 30,000 rows of the other scenes; written in its own table.
table ga_reference: target within / lost / recovery shares as in tables ga and ra, method run (FINALTRAIN 30,000) next to it."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
stem = 'B173nb_b10__LoD2'; A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); el = A['reference__eligible'].astype(bool)
tw = np.load(O/'meshes'/f'{stem}__gtt_target/points.npz')['reference__within_tau1'].astype(bool)
W = {v: np.load(O/'meshes'/f'{stem}__gtt_s0_rerun1_it15000_{v}/points.npz')['reference__within_tau1'].astype(bool) for v in ['base', 'occl', 'median_depth', 'occl_median']}
ok = el & tw; lost = ok & ~W['base']; rec = np.where(W['occl'], 0, np.where(W['median_depth'] | W['occl_median'], 1, 2)); c = np.bincount(rec[lost], minlength=3)
mt = A['reference__judgment_mesh__within_tau1'].astype(bool); mr = A['reference__FINALTRAIN_30000__within_tau1'].astype(bool); mok = el & mt; ml = mok & ~mr
rows = [dict(title=TITLE, stem=stem, arm='참값 목표 판 참고 줄(gtt_s0_rerun1 15,000회 모델, 30,000회 아님)', gt_rows=int(el.sum()), target_within_n=int(ok.sum()), target_within_pct=round(100*ok.sum()/el.sum(), 3),
             lost_n=int(lost.sum()), lost_pct_of_target_within=round(100*lost.sum()/ok.sum(), 3), back_occl_pct=round(100*c[0]/max(1, c.sum()), 3), back_median_pct=round(100*c[1]/max(1, c.sum()), 3), not_back_pct=round(100*c[2]/max(1, c.sum()), 3),
             completeness_pct={v: round(100*float(w[el].mean()), 3) for v, w in W.items()}),
        dict(title=TITLE, stem=stem, arm='본 방법 판(FINALTRAIN 30,000)', gt_rows=int(el.sum()), target_within_n=int(mok.sum()), target_within_pct=round(100*mok.sum()/el.sum(), 3), lost_n=int(ml.sum()), lost_pct_of_target_within=round(100*ml.sum()/mok.sum(), 3))]
table('ga_reference', rows); print('REF', rows, flush=True)
