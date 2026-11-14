"""r7: pair tangential locality with each target's normal uncertainty interval."""
import json
import numpy as np
import torch
from scipy.spatial import cKDTree
from jbgs_target_r6 import TargetR6
from jbgs_target import write


class TargetR7(TargetR6):
    def __init__(self,args,scene,g):
        super().__init__(args,scene,g)
        self.last_opacity_reset=-1
        self._candidate_cache=None

    def candidates(self,xyz):
        q=xyz.detach().double().cpu().numpy();n=len(q)
        chosen=np.zeros(n,np.int64);best_t=np.full(n,np.inf);best_e=np.full(n,np.inf)
        if getattr(self,'_candidate_cache',None) is None:
            normal=self.patch_normal.double().cpu().numpy();normal/=np.linalg.norm(normal,axis=1)[:,None]
            width=(1.96*self.patch_sigma).double().cpu().numpy()
            # Group by enclosing ball radius; wide targets do not inflate every query.
            radius=np.hypot(.5,width+.5);bins=np.floor(np.log2(radius)).astype(np.int32)
            groups=[]
            for key in np.unique(bins):
                ids=np.flatnonzero(bins==key);groups.append((ids,cKDTree(self.points[ids]),float(radius[ids].max())+1e-10))
            self._candidate_cache=(normal,width,groups)
        normal,width,groups=self._candidate_cache
        for start in range(0,n,512):
            stop=min(n,start+512);x=q[start:stop]
            for ids,tree,radius in groups:
                lists=tree.query_ball_point(x,radius,workers=1);lengths=np.fromiter(map(len,lists),dtype=np.int64,count=len(x))
                if not lengths.sum():continue
                row=np.repeat(np.arange(len(x)),lengths);idx=ids[np.concatenate(lists).astype(np.int64)]
                delta=x[row]-self.points[idx];h=np.einsum('ij,ij->i',delta,normal[idx]);tan=np.linalg.norm(delta-h[:,None]*normal[idx],axis=1)
                excess=np.maximum(abs(h)-width[idx],0);ok=(tan<=.5)&(excess<=.5)
                row,idx,tan,excess=row[ok],idx[ok],tan[ok],excess[ok]
                if not len(row):continue
                order=np.lexsort((self.valid_patch[idx],excess,tan,row));row,idx,tan,excess=row[order],idx[order],tan[order],excess[order]
                first=np.r_[True,row[1:]!=row[:-1]];row,idx,tan,excess=row[first]+start,idx[first],tan[first],excess[first]
                better=(tan<best_t[row])|((tan==best_t[row])&((excess<best_e[row])|((excess==best_e[row])&(self.valid_patch[idx]<self.valid_patch[chosen[row]]))))
                rr=row[better];chosen[rr]=idx[better];best_t[rr]=tan[better];best_e[rr]=excess[better]
        return best_t,best_e,chosen

    @torch.no_grad()
    def reattach(self,g,reason):
        rows=torch.where(g.target_tag==1)[0]
        if not len(rows):return
        tangent,excess,idx=self.candidates(g._xyz[rows]);ok=torch.tensor(np.isfinite(tangent),device=rows.device)
        new=torch.tensor(idx,device=rows.device);changed=int((g.target_index[rows[ok]]!=new[ok]).sum())
        g.target_index[rows[ok]]=new[ok];released=rows[~ok]
        g.target_tag[released]=2;g.target_released_at[released]=self.iteration
        before=g._xyz[rows[ok]].clone();self.project_bounds(g)
        move=float(torch.linalg.vector_norm(g._xyz[rows[ok]].double()-before.double(),dim=1).max()) if ok.any() else 0.
        if move>.5+3e-5:raise RuntimeError('R7_REATTACH_PROJECTION_GT_HALF_METRE')
        row=dict(iteration=self.iteration,reason=reason,queried=len(rows),attached=int(ok.sum()),changed_target=changed,released=len(released),max_projection_m=move,
            current_patch=int((g.target_tag==1).sum()),current_released=int((g.target_tag==2).sum()),initial_prior_descendants=int((g.origin==1).sum()),
            candidate_rule='tangent<=0.5 and normal excess outside uncertainty width<=0.5')
        self.events.append(row)
        if getattr(self,'mon',None) is not None:
            with (self.mon/'reattach.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')

    def capture(self,g):
        value=super().capture(g);value['last_opacity_reset']=getattr(self,'last_opacity_reset',-1);return value

    def opacity_grace(self,iteration):
        reset=getattr(self,'last_opacity_reset',-1)
        return reset>=0 and 0<=iteration-reset<=500

    @torch.no_grad()
    def observe(self,iteration,g,loss,rgb,depth,name):
        if iteration%100 and iteration!=1:return
        prior=g.origin==1;patch=g.target_tag==1;idx=g.target_index[patch]
        excess=float((((g._xyz[patch].double()-self.patch_anchor[idx].double())*self.patch_normal[idx].double()).sum(1).abs()-(1.96*self.patch_sigma[idx]).double()).max()) if patch.any() else None
        median=float(g.get_opacity[prior].median()) if prior.any() else None;grace=self.opacity_grace(iteration)
        row=dict(iteration=iteration,gaussians=len(g._xyz),target_opacity_median=median,prior_opacity_median=median,
            patch_opacity_median=float(g.get_opacity[patch].median()) if patch.any() else None,max_normal_excess_m=excess,loss=float(loss),rgb_loss=float(rgb),target_depth_loss=float(depth),camera=name,
            tags={str(i):int((g.target_tag==i).sum()) for i in range(3)},opacity_population='immutable prior-seed lineage including released',
            opacity_check_skipped_reset_grace=grace,last_opacity_reset=getattr(self,'last_opacity_reset',-1),scientific_verdict=None)
        with (self.mon/'curve.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        if iteration==6000:self.n6000=len(g._xyz)
        reason=None
        if not torch.isfinite(g._xyz).all() or not torch.isfinite(loss):reason='nonfinite_position_or_loss'
        elif excess is not None and excess>3e-5:reason='normal_bound_violation'
        elif iteration>=7000 and not grace and (median is None or median<.05):reason='prior_seed_lineage_opacity_median_below_0.05'
        elif iteration==7000 and self.n6000 is not None and len(g._xyz)>3*self.n6000:reason='count_gt_3x_6000'
        if reason:write(self.mon/'STOP.json',dict(row,reason=reason));raise RuntimeError('TARGET_STOP_'+reason)
        if iteration in [6000,7000,15000,30000]:write(self.mon/f'health_{iteration}.json',dict(row,count_at_6000=self.n6000,status='PASS_HEALTH'))
        if iteration%1000==0:print('[target r7]',row,flush=True)
