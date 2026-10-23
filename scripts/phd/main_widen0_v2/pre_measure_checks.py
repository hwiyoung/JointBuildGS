"""Exercise task inputs and plotting helpers before expensive patch measurement."""
import ast
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from components import labels_for
from distributions import site_masks
from preflight import dump
O=Path('/out');root=O/'holdout/internal';checks=[]
for f in Path(__file__).parent.glob('*.py'):ast.parse(f.read_text());checks.append('syntax:'+f.name)
assert len(site_masks(np.array([[0.,0,0],[100.,100,0]])))==4
labels,n,r=labels_for(np.array([[0.,0,0],[.25,0,0],[2.,0,0]]),dict(median_spacing_m=.25,radius_m=.36))
assert n==2 and labels[0]==labels[1] and labels[1]!=labels[2]
tiles=json.loads((O/'inputs/tiles.json').read_text());records=[]
for tile in tiles:
    t=tile['id'];row=dict(tile=t)
    for pr in ['lod2','als']:
        with np.load(root/'prior_tiles'/t/f'{pr}_store.npz') as z:
            row[pr+'_source_patches']=len(z['loc_center'])
            assert z['loc_center'].shape==z['loc_t1'].shape==z['loc_t2'].shape
            assert np.isfinite(z['loc_center']).all()
    gt=np.load(root/'points'/t/'gt_xyz.npy',mmap_mode='r');assert gt.ndim==2 and gt.shape[1]==3
    row['gt_points']=len(gt);records.append(row)
dump(root/'pre_measure_input_sizes.json',dict(rows=records,scientific_verdict=None))
dump(O/'gates/pre_measure.json',dict(status='PASS',tiles=len(tiles),checks=['all_script_syntax','evaluation_masks','known_component_connectivity','all_tile_source_shapes','GT_point_shape'],scientific_verdict=None))
print('pre-measurement checks PASS',len(tiles),'tiles')
