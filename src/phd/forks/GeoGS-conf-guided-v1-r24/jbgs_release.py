"""r24: opt-in release interventions; default decisions delegate to r23.

Event records do not query GT. Expensive nearest-tangent diagnosis is deferred
to CPU postprocessing of immutable event coordinates and frozen targets.
"""
import json,time
from pathlib import Path
import numpy as np
import torch
from jbgs_finaltrain import FinalTrain
from jbgs_target_r6 import META
from jbgs_target import write
from release_search import TangentTree
from utils.general_utils import build_rotation

TRACK=('rl_uid','rl_event','rl_birth','rl_birth_kind','rl_last_xyz','rl_parent_scale','rl_parent_normal','rl_delete')

class Release(FinalTrain):
    def __init__(self,args,scene,g):
        self.release_rule=args.jbgs_release_rule;self.release_log=args.jbgs_release_log
        self._tracking_ready=False;self._deleting=False;self._tangent_tree=None
        self.next_uid=0;self.next_event=0;self.batch_number=0;self.action_totals={'pull':0,'delete':0,'release':0}
        super().__init__(args,scene,g)
        if self.tracking():self.initialize_tracking(g)

    def tracking(self):return getattr(self,'release_log','off')=='on' or getattr(self,'release_rule','release')!='release'

    def initialize_tracking(self,g):
        n=len(g._xyz);dev=g._xyz.device
        self._deleting=False;self._tangent_tree=None;self.next_uid=n;self.next_event=0;self.batch_number=0
        self.action_totals={'pull':0,'delete':0,'release':0}
        g.rl_uid=torch.arange(n,device=dev,dtype=torch.int64)
        g.rl_event=torch.full((n,),-1,device=dev,dtype=torch.int64)
        g.rl_birth=torch.zeros(n,device=dev,dtype=torch.int32);g.rl_birth_kind=torch.zeros(n,device=dev,dtype=torch.int8)
        g.rl_last_xyz=g._xyz.detach().clone();g.rl_parent_scale=torch.full((n,),float('nan'),device=dev)
        g.rl_parent_normal=torch.full((n,3),float('nan'),device=dev);g.rl_delete=torch.zeros(n,device=dev,dtype=torch.bool)
        self._tracking_ready=True

    def tangential(self,xyz):
        if getattr(self,'_tangent_tree',None) is None:
            self._tangent_tree=TangentTree(self.points,self.patch_normal.double().cpu().numpy(),(1.96*self.patch_sigma).double().cpu().numpy(),self.valid_patch)
        return self._tangent_tree.query(xyz.detach().double().cpu().numpy())

    @torch.no_grad()
    def record(self,g,rows,reason,action,old_index=None):
        if not len(rows):return
        n=len(rows);ids=torch.arange(self.next_event,self.next_event+n,device=rows.device,dtype=torch.int64);self.next_event+=n
        if action=='release':g.rl_event[rows]=ids
        self.action_totals[action]+=n
        if self.release_log!='on' and action=='release':return
        old=g.target_index[rows] if old_index is None else old_index
        valid=old>=0;normal=torch.zeros((n,3),device=rows.device,dtype=torch.float64)
        normal[valid]=self.patch_normal[old[valid]].double()
        delta=g._xyz[rows].double()-g.rl_last_xyz[rows].double();hn=(delta*normal).sum(1)
        data=dict(event_id=ids.cpu().numpy(),uid=g.rl_uid[rows].cpu().numpy(),init_id=g.init_id[rows].cpu().numpy(),
          xyz=g._xyz[rows].cpu().numpy(),previous_check_xyz=g.rl_last_xyz[rows].cpu().numpy(),previous_target_index=old.cpu().numpy(),
          birth_iteration=g.rl_birth[rows].cpu().numpy(),birth_kind=g.rl_birth_kind[rows].cpu().numpy(),
          movement_normal_m=hn.cpu().numpy(),movement_tangent_m=torch.linalg.vector_norm(delta-hn[:,None]*normal,dim=1).cpu().numpy(),
          longest_axis_m=g.get_scaling[rows].max(1).values.cpu().numpy(),opacity=g.get_opacity[rows,0].cpu().numpy(),
          parent_longest_axis_m=g.rl_parent_scale[rows].cpu().numpy(),parent_disk_normal=g.rl_parent_normal[rows].cpu().numpy())
        if getattr(self,'mon',None) is not None:
            folder=self.mon/'release_events';folder.mkdir(exist_ok=True)
            name=f'{self.batch_number:06d}_{self.iteration}_{action}';self.batch_number+=1
            np.savez_compressed(folder/(name+'.npz'),**data)
            write(folder/(name+'.json'),dict(iteration=self.iteration,reason=reason,action=action,count=n,
              cause='100_step' if reason=='periodic' else 'density_control',
              classification='deferred exact CPU nearest-tangent query; targets only',scientific_verdict=None))

    @torch.no_grad()
    def reattach(self,g,reason):
        if getattr(self,'_deleting',False):return
        rule=getattr(self,'release_rule','release')
        if rule=='release':
            if not self.tracking() or not getattr(self,'_tracking_ready',False):return super().reattach(g,reason)
            rows=torch.where(g.target_tag==1)[0]
            super().reattach(g,reason)
            lost=rows[g.target_tag[rows]==2]
            self.record(g,lost,reason,'release')
            g.rl_last_xyz[rows]=g._xyz[rows].detach()
            return
        rows=torch.where((g.origin==1)&((g.target_tag==1)|((g.target_tag==2)&(rule=='pull')))&~g.rl_delete)[0]
        if not len(rows):return
        tangent,excess,idx=self.candidates(g._xyz[rows]);ok=np.isfinite(tangent)
        failure=np.flatnonzero(~ok);near=np.zeros(len(rows),bool)
        if len(failure) and rule in ['pull','mix']:
            t,e,j=self.tangential(g._xyz[rows[torch.as_tensor(failure,device=rows.device)]])
            near[failure]=t<=.5;idx[failure]=j
        keep=ok|near;kt=torch.tensor(keep,device=rows.device);old=g.target_index[rows].clone()
        if kt.any():g.target_index[rows[kt]]=torch.as_tensor(idx[keep],device=rows.device);g.target_tag[rows[kt]]=1
        pulling=rows[torch.tensor(near,device=rows.device)]
        if len(pulling):self.record(g,pulling,reason,'pull',old[torch.tensor(near,device=rows.device)])
        lost=rows[~kt]
        if len(lost):
            if rule in ['delete','mix']:
                self.record(g,lost,reason,'delete',old[~kt]);g.rl_delete[lost]=True;g.target_tag[lost]=2
            else:
                newly=lost[g.target_tag[lost]==1];g.target_tag[lost]=2;g.target_released_at[newly]=self.iteration
                self.record(g,newly,reason,'release')
        # Retain the inherited projection for existing valid candidates. Pulls
        # enter the interval through this same constraint at the next update.
        if getattr(self,'mon',None) is not None:
            with (self.mon/'interventions.jsonl').open('a') as f:f.write(json.dumps(dict(iteration=self.iteration,reason=reason,queried=len(rows),pulled=len(pulling),removed=len(lost) if rule in ['delete','mix'] else 0,released=len(lost) if rule=='pull' else 0,rule=rule))+'\n')
        g.rl_last_xyz[rows]=g._xyz[rows].detach()
        if reason=='periodic':self.flush_deletions(g)

    @torch.no_grad()
    def flush_deletions(self,g):
        if not self.tracking() or not getattr(self,'_tracking_ready',False) or not g.rl_delete.any():return
        self._deleting=True
        try:g.prune_points(g.rl_delete.clone())
        finally:self._deleting=False

    def child_metadata(self,g,selected,n):
        data=super().child_metadata(g,selected,n)
        if not self.tracking():return data
        count=int(selected.sum())*n;dev=g._xyz.device
        for k in TRACK:data[k]=getattr(g,k)[selected].repeat((n,1) if getattr(g,k).ndim==2 else n)
        data['rl_uid']=torch.arange(self.next_uid,self.next_uid+count,device=dev,dtype=torch.int64);self.next_uid+=count
        data['rl_birth']=torch.full((count,),self.iteration,device=dev,dtype=torch.int32)
        data['rl_birth_kind']=torch.full((count,),2 if n>1 else 1,device=dev,dtype=torch.int8)
        data['rl_parent_scale']=g.get_scaling[selected].max(1).values.repeat(n)
        data['rl_parent_normal']=build_rotation(g._rotation[selected])[:,:,2].repeat(n,1)
        return data

    def extended(self,g,meta):
        if not self.tracking():return super().extended(g,meta)
        for k in META+TRACK:setattr(g,k,torch.cat([getattr(g,k),meta[k]]))
        self.reattach(g,'clone_or_split')

    def pruned(self,g,keep):
        if not self.tracking():return super().pruned(g,keep)
        for k in META+TRACK:setattr(g,k,getattr(g,k)[keep])
        self.reattach(g,'prune')

    def capture(self,g):
        v=super().capture(g)
        if self.tracking() and getattr(self,'_tracking_ready',False):
            v['release_state']=dict(meta={k:getattr(g,k).detach().cpu().clone() for k in TRACK},next_uid=self.next_uid,next_event=self.next_event,action_totals=self.action_totals)
        return v

    @torch.no_grad()
    def snapshot(self,iteration,g):
        super().snapshot(iteration,g)
        if iteration in [7000,15000,30000] and self.tracking() and getattr(self,'_tracking_ready',False):
            np.savez_compressed(self.mon/f'release_snapshot_{iteration}.npz',**{k:getattr(g,k).cpu().numpy() for k in TRACK})
            write(self.mon/f'release_actions_{iteration}.json',dict(iteration=iteration,counts=self.action_totals,scientific_verdict=None))
