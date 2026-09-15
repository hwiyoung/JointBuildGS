"""All-bound-camera frozen support with R1 alpha; copied as jbgs_region_weight.

The exact previously tested weighted L1 and detached-forward algebra are reused
from jbgs_weight_core. No native camera draw, optimizer, or prior update changes.
"""
from pathlib import Path
import hashlib
import json
import os

import numpy as np
import torch

try:
    from jbgs_weight_core import weighted_metric_depth_loss, first_forward_algebra, validate_alpha, _maps, _subset_stats, sha256, _write
except ModuleNotFoundError:
    from src.phd.p1_single_view_weight_v1.loss import weighted_metric_depth_loss, first_forward_algebra, validate_alpha, _maps, _subset_stats, sha256, _write

PROVENANCE_NAME='region_weight_source_provenance.json'
SOURCE_SCHEMA='JBGS_REGION_WEIGHT_SOURCE_v1'


def load_masks(path, expected_sha, views):
    path=Path(path)
    if sha256(path)!=expected_sha: raise ValueError('Mask manifest hash differs')
    manifest=json.loads(path.read_text())
    rows=manifest['views']
    if len(rows)!=len(views) or {r['camera'] for r in rows}!=set(views):
        raise ValueError('Mask and MVS train camera membership differ')
    masks={}
    for row in rows:
        file=(path.parent/row['path']).resolve()
        file.relative_to(path.parent.resolve())
        if sha256(file)!=row['sha256']: raise ValueError('Mask bytes changed')
        with np.load(file,allow_pickle=False) as data:
            labels=np.array(data['region_id'],copy=True)
            valid=np.array(data['valid'],copy=True)
        v=views[row['camera']]
        if labels.shape!=(v['height'],v['width']) or valid.dtype!=np.bool_ or valid.shape!=labels.shape:
            raise ValueError('Mask camera raster differs')
        if not np.isin(labels,[1,2,3,4,5,6]).all(): raise ValueError('Incomplete mask partition')
        use=np.isin(labels,[1,2,3]); r1=labels==1
        if np.any(use&~valid): raise ValueError('Invalid depth included in support')
        if int(r1.sum())!=row['r1_pixels'] or int(use.sum())!=row['used_pixels']:
            raise ValueError('Mask counts differ')
        masks[row['camera']]=(torch.from_numpy(r1),torch.from_numpy(use))
    return manifest,masks


