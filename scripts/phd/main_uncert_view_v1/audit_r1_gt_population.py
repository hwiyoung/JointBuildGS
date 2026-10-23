import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
root=Path('/ph/main_uncert_v1/PHD-MAIN-UNCERT-v1')
z=np.load(root/'patch_values/R1rep_b10__LoD2__R1.5.npz')
X=np.load(root/'points/R1rep_b10/gt_xyz.npy');tree=cKDTree(X)
ids=np.flatnonzero(z['in_eval'].astype(bool)&z['roof_like'].astype(bool)&np.isfinite(z['eL'])&(z['eL']>=2.8)&(z['eL']<=3.2))
rows=[]
for i in ids:
 c=z['centre'][i];n=z['normal'][i];ctr=c+np.arange(-9.75,10,.5)[:,None]*n
 found=np.unique(np.concatenate([np.asarray(a,int) for a in tree.query_ball_point(ctr,np.hypot(.5,.25)+1e-6)]))
 vec=X[found]-c;t=vec@n;rho=np.linalg.norm(vec-t[:,None]*n,axis=1);t=t[(rho<=.5)&(abs(t)<=10)]
 near=abs(t)<=.2;near50=abs(t)<=.5
 rows.append(dict(patch=int(i),face=int(z['surf'][i]),e_m=float(z['eL'][i]),n=len(t),near20=int(near.sum()),near50=int(near50.sum()),
  selected_n=int((abs(t-z['gt_o'][i])<=1).sum()),near20_median=float(np.median(t[near])) if near.any() else None))
summary=dict(task='R1 LoD2 2.8-3.2 m rooflike diagnostic',n=len(rows),
 near20_atleast10=sum(r['near20']>=10 for r in rows),near20_majority=sum(r['near20']>r['n']/2 for r in rows),
 near50_atleast10=sum(r['near50']>=10 for r in rows),
 median_gt_angle_deg=float(np.median(z['gt_angle'][ids])),angle_over45=int((z['gt_angle'][ids]>45).sum()),
 multiple_layers=int((z['gt_runs'][ids]>=2).sum()),scientific_verdict=None)
Path('/audit/three_m_population.json').write_text(json.dumps(dict(summary=summary,rows=rows),ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False))
for face in sorted({r['face'] for r in rows}):
 a=[r for r in rows if r['face']==face];print(face,len(a),sum(r['near20']>=10 for r in a),sum(r['near20']>r['n']/2 for r in a))
