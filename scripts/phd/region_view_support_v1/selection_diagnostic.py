#!/usr/bin/env python3
"""Reproduce the legacy P1 all-corner gate on the frozen full camera census."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


root=Path('/input');out=Path('/output/selection_review');out.mkdir(exist_ok=False)
cfg=json.loads((root/'config.json').read_text());p=cfg['legacy_prisms']['P1']
views=json.loads((root/'camera_bindings.json').read_text())['cameras']
names=[v['name'] for v in views]
old=json.loads(Path('/bindings/P1.json').read_text())
old_names=set([v['name'] for v in old['train']]+old['evaluation_names'])
old_train=set(v['name'] for v in old['train'])
members=json.loads((root/'candidate_memberships.json').read_text())['regions']['R1']
new_train={names[i] for i in members['train']}
ground=np.load('/review/P1_ground_strict_point_support.npz')
support=np.unpackbits(ground['packed'],axis=1)[:,:int(ground['point_count'])]
source=views[names.index('DJI_20241217084553_0100_D.JPG')]
corners=np.array([[x,y,z] for x in p['x'] for y in p['y'] for z in p['z']])
rows=[]
for i,v in enumerate(views):
    cam=corners@np.asarray(v['R']).T+np.asarray(v['t']);z=cam[:,2]
    uvz=cam@np.asarray(v['K']).T;uv=uvz[:,:2]/np.where(z>1e-6,z,1)[:,None]
    xy=np.floor(uv+.5).astype(int)
    inside=(z>1e-6)&(xy[:,0]>=0)&(xy[:,0]<v['width'])&(xy[:,1]>=0)&(xy[:,1]<v['height'])
    rows.append(dict(name=v['name'],old_all=v['name'] in old_names,old_train=v['name'] in old_train,
        R1_train=v['name'] in new_train,inside_corners=int(inside.sum()),
        all_corners_pass=bool(inside.all()),ground_support_pct=100*float(support[i].mean()),
        distance_from_0100_camera_m=float(np.linalg.norm(np.asarray(v['center'])-source['center'])),
        rgb_sha256=v['rgb_sha256'],native_depth_sha256=v['native_depth']['sha256']))
all_corners={r['name'] for r in rows if r['all_corners_pass']}
recovered=sorted([r for r in rows if r['R1_train'] and not r['old_all']],key=lambda r:-r['ground_support_pct'])
with (out/'P1_selection_all_937.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
report=dict(scientific_verdict=None,old_all_views=len(old_names),all_corners_pass_count=len(all_corners),
    exact_legacy_membership_reproduced=all_corners==old_names,
    missing_from_corner_rule=sorted(old_names-all_corners),extra_in_corner_rule=sorted(all_corners-old_names),
    recovered_top_views=recovered[:20],
    limits='Region extent and selection rule both changed. The recovered cameras also observe the original P1 ground; wider area alone is not the causal explanation.',
    inputs={'camera_bindings_sha256':digest(root/'camera_bindings.json'),'P1_binding_sha256':digest('/bindings/P1.json'),
            'P1_strict_support_sha256':digest('/review/P1_ground_strict_point_support.npz')},
    script_sha256=digest(__file__))
(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
