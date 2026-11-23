"""Check: df2_inputs with the FINALTRAIN target file reproduces FINALTRAIN seeds.npz and every map (arrays equal; sha256 noted). usage: df2_ftcheck.py <stem>"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
stem = sys.argv[1]; a = O/'families/ftcheck/stage1'/stem; b = FT/'stage1'/stem
res = dict(stem=stem, seeds_sha_equal=sha(a/'seeds.npz') == sha(b/'seeds.npz'))
sa, sb = loadz(a/'seeds.npz'), loadz(b/'seeds.npz'); res['seeds_arrays_equal'] = set(sa) == set(sb) and all(np.array_equal(sa[k], sb[k]) for k in sb)
ia = json.loads((O/'maps/ftcheck/base'/stem/'index.json').read_text()); ib = json.loads((b/'maps/index.json').read_text())
same_sha = arr = 0; bad = []
for n, v in ib['views'].items():
    same_sha += ia['views'][n]['sha256'] == v['sha256']
    za, zb = loadz(O/'maps/ftcheck/base'/stem/ia['views'][n]['file']), loadz(b/'maps'/v['file'])
    ok = all(np.array_equal(za[k], zb[k], equal_nan=True) for k in ['depth', 'sigma', 'weight', 'owner']); arr += ok
    if not ok: bad.append(n)
res.update(views=len(ib['views']), map_sha_equal=same_sha, map_arrays_equal=arr, differing_views=bad[:10], view_order_equal=list(ia['views']) == list(ib['views']), scientific_verdict=None)
res['passed'] = bool(res['seeds_arrays_equal'] and arr == len(ib['views']) and res['view_order_equal'])
dump(O/'checks'/f'ftcheck_{stem}.json', res); print('FTCHECK', json.dumps(res), flush=True)
