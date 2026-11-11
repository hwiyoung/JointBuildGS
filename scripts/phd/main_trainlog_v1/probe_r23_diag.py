"""Diagnostic after unit_check_v2 (not a rule change): r23 with four runs, symmetric to rule B."""
import itertools
from probe_check import *
def main():
    R23 = ['r23', 'r23_b', 'r23_c', 'r23_d']; OFF = ['r27_off_a', 'r27_off_b', 'r27_off_c', 'r27_off_d']
    S = {l: {it: load(l, it) for it in ITS} for l in R23+OFF}; rows = []
    for it in ITS:
        same = {p: quantities(S[p[0]][it], S[p[1]][it]) for p in list(itertools.combinations(R23, 2))+list(itertools.combinations(OFF, 2))}
        cross = {(a, b): quantities(S[a][it], S[b][it]) for a in R23 for b in OFF}
        for k in sorted(set().union(*[set(v) for v in list(same.values())+list(cross.values())])):
            sv = [v[k] for v in same.values() if k in v]; cv = [v[k] for v in cross.values() if k in v]
            if sv and cv: rows.append(dict(iteration=it, quantity=k, same_n=len(sv), same_min=min(sv), same_max=max(sv), cross_n=len(cv), cross_median=float(np.median(cv)), cross_max=max(cv), median_le_same_max=float(np.median(cv)) <= max(sv)))
    ok = all(r['median_le_same_max'] for r in rows)
    dump(O/'verification/unit_checks_r23_diagnostic.json', dict(at=now(), runs=R23+OFF, rows=rows, all_median_le_same_max=ok, note='diagnostic only; locked v2 r23 rule used a single r23 run', scientific_verdict=None))
    table('unit_checks_r23_diagnostic', rows); print('R23_DIAG', ok)
    for r in rows: print(r['iteration'], r['quantity'], r['same_min'], r['same_max'], r['cross_median'], r['cross_max'], r['median_le_same_max'])
if __name__ == '__main__': main()
