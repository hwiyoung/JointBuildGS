"""Order 5.1 / 5.2 tables from the scored extractions (CPU). usage: df9_score.py <stem> [<run> ...]   (default: every run with all three extractions scored)
Per run and extraction (base = WRONGTARGET basis, occl10, occlga):
  4 cases × 판 0 target right/wrong: points and share whose result surface is within τ (addendum11 normal-line distance, te_mesh score points.npz);
  named values: 주 지표 lost rate (case 2, target right), 지킬 값 1 fixed rate (case 1, target wrong), 지킬 값 2 lost rate (case 0, target right),
  함께 볼 값 fixed rate (case 2, target wrong), 참고 lost rate (case 4, target right); also without the type-changed patches (reply 1 §2),
  main value by target type, and on the switch's own points (판 5~8: split patches).
  completeness / accuracy (p9_final rule: reference within over eligible rows; result within over eligible_new), completeness per case,
  Gaussian counts at 15,000 and 30,000. Cells under 1,000 points: rate None (count only).
writes /df/score/<stem>__<run>.json, /df/points_out/res_<stem>.npz (per point within per run × extraction, bits base/occl10/occlga)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
GT = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'; VARS = ['base', 'occl10', 'occlga']; MIN = 1000
CASES = {0: '두 자료 모두 맞음', 1: '사전 정보가 틀림', 2: '영상 깊이가 틀림', 4: '영상 깊이 결측'}

def gauss(model):
    out = {}
    for it in (15000, 30000):
        f = model/'point_cloud'/f'iteration_{it}'/'point_cloud.ply'
        if f.exists():
            with f.open('rb') as h:
                for line in h:
                    if line.startswith(b'element vertex'): out[it] = int(line.split()[2]); break
    return out

def rate(mask, good):
    n = int(mask.sum()); return n, (100*float(good[mask].mean()) if n >= MIN else None)

def named(P, W, sel):
    cs, tok = P['case_id'], P['target_ok']; r = {}
    for key, cc, tt, lost in [('main_lost', 2, True, True), ('keep1_fixed', 1, False, False), ('keep2_lost', 0, True, True), ('also_fixed', 2, False, False), ('ref_lost', 4, True, True)]:
        m = sel & (cs == cc) & (tok == tt); n, v = rate(m, ~W if lost else W); r[key+'_n'] = n; r[key+'_pct'] = v
    return r

def main(stem, *runs):
    P = loadz(O/'points'/f'pts_{stem}.npz'); a11 = loadz(GT/'addendum11/final_data'/f'{stem}.npz', ['reference__eligible', 'reference__case_id']); el = a11['reference__eligible'].astype(bool); case_all = a11['reference__case_id']
    if not runs: runs = sorted({p.name.split('__df_')[1].rsplit('_', 1)[0] for p in (O/'meshes').glob(f'{stem}__df_*_base') if (p/'score.json').exists()})
    pix = O/'points'/f'pix_{stem}.npz'; occh = loadz(pix, ['occluded_instr_half_p0'])['occluded_instr_half_p0'] if pix.exists() else None
    resp = O/'points_out'/f'res_{stem}.npz'; res = loadz(resp) if resp.exists() else {}
    for run in runs:
        Mz = {v: O/'meshes'/f'{stem}__df_{run}_{v}' for v in VARS}
        have = [v for v in VARS if (Mz[v]/'points.npz').exists()]
        if 'base' not in have: print('SKIP', stem, run, flush=True); continue
        model = O/'runs'/stem/run/'model'; out = dict(extractions_present=have, stem=stem, scene=STEM_KO[stem], run=run, arm=run.rsplit('_s', 1)[0], seed=int(run.rsplit('_s', 1)[1]), gaussians=gauss(model), extractions={})
        bits = np.zeros(len(P['point_id']), 'u1')
        for i, v in enumerate(VARS):
            if v not in have: continue
            Z = loadz(Mz[v]/'points.npz', ['reference__within_tau1', 'result__eligible_new', 'result__within_tau1'])
            Wall = Z['reference__within_tau1'].astype(bool); W = Wall[P['point_id']]; bits |= (W.astype('u1') << i)
            e = Z['result__eligible_new'].astype(bool); acc = 100*float(Z['result__within_tau1'].astype(bool)[e].mean())
            comp = 100*float(Wall[el].mean()); compc = {CASES[c]: 100*float(Wall[el & (case_all == c)].mean()) for c in CASES}
            cells = []
            for c in CASES:
                for t in (True, False):
                    m = (P['case_id'] == c) & (P['target_ok'] == t); n, w = rate(m, W); cells.append(dict(case=CASES[c], target_ok=t, points=n, within_pct=w))
            allp = np.ones(len(W), bool)
            ex = dict(completeness_pct=comp, accuracy_pct=acc, completeness_by_case_pct=compc, cells=cells, named=named(P, W, allp),
                      named_without_type_changed=named(P, W, ~P['type_changed']), named_split_points=named(P, W, P['split']), named_split_p0_return=named(P, W, P['split'] & (P['type'] == 2)), named_split_p0_image=named(P, W, P['split'] & (P['type'] == 1)), named_occl_half_points=(named(P, W, occh) if occh is not None else None),
                      main_lost_by_type={TYPE_KO[k]: dict(zip(['n', 'pct'], rate((P['case_id'] == 2) & P['target_ok'] & (P['type'] == k), ~W))) for k in [0, 1, 2, 3, -1]},
                      fixed_also_by_type={TYPE_KO[k]: dict(zip(['n', 'pct'], rate((P['case_id'] == 2) & ~P['target_ok'] & (P['type'] == k), W))) for k in [0, 1, 2, 3, -1]})
            out['extractions'][v] = ex
        res[run] = bits; dump(O/'score'/f'{stem}__{run}.json', dict(out, scientific_verdict=None)); print('SCORED', stem, run, json.dumps(out['extractions']['base']['named']), flush=True)
    savez(resp, **res)

if __name__ == '__main__': main(*sys.argv[1:])
