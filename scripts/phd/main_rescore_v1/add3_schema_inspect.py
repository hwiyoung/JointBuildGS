"""Read saved tolerance arrays after a legacy-receipt schema mismatch."""
from common import *
for family in ['prior', 'mvs']:
    root=O/'scores'/f'B173nb_b10__ALS__{family}'
    v=json.loads((root/'values.json').read_text())
    z=loadz(root/'points.npz',['scene_tau_m','sample_tau_m','row_tau_m'])
    print(family, v['provenance'], flush=True)
    for key,x in z.items():
        u,n=np.unique(x,return_counts=True)
        print(key, list(zip(u.tolist(),n.tolist())),flush=True)
