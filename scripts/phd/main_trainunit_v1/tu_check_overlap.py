"""Record-only check: JUDGECHECK patches that sit on FINALTRAIN site patches (same place twice)."""
import sys
from scipy.spatial import cKDTree
from tu_common import *
out = {}
for prior in PRIORS:
    U = loadz(TU / 'targets' / f'campus__{prior}.npz', ['centre', 'source', 'building', 'kind', 'area'])
    site = U['source'] < 3
    tree = cKDTree(U['centre'][site])
    d, _ = tree.query(U['centre'][~site], workers=8)
    jb = U['building'][~site]
    rows = []
    for thr in [0.1, 0.3, 1.0]:
        m = d < thr
        rows.append(dict(threshold_m=thr, patches=int(m.sum()), area_m2=float(U['area'][~site][m].sum()), buildings=sorted(set(jb[m].tolist()))[:20]))
    out[prior] = dict(judgecheck=int((~site).sum()), near_site=rows, site_buildings=sorted(set(U['building'][site].tolist()))[:20])
    print(prior, [(r['threshold_m'], r['patches'], len(r['buildings'])) for r in rows], flush=True)
ctx = json.loads((WD / 'inputs/lod2_context_buildings.json').read_text())
out['context_buildings'] = len(ctx['buildings']) if isinstance(ctx, dict) and 'buildings' in ctx else len(ctx)
out['at'] = now(); out['scientific_verdict'] = None
dump(TU / 'targets/overlap_check.json', out)
print('context', out['context_buildings'])
