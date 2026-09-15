"""Explain frozen candidate membership; never select a new training/evaluation set."""
import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import scipy
from scipy.spatial import cKDTree


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stats(values):
    a = np.asarray(values)
    return dict(n=int(a.size), median=float(np.median(a)),
                p10=float(np.quantile(a, .1)), p90=float(np.quantile(a, .9)))


out = Path('/out')
cfg = read(out / 'config.json')
root = Path('/art') / cfg['attempt_relative']
script = root / 'review_source_v2/review_and_masks.py'
# Execute only the original local-planarity function, without rerunning review/masks.
tree = ast.parse(script.read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'normals')
namespace = dict(np=np, cKDTree=cKDTree)
exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), 'exec'), namespace)
result = dict(scientific_verdict=None, regions={}, inputs={str(script): sha(script)},
              script_sha256=sha(__file__), versions=dict(numpy=np.__version__, scipy=scipy.__version__))

for region in ['R2', 'R3', 'R4', 'R5']:
    folder = root / region
    paths = [folder / 'audit/result/surface_evidence.npz', folder / 'review/judgments.npz',
             folder / 'review_zones.json', folder / 'audit/result/config.json', folder / 'masks/receipt.json']
    result['inputs'].update({str(p): sha(p) for p in paths})
    ev, j = np.load(paths[0]), np.load(paths[1])
    meta, audit, masks = [read(p) for p in paths[2:]]
    _, planar = namespace['normals'](ev['mvs_xyz'])
    zone = j['mvs_zone']; rel = ev['mvs_relation']
    building = np.array([z['kind'] == 'building' for z in meta['zones']])[zone]
    eligible = np.array([z['correction_test'] for z in meta['zones']])[zone]
    replay = planar & building & eligible & (rel == 2)
    assert np.array_equal(replay, j['mvs_judgment'] == 2), region
    stages = {'all_mvs': np.ones(len(zone), bool), 'prior_in_front_relation': rel == 2,
              'in_reviewed_building': (rel == 2) & building,
              'in_correction_context': (rel == 2) & building & eligible,
              'passes_local_planarity': replay}
    rows = []
    for i, z in enumerate(meta['zones']):
        sel = zone == i
        rows.append(dict(zone=z['id'], name=z['name'], correction_context=z['correction_test'],
                         stages={k: int((v & sel).sum()) for k, v in stages.items()},
                         relations={str(k): int((sel & (rel == k)).sum()) for k in range(6)}))
    result['regions'][region] = dict(stages={k: int(v.sum()) for k, v in stages.items()},
                                    zones=rows, release_pixels=masks['total_pixels'],
                                    release_views=masks['contributing_views'],
                                    relation_thresholds={k: audit[k] for k in ['large_disagreement_m',
                                        'minimum_support_views', 'minimum_camera_span_m', 'dominant_relation_fraction']})

for region in ['R1', 'R2']:
    path = root / cfg['analysis'] / (region + '_paired_samples.npz')
    result['inputs'][str(path)] = sha(path)
    a = np.load(path); sel = (a['source'] == 0) & (a['judgment'] == 2)
    rows = []
    for zid in [-1] + np.unique(a['zone'][sel]).tolist():
        s = sel & ((a['zone'] == zid) if zid >= 0 else True)
        d0, dd = a['distance_mvs'][s], a['distance_da3'][s]
        rows.append(dict(zone=zid, n=int(s.sum()), baseline_distance=stats(d0), da3_distance=stats(dd),
                         paired_distance_change=stats(dd-d0),
                         da3_farther_over_01m_percent=float(100*np.mean(dd-d0 > .1)),
                         baseline_nearest_z_offset=stats(a['closest_mvs'][s, 2]-a['xyz'][s, 2]),
                         da3_nearest_z_offset=stats(a['closest_da3'][s, 2]-a['xyz'][s, 2])))
    result['regions'].setdefault(region, {})['frozen_correction_distances'] = rows

result['status'] = 'PASS_FROZEN_COHORT_REPLAY'
result['limitations'] = [
    'One-sided input-relation hypotheses, not confirmed change or accurate current surfaces.',
    'Point-to-mesh input agreement is not independent accuracy or same-surface correspondence.',
    'Planarity is recomputed from the frozen function and checked against every saved correction label.',
    'No masks, source data, trained results, or published evaluation cohorts were modified.']
(out / 'receipt.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
print(json.dumps({r: {k:v for k,v in d.items() if k in ['stages','release_pixels','release_views']}
                  for r,d in result['regions'].items()}, ensure_ascii=False))
