"""Explicit observation interventions; neither masking RGB nor releasing protection."""
import hashlib
import json
import os
from pathlib import Path
import numpy as np
import torch

BRANCH=os.environ.get('JBGS_COMPARISON_BRANCH','mvs')
INSIDE_MULTIPLIER=int(os.environ.get('JBGS_LOCAL_PRIOR_INSIDE','0'))
assert INSIDE_MULTIPLIER in (0,1)
MASKS={}
MASK_COUNTS={}
SEEN=set()

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()

def setup():
    import jbgs_mvs_pgsr as integration
    if BRANCH=='da3':
        native=integration.Controller.load_mvs_depth_set
        def load(self,all_cameras,target_size,*,train_camera_names):
            # Retain original camera/calibration and binding validation, then replace targets.
            original=native(self,all_cameras,target_size,train_camera_names=train_camera_names)
            del original
            r=json.loads(Path('/da3/receipt.json').read_text())
            assert r['status']=='PASS_TRAIN_ONLY_DEPTH_GENERATION' and r['full_region'] is True
            split=json.loads(Path('/input/scene/split_manifest.json').read_text())
            assert r['region']==split['region']
            recorded={name:entry for batch in r['batches'] for name,entry in batch['files'].items()}
            maps={};rows=[]
            for v in split['train']:
                name=Path(v['name']).stem;rel='raw_depth_upsampled/'+name+'.npy';p=Path('/da3')/rel
                expected=recorded[rel];assert sha(p)==expected
                d=np.load(p,allow_pickle=False);assert d.shape==target_size and d.dtype==np.float32
                maps[name]=torch.from_numpy(d);rows.append(dict(name=name,sha256=expected,valid_pixels=int((np.isfinite(d)&(d>0)).sum())))
            assert set(maps)==set(train_camera_names)
            Path('/output/actual_visual_inputs.json').write_text(json.dumps(dict(source='DA3_CAMERA_Z',rows=rows,receipt_sha256=sha('/da3/receipt.json'),scientific_verdict=None)))
            return integration._DepthSet(maps)
        integration.Controller.load_mvs_depth_set=load
        def trace(self,*,iteration,camera,prior_loss,visual_loss,prior_weight,visual_weight,geometry_loss,rgb_loss):
            if iteration==8001 or iteration%100==0:
                integration._write(self.output/'mvs_pgsr_trace.jsonl',dict(iteration=iteration,camera=camera,
                    visual_source='DA3_CAMERA_Z',prior_loss=integration._value(prior_loss),mvs_loss=integration._value(visual_loss),
                    prior_weight=integration._value(prior_weight),mvs_weight=integration._value(visual_weight),
                    geometry_weighted_total=integration._value(geometry_loss),rgb_loss=integration._value(rgb_loss),
                    **self.last,scientific_verdict=None))
        integration.Controller.training_trace=trace
    elif BRANCH=='local_prior0':
        r=json.loads(Path('/masks/receipt.json').read_text());assert r['status']=='PASS' and r['reviewed_correction_surfaces'] is True
        for row in r['masks']:
            p=Path('/masks')/row['path'];assert sha(p)==row['sha256']
            a=np.load(p,allow_pickle=False);assert a.dtype==bool and a.ndim==2
            MASKS[row['name']]=torch.from_numpy(a);MASK_COUNTS[row['name']]=int(a.sum())
        assert sum(MASK_COUNTS.values())>0, 'No reviewed correction support: do not create a duplicate control'
        Path('/output/local_mask_binding.json').write_text(json.dumps(dict(receipt_sha256=sha('/masks/receipt.json'),counts=MASK_COUNTS,
            policy=f'Prior multiplier {INSIDE_MULTIPLIER} only on reviewed pixels; denominator is original finite positive prior support; others 1; protection native',scientific_verdict=None)))

def prior_loss(camera,iteration,native,pred_depth,gt_depth,**kwargs):
    if BRANCH!='local_prior0' or iteration<=8000 or camera not in MASKS:
        return native(pred_depth,gt_depth,**kwargs)
    assert not kwargs.get('use_scale_invariant',False)
    if gt_depth is None:return native(pred_depth,gt_depth,**kwargs)
    pred=pred_depth.squeeze(0);valid=torch.isfinite(gt_depth)&torch.isfinite(pred)&(gt_depth>0)
    mask=MASKS[camera].to(pred.device);assert mask.shape==pred.shape
    if INSIDE_MULTIPLIER==1:mask=torch.zeros_like(mask)
    if not valid.any():return native(pred_depth,gt_depth,**kwargs)
    if camera not in SEEN or iteration%100==0:
        with Path('/output/local_prior_trace.jsonl').open('a') as f:
            f.write(json.dumps(dict(iteration=iteration,camera=camera,original_valid=int(valid.sum()),
                zero_weight_valid=int((mask&valid).sum()),outside_multiplier=1,inside_multiplier=INSIDE_MULTIPLIER,
                denominator='original_valid',scientific_verdict=None))+'\n')
        SEEN.add(camera)
    return ((pred[valid]-gt_depth[valid]).abs()*(~mask[valid])).mean()
