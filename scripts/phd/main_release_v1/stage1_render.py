"""Existing max-alpha*T instrument, exact saved-depth replay, tag contribution."""
import sys,math,importlib.util
from types import SimpleNamespace
from common import *
sys.path.insert(0,'/source');sys.path.append('/repo/scripts/phd/main_rescore_v1')
import torch
import diff_surfel_rasterization as raster
from scene import GaussianModel
from gaussian_renderer import render
from render_model import camera
@torch.no_grad()
def main(site,prior):
    cfg();torch.cuda.set_per_process_memory_fraction(.25);stem=f'{site}__{prior}';root=O/'stage1'/stem/'lineage';root.mkdir(exist_ok=True)
    prep=loadz(root.parent/'gaussians.npz');bind=json.loads((root.parent/'binding.json').read_text());model=Path(bind['model']);rr=score_root(site)/'renders'/f'{stem}__FINALTRAIN_30000'
    receipt=json.loads((rr/'receipt.json').read_text());views=[v for v in receipt['views'] if not v['virtual']];box=np.array(receipt['box'])
    g=GaussianModel(3);g.load_ply(str(model/'point_cloud/iteration_30000/point_cloud.ply'));assert np.array_equal(g.init_id.cpu().numpy(),prep['init_id'])
    keep=((g.get_xyz>=torch.tensor(box[0],device='cuda'))&(g.get_xyz<=torch.tensor(box[1],device='cuda'))).all(1);indices=np.flatnonzero(keep.cpu().numpy())
    for name in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']:setattr(g,name,torch.nn.Parameter(getattr(g,name).detach()[keep].clone(),requires_grad=False))
    g.active_sh_degree=0;pipe=SimpleNamespace(convert_SHs_python=False,compute_cov3D_python=False,depth_ratio=0.,debug=False);bg=torch.zeros(3,device='cuda')
    lib=TG/'r5/runtime/maxid_build/jbgs_target_r5_maxid.so';spec=importlib.util.spec_from_file_location('jbgs_target_r5_maxid',lib);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);raster._C=mod
    existing=score_root(site)/'lineage'/site;use_existing=prior=='LoD2' and (existing/'receipt.json').exists()
    if use_existing:
        old=loadz(existing/'gaussian_lineage.npz',['full_gaussian_index']);assert np.array_equal(old['full_gaussian_index'],indices)
    groups=[(r,k) for r in [0,1,2,4,9] for k in [0,1]];group=np.full(len(indices),-1,'i4')
    for j,(r,k) in enumerate(groups):group[(prep['tag'][indices]==2)&prep['inside_eval'][indices]&(prep['initial_judgment_region'][indices]==r)&(prep['case'][indices]==k)]=j
    totals=np.zeros(len(groups));records=[]
    for i,v in enumerate(views):
        saved=loadz(rr/v['file'],['depth'])['depth'];positive=saved>0;cam=camera(v);dest=root/'views'/v['file'];dest.parent.mkdir(exist_ok=True)
        if use_existing:
            source=existing/'views'/v['file'];index=loadz(source,['max_gaussian'])['max_gaussian'];replay=True
            if not dest.exists():dest.symlink_to(source)
        else:
            pkg=render(cam,g,pipe,bg);dep=pkg['surf_depth'].squeeze().cpu().numpy();assert np.array_equal(dep[positive],saved[positive],equal_nan=True),'INSTRUMENTED_DEPTH_MISMATCH'
            index=np.rint(pkg['rend_dist'].squeeze().cpu().numpy()).astype('i4')-1;index[~positive]=-1;savez(dest,max_gaussian=index);replay=True
        contrib=[]
        for start in range(0,len(groups),3):
            colors=np.zeros((len(indices),3),'f4')
            for k in range(3):colors[group==start+k,k]=1
            pkg=render(cam,g,pipe,bg,override_color=torch.as_tensor(colors,device='cuda'));values=pkg['render'].double().sum((1,2)).cpu().numpy();contrib.extend(values.tolist())
        totals+=np.asarray(contrib[:len(groups)]);records.append(dict(view=v['index'],depth_exact=replay,reused_maxid=use_existing,alpha_T_sums=contrib[:len(groups)]))
        if i%40==0:print('LINEAGE',stem,i+1,len(views),flush=True)
    savez(root/'gaussian_lineage.npz',full_gaussian_index=indices)
    dump(root/'receipt.json',dict(at=now(),status='PASS_EXACT_SAVED_DEPTH_MAX_ALPHA_T',groups=groups,alpha_T_sums=totals.tolist(),views=records,render_root=str(rr),source_model_sha256=receipt['model_sha256'],snapshot_sha256=bind['snapshot_sha256'],library_sha256=sha(lib),contribution_scope='sum over original train-view pixels; repeated visibility across views is retained; groups by original seed judgment; only in-evaluation-box released Gaussians',scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
