"""Scorer validation (config scoring.new_meshes): re-score the stored A1 meshes with te_mesh.score and compare with GTJUDGE addendum12 distance_A1."""
from common import *
def main():
    rows = []
    for stem in SCENES:
        Z = loadz(O/'meshes'/f'{stem}__A1v'/'points.npz'); A = np.load(GT/'addendum12/distance_A1'/f'{stem}.npz')
        for k in ['s_m', 'state', 'within_tau1']:
            a, b = Z[f'reference__{k}'].astype(float), A[f'reference__A1__{k}'].astype(float); rows.append(dict(stem=stem, part='reference', key=k, n=len(a), equal=bool(np.array_equal(a, b, equal_nan=True)), max_abs_diff=float(np.nanmax(np.abs(a-b))) if len(a) else 0.))
        for k in ['case_id', 'reference_row_id', 'tau_m', 's_m', 'state', 'eligible_new', 'eligible_old', 'within_tau1', 'wall']:
            a, b = Z[f'result__{k}'].astype(float), A[f'result__A1__{k}'].astype(float); rows.append(dict(stem=stem, part='result', key=k, n=len(a), same_length=len(a) == len(b), equal=bool(len(a) == len(b) and np.array_equal(a, b, equal_nan=True)),
                                                                                                    max_abs_diff=float(np.nanmax(np.abs(a-b))) if len(a) == len(b) and len(a) else None))
        A.close()
    table('scorer_validation', rows); ok = all(r['equal'] for r in rows); dump(O/'verification/scorer_validation.json', dict(at=now(), status='PASS' if ok else 'FAIL', rows=rows, scientific_verdict=None))
    print('SCORER', 'PASS' if ok else 'FAIL', [(r['stem'], r['key'], r['equal'], r['max_abs_diff']) for r in rows if not r['equal']])
if __name__ == '__main__': main()
