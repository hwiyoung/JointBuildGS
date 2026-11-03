"""Three-build forward parity and timing; no training or accounting overhead."""
import sys,gc,time
sys.path.insert(0,'/source')
import torch,numpy as np
import diff_surfel_rasterization as raster
from gaussian_renderer import render
from common import *
from rfix_measure import load_scene,module_from
from rfix_unit import extension
ROOT=OUT/'rfix_speed'
def speed(label):return module_from(ROOT/'builds'/label/'extension'/('jbgs_rfix_speed_'+label+'.so'),'jbgs_rfix_speed_'+label)
class Observer:
 def __init__(self,module):self.module=module
 def __getattr__(self,k):return getattr(self.module,k)
 def rasterize_gaussians(self,*args):
  v=self.module.rasterize_gaussians(*args);self.stats=dict(overlaps=int(v[0]),binning_bytes=v[5].numel());self.maps=v[2];return v
@torch.no_grad()
def main():
 key=sys.argv[1];cfg=json.loads((CFG/'rfix_speed.json').read_text());row=next(r for r in cfg['states'] if r['key']==key);label={'image_only':'imageonly','geogs':'geogs'}.get(row['family'],'target');dest=ROOT/'states'/key;dest.mkdir(parents=True,exist_ok=False)
 g,scene,pipe=load_scene(row);cams=sorted(scene.getTrainCameras(),key=lambda c:c.image_name);assert [c.image_name for c in cams]==cfg['views'];bg=torch.zeros(3,device='cuda');mods=[('original',raster._C),('approved',extension(label)),('speed',speed(label))];rows=[]
 dump(dest/'lock.json',dict(at=stamp(),code_sha256=sha(__file__),binaries={k:sha(m.__file__) for k,m in mods},scientific_verdict=None))
 for i,cam in enumerate(cams):
  arrays=[];perf=[]
  for name,mod in mods:
   obs=Observer(mod);raster._C=obs;torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.perf_counter();pkg=render(cam,g,pipe,bg);torch.cuda.synchronize();elapsed=time.perf_counter()-start
   perf.append(dict(variant=name,seconds=elapsed,peak_allocated_bytes=torch.cuda.max_memory_allocated(),**obs.stats));vals={k:v.detach().cpu().numpy().copy() for k,v in pkg.items() if torch.is_tensor(v) and k!='viewspace_points'};vals['raw_maps']=obs.maps.cpu().numpy().copy();arrays.append(vals);del pkg,obs;gc.collect()
  a,b,c=arrays;checks={k:dict(byte_equal=bool(a[k].tobytes()==c[k].tobytes()),max_abs=float(np.nanmax(np.abs(a[k].astype('f8')-c[k].astype('f8'))))) for k in a};passed=all(v['byte_equal'] for v in checks.values());rec=dict(camera=cam.image_name,performance=perf,comparison=checks,pass_=passed);rows.append(rec)
  dump(dest/'progress.json',dict(at=stamp(),completed=i+1,total=len(cams),last=rec,scientific_verdict=None))
  if i%20==0:print('SPEED_FORWARD',key,i+1,passed,[round(p['seconds'],4) for p in perf],flush=True)
  if not passed:np.savez_compressed(dest/(cam.image_name+'_difference.npz'),**{v+'_'+k:arr[k] for v,arr in [('original',a),('speed',c)] for k in arr})
  del arrays,a,b,c,vals;gc.collect()
 dump(dest/'result.json',dict(at=stamp(),status='PASS' if all(r['pass_'] for r in rows) else 'FAIL',records=rows,scientific_verdict=None))
if __name__=='__main__':main()
