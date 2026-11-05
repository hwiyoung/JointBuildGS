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
    parser.add_argument('--jbgs_targets',default=None)
    parser.add_argument('--jbgs_preserve_freespace',choices=['off','on'],default='off')
    parser.add_argument('--jbgs_finaltrain',choices=['off','on'],default='off')
    parser.add_argument('--jbgs_target',choices=['off','on'],default='off')
    parser.add_argument('--jbgs_target_rev',choices=['r4n','r6','r7','r8'],default='r4n')
    parser.add_argument('--jbgs_target_dir',default='')
    parser.add_argument('--jbgs_target_lambda',type=float,default=.05)


def write(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


@torch.no_grad()
def normal_projection(x,anchor,normal,sigma):
    # CANDPICK-v2 engine.project_bounds normal component, without tangent bounds.
    # Large tangential coordinates cause cancellation in float32 dot products.
    # Keep model tensors and the original 1.96*sigma limit in float32; evaluate
    # the projection in double and account for unit-normal storage roundoff.
    xd=x.double();a=anchor.double();n=normal.double()
    h=((xd-a)*n).sum(1);limit=(1.96*sigma).double()
    bounded=torch.maximum(torch.minimum(h,limit),-limit)
    return (xd+((bounded-h)/(n*n).sum(1))[:,None]*n).to(x.dtype)


class Target:
    def __init__(self,args,scene,g):
        if args.jbgs_judgment!='off':raise ValueError('TARGET requires old judgment module off')
        if args.jbgs_appearance!='off' or args.jbgs_mv_consistency!='off':raise ValueError('TARGET auxiliary module enabled')
        self.root=Path(args.jbgs_target_dir);self.mon=Path(args.model_path)/'target_monitor';self.mon.mkdir(parents=True)
        self.depth_lambda=args.jbgs_target_lambda;self.scene=scene;self.n6000=None
        with np.load(self.root/'seeds.npz') as z:s={k:z[k] for k in z.files}
        keep=torch.as_tensor(s['keep_original'],device='cuda',dtype=torch.long)
        bg_rotation=None
        if args.jbgs_target_rev=='r8':
            bg_ids=torch.as_tensor(s['background_original'],device='cuda',dtype=torch.long)
            bg_rotation=g._rotation.detach()[bg_ids].clone()
        assert len(s['original_xyz'])==len(g._xyz)
        assert torch.allclose(g._xyz.detach(),torch.as_tensor(s['original_xyz'],device='cuda',dtype=torch.float32),rtol=0,atol=1e-5)
        for attr in ['_xyz','_features_dc','_features_rest','_opacity','_scaling','_rotation']:
            setattr(g,attr,nn.Parameter(getattr(g,attr).detach()[keep].contiguous().requires_grad_(True)))
        count=len(s['xyz'])
        if 'background_rgb' in s:
            from utils.sh_utils import RGB2SH
            from simple_knn._C import distCUDA2
            bg_count=count-len(keep)
            assert bg_count==len(s['background_rgb'])
            for attr in ['_xyz','_features_dc','_features_rest','_opacity','_scaling','_rotation']:
                old=getattr(g,attr).detach()
                extra=torch.zeros((bg_count,)+old.shape[1:],device=old.device,dtype=old.dtype)
                setattr(g,attr,nn.Parameter(torch.cat([old,extra]).contiguous().requires_grad_(True)))
            g._features_dc[len(keep):,0,:]=RGB2SH(torch.as_tensor(s['background_rgb'],device='cuda',dtype=torch.float32))
            g._opacity[len(keep):]=g.inverse_opacity_activation(torch.full((bg_count,1),.1,device='cuda'))
            # Original nearest-neighbor initialization rule, evaluated on the new combined cloud.
            initial=torch.as_tensor(s['xyz'],device='cuda',dtype=torch.float32)
            scale=torch.log(torch.sqrt(torch.clamp_min(distCUDA2(initial),1e-7)))
            g._scaling[len(keep):]=scale[len(keep):,None].repeat(1,2)
        g._xyz.copy_(torch.as_tensor(s['xyz'],device='cuda',dtype=torch.float32))
        g._rotation.copy_(torch.as_tensor(s['quaternion'],device='cuda',dtype=torch.float32))
        if bg_rotation is not None:
            from utils.general_utils import build_rotation
            g._rotation[len(keep):]=bg_rotation
            s['normal'][len(keep):]=build_rotation(bg_rotation)[:,:,2].cpu().numpy()
        # Preserve baseline scale, colour, opacity and number of retained seeds.
        g.max_radii2D=torch.zeros(count,device='cuda');g.frozen_mask=torch.zeros(count,device='cuda',dtype=torch.bool)
        g.origin=torch.as_tensor(s['origin'],device='cuda',dtype=torch.int8)
        g.init_id=torch.arange(count,device='cuda',dtype=torch.int32)
        self.anchor=torch.as_tensor(s['target'],device='cuda',dtype=torch.float32)
        self.normal=torch.as_tensor(s['normal'],device='cuda',dtype=torch.float32)
        self.sigma=torch.as_tensor(s['sigma'],device='cuda',dtype=torch.float32)
        self.region=torch.as_tensor(s['region'],device='cuda',dtype=torch.int8)
        self.initial_scale=g.get_scaling.detach().clone()
        self.initial_large_background=(g.origin==0)&(self.initial_scale.max(1).values>1.)
        large_ids=torch.where(self.initial_large_background)[0].cpu().numpy()
        scale=self.initial_scale.cpu().numpy();positions=self.anchor.cpu().numpy()
        ranked=large_ids[np.lexsort((large_ids,-scale[large_ids].max(1)))][:10]
        write(self.mon/'initial_large_background.json',dict(threshold_m=1.,size='maximum activated tangent scale',
            background_count=int((g.origin==0).sum()),count_gt_1m=len(large_ids),
            top10=[dict(init_id=int(i),xyz_local_m=positions[i].tolist(),scale_axes_m=scale[i].tolist(),
                        max_scale_m=float(scale[i].max())) for i in ranked],
            coordinates='inherited local training frame; EPSG:25832 translation in site source metadata',
            scale_rule='unchanged baseline distCUDA2, no cap, no isolated point removal',
            stop_criterion=False,scientific_verdict=None))
        self.maps={};self.index=json.loads((self.root/'maps/index.json').read_text())
        assert set(self.index['views'])=={v.image_name for v in scene.getTrainCameras()}
        for name,meta in self.index['views'].items():
            with np.load(self.root/'maps'/meta['file']) as z:
                data={k:torch.from_numpy(z[k]).pin_memory() for k in ['depth','sigma','weight','owner']}
            self.maps[name]=data
        write(self.mon/'initialization.json',dict(seeds=count,prior_seeds=int((s['origin']==1).sum()),
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
            scale=g.get_scaling.cpu().numpy(),rotation=g.get_rotation.cpu().numpy(),
            initial_scale=self.initial_scale.cpu().numpy(),initial_large_background=self.initial_large_background.cpu().numpy(),
            anchor=self.anchor.cpu().numpy(),normal=self.normal.cpu().numpy(),sigma=self.sigma.cpu().numpy(),region=self.region.cpu().numpy())

    @torch.no_grad()
    def large_background_evidence(self,iteration,g,root):
        ids=g.init_id.long();select=self.initial_large_background[ids]
        parent=ids[select].cpu().numpy();xyz=g._xyz[select].cpu().numpy()
        delta=g._xyz[select]-self.anchor[ids[select]]
        normal=(delta*self.normal[ids[select]]).sum(1)
        tangent=torch.linalg.vector_norm(delta-normal[:,None]*self.normal[ids[select]],dim=1)
        scales=g.get_scaling[select].cpu().numpy();opacity=g.get_opacity[select,0].cpu().numpy()
        np.savez_compressed(root/'large_background_descendants.npz',init_id=parent,xyz=xyz,scale=scales,opacity=opacity,
            normal_displacement=normal.cpu().numpy(),tangent_displacement=tangent.cpu().numpy())
        ancestors,counts=np.unique(parent,return_counts=True)
        def stats(values):
            values=np.asarray(values)
            return dict(min=float(values.min()),median=float(np.median(values)),p95=float(np.quantile(values,.95)),max=float(values.max())) if values.size else None
        write(root/'large_background_descendants.json',dict(iteration=iteration,
            checkpoint_state='saved model before scheduled iteration-7000 densification',
            initial_large_background_count=int(self.initial_large_background.sum()),surviving_gaussians=len(parent),
            surviving_original_ancestors=len(ancestors),counts_by_ancestor=dict(zip(map(str,ancestors.tolist()),counts.tolist())),
            size_max_axis_m=stats(scales.max(1) if len(scales) else []),opacity=stats(opacity),
            normal_displacement_abs_m=stats(normal.abs().cpu().numpy()),tangent_displacement_m=stats(tangent.cpu().numpy()),
            parent_or_child='combined surviving descendants; immutable init_id retains original ancestor across clone/split/prune',
            floating_conclusion='requires evaluation mesh first hits; tangential spread alone is not a floating surface',
            stop_criterion=False,scientific_verdict=None))

    @torch.no_grad()
    def checkpoint_evidence(self,iteration,g,renderer,pipe,background):
        if iteration!=7000:return
        root=self.mon.parent/'check7000';root.mkdir(exist_ok=False)
        self.large_background_evidence(iteration,g,root)
        depthroot=root/'renders';depthroot.mkdir()
        labels=torch.zeros((len(g._xyz),3),device=g._xyz.device)
        labels[:,0]=(g.origin==0).float()
        labels[:,1]=self.initial_large_background[g.init_id.long()].float()
        labels[:,2]=(g.origin==1).float()
        views=[];inside=0;denominator=0
        for cam in sorted(self.scene.getTrainCameras(),key=lambda c:c.image_name):
            pkg=renderer(cam,g,pipe,background)
            depth=pkg['surf_depth'].squeeze().detach().cpu().numpy()
            m=self.maps[cam.image_name];target=m['depth'].numpy();sigma=m['sigma'].numpy()
            good=np.isfinite(target)&(target>0)&np.isfinite(sigma)&(sigma>0)
            ok=good&np.isfinite(depth)&(depth>0)&(abs(depth-target)<=1.96*sigma)
            count=int(ok.sum());total=int(good.sum());inside+=count;denominator+=total
            dest=depthroot/(cam.image_name+'.npz')
            attribution=renderer(cam,g,pipe,torch.zeros_like(background),override_color=labels)
            alpha=attribution['rend_alpha'].clamp_min(1e-8)
            fraction=(attribution['render']/alpha).clamp(0,1).permute(1,2,0).cpu().numpy()
            np.savez_compressed(dest,depth=depth,rgb=(pkg['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype(np.uint8),
                origin_fraction=fraction.astype(np.float32),alpha=attribution['rend_alpha'].squeeze().cpu().numpy())
            views.append(dict(camera=cam.image_name,inside=count,target_pixels=total,
                K=self.index['views'][cam.image_name]['K'],W2C=self.index['views'][cam.image_name]['W2C']))
        coverage=inside/denominator if denominator else None
        record=dict(iteration=iteration,inside=inside,target_pixels=denominator,fraction=coverage,criterion=.8,
            status='PASS' if coverage is not None and coverage>=.8 else 'FAIL',views=views,
            origin_fraction_channels=['background','initial_background_over_1m_ancestry','prior'],
            attribution='alpha-normalized rendered contributions with fixed membership colours; diagnostics only',scientific_verdict=None)
        write(root/'coverage.json',record)
        if record['status']!='PASS':
            write(self.mon/'STOP.json',dict(iteration=iteration,reason='target_coverage_below_0.8',fraction=coverage,scientific_verdict=None))
            raise RuntimeError('TARGET_STOP_COVERAGE')

    @torch.no_grad()
    def observe(self,iteration,g,loss,rgb,depth,name):
        if iteration%100 and iteration!=1:return
        ids=g.init_id.long();prior=g.origin==1
        opacity=float(g.get_opacity.median()) if len(ids) else None
        prior_opacity=float(g.get_opacity[prior].median()) if prior.any() else None
        excess_float32=float((((g._xyz-self.anchor[ids])*self.normal[ids]).sum(1).abs()-1.96*self.sigma[ids]).max())
        excess=float((((g._xyz.double()-self.anchor[ids].double())*self.normal[ids].double()).sum(1).abs()-(1.96*self.sigma[ids]).double()).max())
        row=dict(iteration=iteration,gaussians=len(ids),target_opacity_median=opacity,max_normal_excess_m=excess,
            loss=float(loss),rgb_loss=float(rgb),target_depth_loss=float(depth),camera=name,
            max_normal_excess_float32_reference_m=excess_float32,
            bound_check_arithmetic='float64 dot product of stored float32 coordinates; unchanged 3e-5 m tolerance',
            opacity_population='all target-bound descendants including MVS background',prior_opacity_median=prior_opacity,scientific_verdict=None)
        with (self.mon/'curve.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        if iteration==6000:self.n6000=len(ids)
        reason=None
        if not torch.isfinite(g._xyz).all():reason='nonfinite_position'
        elif excess>3e-5:reason='normal_bound_violation'
        elif iteration>=7000 and (opacity is None or opacity<.05):reason='target_opacity_median_below_0.05'
        elif iteration==7000 and self.n6000 is not None and len(ids)>3*self.n6000:reason='count_gt_3x_6000'
        if reason:
            self.snapshot(iteration,g)
            write(self.mon/'STOP.json',dict(row,reason=reason))
            raise RuntimeError('TARGET_STOP_'+reason)
        if iteration in [6000,7000,30000]:
            write(self.mon/f'health_{iteration}.json',dict(row,count_at_6000=self.n6000,status='PASS_HEALTH',scientific_verdict=None))
        if iteration%1000==0:print('[target]',row,flush=True)


@torch.no_grad()
def create(args,scene,g,render,pipe):
    if getattr(args,'jbgs_targets',None):
        from jbgs_gtjudge import verify_override
        verify_override(args,Path(args.jbgs_target_dir))
    if getattr(args,'jbgs_finaltrain','off')=='on':
        if args.jbgs_target!='on' or args.jbgs_target_rev!='r8':
            raise ValueError('FINALTRAIN requires the unchanged r8 controller base')
        from jbgs_finaltrain import FinalTrain
        return FinalTrain(args,scene,g)
    if args.jbgs_target=='on' and args.jbgs_target_rev=='r8':
        from jbgs_target_r8 import TargetR8
        return TargetR8(args,scene,g)
    if args.jbgs_target=='on' and args.jbgs_target_rev=='r7':
        from jbgs_target_r7 import TargetR7
        return TargetR7(args,scene,g)
    if args.jbgs_target=='on' and args.jbgs_target_rev=='r6':
        from jbgs_target_r6 import TargetR6
        return TargetR6(args,scene,g)
    return Target(args,scene,g) if args.jbgs_target=='on' else None
