"""Frozen rule accuracy on development and sealed holdout; no threshold selection."""
import sys
import numpy as np
from scipy import ndimage
from common import *
from target_rules import uncertainties,detection,targets
from photo_derivation import derive

PC=PH/'main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1'
WP=PH/'main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1'
W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'


def lookup(keys,query):
    order=np.argsort(keys);sortedkeys=keys[order];pos=np.searchsorted(sortedkeys,query)
    out=np.full(len(query),-1,np.int64)
    if not len(keys):return out
    good=pos<len(keys);good&=sortedkeys[np.minimum(pos,len(keys)-1)]==query
    out[good]=order[pos[good]];return out


def photo(tile,prior,ids,kind,DL,sealed):
    output=np.full(len(ids),2,np.int8);available=np.zeros(len(ids),bool)
    pointid=np.full(len(ids),'',dtype='<U100')
    for k,source in [(1,PC),(2,WP)]:
        if prior=='ALS' and k==2:continue
        if sealed:source=source/'holdout'
        pp=source/'points'/f'{tile}__{prior}.npz';mp=source/'patches'/f'{tile}__{prior}.npz'
        if not pp.exists() or not mp.exists():continue
        with np.load(pp) as z:p={key:z[key] for key in ['point_id','heights','curve','peak_mask','texture','selected_count']}
        with np.load(mp) as z:
            core=lookup(ids,z['patch_id']);owner=lookup(p['point_id'],z['point_id'])
        assert (owner>=0).all();valid=(core>=0)
        valid&=kind[np.maximum(core,0)]==k;core,owner=core[valid],owner[valid]
        assert len(np.unique(core))==len(core)
        finite=np.isfinite(DL[core]);count=np.bincount(owner[finite],minlength=len(p['point_id']))
        bound=np.full(len(count),np.nan);has=np.flatnonzero(count)
        if len(has):bound[has]=ndimage.median(DL[core[finite]],labels=owner[finite]+1,index=has+1)
        output[core]=derive(p,bound)['judgment'][owner,4]
        available[core]=True;pointid[core]=p['point_id'][owner]
    return output,available,pointid


def accuracy_rows(d,label,variant,split,prior,scope=None):
    rows=[];scope=np.ones(len(label),bool) if scope is None else scope
    for k in [1,2]:
        for labelstr,subset in [('all',np.ones(len(label),bool)),('original',~d['any_replaced']),('replaced',d['any_replaced'])]:
            m=scope&(d['kind']==k)&subset
            sig=m&np.isin(label,[2,3]);den=sig&np.isin(d['cell'],[0,1,2])
            wrong=sig&(((d['cell']==1)&(label==2))|((d['cell']==2)&(label==3)))
            total=float(d['area'][m].sum());denarea=float(d['area'][den].sum());wrongarea=float(d['area'][wrong].sum())
            row=dict(split=split,prior=prior,kind=k,replacement=labelstr,variant=variant,
                patches=int(m.sum()),area_m2=total,significant_area_m2=float(d['area'][sig].sum()),
                denominator_area_m2=denarea,wrong_area_m2=wrongarea,wrong_fraction=wrongarea/denarea if denarea else None)
            for cell in range(7):
                for lab,name in [(-1,'unavailable'),(0,'unobserved'),(1,'agreement'),(2,'preservation'),(3,'correction')]:
                    row[f'cell{cell}_{name}_area_m2']=float(d['area'][m&(d['cell']==cell)&(label==lab)].sum())
            rows.append(row)
    return rows