class Controller:
    def __init__(self,model_path,args,mvs_control,environment=None):
        env=os.environ if environment is None else environment
        if (env.get('JBGS_MVS_PGSR_MODE')!='mvs' or env.get('JBGS_MVS_REGION') not in ('P2','P3')
            or args.dynamic_depth_weight or args.lambda_da_depth!=.05 or args.lambda_lod_anchor!=.005
            or args.use_confidence or args.use_scale_invariant or args.jbgs_release_protection
            or args.stage_switch_iter!=8000 or not args.jbgs_resume_full
            or not args.freeze_onlybldg or not args.protect_bldg):
            raise ValueError('Require protected Anchor8k, MVS-only, fixed visual .05/prior .005')
        self.region=env['JBGS_MVS_REGION']; self.alpha=validate_alpha(float(env['JBGS_REGION_WEIGHT_ALPHA']))
        self.manifest_sha=env['JBGS_REGION_WEIGHT_MASK_SHA256']
        self.manifest,self.masks=load_masks(env['JBGS_REGION_WEIGHT_MASK'],self.manifest_sha,mvs_control.views)
        if self.manifest['region']!=self.region or self.manifest['binding_sha256']!=mvs_control.binding_sha:
            raise ValueError('Mask region or depth binding differs')
        self.output=Path(model_path); self.last_iteration=8000; self.first_algebra=True; self.seen=set()
        _write(self.output/'region_weight_binding.json',dict(schema='JBGS_REGION_WEIGHT_BINDING_v1',scientific_verdict=None,
            region=self.region,alpha=self.alpha,mask_sha256=self.manifest_sha,train_camera_count=len(self.masks),
            mvs_binding_sha256=mvs_control.binding_sha,views=self.manifest['views'],
            fixed_mvs_weight=.05,fixed_prior_weight=.005,dynamic_depth_weight=False,native_protection=True,
            other_used_multiplier=1,excluded_multiplier=0,all_train_views_masked=True,
            normalization='original_per_view_valid_pixel_count_with_frozen_support'))

    def apply(self,pred_depth,target_depth,native_loss,*,camera,iteration):
        if iteration!=self.last_iteration+1 or camera not in self.masks:
            raise ValueError('Unexpected iteration/camera in frozen train schedule')
        self.last_iteration=iteration
        if target_depth is None: raise ValueError('Bound camera has no MVS raster')
        _write(self.output/'region_weight_camera_trace.jsonl',dict(iteration=iteration,camera=camera),'a')
        if iteration==8001:
            _write(self.output/'region_weight_first_step.json',dict(iteration=iteration,camera=camera,
                native_mvs_loss=float(native_loss.detach()),scientific_verdict=None,
                pred_depth_sha256=hashlib.sha256(pred_depth.detach().cpu().contiguous().numpy().tobytes()).hexdigest()))
        mask,use=(x.to(device=pred_depth.device) for x in self.masks[camera])
        pred,target,valid=_maps(pred_depth,target_depth,mask,use)
        if self.first_algebra and bool((valid&mask).any()) and bool((valid&use&~mask).any()):
            algebra=first_forward_algebra(pred_depth,target_depth,mask,use)
            algebra.update(camera=camera,iteration=iteration,mask_sha256=self.manifest_sha)
            _write(self.output/'region_weight_first_algebra.json',algebra);self.first_algebra=False
        value=weighted_metric_depth_loss(pred_depth,target_depth,mask,self.alpha,use_mask=use)
        if camera not in self.seen or iteration%100==0:
            with torch.no_grad():
                count=int(valid.sum())
                baseline=(pred[valid]-target[valid]).abs().mean() if count else pred[valid].sum()
                if not torch.equal(baseline,native_loss.detach()): raise ValueError('Native metric L1 differs')
                _write(self.output/'region_weight_trace.jsonl',dict(iteration=iteration,camera=camera,
                    alpha=self.alpha,first_camera_visit=camera not in self.seen,native_valid_count=count,
                    native_loss=float(native_loss.detach()),applied_loss=float(value.detach()),
                    r1=_subset_stats(pred,target,valid&mask,count,self.alpha),
                    other_used=_subset_stats(pred,target,valid&use&~mask,count,1),
                    excluded=_subset_stats(pred,target,valid&~use,count,0),scientific_verdict=None),'a')
                self.seen.add(camera)
        return value


def verify_resume_source(state,source_root,current_hashes):
    root=Path(source_root); receipt=json.loads((root/PROVENANCE_NAME).read_text())
    if receipt.get('schema')!=SOURCE_SCHEMA or receipt.get('scientific_verdict') is not None:
        raise ValueError('Unexpected region source lineage')
    if current_hashes!=receipt['prepared_implementation_hashes']: raise ValueError('Prepared implementation changed')
    if sha256(root/'mvs_pgsr_source_provenance.json')!=receipt['parent_source_provenance_sha256']:
        raise ValueError('Parent source provenance changed')
    if state['implementation_hashes'] not in [receipt[k] for k in ('ancestor_anchor_implementation_hashes','parent_implementation_hashes','prepared_implementation_hashes')]:
        raise ValueError('Checkpoint outside exact source lineage')
    if state['source_sha256']!=state['implementation_hashes']['train.py']: raise ValueError('Checkpoint train hash differs')
    for name,expected in receipt['helper_sha256'].items():
        if sha256(root/name)!=expected: raise ValueError('Helper changed')
