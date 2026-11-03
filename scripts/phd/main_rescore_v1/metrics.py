"""Four uncapped values; the normal-distance eligibility is inherited AXES E."""
import numpy as np
def four(gt_distance,result_distance,gt_tau,result_tau,gt_mask=None,result_mask=None):
 g=np.asarray(gt_distance,dtype=float);r=np.asarray(result_distance,dtype=float)
 gt_tau=np.broadcast_to(gt_tau,g.shape);result_tau=np.broadcast_to(result_tau,r.shape)
 gm=np.ones(len(g),bool) if gt_mask is None else np.asarray(gt_mask,bool)
 rm=np.ones(len(r),bool) if result_mask is None else np.asarray(result_mask,bool)
 n=int(gm.sum());m=int(rm.sum())
 return dict(n_gt=n,n_result=m,completeness=float((g[gm]<=gt_tau[gm]).mean()) if n else None,accuracy=float((r[rm]<=result_tau[rm]).mean()) if m else None,gt_mean_m=float(g[gm].mean()) if n else None,result_mean_m=float(r[rm].mean()) if m else None)
def inherited_result_mask(nd,lat):return np.isfinite(nd)&np.isfinite(lat)&(lat<=.5)
