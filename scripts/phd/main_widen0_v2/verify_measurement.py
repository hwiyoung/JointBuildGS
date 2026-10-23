"""Boundary, missing-value, face-assignment and copied-definition checks."""
import ast
import json
from pathlib import Path
import numpy as np
from face_assignment import attach,triangle_distance
from export_values import classify
from preflight import dump,sha,PH

for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text())
assert sha(Path(__file__).parent/'u_core.py')==sha('/repo/scripts/phd/main_uncert_v1/u_core.py')
g=np.array([0,0,0,0,0,0,1,2,3,0,0]);p=np.array([.2,.21,.2,.21,.2,.21,0,0,0,.2,.21]);e=np.array([.2,.2,.21,.21,np.nan,np.nan,.1,.1,.1,.1,.1])
assert classify(g,p,e,.2).tolist()==[0,1,2,3,4,5,6,6,6,0,1]
around=np.array([np.nextafter(np.float32(.2),np.float32(0)),np.float32(.2),np.nextafter(np.float32(.2),np.float32(1))])
assert np.array_equal(classify(np.zeros(3),around,around,.2),classify(np.zeros(3),around,around,np.full(3,.2)))
tri=np.array([[0.,0,0],[2,0,0],[0,2,0]])
assert np.allclose(triangle_distance(np.array([[.2,.2,1],[3.,0,0]]),tri),[1,1])
V=np.vstack([tri,tri+[0,0,2],[[0,0,0],[0,2,0],[0,0,2]]]);F=np.arange(9).reshape(-1,3)
rec=[dict(ext=1,type='roof',building='A'),dict(ext=2,type='roof',building='B'),dict(ext=3,type='wall',building='C')]
cent=np.array([[.2,.2,1.8],[.2,.2,1.],[.8,.2,.2],[1.01,.2,.2],[3,3,3]])
a,r=attach(cent,np.array([1,1,0,0,1],bool),rec,dict(V=V,F=F,tri_surface=np.array([1,2,3])))
assert a.tolist()==[1,0,2,-1,-1],a
old_cells=json.loads(Path('/repo/configs/phd/main_uncert_v1/uncert_v1.json').read_text())['cells']['order']
for site in ['B0_b10','B173nb_b10','R1rep_b10']:
    for prior in ['LoD2','ALS']:
        with np.load(PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1/patch_values'/f'{site}__{prior}__R1.5.npz') as z:
            ev=z['in_eval'].astype(bool);tau=z['tau'][ev];cell=z['cell'][ev]
            assert np.isfinite(tau).all() and np.all(tau>0),(site,prior,'old tau')
            assert np.all((cell>=0)&(cell<len(old_cells))),(site,prior,'old cell')
            assert np.all(z['building'][ev]!='') if prior=='LoD2' else np.all(z['building'][ev]=='')
dump('/out/gates/measurement_definitions.json',dict(status='PASS',checks=['syntax','byte-identical numerical core','seven exclusive boundary cells','scalar and vector tau agree at float32 neighbours of 0.20 m','finite actual error independent of ring availability','GT failure states retained','roof nearest height and deterministic tie','wall 1 m cutoff','unmatched excluded','historical evaluation tau and cell ranges valid; LoD2 IDs present and ALS IDs unavailable'],scientific_verdict=None))
print('measurement definition checks PASS')
