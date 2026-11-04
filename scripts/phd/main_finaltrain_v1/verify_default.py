import torch
from common import *
def same(a,b):
    if torch.is_tensor(a):return torch.equal(a,b)
    if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    if isinstance(a,np.ndarray):return np.array_equal(a,b)
    return a==b
a=torch.load(O/'verification/default/r22/state.pth',map_location='cpu',weights_only=False)
b=torch.load(O/'verification/default/r23_off/state.pth',map_location='cpu',weights_only=False)
assert same(a,b),'Default-off 100-step model/Adam/decision/camera divergence'
dump(O/'verification/unit_default.json',dict(at=now(),status='PASS',steps=100,seed=0,
    actual_GaussianModel=True,model_Adam_equal=True,target_decisions_equal=True,camera_sequence_equal=True,scientific_verdict=None))
print('PASS_DEFAULT_100')
