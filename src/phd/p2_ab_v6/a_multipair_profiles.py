"""All geometrically admissible decision-view pairs; robust group aggregation."""
import numpy as np
from src.phd.p2_ab_v6.a_observational_envelope import view_eligibility,plane_samples,zncc_profiles


def aggregate_pairs(costs,minimum_pairs):
    """A complete curve is either valid or missing; never select lowest photo cost."""
    valid=np.isfinite(costs).all(-1)
    count=valid.sum(-1)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        profile=np.nanmedian(np.where(valid[...,None],costs,np.nan),axis=-2)
    profile[count<minimum_pairs]=np.nan
    return profile.astype(np.float32),count.astype(np.int16)


def profile_source(seed,anchor,als,als_rows,views,cfg):
    xyz=seed['xyz'][anchor];normal=seed['normals'][anchor];offset=np.asarray(cfg['offsets_m'],np.float32)
    n=len(anchor);npair=max(len(g)*(len(g)-1)//2 for g in cfg['view_groups'])
    shape=(n,2,npair,len(offset))
    pair_cost=np.full(shape,np.nan,np.float32);als_pair_cost=pair_cost.copy();paired_mvs=pair_cost.copy();paired_als=pair_cost.copy()
    pair_pixels=np.zeros((n,2,npair),np.int16);als_pair_pixels=pair_pixels.copy();paired_pixels=pair_pixels.copy()
    pair_ids=np.full((n,2,npair,2),-1,np.int32);pair_angles=np.zeros((n,2,npair),np.float32)
    for g,group in enumerate(cfg['view_groups']):
        gv=[views[i]for i in group]
        visible,directions,quality=view_eligibility(xyz,normal,gv,cfg)
        pindex=0
        for i in range(len(gv)):
            for j in range(i+1,len(gv)):
                cosine=np.einsum('nc,nc->n',directions[i],directions[j]);angle=np.arccos(np.clip(cosine,-1,1))*180/np.pi
                good=visible[i]&visible[j]&(angle>=cfg['minimum_pair_angle_deg'])&(angle<=cfg['maximum_pair_angle_deg'])
                for ri,ti,side in [(i,j,quality[i]>=quality[j]),(j,i,quality[j]>quality[i])]:
                    selected=np.flatnonzero(good&side);a=gv[ri];b=gv[ti]
                    pair_ids[selected,g,pindex]=[a['image_id'],b['image_id']];pair_angles[selected,g,pindex]=angle[selected]
                    for start in range(0,len(selected),256):
                        ii=selected[start:start+256]
                        refgray,targetgray,mask=plane_samples(xyz[ii],xyz[ii],normal[ii],offset,a,b,cfg)
                        cost,npx,_=zncc_profiles(refgray,targetgray,mask,cfg);pair_cost[ii,g,pindex]=cost;pair_pixels[ii,g,pindex]=npx
                        paired=np.flatnonzero(als_rows[ii]>=0)
                        if len(paired):
                            jj=ii[paired];aa=als_rows[jj]
                            ar,at,am=plane_samples(xyz[jj],als['xyz'][aa],als['normals'][aa],offset,a,b,cfg)
                            ac,an,_=zncc_profiles(ar,at,am,cfg);als_pair_cost[jj,g,pindex]=ac;als_pair_pixels[jj,g,pindex]=an
                            common=mask[paired]&am
                            mc,pn,_=zncc_profiles(refgray[paired],targetgray[paired],common,cfg)
                            ac,_,_=zncc_profiles(ar,at,common,cfg)
                            paired_mvs[jj,g,pindex]=mc;paired_als[jj,g,pindex]=ac;paired_pixels[jj,g,pindex]=pn
                print('group',g,'pair',pindex+1,'/',npair,'geometric anchors',int(good.sum()),'validprofiles',int(np.isfinite(pair_cost[:,g,pindex]).all(1).sum()),flush=True)
                pindex+=1
    minimum=cfg['minimum_valid_pairs_per_group']
    costs,count=aggregate_pairs(pair_cost,minimum);als_costs,als_count=aggregate_pairs(als_pair_cost,minimum)
    # Pairwise source comparison uses exactly the same surviving pair identities.
    both=np.isfinite(paired_mvs).all(-1)&np.isfinite(paired_als).all(-1)
    paired_mvs[~both]=np.nan;paired_als[~both]=np.nan
    pm,pc=aggregate_pairs(paired_mvs,minimum);pa,_=aggregate_pairs(paired_als,minimum)
    return dict(costs=costs,als_costs=als_costs,paired_mvs=pm,paired_als=pa,
        pixels=pair_pixels.sum(2).clip(max=32767).astype(np.int16),als_pixels=als_pair_pixels.sum(2).clip(max=32767).astype(np.int16),paired_pixels=paired_pixels.sum(2).clip(max=32767).astype(np.int16),
        pairs=pair_ids,angles=pair_angles,valid_pair_count=count,als_valid_pair_count=als_count,paired_valid_pair_count=pc,
        pair_cost=pair_cost,als_pair_cost=als_pair_cost,common_pair_mvs_cost=paired_mvs,common_pair_als_cost=paired_als,pair_pixels=pair_pixels,als_pair_pixels=als_pair_pixels,common_pair_pixels=paired_pixels)
