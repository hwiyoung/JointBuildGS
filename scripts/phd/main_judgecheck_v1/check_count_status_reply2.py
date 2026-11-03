import numpy as np
from preflight import O
counts=[]
for p in sorted((O/'r1/geometry').glob('*ALS.npz')):
 with np.load(p) as z:
  bad=z['n']<0;m=bad&~np.isfinite(z['u_mvs'])
  if bad.any():print(p.name,'normal_missing',int(bad.sum()),'n',np.unique(z['n'][bad],return_counts=True),'missing_u_with_unknown_n',int(m.sum()),'area',float(z['area'][m].sum()),flush=True)
  counts.append((int(m.sum()),float(z['area'][m].sum())))
print('TOTAL',sum(c for c,a in counts),sum(a for c,a in counts))
