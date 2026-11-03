"""Calibrate photo threshold from unchanged agreement sample; classify all safe points."""
import json,sys,warnings
import numpy as np
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz,savez
from record_setting_reply2 import record as record_setting
BASE=O/'r2'
GROUPS=[('ALS',1),('LoD2',1),('LoD2',2)]
PHOTO_LABELS={0:'지지',1:'반박',2:'애매(둘 다 낮음)',3:'애매(둘 다 높음)',4:'애매(MVS 면 없음)',5:'애매(조각 부족)',6:'무늬 없음',7:'사진 부족',8:'옛 판 애매',9:'미계산/범위 없음'}
def weighted_quantile(x,w,q):
    m=np.isfinite(x)&np.isfinite(w)&(w>0);x=x[m];w=w[m]
    if not len(x):return np.nan
    ix=np.argsort(x,kind='stable');x=x[ix];w=w[ix];return float(x[min(np.searchsorted(np.cumsum(w),q*w.sum(),side='left'),len(x)-1)])
def old_photo(g,prior):
    h=g['heights'].astype(float);curve=g['curve'].astype(float);b=g['b_m'];centre=g['core_prior_height_median_m'] if prior=='ALS' else np.zeros(len(b))
    dh=abs(h-centre[:,None]);inside=dh<=b[:,None];outside=(dh>b[:,None])&(g['peak_mask']|(dh>b[:,None]+.3))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning);si=np.nanmax(np.where(inside,curve,np.nan),axis=1);so=np.nanmax(np.where(outside,curve,np.nan),axis=1)
    code=np.full(len(b),8,np.int8);diff=si-so
    code[(diff>=.10)&(si>=.3)]=0;code[(diff<=-.10)&(so>=.3)]=1
    code[~np.isfinite(b)|~np.isfinite(centre)]=9;code[g['texture']<5]=6;code[g['selected_count']<3]=7
    code=np.select([code==8,code==6,code==7],[2,3,4],default=code).astype('i1')
    return code,si,so

def corrected(scores,texture,selected,available,t):
    N=scores.shape[0];out=np.full(N,9,np.int8)
    if np.isfinite(t):
        p=scores[:,0];m=scores[:,1];out[(p<t)&(m>=t)]=1;out[(p>=t)&(m<t)]=0;out[(p<t)&(m<t)]=2;out[(p>=t)&(m>=t)]=3
        out[~np.isfinite(scores).all(1)]=5
    out[~available[:,1]]=4;out[(texture<5).all(1)]=6;out[((selected>=0).sum(-1)<3).any(1)]=7
    return out

