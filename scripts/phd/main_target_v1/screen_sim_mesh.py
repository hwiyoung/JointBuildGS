"""Read-only saved render -> unchanged current TSDF -> unchanged AXES71-v2."""
import sys,json,time,gc
from pathlib import Path
import numpy as np
sys.path.insert(0,'/repo/scripts/phd/main_meshpatch_v1')
from mesh_common import dump,sha,now
ROOT=Path('/target/screen_sim'); C=Path('/cfg')
def prep(key,variant):
 t=time.time();wd=ROOT/'meshes'/key/variant;dst=wd/'inputs';dst.mkdir(parents=True,exist_ok=True)
 idx=json.loads((ROOT/'inputs/index.json').read_text());cfg=json.loads((C/'screen_sim.json').read_text());row=next(r for r in cfg['states'] if r['key']==key);views=idx['views'];box=np.asarray(idx['mesh_box'],np.float32)
 H,W=views[0]['height'],views[0]['width'];n=len(views)
 depth=np.lib.format.open_memmap(dst/'depth_masked.npy','w+',dtype='f4',shape=(n,H,W));rgb=np.lib.format.open_memmap(dst/'rgb.npy','w+',dtype='u1',shape=(n,H,W,3));yy,xx=np.mgrid[:H,:W].astype(np.float32);counts=[];intr=[];extr=[];bindings={}
 for i,v in enumerate(views):
  p=ROOT/'states'/key/variant/'renders'/(v['camera']+'.npz');bindings[str(p)]=sha(p);a=np.load(p);d=a['depth'];K=np.asarray(v['K'],np.float32);M=np.asarray(v['W2C'],np.float32);iv=np.linalg.inv(M).astype(np.float32)
  cam=np.stack([(xx-K[0,2])/K[0,0]*d,(yy-K[1,2])/K[1,1]*d,d,np.ones_like(d)],-1);world=(cam.reshape(-1,4)@iv.T)[:,:3].reshape(H,W,3)
  valid=np.isfinite(d)&(d>0);inside=((world>=box[0])&(world<=box[1])).all(-1)&valid;depth[i]=np.where(inside,d,0);rgb[i]=a['rgb'];counts.append([float(inside.mean()),float(valid.mean())]);intr.append([K[0,0],K[1,1],K[0,2],K[1,2]]);extr.append(M)
 depth.flush();rgb.flush();np.savez(dst/'cams.npz',names=[v['camera'] for v in views],intr=intr,wh=[[W,H]]*n,extrinsic=extr)
 dump(dst/'meta.json',dict(site='B173nb_b10',result=key+'_'+variant,prior_scene=row['prior'],depth_dir=str(ROOT/'states'/key/variant/'renders'),box=idx['mesh_box'],height=H,width=W,views=n,views_without_depth=[],mean_share_of_pixels_in_box=float(np.mean(counts,axis=0)[0]),mean_share_of_pixels_with_depth=float(np.mean(counts,axis=0)[1]),seconds=time.time()-t,scientific_verdict=None))
 dump(dst/'binding.json',dict(at=now(),config_sha256=sha(C/'screen_sim.json'),inputs=bindings,depth_sha256=sha(dst/'depth_masked.npy'),rgb_sha256=sha(dst/'rgb.npy'),cams_sha256=sha(dst/'cams.npz'),scientific_verdict=None));print('SIM_PREP',key,variant,flush=True)
def score(key,variant,prior):
 sys.path.insert(0,'/repo/scripts/phd/main_meshpatch_v1')
 from axes_adapter import ax,aa,inputs,distances
 import mesh_worker as MW,mesh_common as MC
 import open3d as o3d
 t=time.time();root=ROOT/'scores'/key/variant/prior;root.mkdir(parents=True,exist_ok=True);mesh=ROOT/'meshes'/key/variant/'merged.ply';ctx=inputs('B173nb_b10',prior);ident=key+'_'+variant
 print('SIM_SCORE_DIST',key,variant,prior,flush=True);paths=distances('B173nb_b10',prior,ident,mesh,root/'dist',ctx);A=aa.arrays('B173nb_b10',prior,ident,ctx['cells'],paths=paths);blocks={}
 for cell in ['all']+ax.KEYS:
  g=A['scene'] if cell=='all' else aa.sel(A['rows'],aa.cell_sel(A['rows']['cell'],cell,ax.SUMS));s=A['smp'] if cell=='all' else aa.sel(A['smp'],aa.cell_sel(A['smp']['cell'],cell,ax.SUMS));gb=aa.gt_block(g,with05=cell=='all');rb=aa.res_block(s,place=cell!='all',with05=cell=='all');blocks[cell]=dict(gt=gb,res=rb,both=aa.combine(gb,rb))
 del A;gc.collect();e=ctx['ev'];v=dict(np.load(ax.PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'B173nb_b10__{prior}/values.npz'));m=o3d.io.read_triangle_mesh(str(mesh));z=MW.first_hit(m,e,v);cat=MC.classes(e,z);np.savez_compressed(root/'patch_z.npz',**z,category=cat,gt_cell=ctx['cells']['cell']);areas={}
 for cell in ['all']+ax.KEYS:
  scope=np.ones(len(e['area']),bool) if cell=='all' else aa.cell_sel(ctx['cells']['cell'],cell,ax.SUMS);sel=scope&e['in_eval']&e['scoring_allowed'];area=float(e['area'][sel].sum());fa=float(e['area'][sel&(cat==1)].sum());na=float(e['area'][sel&z['no_surface']].sum());areas[cell]=dict(area_m2=area,unscorable_area_m2=float(e['area'][scope&e['in_eval']&~e['scoring_allowed']].sum()),patches=int(sel.sum()),floating_area_m2=fa,no_surface_area_m2=na,floating_fraction=fa/area if area else None,no_surface_fraction=na/area if area else None)
 dump(root/'values.json',dict(status='PASS',at=now(),state=key,variant=variant,prior=prior,mesh_sha256=sha(mesh),metrics=blocks,surface=areas,seconds=time.time()-t,scientific_verdict=None));print('SIM_SCORE_DONE',key,variant,prior,flush=True)
def main():
 lock=json.loads((C/'screen_sim_mesh.lock.json').read_text())
 for p,h in lock['files'].items():assert sha(p)==h,p
 mode,key,variant=sys.argv[1:4];wd=ROOT/'meshes'/key/variant
 if mode=='prep':prep(key,variant)
 elif mode=='score':score(key,variant,sys.argv[4])
 else:
  from src.phd import streamed_tsdf as T
  if mode=='plan':T.plan(wd,'auto:16');T.order(wd)
  elif mode=='tile':T.tile(wd,int(sys.argv[4]))
  elif mode=='merge':T.merge(wd,wd/'merged.ply',wd/'merged.json')
  else:raise ValueError(mode)
if __name__=='__main__':main()
