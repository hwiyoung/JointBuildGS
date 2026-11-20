"""PHD-MAIN-BASE151-v1 read-only check (11-20 회신 1): per run and unit of /gtjudge/score151, rows / rows hit / samples,
units with zero accuracy samples, and whether every row of the prior file is counted once in rows.npz. Prints, writes nothing.
scientific_verdict: null
"""
import json
import sys

import numpy as np

sys.path.insert(0, '/b151s')
import b151_score151 as S  # noqa: E402
import b151_common as BC  # noqa: E402

S.gt_cfg(); BC.cfg('score151')
units = sorted(S.layout())
for d in sorted((S.O / 'score151').iterdir()):
    run, prior = d.name.split('__')
    n_rows = len(np.load(BC.B / 'gt' / f'gt151_{prior}.npz')['case'])
    seen = np.zeros(n_rows, 'i4')
    zero, missing, hits, kept_key = [], [], 0, 0
    for u in units:
        p = d / f'{u}.npz'
        if not p.exists():
            missing.append(u); continue
        z = np.load(p)
        m = z['row_main']; seen[z['rows'][m]] += 1
        hits += int(np.isfinite(z['row_s'][m]).sum())
        kept_key += 'kept_triangles_any' in z.files
        if int(z['samples']) == 0:
            zero.append((u, int(m.sum()), int(np.isfinite(z['row_s'][m]).sum()), bool(z['kept_triangles_any']) if 'kept_triangles_any' in z.files else None))
    summ = json.loads((d / 'summary.json').read_text()) if (d / 'summary.json').exists() else None
    print(json.dumps(dict(run=d.name, units_scored=len(units) - len(missing), missing=missing, rows=n_rows,
                          rows_counted_once=int((seen == 1).sum()), rows_counted_twice=int((seen > 1).sum()), rows_not_on_unit=int((seen == 0).sum()),
                          rows_hit=hits, zero_sample_units=zero, units_with_kept_flag=kept_key, gathered=summ is not None,
                          gathered_at=summ and summ['at']), ensure_ascii=False))
