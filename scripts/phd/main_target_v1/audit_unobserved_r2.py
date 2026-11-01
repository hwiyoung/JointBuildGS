"""Input-only audit of saved cylinder counts, before locking the r2 amendment."""
import numpy as np
from common import *


def main():
    cfg, lock = locked()
    root = OUT / 'r2/input_audit'
    root.mkdir(parents=True, exist_ok=True)
    rows, sources = [], []
    for site in cfg['sites'] + cfg['deferred_sites']:
        for prior in cfg['priors']:
            key = f'{site}_{prior}'
            inp = OUT / 'stage0_r1/inputs' / f'{key}.npz'
            raw = OUT / 'stage0_r1/cylinders' / f'{key}.bin'
            with np.load(inp) as z:
                d = {k: z[k] for k in ['centre', 'normal', 'kind', 'area', 'in_eval']}
            with np.load(OUT / 'targets' / f'{key}.npz') as z:
                unobserved = z['region'] == 0
            with np.load(raw.with_suffix('.selected.npz')) as z:
                ridx = z['radius_index']
            a = np.memmap(raw, dtype='<f8', mode='r', shape=(len(ridx), 3, 10, 7))
            h5 = np.array(a[np.arange(len(ridx)), 0, ridx])
            h10 = np.array(a[np.arange(len(ridx)), 2, ridx])
            masks = {
                'r1_unobserved': unobserved,
                'raw_h5_positive': unobserved & (h5[:, 6] > 0),
                'raw_h5_1_to_3': unobserved & (h5[:, 6] > 0) & (h5[:, 6] < 4),
                'face_not_found_h5': unobserved & (h5[:, 6] >= 4) & (h5[:, 0] == 0),
                'selected_under_4_h5': unobserved & (h5[:, 6] >= 4) & (h5[:, 0] > 0),
                'length_h5_empty_h10_observed': unobserved & (d['kind'] == 1) & (h5[:, 6] == 0) & (h10[:, 0] >= 4),
                'length_h5_empty_h10_has_points': unobserved & (d['kind'] == 1) & (h5[:, 6] == 0) & (h10[:, 6] > 0),
                'still_empty_h10': unobserved & (h10[:, 6] == 0),
            }
            for scope, scope_mask in [('evaluation', d['in_eval']), ('band', ~d['in_eval'])]:
                for kind in [1, 2]:
                    for name, mask in masks.items():
                        m = mask & scope_mask & (d['kind'] == kind)
                        rows.append(dict(site=site, prior=prior, scope=scope, kind=kind,
                                         reason=name, patches=int(m.sum()), area_m2=float(d['area'][m].sum())))
            np.savez_compressed(root / f'{key}.npz', **d, h5=h5, h10=h10, **masks)
            sources.extend(dict(path=str(p), sha256=sha(p)) for p in [inp, raw])
    result = dict(at=stamp(), rows=rows, inputs=sources, config_sha256=lock['config_sha256'],
                  no_gt_loaded=True, scientific_verdict=None)
    dump(root / 'counts.json', result)
    dump(DOC / 'tables/unobserved_input_audit_r2.json', result)
    for row in rows:
        if row['scope'] == 'evaluation' and row['patches'] and row['reason'] != 'r1_unobserved':
            print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
