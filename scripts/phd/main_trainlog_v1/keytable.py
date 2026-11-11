"""Order 3 key-iteration table (question 바): mesh scores per case + scene, lineage bound share, first crossings (CPU)."""
from common import *
CASES = [0, 1, 2, 4, 'all']

def main():
    c = cfg(); rows = []; cross = {}
    for it in c['key_iterations']:
        p = O/'meshes'/f'tl_{it}'/'score.json'
        if not p.exists(): rows.append(dict(iteration=it, status='확인 불가: 메시 없음')); continue
        sc = {r['case_id']: r for r in json.loads(p.read_text())['rows']}; row = dict(iteration=it)
        for k in CASES:
            r = sc.get(k) or sc.get(str(k)); row[f'case{k}_completeness_pct'] = r['completeness_pct'] if r else None; row[f'case{k}_accuracy_pct'] = r['accuracy_pct'] if r else None
            row[f'case{k}_gt_n'] = r['n_gt'] if r else None
        lp = O/'lineage'/f'{it}.npz'
        if lp.exists():
            z = loadz(lp); d = loadz(DER/'gaussians'/f'{it}.npz', ['uid', 'target_tag']); bound = set(d['uid'][d['target_tag'] == 1].tolist())
            for g, lab in [(1, 'case_site'), (2, 'comparison_site')]:
                m = (z['group'] == g) & (z['uid'] >= 0); u = z['uid'][m]; row[f'{lab}_rows_attributed'] = int(m.sum()); row[f'{lab}_rows_total'] = int((z['group'] == g).sum())
                row[f'{lab}_drawing_bound_share_pct'] = float(np.mean([x in bound for x in u.tolist()])*100) if len(u) else None
                row[f'{lab}_drawing_gaussians'] = int(len(np.unique(u)))
        mj = O/'meshes'/f'tl_{it}'/'timing.json'
        rows.append(row)
    for thr, lab in [(66.577, '판단만 66.6'), (79.101, 'GeoGS 79.1'), (95., '95')]:
        hit = [r['iteration'] for r in rows if r.get('case1_completeness_pct') is not None and r['case1_completeness_pct'] > thr]; cross[lab] = hit[0] if hit else None
    table('key_iterations', rows); dump(D/'key_iterations.json', dict(at=now(), rows=rows, first_key_iteration_above=cross, note='case 1 = 사전 정보 오류 경우; GTJUDGE score_new + addendum11 rule', scientific_verdict=None))
    print('KEY', cross, flush=True)
if __name__ == '__main__': main()
