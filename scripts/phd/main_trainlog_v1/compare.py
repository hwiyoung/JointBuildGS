"""Order 3 '원래 판과 대조' table (CPU). Original = PROCFIG-v1 gaussians/{7000,15000,30000}.npz (complete checkpoints);
new = derived/gaussians/<it>.npz of the trainlog run. Mesh row from meshes/<family>/score.json (case 1)."""
from common import *
from tl_defs import Defs, TAU
DERG = DER/'gaussians'

def stats(d, defs):
    s = defs.section(d); b = s['bound']; tin = np.abs(s['sd']) <= TAU
    return dict(building=len(d['xyz']), tag0=int((d['target_tag'] == 0).sum()), tag1=int((d['target_tag'] == 1).sum()), tag2=int((d['target_tag'] == 2).sum()),
                wall=int(d['wall'].sum()), wrong_lineage=int((d['group33'] == 1).sum()),
                tau_in_bound_pct=float(tin[b].mean()*100) if b.any() else None, tau_in_unbound_pct=float(tin[~b].mean()*100) if (~b).any() else None)

def main():
    c = cfg(); tol = c['comparison']; d0 = loadz(DERG/'0.npz'); defs = Defs(d0); od = Defs(loadz(PF/'gaussians/0.npz'))
    same_ref = bool(np.array_equal(defs.tx, od.tx)); rows = []; flags = []
    for it in tol['iterations']:
        a = stats(loadz(PF/'gaussians'/f'{it}.npz'), defs); b = stats(loadz(DERG/f'{it}.npz'), defs)
        for k in a:
            x, y = a[k], b[k]; count = k not in ['tau_in_bound_pct', 'tau_in_unbound_pct']
            diff = (y-x)/x*100 if count and x else (y-x if x is not None and y is not None else None)
            ok = (abs(diff) <= tol['count_tolerance_pct']) if count else (abs(diff) <= tol['metric_tolerance_pp'] if diff is not None else None)
            rows.append(dict(iteration=it, item=k, original=x, new=y, difference=diff, unit='%' if count else '%p', within=ok)); flags.append(ok)
    for fam, lab in [('tl_30000', 'mesh 30,000 (point_cloud/iteration_30000)')]:
        p = O/'meshes'/fam/'score.json'
        if p.exists():
            r = next(r for r in json.loads(p.read_text())['rows'] if r['case_id'] == 1)
            for k, ref in [('completeness_pct', tol['original_values']['completeness_case1_pct']), ('accuracy_pct', tol['original_values']['accuracy_case1_pct'])]:
                diff = r[k]-ref; ok = abs(diff) <= tol['metric_tolerance_pp']; rows.append(dict(iteration=30000, item=f'case1_{k}', original=ref, new=r[k], difference=diff, unit='%p', within=ok)); flags.append(ok)
        else: rows.append(dict(iteration=30000, item='case1 mesh', original=None, new=None, difference=None, unit='', within=None))
    same = all(f is True for f in flags)
    table('comparison_original_vs_new', rows)
    dump(D/'comparison.json', dict(at=now(), label=tol['label_if_within'] if same else tol['label_if_not'], same_plate=same, rows=rows, reference_targets_identical=same_ref,
         rule='counts ±5 %, τ-in and mesh ±2 %p (config comparison)', scientific_verdict=None))
    print('COMPARE', 'SAME' if same else 'DIFFERENT', flush=True)
    for r in rows: print(r)
if __name__ == '__main__': main()
