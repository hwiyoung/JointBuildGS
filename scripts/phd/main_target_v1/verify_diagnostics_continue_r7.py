"""Independent exhaustive-distance and uncullled-pixel checks for the ALS diagnostic."""
import numpy as np
from common import *
from diagnose_als_continue_r7 import load

def main():
 root=OUT/'r7_continue/diagnostics/ALS';run=OUT/'r7/runs/tg_B173nb_b10_ALS_s0_r7';s=load(run/'model/target_monitor/snapshot_7000.npz');t=load(OUT/'r7/targets/B173nb_b10_ALS.npz');flags=load(root/'counterfactual_gaussians.npz')['r7_targets'];valid=(t['region']>=0)&np.isfinite(t['target']).all(1)&np.isfinite(t['normal']).all(1)&np.isfinite(t['sigma'])&(t['sigma']>0);points=t['target'][valid].astype(float);kept=np.flatnonzero((s['target_tag']==1)&~flags);test=np.r_[np.flatnonzero(flags),kept[np.linspace(0,len(kept)-1,64,dtype=int)]];dist=np.array([np.linalg.norm(points-s['xyz'][i].astype(float),axis=1).min() for i in test]);assert np.array_equal(dist>.5,flags[test]);e=load(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2/B173nb_b10__ALS/evaluation.npz');z=load(run/'post7000/patch_z.npz');floating=e['in_eval']&e['scoring_allowed']&(z['category']==1);hits=e['centre'][floating]+z['z'][floating,None]*e['normal'][floating];n=e['normal'][floating].astype(float);n/=np.linalg.norm(n,axis=1)[:,None];axis=np.tile([0.,0.,1.],(len(n),1));axis[abs(n[:,2])>.9]=[1,0,0];u=np.cross(n,axis);u/=np.linalg.norm(u,axis=1)[:,None];v=np.cross(n,u);cover=json.loads((run/'model/check7000/coverage.json').read_text());checked=0;matches=0;gaussians=set()
 for view in cover['views']:
  a=load(root/'full_pixel_enumeration'/f"{view['camera']}.npz");yy,xx=a['y'],a['x']
  if not len(yy):continue
  depth=load(run/'model/check7000/renders'/f"{view['camera']}.npz")['depth'][yy,xx];mx=load(OUT/'r7/failures/ALS/pixels'/f"{view['camera']}.npz")['max_gaussian'];assert np.array_equal(a['max_gaussian'],mx[yy,xx]) and flags[a['max_gaussian']].all();C=np.linalg.inv(np.asarray(view['W2C']));K=np.asarray(view['K']);rays=np.c_[(xx-K[0,2])/K[0,0],(yy-K[1,2])/K[1,1],np.ones(len(xx))]@C[:3,:3].T
  for i,ray in enumerate(rays):
   den=n@ray;ok=abs(den)>1e-12;inds=np.flatnonzero(ok);d=np.sum((hits[inds]-C[:3,3])*n[inds],axis=1)/den[inds];ok=(d>0)&(abs(d-float(depth[i]))<=.25);inds=inds[ok];d=d[ok];delta=C[:3,3]+d[:,None]*ray-hits[inds];inside=(abs(np.sum(delta*u[inds],axis=1))<=.125+1e-9)&(abs(np.sum(delta*v[inds],axis=1))<=.125+1e-9);got=bool(inside.any());assert got==bool(a['floating_footprint'][i]),(view['camera'],i);checked+=1;matches+=int(got)
   if got:gaussians.add(int(a['max_gaussian'][i]))
 summary=json.loads((root/'full_pixel_enumeration/summary.json').read_text());print('VERIFY_COUNTS',checked,matches,len(gaussians),'AREA',np.unique(e['area'][floating],return_counts=True),flush=True);assert checked==summary['all_candidate_max_pixels'] and matches==summary['floating_footprint_pixels'] and len(gaussians)==summary['would_release_and_float_max_unique_gaussians'];assert np.allclose(e['area'][floating],.0625,rtol=0,atol=1e-8)
 cross=json.loads((root/'floating_cross.json').read_text())['rows'];checks=[]
 for rev in ['r6','r7']:
  p=OUT/rev/'runs'/f'tg_B173nb_b10_ALS_s0_{rev}/post7000/patch_z.npz';zz=load(p);eligible=e['in_eval']&e['scoring_allowed']
  for scope,sel in [('all',eligible),('cells_0_3',eligible&(zz['cell']>=0)&(zz['cell']<=3))]:
   expected=float(e['area'][sel&(zz['category']==1)].sum());actual=sum(r['floating_area_m2'] for r in cross if r['revision']==rev and r['scope']==scope);assert abs(expected-actual)<1e-6;checks.append(dict(revision=rev,scope=scope,area_m2=actual))
 result=dict(status='PASS',at=stamp(),bruteforce_nearest_targets=len(test),all_candidate_pixels_bruteforce_checked=checked,floating_pixels=matches,unique_gaussians=len(gaussians),patch_square_area_verified_m2=.0625,area_conservation=checks,scientific_verdict=None);dump(root/'verification.json',result);dump(DOC/'tables/continue_r7_ALS_diagnostic_verification.json',result);print('ALS_DIAGNOSTIC_VERIFIED',result,flush=True)
if __name__=='__main__':main()
