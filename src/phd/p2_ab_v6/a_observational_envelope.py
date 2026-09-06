"""Current-image plane-warp evidence, explicitly not calibrated source authority."""
from __future__ import annotations
import numpy as np
from scipy.spatial import cKDTree
import cv2


def native_anchors(seed, spacing):
    key=np.column_stack((seed["native_patch_id"],np.floor(seed["xyz"]/spacing).astype(np.int64)))
    _,indices=np.unique(key,axis=0,return_index=True)
    return np.sort(indices)


def map_same_patch(seed,anchors,max_distance,min_cosine):
    ids=np.full(len(seed["xyz"]),-1,np.int64)
    distances=np.full(len(ids),np.inf,np.float32)
    for patch in np.unique(seed["native_patch_id"]):
        si=np.flatnonzero(seed["native_patch_id"]==patch)
        ai=np.flatnonzero(seed["native_patch_id"][anchors]==patch)
        if not len(ai):continue
        d,k=cKDTree(seed["xyz"][anchors[ai]]).query(seed["xyz"][si])
        chosen=ai[k]
        cosine=np.einsum("ij,ij->i",seed["normals"][si],seed["normals"][anchors[chosen]])
        good=(d<=max_distance)&(cosine>=min_cosine)
        ids[si[good]]=chosen[good];distances[si]=d
    return ids,distances


def sample(array,uv,nearest=False):
    shape=uv.shape[:-1]
    flat=np.asarray(uv,np.float32).reshape(-1,2)
    count=len(flat);width=min(1024,max(1,count));height=(count+width-1)//width
    padded=np.full((height*width,2),-1e6,np.float32)
    padded[:count]=np.nan_to_num(flat,nan=-1e6,posinf=-1e6,neginf=-1e6)
    # Camera convention: pixel centres at index+.5, array centres at integer.
    values=cv2.remap(array,(padded[:,0]-.5).reshape(height,width),(padded[:,1]-.5).reshape(height,width),
        cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)
    return values.reshape(-1)[:count].reshape(shape)


def project(xyz,view):
    camera=xyz@view["R"].T+view["t"]
    uvh=camera@view["K"].T
    return uvh[...,:2]/np.maximum(uvh[...,2:],1e-8),camera[...,2]


def view_eligibility(xyz,normals,views,cfg):
    visible=[];directions=[];qualities=[]
    for view in views:
        uv,z=project(xyz,view)
        v=view["center"]-xyz;v/=np.maximum(np.linalg.norm(v,axis=1,keepdims=True),1e-8)
        cosine=np.abs(np.einsum("ij,ij->i",normals,v))
        depth=sample(view["context_depth"],uv,True)
        inside=(z>0)&(uv[:,0]>=cfg["patch_radius_px"]+.5)&(uv[:,1]>=cfg["patch_radius_px"]+.5)
        inside&=(uv[:,0]<view["width"]-cfg["patch_radius_px"]-.5)&(uv[:,1]<view["height"]-cfg["patch_radius_px"]-.5)
        known_foreground=(depth>0)&(depth+cfg["foreground_gap_m"]<z)
        good=inside&(sample(view["valid"],uv,True)>.5)&~known_foreground&(cosine>=cfg["minimum_view_normal_cosine"])
        visible.append(good);directions.append(v);qualities.append(np.where(good,cosine,-1.))
    return np.stack(visible),np.stack(directions),np.stack(qualities)


def choose_pairs(xyz,normals,views,cfg):
    visible,directions,quality=view_eligibility(xyz,normals,views,cfg)
    ref=quality.argmax(0);col=np.arange(len(xyz));reference_direction=directions[ref,col]
    cosine=np.einsum("vnc,nc->vn",directions,reference_direction)
    angle=np.arccos(np.clip(cosine,-1,1))*180/np.pi
    good=visible&(angle>=cfg["minimum_pair_angle_deg"])&(angle<=cfg["maximum_pair_angle_deg"])
    score=np.where(good,np.sin(angle*np.pi/180)*np.maximum(quality,0),-1)
    target=score.argmax(0)
    valid=(quality[ref,col]>=0)&(score[target,col]>0)
    ref[~valid]=-1;target[~valid]=-1
    return ref,target,np.where(valid,angle[target,col],0).astype(np.float32)


