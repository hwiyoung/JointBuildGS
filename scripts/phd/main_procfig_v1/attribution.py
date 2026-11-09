"""Bounded inference-only reuse of RESCORE max-alpha*T lineage, never optimize."""
from common import *
import math, importlib.util, traceback
from types import SimpleNamespace
from scipy.sparse import coo_matrix
sys.path.insert(0,'/source')
import torch
import diff_surfel_rasterization as raster
from scene import GaussianModel
from gaussian_renderer import render

@torch.no_grad()
def main():
 start=time.monotonic();c=cfg();torch.cuda.set_per_process_memory_fraction(.55)
 rr=FT/'meshes'/STEM/'render';rec=json.loads((rr/'receipt.json').read_text());views=[v for v in rec['views'] if not v['virtual']];box=np.array(rec['box']);ref=loadz(O/'work/reference_building.npz');groups=loadz(O/'work/patch_groups.npz')['group'];own=ref['owner'];group=np.zeros(len(own),'i1');ok=own>=0;group[ok]=groups[own[ok]];sel=np.flatnonzero(group>0);xyz=ref['xyz'][sel];pointgroups=group[sel]
 source=R/'scripts/phd/main_rescore_v1/render_model.py';env=dict(np=np,torch=torch,math=math,SimpleNamespace=SimpleNamespace);camfn=inherit(source,['camera'],env)['camera']
 g=GaussianModel(3);ply=MODEL/'point_cloud/iteration_30000/point_cloud.ply';g.load_ply(str(ply));snap=loadz(MODEL/'target_monitor/snapshot_30000.npz',['init_id','origin','target_tag','target_index','patch_ids']);assert np.array_equal(g.init_id.cpu().numpy(),snap['init_id'])
 inside=((g.get_xyz>=torch.tensor(box[0],device='cuda'))&(g.get_xyz<=torch.tensor(box[1],device='cuda'))).all(1);fullids=np.flatnonzero(inside.cpu().numpy())
 for name in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']:setattr(g,name,torch.nn.Parameter(getattr(g,name).detach()[inside].clone(),requires_grad=False))
 g.active_sh_degree=0;pipe=SimpleNamespace(convert_SHs_python=False,compute_cov3D_python=False,depth_ratio=0.,debug=False);bg=torch.zeros(3,device='cuda')
 lib=PH/'main_target_v1/PHD-MAIN-TARGET-v1/r5/runtime/maxid_build/jbgs_target_r5_maxid.so';spec=importlib.util.spec_from_file_location('jbgs_target_r5_maxid',lib);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);raster._C=mod
 P=[];G=[];records=[]
 for j,v in enumerate(views):
  if time.monotonic()-start>c['max_attribution_seconds']:raise TimeoutError('30 minute attribution budget')
  pkg=render(camfn(v),g,pipe,bg);dep=pkg['surf_depth'].squeeze().cpu().numpy();index=np.rint(pkg['rend_dist'].squeeze().cpu().numpy()).astype('i4')-1;saved=loadz(rr/v['file'],['depth'])['depth'];positive=saved>0
  if not np.array_equal(dep[positive],saved[positive],equal_nan=True):
   d=abs(dep[positive]-saved[positive]);dump(O/'work/attribution_depth_mismatch.json',dict(view=v['name'],maximum_difference_m=float(d.max()),different_pixels=int((d!=0).sum())));raise RuntimeError('INSTRUMENTED_DEPTH_MISMATCH: inherited exact replay gate; no attribution inferred')
  E=np.asarray(v['W2C']);K=np.asarray(v['K']);q=xyz@E[:3,:3].T+E[:3,3];ids=np.flatnonzero(q[:,2]>0);a=q[ids];u=np.rint(K[0,0]*a[:,0]/a[:,2]+K[0,2]).astype(int);w=np.rint(K[1,1]*a[:,1]/a[:,2]+K[1,2]).astype(int);ins=(u>=0)&(w>=0)&(u<v['width'])&(w<v['height']);ids=ids[ins];u=u[ins];w=w[ins];seen=(saved[w,u]>0)&(abs(saved[w,u]-q[ids,2])<=.25)&(index[w,u]>=0);P.append(ids[seen]);G.append(index[w[seen],u[seen]])
  records.append(dict(view=v['name'],depth_exact=True,matched_reference_rows=int(seen.sum())))
  if j%40==0:print('ATTRIBUTION_VIEW',j+1,len(views),flush=True)
 a=np.concatenate(P);b=np.concatenate(G);matrix=coo_matrix((np.ones(len(a),'i4'),(a,b)),shape=(len(xyz),len(fullids))).tocsr();chosen=np.full(len(xyz),-1,'i4');votes=np.asarray(matrix.sum(1)).ravel()
 for i in np.flatnonzero(np.diff(matrix.indptr)):
  starti,endi=matrix.indptr[i:i+2];ids=matrix.indices[starti:endi];counts=matrix.data[starti:endi];chosen[i]=ids[np.argmax(counts)]
 valid=chosen>=0;full=np.full(len(chosen),-1,'i8');full[valid]=fullids[chosen[valid]];seed=loadz(FT/'stage1'/STEM/'seeds.npz',['patch']);initial=np.full(len(chosen),-1,'i8');initial[valid]=seed['patch'][snap['init_id'][full[valid]]];origin=np.full(len(chosen),-1,'i1');origin[valid]=snap['origin'][full[valid]];tag=np.full(len(chosen),-1,'i1');tag[valid]=snap['target_tag'][full[valid]];descgroup=np.zeros(len(chosen),'i1');good=initial>=0;descgroup[good]=groups[initial[good]]
 save=dict(reference_row_id=ref['row_id'][sel],group=pointgroups,max_contributor_full_gaussian=full,origin=origin,target_tag=tag,initial_patch=initial,initial_patch_group=descgroup,visible_views=votes)
 savez(O/'gaussians/attribution_30000.npz',**save);rows=[]
 for gp in [1,2]:
  for org in [-1,0,1]:
   for tg in [-1,0,1,2]:
    mask=(pointgroups==gp)&(origin==org)&(tag==tg)
    if mask.any():rows.append(dict(group=gp,origin=org,target_tag=tg,reference_rows=int(mask.sum()),fraction_of_group=float(mask.sum()/(pointgroups==gp).sum())))
 table('actual_max_alpha_T_origin',rows)
 dump(D/'attribution_receipt.json',dict(status='PASS_EXACT_SAVED_DEPTH_MAX_ALPHA_T',reference_rows=len(xyz),attributed_rows=int(valid.sum()),unavailable_rows=int((~valid).sum()),views=records,seconds=time.monotonic()-start,renderer=dict(path=str(lib),sha256=sha(lib)),method='RESCORE modal maximum alpha*T over exact original train depths, 0.25m visibility, lowest Gaussian ID on tie',scientific_verdict=None,optimization_steps=0))
try:main()
except Exception as e:
 traceback.print_exc();dump(D/'attribution_receipt.json',dict(status='확인 불가',reason=str(e),scientific_verdict=None,optimization_steps=0));issue('30,000회 최대 α×T 출신: 확인 불가. '+str(e))
