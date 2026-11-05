"""Only the newly added cylinder, orientation and delayed-calibration definitions."""
import numpy as np
from common import *
from cylinder import Cylinder
from geometry_add1 import orient
cfg();stage_lock(0)
rng=np.random.default_rng(310);P=rng.normal(size=(1013,3));Q=rng.normal(size=(113,3));N=rng.normal(size=(113,3));N/=np.linalg.norm(N,axis=1)[:,None]
length=np.where(np.arange(len(Q))%2,5.,10.);r=.13;c=Cylinder(P);s,idx=c.query(Q,N,length,r);c.close()
expected=[]
for q,n,L in zip(Q,N,length):
    d=P-q;ax=d@n;rad=np.linalg.norm(d-ax[:,None]*n,axis=1);ids=np.flatnonzero((rad<=r)&(abs(ax)<=L))
    if not len(ids):expected.append(np.nan)
    else:expected.append(ax[ids[np.argmin(abs(ax[ids]))]])
assert np.allclose(s,expected,equal_nan=True,atol=1e-12)
p=np.array([[0.,0.,0.],[1,0,0]]);n=np.array([[0,0,-1.],[-1,0,0.]])
x=orient(p,n,[False,True],np.array([[5.,0.,5.]]));assert x[0,2]>0 and x[1,0]>0
v=dict(at=now(),status='PASS_NEW_ADD1_ONLY',cylinder_bruteforce_queries=113,orientation=True,previous_units_repeated=False,scientific_verdict=None)
dump(O/'verification/unit_add1_cpu.json',v);dump(D/'tables/unit_add1_cpu.json',v);print('ADD1_CPU_PASS')
