"""Enumerate every max-contributor pixel of counterfactual candidates against floating patch footprints."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from common import *
from diagnose_als_continue_r7 import load

def main():
 cfgp=CFG/'counterfactual_pixels_continue_r7.r1.json';cfg=json.loads(cfgp.read_text());assert sha(cfgp)==json.loads((CFG/'counterfactual_pixels_continue_r7.r1.lock.json').read_text())['sha256'];root=OUT/'r7_continue/diagnostics/ALS';dest=root/'full_pixel_enumeration_r1';dest.mkdir(exist_ok=False);flags=load(root/'counterfactual_gaussians.npz')['r7_targets'];run=OUT/'r7/runs/tg_B173nb_b10_ALS_s0_r7';s=load(run/'model/target_monitor/snapshot_7000.npz');assert len(flags)==len(s['xyz']);e=load(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2/B173nb_b10__ALS/evaluation.npz');z=load(run/'post7000/patch_z.npz');elig=e['in_eval']&e['scoring_allowed']&(z['category']==1);ids=np.flatnonzero(elig);hits=e['centre'][ids]+z['z'][ids,None]*e['normal'][ids];nn=e['normal'][ids].astype(float);nn/=np.linalg.norm(nn,axis=1)[:,None];st=load(S0/'fork_inputs/s61/B173nb_b10/store_ALS.npz');assert np.array_equal(st['loc_center'],e['centre']) and not st['loc_extra'][ids].any();t1=st['loc_t1'][ids];t2=st['loc_t2'][ids];assert np.allclose(np.linalg.norm(np.cross(t1,t2),axis=1)*.0625,e['area'][ids],rtol=0,atol=1e-10);dual=np.linalg.pinv(np.stack([t1,t2],axis=2));u=dual[:,0,:];v=dual[:,1,:];corner_radius=.125*np.maximum(np.linalg.norm(t1+t2,axis=1),np.linalg.norm(t1-t2,axis=1)).max();tree=cKDTree(hits);cover=json.loads((run/'model/check7000/coverage.json').read_text());seen=np.zeros(len(flags),bool);views=[];allpixels=matched=0
 for vi,view in enumerate(cover['views']):
  name=view['camera'];a=load(run/'model/check7000/renders'/f'{name}.npz');g=load(OUT/'r7/failures/ALS/pixels'/f'{name}.npz')['max_gaussian'];valid=(g>=0)&np.isfinite(a['depth'])&(a['depth']>0)&(a['alpha']>1e-5);candidate=valid&flags[np.maximum(g,0)];yy,xx=np.nonzero(candidate);depth=a['depth'][yy,xx].astype(float);K=np.asarray(view['K']);C=np.linalg.inv(np.asarray(view['W2C']));rays=np.stack([(xx-K[0,2])/K[0,0],(yy-K[1,2])/K[1,1],np.ones(len(xx))],1)@C[:3,:3].T;world=C[:3,3]+depth[:,None]*rays;radius=.25*np.linalg.norm(rays,axis=1)+corner_radius+1e-9;candidates=tree.query_ball_point(world,radius,workers=2);matches=np.zeros(len(xx),bool)
  for i,js in enumerate(candidates):
   if not js:continue
   js=np.asarray(js);den=nn[js]@rays[i];ok=abs(den)>1e-12;js=js[ok];den=den[ok]
   if not len(js):continue
   d=np.sum((hits[js]-C[:3,3])*nn[js],axis=1)/den;ok=(d>0)&(abs(d-depth[i])<=.25);js=js[ok];d=d[ok]
   if not len(js):continue
   delta=C[:3,3]+d[:,None]*rays[i]-hits[js];inside=(abs(np.sum(delta*u[js],axis=1))<=.125+1e-9)&(abs(np.sum(delta*v[js],axis=1))<=.125+1e-9);matches[i]=bool(inside.any())
  gauss=g[yy[matches],xx[matches]];seen[gauss]=True;allpixels+=len(xx);matched+=int(matches.sum());views.append(dict(camera=name,candidate_max_pixels=len(xx),floating_footprint_pixels=int(matches.sum()),outside_measured_floating_footprints=int((~matches).sum()),unique_gaussians=len(np.unique(gauss))));np.savez_compressed(dest/f'{name}.npz',y=yy,x=xx,max_gaussian=g[yy,xx],floating_footprint=matches)
  if vi%40==0:print('FULL_COUNTERFACTUAL_PIXELS',vi+1,203,len(xx),int(matches.sum()),flush=True)
 result=dict(at=stamp(),status='PASS_EXHAUSTIVE_CANDIDATE_PIXEL_ENUMERATION',candidate_gaussians=int(flags.sum()),all_candidate_max_pixels=allpixels,floating_footprint_pixels=matched,would_release_and_float_max_unique_gaussians=int(seen.sum()),gaussian_ids=np.flatnonzero(seen).tolist(),views=views,definition=cfg,limitation='Whole pixel enumeration for the 47 candidate IDs, within the measured floating footprints from the inherited store tangents. Pixels outside those footprints are not assigned a GT floating label.',scientific_verdict=None);dump(dest/'summary.json',result);print('FULL_PIXEL_ENUMERATION_DONE',int(seen.sum()),matched,allpixels,flush=True)
if __name__=='__main__':main()
