"""PHD-MAIN-BASE151-v1 read-only (11-20 회신 1): rows of one scored unit -> hit / within tau / no surface, with the case of each hit row. Prints only.
scientific_verdict: null
"""
import sys

import numpy as np

sys.path.insert(0, '/b151s')
import b151_score151 as S  # noqa: E402
import b151_common as BC  # noqa: E402

run, prior, u = sys.argv[1:]
S.gt_cfg(); BC.cfg('score151')
z = np.load(S.O / 'score151' / f'{run}__{prior}' / f'{u}.npz')
g = np.load(BC.B / 'gt' / f'gt151_{prior}.npz')
m = z['row_main']; r = z['rows'][m]; s = z['row_s'][m]; tau = g['tau'][r]
hit = np.isfinite(s)
print('rows', len(r), 'hit', int(hit.sum()), 'within_tau', int((hit & (abs(s) <= tau)).sum()), 'no_surface', int((~hit).sum()),
      'literal_rows', int((~m).sum()), 'samples', int(z['samples']))
for i in np.flatnonzero(hit):
    print('hit_row', int(r[i]), 's_m', round(float(s[i]), 3), 'tau_m', round(float(tau[i]), 3), 'case', int(g['case'][r[i]]), 'building', str(g['building'][r[i]]))
