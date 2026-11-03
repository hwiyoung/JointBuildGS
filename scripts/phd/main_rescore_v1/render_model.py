"""Saved model inference at the frozen camera list, using each family's renderer."""
import sys,math
from types import SimpleNamespace
from common import *
sys.path.insert(0,'/source')
import torch
from scene import GaussianModel
from gaussian_renderer import render

def camera(v):
 W,H=v['width'],v['height'];K=np.array(v['K']);zn,zf=.01,100.
 P=np.zeros((4,4),'f4');P[0,0]=2*K[0,0]/W;P[1,1]=2*K[1,1]/H;P[0,2]=(2*K[0,2]-(W-1))/W;P[1,2]=(2*K[1,2]-(H-1))/H;P[2,2]=zf/(zf-zn);P[2,3]=-zf*zn/(zf-zn);P[3,2]=1
 w=torch.tensor(v['W2C'],device='cuda',dtype=torch.float32).T;p=torch.tensor(P,device='cuda').T
 return SimpleNamespace(image_width=W,image_height=H,image_name=v['name'],FoVx=2*math.atan(W/(2*K[0,0])),FoVy=2*math.atan(H/(2*K[1,1])),znear=zn,zfar=zf,world_view_transform=w,projection_matrix=p,full_proj_transform=w@p,camera_center=w.inverse()[3,:3])
@torch.no_grad()
def main(jobfile):
 cfg();start=time.monotonic();fraction=float(os.environ.get('RESCORE_RENDER_GPU_FRACTION','.25'));torch.cuda.set_per_process_memory_fraction(fraction);job=json.loads(Path(jobfile).read_text());model=Path(job['ply']);root=O/'renders'/job['key'];root.mkdir(parents=True,exist_ok=True);cached=0
 views=json.loads((O/'views'/f"{job['site']}.json").read_text())['views'];box=np.array(job['box']);degree=0
 with model.open('rb') as f:
  names=[]
  while True:
   line=f.readline().decode('ascii').strip()
   if line=='end_header':break
   if line.startswith('property') and 'f_rest_' in line:names.append(line)
 degree=round(math.sqrt(len(names)/3+1)-1);g=GaussianModel(degree);g.load_ply(str(model));inside=((g.get_xyz>=torch.tensor(box[0],device='cuda'))&(g.get_xyz<=torch.tensor(box[1],device='cuda'))).all(1)
 for name in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']:setattr(g,name,torch.nn.Parameter(getattr(g,name).detach()[inside].clone(),requires_grad=False))
 g.active_sh_degree=0;pipe=SimpleNamespace(convert_SHs_python=False,compute_cov3D_python=False,depth_ratio=0.,debug=False);bg=torch.zeros(3,device='cuda');records=[]
 for i,v in enumerate(views):
  p=root/f'{i:04d}.npz'
  if p.exists():
   with np.load(p) as z:assert z['depth'].shape==(v['height'],v['width']) and z['rgb'].shape==(v['height'],v['width'],3)
   records.append(dict(v,file=p.name,sha256=sha(p)));cached+=1;continue
  cam=camera(v);pkg=render(cam,g,pipe,bg);depth=pkg['depth' if job['family']=='CDGS' else 'surf_depth'].reshape(v['height'],v['width']);H,W=depth.shape;K=np.array(v['K']);yy,xx=torch.meshgrid(torch.arange(H,device='cuda'),torch.arange(W,device='cuda'),indexing='ij');xyz=torch.stack([(xx-K[0,2])*depth/K[0,0],(yy-K[1,2])*depth/K[1,1],depth,torch.ones_like(depth)],-1);world=xyz@cam.world_view_transform.inverse();mask=((world[...,:3]>=torch.tensor(box[0],device='cuda'))&(world[...,:3]<=torch.tensor(box[1],device='cuda'))).all(-1)&(depth>0);d=depth.cpu().numpy().copy();d[~mask.cpu().numpy()]=0
  rgb=(pkg['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype('u1');p=root/f'{i:04d}.npz';savez(p,depth=d,rgb=rgb);records.append(dict(v,file=p.name,sha256=sha(p)))
  if i%40==0:print('RENDER',job['key'],i+1,len(views),flush=True)
 dump(root/'receipt.json',dict(status='PASS',views=records,cached_views=cached,gpu_memory_fraction=fraction,box=box.tolist(),model_sha256=sha(model),source_sha256=sha(__file__),renderer_sha256=sha('/source/gaussian_renderer/__init__.py'),job=job,seconds=time.monotonic()-start,optimization_steps=0,scientific_verdict=None))
 timing('render_'+job['key'],start)
if __name__=='__main__':main(sys.argv[1])
