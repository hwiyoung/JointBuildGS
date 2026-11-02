"""Read-only original forward; export existing tile/geometry buffers, no kernel edits."""
import sys
sys.path.insert(0,'/source')
from argparse import ArgumentParser
import numpy as np
import torch
import diff_surfel_rasterization as raster
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from common import *
ROOT=OUT/'r8_screen_prune';H=OUT/'r8_recorded_continue/heavy'
class Observer:
 def __init__(self,original,selected,pixels):self.original=original;self.selected=selected;self.pixels=pixels
 def __getattr__(self,n):return getattr(self.original,n)
 def rasterize_gaussians(self,*args):
  out=self.original.rasterize_gaussians(*args);n=int(args[1].shape[0]);geom=out[4];binning=out[5];im=out[6];R=int(out[0]);height,width=int(args[12]),int(args[13]);assert height==self.height and width==self.width,(height,width)
  pix=self.pixels;grid=(width+15)//16;tile_ids=(pix[:,0]//16)*grid+pix[:,1]//16;unique_tiles=np.unique(tile_ids)
  off=0
  for size in [12,8]:off=(off+127)//128*128+height*width*size
  off=(off+127)//128*128
  ranges=im[off:off+height*width*8].view(torch.int32).reshape(-1,2)[torch.as_tensor(unique_tiles,device='cuda')].cpu().numpy().astype('i8')
  points=binning[:R*4].view(torch.int32);lists=[points[int(a):int(b)].cpu().numpy().copy() for a,b in ranges];union=np.unique(np.concatenate(lists));ug=torch.as_tensor(union.astype('i8'),device='cuda')
  data={};off=0
  for name,size,dtype,dim in [('depth',4,torch.float32,1),('clamped',3,None,3),('radius',4,torch.int32,1),('xy',8,torch.float32,2),('trans',36,torch.float32,9),('normal_opacity',16,torch.float32,4),('color',12,torch.float32,3),('tiles',4,torch.int32,1)]:
   off=(off+127)//128*128
   if dtype is not None:data[name]=geom[off:off+n*size].view(dtype).reshape(n,dim)[ug].cpu().numpy().copy()
   off+=n*size
  data.update(union=union,selected=self.selected,pixels=pix,pixel_tile=tile_ids,unique_tiles=unique_tiles,ranges=ranges,offsets=np.r_[0,np.cumsum([len(x) for x in lists])],point_list=np.concatenate(lists))
  np.savez_compressed(ROOT/'alpha_raw.npz',**data)
  self.meta=dict(overlaps=R,gaussians=n,selected=len(self.selected),candidate_pixels=len(pix),unique_tiles=len(unique_tiles),unique_candidates=len(union),geometry_bytes=geom.numel(),binning_bytes=binning.numel(),image_bytes=im.numel())
  return out
@torch.no_grad()
def main():
 lock=json.loads((CFG/'r8_screen_alpha.lock.json').read_text())
 for p,h in lock['files'].items():assert sha(p)==h,p
 conf=json.loads((CFG/'r8_heavy.json').read_text());row=next(r for r in conf['rows'] if r['key']=='r8_14031_stop');camname=conf.get('heavy_camera','DJI_20241217102535_0020_D')
 parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser);args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10/scene_LoD2'),'-m',row['model'],'--eval','-r','1','--data_device','cpu'])
 safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=7000,shuffle=False);g.load_ply(row['ply']);cam=next(c for c in scene.getTrainCameras() if c.image_name==camname)
 with np.load(ROOT/'top1_depth_alpha.npz') as z:sel=z['row'].copy()
 with np.load(H/'subset/top1.npz') as z:alpha=z['alpha'].squeeze().copy();subsetrgb=z['rgb'].copy()
 assert alpha.max()<.01 and np.isfinite(alpha).all();pixels=np.argwhere(alpha>0).astype('i8');obs=Observer(raster._C,sel,pixels);obs.height=cam.image_height;obs.width=cam.image_width;raster._C=obs
 pkg=render(cam,g,pp.extract(args),torch.zeros(3,device='cuda'));torch.cuda.synchronize();fullrgb=pkg['render'].cpu().numpy();fullalpha=pkg['rend_alpha'].squeeze().cpu().numpy()
 with np.load(H/'states/r8_14031_stop'/f'{camname}.npz') as prev:assert np.array_equal(fullrgb,prev['rgb'])
 np.savez_compressed(ROOT/'alpha_reference.npz',subset_alpha=alpha,subset_rgb=subsetrgb,full_rgb=fullrgb,full_alpha=fullalpha)
 obs.meta.update(at=stamp(),render_rgb_byte_equal=True,extension=str(obs.original.__file__),extension_sha256=sha(obs.original.__file__),cuda_source_modified=False,optimization_steps=0,peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),scientific_verdict=None);dump(ROOT/'alpha_export.json',obs.meta);print('ALPHA_EXPORT',obs.meta,flush=True)
if __name__=='__main__':main()
