"""Four fixed synthetic cases, original versus separately built tile-only renderer."""
import sys,importlib.util,math
sys.path.insert(0,'/source')
import torch,numpy as np
import diff_surfel_rasterization as raster
from utils.graphics_utils import getProjectionMatrix
from common import *
ROOT=OUT/'rfix_speed'
from rfix_speed_measure import speed as extension
@torch.no_grad()
def main():
 label=sys.argv[1];out=ROOT/'units_r2'/label;out.mkdir(parents=True,exist_ok=False)
 cases=[dict(name='tilted_close_lens',xyz=[0,0,.25],scale=[.4,.4],tilt=80),dict(name='outside_burst',xyz=[5,0,.4],scale=[1,1],tilt=75),dict(name='cross_near_partially_visible',xyz=[0,0,.4],scale=[.8,.8],tilt=65),dict(name='ordinary',xyz=[0,0,4],scale=[.1,.1],tilt=0)]
 dump(out/'lock.json',dict(at=stamp(),cases=cases,code_sha256=sha(__file__),renderer_sha256=sha(ROOT/'builds'/label/'extension'/('jbgs_rfix_speed_'+label+'.so')),scientific_verdict=None))
 original=raster._C;fixed=extension(label);rows=[];W=H=64
 proj=getProjectionMatrix(.01,100,math.pi/2,math.pi/2).T.cuda();view=torch.eye(4,device='cuda')
 settings=raster.GaussianRasterizationSettings(H,W,1.,1.,torch.zeros(3,device='cuda'),1.,view,proj,0,torch.zeros(3,device='cuda'),False,False)
 for case in cases:
  xyz=torch.tensor([case['xyz']],device='cuda',dtype=torch.float32);scale=torch.tensor([case['scale']],device='cuda',dtype=torch.float32);a=math.radians(case['tilt'])/2;rot=torch.tensor([[math.cos(a),0,math.sin(a),0]],device='cuda');outs=[]
  for mod in [original,original,fixed]:
   raster._C=mod
   # Low-level native tuple keeps all seven auxiliary maps visible.
   args=(settings.bg,xyz,torch.ones(1,3,device='cuda'),torch.full((1,1),.5,device='cuda'),scale,rot,1.,torch.empty(0,device='cuda'),view,proj,1.,1.,H,W,torch.empty(0,device='cuda'),0,torch.zeros(3,device='cuda'),False,False)
   v=mod.rasterize_gaussians(*args);torch.cuda.synchronize();outs.append((v[0],v[1].cpu().numpy(),v[2].cpu().numpy(),v[3].cpu().numpy()));del v
  a,b,c=outs;d=max(float(abs(a[i]-c[i]).max()) for i in [1,2]);jitter=max(float(abs(a[i]-b[i]).max()) for i in [1,2]);rad=np.array_equal(a[3],c[3]);alpha=a[1][0];tiles=sum(bool((alpha[y:y+16,x:x+16]>=1/255).any()) for y in range(0,H,16) for x in range(0,W,16));passed=d<=jitter and rad and c[0]<=a[0]
  rows.append(dict(case=case,original_overlaps=a[0],fixed_overlaps=c[0],exact_visible_tiles=tiles,extra_small_rectangle_tiles=c[0]-tiles,radii=a[3].tolist(),radii_equal=rad,max_abs=d,jitter_max_abs=jitter,pass_=passed));np.savez_compressed(out/(case['name']+'.npz'),before_rgb=a[1],after_rgb=c[1],before_maps=a[2],after_maps=c[2]);print(rows[-1],flush=True)
 dump(out/'result.json',dict(at=stamp(),status='PASS' if all(r['pass_'] for r in rows) else 'FAIL',rows=rows,optimization_steps=0,scientific_verdict=None))
 assert all(r['pass_'] for r in rows)
if __name__=='__main__':main()
