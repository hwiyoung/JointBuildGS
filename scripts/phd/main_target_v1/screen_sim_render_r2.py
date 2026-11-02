"""Saved-model forward-only screen-pruning simulation and contribution accounting."""
import os,sys,time,gc,importlib.util,math
sys.path.insert(0,'/source');os.environ['MAX_JOBS']='2'
from argparse import ArgumentParser
import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.cpp_extension import load
import diff_surfel_rasterization as raster
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from utils.loss_utils import create_window
from common import *
ROOT=OUT/'screen_sim'
class Observer:
 def __init__(self,module,account_module,n):
  self.original=module;self.module=account_module;self.n=n;self.account=False;self.last=None
 def __getattr__(self,k):return getattr(self.original,k)
 def rasterize_gaussians(self,*args):
  out=self.original.rasterize_gaussians(*args);N=int(args[1].shape[0]);H,W=int(args[12]),int(args[13]);record=dict(overlaps=int(out[0]),binning_bytes=out[5].numel())
  if self.account:
   geom,binning,im=out[4:7];off=0;fields={}
   for name,size,dim,dt in [('depth',4,1,torch.float32),('clamped',3,3,None),('radius',4,1,torch.int32),('xy',8,2,torch.float32),('mat',36,9,torch.float32),('no',16,4,torch.float32),('color',12,3,torch.float32)]:
    off=(off+127)//128*128
    if dt is not None:fields[name]=geom[off:off+N*size].view(dt).reshape(N,dim)
    off+=N*size
   off=0
   for size in [12,8]:off=(off+127)//128*128+H*W*size
   off=(off+127)//128*128;ranges=im[off:off+H*W*8].view(torch.int32).reshape(-1,2);ids=binning[:int(out[0])*4].view(torch.int32)
   replay=self.module.weights(ranges,ids,fields['xy'],fields['mat'],fields['no'],fields['color'],self.roi,self.sum,self.roi_sum,self.maximum,W,H)
   rgb_error=float((replay[:3]-out[1]).abs().max());alpha_error=float((replay[3]-out[2][1]).abs().max());assert max(rgb_error,alpha_error)<=self.tolerance,('RENDER_ACCOUNTING_PARITY',rgb_error,alpha_error)
   record.update(account_rgb_max_abs=rgb_error,account_alpha_max_abs=alpha_error)
  self.last=record;return out
def quality(pred,gt,roi):
 p=pred.clamp(0,1);diff=(p-gt).square();window=create_window(11,3).to(p.device);a,b=p[None],gt[None];ma=F.conv2d(a,window,padding=5,groups=3);mb=F.conv2d(b,window,padding=5,groups=3);va=F.conv2d(a*a,window,padding=5,groups=3)-ma*ma;vb=F.conv2d(b*b,window,padding=5,groups=3)-mb*mb;co=F.conv2d(a*b,window,padding=5,groups=3)-ma*mb;sm=(((2*ma*mb+.01**2)*(2*co+.03**2))/((ma*ma+mb*mb+.01**2)*(va+vb+.03**2))).squeeze(0).mean(0)
 def values(mask):
  n=int(mask.sum());m=float(diff[:,mask].double().mean()) if n else None
  return dict(pixels=n,mse=m,psnr=-10*math.log10(m) if m is not None and m>0 else None,perfect=m==0 if m is not None else None,ssim=float(sm[mask].double().mean()) if n else None)
 return dict(all=values(torch.ones_like(roi)),roi=values(roi))
def subset(g,mask):
 h=GaussianModel(g.max_sh_degree);h.active_sh_degree=g.active_sh_degree
 for name in ['_xyz','_features_dc','_features_rest','_opacity','_scaling','_rotation']:setattr(h,name,torch.nn.Parameter(getattr(g,name)[mask].detach(),requires_grad=False))
 return h
