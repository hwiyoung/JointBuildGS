import numpy as np
from scipy.special import expit
from analyze import stats,track,signed_distances,opacity_stats
assert stats([1,1,1])['median_m']==1
assert stats([-1,-1,-1])['median_m']==-1
assert stats([0,0,0])['nmad_m']==0
assert stats([-.3,.1,.3])['abs_gt_0_2_fraction']==2/3
assert np.allclose(expit(np.array([0.,np.log(99),-np.log(999)])),[.5,.99,.001])
a=np.array([[0.,0,0],[0.01,0,0],[1,0,0],[2,0,0]])
b=np.array([[0.,0,0],[1.01,0,0],[3,0,0]])
d,i,k,r=track(a,b)
assert r=={'source_count':4,'distance_failed':1,'nonfinite_source_failed':0,'nonfinite_destination_excluded':0,'collision_failed':1,'matched_unique':2,'unmatched_total':2},r
assert np.allclose(d[k],[0,.01])
# Invalid destination rows must not renumber native mask indices.
d,i,k,r=track(np.array([[1.,0,0],[np.nan,0,0],[3.,0,0]]),np.array([[np.nan,0,0],[1.01,0,0]]))
assert i[k].tolist()==[1] and r['nonfinite_destination_excluded']==1
assert r['nonfinite_source_failed']==1 and r['distance_failed']==1 and r['unmatched_total']==2
d,i,k,r=track(np.array([[0.,0,0]]),np.array([[np.nan,0,0]]))
assert not k.any() and r['distance_failed']==1
s=opacity_stats([np.nan,.001,.9]);assert s['n']==3 and s['opacity_valid_n']==2 and s['opacity_nonfinite_n']==1
assert s['opacity_gt_0_5_fraction']==.5 and s['opacity_lt_0_01_fraction']==.5
# Roof sign: an upward reconstruction offset is positive against an upward original normal.
for dz in [-1.,.25,1.]:
 displacement=np.array([[0.,0.,dz]]);normal=np.array([[0.,0.,1.]]);signed,component=signed_distances(displacement,normal);assert signed[0]==dz
signed,component=signed_distances(np.array([[3.,0.,4.],[-3.,0.,-4.]]),np.array([[0.,0.,1.],[0.,0.,1.]]))
assert np.allclose(signed,[5.,-5.]) and np.allclose(component,[4.,-4.])
print('PASS: signed offsets, NMAD, thresholds, sigmoid, unique matching and failure accounting')
