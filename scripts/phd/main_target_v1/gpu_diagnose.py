"""No-training diagnosis of failed initial render; fixed cameras and analytic plane control."""
import sys
sys.path.insert(0,'/source');sys.path.insert(0,'/repo')
from argparse import ArgumentParser
import numpy as np
import torch
from common import *
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from utils.graphics_utils import BasicPointCloud
from utils.general_utils import safe_state,build_rotation
from gaussian_renderer import render
from src.phd.prior_propagation_v6.orientation import quat_from_normal
import jbgs_target

def stats(a):
    a=np.asarray(a);a=a[np.isfinite(a)]
    return dict(count=len(a),quantiles=np.quantile(a,[0,.1,.5,.9,1]).tolist()) if len(a) else dict(count=0,quantiles=None)

@torch.no_grad()
def main():
    site,prior=sys.argv[1:3];cfg,lock=training_locked();tag='decompose' if len(sys.argv)>3 else 'diagnose'
    root=OUT/tag/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=False)
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(root/'model'),'--eval','-r','1','--data_device','cpu'])
    (root/'model').mkdir();safe_state(False);args.jbgs_target='on';args.jbgs_target_dir=str(OUT/'stage1'/f'{site}_{prior}')
    args.jbgs_target_lambda=.05;args.jbgs_judgment='off';args.jbgs_appearance='off';args.jbgs_mv_consistency='off'
    g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g);pipe=pp.extract(args);controller=jbgs_target.create(args,scene,g,render,pipe)
    reps=[r for r in json.loads((CFG/'representatives_v1.json').read_text())['rows'] if r['site']==site and prior in r['priors']]
    bg=torch.zeros(3,device='cuda');rows=[]
    with np.load(OUT/'targets'/f'{site}_{prior}.npz') as z:target={k:z[k] for k in z.files}
    with np.load(OUT/'stage1'/f'{site}_{prior}'/'seeds.npz') as z:seed={k:z[k] for k in z.files}
    normals=build_rotation(g._rotation)[:,:,2];normalerr=float((normals-controller.normal).abs().max())
    for rep in reps:
        cam=next(c for c in scene.getTrainCameras() if c.image_name==rep['camera']['name']);pkg=render(cam,g,pipe,bg)
        D=pkg['surf_depth'].squeeze().cpu().numpy();alpha=pkg['rend_alpha'].squeeze().cpu().numpy();m=controller.maps[cam.image_name]
        T=m['depth'].numpy();owner=m['owner'].numpy();valid=np.isfinite(T)&(T>0)&np.isfinite(D)&(D>0);p=owner>=0
        counts=np.bincount(seed['patch'][seed['origin']==1],minlength=len(target['area']))
        strata={}
        for name,mask in [('all',valid),('prior',valid&p),('background',valid&~p),
            ('prior_owner_has_seed',valid&p&(counts[np.maximum(owner,0)]>0)),
            ('prior_owner_no_seed',valid&p&(counts[np.maximum(owner,0)]==0))]:
            strata[name]=dict(error=stats(abs(D[mask]-T[mask])),render_depth=stats(D[mask]),target_depth=stats(T[mask]),alpha=stats(alpha[mask]))
        for cutoff in [.01,.05,.1,.5,.9]:
            mask=valid&p&(alpha>cutoff);strata[f'prior_alpha_gt_{cutoff}']=dict(error=stats(abs(D[mask]-T[mask])),alpha=stats(alpha[mask]))
        np.savez_compressed(root/f'rep_{rep["id"]}.npz',depth=D,alpha=alpha,target=T,owner=owner,
            rgb=pkg['render'].cpu().numpy(),photo=cam.original_image.cpu().numpy())
        # Diagnostic-only decomposition, never an accepted initialization or new gate.
        saved={k:getattr(g,k) for k in ['_xyz','_features_dc','_features_rest','_opacity','_scaling','_rotation']}
        largest=int(torch.argmax(g.get_scaling.max(1).values));decomposition={}
        for label,keep in [('prior_only',g.origin==1),('largest_initial_disk_only',torch.arange(len(g._xyz),device='cuda')==largest)]:
            for key,value in saved.items():setattr(g,key,torch.nn.Parameter(value[keep].detach()))
            part=render(cam,g,pipe,bg);dep=part['surf_depth'].squeeze().cpu().numpy();alp=part['rend_alpha'].squeeze().cpu().numpy()
            mask=valid&p&(dep>0);decomposition[label]=dict(prior_error=stats(abs(dep[mask]-T[mask])),
                prior_alpha=stats(alp[valid&p]),all_alpha=stats(alp[valid]),depth=stats(dep[valid]))
        for key,value in saved.items():setattr(g,key,value)
        # Camera-z=50 plane, orient every disk identically; no scene observations/GT.
        M=cam.world_view_transform.T.cpu().numpy();grid=np.linspace(-8,8,17);xx,yy=np.meshgrid(grid,grid)
        camxyz=np.c_[xx.ravel(),yy.ravel(),np.full(xx.size,50.)];xyz=(camxyz-M[:3,3])@M[:3,:3]
        n=np.tile(-M[2,:3],(len(xyz),1));plane=GaussianModel(0)
        plane.create_from_pcd(BasicPointCloud(xyz,np.ones_like(xyz)*.5,n),1)
        plane._rotation.copy_(torch.as_tensor(quat_from_normal(n),device='cuda',dtype=torch.float32))
        rp=render(cam,plane,pipe,bg);pd=rp['surf_depth'].squeeze().cpu().numpy();pa=rp['rend_alpha'].squeeze().cpu().numpy()
        control=stats(abs(pd[pa>.01]-50));assert control['quantiles'][2]<.001,control
        rows.append(dict(representative=rep['id'],camera=cam.image_name,strata=strata,analytic_plane_control=control,decomposition=decomposition,
            W2C_max_difference=float(np.max(abs(M-np.asarray(rep['camera']['W2C']))))))
    record=dict(site=site,prior=prior,rows=rows,quaternion_normal_max_error=normalerr,
        seed_prior_target_max_error=float(np.max(abs(seed['xyz'][seed['origin']==1]-target['target'][seed['patch'][seed['origin']==1]]))),
        initial_opacity=stats(g.get_opacity[:,0].cpu().numpy()),initial_scales=stats(g.get_scaling.cpu().numpy()),
        largest_initial_disk=dict(seed_index=largest,origin=int(g.origin[largest]),xyz=g._xyz[largest].cpu().tolist(),scale=g.get_scaling[largest].cpu().tolist()),
        training_steps=0,config_sha256=lock['config_sha256'],scientific_verdict=None)
    dump(root/'diagnosis.json',record);print('DIAGNOSIS_COMPLETE',site,prior,flush=True)

if __name__=='__main__':main()