def plane_samples(reference_xyz,plane_xyz,normals,offsets,ref,target,cfg):
    """Fixed reference pixels for every displacement and both source hypotheses."""
    uv,_=project(reference_xyz,ref)
    uv=np.floor(uv)+.5
    radius=cfg["patch_radius_px"]
    dy,dx=np.mgrid[-radius:radius+1,-radius:radius+1]
    pix=uv[:,None,:]+np.stack((dx,dy),axis=-1).reshape(1,-1,2)
    hom=np.concatenate((pix,np.ones((*pix.shape[:-1],1))),axis=-1)
    ray=hom@np.linalg.inv(ref["K"]).T@ref["R"]
    denom=np.einsum("npc,nc->np",ray,normals)
    numerator=np.einsum("nc,nc->n",plane_xyz-ref["center"],normals)
    distance=(numerator[:,None,None]+offsets[None,:,None])/np.where(np.abs(denom[:,None,:])>1e-8,denom[:,None,:],np.nan)
    world=ref["center"]+distance[...,None]*ray[:,None,:,:]
    target_uv,target_z=project(world,target)
    gray_ref=sample(ref["gray"],pix)
    gray_target=sample(target["gray"],target_uv)
    validity=(distance>0)&np.isfinite(distance)&(target_z>0)
    validity&=(sample(target["valid"],target_uv,True)>.5)
    context=sample(target["context_depth"],target_uv,True)
    validity&=~((context>0)&(context+cfg["foreground_gap_m"]<target_z))
    refcontext=sample(ref["context_depth"],pix,True)
    validity&=~((refcontext[:,None,:]>0)&(refcontext[:,None,:]+cfg["foreground_gap_m"]<distance))
    validity&=(sample(ref["valid"],pix,True)[:,None,:]>.5)
    # Same fixed pixels across the complete offset grid; no shrinking at a good fit.
    common=validity.all(axis=1)
    return gray_ref,gray_target,common


def zncc_profiles(reference,target,mask,cfg):
    n=mask.sum(1)
    weights=mask[:,None,:].astype(np.float64)
    a=reference[:,None,:];b=target
    ma=(a*weights).sum(-1)/np.maximum(n[:,None],1)
    mb=(b*weights).sum(-1)/np.maximum(n[:,None],1)
    da=(a-ma[...,None])*weights;db=(b-mb[...,None])*weights
    va=(da*da).sum(-1);vb=(db*db).sum(-1)
    corr=(da*db).sum(-1)/np.sqrt(np.maximum(va*vb,1e-20))
    cost=(1-np.clip(corr,-1,1))/2
    stdref=np.sqrt(va[:,0]/np.maximum(n,1));stdtarget=np.sqrt(vb/np.maximum(n[:,None],1))
    valid=(n>=cfg["minimum_patch_pixels"])&(stdref>=cfg["minimum_patch_std"])&(stdtarget.min(1)>=cfg["minimum_patch_std"])
    cost[~valid]=np.nan
    return cost.astype(np.float32),n.astype(np.int16),stdref.astype(np.float32)


def observational_envelopes(costs,offsets,cfg):
    """Union two disjoint-view basins; reject ambiguity; use-error conditional only."""
    n=len(costs);lo=np.zeros(n,np.float32);hi=lo.copy();target=lo.copy()
    allowed_lo=lo.copy();allowed_hi=lo.copy();valid=np.zeros(n,bool)
    reasons=np.full(n,1,np.uint8)
    basin=np.zeros(costs.shape,bool)
    for i in range(n):
        if not np.isfinite(costs[i]).all():continue
        minima=costs[i].argmin(1)
        if (costs[i].min(1)>cfg["maximum_best_cost"]).any():reasons[i]=2;continue
        b=costs[i]<=costs[i].min(1)[:,None]+cfg["basin_cost_slack"]
        basin[i]=b
        if b[:,0].any() or b[:,-1].any():reasons[i]=3;continue
        if any(np.count_nonzero(np.diff(np.r_[False,row,False].astype(np.int8))==1)!=1 for row in b):reasons[i]=4;continue
        if abs(float(offsets[minima[0]]-offsets[minima[1]]))>cfg["maximum_group_minimum_separation_m"]+1e-6:reasons[i]=5;continue
        half=float(np.max(np.diff(offsets)))/2
        union=b.any(0)
        lo[i]=float(offsets[union].min())-half;hi[i]=float(offsets[union].max())+half
        eps=cfg["normal_use_error_epsilon_m"]
        allowed_lo[i]=hi[i]-eps;allowed_hi[i]=lo[i]+eps
        if allowed_lo[i]>allowed_hi[i]:reasons[i]=6;continue
        target[i]=np.clip(float(offsets[costs[i].mean(0).argmin()]),allowed_lo[i],allowed_hi[i])
        valid[i]=True;reasons[i]=0
    return dict(observation_low_m=lo,observation_high_m=hi,allowed_low_m=allowed_lo,allowed_high_m=allowed_hi,
        target_m=target,observable=valid,reason_code=reasons,admissible_grid=basin,
        initial_eligible=valid&(allowed_lo<=0)&(allowed_hi>=0),
        correction_needed=valid&((allowed_lo>0)|(allowed_hi<0)),
        initial_max_use_error_m=np.maximum(np.abs(lo),np.abs(hi)))
