"""Opt-in r6: free background, irreversible release, local frozen-patch reassignment.

No GT or new judgment enters this controller. Immutable init_id/origin are separate
from the mutable tag/target association. All geometry queries use float64.
"""
import copy, hashlib, json, random
from pathlib import Path
import numpy as np
import torch
from scipy.spatial import cKDTree
from jbgs_target import Target, normal_projection, write
META=('target_tag','target_index','target_released_at')

class TargetR6(Target):
    def __init__(self,args,scene,g):
        self.ready=False
        super().__init__(args,scene,g)
        target_file=self.root.parent.parent/'targets'/(self.root.name+'.npz')
        with np.load(target_file) as z:
            self.valid_patch=np.flatnonzero((z['region']>=0)&np.isfinite(z['target']).all(1)&np.isfinite(z['normal']).all(1)&np.isfinite(z['sigma'])&(z['sigma']>0))
            self.points=np.asarray(z['target'][self.valid_patch],np.float64)
            self.patch_anchor=torch.tensor(self.points,device=g._xyz.device,dtype=torch.float32)
            self.patch_normal=torch.tensor(z['normal'][self.valid_patch],device=g._xyz.device,dtype=torch.float32)
            self.patch_sigma=torch.tensor(z['sigma'][self.valid_patch],device=g._xyz.device,dtype=torch.float32)
            self.patch_region=torch.tensor(z['region'][self.valid_patch],device=g._xyz.device,dtype=torch.int8)
            inverse=np.full(len(z['region']),-1,np.int64);inverse[self.valid_patch]=np.arange(len(self.valid_patch))
        self.tree=cKDTree(self.points);self.target_hash=hashlib.sha256(target_file.read_bytes()).hexdigest()
        with np.load(self.root/'seeds.npz') as z:
            index=np.full(len(z['origin']),-1,np.int64);prior=z['origin']==1;index[prior]=inverse[z['patch'][prior]]
        assert (index[prior]>=0).all()
        g.target_tag=g.origin.clone();g.target_index=torch.tensor(index,device=g._xyz.device)
        g.target_released_at=torch.full((len(index),),-1,device=g._xyz.device,dtype=torch.int32)
        g.target_r6=self;self.iteration=0;self.events=[];self.n6000=None;self.ready=True
        self.snapshot(0,g)

    def nearest(self,xyz):
        # Exact cKDTree distance; deterministic lowest original patch index on ties.
        q=xyz.detach().double().cpu().numpy();dist,idx=self.tree.query(q,k=2,workers=1)
        if not len(q):return np.empty(0),np.empty(0,np.int64)
        first=idx[:,0].copy();d=dist[:,0].copy()
        ties=np.flatnonzero((dist[:,1]<=.5)&np.isclose(dist[:,0],dist[:,1],rtol=0,atol=1e-12))
        for i in ties:
            candidates=np.asarray(self.tree.query_ball_point(q[i],d[i]+1e-12),np.int64)
            dd=np.linalg.norm(self.points[candidates]-q[i],axis=1);minimum=dd.min()
            first[i]=candidates[np.flatnonzero(dd==minimum)].min();d[i]=minimum
        return d,first

    @torch.no_grad()
    def reattach(self,g,reason):
        rows=torch.where(g.target_tag==1)[0]
        if not len(rows):return
        d,idx=self.nearest(g._xyz[rows]);ok=torch.tensor(d<=.5,device=rows.device)
        new=torch.tensor(idx,device=rows.device);changed=int((g.target_index[rows[ok]]!=new[ok]).sum())
        g.target_index[rows[ok]]=new[ok]
        released=rows[~ok];g.target_tag[released]=2;g.target_released_at[released]=self.iteration
        before=g._xyz[rows[ok]].clone();self.project_bounds(g)
        move=float(torch.linalg.vector_norm(g._xyz[rows[ok]].double()-before.double(),dim=1).max()) if ok.any() else 0.
        if move>.5+3e-5:raise RuntimeError('R6_REATTACH_PROJECTION_GT_HALF_METRE')
        row=dict(iteration=self.iteration,reason=reason,queried=len(rows),attached=int(ok.sum()),changed_target=changed,
            released=len(released),max_projection_m=move,current_patch=int((g.target_tag==1).sum()),
            current_released=int((g.target_tag==2).sum()),initial_prior_descendants=int((g.origin==1).sum()))
        self.events.append(row)
        if getattr(self,'mon',None) is not None:
            with (self.mon/'reattach.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')

    @torch.no_grad()
    def project_bounds(self,g):
        rows=torch.where(g.target_tag==1)[0];idx=g.target_index[rows]
        if len(rows):g._xyz[rows]=normal_projection(g._xyz[rows],self.patch_anchor[idx],self.patch_normal[idx],self.patch_sigma[idx])

    def child_metadata(self,g,selected,n):return {k:getattr(g,k)[selected].repeat(n) for k in META}
    def extended(self,g,meta):
        if meta is None:raise RuntimeError('R6_CHILD_WITHOUT_PARENT_METADATA')
        for k in META:setattr(g,k,torch.cat([getattr(g,k),meta[k]]))
        self.reattach(g,'clone_or_split')
    def pruned(self,g,keep):
        for k in META:setattr(g,k,getattr(g,k)[keep])
        self.reattach(g,'prune')

    def capture(self,g):
        return dict(meta={k:getattr(g,k).detach().cpu().clone() for k in META},events=copy.deepcopy(self.events),
            n6000=self.n6000,iteration=self.iteration,target_sha256=self.target_hash,
            seed_sha256=hashlib.sha256((self.root/'seeds.npz').read_bytes()).hexdigest(),
            maps_index_sha256=hashlib.sha256((self.root/'maps/index.json').read_bytes()).hexdigest())

    @torch.no_grad()
    def snapshot(self,iteration,g):
        if not self.ready:return
        # Initial anchors preserve movement provenance; association fields are per current Gaussian.
        data=dict(xyz=g._xyz.detach().cpu().numpy(),init_id=g.init_id.cpu().numpy(),origin=g.origin.cpu().numpy(),
            opacity=g.get_opacity[:,0].cpu().numpy(),scale=g.get_scaling.cpu().numpy(),rotation=g.get_rotation.cpu().numpy(),
            initial_scale=self.initial_scale.cpu().numpy(),initial_large_background=self.initial_large_background.cpu().numpy(),
            anchor=self.anchor.cpu().numpy(),normal=self.normal.cpu().numpy(),sigma=self.sigma.cpu().numpy(),region=self.region.cpu().numpy(),
            patch_ids=self.valid_patch,patch_anchor=self.patch_anchor.cpu().numpy(),patch_normal=self.patch_normal.cpu().numpy(),
            patch_sigma=self.patch_sigma.cpu().numpy(),patch_region=self.patch_region.cpu().numpy())
        data.update({k:getattr(g,k).cpu().numpy() for k in META})
        np.savez_compressed(self.mon/f'snapshot_{iteration}.npz',**data)
        write(self.mon/f'reattach_{iteration}.json',dict(iteration=iteration,events=self.events,scientific_verdict=None))

    @torch.no_grad()
    def observe(self,iteration,g,loss,rgb,depth,name):
        if iteration%100 and iteration!=1:return
        prior=g.origin==1;patch=g.target_tag==1;idx=g.target_index[patch]
        excess=float((((g._xyz[patch].double()-self.patch_anchor[idx].double())*self.patch_normal[idx].double()).sum(1).abs()-(1.96*self.patch_sigma[idx]).double()).max()) if patch.any() else None
        median=float(g.get_opacity[prior].median()) if prior.any() else None
        row=dict(iteration=iteration,gaussians=len(g._xyz),target_opacity_median=median,prior_opacity_median=median,
            patch_opacity_median=float(g.get_opacity[patch].median()) if patch.any() else None,
            max_normal_excess_m=excess,loss=float(loss),rgb_loss=float(rgb),target_depth_loss=float(depth),camera=name,
            tags={str(i):int((g.target_tag==i).sum()) for i in range(3)},opacity_population='immutable prior-seed lineage including released',scientific_verdict=None)
        with (self.mon/'curve.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        if iteration==6000:self.n6000=len(g._xyz)
        reason=None
        if not torch.isfinite(g._xyz).all():reason='nonfinite_position'
        elif excess is not None and excess>3e-5:reason='normal_bound_violation'
        elif iteration>=7000 and (median is None or median<.05):reason='prior_seed_lineage_opacity_median_below_0.05'
        elif iteration==7000 and self.n6000 is not None and len(g._xyz)>3*self.n6000:reason='count_gt_3x_6000'
        if reason:
            write(self.mon/'STOP.json',dict(row,reason=reason));raise RuntimeError('TARGET_STOP_'+reason)
        if iteration in [6000,7000,15000,30000]:write(self.mon/f'health_{iteration}.json',dict(row,count_at_6000=self.n6000,status='PASS_HEALTH'))
        if iteration%1000==0:print('[target r6]',row,flush=True)

    @torch.no_grad()
    def checkpoint_evidence(self,iteration,g,renderer,pipe,background):
        if iteration not in [7000,15000,30000]:return
        root=self.mon.parent/f'check{iteration}';root.mkdir(exist_ok=False);(root/'renders').mkdir()
        self.large_background_evidence(iteration,g,root)
        labels=torch.stack([(g.target_tag==i).float() for i in [0,2,1]],dim=1)
        distance,_=self.nearest(g._xyz);near=torch.tensor(distance<=.5,device=g._xyz.device)
        near_labels=torch.stack([((g.target_tag==i)&near).float() for i in [0,2,1]],dim=1)
        views=[];inside=total=0;near_sums=np.zeros(3,np.float64)
        for cam in sorted(self.scene.getTrainCameras(),key=lambda c:c.image_name):
            pkg=renderer(cam,g,pipe,background);depth=pkg['surf_depth'].squeeze().cpu().numpy()
            m=self.maps[cam.image_name];target=m['depth'].numpy();sigma=m['sigma'].numpy()
            good=np.isfinite(target)&(target>0)&np.isfinite(sigma)&(sigma>0)
            ok=good&np.isfinite(depth)&(depth>0)&(abs(depth-target)<=1.96*sigma)
            count=int(ok.sum());den=int(good.sum());inside+=count;total+=den
            a=renderer(cam,g,pipe,torch.zeros_like(background),override_color=labels)
            alpha=a['rend_alpha'].clamp_min(1e-8);fraction=(a['render']/alpha).clamp(0,1).permute(1,2,0).cpu().numpy()
            nr=renderer(cam,g,pipe,torch.zeros_like(background),override_color=near_labels)
            nf=(nr['render']/alpha).clamp(0,1).permute(1,2,0).cpu().numpy();near_sums+=nf[good].sum(0,dtype=np.float64)
            np.savez_compressed(root/'renders'/(cam.image_name+'.npz'),depth=depth,
                rgb=(pkg['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype(np.uint8),
                origin_fraction=fraction.astype(np.float32),near_origin_fraction=nf.astype(np.float32),alpha=a['rend_alpha'].squeeze().cpu().numpy())
            views.append(dict(camera=cam.image_name,inside=count,target_pixels=den,K=self.index['views'][cam.image_name]['K'],W2C=self.index['views'][cam.image_name]['W2C']))
        write(root/'coverage.json',dict(iteration=iteration,inside=inside,target_pixels=total,fraction=inside/total if total else None,
            criterion=None,reference=.8,status='RECORD_ONLY',views=views,origin_fraction_channels=['background','released','patch'],
            near_target_counts={str(i):int(((g.target_tag==i)&near).sum()) for i in range(3)},
            near_target_mean_contribution=(near_sums/total).tolist() if total else None,
            attribution='alpha-normalized tag contribution, record only',scientific_verdict=None))
        print('R6_READOUT_COMPLETE',iteration,inside,total,flush=True)


def restore_complete(path,state,env):
    """Resume exact end-of-iteration state, with no historical stage-switch branching."""
    import jbgs_state as S
    args,g,scene=env['args'],env['gaussians'],env['scene'];control=env['target_control']
    if args.jbgs_target!='on' or args.jbgs_target_rev!='r6':raise ValueError('r6 state needs r6 controller')
    assert state['schema']==S.SCHEMA and state['implementation_hashes']==S.implementation_hashes()
    assert state['optimization']==vars(env['opt'])
    allowed=S.NON_METHOD_ARGS|{'jbgs_resume_full','jbgs_stop_after','jbgs_capture_iterations'}
    differences={k:[v,getattr(args,k)] for k,v in state['args'].items() if k not in allowed and getattr(args,k)!=v}
    if differences:raise ValueError(f'R6 resume settings changed: {differences}')
    assert state['input_manifest_sha256']==(S.digest(args.jbgs_input_manifest) if args.jbgs_input_manifest else None)
    saved=state['target_r6'];current=control.capture(g)
    for k in ['target_sha256','seed_sha256','maps_index_sha256']:assert saved[k]==current[k],k
    g.restore(state['model'],env['opt'])
    for k in ['origin','init_id','frozen_mask','completed_mask']:
        value=state[k];setattr(g,k,None if value is None else value.to(g._xyz.device))
    for k,v in saved['meta'].items():setattr(g,k,v.to(g._xyz.device))
    control.n6000=saved['n6000'];control.events=saved['events'];control.iteration=saved['iteration'];g.target_r6=control
    building=state['building_freeze_mask'];out=dict(state['runtime'],first_iter=state['iteration'],building_freeze_mask=None if building is None else building.to(g._xyz.device))
    for role,cameras in [('train',scene.getTrainCameras()),('test',scene.getTestCameras())]:
        by_name={c.image_name:c for c in cameras};assert set(by_name)==set(state[role+'_order'])
        cameras[:]=[by_name[n] for n in state[role+'_order']]
    by_name={c.image_name:c for c in scene.getTrainCameras()};stack=state['viewpoint_stack']
    out['viewpoint_stack']=None if stack is None else [by_name[n] for n in stack]
    random.setstate(state['rng']['python']);np.random.set_state(state['rng']['numpy'])
    torch.set_rng_state(state['rng']['torch_cpu'].cpu());torch.cuda.set_rng_state_all([v.cpu() for v in state['rng']['torch_cuda']])
    write(Path(args.model_path)/'jbgs_restore.json',dict(checkpoint=str(path),checkpoint_sha256=S.digest(path),iteration=state['iteration'],
        target_state=True,optimizer_state=True,rng_and_camera_state=True,scientific_verdict=None))
    return out