def main(group):
    prior,kind=GROUPS[group];pieces=[];threshold_x=[];threshold_w=[];source_hashes={}
    for p in sorted((BASE/'photo_targets').glob(f'*__{prior}__{kind}.npz')):
        g=loadz(p);tile=p.stem.split('__')[0];N=len(g['point_id']);target=g['target_type']>0
        best=np.full((2,N,2),np.nan);height=best.copy();tex=best.copy();selected=np.full((N,2,10),-1,np.int32);avail=np.zeros((N,2),bool);angle=np.full(N,np.nan);fitcount=np.zeros(N,np.int32);fitreason=np.full(N,'not_target',dtype='<U32');maskfraction=np.full((N,2),np.nan);computed=np.zeros(N,bool)
        centres=np.full((N,2,3),np.nan);normals=centres.copy();residual=np.full(N,np.nan);axis_height=np.full((N,2),np.nan);bestmask=np.full((N,2),np.nan)
        if target.any():
            prep=BASE/'photo_prepared'/f'{tile}.npz';z=loadz(prep);ix=np.flatnonzero(z['group']==group)
            dest=BASE/'photo_scores'/tile;sub=dest/f'group{group}'
            if (dest/'complete.json').exists():sc=loadz(dest/'scores.npz');jj=ix
            else:assert (sub/'complete.json').exists(),str(sub);sc=loadz(sub/'scores.npz');jj=np.arange(len(ix))
            owners=z['source_index'][ix];assert np.array_equal(sc['point_id'][jj],g['point_id'][owners]);assert np.array_equal(np.sort(owners),np.flatnonzero(target))
            for out,key in [(best,'best_score'),(height,'best_height'),(tex,'texture')]:out[:,owners]=sc[key][:,jj]
            selected[owners]=z['selected_images'][ix];avail[owners]=z['available'][ix];selected[~avail]=-1
            angle[owners]=z['mvs_normal_angle_deg'][ix];fitcount[owners]=z['mvs_fit_count'][ix];fitreason[owners]=z['mvs_fit_reason'][ix];maskfraction[owners]=z['mask_fraction_at_zero'][ix];computed[owners]=True
            centres[owners]=z['centres'][ix];normals[owners]=z['normals'][ix];residual[owners]=z['mvs_fit_nmad_m'][ix]
            axis_height[owners]=np.einsum('npj,nj->np',z['centres'][ix]-g['centre'][owners,None,:],z['normals'][ix,0])
            for owner,zi in zip(owners,ix):
                for face in range(2):
                    l,r=z['plane_row_ptr'][2*zi+face:2*zi+face+2];hits=np.flatnonzero(np.isclose(z['row_height'][l:r],height[0,owner,face],atol=1e-12,rtol=0))
                    if len(hits):bestmask[owner,face]=np.unpackbits(z['mask_bits'][l+hits[0]],count=625).mean()
            source_hashes[str(prep)]=sha(prep);source_hashes[str((dest if (dest/'complete.json').exists() else sub)/'scores.npz')]=sha((dest if (dest/'complete.json').exists() else sub)/'scores.npz')
        sample=g['target_type2'];threshold_x.append(best[0,sample,0]);threshold_w.append(g['eligible_area_m2'][sample])
        old,si,so=old_photo(g,prior)
        out=dict(point_id=g['point_id'],prior=np.full(N,prior),kind=np.full(N,kind,np.int8),split=np.full(N,'development'),building=g['building'],centre=g['centre'],b_m=g['b_m'],core_d_median_m=g['core_d_median_m'],core_prior_height_median_m=g['core_prior_height_median_m'],
            target_type=g['target_type'],target_type_bits=g['target_type_bits'],sweep_defined=g['sweep_defined'],eligible_area_m2=g['eligible_area_m2'],computed=computed,best_score=best,best_height=height,texture=tex,selected_images=selected,selected_count=(selected>=0).sum(-1).astype('i1'),available=avail,
            plane_centres=centres,plane_normals=normals,plane_axis_height_m=axis_height,mvs_fit_nmad_m=residual,
            mvs_normal_angle_deg=angle,mvs_fit_count=fitcount,mvs_fit_reason=fitreason,mask_fraction_at_zero=maskfraction,mask_fraction_at_best_clipped=bestmask,old_code=old,old_s_in=si,old_s_out=so)
        pieces.append((p.name,out))
    x=np.concatenate(threshold_x);w=np.concatenate(threshold_w);t=weighted_quantile(x,w,.05);t10=weighted_quantile(x,w,.10)
    record=dict(at=now(),group=f'{prior}_{kind}',t=float(t) if np.isfinite(t) else None,t10=float(t10) if np.isfinite(t10) else None,
        sample_points=len(x),finite_score_points=int(np.isfinite(x).sum()),sample_area_m2=float(w.sum()),finite_score_area_m2=float(w[np.isfinite(x)].sum()),
        rule='area-weighted inverted empirical CDF; clipped P score; same t for clipped/unclipped sensitivity',truth_used=False,
        source_sha256=sha(Path(__file__)),sources=source_hashes,excluded_shared_cores=dict(count=73,area_m2=5.442552935831812),scientific_verdict=None)
    dump(C/f'photo_threshold.{prior}_{kind}.reply2.lock.json',record);dump(D/'tables'/f'photo_threshold_{prior}_{kind}.json',record)
    current=json.loads((C/'judgecheck_v1.json').read_text())['photos'].get('t') or {};current[f'{prior}_{kind}']=record['t']
    record_setting('photos','t',current,'Stage A unchanged agreement-sample weighted fifth percentile, frozen before photo judgment; reference data not used')
    for name,d in pieces:
        codes=np.array([corrected(d['best_score'][mode],d['texture'][mode],d['selected_images'],d['available'],t) for mode in range(2)])
        codes[:,~d['computed']|~d['sweep_defined']]=9;d['new_code']=codes;savez(BASE/'photo_points'/name,**d)
    dump(BASE/'photo_points'/f'{prior}_{kind}.complete.json',dict(at=now(),files=len(pieces),points=sum(len(d['point_id']) for _,d in pieces),t=record['t'],scientific_verdict=None))
    print('PHOTO_JUDGMENT_COMPLETE',prior,kind,'t',record['t'],flush=True)
if __name__=='__main__':main(int(sys.argv[1]))
