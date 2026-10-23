import json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,'/repo/scripts/phd/main_uncert_v1')
from u_core import find_face
root=Path('/ph/main_uncert_v1/PHD-MAIN-UNCERT-v1')
z=np.load(root/'patch_values/R1rep_b10__LoD2__R1.5.npz')
gt=np.load(root/'points/R1rep_b10/gt_xyz.npy');tree=cKDTree(gt)
mesh=np.load('/ph/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box/R1rep_b10/lod2_mesh.npz')
tri=mesh['V'][mesh['F']];ext=mesh['tri_surface'];e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0]
cfg=json.loads(Path('/repo/configs/phd/main_uncert_v1/uncert_v1.json').read_text())['defs']
out=[]
for i in [7212,82749,101627,96891,80442,91769,107801]:
 c=z['centre'][i];n=z['normal'][i];H=10 if z['roof_like'][i] else 3
 q=c+np.arange(-H+.25,H,.5)[:,None]*n
 ix=np.unique(np.concatenate([np.asarray(a,int) for a in tree.query_ball_point(q,np.hypot(.5,.25)+1e-6)]))
 vec=gt[ix]-c;t=vec@n;lat=vec-t[:,None]*n;rho=np.linalg.norm(lat,axis=1)
 keep=(rho<=.5)&(abs(t)<=H);ix=ix[keep];vec=vec[keep];t=t[keep];rho=rho[keep]
 o,runs,count=find_face(t,H,cfg);sel=abs(t-o)<=1
 assert abs(np.median(t[sel])-z['gt_p'][i])<1e-6
 ts=np.sort(t);splits=np.flatnonzero(np.diff(ts)>.15)+1;groups=np.split(ts,splits)
 group=[dict(n=len(g),lo=float(g.min()),median=float(np.median(g)),hi=float(g.max()),selected=int(np.sum(abs(g-o)<=1))) for g in groups]
 # All intersections of the patch's normal line with the LoD2 mesh.
 h=np.cross(np.broadcast_to(n,e2.shape),e2);det=np.einsum('ij,ij->i',e1,h);ok=abs(det)>1e-9
 inv=np.divide(1,det,out=np.zeros_like(det),where=ok);s=c-tri[:,0];u=inv*np.einsum('ij,ij->i',s,h)
 qq=np.cross(s,e1);v=inv*(qq@n);tt=inv*np.einsum('ij,ij->i',e2,qq)
 hit=ok&(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)
 intersections=[dict(face=int(a),normal_m=float(b)) for a,b in zip(ext[hit],tt[hit])]
 close=(abs(t)<.2)
 row=dict(patch=i,face=int(z['surf'][i]),roof=bool(z['roof_like'][i]),normal=n.tolist(),centre=c.tolist(),
  gt_p_m=float(z['gt_p'][i]),gt_o_m=float(o),gt_runs=int(runs),gt_angle_deg=float(z['gt_angle'][i]),
  original_gt_median_m=float(z['gt_med'][i]),column_n=len(t),selected_n=int(sel.sum()),
  within_20cm_n=int(close.sum()),closest_normal_distance_m=float(min(abs(t))),
  nearest_gt_distance_m=float(tree.query(c)[0]),point_groups=group,lod2_intersections=intersections,
  mvs_a_p_m=float(z['mvs_a_p'][i]),mvs_a_e_m=float(z['mvs_a_e'][i]),mvs_a_o_m=float(z['mvs_a_o'][i]))
 out.append(row);np.savez('/audit/three_m_patch_'+str(i)+'.npz',vec=vec,t=t,selected=sel,normal=n,centre=c)
 print(json.dumps(row,ensure_ascii=False),flush=True)
def clean(x):
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,list):return [clean(v) for v in x]
 if isinstance(x,float) and not np.isfinite(x):return None
 return x
Path('/audit/three_m_results.json').write_text(json.dumps(clean(out),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