def main():
    cfg,lock=locked();t2=json.loads((OUT/'stage0_r1/T2.json').read_text())
    assert t2['status']=='PASS_T2_MIXTURE'
    allrows=[]
    for sealed in [False,True]:
        split='holdout' if sealed else 'development'
        root=OUT/('holdout/stage0_r1' if sealed else 'stage0_r1/development')
        root.mkdir(parents=True,exist_ok=True)
        jn=JN/'holdout' if sealed else JN;wroot=W/'holdout' if sealed else W
        source_manifest=[]
        for prior in ['ALS','LoD2']:
            pieces=[];offsets=[];start=0
            for f in sorted((jn/'core_points').glob(f'*__{prior}.npz')):
                with np.load(f) as z:
                    keys=['patch_id','building','kind','area','n','d_mean_cm','s_cm','sigma_p','normal','normal_defined','mvs_a_a','cell']
                    d={k:z[k] for k in keys}
                tile=f.stem.split('__')[0];uf=wroot/'patch_values'/f'{tile}__{prior}__R1.5.npz'
                with np.load(uf) as z:
                    ix=lookup(z['patch_id'],d['patch_id']);assert (ix>=0).all();d['raw_u']=z['mvs_a_u'][ix]
                pieces.append(d);offsets.append((tile,start,start+len(d['area'])));start+=len(d['area'])
                source_manifest.extend([{'path':str(p),'sha256':sha(p)} for p in [f,uf]])
            if not pieces:continue
            d={k:np.concatenate([p[k] for p in pieces]) for k in pieces[0]};del pieces
            values,med=uncertainties(d['raw_u'],d['sigma_p'],d['mvs_a_a'],d['kind'],d['building'])
            d.update(values);dist=d['d_mean_cm']/100.;s=d['s_cm']/100.
            DL=detection(d['n'],s,d['u'],d['sigma_p'])
            DLa=detection(d['n'],s,d['a_sensitivity'],d['sigma_p'])
            photos=np.full(len(dist),2,np.int8);photosa=photos.copy();avail=np.zeros(len(dist),bool)
            photo_ids=np.full(len(dist),'',dtype='<U100')
            for tile,a,b in offsets:
                photos[a:b],avail[a:b],photo_ids[a:b]=photo(tile,prior,d['patch_id'][a:b],d['kind'][a:b],DL[a:b],sealed)
                photosa[a:b],_,_=photo(tile,prior,d['patch_id'][a:b],d['kind'][a:b],DLa[a:b],sealed)
            label,h,sigma=targets(d['n'],dist,DL,d['u'],d['sigma_p'],d['normal'],t2['fits']['main_u']['T2_m'],photos)
            variants={'main':label}
            different=np.isin(label,[2,3])
            for name,value in [('prior_only',2),('mvs_only',3)]:
                ll=label.copy();ll[different]=value;variants[name]=ll
            ll=label.copy();ll[different]=np.where(np.abs(dist[different])>t2['fits']['main_u']['T2_m'],3,2);variants['T2_only']=ll
            ll=label.copy();ll[different]=np.where(photos[different]==1,3,2);variants['photo_only']=ll
            if t2['fits']['sensitivity_a']['T2_m'] is not None:
                variants['sensitivity_a']=targets(d['n'],dist,DLa,d['a_sensitivity'],d['sigma_p'],d['normal'],t2['fits']['sensitivity_a']['T2_m'],photosa)[0]
            for name,ll in variants.items():allrows.extend(accuracy_rows(d,ll,name,split,prior))
            # Holdout per-patch rows and identifiers never go under DOC or public payload folders.
            output=dict(patch_id=d['patch_id'],building=d['building'],kind=d['kind'],area=d['area'],cell=d['cell'],
                region=label,h=h,sigma=sigma,DL=DL,DL_a=DLa,photo=photos,photo_available=avail,
                photo_point_id=photo_ids,u=d['u'],sigma_p=d['sigma_p'],u_replaced=d['u_replaced'],
                sigma_p_replaced=d['sigma_p_replaced'],any_replaced=d['any_replaced'])
            for tile,a,b in offsets:np.savez_compressed(root/f'{tile}__{prior}.npz',**{k:v[a:b] for k,v in output.items()})
            dump(root/f'{prior}_medians.json',med)
            print('JUDGMENT_CENSUS',split,prior,len(dist),'patches',flush=True)
        dump(root/'inputs.json',{'files':source_manifest,'config_sha256':lock['config_sha256'],'scientific_verdict':None})
    dump(DOC/'tables/judgment_accuracy_r1.json',dict(rows=allrows,source_tag='[이 발주에서 냄]',
        holdout_public_fields='counts, areas and ratios only; no per-patch values',scientific_verdict=None))
    dump(OUT/'stage0_r1/judgment_census_complete.json',dict(status='COMPLETE',at=stamp(),config_sha256=lock['config_sha256'],scientific_verdict=None))


if __name__=='__main__':main()