@torch.no_grad()
def main():
 key=sys.argv[1];c=json.loads((CFG/'screen_sim.json').read_text());assert sha(CFG/'screen_sim.json')==json.loads((CFG/'screen_sim.lock.json').read_text())['config_sha256'];lock=json.loads((CFG/'screen_sim_render_r2.lock.json').read_text())
 for p,h in lock['files'].items():assert sha(p)==h,p
 row=next(r for r in c['states'] if r['key']==key);assert row['available'];dest=ROOT/'states'/key;dest.mkdir(parents=True,exist_ok=False);start=time.monotonic();inp=json.loads((ROOT/'inputs/index.json').read_text());meta={r['camera']:r for r in inp['views']};fixed=set(inp['fixed_views'])
 build=dest/'account_build';build.mkdir();module=load(name='screen_sim_weights',sources=[str(Path(__file__).with_name('screen_sim_weights.cu'))],extra_cuda_cflags=['-O3'],extra_cflags=['-O3'],build_directory=str(build),verbose=True)
 parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser);args=parser.parse_args(['-s','/scene','-m',row['model'],'--eval','-r','1','--data_device','cpu','--sparse_dir_name','sparse_lod']);safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=row['scene_iteration'],shuffle=False);g.load_ply(row['ply']);pipe=pp.extract(args);assert not pipe.convert_SHs_python and not pipe.compute_cov3D_python
 cams=sorted(scene.getTrainCameras(),key=lambda x:x.image_name);assert [v.image_name for v in cams]==c['views'];bg=torch.zeros(3,device='cuda');N=len(g._xyz);observer=Observer(raster._C,module,N);raster._C=observer;observer.tolerance=c['contribution']['parity_max_abs'];observer.sum=torch.zeros(N,dtype=torch.float64,device='cuda');observer.roi_sum=torch.zeros_like(observer.sum);observer.maximum=torch.zeros(N,device='cuda');maxrad=np.zeros(N,'i4');argmax=np.full(N,-1,'i2');maxrelative=np.zeros(N,'f4');radiusdir=dest/'radii';radiusdir.mkdir();summaries={};denom=0.;roi_denom=0.;all_width=[];masks={}
 for variant in ['before']+[v['key'] for v in c['candidates']]:
  vd=dest/variant;vd.mkdir();renders=vd/'renders';renders.mkdir();observer.account=variant=='before'
  if variant=='before':h=g;selected=0
  else:
   mask=masks[variant];h=subset(g,torch.as_tensor(~mask,device='cuda'));selected=int(mask.sum())
  records=[]
  for i,cam in enumerate(cams):
   m=meta[cam.image_name];H,W=cam.image_height,cam.image_width;assert (H,W)==(m['height'],m['width']);assert np.allclose(cam.world_view_transform.T.cpu().numpy(),m['W2C'],atol=2e-5)
   with np.load(ROOT/'inputs'/(cam.image_name+'.npz')) as a:roi=torch.as_tensor(a['roi'],device='cuda')
   observer.roi=roi;torch.cuda.reset_peak_memory_stats();ts=time.monotonic();pkg=render(cam,h,pipe,bg);torch.cuda.synchronize();record=observer.last.copy();record.update(camera=cam.image_name,width=W,height=H,quality=quality(pkg['render'],cam.original_image[:3].cuda(),roi),gaussians=len(h._xyz),removed=selected,seconds=time.monotonic()-ts,peak_allocated_bytes=torch.cuda.max_memory_allocated())
   depth=pkg['surf_depth'].squeeze().cpu().numpy();rgb=(pkg['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype('u1');np.savez_compressed(renders/(cam.image_name+'.npz'),depth=depth,rgb=rgb)
   if cam.image_name in fixed:np.savez_compressed(vd/(cam.image_name+'_float.npz'),rgb=pkg['render'].clamp(0,1).cpu().numpy(),gt=cam.original_image[:3].cpu().numpy(),alpha=pkg['rend_alpha'].squeeze().cpu().numpy())
   if variant=='before':
    radii=pkg['radii'].cpu().numpy();assert np.all(radii>=0);take=radii>maxrad;maxrad[take]=radii[take];argmax[take]=i;maxrelative=np.maximum(maxrelative,radii.astype('f4')/W);np.savez_compressed(radiusdir/(cam.image_name+'.npz'),radius=radii);denom+=float(pkg['rend_alpha'].double().sum());roi_denom+=float(pkg['rend_alpha'].squeeze()[roi].double().sum());all_width.append(W)
   records.append(record);dump(vd/'progress.json',dict(at=stamp(),completed=i+1,views=203,last=record,scientific_verdict=None))
   if i%20==0:print('SIM_RENDER',key,variant,i+1,203,record['overlaps'],flush=True)
   del pkg,roi,depth,rgb;gc.collect()
  if variant=='before':
   sums=observer.sum.cpu().numpy();roi_sums=observer.roi_sum.cpu().numpy();maximum=observer.maximum.cpu().numpy();relative_error=abs(sums.sum()-denom)/max(denom,1);roi_error=abs(roi_sums.sum()-roi_denom)/max(roi_denom,1);assert max(relative_error,roi_error)<=c['contribution']['aggregate_relative_tolerance'],(relative_error,roi_error)
   for candidate in c['candidates']:masks[candidate['key']]=maxrad>candidate['value'] if candidate['mode']=='pixels' else maxrelative>candidate['value'];np.save(dest/(candidate['key']+'_remove.npy'),masks[candidate['key']])
   np.savez_compressed(dest/'gaussians.npz',xyz=g._xyz.cpu().numpy(),max_radius=maxrad,max_radius_view=argmax,max_radius_over_width=maxrelative,total_contribution=sums,roi_contribution=roi_sums,max_contribution=maximum)
   dump(dest/'contribution.json',dict(all203=True,all_gaussians=True,sum_w=float(sums.sum()),render_alpha_sum=denom,roi_sum_w=float(roi_sums.sum()),render_roi_alpha_sum=roi_denom,relative_error=relative_error,roi_relative_error=roi_error,widths=sorted(set(all_width)),extension_sha256=sha(observer.original.__file__),account_module_sha256=sha(build/'screen_sim_weights.so'),scientific_verdict=None));del observer.sum,observer.roi_sum,observer.maximum;torch.cuda.empty_cache()
  summaries[variant]=dict(at=stamp(),views=records,selected=selected,remaining=N-selected,scientific_verdict=None);dump(vd/'summary.json',summaries[variant]);del h;torch.cuda.empty_cache()
 dump(dest/'receipt.json',dict(at=stamp(),status='PASS_FORWARD_ONLY',row=row,gaussians=N,variants=list(summaries),seconds=time.monotonic()-start,model_sha256=sha(row['ply']),fixed_views=inp['fixed_views'],optimization_steps=0,backward_calls=0,scientific_verdict=None));print('SIM_STATE_COMPLETE',key,flush=True)
if __name__=='__main__':main()
