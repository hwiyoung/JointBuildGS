"""PHD-MAIN-TARGET-v1: immutable target anchors, normal bounds and fixed depth maps.

Default off. Parent target ownership follows the inherited init_id propagation in
GaussianModel split/clone/prune. No judgments are recomputed during optimization.
"""
import json
import hashlib
from pathlib import Path
import numpy as np
import torch
from torch import nn


def register_args(parser):
    parser.add_argument('--jbgs_target',choices=['off','on'],default='off')
    parser.add_argument('--jbgs_target_dir',default='')
    parser.add_argument('--jbgs_target_lambda',type=float,default=.05)


def write(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


@torch.no_grad()
def normal_projection(x,anchor,normal,sigma):
    # CANDPICK-v2 engine.project_bounds normal component, without tangent bounds.
    delta=x-anchor;h=(delta*normal).sum(1);limit=1.96*sigma
    bounded=torch.maximum(torch.minimum(h,limit),-limit)
    return x+(bounded-h)[:,None]*normal


class Target:
    def __init__(self,args,scene,g):
        if args.jbgs_judgment!='off':raise ValueError('TARGET requires old judgment module off')
        if args.jbgs_appearance!='off' or args.jbgs_mv_consistency!='off':raise ValueError('TARGET auxiliary module enabled')
        self.root=Path(args.jbgs_target_dir);self.mon=Path(args.model_path)/'target_monitor';self.mon.mkdir(parents=True)
        self.depth_lambda=args.jbgs_target_lambda;self.scene=scene;self.n6000=None
        with np.load(self.root/'seeds.npz') as z:s={k:z[k] for k in z.files}
        keep=torch.as_tensor(s['keep_original'],device='cuda',dtype=torch.long)
        assert len(s['original_xyz'])==len(g._xyz)
        assert torch.allclose(g._xyz.detach(),torch.as_tensor(s['original_xyz'],device='cuda',dtype=torch.float32),rtol=0,atol=1e-5)
        for attr in ['_xyz','_features_dc','_features_rest','_opacity','_scaling','_rotation']:
            setattr(g,attr,nn.Parameter(getattr(g,attr).detach()[keep].contiguous().requires_grad_(True)))
        g._xyz.copy_(torch.as_tensor(s['xyz'],device='cuda',dtype=torch.float32))
        g._rotation.copy_(torch.as_tensor(s['quaternion'],device='cuda',dtype=torch.float32))
        # Preserve baseline scale, colour, opacity and number of retained seeds.
        g.max_radii2D=torch.zeros(len(keep),device='cuda');g.frozen_mask=torch.zeros(len(keep),device='cuda',dtype=torch.bool)
        g.origin=torch.as_tensor(s['origin'],device='cuda',dtype=torch.int8)
        g.init_id=torch.arange(len(keep),device='cuda',dtype=torch.int32)
        self.anchor=torch.as_tensor(s['target'],device='cuda',dtype=torch.float32)
        self.normal=torch.as_tensor(s['normal'],device='cuda',dtype=torch.float32)
        self.sigma=torch.as_tensor(s['sigma'],device='cuda',dtype=torch.float32)
        self.region=torch.as_tensor(s['region'],device='cuda',dtype=torch.int8)
        self.maps={};self.index=json.loads((self.root/'maps/index.json').read_text())
        assert set(self.index['views'])=={v.image_name for v in scene.getTrainCameras()}
        for name,meta in self.index['views'].items():
            with np.load(self.root/'maps'/meta['file']) as z:
                data={k:torch.from_numpy(z[k]).pin_memory() for k in ['depth','sigma','weight','owner']}
            self.maps[name]=data
        write(self.mon/'initialization.json',dict(seeds=len(keep),prior_seeds=int((s['origin']==1).sum()),
            background_seeds=int((s['origin']==0).sum()),target_file_sha256=hashlib.sha256((self.root/'seeds.npz').read_bytes()).hexdigest(),
            maps_host_pinned=all(v.is_pinned() for m in self.maps.values() for v in m.values()),
            old_judgment_module=False,scientific_verdict=None))
        self.snapshot(0,g)

    def loss(self,name,render_depth):
        m=self.maps[name];D=render_depth.squeeze(0)
        target=m['depth'].to(D.device,non_blocking=True);w=m['weight'].to(D.device,non_blocking=True)
        valid=torch.isfinite(target)&(target>0)&torch.isfinite(D)&(D>0)&(w>0)
        # Same weighted absolute depth difference and full-image denominator as nojudge.
        return (torch.abs(D[valid]-target[valid])*w[valid]).sum()/float(D.numel())

    @torch.no_grad()
    def project_bounds(self,g):
        ids=g.init_id.long();assert (ids>=0).all() and (ids<len(self.anchor)).all()
        g._xyz.copy_(normal_projection(g._xyz,self.anchor[ids],self.normal[ids],self.sigma[ids]))

    def check_loss(self,iteration,loss):
        if not bool(torch.isfinite(loss)):
            write(self.mon/'STOP.json',dict(iteration=iteration,reason='loss_NaN_or_nonfinite',scientific_verdict=None))
            raise RuntimeError('TARGET_STOP_NONFINITE')

    @torch.no_grad()
    def snapshot(self,iteration,g):
        np.savez_compressed(self.mon/f'snapshot_{iteration}.npz',xyz=g._xyz.detach().cpu().numpy(),
            init_id=g.init_id.cpu().numpy(),origin=g.origin.cpu().numpy(),opacity=g.get_opacity[:,0].cpu().numpy(),
            anchor=self.anchor.cpu().numpy(),normal=self.normal.cpu().numpy(),sigma=self.sigma.cpu().numpy(),region=self.region.cpu().numpy())

    @torch.no_grad()
    def observe(self,iteration,g,loss,rgb,depth,name):
        if iteration%100 and iteration!=1:return
        ids=g.init_id.long();prior=g.origin==1
        opacity=float(g.get_opacity[prior].median()) if prior.any() else None
        excess=float((((g._xyz-self.anchor[ids])*self.normal[ids]).sum(1).abs()-1.96*self.sigma[ids]).max())
        row=dict(iteration=iteration,gaussians=len(ids),target_opacity_median=opacity,max_normal_excess_m=excess,
            loss=float(loss),rgb_loss=float(rgb),target_depth_loss=float(depth),camera=name,scientific_verdict=None)
        with (self.mon/'curve.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        if iteration==6000:self.n6000=len(ids)
        reason=None
        if not torch.isfinite(g._xyz).all():reason='nonfinite_position'
        elif excess>3e-5:reason='normal_bound_violation'
        elif iteration>=7000 and (opacity is None or opacity<.05):reason='target_opacity_median_below_0.05'
        elif iteration==7000 and self.n6000 is not None and len(ids)>3*self.n6000:reason='count_gt_3x_6000'
        if reason:
            write(self.mon/'STOP.json',dict(row,reason=reason))
            raise RuntimeError('TARGET_STOP_'+reason)
        if iteration in [6000,7000,30000]:
            write(self.mon/f'health_{iteration}.json',dict(row,count_at_6000=self.n6000,status='PASS_HEALTH',scientific_verdict=None))
        if iteration%1000==0:print('[target]',row,flush=True)


@torch.no_grad()
def create(args,scene,g,render,pipe):
    return Target(args,scene,g) if args.jbgs_target=='on' else None
