"""Order 9 checks (CPU). usage: tp8_checks.py
1. 0절 counts: target points / lost points / GTT-also-lost equal the order's values.
2. Per point the five kinds sum to the number of facing views (pairs) - by construction, recounted from the stored arrays.
3. Method run and GTT run use the same points and the same (point, view) pairs (same geometry, only the maps differ).
4. CPU compositing (tp4_contrib) mean depth vs the stored base render depth at the same pixels (where both exist).
Writes /docs/checks.json and /tp/checks/contrib_vs_render.json."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
ORDER = {'R1rep_b10__ALS': (18152, 7558, 708), 'B173nb_b10__ALS': (6012, 826, 106), 'B0_b10__ALS': (1040, 130, 49), 'R1rep_b10__LoD2': (2291, 1186, 238),
         'B173nb_b10__LoD2': (4464, 1299, None), 'B0_b10__LoD2': (2411, 365, 119)}

def main():
    out = dict(at=now(), title=TITLE, order0={}, kinds_sum={}, same_pairs={}, contrib_vs_render={}, scientific_verdict=None)
    for stem in STEMS:
        P = loadz(O/'points'/f'sel_{stem}.npz'); J = json.loads((O/'points'/f'sel_{stem}.json').read_text())
        got = (J['counts_full']['target'], J['counts_full']['target_lost'], int(((P['group'] == 0) & (P['group_gtt'] == 1)).sum()) if (P['group_gtt'] >= 0).any() else None)
        out['order0'][stem] = dict(order=ORDER[stem], got=got, equal=tuple(ORDER[stem]) == tuple(got))
        Z = {}
        for run in ['ft', 'gtt']:
            p = O/'pairs'/f'{run}_{stem}.npz'
            if not p.exists(): continue
            z = loadz(p, ['pt', 'view', 'kind']); Z[run] = z; n = len(P['group'])
            cnt = np.zeros((n, 5), 'i8'); np.add.at(cnt, (z['pt'], z['kind']), 1); nv = np.bincount(z['pt'], minlength=n)
            out['kinds_sum'][f'{run}_{stem}'] = dict(equal=bool((cnt.sum(1) == nv).all()), kinds_in_range=bool(((z['kind'] >= 0) & (z['kind'] <= 4)).all()), pairs=int(len(z['pt'])))
        if len(Z) == 2:
            a, b = Z['ft'], Z['gtt']; out['same_pairs'][stem] = bool(np.array_equal(a['pt'], b['pt']) and np.array_equal(a['view'], b['view']))
        for run in ['ft', 'gtt']:
            r = render_dir(stem, run); pp = O/'pairs'/f'{run}_{stem}.npz'
            cps = [O/'contrib'/f'{run}_{stem}_{m}.npz' for m in ('sub', 'all')]; cps = [c for c in cps if c.exists()]
            if r is None or not pp.exists() or not cps: continue
            z = loadz(pp, ['pt', 'view', 'rdepth', 'z']); c = loadz(cps[0], ['pt', 'view', 'mean'])
            key = c['pt'].astype('i8')*100000+c['view']; o = np.argsort(key); k2 = z['pt'].astype('i8')*100000+z['view']; pos = np.clip(np.searchsorted(key[o], k2), 0, len(o)-1)
            hit = key[o][pos] == k2; d = c['mean'][o][pos][hit].astype('f8')-z['rdepth'][hit].astype('f8'); ok = np.isfinite(d)
            out['contrib_vs_render'][f'{run}_{stem}'] = dict(pairs=int(ok.sum()), abs_median_m=float(np.median(np.abs(d[ok]))) if ok.any() else None,
                                                             within_1cm_pct=pct(np.abs(d[ok]) <= .01), within_5cm_pct=pct(np.abs(d[ok]) <= .05), p99_abs_m=float(np.percentile(np.abs(d[ok]), 99)) if ok.any() else None,
                                                             render=str(r))
    dump(D/'checks.json', out); dump(O/'checks/contrib_vs_render.json', out['contrib_vs_render']); print(json.dumps(out, ensure_ascii=False, indent=1)[:3000], flush=True)

if __name__ == '__main__': main()
