"""Boundary, missing-value, face-assignment and copied-definition checks."""
import ast
from pathlib import Path
import numpy as np
from face_assignment import attach,triangle_distance
from export_values import classify
from preflight import dump,sha

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
dump('/out/gates/measurement_definitions.json',dict(status='PASS',checks=['syntax','byte-identical numerical core','seven exclusive boundary cells','scalar and vector tau agree at float32 neighbours of 0.20 m','finite actual error independent of ring availability','GT failure states retained','roof nearest height and deterministic tie','wall 1 m cutoff','unmatched excluded'],scientific_verdict=None))
print('measurement definition checks PASS')
