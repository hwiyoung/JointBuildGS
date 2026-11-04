"""Inference-only maximum-alpha*T Gaussian attribution at existing training views.
The inherited instrumented renderer must reproduce each saved FT depth exactly.
"""
import sys,math,importlib.util,ast
from types import SimpleNamespace
from common import *
sys.path.insert(0,'/source')
import torch
import diff_surfel_rasterization as raster
from scene import GaussianModel
from gaussian_renderer import render
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
@torch.no_grad()
def main():
 start=time.monotonic();torch.cuda.set_per_process_memory_fraction(.25);site='B173nb_b10';prior='LoD2';model=FT/'runs'/site/'ft_LoD2_s0/attempt1/model';rr=FT/'meshes'/f'{site}__{prior}'/'render';receipt=json.loads((rr/'receipt.json').read_text());views=[v for v in receipt['views'] if not v['virtual']];box=np.array(receipt['box']);root=O/'lineage';root.mkdir(exist_ok=True)
 source=Path(__file__).with_name('render_model.py');node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='camera');ns=dict(np=np,torch=torch,math=math,SimpleNamespace=SimpleNamespace);exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
 g=GaussianModel(3);g.load_ply(str(model/'point_cloud/iteration_30000/point_cloud.ply'));snap=loadz(model/'target_monitor/snapshot_30000.npz',['init_id','origin','target_tag','target_index','patch_ids']);assert np.array_equal(g.init_id.cpu().numpy(),snap['init_id']);assert np.array_equal(g.origin.cpu().numpy(),snap['origin']);inside=((g.get_xyz>=torch.tensor(box[0],device='cuda'))&(g.get_xyz<=torch.tensor(box[1],device='cuda'))).all(1);indices=np.flatnonzero(inside.cpu().numpy());seed=loadz(FT/'stage1'/f'{site}__{prior}/seeds.npz',['patch','origin']);ids=snap['init_id'][indices];assert np.array_equal(seed['origin'][ids],snap['origin'][indices]);current=np.full(len(indices),-1,'i8');attached=snap['target_tag'][indices]==1;current[attached]=snap['patch_ids'][snap['target_index'][indices][attached]]
 savez(root/'gaussian_lineage.npz',full_gaussian_index=indices,init_id=ids,origin=snap['origin'][indices],initial_patch=seed['patch'][ids],target_tag=snap['target_tag'][indices],current_patch=current)
 for name in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']:setattr(g,name,torch.nn.Parameter(getattr(g,name).detach()[inside].clone(),requires_grad=False))
 del inside,snap;g.active_sh_degree=0;torch.cuda.empty_cache();pipe=SimpleNamespace(convert_SHs_python=False,compute_cov3D_python=False,depth_ratio=0.,debug=False);bg=torch.zeros(3,device='cuda')
 lib=TG/'r5/runtime/maxid_build/jbgs_target_r5_maxid.so';spec=importlib.util.spec_from_file_location('jbgs_target_r5_maxid',lib);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);raster._C=mod;records=[]
 for i,v in enumerate(views):
  out=root/'views'/v['file'];out.parent.mkdir(exist_ok=True)
  if out.exists():records.append(dict(view=v['index'],file=str(out),sha256=sha(out),reused=True));continue
  cam=ns['camera'](v);pkg=render(cam,g,pipe,bg);dep=pkg['surf_depth'].squeeze().cpu().numpy();idx=np.rint(pkg['rend_dist'].squeeze().cpu().numpy()).astype('i4')-1;saved=loadz(rr/v['file'],['depth'])['depth'];positive=saved>0
  if not np.array_equal(dep[positive],saved[positive],equal_nan=True):
   d=abs(dep[positive]-saved[positive]);dump(root/'replay_failure.json',dict(view=v['name'],max_depth_difference_m=float(d.max()),different_pixels=int((d!=0).sum()),reason='Inherited instrumented renderer differs from fixed FINALTRAIN renderer; attribution not used',scientific_verdict=None));raise RuntimeError('INSTRUMENTED_DEPTH_MISMATCH')
  assert idx.max()<len(indices);idx[~positive]=-1;savez(out,max_gaussian=idx);records.append(dict(view=v['index'],file=str(out),sha256=sha(out),replayed_positive_pixels=int(positive.sum()),depth_exact=True))
  if i%40==0:print('LINEAGE_RENDER',i+1,len(views),flush=True)
 dump(root/'receipt.json',dict(status='PASS_EXACT_SAVED_DEPTH_MAX_ALPHA_T',views=records,views_total=len(views),virtual_views=0,library=str(lib),library_sha256=sha(lib),source_model_sha256=receipt['model_sha256'],snapshot_sha256=sha(model/'target_monitor/snapshot_30000.npz'),seed_sha256=sha(FT/'stage1'/f'{site}__{prior}/seeds.npz'),mapping='argmax alpha*T, first on tie, actual rasterizer; saved FT depth exactly equal on every positive masked pixel',gaussians=len(indices),optimization_steps=0,seconds=time.monotonic()-start,scientific_verdict=None))
if __name__=='__main__':main()
