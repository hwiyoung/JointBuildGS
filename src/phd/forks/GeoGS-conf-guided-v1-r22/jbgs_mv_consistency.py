"""FARPULL add4: only multiview terms in the judgment path; off is inert."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import torch


def register_args(parser):
    parser.add_argument('--jbgs_mv_consistency',choices=['off','plain','weighted'],default='off')
    parser.add_argument('--jbgs_mv_inputs',default='')
    parser.add_argument('--jbgs_mv_max_samples',type=int,default=4096)


def create(args,scene,judgment):
    if args.jbgs_mv_consistency=='off':return None
    if judgment is None:raise ValueError('Multiview add4 requires the unchanged judgment base')
    if args.jbgs_appearance!='off' or args.jbgs_lt_farpull_lambda!=0:raise ValueError('MV arms exclude appearance and farpull')
    return Controller(args,scene,judgment)


class Controller:
    def __init__(self,args,scene,judgment):
        self.args=args;self.j=judgment;self.root=Path(args.jbgs_mv_inputs)
        self.binding=json.loads((self.root/'neighbors.json').read_text())
        self.config=json.loads((self.root.parent/'geometry.json').read_text())
        self.cameras={c.image_name:c for c in scene.getTrainCameras()}
        assert sorted(self.cameras)==self.binding['train_names']
        assert not set(self.cameras)&set(self.binding['evaluation_names'])
        self.out=judgment.mon;self.previous=time.monotonic();self.rois={}
        omega=np.load(self.root/('omega_'+args.jbgs_vfile_vprior+'.npy'))
        assert len(omega)==len(judgment.lt_values['v_prior'])
        self.omega=torch.as_tensor(omega,device='cuda',dtype=torch.float32)
        (self.out/'mv_binding.json').write_text(json.dumps(dict(mode=args.jbgs_mv_consistency,
            inputs=str(self.root),neighbors_sha256=hashlib.sha256((self.root/'neighbors.json').read_bytes()).hexdigest(),
            omega_sha256=hashlib.sha256((self.root/('omega_'+args.jbgs_vfile_vprior+'.npy')).read_bytes()).hexdigest(),
            geometry=self.config['geometry'],max_samples=args.jbgs_mv_max_samples,
            single_view_added=False,native_normal_unchanged=True,scientific_verdict=None),indent=2))

    def seed(self,iteration,name):
        return int.from_bytes(hashlib.sha256(f'{self.args.jbgs_seed}:{self.binding["site"]}:{iteration}:{name}'.encode()).digest()[:8],'little')%(2**31)

    @staticmethod
    def calibration(cam):
        H,W=cam.image_height,cam.image_width;P=cam.projection_matrix.T;E=cam.world_view_transform.T
        K=torch.eye(3,device=P.device,dtype=P.dtype);K[0,0]=P[0,0]*W/2;K[1,1]=P[1,1]*H/2
        K[0,2]=P[0,2]*W/2+(W-1)/2;K[1,2]=P[1,2]*H/2+(H-1)/2
        return K,E[:3,:3],E[:3,3]

    def roi(self,name,like):
        # Reference masks are diagnostic only: never affect sampling or loss.
        if self.binding['site']!='B173nb_b10':return None
        if name not in self.rois:
            p=Path('/out/cause_add3/photos')/(name+'.npz')
            with np.load(p) as z:self.rois[name]=np.unpackbits(z['mask'])[:int(np.prod(z['shape']))].reshape(tuple(z['shape'])).astype(bool)
        return torch.as_tensor(self.rois[name],device=like.device)

    def loss(self,camera,pkg,gaussians,pipe,bg,iteration):
        from gaussian_renderer import render
        from jbgs_mv_geometry import pgsr_geometry_losses
        zero=pkg['surf_depth'].reshape(-1)[:0].sum()
        if iteration<1000:return zero
        name=camera.image_name;seed=self.seed(iteration,name);neighbors=self.binding['graph'][name]['selected']
        args={};near_name=None
        if neighbors:
            near_name=neighbors[seed%len(neighbors)];near=self.cameras[near_name];near_pkg=render(near,gaussians,pipe,bg)
            Kn,Rn,tn=self.calibration(near)
            args=dict(depth_near=near_pkg['surf_depth'],alpha_near=near_pkg['rend_alpha'],rgb_near=near.original_image.cuda(),K_near=Kn,R_near=Rn,t_near=tn)
        omega=None
        if self.args.jbgs_mv_consistency=='weighted':
            loc=self.j.lt_locations[name].long();prior=self.j.P[name]
            has=(loc>=0)&(loc<len(self.omega))&torch.isfinite(prior)&(prior>0)
            omega=torch.ones_like(pkg['surf_depth'][0]);omega[has]=self.omega[loc[has]]
        geo=self.config['geometry'];K,R,t=self.calibration(camera)
        parts=pgsr_geometry_losses(pkg['surf_depth'],pkg['rend_normal'],pkg['rend_alpha'],camera.original_image.cuda(),K,R,t,
            **args,seed=seed,max_samples=self.args.jbgs_mv_max_samples,
            **{k:geo[k] for k in ['microbatch_size','patch_radius','reprojection_threshold','alpha_min','grazing_cos_min']},
            pixel_weights=omega,diagnostic_roi=self.roi(name,pkg['surf_depth']))
        value=geo['mvgeom_weight']*parts['mvgeom']+geo['mvrgb_weight']*parts['mvrgb']
        if not bool(torch.isfinite(value)):raise RuntimeError('LOSSTRAIN_STOP: nonfinite multiview loss')
        self.last=dict(iteration=iteration,camera=name,neighbor=near_name,mode=self.args.jbgs_mv_consistency,
            **parts['counts'],mvgeom=float(parts['mvgeom'].detach()),mvrgb=float(parts['mvrgb'].detach()),
            mv_weighted_total=float(value.detach()),max_samples=self.args.jbgs_mv_max_samples,
            scientific_verdict=None)
        return value

    def observe(self,iteration,gaussians,photo,depth,mv):
        if iteration<1000:return
        row=dict(self.last)
        if iteration%1000==0:
            gradients={}
            for name,term in [('photo',photo),('depth',depth),('multiview',mv)]:
                g=torch.autograd.grad(term,gaussians._xyz,retain_graph=True,allow_unused=True)[0] if term.requires_grad else None
                if g is None:gradients[name]=dict(present=False,median_all=None,median_nonzero=None)
                else:
                    norm=g.detach().norm(dim=1);nz=norm[norm>0]
                    gradients[name]=dict(present=True,median_all=float(torch.quantile(norm,.5)),median_nonzero=float(torch.quantile(nz,.5)) if len(nz) else None,nonzero=int(len(nz)),finite=bool(torch.isfinite(norm).all()))
            row['xyz_gradient_norm']=gradients
        if iteration<=3000 or iteration%1000==0:
            row['wall_time_monotonic']=time.monotonic();row['peak_cuda_allocated_gib']=torch.cuda.max_memory_allocated()/2**30
            row['peak_cuda_reserved_gib']=torch.cuda.max_memory_reserved()/2**30
            with (self.out/'mv_consistency.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')

    def after_iteration(self,iteration,gaussians,pipe,bg):
        if iteration not in [7000,15000]:return
        from jbgs_mv_early import capture
        try:capture(self,gaussians,pipe,bg,iteration)
        except Exception as exc:
            # A diagnostic failure must not change the optimization or health rule.
            (self.out/f'mv_early_ERROR_{iteration}.json').write_text(json.dumps(dict(iteration=iteration,error=repr(exc),scientific_verdict=None)))
