import json, random, sys, glob
from pathlib import Path
import numpy as np
sys.path.insert(0, 'scripts/synthetic_a')
from buildings_3dbag import parse_tile

random.seed(0)
TARGET_TYPES = ['flat', 'gable', 'hip', 'tri-slope', 'complex']
PER_TYPE = 4
MIN_AREA = 50.0
MAX_AREA = 600.0

tiles = sorted(glob.glob('results/synthetic_a/3dbag_raw/amsterdam_jordaan/*.city.json'))
all_bldgs = []
for t in tiles:
    all_bldgs.extend(parse_tile(t))
print(f'loaded {len(all_bldgs)} buildings from {len(tiles)} tiles')

def footprint_area(b):
    pts = np.array(b['vertices'])
    dx = pts[:,0].max() - pts[:,0].min()
    dz = pts[:,2].max() - pts[:,2].min()
    return dx * dz

by_type = {t: [] for t in TARGET_TYPES}
for b in all_bldgs:
    a = footprint_area(b)
    if MIN_AREA <= a <= MAX_AREA and b['type'] in TARGET_TYPES:
        b['area'] = a
        by_type[b['type']].append(b)
for t in TARGET_TYPES:
    print(f'  {t}: {len(by_type[t])} candidates (after area filter)')

selected = []
for t in TARGET_TYPES:
    pool = sorted(by_type[t], key=lambda b: b['area'])
    if len(pool) < PER_TYPE:
        selected.extend(pool); continue
    idxs = [i * len(pool) // PER_TYPE + len(pool) // (2 * PER_TYPE) for i in range(PER_TYPE)]
    selected.extend([pool[i] for i in idxs])

print(f'\nSelected {len(selected)} buildings:')
for b in selected:
    name = b['name']; t = b['type']; a = b['area']; nf = len(b['faces'])
    print(f'  {name:25} type={t:10} area={a:6.1f}  faces={nf}')

out = []
for i, b in enumerate(selected):
    labels = np.asarray(b['labels'])
    unique, counts = np.unique(labels, return_counts=True)
    out.append({
        'sel_id': i, 'name': b['name'], 'type': b['type'], 'area': float(b['area']),
        'n_vertices': len(b['vertices']), 'n_faces': len(b['faces']),
        'label_counts': {str(int(k)): int(v) for k, v in zip(unique, counts)},
    })
Path('results/phase2_synthesis').mkdir(parents=True, exist_ok=True)
Path('results/phase2_synthesis/selected_buildings.json').write_text(json.dumps(out, indent=2))
print(f'\nsaved selection metadata -> results/phase2_synthesis/selected_buildings.json')
