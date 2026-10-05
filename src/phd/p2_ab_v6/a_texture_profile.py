"""Candidate-local contrast handling: a wrong flat offset cannot erase the curve."""
import numpy as np

AUDIT_COUNTS={}


def zncc_profiles(reference,target,mask,cfg,audit_label='unspecified'):
    n=mask.sum(1);weights=mask[:,None,:].astype(np.float64)
    a=reference[:,None,:];b=target
    ma=(a*weights).sum(-1)/np.maximum(n[:,None],1)
    mb=(b*weights).sum(-1)/np.maximum(n[:,None],1)
    da=(a-ma[...,None])*weights;db=(b-mb[...,None])*weights
    va=(da*da).sum(-1);vb=(db*db).sum(-1)
    stdref=np.sqrt(va[:,0]/np.maximum(n,1));stdtarget=np.sqrt(vb/np.maximum(n[:,None],1))
    threshold=cfg['minimum_patch_std']
    support=n>=cfg['minimum_patch_pixels'];ref_good=stdref>=threshold
    informative=stdtarget>=threshold
    old_valid=support&ref_good&informative.all(1)
    valid=support&ref_good&informative.any(1)
    # Clamp the candidate contrast norm; a flat target has neutral correlation 0,
    # while textured offsets retain ordinary ZNCC. No best-offset selection here.
    floor=(threshold**2)*n[:,None]
    corr=(da*db).sum(-1)/np.sqrt(np.maximum(va*np.maximum(vb,floor),1e-20))
    cost=(1-np.clip(corr,-1,1))/2
    cost[~valid]=np.nan
    stats=AUDIT_COUNTS.setdefault(audit_label,{k:0 for k in ['curves','pixel_support','low_reference_texture','any_low_target_texture','all_low_target_texture','old_valid','new_valid','restored_wrong_offset_target_texture']})
    for key,value in dict(curves=len(n),pixel_support=support.sum(),low_reference_texture=(support&~ref_good).sum(),
        any_low_target_texture=(support&ref_good&~informative.all(1)).sum(),all_low_target_texture=(support&ref_good&~informative.any(1)).sum(),
        old_valid=old_valid.sum(),new_valid=valid.sum(),restored_wrong_offset_target_texture=(valid&~old_valid).sum()).items():stats[key]+=int(value)
    return cost.astype(np.float32),n.astype(np.int16),stdref.astype(np.float32)
