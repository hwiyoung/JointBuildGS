"""r8 monitoring; all patch controller behavior inherited unchanged from r7."""
import json
import torch
from jbgs_target_r7 import TargetR7
from jbgs_target import write

class TargetR8(TargetR7):
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
        if iteration%1000==0:
            memory=dict(iteration=iteration,gaussians=len(g._xyz),tags=row['tags'],count_at_6000=self.n6000,
                allocated_bytes=torch.cuda.memory_allocated(),reserved_bytes=torch.cuda.memory_reserved(),
                peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                free_bytes=torch.cuda.mem_get_info()[0],total_bytes=torch.cuda.mem_get_info()[1],scientific_verdict=None)
            with (self.mon/'memory_1000.jsonl').open('a') as f:f.write(json.dumps(memory)+'\n')
        reason=None
        if not torch.isfinite(g._xyz).all() or not torch.isfinite(loss):reason='nonfinite_position_or_loss'
        elif excess is not None and excess>3e-5:reason='normal_bound_violation'
        elif iteration>=7000 and not grace and (median is None or median<.05):reason='prior_seed_lineage_opacity_median_below_0.05'
        elif iteration>=7000 and iteration%1000==0 and self.n6000 is not None and len(g._xyz)>3*self.n6000:reason='count_gt_3x_6000'
        if reason:write(self.mon/'STOP.json',dict(row,reason=reason));raise RuntimeError('TARGET_STOP_'+reason)
        if iteration in [6000,7000,15000,30000]:write(self.mon/f'health_{iteration}.json',dict(row,count_at_6000=self.n6000,status='PASS_HEALTH'))
        if iteration%1000==0:print('[target r8]',row,flush=True)
