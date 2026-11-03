"""Fixed-renderer endpoint evidence; saved trained state, no optimization."""
import sys,time,gc
sys.path.insert(0,'/source')
import numpy as np,torch
import diff_surfel_rasterization as raster
from gaussian_renderer import render
from common import *
from rfix_measure import load_scene,module_from
from screen_sim_render_r3 import Observer
ROOT=OUT/'rfix_continue/endpoint'
@torch.no_grad()
def main():
 cfg=json.loads((CFG/'rfix_endpoint.json').read_text());row=cfg['state'];dest=ROOT/'states/r8_LoD2_rfix/current';dest.mkdir(parents=True,exist_ok=False);(dest/'renders').mkdir()
 for p,h in json.loads((CFG/'rfix_endpoint.lock.json').read_text())['files'].items():assert sha(p)==h,p
 g,scene,pipe=load_scene(row);cams=sorted(scene.getTrainCameras(),key=lambda c:c.image_name);idx=json.loads((OUT/'screen_sim/inputs/index.json').read_text());assert [c.image_name for c in cams]==[v['camera'] for v in idx['views']]
 fixed=module_from(Path(cfg['extension']),'jbgs_rfix_target');weights=module_from(OUT/'screen_sim/states/r8_LoD2_stop/account_build/screen_sim_weights.so','screen_sim_weights');N=len(g._xyz);obs=Observer(fixed,weights,N);obs.account=True;obs.tolerance=1e-5;obs.sum=torch.zeros(N,device='cuda',dtype=torch.float64);obs.roi_sum=torch.zeros_like(obs.sum);obs.maximum=torch.zeros(N,device='cuda');raster._C=obs;maxrad=np.zeros(N,'i4');bg=torch.zeros(3,device='cuda');rows=[]
 for i,cam in enumerate(cams):
  z=np.load(OUT/'screen_sim/inputs'/(cam.image_name+'.npz'));obs.roi=torch.tensor(z['roi'],device='cuda');start=time.perf_counter();pkg=render(cam,g,pipe,bg);torch.cuda.synchronize();rad=pkg['radii'].cpu().numpy();maxrad=np.maximum(maxrad,rad)
  depth=pkg['surf_depth'].squeeze().cpu().numpy();rgb=(pkg['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype('u1');np.savez_compressed(dest/'renders'/(cam.image_name+'.npz'),depth=depth,rgb=rgb)
  if cam.image_name in ['DJI_20241217102535_0020_D','DJI_20241217091133_0109_D']:np.savez_compressed(dest/(cam.image_name+'_float.npz'),rgb=pkg['render'].cpu().numpy(),gt=cam.original_image[:3].cpu().numpy(),alpha=pkg['rend_alpha'].cpu().numpy())
  rows.append(dict(camera=cam.image_name,seconds=time.perf_counter()-start,**obs.last));dump(dest/'progress.json',dict(at=stamp(),completed=i+1,last=rows[-1],scientific_verdict=None));del pkg;gc.collect()
  if i%20==0:print('ENDPOINT_RENDER',i+1,len(cams),flush=True)
 np.savez_compressed(ROOT/'gaussians.npz',xyz=g._xyz.cpu().numpy(),max_radius=maxrad,total_contribution=obs.sum.cpu().numpy(),roi_contribution=obs.roi_sum.cpu().numpy(),max_contribution=obs.maximum.cpu().numpy())
 dump(dest/'result.json',dict(at=stamp(),status='PASS',gaussians=N,views=rows,extension_sha256=sha(cfg['extension']),optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
