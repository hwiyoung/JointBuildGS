"""Read-only r6/r7 ALS counterfactual and floating-area cross-tab, frozen definitions."""
import sys,difflib
import numpy as np
from scipy.spatial import cKDTree
from common import *
def load(p):
 with np.load(p) as z:return dict(z)
def main():
 c=json.loads((CFG/'scoring_continue_r7.json').read_text());assert sha(CFG/'scoring_continue_r7.json')==json.loads((CFG/'scoring_continue_r7.lock.json').read_text())['config_sha256']
 root=OUT/'r7_continue/diagnostics/ALS';root.mkdir(parents=True,exist_ok=False);site='B173nb_b10';prior='ALS'
 ev=load(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2/B173nb_b10__ALS/evaluation.npz');tables=[];sources={};snapshots={};targets={}
 for rev in ['r6','r7']:
  run=OUT/rev/'runs'/f'tg_{site}_{prior}_s0_{rev}';snapp=run/'model/target_monitor/snapshot_7000.npz';s=load(snapp);snapshots[rev]=s
  tp=OUT/('r7' if rev=='r7' else 'r2')/'targets'/f'{site}_{prior}.npz';t=load(tp);targets[rev]=t;z=load(run/'post7000/patch_z.npz');a=load(run/'post7000/origin_attribution.npz');sources[rev]=dict(snapshot_sha256=sha(snapp),target_sha256=sha(tp),origin_sha256=sha(run/'post7000/origin_attribution.npz'))
  dom=np.full(len(ev['area']),4,np.int8);has=a['views']>0;largest=np.argmax(np.nan_to_num(a['mean_fraction'],nan=-1),axis=1);mx=np.nan_to_num(a['mean_fraction'],nan=-1).max(1);dom[has]=3;dom[has&(mx>=.5)]=largest[has&(mx>=.5)]
  half=1.96*t['sigma'];width=np.select([half<.1,half<.5,half<=1,half>1],[0,1,2,3],default=4);width[~np.isfinite(t['target']).all(1)|(t['region']==5)]=4
  eligible=ev['in_eval']&ev['scoring_allowed'];floatmask=eligible&(z['category']==1)
  for scope,eligible_scope in [('all',eligible),('cells_0_3',eligible&(z['cell']>=0)&(z['cell']<=3))]:
   for origin in range(5):
    for region in sorted(np.unique(t['region'][eligible_scope]).tolist()):
     for w in range(5):
      m=eligible_scope&(dom==origin)&(t['region']==region)&(width==w);fm=m&(z['category']==1)
      tables.append(dict(revision=rev,scope=scope,origin=['background','released','patch','mixed','unavailable'][origin],region=int(region),halfwidth_bin=['<0.1','0.1~0.5','0.5~1','>1','unavailable'][w],patches=int(m.sum()),area_m2=float(ev['area'][m].sum()),floating_patches=int(fm.sum()),floating_area_m2=float(ev['area'][fm].sum())))
   assert abs(sum(r['floating_area_m2'] for r in tables if r['revision']==rev and r['scope']==scope)-ev['area'][floatmask&eligible_scope].sum())<1e-6
  np.savez_compressed(root/f'{rev}_floating_cross.npz',dominance=dom,width_bin=width,region=t['region'],floating=floatmask,area=ev['area'],centre=ev['centre'])
 dump(root/'floating_cross.json',dict(at=stamp(),definition=c['als_diagnostic'],rows=tables,sources=sources,scientific_verdict=None))
 s=snapshots['r7'];patch=np.flatnonzero(s['target_tag']==1);counter={};flags={}
 for label,t in [('r7_targets',targets['r7']),('r6_targets_reference',targets['r6'])]:
  valid=(t['region']>=0)&np.isfinite(t['target']).all(1)&np.isfinite(t['normal']).all(1)&np.isfinite(t['sigma'])&(t['sigma']>0)
  d,idx=cKDTree(t['target'][valid].astype('f8')).query(s['xyz'][patch].astype('f8'),workers=2);f=np.zeros(len(s['xyz']),bool);f[patch[d>.5]]=True;flags[label]=f
  counter[label]=dict(current_patch_gaussians=len(patch),would_release=int(f.sum()),valid_targets=int(valid.sum()),distance_quantiles_m=np.quantile(d,[0,.5,.9,.99,1]).tolist())
 run=OUT/'r7/runs/tg_B173nb_b10_ALS_s0_r7';z=load(run/'post7000/patch_z.npz');ids=np.flatnonzero(ev['in_eval']&ev['scoring_allowed']&(z['category']==1));hits=ev['centre'][ids]+z['z'][ids,None]*ev['normal'][ids];cover=json.loads((run/'model/check7000/coverage.json').read_text());seen={k:np.zeros(len(s['xyz']),bool) for k in flags};views=[]
 for vi,v in enumerate(cover['views']):
  a=load(run/'model/check7000/renders'/f"{v['camera']}.npz");M=np.asarray(v['W2C']);K=np.asarray(v['K']);q=hits@M[:3,:3].T+M[:3,3];q=q[q[:,2]>0];u=np.rint(K[0,0]*q[:,0]/q[:,2]+K[0,2]).astype(int);w=np.rint(K[1,1]*q[:,1]/q[:,2]+K[1,2]).astype(int);h,ww=a['depth'].shape;ok=(u>=0)&(w>=0)&(u<ww)&(w<h);u,w,q=u[ok],w[ok],q[ok];ok=np.isfinite(a['depth'][w,u])&(a['depth'][w,u]>0)&(abs(a['depth'][w,u]-q[:,2])<=.25)&(a['alpha'][w,u]>1e-5);pix=np.unique(w[ok]*ww+u[ok]);p=OUT/'r7/failures/ALS/pixels'/f"{v['camera']}.npz";mx=load(p)['max_gaussian'].reshape(-1)[pix];good=mx>=0;assert (mx[good]<len(s['xyz'])).all();row=dict(camera=v['camera'],floating_pixels=len(pix),missing_max=int((~good).sum()))
  for k,f in flags.items():
   selected=mx[good][f[mx[good]]];seen[k][selected]=True;row[k+'_pixels']=len(selected)
  views.append(row)
  if vi%40==0:print('FLOAT_COUNTERFACTUAL',vi+1,len(cover['views']),flush=True)
 for k in counter:counter[k].update(would_release_and_float_max_unique_gaussians=int(seen[k].sum()),float_max_pixel_observations=sum(r[k+'_pixels'] for r in views))
 np.savez_compressed(root/'counterfactual_gaussians.npz',**flags,**{k+'_float_max':v for k,v in seen.items()})
 dump(root/'counterfactual.json',dict(at=stamp(),rows=counter,views=views,floating_pixels=sum(r['floating_pixels'] for r in views),definition=c['als_diagnostic']['floating_pixels'],scientific_verdict=None))
 # Exact source difference inventory; no new model execution for this diagnostic.
 dirs=[REPO/'src/phd/forks'/f'GeoGS-conf-guided-v1-r{i}' for i in [20,21]];files={p.relative_to(d) for d in dirs for p in d.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc']};diff=[];patches=[]
 for rel in sorted(files):
  pp=[d/rel for d in dirs];hh=[sha(p) if p.exists() else None for p in pp]
  if hh[0]==hh[1]:continue
  diff.append(dict(path=str(rel),r6_sha256=hh[0],r7_sha256=hh[1]))
  if rel.suffix in ['.py','.json','.txt','.md','.cu','.h','.cpp']:
   patches.extend(difflib.unified_diff(pp[0].read_text(errors='replace').splitlines(True) if pp[0].exists() else [],pp[1].read_text(errors='replace').splitlines(True) if pp[1].exists() else [],fromfile='r20/'+str(rel),tofile='r21/'+str(rel)))
 (root/'source_changes.diff').write_text(''.join(patches));configs={}
 for name in ['target_v1.r6.json','target_v1.r7.json','target_v1.r7.stage0.json']:
  p=CFG/name;configs[name]=dict(sha256=sha(p),value=json.loads(p.read_text()))
 seeds={};curves={}
 for rev in ['r6','r7']:
  sr=OUT/('r7' if rev=='r7' else 'r2')/'stage1/B173nb_b10_ALS/seeds.npz';x=load(sr);seeds[rev]=dict(path=str(sr),sha256=sha(sr),arrays={k:dict(shape=list(v.shape),sha256=__import__('hashlib').sha256(v.tobytes()).hexdigest()) for k,v in x.items()})
  rr=OUT/rev/'runs'/f'tg_B173nb_b10_ALS_s0_{rev}';curve=[json.loads(line) for line in (rr/'model/target_monitor/curve.jsonl').read_text().splitlines()];curves[rev]=[dict(iteration=r['iteration'],camera=r['camera']) for r in curve if r['iteration']<=7000]
  configs[rev+'_command']=json.loads((rr/'command.json').read_text())
 dump(root/'source_differences.json',dict(at=stamp(),files=diff,configs=configs,seeds=seeds,logged_camera_order=curves,full_training_camera_order='only saved RNG/remaining stack and every-100-step camera records available; full per-iteration sequence was not logged',same_seed_full_rerun='NOT_PERFORMED_UNAVAILABLE; fixed seed alone is not byte determinism evidence',scientific_verdict=None))
 print('ALS_DIAGNOSTIC_DONE',counter,flush=True)
if __name__=='__main__':main()
