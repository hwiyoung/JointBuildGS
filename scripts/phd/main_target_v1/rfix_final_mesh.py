"""Reuses unchanged screen-simulation TSDF and AXES71-v2 scorer at the locked endpoint."""
import sys,json,time
from pathlib import Path
import numpy as np
sys.path.insert(0,'/repo/scripts/phd/main_meshpatch_v1')
from mesh_common import dump,sha,now
import screen_sim_mesh as S
ROOT=Path('/target/rfix_continue/final_endpoint');KEY='r8_LoD2_rfix';VAR='current'
def prep():
 cfg=json.loads(Path('/cfg/rfix_final.json').read_text());idx=json.loads(Path('/target/screen_sim/inputs/index.json').read_text());dst=ROOT/'meshes'/KEY/VAR/'inputs';dst.mkdir(parents=True,exist_ok=False);views=idx['views'];box=np.asarray(idx['mesh_box'],'f4');H,W=views[0]['height'],views[0]['width'];n=len(views)
 depth=np.lib.format.open_memmap(dst/'depth_masked.npy','w+',dtype='f4',shape=(n,H,W));rgb=np.lib.format.open_memmap(dst/'rgb.npy','w+',dtype='u1',shape=(n,H,W,3));yy,xx=np.mgrid[:H,:W].astype('f4');counts=[];intr=[];extr=[];bindings={}
 for i,v in enumerate(views):
  p=ROOT/'states'/KEY/VAR/'renders'/(v['camera']+'.npz');bindings[str(p)]=sha(p);a=np.load(p);d=a['depth'];K=np.asarray(v['K'],'f4');M=np.asarray(v['W2C'],'f4');iv=np.linalg.inv(M).astype('f4');cam=np.stack([(xx-K[0,2])/K[0,0]*d,(yy-K[1,2])/K[1,1]*d,d,np.ones_like(d)],-1);world=(cam.reshape(-1,4)@iv.T)[:,:3].reshape(H,W,3);valid=np.isfinite(d)&(d>0);inside=((world>=box[0])&(world<=box[1])).all(-1)&valid;depth[i]=np.where(inside,d,0);rgb[i]=a['rgb'];counts.append([float(inside.mean()),float(valid.mean())]);intr.append([K[0,0],K[1,1],K[0,2],K[1,2]]);extr.append(M)
 depth.flush();rgb.flush();np.savez(dst/'cams.npz',names=[v['camera'] for v in views],intr=intr,wh=[[W,H]]*n,extrinsic=extr)
 dump(dst/'meta.json',dict(site='B173nb_b10',result=KEY,prior_scene='LoD2',depth_dir=str(ROOT/'states'/KEY/VAR/'renders'),box=idx['mesh_box'],height=H,width=W,views=n,views_without_depth=[],mean_share_of_pixels_in_box=float(np.mean(counts,axis=0)[0]),mean_share_of_pixels_with_depth=float(np.mean(counts,axis=0)[1]),seconds=None,scientific_verdict=None));dump(dst/'binding.json',dict(at=now(),inputs=bindings,scientific_verdict=None))
def target_score():
 root=ROOT/'scores'/KEY/VAR/'LoD2';z=dict(np.load(root/'patch_z.npz'));ph=Path('/ph');e=dict(np.load(ph/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2/B173nb_b10__LoD2/evaluation.npz'));t=dict(np.load('/target/r7/targets/B173nb_b10_LoD2.npz'));eligible=e['in_eval']&e['scoring_allowed'];cat=z['category'];rows=[]
 for label,mask in [('all',eligible),('original',eligible&~t['any_replaced']),('replaced',eligible&t['any_replaced'])]:
  for region in [0,5,1,2,3]:
   s=mask&(t['region']==region);area=float(e['area'][s].sum());rows.append(dict(replacement=label,region=region,patches=int(s.sum()),area_m2=area,result_within_tau_fraction=float(e['area'][s&(cat==0)].sum()/area) if area else None,target_within_tau_fraction=float(e['area'][s&(abs(t['h']-e['p_gt'])<=e['tau'])].sum()/area) if area and region!=5 else None,floating_fraction=float(e['area'][s&(cat==1)].sum()/area) if area else None,no_surface_fraction=float(e['area'][s&z['no_surface']].sum()/area) if area else None))
 dump(root/'result_vs_target.json',dict(at=now(),rows=rows,scientific_verdict=None))
def main():
 inherited=json.loads(Path('/cfg/screen_sim_mesh.lock.json').read_text())
 for p,h in inherited['files'].items():assert sha(p)==h,p
 mode=sys.argv[1];wd=ROOT/'meshes'/KEY/VAR;S.ROOT=ROOT
 if mode=='prep':prep()
 elif mode=='score':S.score(KEY,VAR,'LoD2');target_score()
 else:
  from src.phd import streamed_tsdf as T
  if mode=='plan':T.plan(wd,'auto:16');T.order(wd)
  elif mode=='tile':T.tile(wd,int(sys.argv[2]))
  elif mode=='merge':T.merge(wd,wd/'merged.ply',wd/'merged.json')
  else:raise ValueError(mode)
if __name__=='__main__':main()
